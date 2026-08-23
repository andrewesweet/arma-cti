"""Render and check versioned project-owned harness bundles.

The manifest describes capabilities before it describes destinations. A target
without a capability has no destination entry for that capability, so a
renderer cannot turn an unsupported harness feature into an empty or
equivalent surface. Rendering is useful for temporary layouts; promotion is a
separate, guarded operation for the later installation issue (#505).

Deterministic rendering covers destination ordering, file bytes, and generated
file modes. File mtimes and created-directory modes are intentionally outside
the contract: writes occur now, and directory modes remain subject to umask.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from types import MappingProxyType
from typing import Final, NoReturn, cast

SCHEMA_VERSION: Final = 1
DISPATCH_ID_ENV: Final = "CTI_DISPATCH_ID"
TOKEN_PATTERN: Final = re.compile(r"^[a-z][a-z0-9_-]*$")
CAPABILITY_PATTERN: Final = re.compile(r"^[a-z][a-z0-9_]*$")
PATH_SEPARATORS: Final = frozenset({"\\", "\x00", "\n", "\r", "\t"})
# Target adapters own capability truth. Manifest input may restate but never widen it.
HARNESS_TARGET_CAPABILITIES: Final[Mapping[str, frozenset[str]]] = MappingProxyType(
    {
        "claude-code": frozenset({"hooks", "project_instructions"}),
        "codex": frozenset({"project_instructions"}),
    }
)


class HarnessSurfaceError(ValueError):
    """A manifest, source bundle, or destination cannot drive this renderer."""


class ManifestError(HarnessSurfaceError):
    """The versioned manifest is malformed or internally contradictory."""


class PromotionRefusalError(HarnessSurfaceError):
    """Promotion was refused before any destination byte was changed."""

    def __init__(self, kind: str, detail: str) -> None:
        """Construct one typed refusal with bounded machine-readable detail."""
        self.kind = kind
        self.detail = detail
        super().__init__(f"{kind}: {detail}")


def _manifest_error(message: str) -> NoReturn:
    """Raise one parser error while keeping caller messages machine-readable."""
    raise ManifestError(message)


def _surface_error(message: str) -> NoReturn:
    """Raise one source/destination error while keeping caller messages bounded."""
    raise HarnessSurfaceError(message)


def _promotion_refusal(kind: str, detail: str) -> NoReturn:
    """Raise one typed promotion refusal before any write occurs."""
    raise PromotionRefusalError(kind, detail)


@dataclass(frozen=True)
class Target:
    """One harness target and the capabilities it demonstrably provides."""

    name: str

    def __post_init__(self) -> None:
        """Refuse target names without an implemented support entry."""
        _token(self.name, "target name")
        if self.name not in HARNESS_TARGET_CAPABILITIES:
            _manifest_error(f"target has no harness support: {self.name}")

    @property
    def capabilities(self) -> frozenset[str]:
        """Read capability truth from the target support registry."""
        return HARNESS_TARGET_CAPABILITIES[self.name]

    def supports(self, capability: str) -> bool:
        """Return whether this target has a real surface for ``capability``."""
        return capability in self.capabilities


@dataclass(frozen=True)
class Bundle:
    """One capability-specific source bundle and its supported destinations."""

    name: str
    capability: str
    kind: str
    source_root: str
    files: tuple[str, ...]
    destinations: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        """Keep direct construction inside the same boundary as JSON parsing."""
        _validate_bundle_source(self)
        _validate_bundle_destinations(self)

    def destination_for(self, target: str) -> str | None:
        """Return a target destination, absent when target lacks this bundle."""
        return next((path for name, path in self.destinations if name == target), None)


def _validate_bundle_source(bundle: Bundle) -> None:
    """Validate one bundle's identity and source declaration."""
    _token(bundle.name, "bundle name")
    _token(bundle.capability, f"bundle {bundle.name} capability", capability=True)
    if bundle.kind not in {"file", "directory"}:
        _manifest_error(f"bundle {bundle.name} kind must be file or directory")
    _relative_path(bundle.source_root, f"bundle {bundle.name} source root", allow_dot=True)
    if not isinstance(bundle.files, tuple) or not bundle.files:
        _manifest_error(f"bundle {bundle.name} files must not be empty")
    for relative in bundle.files:
        _relative_path(relative, f"bundle {bundle.name} source file")
    if len(set(bundle.files)) != len(bundle.files):
        _manifest_error(f"bundle {bundle.name} source files contain duplicates")
    if bundle.kind == "file" and len(bundle.files) != 1:
        _manifest_error(f"bundle {bundle.name} file kind requires one source file")


