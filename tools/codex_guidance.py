"""Prove that a dispatched Codex process received its complete project guidance.

The dispatcher owns the policy and timing of this check. This module owns the deep
mechanism: source discovery, strict reading, prompt capture, parsing, normalization,
and the privacy-preserving proof record. It compares bytes delivered by Codex's own
debug surface; it never reconstructs the delivered prompt from the source files after the fact.
"""

from __future__ import annotations

import hashlib
import json
import re
import stat
import subprocess
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

CODEX_PROJECT_DOC_DEFAULT_BYTES: Final = 32 * 1024
CODEX_PROJECT_DOC_CONTAINMENT_BYTES: Final = 96 * 1024
CODEX_PROJECT_CHAIN_RETIREMENT_BYTES: Final = 24 * 1024
CODEX_GUIDANCE_SCHEMA: Final = "codex-guidance-proof-v1"
CODEX_GUIDANCE_NORMALIZATION: Final = "lf-v1"
CODEX_PROJECT_SEPARATOR: Final = "\n--- project-doc ---\n\n"
CODEX_GUIDANCE_SCOPE: Final = "codex_project_instruction_chain"
CODEX_GUIDANCE_TIMEOUT_SECONDS: Final = 30.0
GUIDANCE_MANIFEST_SCHEMA: Final = "cti.guidance-manifest/1"
GUIDANCE_STATE_VERIFIED: Final = "verified"
GUIDANCE_STATE_UNKNOWN: Final = "unknown"
GUIDANCE_STATE_MISSING: Final = "missing"
GUIDANCE_STATE_UNATTRIBUTABLE: Final = "unattributable"
GUIDANCE_STATE_EMPTY: Final = "empty"
GUIDANCE_STATE_UNCLASSIFIED: Final = "unclassified"
UNATTRIBUTABLE_REASON: Final = "no bounded capture"
GUIDANCE_STATES: Final = (
    GUIDANCE_STATE_VERIFIED,
    GUIDANCE_STATE_UNKNOWN,
    GUIDANCE_STATE_MISSING,
    GUIDANCE_STATE_UNATTRIBUTABLE,
    GUIDANCE_STATE_EMPTY,
    GUIDANCE_STATE_UNCLASSIFIED,
)
_HASH_HEX_LENGTH: Final = 64
_CODEX_VERSION_PATTERN: Final = re.compile(r"codex-cli \d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?")
_VERIFIED_MANIFEST_KEYS: Final = frozenset(
    {"schema", "state", "harness", "source_provenance", "loader_outcome", "delivery"}
)
_NON_SUCCESS_MANIFEST_KEYS: Final = frozenset(
    {
        "schema",
        "state",
        "harness",
        "source_provenance",
        "loader_outcome",
        "reason",
        "sources",
        "launch_context",
    }
)
_HARNESS_BY_LANE: Final = {
    "claude-native": "claude-code",
    "zai": "claude-code",
    "codex": "codex",
}
_INSTRUCTION_START = "# AGENTS.md instructions"
_INSTRUCTION_OPEN = "<INSTRUCTIONS>"
_INSTRUCTION_CLOSE = "</INSTRUCTIONS>"


@dataclass(frozen=True)
class _NonSuccessShape:
    """One allowed non-success tuple, including its runner and source shape."""

    harness: str | None
    source_provenance: str
    loader_outcome: str
    reason: str
    empty_sources: bool
    has_launch_directory: bool


_NON_SUCCESS_SHAPES: Final[dict[str, _NonSuccessShape]] = {
    GUIDANCE_STATE_UNKNOWN: _NonSuccessShape(
        harness=None,
        source_provenance="not_available",
        loader_outcome="not_available",
        reason="historical_manifest_absent",
        empty_sources=False,
        has_launch_directory=False,
    ),
    GUIDANCE_STATE_MISSING: _NonSuccessShape(
        harness="codex",
        source_provenance="not_available",
        loader_outcome="not_run",
        reason="missing_preflight_manifest",
        empty_sources=False,
        has_launch_directory=True,
    ),
    GUIDANCE_STATE_UNATTRIBUTABLE: _NonSuccessShape(
        harness="claude-code",
        source_provenance="not_exposed",
        loader_outcome="not_observable",
        reason=UNATTRIBUTABLE_REASON,
        empty_sources=False,
        has_launch_directory=True,
    ),
    GUIDANCE_STATE_EMPTY: _NonSuccessShape(
        harness="codex",
        source_provenance="loader_reported",
        loader_outcome="empty",
        reason="loader_returned_no_sources",
        empty_sources=True,
        has_launch_directory=True,
    ),
    GUIDANCE_STATE_UNCLASSIFIED: _NonSuccessShape(
        harness=None,
        source_provenance="not_available",
        loader_outcome="not_available",
        reason="unclassified_guidance_record",
        empty_sources=False,
        has_launch_directory=False,
    ),
}


