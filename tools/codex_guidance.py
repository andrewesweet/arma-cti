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
from enum import StrEnum
from pathlib import Path
from typing import Final, Self

CODEX_PROJECT_DOC_DEFAULT_BYTES: Final = 32 * 1024
CODEX_PROJECT_DOC_CONTAINMENT_BYTES: Final = 96 * 1024
CODEX_PROJECT_CHAIN_RETIREMENT_BYTES: Final = 24 * 1024
CODEX_GUIDANCE_SCHEMA: Final = "codex-guidance-proof-v1"
CODEX_GUIDANCE_LEDGER_SCHEMA: Final = "codex-guidance-ledger/1"
CODEX_GUIDANCE_NORMALIZATION: Final = "lf-v1"
CODEX_PROJECT_SEPARATOR: Final = "\n--- project-doc ---\n\n"
CODEX_GUIDANCE_SCOPE: Final = "codex_project_instruction_chain"
CODEX_GUIDANCE_TIMEOUT_SECONDS: Final = 30.0
GUIDANCE_MANIFEST_SCHEMA: Final = "cti.guidance-manifest/1"
GUIDANCE_LEDGER_SCHEMA: Final = "cti.guidance-ledger/1"
GUIDANCE_STATE_VERIFIED: Final = "verified"
GUIDANCE_STATE_UNKNOWN: Final = "unknown"
GUIDANCE_STATE_MISSING: Final = "missing"
GUIDANCE_STATE_UNATTRIBUTABLE: Final = "unattributable"
GUIDANCE_STATE_EMPTY: Final = "empty"
GUIDANCE_STATE_UNCLASSIFIED: Final = "unclassified"
UNATTRIBUTABLE_REASON: Final = "no bounded capture"
_HASH_HEX_LENGTH: Final = 64
_CODEX_VERSION_PATTERN: Final = re.compile(
    r"codex-cli (?P<major>0|[1-9]\d*)\."
    r"(?P<minor>0|[1-9]\d*)\."
    r"(?P<patch>0|[1-9]\d*)"
)
_INSTRUCTION_START = "# AGENTS.md instructions"
_INSTRUCTION_OPEN = "<INSTRUCTIONS>"
_INSTRUCTION_CLOSE = "</INSTRUCTIONS>"


class InvalidGuidanceProofError(ValueError):
    """A supplied proof field has an invalid type, shape, or source total."""


class UnmatchedGuidanceProofError(ValueError):
    """Failure evidence was offered as a verified guidance manifest."""


@dataclass(frozen=True, init=False)
class CodexVersion:
    """A parsed Codex CLI release, never an arbitrary metadata string."""

    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, value: object) -> Self | None:
        """Parse the exact CLI release grammar into numeric components."""
        if not isinstance(value, str):
            return None
        match = _CODEX_VERSION_PATTERN.fullmatch(value)
        if match is None:
            return None
        try:
            major = int(match.group("major"))
            minor = int(match.group("minor"))
            patch = int(match.group("patch"))
        except ValueError:
            return None
        parsed = object.__new__(cls)
        object.__setattr__(parsed, "major", major)
        object.__setattr__(parsed, "minor", minor)
        object.__setattr__(parsed, "patch", patch)
        return parsed

    def document(self) -> str:
        """Render only the canonical version represented by the components."""
        return f"codex-cli {self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True, init=False)
class ResolvedLaunchDirectory:
    """A launch directory resolved at capture or matched to its recorded worktree."""

    path: Path

    @classmethod
    def in_repository(cls, directory: Path, repository: Path) -> Self | None:
        """Resolve one existing launch directory inside an existing repository."""
        try:
            resolved_repository = repository.resolve(strict=True)
            resolved = directory.resolve(strict=True)
            resolved.relative_to(resolved_repository)
            if not resolved.is_dir():
                return None
        except (OSError, ValueError):
            return None
        return cls._from_resolved(resolved)

    @classmethod
    def matching_worktree(cls, value: object, worktree: object) -> Self | None:
        """Accept exact absolute record equality without resolving either untrusted path."""
        if not isinstance(value, str) or not isinstance(worktree, str):
            return None
        candidate = Path(value)
        if value != worktree or not candidate.is_absolute():
            return None
        return cls._from_resolved(candidate)

    @classmethod
    def _from_resolved(cls, path: Path) -> Self:
        resolved = object.__new__(cls)
        object.__setattr__(resolved, "path", path)
        return resolved

    def document(self) -> str:
        """Render the canonical resolution, never the untrusted input spelling."""
        return str(self.path)