def _validate_bundle_destinations(bundle: Bundle) -> None:
    """Validate one bundle's immutable target-to-path mapping."""
    if not isinstance(bundle.destinations, tuple) or not bundle.destinations:
        _manifest_error(f"bundle {bundle.name} destinations must not be empty")
    destination_targets: list[str] = []
    for item in bundle.destinations:
        if not isinstance(item, tuple):
            _manifest_error(f"bundle {bundle.name} destination must be a pair")
        try:
            target_name, destination = item
        except ValueError:
            _manifest_error(f"bundle {bundle.name} destination must be a pair")
        destination_targets.append(_token(target_name, f"bundle {bundle.name} target"))
        _relative_path(
            destination,
            f"bundle {bundle.name} destination for {target_name}",
            allow_dot=True,
        )
    if len(set(destination_targets)) != len(destination_targets):
        _manifest_error(f"bundle {bundle.name} destination targets contain duplicates")


@dataclass(frozen=True)
class Manifest:
    """Validated manifest with immutable target and bundle declarations."""

    targets: tuple[Target, ...]
    bundles: tuple[Bundle, ...]

    def __post_init__(self) -> None:
        """Validate cross-table invariants for parsed and directly constructed values."""
        _validate_manifest_members(self.targets, self.bundles)
        _validate_manifest_destinations(self.targets, self.bundles)

    def target(self, name: str) -> Target:
        """Resolve one declared target or refuse the unknown target."""
        for target in self.targets:
            if target.name == name:
                return target
        _manifest_error(f"unknown target: {name}")

    def bundle(self, name: str) -> Bundle:
        """Resolve one declared bundle or refuse the unknown bundle."""
        for bundle in self.bundles:
            if bundle.name == name:
                return bundle
        _manifest_error(f"unknown bundle: {name}")

    def bundles_for(self, target: str) -> tuple[Bundle, ...]:
        """Return only bundles with an explicit destination for target."""
        self.target(target)
        return tuple(
            bundle for bundle in self.bundles if bundle.destination_for(target) is not None
        )

    def document(self) -> dict[str, object]:
        """Render canonical JSON data without source content."""
        return {
            "schema_version": SCHEMA_VERSION,
            "targets": {
                target.name: {"capabilities": sorted(target.capabilities)}
                for target in sorted(self.targets, key=lambda item: item.name)
            },
            "bundles": [
                {
                    "name": bundle.name,
                    "capability": bundle.capability,
                    "kind": bundle.kind,
                    "source": {"root": bundle.source_root, "files": list(bundle.files)},
                    "destinations": dict(sorted(bundle.destinations)),
                }
                for bundle in sorted(self.bundles, key=lambda item: item.name)
            ],
        }


def _validate_manifest_members(
    targets: object,
    bundles: object,
) -> None:
    """Validate manifest collection types, contents, and unique names."""
    if not isinstance(targets, tuple) or not targets:
        _manifest_error("manifest must declare at least one target")
    if not all(isinstance(target, Target) for target in targets):
        _manifest_error("manifest targets must be Target values")
    if not isinstance(bundles, tuple) or not bundles:
        _manifest_error("manifest must declare at least one bundle")
    if not all(isinstance(bundle, Bundle) for bundle in bundles):
        _manifest_error("manifest bundles must be Bundle values")
    if len({target.name for target in targets}) != len(targets):
        _manifest_error("manifest targets contain duplicates")
    if len({bundle.name for bundle in bundles}) != len(bundles):
        _manifest_error("manifest bundles contain duplicate names")