def loader_overrides(max_bytes: int = CODEX_PROJECT_DOC_CONTAINMENT_BYTES) -> tuple[str, ...]:
    """Return the Codex discovery settings shared by exec and preflight."""
    return (
        'project_root_markers=[".git"]',
        "project_doc_fallback_filenames=[]",
        f"project_doc_max_bytes={max_bytes}",
    )


@dataclass(frozen=True)
class LaunchContext:
    """The non-secret launch inputs that the dispatcher is about to hand to Codex."""

    executable: str
    cwd: Path
    environment: Mapping[str, str]
    loader_config: tuple[str, ...] = field(default_factory=loader_overrides)
    timeout_seconds: float = CODEX_GUIDANCE_TIMEOUT_SECONDS


@dataclass(frozen=True)
class SourceRecord:
    """One selected source, with its identity and digest but never its body."""

    path: str
    raw_bytes: int
    sha256: str
    text: str = field(repr=False, compare=False)

    def document(self) -> dict[str, object]:
        """Render the source metadata without retaining instruction text."""
        return {"path": self.path, "raw_bytes": self.raw_bytes, "sha256": self.sha256}


@dataclass(frozen=True)
class GuidanceProof:
    """The safe, content-free measurements recorded for an allowed Codex dispatch."""

    codex_version: str
    launch_directory: str
    project_doc_max_bytes: int
    sources: tuple[SourceRecord, ...]
    raw_project_bytes: int
    expected_project_bytes: int
    expected_project_sha256: str
    delivered_project_bytes: int
    delivered_project_sha256: str
    global_expected_bytes: int
    global_expected_sha256: str
    global_delivered_bytes: int
    global_delivered_sha256: str
    combined_delivered_sha256: str

    def document(self) -> dict[str, object]:
        """Render the proof record without prompt, global, brief, or environment text."""
        return {
            "schema": CODEX_GUIDANCE_SCHEMA,
            "normalization": CODEX_GUIDANCE_NORMALIZATION,
            "codex_version": self.codex_version,
            "launch_directory": self.launch_directory,
            "project_doc_max_bytes": self.project_doc_max_bytes,
            "source_paths": [source.path for source in self.sources],
            "sources": [source.document() for source in self.sources],
            "raw_project_bytes": self.raw_project_bytes,
            "expected_project_bytes": self.expected_project_bytes,
            "expected_project_sha256": self.expected_project_sha256,
            "delivered_project_bytes": self.delivered_project_bytes,
            "delivered_project_sha256": self.delivered_project_sha256,
            "global_expected_bytes": self.global_expected_bytes,
            "global_expected_sha256": self.global_expected_sha256,
            "global_delivered_bytes": self.global_delivered_bytes,
            "global_delivered_sha256": self.global_delivered_sha256,
            "combined_delivered_sha256": self.combined_delivered_sha256,
        }

    def manifest_document(self) -> dict[str, object]:
        """Render the dispatch manifest from this proof, without another capture."""
        return {
            "schema": GUIDANCE_MANIFEST_SCHEMA,
            "state": GUIDANCE_STATE_VERIFIED,
            "harness": "codex",
            # Codex reports delivered text but not LoadedAgentsMd.sources(). The paths below
            # are the independently derived expected chain, never a claim about loader origin.
            "source_provenance": "expected_chain_only",
            "loader_outcome": "matched",
            "delivery": self.document(),
        }


