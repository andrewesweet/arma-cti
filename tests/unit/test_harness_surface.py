"""Black-box tests for the contained harness-surface renderer (#504)."""

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


def files(root: Path) -> dict[str, bytes]:
    """Capture deterministic file content below one rendered target."""
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
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


def test_reference_bundles_render_and_check_identically(tmp_path: Path) -> None:
    document = manifest()
    source = copied_sources(tmp_path, document)
    claude_a = tmp_path / "claude-a"
    claude_b = tmp_path / "claude-b"

    first = surface.render(document, source, "claude-code", claude_a)
    second = surface.render(document, source, "claude-code", claude_b)

    assert first == second
    assert files(claude_a) == files(claude_b)
    assert surface.check(document, source, "claude-code", claude_a).ok
    assert surface.check(document, source, "claude-code", claude_b).ok


def test_source_perturbation_is_reported_without_editing_generated_output(tmp_path: Path) -> None:
    document = manifest()
    source = copied_sources(tmp_path, document)
    destination = tmp_path / "codex"
    surface.render(document, source, "codex", destination)
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
    destination = tmp_path / "claude"
    surface.render(document, source, "claude-code", destination)
    stale = destination / ".claude" / "hooks" / "retired.py"
    stale.write_bytes(b"retired")

    result = surface.check(document, source, "claude-code", destination)

    assert result.ok is False
    assert result.stale == (".claude/hooks/retired.py",)


def test_rendering_an_unsupported_bundle_refuses(tmp_path: Path) -> None:
    document = manifest()
    source = copied_sources(tmp_path, document)

    with pytest.raises(surface.PromotionRefusalError, match="unsupported_destination"):
        surface.render(
            document,
            source,
            "codex",
            tmp_path / "codex",
            bundle_names=("claude-hooks",),
        )


def test_promotion_refuses_dispatch_identity_before_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document = manifest()
    source = copied_sources(tmp_path, document)
    destination = tmp_path / "live"
    destination.mkdir()
    monkeypatch.setenv(surface.DISPATCH_ID_ENV, "d-test")

    with pytest.raises(surface.PromotionRefusalError, match="dispatch_identity_present"):
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


def test_cli_promotion_refuses_a_dispatched_process(tmp_path: Path) -> None:
    document = manifest()
    source = copied_sources(tmp_path, document)
    destination = tmp_path / "live"
    destination.mkdir()
    environment = os.environ.copy()
    environment[surface.DISPATCH_ID_ENV] = "d-cli-test"

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
    assert files(destination) == {}


def test_cli_render_and_check_report_machine_contract(tmp_path: Path) -> None:
    document = manifest()
    source = copied_sources(tmp_path, document)
    destination = tmp_path / "codex"
    common = [
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
    ]
    rendered = subprocess.run(  # noqa: S603 — fixed Python tool plus test paths
        common,
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    checked = subprocess.run(  # noqa: S603 — fixed Python tool plus test paths
        [*common[:2], "check", *common[3:]],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )

    assert rendered.returncode == 0
    assert rendered.stdout == "render=ok target=codex files=1\n"
    assert checked.returncode == 0
    assert checked.stdout == "check=pass target=codex\n"
