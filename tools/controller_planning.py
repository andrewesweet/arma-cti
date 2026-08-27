"""Initiative Planning domain, validation, storage, and tracker publication (#379).

The module keeps planning input and publication separate.  A stage returns data, the host
validates and stores exact bytes, and only a later reconciliation calls tracker capabilities.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, NoReturn, Protocol, cast

sys.path.insert(0, str(Path(__file__).parent))

import acceptance
from controller_policy import ControlAction

PLAN_SCHEMA: Final = "initiative-plan/v1"
PLAN_SCHEMA_VERSION: Final = 1
STAGE_VERDICT_SCHEMA: Final = "stage-verdict/v1"
STAGE_VERDICT_VERSION: Final = 1
INITIATIVE_PLANNING: Final = "initiative_planning"
VALID: Final = "valid"
INVALID: Final = "invalid"
PRODUCT_QUESTION: Final = "product_question"
INCONCLUSIVE: Final = "inconclusive"
INFRA_UNAVAILABLE: Final = "infra_unavailable"

PLAN_FIELDS: Final = frozenset(
    {
        "schema",
        "schema_version",
        "initiative_key",
        "desired_outcome",
        "product_specification",
        "design_disposition",
        "implementation_design",
        "work_items",
        "dependencies",
        "obligation_coverage",
        "obligation_summary",
    }
)
DESIRED_OUTCOME_FIELDS: Final = frozenset({"key", "revision", "content", "content_digest"})
PRODUCT_SPECIFICATION_FIELDS: Final = frozenset({"obligations"})
OBLIGATION_FIELDS: Final = frozenset({"key", "kind", "statement", "specification"})
SPECIFICATION_FIELDS: Final = frozenset(
    {"binding", "feature", "runner", "step_library", "provisional_terms"}
)
PROVISIONAL_FIELDS: Final = frozenset({"term", "definition"})
DISPOSITION_FIELDS: Final = frozenset({"kind", "reference", "reasons"})
IMPLEMENTATION_DESIGN_FIELDS: Final = frozenset({"content", "reference"})
WORK_ITEM_FIELDS: Final = frozenset(
    {"key", "title", "body", "obligation_keys", "exclusive_resources"}
)
DEPENDENCY_FIELDS: Final = frozenset({"blocked_key", "blocked_by", "reason"})
COVERAGE_FIELDS: Final = frozenset({"obligation_key", "work_item_keys"})
SUMMARY_FIELDS: Final = frozenset({"mechanised", "held_to_review"})
STAGE_VERDICT_FIELDS: Final = frozenset(
    {"schema", "schema_version", "stage", "status", "input_revision", "plan", "question", "reason"}
)
QUESTION_FIELDS: Final = frozenset({"question", "choices"})
STABLE_KEY: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
SHA256: Final = re.compile(r"[0-9a-f]{64}\Z")
REVISION: Final = re.compile(r"[A-Za-z0-9_.-]+@[1-9][0-9]*\Z")
MIN_QUESTION_CHOICES: Final = 2


class PlanValidationError(ValueError):
    """A host-side plan package validation refusal."""

    def __init__(self, code: str, detail: str) -> None:
        """Expose stable failure class and precise shape location."""
        self.code = code
        self.detail = detail
        super().__init__(f"planning={code} {detail}")


class PlanStorageError(RuntimeError):
    """A validated package could not be durably stored or was contradicted on disk."""

    def __init__(self, code: str, detail: str) -> None:
        """Expose storage refusal separately from validation failure."""
        self.code = code
        self.detail = detail
        super().__init__(f"planning={code} {detail}")


class StageValidationError(PlanValidationError):
    """A semantic stage did not return a closed verdict envelope."""


class TrackerError(RuntimeError):
    """A tracker capability could not read or apply an idempotent operation."""

    def __init__(self, code: str, detail: str) -> None:
        """Keep provider failures typed for controller reporting."""
        self.code = code
        self.detail = detail
        super().__init__(f"tracker={code} {detail}")


def _fail(code: str, detail: str) -> NoReturn:
    """Raise one deterministic validation refusal."""
    raise PlanValidationError(code, detail)


def _stage_fail(code: str, detail: str) -> NoReturn:
    """Raise one deterministic stage-envelope refusal."""
    raise StageValidationError(code, detail)


def _storage_fail(code: str, detail: str) -> NoReturn:
    """Raise one typed local storage refusal."""
    raise PlanStorageError(code, detail)


def _tracker_fail(code: str, detail: str) -> NoReturn:
    """Raise one typed tracker capability refusal."""
    raise TrackerError(code, detail)


def _mapping(value: object, path: str) -> Mapping[str, object]:
    """Require an object without coercing another JSON type."""
    if not isinstance(value, Mapping):
        _fail("expected_object", f"path={path}")
    return value


def _field_names(value: Mapping[str, object], expected: frozenset[str], path: str) -> None:
    """Reject missing and unexpected object fields before reading their values."""
    missing = sorted(expected - set(value))
    if missing:
        _fail("missing_field", f"path={path}.{missing[0]}")
    unexpected = sorted(set(value) - expected)
    if unexpected:
        _fail("unexpected_field", f"path={path}.{unexpected[0]}")


def _stage_field_names(value: Mapping[str, object], expected: frozenset[str], path: str) -> None:
    """Reject missing and unexpected fields in a stage envelope."""
    missing = sorted(expected - set(value))
    if missing:
        _stage_fail("missing_field", f"path={path}.{missing[0]}")
    unexpected = sorted(set(value) - expected)
    if unexpected:
        _stage_fail("unexpected_field", f"path={path}.{unexpected[0]}")


def _text(value: Mapping[str, object], name: str, path: str) -> str:
    """Read one non-empty string field."""
    item = value.get(name)
    if not isinstance(item, str) or not item.strip():
        _fail("invalid_text", f"path={path}.{name}")
    return item


def _stage_text(value: Mapping[str, object], name: str, path: str) -> str:
    """Read one non-empty stage string field."""
    item = value.get(name)
    if not isinstance(item, str) or not item.strip():
        _stage_fail("invalid_text", f"path={path}.{name}")
    return item


def _key(value: Mapping[str, object], name: str, path: str) -> str:
    """Read one stable identifier."""
    item = _text(value, name, path)
    if STABLE_KEY.fullmatch(item) is None:
        _fail("invalid_stable_key", f"path={path}.{name} value={item!r}")
    return item


def _positive_integer(value: Mapping[str, object], name: str, path: str) -> int:
    """Read one positive JSON integer without accepting booleans."""
    item = value.get(name)
    if isinstance(item, bool) or not isinstance(item, int) or item < 1:
        _fail("invalid_positive_integer", f"path={path}.{name}")
    return item


def _nonnegative_integer(value: Mapping[str, object], name: str, path: str) -> int:
    """Read one count without accepting booleans or negative JSON integers."""
    item = value.get(name)
    if isinstance(item, bool) or not isinstance(item, int) or item < 0:
        _fail("invalid_nonnegative_integer", f"path={path}.{name}")
    return item


def _string_list(value: object, path: str, *, nonempty: bool) -> tuple[str, ...]:
    """Read a list of non-empty strings and reject duplicate declarations."""
    if not isinstance(value, list):
        _fail("expected_list", f"path={path}")
    if nonempty and not value:
        _fail("empty_list", f"path={path}")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            _fail("invalid_text", f"path={path}[{index}]")
        result.append(item)
    if len(set(result)) != len(result):
        _fail("duplicate_key", f"path={path}")
    return tuple(result)


def _json_bytes(document: Mapping[str, object]) -> bytes:
    """Encode mapping input deterministically when caller did not supply source bytes."""
    try:
        return json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        _fail("not_json", f"document={error}")


class _DuplicateJSONKeyError(ValueError):
    """Internal marker for duplicate object keys in raw stage/package JSON."""


def _reject_duplicate_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Preserve the JSON parser's closed-object property by rejecting duplicate names."""
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJSONKeyError(key)
        result[key] = value
    return result