@dataclass(frozen=True)
class GuidanceFailure:
    """A safe preflight failure; raw child output is intentionally never exposed."""

    reason: str
    codex_version: str = ""
    launch_directory: str = ""
    project_doc_max_bytes: int = CODEX_PROJECT_DOC_CONTAINMENT_BYTES
    source_paths: tuple[str, ...] = ()
    evidence: GuidanceProof | None = None

    @property
    def action(self) -> str:
        """Give the caller a bounded recovery action, never a child diagnostic."""
        if self.reason == "instruction_delivery_mismatch":
            return (
                "Repair the Codex loader/source chain or its scoped override, then rerun the "
                "dispatch preflight; no agent work started."
            )
        return (
            "Make the Codex preflight executable, readable, and complete, then rerun the "
            "dispatch; no agent work started."
        )

    def lines(self) -> tuple[str, ...]:
        """Render only bounded measurements suitable for stderr."""
        lines = [
            f"scope={CODEX_GUIDANCE_SCOPE}",
            f"reason={self.reason}",
        ]
        if self.evidence is not None:
            lines.extend(_proof_lines(self.evidence))
            return tuple(lines)
        if self.codex_version:
            lines.append(f"codex_version={self.codex_version}")
        if self.launch_directory:
            lines.append(f"launch_directory={self.launch_directory}")
        lines.append(f"project_doc_max_bytes={self.project_doc_max_bytes}")
        lines.extend(f"source_path={path}" for path in self.source_paths)
        return tuple(lines)


GuidanceResult = GuidanceProof | GuidanceFailure


def _manifest_for_shape(
    state: str,
    launch_directory: str | None = None,
    *,
    harness: str | None = None,
    reason: str | None = None,
) -> dict[str, object]:
    shape = _NON_SUCCESS_SHAPES[state]
    if harness is not None and harness != shape.harness:
        message = "manifest harness does not match state"
        raise ValueError(message)
    if reason is not None and reason != shape.reason:
        message = "manifest reason does not match state"
        raise ValueError(message)
    if shape.has_launch_directory != (launch_directory is not None):
        message = "manifest launch context does not match state"
        raise ValueError(message)
    return {
        "schema": GUIDANCE_MANIFEST_SCHEMA,
        "state": state,
        "harness": shape.harness,
        "source_provenance": shape.source_provenance,
        "loader_outcome": shape.loader_outcome,
        "reason": shape.reason if reason is None else reason,
        "sources": [] if shape.empty_sources else None,
        "launch_context": (
            {"launch_directory": launch_directory} if shape.has_launch_directory else {}
        ),
    }


def unattributable_manifest(harness: str, launch_directory: str, reason: str) -> dict[str, object]:
    """Describe a harness whose bounded non-interactive loader output is unavailable."""
    return _manifest_for_shape(
        GUIDANCE_STATE_UNATTRIBUTABLE,
        launch_directory,
        harness=harness,
        reason=reason,
    )


def missing_manifest(harness: str, launch_directory: str) -> dict[str, object]:
    """Describe a dispatch that lacks the preflight manifest it was required to carry."""
    return _manifest_for_shape(GUIDANCE_STATE_MISSING, launch_directory, harness=harness)


def _state_manifest(state: str) -> dict[str, object]:
    return _manifest_for_shape(state)


def _unknown_manifest() -> dict[str, object]:
    return _state_manifest(GUIDANCE_STATE_UNKNOWN)


def _unclassified_manifest() -> dict[str, object]:
    return _state_manifest(GUIDANCE_STATE_UNCLASSIFIED)


def _valid_hash(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == _HASH_HEX_LENGTH
        and all(character in "0123456789abcdef" for character in value)
    )


def _valid_nonnegative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _valid_codex_version(value: object) -> bool:
    return isinstance(value, str) and _CODEX_VERSION_PATTERN.fullmatch(value) is not None


def _valid_launch_directory(value: object) -> bool:
    if not isinstance(value, str) or not value or not value.isprintable():
        return False
    path = Path(value)
    return (
        path.is_absolute()
        and str(path) == value
        and all(part not in {".", ".."} for part in path.parts)
    )


def _valid_source(value: object) -> bool:
    if not isinstance(value, Mapping) or set(value) != {"path", "raw_bytes", "sha256"}:
        return False
    path = value["path"]
    return (
        isinstance(path, str)
        and "\r" not in path
        and "\n" not in path
        and _valid_nonnegative_int(value["raw_bytes"])
        and _valid_hash(value["sha256"])
    )


