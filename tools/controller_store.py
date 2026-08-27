"""Rebuildable Controller journal, materialized view, and scheduling lock."""

from __future__ import annotations

import errno
import fcntl
import hashlib
import json
import os
import re
import tempfile
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, NoReturn, Self, cast

if TYPE_CHECKING:
    from collections.abc import Mapping

# Keep this tooling module importable both through the CLI and as a standalone
# test target, without making the policy depend on the filesystem.
import sys

sys.path.insert(0, str(Path(__file__).parent))

import controller_policy as policy

JOURNAL_SCHEMA: Final = "controller-journal/v1"
VIEW_SCHEMA: Final = "controller-view/v1"
JOURNAL_NAME: Final = "journal.jsonl"
VIEW_NAME: Final = "view.json"
LOCK_NAME: Final = "scheduling.lock"
STARTED_MARKER_CONTENT: Final = "controller-state/v1\n"
PHASES: Final = ("planned", "applied", "confirmed")
JOURNAL_FIELDS: Final = frozenset(
    {"schema", "cycle_id", "phase", "recorded_at", "recorded_by", "payload"}
)
PAYLOAD_FIELDS: Final = frozenset({"facts", "lifecycle", "actions"})
PLAN_FIELDS: Final = frozenset(
    {
        "revision_id",
        "initiative_key",
        "desired_outcome_key",
        "desired_outcome_revision",
        "content_digest",
    }
)
FACTS_FIELDS: Final = frozenset(
    {"configured_curator", "desired_outcomes", "initiatives", "work_items", "work_runs"}
)
DESIRED_OUTCOME_FIELDS: Final = frozenset({"key", "revision", "content_digest"})
DESIRED_OUTCOME_OPTIONAL_FIELDS: Final = frozenset({"content", "parent_issue"})
SHA256: Final = re.compile(r"[0-9a-f]{64}\Z")
LIFECYCLE_FACT_FIELDS: Final = frozenset({"key", "state"})
VIEW_FIELDS: Final = frozenset({"schema", "journal_sha256", "last_cycle_id", "confirmed"})


class ControllerStateUnreadableError(RuntimeError):
    """Local Controller state was absent, damaged, or incomplete."""

    code: Final = "controller_state_unreadable"

    def __init__(self, reason: str) -> None:
        """Expose a typed refusal rather than deriving a confident state."""
        self.reason = reason
        super().__init__(f"refusal={self.code} reason={reason}")


class ControllerLockHeldError(RuntimeError):
    """Another scheduling writer owns the singleton lock."""

    code: Final = "controller_lock_held"

    def __init__(self, path: Path) -> None:
        """Expose the lock refusal and its exact path."""
        self.path = path
        super().__init__(f"refusal={self.code} path={path}")


class ControllerActionUnsupportedError(RuntimeError):
    """A future action has no registered external port."""

    code: Final = "controller_action_unsupported"

    def __init__(self, action_kind: str) -> None:
        """Expose the unsupported action as a named refusal."""
        self.action_kind = action_kind
        super().__init__(f"refusal={self.code} action={action_kind}")


# Keep the short refusal names available to callers while satisfying the
# repository's exception naming convention.
ControllerStateUnreadable = ControllerStateUnreadableError
ControllerLockHeld = ControllerLockHeldError
ControllerActionUnsupported = ControllerActionUnsupportedError


@dataclass(frozen=True, slots=True)
class LoadedControllerState:
    """The last confirmed state reconstructed from both durable surfaces."""

    confirmed: dict[str, object]
    lifecycle: policy.LifecycleState
    actions: tuple[policy.ControlAction, ...]
    last_cycle_id: str
    record_count: int
    facts: policy.ControlFacts | None = None
    plan: dict[str, object] | None = None
    phase: str = "confirmed"