def _load_json(raw: bytes, *, stage: bool) -> dict[str, object]:
    """Parse UTF-8 JSON with duplicate-key detection."""
    try:
        parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    except _DuplicateJSONKeyError as error:
        if stage:
            _stage_fail("duplicate_json_key", f"key={error.args[0]!r}")
        _fail("duplicate_json_key", f"key={error.args[0]!r}")
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        if stage:
            _stage_fail("invalid_json", f"{error}")
        _fail("invalid_json", f"{error}")
    if not isinstance(parsed, dict):
        if stage:
            _stage_fail("expected_object", "path=$")
        _fail("expected_object", "path=$")
    return parsed


@dataclass(frozen=True, slots=True)
class DesiredOutcomeSnapshot:
    """Frozen Product Curator content passed into Initiative Planning."""

    key: str
    revision: int
    content: str
    content_digest: str

    @property
    def input_revision(self) -> str:
        """Return the stage input identity."""
        return f"{self.key}@{self.revision}"


@dataclass(frozen=True, slots=True)
class StageRequest:
    """Closed request sent through the Semantic Stage Gateway."""

    stage: str
    input_revision: str
    desired_outcome: DesiredOutcomeSnapshot
    repository_context: str
    output_schema: str = STAGE_VERDICT_SCHEMA

    def to_document(self) -> dict[str, object]:
        """Render the frozen stage input without exposing mutable source state."""
        return {
            "stage": self.stage,
            "input_revision": self.input_revision,
            "desired_outcome": {
                "key": self.desired_outcome.key,
                "revision": self.desired_outcome.revision,
                "content": self.desired_outcome.content,
                "content_digest": self.desired_outcome.content_digest,
            },
            "repository_context": self.repository_context,
            "output_schema": self.output_schema,
        }


@dataclass(frozen=True, slots=True)
class StageVerdict:
    """Closed planning-stage outcome; only ``valid`` may produce a package."""

    status: str
    input_revision: str
    plan: Mapping[str, object] | None
    question: Mapping[str, object] | None
    reason: str

    @property
    def publication_allowed(self) -> bool:
        """Return whether host validation may proceed to package storage."""
        return self.status == VALID and self.plan is not None

    def to_document(self) -> dict[str, object]:
        """Render the stage verdict envelope."""
        return {
            "schema": STAGE_VERDICT_SCHEMA,
            "schema_version": STAGE_VERDICT_VERSION,
            "stage": INITIATIVE_PLANNING,
            "status": self.status,
            "input_revision": self.input_revision,
            "plan": dict(self.plan) if self.plan is not None else None,
            "question": dict(self.question) if self.question is not None else None,
            "reason": self.reason,
        }


class SemanticStageGateway(Protocol):
    """Capability boundary for one bounded Initiative Planning stage."""

    def run(self, request: StageRequest) -> Mapping[str, object] | StageVerdict | None:
        """Return one closed stage verdict without tracker mutation."""


class RepositoryContextSource(Protocol):
    """Read repository context once for a frozen stage request."""

    def read(self) -> str:
        """Return the context snapshot."""


@dataclass(frozen=True, slots=True)
class StaticRepositoryContext:
    """Deterministic repository-context adapter for tests and callers with a snapshot."""

    value: str

    def read(self) -> str:
        """Return the arranged context without rereading a mutable checkout."""
        return self.value


@dataclass(frozen=True, slots=True)
class FileRepositoryContext:
    """Read one repository context file exactly once per stage request."""

    path: Path

    def read(self) -> str:
        """Return UTF-8 context or raise a typed stage-unavailable error."""
        try:
            return self.path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            code = "infra_unavailable"
            detail = f"repository_context={self.path}: {error}"
            raise TrackerError(code, detail) from error


@dataclass
class RecordingStageGateway:
    """Stage fake that records frozen requests and returns an arranged verdict."""

    verdict: Mapping[str, object] | StageVerdict | None
    requests: list[StageRequest] = field(default_factory=list)

    def run(self, request: StageRequest) -> Mapping[str, object] | StageVerdict | None:
        """Record one request and return the immutable arranged response."""
        self.requests.append(request)
        return self.verdict