def _valid_proof(value: object) -> bool:
    required = {
        "schema",
        "normalization",
        "codex_version",
        "launch_directory",
        "project_doc_max_bytes",
        "source_paths",
        "sources",
        "raw_project_bytes",
        "expected_project_bytes",
        "expected_project_sha256",
        "delivered_project_bytes",
        "delivered_project_sha256",
        "global_expected_bytes",
        "global_expected_sha256",
        "global_delivered_bytes",
        "global_delivered_sha256",
        "combined_delivered_sha256",
    }
    if not isinstance(value, Mapping) or set(value) != required:
        return False
    sources = value["sources"]
    source_paths = value["source_paths"]
    if (
        not isinstance(sources, list)
        or not sources
        or not all(_valid_source(source) for source in sources)
        or not isinstance(source_paths, list)
        or source_paths != [source["path"] for source in sources]
    ):
        return False
    if not all(isinstance(path, str) for path in source_paths):
        return False
    if (
        value["schema"] != CODEX_GUIDANCE_SCHEMA
        or value["normalization"] != CODEX_GUIDANCE_NORMALIZATION
        or not _valid_codex_version(value["codex_version"])
        or not _valid_launch_directory(value["launch_directory"])
        or not _valid_nonnegative_int(value["project_doc_max_bytes"])
        or not _valid_nonnegative_int(value["raw_project_bytes"])
        or not _valid_nonnegative_int(value["expected_project_bytes"])
        or not _valid_nonnegative_int(value["delivered_project_bytes"])
        or not _valid_nonnegative_int(value["global_expected_bytes"])
        or not _valid_nonnegative_int(value["global_delivered_bytes"])
        or not _valid_hash(value["expected_project_sha256"])
        or not _valid_hash(value["delivered_project_sha256"])
        or not _valid_hash(value["global_expected_sha256"])
        or not _valid_hash(value["global_delivered_sha256"])
        or not _valid_hash(value["combined_delivered_sha256"])
    ):
        return False
    return (
        value["raw_project_bytes"] == sum(source["raw_bytes"] for source in sources)
        and value["expected_project_bytes"] == value["delivered_project_bytes"]
        and value["expected_project_sha256"] == value["delivered_project_sha256"]
        and value["global_expected_bytes"] == value["global_delivered_bytes"]
        and value["global_expected_sha256"] == value["global_delivered_sha256"]
    )


def _manifest_from_proof(value: object) -> dict[str, object] | None:
    if not _valid_proof(value):
        return None
    return {
        "schema": GUIDANCE_MANIFEST_SCHEMA,
        "state": GUIDANCE_STATE_VERIFIED,
        "harness": "codex",
        "source_provenance": "expected_chain_only",
        "loader_outcome": "matched",
        "delivery": dict(value),
    }


def _launch_context_document(value: object) -> dict[str, object] | None:
    if not isinstance(value, Mapping) or set(value) != {"launch_directory"}:
        return None
    directory = value["launch_directory"]
    if not _valid_launch_directory(directory):
        return None
    return {"launch_directory": directory}


def _parse_verified_manifest(value: Mapping[str, object]) -> dict[str, object] | None:
    if set(value) != _VERIFIED_MANIFEST_KEYS or value.get("harness") != "codex":
        return None
    if value.get("source_provenance") != "expected_chain_only":
        return None
    if value.get("loader_outcome") != "matched":
        return None
    return _manifest_from_proof(value.get("delivery"))


def _parse_non_success_manifest(
    value: Mapping[str, object], state: str
) -> dict[str, object] | None:
    shape = _NON_SUCCESS_SHAPES.get(state)
    if shape is None or set(value) != _NON_SUCCESS_MANIFEST_KEYS:
        return None
    if shape.has_launch_directory:
        launch_context = _launch_context_document(value["launch_context"])
    else:
        launch_context = {} if value["launch_context"] == {} else None
    sources = value["sources"]
    valid_sources = sources == [] if shape.empty_sources else sources is None
    fields_mismatch = (
        value["harness"] != shape.harness
        or value["source_provenance"] != shape.source_provenance
        or value["loader_outcome"] != shape.loader_outcome
        or value["reason"] != shape.reason
    )
    if launch_context is None or not valid_sources or fields_mismatch:
        return None
    return {
        "schema": GUIDANCE_MANIFEST_SCHEMA,
        "state": state,
        "harness": shape.harness,
        "source_provenance": shape.source_provenance,
        "loader_outcome": shape.loader_outcome,
        "reason": shape.reason,
        "sources": sources,
        "launch_context": launch_context,
    }