def _validate_manifest_destinations(
    targets: tuple[Target, ...],
    bundles: tuple[Bundle, ...],
) -> None:
    """Bind every bundle destination to one supported target capability."""
    target_map = {target.name: target for target in targets}
    for bundle in bundles:
        for target_name, _destination in bundle.destinations:
            target = target_map.get(target_name)
            if target is None:
                _manifest_error(
                    f"bundle {bundle.name} destination names unknown target {target_name}"
                )
            if not target.supports(bundle.capability):
                _manifest_error(
                    f"bundle {bundle.name} capability {bundle.capability} has no "
                    f"harness support on target {target_name}"
                )


@dataclass(frozen=True)
class PlannedFile:
    """One source byte sequence and its relative generated destination."""

    destination: str
    content: bytes
    mode: int


@dataclass(frozen=True)
class RenderResult:
    """Files written or planned by one target operation."""

    target: str
    files: tuple[str, ...]


@dataclass(frozen=True)
class TemporaryRender:
    """One renderer-owned temporary destination available during its context."""

    destination_root: Path
    result: RenderResult


@dataclass(frozen=True)
class CheckResult:
    """Target drift, split into missing, changed, and stale output."""

    target: str
    missing: tuple[str, ...]
    changed: tuple[str, ...]
    stale: tuple[str, ...]

    @property
    def ok(self) -> bool:
        """Return true only when target has no generated-output drift."""
        return not (self.missing or self.changed or self.stale)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        _manifest_error(f"{label} must be an object")
    return cast("Mapping[str, object]", value)