def validate_stage_verdict(  # noqa: C901, PLR0912, PLR0915 — the closed status envelope is one validation ladder
    value: object,
    request: StageRequest,
) -> StageVerdict:
    """Validate a closed, versioned stage result against its exact frozen input."""
    if request.stage != INITIATIVE_PLANNING:
        _stage_fail("request_wrong_stage", f"value={request.stage!r}")
    if request.output_schema != STAGE_VERDICT_SCHEMA:
        _stage_fail("request_unknown_output_schema", f"value={request.output_schema!r}")
    if request.input_revision != request.desired_outcome.input_revision:
        _stage_fail(
            "request_input_revision_mismatch",
            (
                f"expected={request.desired_outcome.input_revision!r} "
                f"actual={request.input_revision!r}"
            ),
        )
    if not REVISION.fullmatch(request.input_revision):
        _stage_fail("invalid_input_revision", f"value={request.input_revision!r}")
    if isinstance(value, StageVerdict):
        document = value.to_document()
    elif isinstance(value, Mapping):
        document = dict(value)
    else:
        _stage_fail("verdict_absent", "stage returned no object verdict")
    _stage_field_names(document, STAGE_VERDICT_FIELDS, "$")
    if document.get("schema") != STAGE_VERDICT_SCHEMA:
        _stage_fail("unknown_schema", f"path=$.schema value={document.get('schema')!r}")
    if document.get("schema_version") != STAGE_VERDICT_VERSION:
        _stage_fail(
            "unknown_schema_version",
            f"path=$.schema_version value={document.get('schema_version')!r}",
        )
    if document.get("stage") != INITIATIVE_PLANNING:
        _stage_fail("wrong_stage", f"path=$.stage value={document.get('stage')!r}")
    status = _stage_text(document, "status", "$")
    allowed = {VALID, INVALID, PRODUCT_QUESTION, INCONCLUSIVE, INFRA_UNAVAILABLE}
    if status not in allowed:
        _stage_fail("invalid_status", f"path=$.status value={status!r}")
    input_revision = _stage_text(document, "input_revision", "$")
    if REVISION.fullmatch(input_revision) is None:
        _stage_fail("invalid_input_revision", f"path=$.input_revision value={input_revision!r}")
    if input_revision != request.input_revision:
        _stage_fail(
            "input_revision_mismatch",
            f"expected={request.input_revision!r} actual={input_revision!r}",
        )
    reason = _stage_text(document, "reason", "$")
    plan = document.get("plan")
    question = document.get("question")
    if status == VALID:
        if not isinstance(plan, Mapping):
            _stage_fail("valid_plan_missing", "path=$.plan")
        if question is not None:
            _stage_fail("valid_question_present", "path=$.question")
    elif plan is not None:
        _stage_fail("non_valid_plan_present", "path=$.plan")
    if status == PRODUCT_QUESTION:
        question_document = _mapping(question, "$.question")
        _stage_field_names(question_document, QUESTION_FIELDS, "$.question")
        question_text = _stage_text(question_document, "question", "$.question")
        choices = question_document.get("choices")
        if not isinstance(choices, list) or len(choices) < MIN_QUESTION_CHOICES:
            _stage_fail("question_choices", "path=$.question.choices")
        if any(not isinstance(choice, str) or not choice.strip() for choice in choices):
            _stage_fail("question_choices", "path=$.question.choices")
        if len(set(choices)) != len(choices):
            _stage_fail("question_choices_duplicate", "path=$.question.choices")
        question = {"question": question_text, "choices": list(choices)}
    elif question is not None:
        _stage_fail("unexpected_question", "path=$.question")
    return StageVerdict(
        status=status,
        input_revision=input_revision,
        plan=cast("Mapping[str, object] | None", plan),
        question=cast("Mapping[str, object] | None", question),
        reason=reason,
    )


def _validate_desired_outcome(
    document: Mapping[str, object], path: str
) -> tuple[str, int, str, str]:
    """Validate exact Product Curator authority embedded in a plan."""
    _field_names(document, DESIRED_OUTCOME_FIELDS, path)
    key = _key(document, "key", path)
    revision = _positive_integer(document, "revision", path)
    content = _text(document, "content", path)
    digest = _text(document, "content_digest", path)
    if SHA256.fullmatch(digest) is None:
        _fail("invalid_digest", f"path={path}.content_digest")
    expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if digest != expected:
        _fail("desired_outcome_digest_mismatch", f"path={path}.content_digest")
    return key, revision, content, digest


def _validate_provisional_terms(value: object, path: str) -> tuple[str, ...]:
    """Validate provisional declarations while leaving ratification to the landing gate."""
    if not isinstance(value, list):
        _fail("expected_list", f"path={path}")
    terms: list[str] = []
    for index, raw in enumerate(value):
        item = _mapping(raw, f"{path}[{index}]")
        _field_names(item, PROVISIONAL_FIELDS, f"{path}[{index}]")
        term = _text(item, "term", f"{path}[{index}]")
        _text(item, "definition", f"{path}[{index}]")
        terms.append(term)
    if len(set(terms)) != len(terms):
        _fail("duplicate_key", f"path={path}")
    return tuple(terms)


def _validate_obligation(
    value: object,
    path: str,
    repository_root: Path,
) -> tuple[str, str, tuple[str, ...]]:
    """Validate one obligation and send behavioural specs through acceptance.py."""
    item = _mapping(value, path)
    _field_names(item, OBLIGATION_FIELDS, path)
    key = _key(item, "key", path)
    kind = _text(item, "kind", path)
    if kind not in {acceptance.BEHAVIOURAL, acceptance.NON_BEHAVIOURAL}:
        _fail("invalid_obligation_kind", f"path={path}.kind")
    _text(item, "statement", path)
    specification = item.get("specification")
    if kind == acceptance.NON_BEHAVIOURAL:
        if specification is not None:
            _fail("non_behavioural_specification", f"path={path}.specification")
        return key, kind, ()
    spec = _mapping(specification, f"{path}.specification")
    _field_names(spec, SPECIFICATION_FIELDS, f"{path}.specification")
    _text(spec, "binding", f"{path}.specification")
    feature = _text(spec, "feature", f"{path}.specification")
    runner = _text(spec, "runner", f"{path}.specification")
    if runner != acceptance.PYTHON_RUNNER:
        _fail("runner_unsupported", f"path={path}.specification.runner value={runner!r}")
    _text(spec, "step_library", f"{path}.specification")
    provisional = _validate_provisional_terms(
        spec.get("provisional_terms"), f"{path}.specification.provisional_terms"
    )
    record = dict(spec)
    record["kind"] = acceptance.BEHAVIOURAL
    record["feature"] = f"{key}.feature"
    report = acceptance.lint_embedded_obligation(
        repository_root,
        key,
        record,
        feature,
    )
    if report.errors:
        finding = report.errors[0]
        _fail(finding.code, finding.detail)
    unratified = tuple(sorted(term for term in report.unratified if term in provisional))
    return key, kind, unratified