class GuidanceHarness(StrEnum):
    """Runner families as recorded by the authoritative lane registry."""

    CLAUDE_CODE = "claude-code"
    CODEX = "codex"


class LaunchDirectoryCategory(StrEnum):
    """Ledger-safe relationship between launch directory and dispatch record."""

    RECORDED_WORKTREE_MATCH = "recorded_worktree_match"


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

    def ledger_document(self) -> dict[str, object]:
        """Identify the ordered source without sending its path to telemetry."""
        return {
            "path_sha256": _sha256(self.path),
            "path_bytes": _byte_length(self.path),
            "raw_bytes": self.raw_bytes,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, init=False)
class GuidanceProof:
    """Matched measurements retained as the dispatch's primary evidence."""

    codex_version: CodexVersion
    launch_directory: ResolvedLaunchDirectory
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

    @classmethod
    def _from_validated(  # noqa: PLR0913 — one proof owns every measured field
        cls,
        *,
        codex_version: CodexVersion,
        launch_directory: ResolvedLaunchDirectory,
        project_doc_max_bytes: int,
        sources: tuple[SourceRecord, ...],
        raw_project_bytes: int,
        expected_project_bytes: int,
        expected_project_sha256: str,
        delivered_project_bytes: int,
        delivered_project_sha256: str,
        global_expected_bytes: int,
        global_expected_sha256: str,
        global_delivered_bytes: int,
        global_delivered_sha256: str,
        combined_delivered_sha256: str,
    ) -> Self:
        """Validate and construct one proof from capture or parsed measurements."""
        valid_sources = (
            isinstance(sources, tuple)
            and bool(sources)
            and all(_valid_source_record(source) for source in sources)
        )
        if (
            not _valid_codex_version(codex_version)
            or not _valid_launch_directory(launch_directory)
            or not _valid_nonnegative_int(project_doc_max_bytes)
            or not valid_sources
            or not _valid_nonnegative_int(raw_project_bytes)
            or raw_project_bytes != sum(source.raw_bytes for source in sources)
            or not _valid_nonnegative_int(expected_project_bytes)
            or not _valid_hash(expected_project_sha256)
            or not _valid_nonnegative_int(delivered_project_bytes)
            or not _valid_hash(delivered_project_sha256)
            or not _valid_nonnegative_int(global_expected_bytes)
            or not _valid_hash(global_expected_sha256)
            or not _valid_nonnegative_int(global_delivered_bytes)
            or not _valid_hash(global_delivered_sha256)
            or not _valid_hash(combined_delivered_sha256)
        ):
            raise InvalidGuidanceProofError
        proof = object.__new__(cls)
        for name, value in (
            ("codex_version", codex_version),
            ("launch_directory", launch_directory),
            ("project_doc_max_bytes", project_doc_max_bytes),
            ("sources", sources),
            ("raw_project_bytes", raw_project_bytes),
            ("expected_project_bytes", expected_project_bytes),
            ("expected_project_sha256", expected_project_sha256),
            ("delivered_project_bytes", delivered_project_bytes),
            ("delivered_project_sha256", delivered_project_sha256),
            ("global_expected_bytes", global_expected_bytes),
            ("global_expected_sha256", global_expected_sha256),
            ("global_delivered_bytes", global_delivered_bytes),
            ("global_delivered_sha256", global_delivered_sha256),
            ("combined_delivered_sha256", combined_delivered_sha256),
        ):
            object.__setattr__(proof, name, value)
        return proof

    def document(self) -> dict[str, object]:
        """Render dispatch evidence without source bodies, prompt bodies, brief, or environment."""
        return {
            "schema": CODEX_GUIDANCE_SCHEMA,
            "normalization": CODEX_GUIDANCE_NORMALIZATION,
            "codex_version": self.codex_version.document(),
            "launch_directory": self.launch_directory.document(),
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

    def ledger_document(self) -> dict[str, object]:
        """Render only hashes, byte counts, and the launch-directory category."""
        version = self.codex_version.document()
        return {
            "schema": CODEX_GUIDANCE_LEDGER_SCHEMA,
            "normalization": CODEX_GUIDANCE_NORMALIZATION,
            "codex_version_sha256": _sha256(version),
            "codex_version_bytes": _byte_length(version),
            "launch_directory": LaunchDirectoryCategory.RECORDED_WORKTREE_MATCH.value,
            "project_doc_max_bytes": self.project_doc_max_bytes,
            "sources": [source.ledger_document() for source in self.sources],
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

    def manifest(self) -> VerifiedGuidanceManifest:
        """Construct the sole manifest variant a successful proof can inhabit."""
        return VerifiedGuidanceManifest(self)


@dataclass(frozen=True)
class VerifiedGuidanceManifest:
    """A complete matched Codex proof; no state or tuple can be supplied by a caller."""

    delivery: GuidanceProof

    def __post_init__(self) -> None:
        """Refuse a non-proof or unmatched failure evidence as verified guidance."""
        if not isinstance(self.delivery, GuidanceProof) or not _proof_matches(self.delivery):
            raise UnmatchedGuidanceProofError

    def document(self) -> dict[str, object]:
        """Render the only valid verified-manifest shape."""
        return {
            "schema": GUIDANCE_MANIFEST_SCHEMA,
            "state": GUIDANCE_STATE_VERIFIED,
            "harness": GuidanceHarness.CODEX.value,
            # Codex reports delivered text but not LoadedAgentsMd.sources(). The paths below
            # are the independently derived expected chain, never a claim about loader origin.
            "source_provenance": "expected_chain_only",
            "loader_outcome": "matched",
            "delivery": self.delivery.document(),
        }

    def ledger_document(self) -> dict[str, object]:
        """Project the proof into the ledger's content-free schema."""
        return {
            "schema": GUIDANCE_LEDGER_SCHEMA,
            "state": GUIDANCE_STATE_VERIFIED,
            "harness": GuidanceHarness.CODEX.value,
            "source_provenance": "expected_chain_only",
            "loader_outcome": "matched",
            "delivery": self.delivery.ledger_document(),
        }


@dataclass(frozen=True)
class MissingGuidanceManifest:
    """A Codex dispatch whose required preflight proof was absent."""

    launch_directory: ResolvedLaunchDirectory

    def document(self) -> dict[str, object]:
        """Render the only valid missing-manifest shape."""
        return {
            "schema": GUIDANCE_MANIFEST_SCHEMA,
            "state": GUIDANCE_STATE_MISSING,
            "harness": GuidanceHarness.CODEX.value,
            "source_provenance": "not_available",
            "loader_outcome": "not_run",
            "reason": "missing_preflight_manifest",
            "sources": None,
            "launch_context": {"launch_directory": self.launch_directory.document()},
        }

    def ledger_document(self) -> dict[str, object]:
        """Render the missing outcome without an absolute directory."""
        return {
            **self.document(),
            "schema": GUIDANCE_LEDGER_SCHEMA,
            "launch_context": {
                "launch_directory": LaunchDirectoryCategory.RECORDED_WORKTREE_MATCH.value
            },
        }


@dataclass(frozen=True)
class UnattributableGuidanceManifest:
    """A Claude Code dispatch whose harness exposes no bounded source capture."""

    launch_directory: ResolvedLaunchDirectory

    def document(self) -> dict[str, object]:
        """Render the only valid unattributable-manifest shape."""
        return {
            "schema": GUIDANCE_MANIFEST_SCHEMA,
            "state": GUIDANCE_STATE_UNATTRIBUTABLE,
            "harness": GuidanceHarness.CLAUDE_CODE.value,
            "source_provenance": "not_exposed",
            "loader_outcome": "not_observable",
            "reason": UNATTRIBUTABLE_REASON,
            "sources": None,
            "launch_context": {"launch_directory": self.launch_directory.document()},
        }

    def ledger_document(self) -> dict[str, object]:
        """Render the unattributable outcome without an absolute directory."""
        return {
            **self.document(),
            "schema": GUIDANCE_LEDGER_SCHEMA,
            "launch_context": {
                "launch_directory": LaunchDirectoryCategory.RECORDED_WORKTREE_MATCH.value
            },
        }


@dataclass(frozen=True)
class EmptyGuidanceManifest:
    """A Codex loader result that explicitly reported no active sources."""

    launch_directory: ResolvedLaunchDirectory

    def document(self) -> dict[str, object]:
        """Render the only valid empty-manifest shape."""
        return {
            "schema": GUIDANCE_MANIFEST_SCHEMA,
            "state": GUIDANCE_STATE_EMPTY,
            "harness": GuidanceHarness.CODEX.value,
            "source_provenance": "loader_reported",
            "loader_outcome": "empty",
            "reason": "loader_returned_no_sources",
            "sources": [],
            "launch_context": {"launch_directory": self.launch_directory.document()},
        }

    def ledger_document(self) -> dict[str, object]:
        """Render the empty outcome without an absolute directory."""
        return {
            **self.document(),
            "schema": GUIDANCE_LEDGER_SCHEMA,
            "launch_context": {
                "launch_directory": LaunchDirectoryCategory.RECORDED_WORKTREE_MATCH.value
            },
        }


@dataclass(frozen=True)
class GuidanceNotRecorded:
    """Reader result for a historical record carrying no guidance manifest."""

    def document(self) -> dict[str, object]:
        """Render absence found by the reader, never a guidance-manifest variant."""
        return {
            "schema": GUIDANCE_MANIFEST_SCHEMA,
            "state": GUIDANCE_STATE_UNKNOWN,
            "harness": None,
            "source_provenance": "not_available",
            "loader_outcome": "not_available",
            "reason": "historical_manifest_absent",
            "sources": None,
            "launch_context": {},
        }

    def ledger_document(self) -> dict[str, object]:
        """Render historical absence in the ledger schema."""
        return {**self.document(), "schema": GUIDANCE_LEDGER_SCHEMA}


@dataclass(frozen=True)
class UnclassifiedGuidanceRecord:
    """Reader result for external JSON that constructs no guidance manifest."""

    def document(self) -> dict[str, object]:
        """Render the safe category without copying the rejected document."""
        return {
            "schema": GUIDANCE_MANIFEST_SCHEMA,
            "state": GUIDANCE_STATE_UNCLASSIFIED,
            "harness": None,
            "source_provenance": "not_available",
            "loader_outcome": "not_available",
            "reason": "unclassified_guidance_record",
            "sources": None,
            "launch_context": {},
        }

    def ledger_document(self) -> dict[str, object]:
        """Render rejection without copying the rejected document."""
        return {**self.document(), "schema": GUIDANCE_LEDGER_SCHEMA}


type GuidanceManifest = (
    VerifiedGuidanceManifest
    | MissingGuidanceManifest
    | UnattributableGuidanceManifest
    | EmptyGuidanceManifest
)
type GuidanceRecord = GuidanceManifest | GuidanceNotRecorded | UnclassifiedGuidanceRecord


@dataclass(frozen=True)
class GuidanceFailure:
    """A safe preflight failure; raw child output is intentionally never exposed."""

    reason: str
    codex_version: CodexVersion | None = None
    launch_directory: ResolvedLaunchDirectory | None = None
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
        if self.codex_version is not None:
            lines.append(f"codex_version={self.codex_version.document()}")
        if self.launch_directory is not None:
            lines.append(f"launch_directory={self.launch_directory.document()}")
        lines.append(f"project_doc_max_bytes={self.project_doc_max_bytes}")
        lines.extend(f"source_path={path}" for path in self.source_paths)
        return tuple(lines)


GuidanceResult = GuidanceProof | GuidanceFailure


def _valid_hash(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == _HASH_HEX_LENGTH
        and all(character in "0123456789abcdef" for character in value)
    )


def _valid_nonnegative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _valid_utf8_text(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _valid_codex_version(value: object) -> bool:
    if not isinstance(value, CodexVersion):
        return False
    try:
        canonical = value.document()
    except (AttributeError, TypeError, ValueError):
        return False
    return CodexVersion.parse(canonical) == value


def _valid_launch_directory(value: object) -> bool:
    if not isinstance(value, ResolvedLaunchDirectory):
        return False
    try:
        path = value.path
    except AttributeError:
        return False
    return isinstance(path, Path) and path.is_absolute() and _valid_utf8_text(str(path))


def _valid_source_record(value: object) -> bool:
    if not isinstance(value, SourceRecord):
        return False
    try:
        return (
            _valid_utf8_text(value.path)
            and "\r" not in value.path
            and "\n" not in value.path
            and _valid_nonnegative_int(value.raw_bytes)
            and _valid_hash(value.sha256)
            and _valid_utf8_text(value.text)
        )
    except AttributeError:
        return False


def _valid_source(value: object) -> bool:
    if not isinstance(value, Mapping) or set(value) != {"path", "raw_bytes", "sha256"}:
        return False
    path = value["path"]
    return (
        isinstance(path, str)
        and _valid_utf8_text(path)
        and "\r" not in path
        and "\n" not in path
        and _valid_nonnegative_int(value["raw_bytes"])
        and _valid_hash(value["sha256"])
    )


def _proof_matches(proof: GuidanceProof) -> bool:
    return (
        proof.expected_project_bytes == proof.delivered_project_bytes
        and proof.expected_project_sha256 == proof.delivered_project_sha256
        and proof.global_expected_bytes == proof.global_delivered_bytes
        and proof.global_expected_sha256 == proof.global_delivered_sha256
    )


def _proof_from_document(value: object, worktree: object) -> GuidanceProof | None:
    """Parse untyped JSON at its unavoidable boundary into proof value objects.

    Serialized historical records can carry arbitrary JSON, so this is the one place
    validation remains after the fact. Nothing past this seam receives the raw version or
    launch-directory strings, and any document that cannot construct the typed proof becomes
    `unclassified` without being copied.
    """
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
        return None
    sources = value["sources"]
    source_paths = value["source_paths"]
    if (
        not isinstance(sources, list)
        or not sources
        or not all(_valid_source(source) for source in sources)
        or not isinstance(source_paths, list)
        or source_paths != [source["path"] for source in sources]
    ):
        return None
    if not all(isinstance(path, str) for path in source_paths):
        return None
    codex_version = CodexVersion.parse(value["codex_version"])
    launch_directory = ResolvedLaunchDirectory.matching_worktree(
        value["launch_directory"], worktree
    )
    if (
        value["schema"] != CODEX_GUIDANCE_SCHEMA
        or value["normalization"] != CODEX_GUIDANCE_NORMALIZATION
        or codex_version is None
        or launch_directory is None
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
        return None
    if (
        value["raw_project_bytes"] != sum(source["raw_bytes"] for source in sources)
        or value["expected_project_bytes"] != value["delivered_project_bytes"]
        or value["expected_project_sha256"] != value["delivered_project_sha256"]
        or value["global_expected_bytes"] != value["global_delivered_bytes"]
        or value["global_expected_sha256"] != value["global_delivered_sha256"]
    ):
        return None
    proof: GuidanceProof | None
    try:
        proof = GuidanceProof._from_validated(  # noqa: SLF001 — boundary owns this factory
            codex_version=codex_version,
            launch_directory=launch_directory,
            project_doc_max_bytes=value["project_doc_max_bytes"],
            sources=tuple(
                SourceRecord(
                    path=source["path"],
                    raw_bytes=source["raw_bytes"],
                    sha256=source["sha256"],
                    text="",
                )
                for source in sources
            ),
            raw_project_bytes=value["raw_project_bytes"],
            expected_project_bytes=value["expected_project_bytes"],
            expected_project_sha256=value["expected_project_sha256"],
            delivered_project_bytes=value["delivered_project_bytes"],
            delivered_project_sha256=value["delivered_project_sha256"],
            global_expected_bytes=value["global_expected_bytes"],
            global_expected_sha256=value["global_expected_sha256"],
            global_delivered_bytes=value["global_delivered_bytes"],
            global_delivered_sha256=value["global_delivered_sha256"],
            combined_delivered_sha256=value["combined_delivered_sha256"],
        )
    except InvalidGuidanceProofError:
        proof = None
    canonical_input = dict(value)
    if proof is not None:
        canonical_input["launch_directory"] = launch_directory.document()
    return proof if proof is not None and proof.document() == canonical_input else None


def _manifest_from_proof(value: object, worktree: object) -> VerifiedGuidanceManifest | None:
    proof = _proof_from_document(value, worktree)
    return None if proof is None else proof.manifest()


def _launch_context(value: object, worktree: object) -> ResolvedLaunchDirectory | None:
    if not isinstance(value, Mapping) or set(value) != {"launch_directory"}:
        return None
    return ResolvedLaunchDirectory.matching_worktree(value["launch_directory"], worktree)


def _parse_manifest(
    value: object,
    worktree: object,
    harness: GuidanceHarness | None,
) -> GuidanceManifest | None:
    """Construct one recorded variant from external JSON, or no variant at all.

    A serialized record is necessarily untyped and may be tampered after dispatch. This
    boundary parser is the argued exception to unrepresentable invalid states: it must inspect
    bytes before it can construct a type. Exact comparison is against each variant's own
    serializer, so no second tuple table exists and rejected free text is never retained.
    """
    if not isinstance(value, Mapping) or value.get("schema") != GUIDANCE_MANIFEST_SCHEMA:
        return None
    state = value.get("state")
    candidate: GuidanceManifest | None = None
    if state == GUIDANCE_STATE_VERIFIED and harness is GuidanceHarness.CODEX:
        candidate = _manifest_from_proof(value.get("delivery"), worktree)
    elif state in (
        GUIDANCE_STATE_MISSING,
        GUIDANCE_STATE_UNATTRIBUTABLE,
        GUIDANCE_STATE_EMPTY,
    ):
        launch_directory = _launch_context(value.get("launch_context"), worktree)
        if launch_directory is None:
            return None
        if state == GUIDANCE_STATE_MISSING and harness is GuidanceHarness.CODEX:
            candidate = MissingGuidanceManifest(launch_directory)
        elif state == GUIDANCE_STATE_UNATTRIBUTABLE and harness is GuidanceHarness.CLAUDE_CODE:
            candidate = UnattributableGuidanceManifest(launch_directory)
        elif state == GUIDANCE_STATE_EMPTY and harness is GuidanceHarness.CODEX:
            candidate = EmptyGuidanceManifest(launch_directory)
    if candidate is None:
        return None
    canonical_input = dict(value)
    if isinstance(candidate, VerifiedGuidanceManifest):
        canonical_input["delivery"] = candidate.delivery.document()
    else:
        canonical_input["launch_context"] = {
            "launch_directory": candidate.launch_directory.document()
        }
    return candidate if candidate.document() == canonical_input else None


def manifest_from_record(
    record: Mapping[str, object], harness: GuidanceHarness | None
) -> GuidanceRecord:
    """Read one typed manifest without copying arbitrary dispatch-record data."""
    has_manifest = "guidance_manifest" in record
    has_legacy = "instruction_delivery" in record
    worktree = record.get("worktree")
    if not has_manifest:
        if not has_legacy:
            return GuidanceNotRecorded()
        parsed_legacy = _manifest_from_proof(record["instruction_delivery"], worktree)
        return (
            parsed_legacy
            if (parsed_legacy is not None and harness is GuidanceHarness.CODEX)
            else UnclassifiedGuidanceRecord()
        )
    parsed = _parse_manifest(record["guidance_manifest"], worktree, harness)
    if parsed is None:
        return UnclassifiedGuidanceRecord()
    if has_legacy:
        parsed_legacy = _manifest_from_proof(record["instruction_delivery"], worktree)
        if (
            not isinstance(parsed, VerifiedGuidanceManifest)
            or parsed_legacy is None
            or parsed.delivery != parsed_legacy.delivery
        ):
            return UnclassifiedGuidanceRecord()
    return parsed


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
        f"codex_version={proof.codex_version.document()}",
        f"launch_directory={proof.launch_directory.document()}",
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
    launch_directory: ResolvedLaunchDirectory | None = None,
    codex_version: CodexVersion | None = None,
    source_paths: tuple[str, ...] = (),
    evidence: GuidanceProof | None = None,
) -> GuidanceFailure:
    return GuidanceFailure(
        reason=reason,
        codex_version=codex_version,
        launch_directory=launch_directory,
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


def _codex_version(context: LaunchContext) -> CodexVersion | GuidanceFailure:
    result = _run((context.executable, "--version"), context)
    if isinstance(result, GuidanceFailure):
        return result
    if result.returncode != 0:
        return _failure("loader_exit", context)
    try:
        output = result.stdout.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return _failure("loader_exit", context)
    rendered = next((line.strip() for line in output.splitlines() if line.strip()), "")
    version = CodexVersion.parse(rendered)
    if version is None:
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
    codex_version: CodexVersion,
    launch_directory: ResolvedLaunchDirectory,
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


def _launch_directory(
    context: LaunchContext, root: Path
) -> ResolvedLaunchDirectory | GuidanceFailure:
    launch = ResolvedLaunchDirectory.in_repository(context.cwd, root)
    if launch is None:
        return _failure("launch_directory_unavailable", context)
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
    root: Path, launch: ResolvedLaunchDirectory, context: LaunchContext
) -> tuple[tuple[SourceRecord, ...], GuidanceFailure | None]:
    sources: list[SourceRecord] = []
    paths: list[str] = []
    for directory in _directories(root, launch.path):
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
    version: CodexVersion,
    launch: ResolvedLaunchDirectory,
    max_bytes: int,
    sources: tuple[SourceRecord, ...],
    expected_project: str,
    delivered_project: str,
    global_expected: str,
    global_delivered: str,
    combined_delivered: str,
) -> GuidanceProof:
    return GuidanceProof._from_validated(  # noqa: SLF001 — capture owns this factory
        codex_version=version,
        launch_directory=launch,
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
