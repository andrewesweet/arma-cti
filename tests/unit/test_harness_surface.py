"""Black-box tests for the harness-surface renderer (#504)."""

from __future__ import annotations

import copy
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest
from conftest import REPO, load_tool

surface = load_tool("harness_surface")
MANIFEST_PATH = REPO / "config" / "harness-surfaces.json"
TOOL_PATH = REPO / "tools" / "harness_surface.py"


def manifest() -> surface.Manifest:
    """Load the tracked reference manifest."""
    return surface.load(MANIFEST_PATH)


def copied_sources(tmp_path: Path, document: surface.Manifest) -> Path:
    """Copy only declared source files, excluding untracked harness debris."""
    root = tmp_path / "source"
    for bundle in document.bundles:
        source_root = root.joinpath(*Path(bundle.source_root).parts)
        for relative in bundle.files:
            source = REPO / bundle.source_root / relative
            destination = source_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            shutil.copymode(source, destination)
    return root


def files(root: Path) -> dict[str, tuple[bytes, int]]:
    """Capture generated file bytes and modes; other metadata is outside the contract."""
    return {
        path.relative_to(root).as_posix(): (
            path.read_bytes(),
            path.stat().st_mode & 0o7777,
        )
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def document_with(mutator: Any) -> dict[str, object]:  # noqa: ANN401 — fixture mutation helper
    """Return a deep-copied manifest document with one intentional mutation."""
    document = copy.deepcopy(manifest().document())
    mutator(document)
    return document


def bundle_table(document: dict[str, object], name: str) -> dict[str, object]:
    """Extract one mutable JSON bundle table for a malformed-manifest test."""
    bundles = cast("list[dict[str, object]]", document["bundles"])
    return next(bundle for bundle in bundles if bundle["name"] == name)


def current_dispatch_identity() -> str:
    """Return this test process's real dispatch identity when one exists."""
    dispatch_id = os.environ.get(surface.DISPATCH_ID_ENV, "").strip()
    if not dispatch_id:
        pytest.skip("live refusal coverage requires a dispatched test process")
    return dispatch_id


def test_manifest_round_trips_canonically_and_keeps_target_asymmetry() -> None:
    document = manifest()

    assert surface.parse(document.document()).document() == document.document()
    assert document.target("claude-code").supports("hooks")
    assert not document.target("codex").supports("hooks")
    hooks = document.bundle("claude-hooks")
    assert hooks.destination_for("claude-code") == ".claude/hooks"
    assert hooks.destination_for("codex") is None
    assert "codex" not in dict(hooks.destinations)


def test_manifest_rejects_unsupported_or_empty_destinations() -> None:
    def add_unsupported(document: dict[str, object]) -> None:
        hooks = bundle_table(document, "claude-hooks")
        destinations = cast("dict[str, object]", hooks["destinations"])
        destinations["codex"] = ".claude/hooks"

    with pytest.raises(surface.ManifestError, match="does not declare that capability"):
        surface.parse(document_with(add_unsupported))

    def add_empty(document: dict[str, object]) -> None:
        project = bundle_table(document, "project-instructions")
        destinations = cast("dict[str, object]", project["destinations"])
        destinations["codex"] = ""

    with pytest.raises(surface.ManifestError, match="non-empty"):
        surface.parse(document_with(add_empty))


def test_manifest_rejects_caller_declared_codex_hooks_with_a_destination() -> None:
    def declare_codex_hooks(document: dict[str, object]) -> None:
        targets = cast("dict[str, dict[str, object]]", document["targets"])
        capabilities = cast("list[str]", targets["codex"]["capabilities"])
        capabilities.append("hooks")
        hooks = bundle_table(document, "claude-hooks")
        destinations = cast("dict[str, object]", hooks["destinations"])
        destinations["codex"] = ".codex/hooks"

    with pytest.raises(surface.ManifestError, match="harness support"):
        surface.parse(document_with(declare_codex_hooks))


def test_manifest_constructor_cannot_bypass_target_capability_support() -> None:
    codex = surface.Target("codex")
    hooks = surface.Bundle(
        name="invented-hooks",
        capability="hooks",
        kind="directory",
        source_root=".claude/hooks",
        files=("protect-gated-paths.py",),
        destinations=(("codex", ".codex/hooks"),),
    )

    with pytest.raises(surface.ManifestError, match="harness support"):
        surface.Manifest((codex,), (hooks,))


def test_target_subclass_cannot_override_adapter_support() -> None:
    class LyingTarget(surface.Target):
        """Caller-defined target that claims support no adapter implements."""

        @property
        def capabilities(self) -> frozenset[str]:
            """Invent hook support for the regression case."""
            return frozenset({"hooks", "project_instructions"})

    codex = LyingTarget("codex")
    hooks = surface.Bundle(
        name="invented-hooks",
        capability="hooks",
        kind="directory",
        source_root=".claude/hooks",
        files=("protect-gated-paths.py",),
        destinations=(("codex", ".codex/hooks"),),
    )

    with pytest.raises(surface.ManifestError, match="Target values"):
        surface.Manifest((codex,), (hooks,))


def test_reference_bundles_render_and_check_identically(tmp_path: Path) -> None:
    document = manifest()
    source = copied_sources(tmp_path, document)

    with (
        surface.render_temporary(document, source, "claude-code") as first,
        surface.render_temporary(document, source, "claude-code") as second,
    ):
        assert first.result == second.result
        assert files(first.destination_root) == files(second.destination_root)
        assert surface.check(document, source, "claude-code", first.destination_root).ok
        assert surface.check(document, source, "claude-code", second.destination_root).ok


def test_temporary_render_destination_expires_with_its_capability(tmp_path: Path) -> None:
    document = manifest()
    source = copied_sources(tmp_path, document)

    with surface.render_temporary(document, source, "codex") as rendered:
        destination = rendered.destination_root
        assert destination.is_dir()

    assert not destination.exists()


def test_source_perturbation_is_reported_without_editing_generated_output(tmp_path: Path) -> None:
    document = manifest()
    source = copied_sources(tmp_path, document)

    with surface.render_temporary(document, source, "codex") as rendered:
        destination = rendered.destination_root
        original = (destination / "AGENTS.md").read_bytes()

        agents = source / "AGENTS.md"
        agents.write_bytes(agents.read_bytes() + b"\nsource perturbation\n")
        result = surface.check(document, source, "codex", destination)

        assert result.changed == ("AGENTS.md",)
        assert result.missing == ()
        assert result.stale == ()
        assert (destination / "AGENTS.md").read_bytes() == original


def test_stale_directory_output_is_reported(tmp_path: Path) -> None:
    document = manifest()
    source = copied_sources(tmp_path, document)

    with surface.render_temporary(document, source, "claude-code") as rendered:
        destination = rendered.destination_root
        stale = destination / ".claude" / "hooks" / "retired.py"
        stale.write_bytes(b"retired")

        result = surface.check(document, source, "claude-code", destination)

        assert result.ok is False
        assert result.stale == (".claude/hooks/retired.py",)


def test_rendering_an_unsupported_bundle_refuses(tmp_path: Path) -> None:
    document = manifest()
    source = copied_sources(tmp_path, document)

    with (
        pytest.raises(surface.PromotionRefusalError, match="unsupported_destination"),
        surface.render_temporary(
            document,
            source,
            "codex",
            bundle_names=("claude-hooks",),
        ),
    ):
        pytest.fail("unsupported temporary render entered its context")


def test_render_refuses_the_current_dispatch_identity_before_writing(tmp_path: Path) -> None:
    dispatch_id = current_dispatch_identity()
    document = manifest()
    source = copied_sources(tmp_path, document)
    destination = tmp_path / "caller-selected"

    with pytest.raises(
        surface.PromotionRefusalError,
        match=rf"{surface.DISPATCH_ID_ENV}={dispatch_id}",
    ):
        surface.render(document, source, "codex", destination)

    assert not destination.exists()


def test_promotion_refuses_the_current_dispatch_identity_before_writing(tmp_path: Path) -> None:
    dispatch_id = current_dispatch_identity()
    document = manifest()
    source = copied_sources(tmp_path, document)
    destination = tmp_path / "live"
    destination.mkdir()

    with pytest.raises(
        surface.PromotionRefusalError,
        match=rf"{surface.DISPATCH_ID_ENV}={dispatch_id}",
    ):
        surface.promote(
            document,
            source,
            "codex",
            destination,
            ("project-instructions",),
        )
    assert files(destination) == {}


def test_promotion_refuses_unsupported_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document = manifest()
    source = copied_sources(tmp_path, document)
    destination = tmp_path / "live"
    destination.mkdir()
    monkeypatch.delenv(surface.DISPATCH_ID_ENV, raising=False)

    with pytest.raises(surface.PromotionRefusalError, match="unsupported_destination"):
        surface.promote(
            document,
            source,
            "codex",
            destination,
            ("claude-hooks",),
        )
    assert files(destination) == {}


def test_promotion_writes_selected_supported_bundle_in_temp_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document = manifest()
    source = copied_sources(tmp_path, document)
    destination = tmp_path / "temporary-live"
    destination.mkdir()
    monkeypatch.delenv(surface.DISPATCH_ID_ENV, raising=False)

    result = surface.promote(
        document,
        source,
        "codex",
        destination,
        ("project-instructions",),
    )

    assert result.files == ("AGENTS.md",)
    assert surface.check(document, source, "codex", destination).ok


def test_promotion_refuses_unwritable_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document = manifest()
    source = copied_sources(tmp_path, document)
    destination = tmp_path / "live"
    destination.mkdir()
    destination.chmod(0o555)
    monkeypatch.delenv(surface.DISPATCH_ID_ENV, raising=False)
    try:
        with pytest.raises(surface.PromotionRefusalError, match="destination_unwritable"):
            surface.promote(
                document,
                source,
                "codex",
                destination,
                ("project-instructions",),
            )
    finally:
        destination.chmod(0o755)
    assert files(destination) == {}


def test_promotion_refuses_destination_without_effective_directory_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document = manifest()
    source = copied_sources(tmp_path, document)
    destination = tmp_path / "live"
    destination.mkdir()
    destination.chmod(0o666)
    monkeypatch.delenv(surface.DISPATCH_ID_ENV, raising=False)
    try:
        with pytest.raises(surface.PromotionRefusalError, match="destination_unwritable"):
            surface.promote(
                document,
                source,
                "codex",
                destination,
                ("project-instructions",),
            )
    finally:
        destination.chmod(0o755)

    assert files(destination) == {}


def test_promotion_refuses_an_existing_directory_where_a_file_would_land(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document = manifest()
    source = copied_sources(tmp_path, document)
    destination = tmp_path / "live"
    output = destination / "AGENTS.md"
    output.mkdir(parents=True)
    monkeypatch.delenv(surface.DISPATCH_ID_ENV, raising=False)

    with pytest.raises(surface.PromotionRefusalError, match="destination_unwritable"):
        surface.promote(
            document,
            source,
            "codex",
            destination,
            ("project-instructions",),
        )

    assert output.is_dir()
    assert files(destination) == {}


def test_cli_promotion_refuses_the_current_dispatch_identity(tmp_path: Path) -> None:
    dispatch_id = current_dispatch_identity()
    document = manifest()
    source = copied_sources(tmp_path, document)
    destination = tmp_path / "live"
    destination.mkdir()
    environment = os.environ.copy()

    completed = subprocess.run(  # noqa: S603 — fixed Python tool plus test paths
        [
            sys.executable,
            str(TOOL_PATH),
            "promote",
            "--manifest",
            str(MANIFEST_PATH),
            "--source-root",
            str(source),
            "--target",
            "codex",
            "--destination",
            str(destination),
            "--bundle",
            "project-instructions",
        ],
        cwd=REPO,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 1
    assert "refusal=dispatch_identity_present" in completed.stderr
    assert f"{surface.DISPATCH_ID_ENV}={dispatch_id}" in completed.stderr
    assert files(destination) == {}


def test_cli_render_refuses_the_current_dispatch_identity(tmp_path: Path) -> None:
    dispatch_id = current_dispatch_identity()
    document = manifest()
    source = copied_sources(tmp_path, document)
    destination = tmp_path / "caller-selected"

    completed = subprocess.run(  # noqa: S603 — fixed Python tool plus test paths
        [
            sys.executable,
            str(TOOL_PATH),
            "render",
            "--manifest",
            str(MANIFEST_PATH),
            "--source-root",
            str(source),
            "--target",
            "codex",
            "--destination",
            str(destination),
        ],
        cwd=REPO,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 1
    assert "refusal=dispatch_identity_present" in completed.stderr
    assert f"{surface.DISPATCH_ID_ENV}={dispatch_id}" in completed.stderr
    assert not destination.exists()


def test_cli_check_reports_machine_contract_for_a_temporary_render(tmp_path: Path) -> None:
    document = manifest()
    source = copied_sources(tmp_path, document)

    with surface.render_temporary(document, source, "codex") as rendered:
        checked = subprocess.run(  # noqa: S603 — fixed Python tool plus test paths
            [
                sys.executable,
                str(TOOL_PATH),
                "check",
                "--manifest",
                str(MANIFEST_PATH),
                "--source-root",
                str(source),
                "--target",
                "codex",
                "--destination",
                str(rendered.destination_root),
            ],
            cwd=REPO,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert checked.returncode == 0
        assert checked.stdout == "check=pass target=codex\n"
