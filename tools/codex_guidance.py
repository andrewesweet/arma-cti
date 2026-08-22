"""Prove that a dispatched Codex process received its complete project guidance.

The dispatcher owns the policy and timing of this check. This module owns the deep
mechanism: source discovery, strict reading, prompt capture, parsing, normalization,
and the privacy-preserving proof record. It compares bytes delivered by Codex's own
debug surface; it never reconstructs the delivered prompt from the source files after the fact.
"""

from __future__ import annotations

import hashlib
import json
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
_INSTRUCTION_START = "# AGENTS.md instructions"
_INSTRUCTION_OPEN = "<INSTRUCTIONS>"
_INSTRUCTION_CLOSE = "</INSTRUCTIONS>"


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
    return "\n\n".join(source.text for source in sources if source.text)


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

    if not full_body.startswith(global_body):
        return _failure(
            "unreadable_global_only_result",
            context,
            launch_directory=launch,
            codex_version=version,
            source_paths=source_paths,
        )
    remainder = full_body[len(global_body) :]
    if not remainder.startswith(CODEX_PROJECT_SEPARATOR):
        return _failure(
            "unreadable_global_only_result",
            context,
            launch_directory=launch,
            codex_version=version,
            source_paths=source_paths,
        )
    delivered_project = remainder[len(CODEX_PROJECT_SEPARATOR) :]
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