def _validate_disposition(
    document: Mapping[str, object], path: str
) -> tuple[str, str | None, tuple[str, ...]]:
    """Require explicit Design Disposition and align optional Implementation Design."""
    _field_names(document, DISPOSITION_FIELDS, path)
    kind = _text(document, "kind", path)
    if kind not in {"provided", "not_required"}:
        _fail("invalid_design_disposition", f"path={path}.kind")
    reasons = _string_list(document.get("reasons"), f"{path}.reasons", nonempty=True)
    reference = document.get("reference")
    if kind == "provided":
        if not isinstance(reference, str) or not reference.strip():
            _fail("provided_design_reference_missing", f"path={path}.reference")
    elif reference is not None:
        _fail("not_required_design_reference", f"path={path}.reference")
    return kind, cast("str | None", reference), reasons


def _validate_implementation_design(value: object, path: str) -> None:
    """Validate optional cross-Work-Item design without making it mandatory."""
    if value is None:
        return
    document = _mapping(value, path)
    _field_names(document, IMPLEMENTATION_DESIGN_FIELDS, path)
    _text(document, "content", path)
    _text(document, "reference", path)


def _validate_work_items(
    value: object,
    path: str,
    obligation_keys: set[str],
) -> tuple[dict[str, tuple[str, ...]], tuple[tuple[str, tuple[str, ...]], ...]]:
    """Validate stable Work Items and collect their obligation/resource claims."""
    if not isinstance(value, list) or not value:
        _fail("work_items_empty", f"path={path}")
    seen: set[str] = set()
    obligations: dict[str, tuple[str, ...]] = {}
    resources: list[tuple[str, tuple[str, ...]]] = []
    for index, raw in enumerate(value):
        item_path = f"{path}[{index}]"
        item = _mapping(raw, item_path)
        _field_names(item, WORK_ITEM_FIELDS, item_path)
        key = _key(item, "key", item_path)
        if key in seen:
            _fail("duplicate_work_item_key", f"key={key!r}")
        seen.add(key)
        _text(item, "title", item_path)
        _text(item, "body", item_path)
        claimed = _string_list(
            item.get("obligation_keys"), f"{item_path}.obligation_keys", nonempty=True
        )
        unknown = sorted(set(claimed) - obligation_keys)
        if unknown:
            _fail("dangling_obligation_reference", f"work_item={key!r} obligation={unknown[0]!r}")
        claimed_resources = _string_list(
            item.get("exclusive_resources"), f"{item_path}.exclusive_resources", nonempty=False
        )
        obligations[key] = claimed
        resources.append((key, claimed_resources))
    return obligations, tuple(resources)


def _validate_dependencies(  # noqa: C901 — edge validation keeps refs, reason, uniqueness, and DFS together
    value: object,
    path: str,
    work_item_keys: set[str],
) -> tuple[tuple[str, str, str], ...]:
    """Validate dependency edges, resource edges, uniqueness, and acyclicity."""
    if not isinstance(value, list):
        _fail("expected_list", f"path={path}")
    edges: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    graph = {key: [] for key in work_item_keys}
    for index, raw in enumerate(value):
        item_path = f"{path}[{index}]"
        item = _mapping(raw, item_path)
        _field_names(item, DEPENDENCY_FIELDS, item_path)
        blocked = _key(item, "blocked_key", item_path)
        blocker = _key(item, "blocked_by", item_path)
        reason = _text(item, "reason", item_path)
        if blocked not in work_item_keys or blocker not in work_item_keys:
            missing = blocked if blocked not in work_item_keys else blocker
            _fail("dangling_dependency", f"edge={blocked!r}->{blocker!r} missing={missing!r}")
        if blocked == blocker:
            _fail("dependency_cycle", f"self_edge={blocked!r}")
        if reason not in {"data", "resource"}:
            _fail("invalid_dependency_reason", f"path={item_path}.reason")
        identity = (blocked, blocker)
        if identity in seen:
            _fail("duplicate_dependency", f"edge={blocked!r}->{blocker!r}")
        seen.add(identity)
        edges.append((blocked, blocker, reason))
        graph[blocked].append(blocker)
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(key: str) -> None:
        if key in visiting:
            _fail("dependency_cycle", f"at={key!r}")
        if key in visited:
            return
        visiting.add(key)
        for blocker in graph[key]:
            visit(blocker)
        visiting.remove(key)
        visited.add(key)

    for key in sorted(graph):
        visit(key)
    return tuple(edges)


def _validate_resource_edges(
    resources: tuple[tuple[str, tuple[str, ...]], ...],
    edges: tuple[tuple[str, str, str], ...],
) -> None:
    """Require an explicit resource dependency for every exclusive-resource collision."""
    edge_map = {(left, right): reason for left, right, reason in edges}
    for index, (left, left_resources) in enumerate(resources):
        for right, right_resources in resources[index + 1 :]:
            if not set(left_resources) & set(right_resources):
                continue
            if not (
                edge_map.get((left, right)) == "resource"
                or edge_map.get((right, left)) == "resource"
            ):
                _fail(
                    "missing_resource_dependency",
                    f"work_items={left!r},{right!r}",
                )


def _validate_coverage(
    value: object,
    path: str,
    obligation_keys: set[str],
    work_item_obligations: Mapping[str, tuple[str, ...]],
) -> None:
    """Require one exact declared coverage row per obligation and match Work Item claims."""
    if not isinstance(value, list):
        _fail("expected_list", f"path={path}")
    seen: set[str] = set()
    declared: dict[str, tuple[str, ...]] = {}
    for index, raw in enumerate(value):
        item_path = f"{path}[{index}]"
        item = _mapping(raw, item_path)
        _field_names(item, COVERAGE_FIELDS, item_path)
        obligation = _key(item, "obligation_key", item_path)
        if obligation in seen:
            _fail("duplicate_coverage_key", f"obligation={obligation!r}")
        seen.add(obligation)
        if obligation not in obligation_keys:
            _fail("dangling_obligation_reference", f"obligation={obligation!r}")
        work_items = _string_list(
            item.get("work_item_keys"), f"{item_path}.work_item_keys", nonempty=True
        )
        missing = sorted(set(work_items) - set(work_item_obligations))
        if missing:
            _fail("dangling_work_item_reference", f"work_item={missing[0]!r}")
        declared[obligation] = work_items
    uncovered = sorted(obligation_keys - set(declared))
    if uncovered:
        _fail("uncovered_obligation", f"obligation={uncovered[0]!r}")
    for obligation in sorted(obligation_keys):
        actual = tuple(
            sorted(key for key, claims in work_item_obligations.items() if obligation in claims)
        )
        if tuple(sorted(declared[obligation])) != actual:
            _fail("coverage_mismatch", f"obligation={obligation!r}")