def _parse_manifest(value: object) -> dict[str, object] | None:
    if not isinstance(value, Mapping) or value.get("schema") != GUIDANCE_MANIFEST_SCHEMA:
        return None
    state = value.get("state")
    if state == GUIDANCE_STATE_VERIFIED:
        return _parse_verified_manifest(value)
    if not isinstance(state, str) or state not in GUIDANCE_STATES:
        return None
    return _parse_non_success_manifest(value, state)


def _manifest_matches_lane(record: Mapping[str, object], manifest: Mapping[str, object]) -> bool:
    harness = manifest.get("harness")
    if harness is None:
        return True
    lane = record.get("lane")
    return isinstance(lane, str) and _HARNESS_BY_LANE.get(lane) == harness


def manifest_from_record(record: Mapping[str, object]) -> dict[str, object]:
    """Read one manifest from a dispatch record without copying arbitrary record data."""
    has_manifest = "guidance_manifest" in record
    has_legacy = "instruction_delivery" in record
    if not has_manifest:
        if not has_legacy:
            return _unknown_manifest()
        parsed_legacy = _manifest_from_proof(record["instruction_delivery"])
        return (
            parsed_legacy
            if parsed_legacy is not None and _manifest_matches_lane(record, parsed_legacy)
            else _unclassified_manifest()
        )
    value = record["guidance_manifest"]
    parsed = _parse_manifest(value)
    if parsed is None or not _manifest_matches_lane(record, parsed):
        return _unclassified_manifest()
    legacy_matches = True
    if has_legacy:
        parsed_legacy = _manifest_from_proof(record["instruction_delivery"])
        legacy_matches = (
            parsed["state"] == GUIDANCE_STATE_VERIFIED
            and parsed_legacy is not None
            and parsed["delivery"] == parsed_legacy["delivery"]
        )
    return parsed if legacy_matches else _unclassified_manifest()