def _exact_keys(value: Mapping[str, object], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        detail = []
        if missing:
            detail.append(f"missing={','.join(missing)}")
        if unknown:
            detail.append(f"unknown={','.join(unknown)}")
        _manifest_error(f"{label} keys invalid ({' '.join(detail)})")


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or any(char in value for char in PATH_SEPARATORS):
        _manifest_error(f"{label} must be a non-empty single-line string")
    return value


def _token(value: object, label: str, *, capability: bool = False) -> str:
    text = _text(value, label)
    pattern = CAPABILITY_PATTERN if capability else TOKEN_PATTERN
    if pattern.fullmatch(text) is None:
        _manifest_error(f"{label} has invalid name: {text}")
    return text


def _relative_path(value: object, label: str, *, allow_dot: bool = False) -> str:
    text = _text(value, label)
    if text == "." and allow_dot:
        return text
    if text.startswith("/") or ":" in text:
        _manifest_error(f"{label} must be relative: {text}")
    parts = PurePosixPath(text).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        _manifest_error(f"{label} must be a normalized relative path: {text}")
    if "/".join(parts) != text:
        _manifest_error(f"{label} must be a normalized relative path: {text}")
    return text


def _string_list(value: object, label: str, *, paths: bool) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        _manifest_error(f"{label} must be a non-empty list")
    result = tuple(
        _relative_path(item, f"{label}[{index}]") if paths else _text(item, f"{label}[{index}]")
        for index, item in enumerate(value)
    )
    if len(set(result)) != len(result):
        _manifest_error(f"{label} contains duplicates")
    return result


def _parse_targets(raw_targets: object) -> tuple[Target, ...]:
    target_tables = _mapping(raw_targets, "targets")
    if not target_tables:
        _manifest_error("targets must declare at least one target")
    targets: list[Target] = []
    for name, raw_target in target_tables.items():
        target_name = _token(name, "target name")
        target = _mapping(raw_target, f"targets.{target_name}")
        _exact_keys(target, {"capabilities"}, f"targets.{target_name}")
        capabilities = _string_list(
            target["capabilities"], f"targets.{target_name}.capabilities", paths=False
        )
        for capability in capabilities:
            if CAPABILITY_PATTERN.fullmatch(capability) is None:
                _manifest_error(
                    f"targets.{target_name}.capabilities contains invalid capability: {capability}"
                )
        target_value = Target(target_name)
        declared = frozenset(capabilities)
        if declared != target_value.capabilities:
            missing = sorted(target_value.capabilities - declared)
            unsupported = sorted(declared - target_value.capabilities)
            detail = []
            if missing:
                detail.append(f"missing={','.join(missing)}")
            if unsupported:
                detail.append(f"unsupported={','.join(unsupported)}")
            _manifest_error(
                f"target {target_name} capabilities differ from harness support "
                f"({' '.join(detail)})"
            )
        targets.append(target_value)
    if len({target.name for target in targets}) != len(targets):
        _manifest_error("targets contains duplicates")
    return tuple(sorted(targets, key=lambda item: item.name))


def _parse_bundle(index: int, raw_bundle: object, targets: Mapping[str, Target]) -> Bundle:
    bundle = _mapping(raw_bundle, f"bundles[{index}]")
    _exact_keys(
        bundle,
        {"name", "capability", "kind", "source", "destinations"},
        f"bundles[{index}]",
    )
    name = _token(bundle["name"], f"bundles[{index}].name")
    capability = _token(bundle["capability"], f"bundles[{index}].capability", capability=True)
    kind = _text(bundle["kind"], f"bundles[{index}].kind")
    if kind not in {"file", "directory"}:
        _manifest_error(f"bundles[{index}].kind must be file or directory")
    source = _mapping(bundle["source"], f"bundles[{index}].source")
    _exact_keys(source, {"root", "files"}, f"bundles[{index}].source")
    source_root = _relative_path(source["root"], f"bundles[{index}].source.root", allow_dot=True)
    files = _string_list(source["files"], f"bundles[{index}].source.files", paths=True)
    if kind == "file" and len(files) != 1:
        _manifest_error(f"bundles[{index}] file kind requires one source file")
    destinations = _mapping(bundle["destinations"], f"bundles[{index}].destinations")
    if not destinations:
        _manifest_error(
            f"bundles[{index}].destinations must name supported targets; omit unsupported targets"
        )
    parsed_destinations: list[tuple[str, str]] = []
    for target_name, raw_destination in destinations.items():
        if target_name not in targets:
            _manifest_error(f"bundles.{name}.destinations names unknown target {target_name}")
        if not targets[target_name].supports(capability):
            _manifest_error(
                f"bundles.{name} maps capability {capability} to target {target_name}, "
                "which does not declare that capability"
            )
        parsed_destinations.append(
            (
                target_name,
                _relative_path(
                    raw_destination,
                    f"bundles.{name}.destinations.{target_name}",
                    allow_dot=True,
                ),
            )
        )
    return Bundle(
        name=name,
        capability=capability,
        kind=kind,
        source_root=source_root,
        files=files,
        destinations=tuple(sorted(parsed_destinations)),
    )


def parse(document: object) -> Manifest:
    """Parse the strict manifest shape into immutable value objects."""
    root = _mapping(document, "manifest")
    _exact_keys(root, {"schema_version", "targets", "bundles"}, "manifest")
    if root["schema_version"] != SCHEMA_VERSION:
        _manifest_error(f"schema_version must be {SCHEMA_VERSION}")
    targets = _parse_targets(root["targets"])
    target_map = {target.name: target for target in targets}
    raw_bundles = root["bundles"]
    if not isinstance(raw_bundles, list) or not raw_bundles:
        _manifest_error("bundles must be a non-empty list")
    bundles = tuple(
        _parse_bundle(index, raw_bundle, target_map) for index, raw_bundle in enumerate(raw_bundles)
    )
    if len({bundle.name for bundle in bundles}) != len(bundles):
        _manifest_error("bundles contains duplicate names")
    return Manifest(targets, bundles)


def load(path: Path) -> Manifest:
    """Read and parse one UTF-8 JSON manifest."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        message = f"cannot read manifest {path}: {error}"
        raise ManifestError(message) from error
    return parse(document)


def _inside(base: Path, candidate: Path) -> bool:
    try:
        candidate.resolve(strict=False).relative_to(base.resolve(strict=False))
    except (OSError, ValueError):
        return False
    return True


def _source_path(source_root: Path, relative: str, label: str) -> Path:
    if source_root.is_symlink() or not source_root.is_dir():
        _surface_error(f"source_root_unusable={source_root}")
    candidate = source_root.joinpath(*PurePosixPath(relative).parts)
    if candidate.is_symlink() or not candidate.is_file() or not _inside(source_root, candidate):
        _surface_error(f"source_unusable={label} path={candidate}")
    return candidate


def _read_plan(
    manifest: Manifest,
    source_root: Path,
    target: str,
    bundle_names: Iterable[str] | None = None,
) -> tuple[PlannedFile, ...]:
    manifest.target(target)
    selected = (
        manifest.bundles_for(target)
        if bundle_names is None
        else tuple(manifest.bundle(name) for name in bundle_names)
    )
    plans: list[PlannedFile] = []
    seen_destinations: set[str] = set()
    for bundle in sorted(selected, key=lambda item: item.name):
        destination_root = bundle.destination_for(target)
        if destination_root is None:
            _promotion_refusal(
                "unsupported_destination",
                f"target={target} bundle={bundle.name} capability={bundle.capability}",
            )
        source_directory = source_root.joinpath(*PurePosixPath(bundle.source_root).parts)
        for relative in bundle.files:
            source = _source_path(source_directory, relative, f"bundle={bundle.name}")
            destination = (
                destination_root
                if bundle.kind == "file"
                else str(PurePosixPath(destination_root) / PurePosixPath(relative))
            )
            if destination in seen_destinations:
                _surface_error(f"destination_conflict={destination}")
            seen_destinations.add(destination)
            plans.append(
                PlannedFile(
                    destination=destination,
                    content=source.read_bytes(),
                    mode=stat.S_IMODE(source.stat().st_mode),
                )
            )
    return tuple(sorted(plans, key=lambda item: item.destination))


def _destination_path(root: Path, relative: str, *, reject_final_symlink: bool = True) -> Path:
    if root.is_symlink() or (root.exists() and not root.is_dir()):
        _surface_error(f"destination_root_unusable={root}")
    candidate = root.joinpath(*PurePosixPath(relative).parts)
    if not _inside(root, candidate.parent):
        _surface_error(f"destination_escape={relative}")
    current = root
    parts = PurePosixPath(relative).parts
    for index, part in enumerate(parts):
        current = current / part
        if current.is_symlink() and (reject_final_symlink or index < len(parts) - 1):
            _surface_error(f"destination_symlink={current}")
    return candidate


def _ensure_directory(path: Path) -> None:
    if path.exists():
        if path.is_symlink() or not path.is_dir():
            _surface_error(f"destination_directory_unusable={path}")
        return
    path.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        _surface_error(f"destination_directory_unusable={path}")


def _write_plans(
    target: str,
    plans: Sequence[PlannedFile],
    destination_root: Path,
    *,
    dispatched_temporary: bool,
    promotion_preflight: bool,
) -> RenderResult:
    """Contain every filesystem write at one boundary."""
    dispatch_id = os.environ.get(DISPATCH_ID_ENV, "").strip()
    if dispatch_id and not dispatched_temporary:
        _promotion_refusal("dispatch_identity_present", f"{DISPATCH_ID_ENV}={dispatch_id}")
    if promotion_preflight:
        _promotion_destination_check(destination_root, plans)
    _ensure_directory(destination_root)
    for plan in plans:
        destination = _destination_path(destination_root, plan.destination)
        _ensure_directory(destination.parent)
        destination.write_bytes(plan.content)
        destination.chmod(plan.mode)
    return RenderResult(target, tuple(plan.destination for plan in plans))


def render(
    manifest: Manifest,
    source_root: Path,
    target: str,
    destination_root: Path,
    *,
    bundle_names: Iterable[str] | None = None,
) -> RenderResult:
    """Render into a caller-selected layout from a non-dispatched process."""
    plans = _read_plan(manifest, source_root, target, bundle_names)
    return _write_plans(
        target,
        plans,
        destination_root,
        dispatched_temporary=False,
        promotion_preflight=False,
    )


@contextmanager
def render_temporary(
    manifest: Manifest,
    source_root: Path,
    target: str,
    *,
    bundle_names: Iterable[str] | None = None,
) -> Iterator[TemporaryRender]:
    """Render into a renderer-owned temporary layout, including during dispatch."""
    plans = _read_plan(manifest, source_root, target, bundle_names)
    with TemporaryDirectory(prefix="cti-harness-surface-") as temporary:
        destination_root = Path(temporary)
        result = _write_plans(
            target,
            plans,
            destination_root,
            dispatched_temporary=True,
            promotion_preflight=False,
        )
        yield TemporaryRender(destination_root, result)


def _walk_files(root: Path) -> tuple[str, ...]:
    if not root.exists():
        return ()
    if root.is_symlink() or not root.is_dir():
        return ("",)
    found: list[str] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink() or path.is_file():
            found.append(relative)
    return tuple(found)


def _compare_expected(
    expected: Mapping[str, PlannedFile], destination_root: Path
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Compare expected bytes and modes, treating output symlinks as drift."""
    missing: list[str] = []
    changed: list[str] = []
    for relative, plan in expected.items():
        try:
            destination = _destination_path(destination_root, relative, reject_final_symlink=False)
        except HarnessSurfaceError:
            changed.append(relative)
            continue
        if not destination.exists():
            missing.append(relative)
            continue
        if destination.is_symlink() or not destination.is_file():
            changed.append(relative)
            continue
        if (
            destination.read_bytes() != plan.content
            or stat.S_IMODE(destination.stat().st_mode) != plan.mode
        ):
            changed.append(relative)
    return tuple(sorted(missing)), tuple(sorted(changed))


def _stale_output(
    manifest: Manifest,
    target: str,
    selected_names: tuple[str, ...] | None,
    expected: Mapping[str, PlannedFile],
    destination_root: Path,
) -> tuple[str, ...]:
    """Find files left inside directory destinations after a source changed."""
    selected = None if selected_names is None else set(selected_names)
    stale: set[str] = set()
    for bundle in manifest.bundles_for(target):
        if selected is not None and bundle.name not in selected:
            continue
        if bundle.kind != "directory":
            continue
        destination_root_path = bundle.destination_for(target)
        if destination_root_path is None:
            continue
        try:
            scope = _destination_path(
                destination_root, destination_root_path, reject_final_symlink=False
            )
        except HarnessSurfaceError:
            continue
        for relative in _walk_files(scope):
            if relative:
                generated = str(PurePosixPath(destination_root_path) / PurePosixPath(relative))
                if generated not in expected:
                    stale.add(generated)
    return tuple(sorted(stale))


def check(
    manifest: Manifest,
    source_root: Path,
    target: str,
    destination_root: Path,
    *,
    bundle_names: Iterable[str] | None = None,
) -> CheckResult:
    """Compare generated output with source bytes without modifying either side."""
    selected_names = None if bundle_names is None else tuple(bundle_names)
    plans = _read_plan(manifest, source_root, target, selected_names)
    expected = {plan.destination: plan for plan in plans}
    missing, changed = _compare_expected(expected, destination_root)
    stale = _stale_output(manifest, target, selected_names, expected, destination_root)
    return CheckResult(target, missing, changed, stale)


def _has_effective_access(path: Path, mode: int) -> bool:
    """Ask the filesystem about this process's current effective access."""
    try:
        return os.access(path, mode, effective_ids=True)
    except (NotImplementedError, TypeError):
        return os.access(path, mode)


def _promotion_destination_check(root: Path, plans: Sequence[PlannedFile]) -> None:
    directory_access = os.W_OK | os.X_OK
    if (
        not root.exists()
        or root.is_symlink()
        or not root.is_dir()
        or not _has_effective_access(root, directory_access)
    ):
        _promotion_refusal("destination_unwritable", f"root={root}")
    for plan in plans:
        try:
            destination = _destination_path(root, plan.destination)
        except HarnessSurfaceError as error:
            _promotion_refusal("destination_unwritable", str(error))
        parent = destination.parent
        while not parent.exists() and parent != root:
            parent = parent.parent
        if parent.is_symlink() or not parent.is_dir():
            _promotion_refusal("destination_unwritable", f"path={destination}")
        if not _has_effective_access(parent, directory_access):
            _promotion_refusal("destination_unwritable", f"path={parent}")
        if destination.exists():
            if destination.is_symlink() or not destination.is_file():
                _promotion_refusal("destination_unwritable", f"path={destination}")
            if not _has_effective_access(destination, os.W_OK):
                _promotion_refusal("destination_unwritable", f"path={destination}")


def promote(
    manifest: Manifest,
    source_root: Path,
    target: str,
    destination_root: Path,
    bundle_names: Sequence[str],
) -> RenderResult:
    """Promote explicit bundles only from a non-dispatched, writable process."""
    if not bundle_names:
        _promotion_refusal("bundle_selection_empty", "name at least one bundle")
    if len(set(bundle_names)) != len(bundle_names):
        _promotion_refusal("bundle_selection_duplicate", "bundle names must be unique")
    for name in bundle_names:
        bundle = manifest.bundle(name)
        if bundle.destination_for(target) is None:
            _promotion_refusal(
                "unsupported_destination",
                f"target={target} bundle={name} capability={bundle.capability}",
            )
    plans = _read_plan(manifest, source_root, target, bundle_names)
    return _write_plans(
        target,
        plans,
        destination_root,
        dispatched_temporary=False,
        promotion_preflight=True,
    )


def _print_check(result: CheckResult) -> None:
    if result.ok:
        print(f"check=pass target={result.target}")  # noqa: T201 — CLI contract
        return
    print(f"check=fail target={result.target}", file=sys.stderr)  # noqa: T201 — CLI contract
    for label, paths in (
        ("missing", result.missing),
        ("changed", result.changed),
        ("stale", result.stale),
    ):
        for path in paths:
            print(f"{label}={path}", file=sys.stderr)  # noqa: T201 — CLI contract


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("render", "check", "promote"))
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--bundle", action="append", dest="bundles", default=[])
    return parser