def _bind_package_bytes(
    document: dict[str, object], raw_bytes: bytes | None
) -> tuple[dict[str, object], bytes]:
    """Bind validation to the exact source bytes instead of a later re-encoding."""
    if raw_bytes is None:
        return document, _json_bytes(document)
    parsed = _load_json(raw_bytes, stage=False)
    if parsed != document:
        _fail("package_bytes_mismatch", "raw bytes do not contain the validated package")
    return parsed, raw_bytes


@dataclass(frozen=True, slots=True)
class ValidatedPlan:
    """Exact host-validated package plus derived publication metadata."""

    document: dict[str, object]
    raw_bytes: bytes
    content_digest: str
    revision_id: str
    initiative_key: str
    desired_outcome: DesiredOutcomeSnapshot
    obligation_counts: dict[str, int]
    behavioural: tuple[str, ...]
    held_to_review: tuple[str, ...]
    unratified_terms: tuple[str, ...]

    @property
    def package_digest(self) -> str:
        """Alias digest with domain wording used by publication records."""
        return self.content_digest


def validate_plan_package(
    value: Mapping[str, object],
    *,
    repository_root: Path | None = None,
    raw_bytes: bytes | None = None,
) -> ValidatedPlan:
    """Validate every package shape before returning anything publishable."""
    document, raw_bytes = _bind_package_bytes(dict(value), raw_bytes)
    _field_names(document, PLAN_FIELDS, "$")
    if document.get("schema") != PLAN_SCHEMA:
        _fail("unknown_schema", f"path=$.schema value={document.get('schema')!r}")
    if document.get("schema_version") != PLAN_SCHEMA_VERSION:
        _fail(
            "unknown_schema_version",
            f"path=$.schema_version value={document.get('schema_version')!r}",
        )
    initiative_key = _key(document, "initiative_key", "$")
    outcome_document = _mapping(document.get("desired_outcome"), "$.desired_outcome")
    outcome_key, outcome_revision, outcome_content, outcome_digest = _validate_desired_outcome(
        outcome_document, "$.desired_outcome"
    )
    specification = _mapping(document.get("product_specification"), "$.product_specification")
    _field_names(specification, PRODUCT_SPECIFICATION_FIELDS, "$.product_specification")
    raw_obligations = specification.get("obligations")
    if not isinstance(raw_obligations, list) or not raw_obligations:
        _fail("obligations_empty", "path=$.product_specification.obligations")
    obligation_keys: set[str] = set()
    behavioural: list[str] = []
    held: list[str] = []
    unratified: set[str] = set()
    repo = repository_root or acceptance.REPO
    for index, raw in enumerate(raw_obligations):
        key, kind, terms = _validate_obligation(
            raw, f"$.product_specification.obligations[{index}]", repo
        )
        if key in obligation_keys:
            _fail("duplicate_obligation_key", f"key={key!r}")
        obligation_keys.add(key)
        unratified.update(terms)
        (behavioural if kind == acceptance.BEHAVIOURAL else held).append(key)
    disposition = _mapping(document.get("design_disposition"), "$.design_disposition")
    disposition_kind, _disposition_reference, _reasons = _validate_disposition(
        disposition, "$.design_disposition"
    )
    implementation_design = document.get("implementation_design")
    _validate_implementation_design(implementation_design, "$.implementation_design")
    if disposition_kind == "provided" and implementation_design is None:
        _fail("provided_design_missing", "path=$.implementation_design")
    if disposition_kind == "not_required" and implementation_design is not None:
        _fail("unexpected_implementation_design", "path=$.implementation_design")
    work_item_obligations, resources = _validate_work_items(
        document.get("work_items"), "$.work_items", obligation_keys
    )
    edges = _validate_dependencies(
        document.get("dependencies"), "$.dependencies", set(work_item_obligations)
    )
    _validate_resource_edges(resources, edges)
    _validate_coverage(
        document.get("obligation_coverage"),
        "$.obligation_coverage",
        obligation_keys,
        work_item_obligations,
    )
    summary = _mapping(document.get("obligation_summary"), "$.obligation_summary")
    _field_names(summary, SUMMARY_FIELDS, "$.obligation_summary")
    mechanised = _nonnegative_integer(summary, "mechanised", "$.obligation_summary")
    held_to_review = _nonnegative_integer(summary, "held_to_review", "$.obligation_summary")
    if mechanised != len(behavioural):
        _fail("obligation_summary_mismatch", "field=mechanised")
    if held_to_review != len(held):
        _fail("obligation_summary_mismatch", "field=held_to_review")
    content_digest = hashlib.sha256(raw_bytes).hexdigest()
    revision_id = f"{initiative_key}-r{outcome_revision}-{content_digest[:16]}"
    return ValidatedPlan(
        document=document,
        raw_bytes=raw_bytes,
        content_digest=content_digest,
        revision_id=revision_id,
        initiative_key=initiative_key,
        desired_outcome=DesiredOutcomeSnapshot(
            outcome_key,
            outcome_revision,
            outcome_content,
            outcome_digest,
        ),
        obligation_counts={"mechanised": mechanised, "held_to_review": held_to_review},
        behavioural=tuple(behavioural),
        held_to_review=tuple(held),
        unratified_terms=tuple(sorted(unratified)),
    )


def validate_plan_bytes(raw: bytes, *, repository_root: Path | None = None) -> ValidatedPlan:
    """Parse and validate exact UTF-8 package bytes without normalising them."""
    document = _load_json(raw, stage=False)
    return validate_plan_package(document, repository_root=repository_root, raw_bytes=raw)


@dataclass(frozen=True, slots=True)
class StoredPlan:
    """Durable paths for one exact validated package."""

    plan: ValidatedPlan
    package_path: Path
    digest_path: Path

    @property
    def raw_bytes(self) -> bytes:
        """Expose stored package bytes from validation result."""
        return self.plan.raw_bytes

    @property
    def content_digest(self) -> str:
        """Expose digest bound to exact package bytes."""
        return self.plan.content_digest

    @property
    def revision_id(self) -> str:
        """Expose deterministic Plan Revision identity."""
        return self.plan.revision_id