class SchedulingLock:
    """A non-blocking process lock used only by scheduling writers."""

    def __init__(self, path: Path) -> None:
        """Keep the lock file outside worktrees and unopened until acquisition."""
        self.path = path
        self._handle: Any | None = None

    def acquire(self) -> None:
        """Acquire the singleton lock or raise its typed refusal immediately."""
        if self._handle is not None:
            raise ControllerLockHeld(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            handle.close()
            if error.errno in {errno.EACCES, errno.EAGAIN}:
                raise ControllerLockHeld(self.path) from error
            raise
        self._handle = handle

    def release(self) -> None:
        """Release the lock and close its descriptor."""
        if self._handle is None:
            return
        fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        self._handle.close()
        self._handle = None

    def __enter__(self) -> Self:
        """Acquire the lock for a scheduling writer context."""
        self.acquire()
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        """Release the scheduling lock."""
        self.release()


class ControllerStore:
    """Own the append-only journal and atomically rebuilt materialized view."""

    def __init__(self, root: Path) -> None:
        """Resolve all local Controller state beneath one caller-supplied root."""
        self.root = root

    @property
    def journal_path(self) -> Path:
        """Return the durable transition journal path."""
        return self.root / JOURNAL_NAME

    @property
    def view_path(self) -> Path:
        """Return the atomically materialized view path."""
        return self.root / VIEW_NAME

    @property
    def lock_path(self) -> Path:
        """Return the singleton scheduling lock path."""
        return self.root / LOCK_NAME

    @property
    def plans_root(self) -> Path:
        """Return the exact validated-plan store root."""
        return self.root / "plans"

    @property
    def started_marker_path(self) -> Path:
        """Return the durable marker kept outside removable controller state."""
        return self.root.parent / f".{self.root.name}.started"

    def is_fresh(self) -> bool:
        """Distinguish never-started state from an interrupted controller."""
        if self._started_marker_exists():
            return False
        return not self.journal_path.exists() and not self.view_path.exists()

    def mark_started(self) -> None:
        """Publish controller intent before taking the scheduling lock."""
        if self._started_marker_exists():
            return
        marker = self.started_marker_path
        try:
            marker.parent.mkdir(parents=True, exist_ok=True)
            with marker.open("x", encoding="utf-8") as handle:
                handle.write(STARTED_MARKER_CONTENT)
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError:
            self._started_marker_exists()
            return
        except (OSError, UnicodeError) as error:
            _refuse(f"controller_bootstrap_marker_write_failed:{error}")
        try:
            _fsync_directory(marker.parent)
        except OSError as error:
            _refuse(f"controller_bootstrap_marker_write_failed:{error}")

    def recover_interrupted_bootstrap(self) -> None:
        """Clear an empty started marker after an explicit recovery request."""
        with self.scheduling_lock():
            if not self._started_marker_exists():
                _refuse("controller_bootstrap_not_interrupted")
            if self.journal_path.exists() or self.view_path.exists():
                _refuse("controller_bootstrap_recovery_requires_state_review")
            try:
                self.started_marker_path.unlink()
                _fsync_directory(self.started_marker_path.parent)
            except (OSError, UnicodeError) as error:
                _refuse(f"controller_bootstrap_recovery_failed:{error}")

    def scheduling_lock(self) -> SchedulingLock:
        """Return the lock for this Controller state root."""
        return SchedulingLock(self.lock_path)

    def next_cycle_number(
        self,
        previous: LoadedControllerState | None = None,
        *,
        fresh_start: bool = False,
    ) -> int:
        """Return the next cycle ordinal after validating existing state."""
        if fresh_start and previous is None:
            return 1
        state = previous
        if state is None:
            if self.is_fresh():
                return 1
            state = self.load()
        return state.record_count // len(PHASES) + 1

    def append_phase(
        self,
        cycle_id: str,
        phase: str,
        payload: Mapping[str, object],
        *,
        recorded_at: str,
        recorded_by: str,
    ) -> None:
        """Append one durable planned/applied/confirmed transition record."""
        if phase not in PHASES:
            raise ValueError(phase)
        if not cycle_id or not recorded_at or not recorded_by:
            raise ValueError
        document = _payload_document(payload)
        self.root.mkdir(parents=True, exist_ok=True)
        record = {
            "schema": JOURNAL_SCHEMA,
            "cycle_id": cycle_id,
            "phase": phase,
            "recorded_at": recorded_at,
            "recorded_by": recorded_by,
            "payload": document,
        }
        try:
            with self.journal_path.open("a", encoding="utf-8") as handle:
                handle.write(_json_line(record))
                handle.flush()
                os.fsync(handle.fileno())
        except (OSError, UnicodeError) as error:
            detail = f"journal_write_failed:{error}"
            raise ControllerStateUnreadable(detail) from error

    def write_cycle(
        self,
        cycle_id: str,
        payload: Mapping[str, object],
        *,
        recorded_at: str,
        recorded_by: str,
    ) -> None:
        """Arrange or write one complete three-phase cycle and its view."""
        for phase in PHASES:
            self.append_phase(
                cycle_id,
                phase,
                payload,
                recorded_at=recorded_at,
                recorded_by=recorded_by,
            )
        self.materialize_view()

    def materialize_view(self) -> None:
        """Atomically write the view only after a complete journal can be read."""
        records = self._read_records()
        final = records[-1]
        view = {
            "schema": VIEW_SCHEMA,
            "journal_sha256": _sha256(self.journal_path.read_bytes()),
            "last_cycle_id": final["cycle_id"],
            "confirmed": final["payload"],
        }
        _atomic_write(self.view_path, view)

    def load(self) -> LoadedControllerState:
        """Rebuild state from the journal and verify the materialized view agrees."""
        records = self._read_records()
        view = self._read_view()
        final = records[-1]
        journal_digest = _sha256(self.journal_path.read_bytes())
        if view["journal_sha256"] != journal_digest:
            _refuse("view_journal_digest_mismatch")
        if view["last_cycle_id"] != final["cycle_id"]:
            _refuse("view_last_cycle_mismatch")
        if view["confirmed"] != final["payload"]:
            _refuse("view_confirmed_payload_mismatch")
        confirmed = _payload_document(final["payload"])
        lifecycle_raw = confirmed["lifecycle"]
        if not isinstance(lifecycle_raw, dict):
            _refuse("lifecycle_not_object")
        lifecycle = policy.LifecycleState(
            _string(lifecycle_raw, "state"),
            _nullable_string(lifecycle_raw, "admitted_initiative"),
            _string(lifecycle_raw, "reason"),
        )
        actions_raw = confirmed["actions"]
        if not isinstance(actions_raw, list):
            _refuse("actions_not_list")
        actions = tuple(_action(item) for item in actions_raw)
        facts = _facts_value(confirmed["facts"])
        plan = _plan_value(confirmed.get("plan"))
        return LoadedControllerState(
            confirmed=confirmed,
            lifecycle=lifecycle,
            actions=actions,
            last_cycle_id=_string(final, "cycle_id"),
            record_count=len(records),
            facts=facts,
            plan=plan,
        )

    def load_recoverable(self) -> LoadedControllerState:
        """Load a confirmed state or one trailing planned/applied transition for resumption."""
        records = self._read_records(allow_incomplete=True)
        remainder = len(records) % len(PHASES)
        if remainder == 0:
            return self.load()
        trailing = records[-remainder:]
        payload = _payload_document(trailing[-1]["payload"])
        if self.view_path.exists():
            view = self._read_view()
            prefix_count = len(records) - remainder
            if prefix_count == 0:
                _refuse("partial_cycle_has_view")
            journal_lines = self.journal_path.read_bytes().splitlines(keepends=True)
            prefix_bytes = b"".join(journal_lines[:prefix_count])
            if view["journal_sha256"] != _sha256(prefix_bytes):
                _refuse("view_journal_digest_mismatch")
            if view["last_cycle_id"] != records[prefix_count - 1]["cycle_id"]:
                _refuse("view_last_cycle_mismatch")
            if view["confirmed"] != records[prefix_count - 1]["payload"]:
                _refuse("view_confirmed_payload_mismatch")
            _payload_document(view["confirmed"])
        elif len(records) != remainder:
            _refuse("partial_cycle_view_missing")
        lifecycle = _lifecycle_value(payload["lifecycle"])
        actions = _actions_value(payload["actions"])
        facts = _facts_value(payload["facts"])
        plan = _plan_value(payload.get("plan"))
        completed_ids = {row["cycle_id"] for row in records[:-remainder]}
        if trailing[0]["cycle_id"] in completed_ids:
            _refuse("partial_cycle_duplicate_identity")
        return LoadedControllerState(
            confirmed=payload,
            lifecycle=lifecycle,
            actions=actions,
            last_cycle_id=_string(trailing[-1], "cycle_id"),
            record_count=len(records),
            facts=facts,
            plan=plan,
            phase=_string(trailing[-1], "phase"),
        )

    def _read_records(self, *, allow_incomplete: bool = False) -> list[dict[str, object]]:
        """Read, parse, and sequence every journal record fail-closed."""
        raw = self._journal_bytes()
        text = _journal_text(raw)
        records = [
            _parse_record(line, line_number)
            for line_number, line in enumerate(text.splitlines(), 1)
        ]
        _validate_record_sequence(records, allow_incomplete=allow_incomplete)
        return records

    def _journal_bytes(self) -> bytes:
        """Read journal bytes without turning absence into an empty state."""
        try:
            raw = self.journal_path.read_bytes()
        except FileNotFoundError as error:
            if self._started_marker_exists():
                _refuse("controller_bootstrap_interrupted")
            _refuse(f"journal_unreadable:{error}")
        except (OSError, UnicodeError) as error:
            _refuse(f"journal_unreadable:{error}")
        return raw

    def _started_marker_exists(self) -> bool:
        """Validate the intent marker without treating its absence as damage."""
        try:
            content = self.started_marker_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return False
        except (OSError, UnicodeError) as error:
            _refuse(f"controller_bootstrap_marker_unreadable:{error}")
        if content != STARTED_MARKER_CONTENT:
            _refuse("controller_bootstrap_marker_invalid")
        return True

    def _read_view(self) -> dict[str, object]:
        """Read and validate the materialized view envelope."""
        try:
            raw = self.view_path.read_text(encoding="utf-8")
            value = json.loads(raw)
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            _refuse(f"view_unreadable:{error}")
        if not isinstance(value, dict) or set(value) != VIEW_FIELDS:
            _refuse("view_fields")
        if value.get("schema") != VIEW_SCHEMA:
            _refuse("view_unknown_schema")
        for field_name in ("journal_sha256", "last_cycle_id"):
            if not isinstance(value.get(field_name), str) or not value[field_name]:
                _refuse(f"view_invalid_{field_name}")
        if not isinstance(value.get("confirmed"), dict):
            _refuse("view_confirmed_not_object")
        _payload_document(value["confirmed"])
        return value


def _payload_document(payload: Mapping[str, object]) -> dict[str, object]:
    """Validate and copy the stable payload envelope."""
    fields = set(payload)
    if fields not in {PAYLOAD_FIELDS, PAYLOAD_FIELDS | {"plan"}}:
        _refuse("payload_fields")
    facts = payload.get("facts")
    lifecycle = payload.get("lifecycle")
    actions = payload.get("actions")
    if not isinstance(facts, dict):
        _refuse("payload_facts_not_object")
    _facts_document(facts)
    if not isinstance(lifecycle, dict):
        _refuse("payload_lifecycle_not_object")
    if set(lifecycle) != {"state", "admitted_initiative", "reason"}:
        _refuse("payload_lifecycle_fields")
    _string(lifecycle, "state")
    _nullable_string(lifecycle, "admitted_initiative")
    _string(lifecycle, "reason")
    if not isinstance(actions, list):
        _refuse("payload_actions_not_list")
    for order, item in enumerate(actions, start=1):
        _action(item)
        if item["order"] != order:
            _refuse("action_order_sequence")
    document: dict[str, object] = {"facts": facts, "lifecycle": lifecycle, "actions": actions}
    if "plan" in fields:
        document["plan"] = _plan_value(payload.get("plan"))
    return document


def _plan_value(value: object) -> dict[str, object] | None:
    """Validate optional journal metadata tying actions to one stored Plan Revision."""
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != PLAN_FIELDS:
        _refuse("payload_plan_fields")
    for field_name in ("revision_id", "initiative_key", "desired_outcome_key", "content_digest"):
        _string(value, field_name)
    revision = value.get("desired_outcome_revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        _refuse("payload_plan_revision")
    digest = value["content_digest"]
    if SHA256.fullmatch(digest) is None:  # type: ignore[arg-type] — _string above validates text
        _refuse("payload_plan_digest")
    return dict(value)


def _lifecycle_value(value: object) -> policy.LifecycleState:
    """Decode one serialized lifecycle state."""
    if not isinstance(value, dict):
        _refuse("lifecycle_not_object")
    if set(value) != {"state", "admitted_initiative", "reason"}:
        _refuse("payload_lifecycle_fields")
    return policy.LifecycleState(
        _string(value, "state"),
        _nullable_string(value, "admitted_initiative"),
        _string(value, "reason"),
    )


def _actions_value(value: object) -> tuple[policy.ControlAction, ...]:
    """Decode serialized actions while preserving their order."""
    if not isinstance(value, list):
        _refuse("actions_not_list")
    actions: list[policy.ControlAction] = []
    for order, item in enumerate(value, start=1):
        action = _action(item)
        if not isinstance(item, dict) or item.get("order") != order:
            _refuse("action_order_sequence")
        actions.append(action)
    return tuple(actions)


def _facts_value(value: object) -> policy.ControlFacts:
    """Decode normalized facts from a journal payload."""
    if not isinstance(value, dict):
        _refuse("payload_facts_not_object")
    _facts_document(value)
    curator = value.get("configured_curator")
    outcomes_raw = value["desired_outcomes"]
    initiatives_raw = value["initiatives"]
    work_items_raw = value["work_items"]
    work_runs_raw = value["work_runs"]
    if not all(
        isinstance(entries, list)
        for entries in (outcomes_raw, initiatives_raw, work_items_raw, work_runs_raw)
    ):
        _refuse("facts_collection_not_list")
    outcomes = tuple(
        policy.DesiredOutcomeFact(
            _string(item, "key"),
            _positive_revision(item),
            _string(item, "content_digest"),
            _optional_text(item, "content"),
            _optional_issue(item, "parent_issue"),
        )
        for item in cast("list[dict[str, object]]", outcomes_raw)
    )
    initiatives = tuple(
        policy.InitiativeFact(_string(item, "key"), _string(item, "state"))
        for item in cast("list[dict[str, object]]", initiatives_raw)
    )
    work_items = tuple(
        policy.WorkItemFact(_string(item, "key"), _string(item, "state"))
        for item in cast("list[dict[str, object]]", work_items_raw)
    )
    work_runs = tuple(
        policy.WorkRunFact(_string(item, "key"), _string(item, "state"))
        for item in cast("list[dict[str, object]]", work_runs_raw)
    )
    return policy.ControlFacts(
        cast("str | None", curator), outcomes, initiatives, work_items, work_runs
    )


def _facts_document(facts: Mapping[str, object]) -> None:
    """Validate the normalized Control Facts envelope."""
    if set(facts) != FACTS_FIELDS:
        _refuse("facts_fields")
    curator = facts.get("configured_curator")
    if curator is not None and (not isinstance(curator, str) or not curator):
        _refuse("facts_configured_curator")
    for field_name in ("desired_outcomes", "initiatives", "work_items", "work_runs"):
        values = facts.get(field_name)
        if not isinstance(values, list):
            _refuse(f"facts_{field_name}_not_list")
        for value in values:
            _fact_entry(field_name, value)


def _fact_entry(field_name: str, value: object) -> None:
    """Validate one typed entry inside a normalized fact collection."""
    if not isinstance(value, dict):
        _refuse(f"facts_{field_name}_entry_not_object")
    expected = DESIRED_OUTCOME_FIELDS if field_name == "desired_outcomes" else LIFECYCLE_FACT_FIELDS
    actual = set(value)
    if field_name == "desired_outcomes":
        allowed = expected | DESIRED_OUTCOME_OPTIONAL_FIELDS
        if not actual.issubset(allowed) or not expected.issubset(actual):
            _refuse(f"facts_{field_name}_entry_fields")
    elif actual != expected:
        _refuse(f"facts_{field_name}_entry_fields")
    _string(value, "key")
    if field_name != "desired_outcomes":
        _string(value, "state")
        return
    revision = value.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        _refuse("facts_desired_outcomes_revision")
    _string(value, "content_digest")
    if "content" in value:
        _optional_text(value, "content")
    if "parent_issue" in value:
        _optional_issue(value, "parent_issue")


def _positive_revision(value: Mapping[str, object]) -> int:
    """Read a validated Desired Outcome revision from local state."""
    revision = value.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        _refuse("facts_desired_outcomes_revision")
    return revision


def _optional_text(value: Mapping[str, object], field_name: str) -> str | None:
    """Read an optional non-empty text field."""
    item = value.get(field_name)
    if item is not None and (not isinstance(item, str) or not item):
        _refuse(f"facts_invalid_{field_name}")
    return cast("str | None", item)


def _optional_issue(value: Mapping[str, object], field_name: str) -> int | None:
    """Read an optional positive issue number."""
    item = value.get(field_name)
    if item is not None and (isinstance(item, bool) or not isinstance(item, int) or item < 1):
        _refuse(f"facts_invalid_{field_name}")
    return cast("int | None", item)


def _action(value: object) -> policy.ControlAction:
    """Validate one serialized Control Action."""
    if not isinstance(value, dict):
        _refuse("action_not_object")
    if set(value) != {"order", "kind", "logical_key", "payload"}:
        _refuse("action_fields")
    order = value.get("order")
    if not isinstance(order, int) or order < 1:
        _refuse("action_order")
    kind = _string(value, "kind")
    logical_key = _string(value, "logical_key")
    payload = value.get("payload")
    if not isinstance(payload, dict):
        _refuse("action_payload")
    return policy.ControlAction(kind, logical_key, tuple(payload.items()))


def _string(value: Mapping[str, object], field_name: str) -> str:
    """Read one required non-empty string or refuse local state."""
    item = value.get(field_name)
    if not isinstance(item, str) or not item:
        _refuse(f"invalid_{field_name}")
    return item


def _nullable_string(value: Mapping[str, object], field_name: str) -> str | None:
    """Read one nullable string without coercing absent data."""
    item = value.get(field_name)
    if item is not None and (not isinstance(item, str) or not item):
        _refuse(f"invalid_{field_name}")
    return item


def _json_line(value: Mapping[str, object]) -> str:
    """Encode one compact, deterministic journal record."""
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
    except (TypeError, ValueError) as error:
        detail = f"journal_value_not_serializable:{error}"
        raise ControllerStateUnreadable(detail) from error


def _atomic_write(path: Path, value: Mapping[str, object]) -> None:
    """Write a complete view, fsync it, replace it, and fsync its directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(value, sort_keys=True, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        Path(temporary).replace(path)
        temporary = None
        _fsync_directory(path.parent)
    except (OSError, TypeError, ValueError) as error:
        if temporary is not None:
            with suppress(OSError):
                Path(temporary).unlink()
        detail = f"view_write_failed:{error}"
        raise ControllerStateUnreadable(detail) from error


def _fsync_directory(path: Path) -> None:
    """Flush directory metadata after a durable marker or replacement."""
    directory = os.open(path, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _sha256(value: bytes) -> str:
    """Return the digest used to bind the view to exact journal bytes."""
    return hashlib.sha256(value).hexdigest()


def _journal_text(raw: bytes) -> str:
    """Decode one complete journal byte stream."""
    if not raw:
        _refuse("journal_empty")
    if not raw.endswith(b"\n"):
        _refuse("journal_final_record_truncated")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as error:
        _refuse(f"journal_invalid_utf8:{error}")


def _parse_record(line: str, line_number: int) -> dict[str, object]:
    """Parse and validate one journal line."""
    if not line.strip():
        _refuse(f"journal_blank_line:{line_number}")
    try:
        value = json.loads(line)
    except json.JSONDecodeError as error:
        _refuse(f"journal_invalid_json:{line_number}:{error.msg}")
    if not isinstance(value, dict):
        _refuse(f"journal_record_not_object:{line_number}")
    if set(value) != JOURNAL_FIELDS:
        _refuse(f"journal_record_fields:{line_number}")
    if value.get("schema") != JOURNAL_SCHEMA:
        _refuse(f"journal_unknown_schema:{line_number}")
    phase = value.get("phase")
    if phase not in PHASES:
        _refuse(f"journal_unknown_phase:{line_number}")
    for field_name in ("cycle_id", "recorded_at", "recorded_by"):
        if not isinstance(value.get(field_name), str) or not value[field_name]:
            _refuse(f"journal_invalid_{field_name}:{line_number}")
    payload = value.get("payload")
    if not isinstance(payload, dict):
        _refuse(f"journal_payload_not_object:{line_number}")
    _payload_document(payload)
    return value


def _validate_record_sequence(  # noqa: C901, PLR0912 — recovery validates complete triples and one trailing prefix
    records: list[dict[str, object]],
    *,
    allow_incomplete: bool = False,
) -> None:
    """Require complete triples, or one ordered trailing prefix when recovering."""
    if not records:
        _refuse("journal_empty")
    cycle_ids: list[object] = []
    for start in range(0, len(records), len(PHASES)):
        cycle = records[start : start + len(PHASES)]
        if len(cycle) < len(PHASES):
            if not allow_incomplete:
                break
            phases = [row["phase"] for row in cycle]
            if phases != list(PHASES[: len(cycle)]):
                _refuse(f"journal_phase_sequence:{start + 1}")
            if len({row["cycle_id"] for row in cycle}) != 1:
                _refuse(f"journal_cycle_identity:{start + 1}")
            if any(row["payload"] != cycle[0]["payload"] for row in cycle[1:]):
                _refuse(f"journal_payload_mismatch:{start + 1}")
            break
        if [row["phase"] for row in cycle[:2]] != list(PHASES[:2]):
            _refuse(f"journal_phase_sequence:{start + 1}")
        ids = {row["cycle_id"] for row in cycle}
        if len(ids) != 1:
            _refuse(f"journal_cycle_identity:{start + 1}")
        if any(row["payload"] != cycle[0]["payload"] for row in cycle[1:]):
            _refuse(f"journal_payload_mismatch:{start + 1}")
        cycle_ids.append(cycle[0]["cycle_id"])
    if len(records) % len(PHASES) != 0 and not allow_incomplete:
        _refuse("journal_incomplete_cycle")
    if len(set(cycle_ids)) != len(cycle_ids):
        _refuse("journal_duplicate_cycle")
    if len(records) % len(PHASES) == 0 and records[-1]["phase"] != "confirmed":
        _refuse("journal_last_transition_unconfirmed")


def _refuse(reason: str) -> NoReturn:
    """Raise the one local-state refusal for every malformed shape."""
    raise ControllerStateUnreadable(reason)