def normalize(text: str) -> str:
    """Apply the versioned newline normalization used by expected and delivered text."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _byte_length(text: str) -> int:
    return len(text.encode("utf-8"))


def _safe_path(path: Path, root: Path) -> str:
    """Render a relative source identity without allowing a filename to add output lines."""
    relative = path.relative_to(root).as_posix()
    return relative.replace("\r", "\\r").replace("\n", "\\n")


def _proof_lines(proof: GuidanceProof) -> tuple[str, ...]:
    """Render proof measurements for a refusal without rendering any body text."""
    lines = [
        f"schema={CODEX_GUIDANCE_SCHEMA}",
        f"normalization={CODEX_GUIDANCE_NORMALIZATION}",
        f"codex_version={proof.codex_version}",
        f"launch_directory={proof.launch_directory}",
        f"project_doc_max_bytes={proof.project_doc_max_bytes}",
        f"raw_project_bytes={proof.raw_project_bytes}",
        f"expected_project_bytes={proof.expected_project_bytes}",
        f"expected_project_sha256={proof.expected_project_sha256}",
        f"delivered_project_bytes={proof.delivered_project_bytes}",
        f"delivered_project_sha256={proof.delivered_project_sha256}",
        f"global_expected_bytes={proof.global_expected_bytes}",
        f"global_expected_sha256={proof.global_expected_sha256}",
        f"global_delivered_bytes={proof.global_delivered_bytes}",
        f"global_delivered_sha256={proof.global_delivered_sha256}",
        f"combined_delivered_sha256={proof.combined_delivered_sha256}",
    ]
    lines.extend(f"source_path={source.path}" for source in proof.sources)
    return tuple(lines)


def _failure(  # noqa: PLR0913 — the safe failure carries the bounded preflight context
    reason: str,
    context: LaunchContext,
    *,
    launch_directory: Path | None = None,
    codex_version: str = "",
    source_paths: tuple[str, ...] = (),
    evidence: GuidanceProof | None = None,
) -> GuidanceFailure:
    return GuidanceFailure(
        reason=reason,
        codex_version=codex_version,
        launch_directory="" if launch_directory is None else str(launch_directory),
        project_doc_max_bytes=_project_doc_max(context.loader_config),
        source_paths=source_paths,
        evidence=evidence,
    )


def _project_doc_max(overrides: tuple[str, ...]) -> int:
    for override in overrides:
        key, separator, value = override.partition("=")
        if key == "project_doc_max_bytes" and separator:
            try:
                return int(value)
            except ValueError:
                return CODEX_PROJECT_DOC_CONTAINMENT_BYTES
    return CODEX_PROJECT_DOC_CONTAINMENT_BYTES


def _with_project_doc_max(overrides: tuple[str, ...], max_bytes: int) -> tuple[str, ...]:
    result = tuple(
        f"project_doc_max_bytes={max_bytes}"
        if override.startswith("project_doc_max_bytes=")
        else override
        for override in overrides
    )
    if any(override.startswith("project_doc_max_bytes=") for override in result):
        return result
    return (*result, f"project_doc_max_bytes={max_bytes}")


def _config_argv(overrides: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(part for override in overrides for part in ("--config", override))


def _run(
    argv: tuple[str, ...], context: LaunchContext
) -> subprocess.CompletedProcess[bytes] | GuidanceFailure:
    try:
        return subprocess.run(  # noqa: S603 — executable and args are the dispatch plan
            list(argv),
            cwd=context.cwd,
            env=dict(context.environment),
            capture_output=True,
            check=False,
            timeout=context.timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return _failure("loader_timeout", context)
    except (OSError, ValueError):
        return _failure("loader_exit", context)


def _codex_version(context: LaunchContext) -> str | GuidanceFailure:
    result = _run((context.executable, "--version"), context)
    if isinstance(result, GuidanceFailure):
        return result
    if result.returncode != 0:
        return _failure("loader_exit", context)
    try:
        output = result.stdout.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return _failure("loader_exit", context)
    version = next((line.strip() for line in output.splitlines() if line.strip()), "")
    if not version:
        return _failure("loader_exit", context)
    return version


def _json_strings(value: object) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for child in value.values():
            yield from _json_strings(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _json_strings(child)


def _instruction_body(payload: object) -> tuple[str, str] | str:
    """Find exactly one wrapper and return its fragment and body, or a stable reason."""
    candidates: list[tuple[str, int, int]] = []
    for text in _json_strings(payload):
        start = 0
        while True:
            found = text.find(_INSTRUCTION_START, start)
            if found < 0:
                break
            open_at = text.find(_INSTRUCTION_OPEN, found)
            if open_at < 0:
                candidates.append((text, found, -1))
                break
            body_start = open_at + len(_INSTRUCTION_OPEN)
            close_at = text.find(_INSTRUCTION_CLOSE, body_start)
            candidates.append((text, found, close_at))
            start = close_at + len(_INSTRUCTION_CLOSE) if close_at >= 0 else len(text)
    if not candidates:
        return "missing_wrapper"
    if len(candidates) > 1:
        return "duplicate_wrapper"
    text, start, close_at = candidates[0]
    if close_at < 0:
        return "missing_wrapper"
    body_start = text.find(_INSTRUCTION_OPEN, start) + len(_INSTRUCTION_OPEN)
    fragment_end = close_at + len(_INSTRUCTION_CLOSE)
    return text[start:fragment_end], text[body_start:close_at]


def _capture(  # noqa: PLR0913 — each capture needs its scope and safe diagnostic context
    context: LaunchContext,
    *,
    max_bytes: int,
    global_only: bool,
    codex_version: str,
    launch_directory: Path,
    source_paths: tuple[str, ...],
) -> tuple[str, GuidanceFailure] | tuple[None, GuidanceFailure] | tuple[str, None]:
    overrides = _with_project_doc_max(context.loader_config, max_bytes)
    result = _run(
        (context.executable, "debug", "prompt-input", *_config_argv(overrides)),
        context,
    )
    if isinstance(result, GuidanceFailure):
        reason = "unreadable_global_only_result" if global_only else result.reason
        return None, _failure(
            reason,
            context,
            launch_directory=launch_directory,
            codex_version=codex_version,
            source_paths=source_paths,
        )
    if result.returncode != 0:
        reason = "unreadable_global_only_result" if global_only else "loader_exit"
        return None, _failure(
            reason,
            context,
            launch_directory=launch_directory,
            codex_version=codex_version,
            source_paths=source_paths,
        )
    try:
        payload = json.loads(result.stdout)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
        reason = "unreadable_global_only_result" if global_only else "invalid_json"
        return None, _failure(
            reason,
            context,
            launch_directory=launch_directory,
            codex_version=codex_version,
            source_paths=source_paths,
        )
    extracted = _instruction_body(payload)
    if isinstance(extracted, str):
        if (
            global_only
            and max_bytes == 0
            and extracted == "missing_wrapper"
            and isinstance(payload, list)
        ):
            # Codex emits no wrapper when its global instruction prefix is empty. That is a
            # valid empty capture, not an unreadable result.
            return "", None
        reason = "unreadable_global_only_result" if global_only else extracted
        return None, _failure(
            reason,
            context,
            launch_directory=launch_directory,
            codex_version=codex_version,
            source_paths=source_paths,
        )
    _fragment, body = extracted
    # The wrapper's opening tag is followed by one formatting newline. Exclude that
    # delimiter so a zero-length global capture is genuinely empty and the project
    # separator is the first delivered byte after subtraction.
    return normalize(body.removeprefix("\n")), None


def _git_root(context: LaunchContext) -> Path | GuidanceFailure:
    result = _run(("git", "rev-parse", "--show-toplevel"), context)
    if isinstance(result, GuidanceFailure) or result.returncode != 0:
        return _failure("project_root_unavailable", context)
    try:
        output = result.stdout.decode("utf-8", errors="strict").strip()
        return Path(output).resolve(strict=True)
    except (UnicodeDecodeError, OSError, ValueError):
        return _failure("project_root_unavailable", context)


def _launch_directory(context: LaunchContext, root: Path) -> Path | GuidanceFailure:
    try:
        launch = context.cwd.resolve(strict=True)
        launch.relative_to(root)
        if not launch.is_dir():
            return _failure("launch_directory_unavailable", context)
    except (OSError, ValueError):
        return _failure("launch_directory_unavailable", context)
    else:
        return launch


def _directories(root: Path, launch: Path) -> tuple[Path, ...]:
    relative = launch.relative_to(root)
    directories = [root]
    directories.extend(directories[-1] / part for part in relative.parts)
    return tuple(directories)


def _select_source(directory: Path) -> Path | GuidanceFailure | None:
    for filename in ("AGENTS.override.md", "AGENTS.md"):
        candidate = directory / filename
        try:
            information = candidate.stat()
        except FileNotFoundError:
            continue
        except OSError:
            return GuidanceFailure("source_metadata", source_paths=(filename,))
        if stat.S_ISREG(information.st_mode):
            return candidate
    return None


def _read_sources(
    root: Path, launch: Path, context: LaunchContext
) -> tuple[tuple[SourceRecord, ...], GuidanceFailure | None]:
    sources: list[SourceRecord] = []
    paths: list[str] = []
    for directory in _directories(root, launch):
        selected = _select_source(directory)
        if isinstance(selected, GuidanceFailure):
            return (), _failure(
                selected.reason,
                context,
                launch_directory=launch,
                source_paths=tuple(paths),
            )
        if selected is None:
            if directory == root:
                return (), _failure(
                    "missing_source",
                    context,
                    launch_directory=launch,
                    source_paths=tuple(paths),
                )
            continue
        path = _safe_path(selected, root)
        paths.append(path)
        try:
            raw = selected.read_bytes()
        except OSError:
            return (), _failure(
                "unreadable_source",
                context,
                launch_directory=launch,
                source_paths=tuple(paths),
            )
        try:
            text = normalize(raw.decode("utf-8", errors="strict"))
        except UnicodeDecodeError:
            return (), _failure(
                "invalid_utf8",
                context,
                launch_directory=launch,
                source_paths=tuple(paths),
            )
        sources.append(SourceRecord(path=path, raw_bytes=len(raw), sha256=_sha256(text), text=text))
    return tuple(sources), None


def _project_text(sources: tuple[SourceRecord, ...]) -> str:
    return "\n\n".join(source.text for source in sources if source.text.strip())


def _evidence(  # noqa: PLR0913 — one immutable measurement object owns all proof fields
    *,
    version: str,
    launch: Path,
    max_bytes: int,
    sources: tuple[SourceRecord, ...],
    expected_project: str,
    delivered_project: str,
    global_expected: str,
    global_delivered: str,
    combined_delivered: str,
) -> GuidanceProof:
    return GuidanceProof(
        codex_version=version,
        launch_directory=str(launch),
        project_doc_max_bytes=max_bytes,
        sources=sources,
        raw_project_bytes=sum(source.raw_bytes for source in sources),
        expected_project_bytes=_byte_length(expected_project),
        expected_project_sha256=_sha256(expected_project),
        delivered_project_bytes=_byte_length(delivered_project),
        delivered_project_sha256=_sha256(delivered_project),
        global_expected_bytes=_byte_length(global_expected),
        global_expected_sha256=_sha256(global_expected),
        global_delivered_bytes=_byte_length(global_delivered),
        global_delivered_sha256=_sha256(global_delivered),
        combined_delivered_sha256=_sha256(combined_delivered),
    )


def _project_capture(global_body: str, full_body: str) -> str | None:
    """Extract project text from Codex's global-plus-project or project-only capture."""
    if not global_body:
        # Codex omits the separator when no global instruction prefix exists. The fake matrix
        # retains the separator shape for older deterministic cases, so accept both forms.
        return full_body.removeprefix(CODEX_PROJECT_SEPARATOR)
    if not full_body.startswith(global_body):
        return None
    remainder = full_body[len(global_body) :]
    if not remainder.startswith(CODEX_PROJECT_SEPARATOR):
        return None
    return remainder[len(CODEX_PROJECT_SEPARATOR) :]