@dataclass(frozen=True, slots=True)
class ValidatedPlanStore:
    """Atomic local store written before tracker publication."""

    root: Path
    repository_root: Path | None = None

    def _paths(self, revision_id: str) -> tuple[Path, Path]:
        """Resolve one revision's package and digest files under the store root."""
        if STABLE_KEY.fullmatch(revision_id) is None:
            _storage_fail("invalid_revision_id", f"revision={revision_id!r}")
        directory = self.root / "validated-plans" / revision_id
        return directory / "package.json", directory / "content.sha256"

    def store(self, plan: ValidatedPlan) -> StoredPlan:
        """Atomically persist exact bytes and its digest, idempotently."""
        if hashlib.sha256(plan.raw_bytes).hexdigest() != plan.content_digest:
            _storage_fail("plan_digest_mismatch", f"revision={plan.revision_id}")
        package_path, digest_path = self._paths(plan.revision_id)
        package_path.parent.mkdir(parents=True, exist_ok=True)
        if package_path.exists():
            try:
                existing = package_path.read_bytes()
                digest = digest_path.read_text(encoding="utf-8").strip()
            except (OSError, UnicodeError) as error:
                code = "plan_storage_unreadable"
                _storage_fail(code, str(error))
            if existing != plan.raw_bytes or digest != plan.content_digest:
                _storage_fail("plan_revision_conflict", f"revision={plan.revision_id}")
            return StoredPlan(plan, package_path, digest_path)
        _atomic_bytes(package_path, plan.raw_bytes)
        _atomic_text(digest_path, plan.content_digest + "\n")
        return StoredPlan(plan, package_path, digest_path)

    def load(self, revision_id: str) -> StoredPlan:
        """Reload and revalidate one stored package before resumption."""
        package_path, digest_path = self._paths(revision_id)
        try:
            raw = package_path.read_bytes()
            stored_digest = digest_path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError) as error:
            code = "plan_storage_unreadable"
            _storage_fail(code, str(error))
        actual = hashlib.sha256(raw).hexdigest()
        if actual != stored_digest:
            _storage_fail("plan_digest_mismatch", f"revision={revision_id}")
        plan = validate_plan_bytes(raw, repository_root=self.repository_root)
        if plan.revision_id != revision_id:
            _storage_fail("plan_revision_mismatch", f"expected={revision_id}")
        return StoredPlan(plan, package_path, digest_path)


@dataclass
class PlanningSubmission:
    """Validate/store handoff; intentionally has no tracker calls."""

    store: ValidatedPlanStore
    tracker: object | None = None
    repository_root: Path | None = None

    def submit(self, package: bytes | Mapping[str, object]) -> StoredPlan:
        """Validate exact input then store it, never publishing to a tracker."""
        if isinstance(package, bytes):
            plan = validate_plan_bytes(package, repository_root=self.repository_root)
        elif isinstance(package, Mapping):
            plan = validate_plan_package(package, repository_root=self.repository_root)
        else:
            _fail("invalid_input", "package must be UTF-8 bytes or an object")
        return self.store.store(plan)


def _atomic_bytes(path: Path, value: bytes) -> None:
    """Write exact bytes durably then replace the destination."""
    temporary: str | None = None
    try:
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        Path(temporary).replace(path)
        temporary = None
    except (OSError, TypeError) as error:
        if temporary is not None:
            with suppress(OSError):
                Path(temporary).unlink()
        _storage_fail("plan_storage_write_failed", str(error))


def _atomic_text(path: Path, value: str) -> None:
    """Write one digest text file through the same atomic path."""
    _atomic_bytes(path, value.encode("utf-8"))


@dataclass(frozen=True, slots=True)
class TrackerRef:
    """Tracker identity needed for sub-issue and dependency edges."""

    identifier: str
    number: int | None = None
    database_id: int | None = None


class TrackerPort(Protocol):
    """Narrow idempotent tracker capability used by PlanPublisher."""

    def has_plan_revision(self, parent_issue: str, marker: str) -> bool:
        """Check parent comments for one plan-revision intent marker."""

    def append_plan_revision(self, parent_issue: str, marker: str, body: str) -> None:
        """Append one immutable Plan Revision record."""

    def find_intent(self, intent: str) -> TrackerRef | None:
        """Find an issue carrying one stable Work Item intent marker."""

    def create_work_item(self, intent: str, title: str, body: str) -> TrackerRef:
        """Create one marked Work Item issue."""

    def has_sub_issue(self, parent_issue: str, child: TrackerRef, marker: str) -> bool:
        """Check one parent/sub-issue link marker."""

    def attach_sub_issue(self, parent_issue: str, child: TrackerRef, marker: str) -> None:
        """Attach one child issue to the parent."""

    def has_dependency(self, blocked: TrackerRef, blocker: TrackerRef, marker: str) -> bool:
        """Check one native dependency edge."""

    def add_dependency(self, blocked: TrackerRef, blocker: TrackerRef, marker: str) -> None:
        """Add one native dependency edge."""


def _payload(action: ControlAction, name: str) -> object:
    """Read one serialized action payload field."""
    values = dict(action.payload)
    return values[name]


def _marker(prefix: str, value: str) -> str:
    """Render one machine-readable stable intent marker."""
    return f"<!-- arma-cti:{prefix}={value} -->"


def plan_revision_marker(plan: ValidatedPlan) -> str:
    """Return parent marker binding initiative, revision, and exact package digest."""
    return _marker("plan-revision", f"{plan.revision_id} digest={plan.content_digest}")


def work_item_intent(plan: ValidatedPlan, key: str) -> str:
    """Return stable Work Item intent identity."""
    return f"{plan.initiative_key}:work-item:{key}"


def work_item_marker(plan: ValidatedPlan, key: str) -> str:
    """Return stable Work Item body marker."""
    return _marker("work-item", work_item_intent(plan, key))


def dependency_marker(plan: ValidatedPlan, blocked: str, blocker: str) -> str:
    """Return stable dependency intent marker."""
    return _marker("dependency", f"{plan.initiative_key}:{blocked}:{blocker}")


def _plan_body(plan: ValidatedPlan) -> str:
    """Render append-only parent content containing exact machine-readable plan data."""
    try:
        encoded = plan.raw_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        _fail("package_bytes_invalid_utf8", str(error))
    if not encoded.endswith("\n"):
        encoded += "\n"
    return (
        f"{plan_revision_marker(plan)}\n"
        f"## Plan Revision `{plan.revision_id}`\n\n"
        f"Content digest: `{plan.content_digest}`\n\n"
        "```json\n"
        f"{encoded}\n"
        "```\n"
    )