def _run(args: argparse.Namespace) -> int:
    """Run one parsed operation, allowing ``main`` to report typed failures."""
    manifest = load(args.manifest)
    if args.action == "render":
        result = render(
            manifest,
            args.source_root,
            args.target,
            args.destination,
            bundle_names=args.bundles or None,
        )
        print(  # noqa: T201 — CLI contract
            f"render=ok target={result.target} files={len(result.files)}"
        )
        return 0
    if args.action == "check":
        result = check(
            manifest,
            args.source_root,
            args.target,
            args.destination,
            bundle_names=args.bundles or None,
        )
        _print_check(result)
        return 0 if result.ok else 1
    result = promote(
        manifest,
        args.source_root,
        args.target,
        args.destination,
        args.bundles,
    )
    print(  # noqa: T201 — CLI contract
        f"promote=ok target={result.target} files={len(result.files)}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run one contained renderer/checker operation."""
    args = _parser().parse_args(argv)
    try:
        result = _run(args)
    except PromotionRefusalError as error:
        print(  # noqa: T201 — CLI contract
            f"refusal={error.kind} detail={error.detail}", file=sys.stderr
        )
        return 1
    except HarnessSurfaceError as error:
        print(  # noqa: T201 — CLI contract
            f"harness_surface_invalid={error}", file=sys.stderr
        )
        return 2
    else:
        return result


if __name__ == "__main__":
    raise SystemExit(main())