def verify_delivery(  # noqa: PLR0911 — fail-closed ladder
    context: LaunchContext,
) -> GuidanceResult:
    """Return a proof or a fail-closed reason before any agent work starts."""
    root = _git_root(context)
    if isinstance(root, GuidanceFailure):
        return root
    launch = _launch_directory(context, root)
    if isinstance(launch, GuidanceFailure):
        return launch

    sources, failure = _read_sources(root, launch, context)
    if failure is not None:
        return failure
    source_paths = tuple(source.path for source in sources)

    version = _codex_version(context)
    if isinstance(version, GuidanceFailure):
        return _failure(
            version.reason,
            context,
            launch_directory=launch,
            source_paths=source_paths,
        )

    full_body, failure = _capture(
        context,
        max_bytes=_project_doc_max(context.loader_config),
        global_only=False,
        codex_version=version,
        launch_directory=launch,
        source_paths=source_paths,
    )
    if failure is not None or full_body is None:
        return failure or _failure(
            "loader_exit",
            context,
            launch_directory=launch,
            codex_version=version,
            source_paths=source_paths,
        )
    global_body, failure = _capture(
        context,
        max_bytes=0,
        global_only=True,
        codex_version=version,
        launch_directory=launch,
        source_paths=source_paths,
    )
    if failure is not None or global_body is None:
        return failure or _failure(
            "unreadable_global_only_result",
            context,
            launch_directory=launch,
            codex_version=version,
            source_paths=source_paths,
        )

    delivered_project = _project_capture(global_body, full_body)
    if delivered_project is None:
        return _failure(
            "unreadable_global_only_result",
            context,
            launch_directory=launch,
            codex_version=version,
            source_paths=source_paths,
        )
    # The prompt wrapper contributes one newline before its closing tag. Remove that
    # wrapper byte only; the source chain's own final-newline state remains untouched.
    delivered_project = delivered_project.removesuffix("\n")
    expected_project = _project_text(sources)
    proof = _evidence(
        version=version,
        launch=launch,
        max_bytes=_project_doc_max(context.loader_config),
        sources=sources,
        expected_project=expected_project,
        delivered_project=delivered_project,
        global_expected=global_body,
        global_delivered=full_body[: len(global_body)],
        combined_delivered=full_body,
    )
    if expected_project != delivered_project:
        return GuidanceFailure("instruction_delivery_mismatch", evidence=proof)
    return proof