def _work_item_body(plan: ValidatedPlan, item: Mapping[str, object]) -> str:
    """Render one Work Item with obligation traceability and plan authority."""
    key = str(item["key"])
    obligations = ", ".join(str(value) for value in cast("list[object]", item["obligation_keys"]))
    return (
        f"{work_item_marker(plan, key)}\n"
        f"<!-- arma-cti:plan-revision={plan.revision_id} digest={plan.content_digest} -->\n"
        f"<!-- arma-cti:obligations={obligations} -->\n\n"
        f"{item['body']}\n"
    )


def publication_actions(plan: ValidatedPlan, parent_issue: str) -> tuple[ControlAction, ...]:
    """Build deterministic parent, Work Item, link, and dependency actions."""
    if plan.unratified_terms:
        _fail("provisional_unratified", f"terms={','.join(plan.unratified_terms)}")
    actions: list[ControlAction] = [
        ControlAction(
            "tracker.publish_plan_revision",
            plan.revision_id,
            (
                ("parent_issue", parent_issue),
                ("marker", plan_revision_marker(plan)),
                ("body", _plan_body(plan)),
                ("digest", plan.content_digest),
            ),
        )
    ]
    document = _load_json(plan.raw_bytes, stage=False)
    items = cast("list[Mapping[str, object]]", document["work_items"])
    for item in items:
        key = str(item["key"])
        intent = work_item_intent(plan, key)
        actions.append(
            ControlAction(
                "tracker.publish_work_item",
                intent,
                (
                    ("intent", intent),
                    ("title", str(item["title"])),
                    ("body", _work_item_body(plan, item)),
                ),
            )
        )
        actions.append(
            ControlAction(
                "tracker.attach_sub_issue",
                f"{plan.initiative_key}:sub-issue:{key}",
                (
                    ("parent_issue", parent_issue),
                    ("intent", intent),
                    ("marker", _marker("sub-issue", f"{plan.initiative_key}:{key}")),
                ),
            )
        )
    dependencies = cast("list[Mapping[str, object]]", document["dependencies"])
    for dependency in dependencies:
        blocked = str(dependency["blocked_key"])
        blocker = str(dependency["blocked_by"])
        actions.append(
            ControlAction(
                "tracker.add_dependency",
                f"{plan.initiative_key}:dependency:{blocked}:{blocker}",
                (
                    ("blocked_intent", work_item_intent(plan, blocked)),
                    ("blocker_intent", work_item_intent(plan, blocker)),
                    ("marker", dependency_marker(plan, blocked, blocker)),
                ),
            )
        )
    return tuple(actions)


@dataclass
class PlanPublisher:
    """Apply publication actions with an intent lookup before every mutation."""

    tracker: TrackerPort

    def apply(  # noqa: C901 — each tracker operation has its own idempotency/read-before-write rung
        self, action: ControlAction
    ) -> None:
        """Execute one action idempotently; a retry never creates a duplicate artifact."""
        if action.kind == "tracker.publish_plan_revision":
            parent = str(_payload(action, "parent_issue"))
            marker = str(_payload(action, "marker"))
            if not self.tracker.has_plan_revision(parent, marker):
                self.tracker.append_plan_revision(parent, marker, str(_payload(action, "body")))
            return
        if action.kind == "tracker.publish_work_item":
            intent = str(_payload(action, "intent"))
            if self.tracker.find_intent(intent) is None:
                self.tracker.create_work_item(
                    intent,
                    str(_payload(action, "title")),
                    str(_payload(action, "body")),
                )
            return
        if action.kind == "tracker.attach_sub_issue":
            parent = str(_payload(action, "parent_issue"))
            marker = str(_payload(action, "marker"))
            child = self.tracker.find_intent(str(_payload(action, "intent")))
            if child is None:
                _tracker_fail(
                    "publication_dependency_missing", f"intent={_payload(action, 'intent')}"
                )
            if not self.tracker.has_sub_issue(parent, child, marker):
                self.tracker.attach_sub_issue(parent, child, marker)
            return
        if action.kind == "tracker.add_dependency":
            blocked = self.tracker.find_intent(str(_payload(action, "blocked_intent")))
            blocker = self.tracker.find_intent(str(_payload(action, "blocker_intent")))
            if blocked is None or blocker is None:
                _tracker_fail("publication_dependency_missing", "dependency issue not found")
            marker = str(_payload(action, "marker"))
            if not self.tracker.has_dependency(blocked, blocker, marker):
                self.tracker.add_dependency(blocked, blocker, marker)
            return
        _tracker_fail("unsupported_action", f"kind={action.kind!r}")


@dataclass
class RecordingTracker:
    """In-memory tracker fake with optional fail-after-mutation injection."""

    fail_after: int | None = None
    calls: list[str] = field(default_factory=list)
    parent_markers: set[tuple[str, str]] = field(default_factory=set)
    issues: dict[str, TrackerRef] = field(default_factory=dict)
    sub_issues: set[tuple[str, str, str]] = field(default_factory=set)
    dependencies: set[tuple[str, str, str]] = field(default_factory=set)
    mutation_count: int = 0
    _next_number: int = 1000

    def _call(self, name: str) -> None:
        self.calls.append(name)
        self.mutation_count += 1
        if self.fail_after is not None and self.mutation_count == self.fail_after:
            _tracker_fail("injected_failure", f"after={name}")

    def has_plan_revision(self, parent_issue: str, marker: str) -> bool:
        """Report whether a parent already carries the exact revision marker."""
        self.calls.append(f"check_plan:{parent_issue}")
        return (parent_issue, marker) in self.parent_markers

    def append_plan_revision(self, parent_issue: str, marker: str, body: str) -> None:
        """Record one parent revision mutation in the in-memory fake."""
        del body
        self.parent_markers.add((parent_issue, marker))
        self._call(f"append_plan:{parent_issue}")

    def find_intent(self, intent: str) -> TrackerRef | None:
        """Find a previously created Work Item by stable intent."""
        self.calls.append(f"find:{intent}")
        return self.issues.get(intent)

    def create_work_item(self, intent: str, title: str, body: str) -> TrackerRef:
        """Create one in-memory Work Item and preserve its stable intent."""
        del title, body
        ref = TrackerRef(str(self._next_number), self._next_number, self._next_number)
        self._next_number += 1
        self.issues[intent] = ref
        self._call(f"create:{intent}")
        return ref

    def has_sub_issue(self, parent_issue: str, child: TrackerRef, marker: str) -> bool:
        """Report whether the exact parent/child link marker is present."""
        self.calls.append(f"check_sub:{parent_issue}:{child.identifier}")
        return (parent_issue, child.identifier, marker) in self.sub_issues

    def attach_sub_issue(self, parent_issue: str, child: TrackerRef, marker: str) -> None:
        """Record one in-memory parent/child link mutation."""
        self.sub_issues.add((parent_issue, child.identifier, marker))
        self._call(f"attach:{parent_issue}:{child.identifier}")

    def has_dependency(self, blocked: TrackerRef, blocker: TrackerRef, marker: str) -> bool:
        """Report whether the exact dependency marker is present."""
        self.calls.append(f"check_dependency:{blocked.identifier}:{blocker.identifier}")
        return (blocked.identifier, blocker.identifier, marker) in self.dependencies

    def add_dependency(self, blocked: TrackerRef, blocker: TrackerRef, marker: str) -> None:
        """Record one in-memory dependency mutation."""
        self.dependencies.add((blocked.identifier, blocker.identifier, marker))
        self._call(f"dependency:{blocked.identifier}:{blocker.identifier}")


@dataclass(frozen=True, slots=True)
class GitHubTracker:
    """Small ``gh api`` adapter; all idempotency remains in PlanPublisher."""

    repository: str
    runner: Callable[[Sequence[str]], str] | None = None

    def _run(self, arguments: Sequence[str]) -> str:
        """Run a fixed-argv GitHub call through the injected seam."""
        if self.runner is not None:
            try:
                return self.runner(arguments)
            except Exception as error:  # noqa: BLE001 — provider failures become one typed refusal
                code = "infra_unavailable"
                _tracker_fail(code, str(error))
        try:
            result = subprocess.run(  # noqa: S603 — argv is built from validated API arguments
                ["gh", *arguments],  # noqa: S607 — executable is the fixed GitHub CLI
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.SubprocessError) as error:
            _tracker_fail("infra_unavailable", str(error))
        return result.stdout

    def has_plan_revision(self, parent_issue: str, marker: str) -> bool:
        """Search parent comments for exact plan marker."""
        output = self._run(("api", f"repos/{self.repository}/issues/{parent_issue}/comments"))
        return any(marker in str(row.get("body", "")) for row in _json_rows(output))

    def append_plan_revision(self, parent_issue: str, marker: str, body: str) -> None:
        """Append one plan revision comment to its existing parent issue."""
        del marker
        self._run(
            (
                "api",
                "--method",
                "POST",
                f"repos/{self.repository}/issues/{parent_issue}/comments",
                "-f",
                f"body={body}",
            )
        )

    def find_intent(self, intent: str) -> TrackerRef | None:
        """Find one marked issue across all issue states."""
        marker = _marker("work-item", intent)
        output = self._run(("api", f"repos/{self.repository}/issues?state=all&per_page=100"))
        for row in _json_rows(output):
            if marker in str(row.get("body", "")):
                return TrackerRef(
                    str(row.get("number")),
                    _optional_int(row.get("number")),
                    _optional_int(row.get("id")),
                )
        return None

    def create_work_item(self, intent: str, title: str, body: str) -> TrackerRef:
        """Create one issue carrying its stable work-item marker."""
        del intent
        output = self._run(
            (
                "api",
                "--method",
                "POST",
                f"repos/{self.repository}/issues",
                "-f",
                f"title={title}",
                "-f",
                f"body={body}",
            )
        )
        rows = _json_rows(output)
        if len(rows) != 1:
            _tracker_fail("tracker_response_invalid", "issue creation returned no object")
        row = rows[0]
        return TrackerRef(
            str(row.get("number")), _optional_int(row.get("number")), _optional_int(row.get("id"))
        )

    def has_sub_issue(self, parent_issue: str, child: TrackerRef, marker: str) -> bool:
        """Read native sub-issue list and retain marker argument as operation identity."""
        del marker
        output = self._run(("api", f"repos/{self.repository}/issues/{parent_issue}/sub_issues"))
        return any(_optional_int(row.get("number")) == child.number for row in _json_rows(output))

    def attach_sub_issue(self, parent_issue: str, child: TrackerRef, marker: str) -> None:
        """Attach child by GitHub database id."""
        del marker
        if child.database_id is None:
            _tracker_fail("tracker_response_invalid", "child has no database id")
        self._run(
            (
                "api",
                "--method",
                "POST",
                f"repos/{self.repository}/issues/{parent_issue}/sub_issues",
                "-F",
                f"sub_issue_id={child.database_id}",
            )
        )

    def has_dependency(self, blocked: TrackerRef, blocker: TrackerRef, marker: str) -> bool:
        """Read native blocked-by dependencies."""
        del marker
        if blocked.number is None or blocker.number is None:
            _tracker_fail("tracker_response_invalid", "dependency issue has no number")
        output = self._run(
            ("api", f"repos/{self.repository}/issues/{blocked.number}/dependencies/blocked_by")
        )
        return any(_optional_int(row.get("number")) == blocker.number for row in _json_rows(output))

    def add_dependency(self, blocked: TrackerRef, blocker: TrackerRef, marker: str) -> None:
        """Add native blocked-by edge using blocker's database id."""
        del marker
        if blocked.number is None or blocker.database_id is None:
            _tracker_fail("tracker_response_invalid", "dependency reference incomplete")
        self._run(
            (
                "api",
                "--method",
                "POST",
                f"repos/{self.repository}/issues/{blocked.number}/dependencies/blocked_by",
                "-F",
                f"issue_id={blocker.database_id}",
            )
        )


def _json_rows(output: str) -> list[dict[str, object]]:
    """Decode one GitHub JSON object or array response."""
    try:
        value = json.loads(output)
    except json.JSONDecodeError as error:
        _tracker_fail("tracker_response_invalid", str(error))
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list) and all(isinstance(row, dict) for row in value):
        return cast("list[dict[str, object]]", value)
    _tracker_fail("tracker_response_invalid", "expected object or object list")


def _optional_int(value: object) -> int | None:
    """Read an optional GitHub numeric identity."""
    return value if isinstance(value, int) and not isinstance(value, bool) else None
