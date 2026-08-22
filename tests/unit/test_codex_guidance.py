"""The Codex instruction-delivery proof: source selection, capture, and refusal."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import pytest
from conftest import REPO, codex_guidance_proof_document, load_tool

guidance = load_tool("codex_guidance")
dispatch = load_tool("dispatch")
SEAM = REPO / "tools" / "dispatch.sh"
READY_BODY = REPO / "tests" / "fixtures" / "routing-eligible.md"


def git_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(
        ["git", "init", "-q", "-b", "main"],  # noqa: S607 — fixed git setup argv
        cwd=root,
        check=True,
        capture_output=True,
    )
    for key, value in (("user.email", "t@example.invalid"), ("user.name", "t")):
        subprocess.run(  # noqa: S603 — fixed temporary repository configuration
            ["git", "config", key, value],  # noqa: S607 — fixed git setup command and data
            cwd=root,
            check=True,
            capture_output=True,
        )
    return root


def wrapper(body: str) -> list[dict[str, object]]:
    return [
        {
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": (
                        "# AGENTS.md instructions for /fixture\n\n<INSTRUCTIONS>\n"
                        f"{body}</INSTRUCTIONS>"
                    ),
                }
            ],
        }
    ]


def truncate_sources(raw_sources: tuple[bytes, ...], limit: int) -> str:
    """Model Codex's byte budget in the fake harness, excluding inter-file separators."""
    selected = tuple(
        raw
        for raw in raw_sources
        if guidance.normalize(raw.decode("utf-8", errors="ignore")).strip()
    )
    remaining = limit
    delivered: list[str] = []
    for index, raw in enumerate(selected):
        if remaining <= 0:
            break
        part = raw[:remaining]
        delivered.append(guidance.normalize(part.decode("utf-8", errors="ignore")))
        remaining -= len(part)
        if remaining > 0 and index + 1 < len(selected):
            delivered.append("\n\n")
    return "".join(delivered)


class FakeCodex:
    """Return deterministic prompt captures while retaining the real subprocess seam."""

    def __init__(  # noqa: D107 — fixture constructor arguments are documented by the class
        self,
        root: Path,
        raw_sources: tuple[bytes, ...],
        *,
        global_body: str = "",
        mode: str = "match",
        fixed_project: str | None = None,
    ) -> None:
        self.root = root
        self.raw_sources = raw_sources
        self.global_body = global_body
        self.mode = mode
        self.fixed_project = fixed_project
        self.calls: list[tuple[tuple[str, ...], Path, dict[str, str]]] = []

    def __call__(  # noqa: C901, D102, PLR0911, PLR0912, PLR0913 — finite fake CLI mode matrix
        self,
        argv: list[str],
        *,
        cwd: Path,
        env: dict[str, str],
        capture_output: bool,
        check: bool,
        timeout: float,
    ) -> subprocess.CompletedProcess[bytes]:
        del capture_output, check, timeout
        command = tuple(argv)
        self.calls.append((command, cwd, dict(env)))
        if command[:3] == ("git", "rev-parse", "--show-toplevel"):
            return subprocess.CompletedProcess(argv, 0, f"{self.root}\n".encode(), b"")
        if command == ("codex", "--version"):
            return subprocess.CompletedProcess(argv, 0, b"codex-cli 0.147.0\n", b"")
        if len(command) < 3 or command[1:3] != ("debug", "prompt-input"):
            return subprocess.CompletedProcess(argv, 97, b"", b"unexpected")
        if self.mode == "timeout":
            raise subprocess.TimeoutExpired(argv, 1)
        if self.mode == "nonzero":
            return subprocess.CompletedProcess(argv, 9, b"", b"secret child error")
        if self.mode == "invalid_json":
            return subprocess.CompletedProcess(argv, 0, b"not-json", b"")
        max_bytes = next(
            int(value.split("=", 1)[1])
            for value in command
            if value.startswith("project_doc_max_bytes=")
        )
        if max_bytes == 0:
            if self.mode == "global_unreadable":
                return subprocess.CompletedProcess(argv, 0, b"{}", b"")
            if not self.global_body:
                return subprocess.CompletedProcess(argv, 0, b"[]", b"")
            body = self.global_body
        elif self.fixed_project is not None:
            separator = guidance.CODEX_PROJECT_SEPARATOR if self.global_body else ""
            body = self.global_body + separator + self.fixed_project + "\n"
        else:
            separator = guidance.CODEX_PROJECT_SEPARATOR if self.global_body else ""
            body = (
                self.global_body + separator + truncate_sources(self.raw_sources, max_bytes) + "\n"
            )
        if self.mode == "reversed" and max_bytes > 0:
            separator = guidance.CODEX_PROJECT_SEPARATOR if self.global_body else ""
            body = (
                self.global_body
                + separator
                + "\n\n".join(reversed(tuple(raw.decode("utf-8") for raw in self.raw_sources)))
            )
        if self.mode == "missing_wrapper":
            payload: object = []
        elif self.mode == "duplicate_wrapper":
            payload = wrapper(body) + wrapper(body)
        else:
            payload = wrapper(body)
        return subprocess.CompletedProcess(
            argv,
            0,
            json.dumps(payload).encode("utf-8"),
            b"",
        )


def install_fake(  # noqa: PLR0913 — the subprocess fixture exposes each capture mode
    monkeypatch: pytest.MonkeyPatch,
    root: Path,
    raw_sources: tuple[bytes, ...],
    *,
    global_body: str = "",
    mode: str = "match",
    fixed_project: str | None = None,
) -> FakeCodex:
    fake = FakeCodex(
        root,
        raw_sources,
        global_body=global_body,
        mode=mode,
        fixed_project=fixed_project,
    )
    monkeypatch.setattr(guidance.subprocess, "run", fake)
    return fake


def context(root: Path, max_bytes: int = 100) -> guidance.LaunchContext:
    return guidance.LaunchContext(
        executable="codex",
        cwd=root,
        environment={"PATH": os.environ["PATH"], "CTI_SENTINEL": "not-output"},
        loader_config=guidance.loader_overrides(max_bytes),
    )


def write_sources(root: Path, raw_sources: tuple[bytes, ...], *, nested: bool = False) -> Path:
    (root / "AGENTS.md").write_bytes(raw_sources[0])
    if nested:
        launch = root / "nested" / "leaf"
        launch.mkdir(parents=True)
        for index, raw in enumerate(raw_sources[1:], start=1):
            (root / "nested" / ("AGENTS.md" if index == 1 else "AGENTS.override.md")).write_bytes(
                raw
            )
        return launch
    return root


def open_queue(tmp_path: Path) -> Path:
    queue_dir = tmp_path / "queue"
    queue_dir.mkdir()
    (queue_dir / "policy.json").write_text(
        json.dumps(
            {
                "version": 1,
                "freeze": {
                    "state": "open",
                    "since": "2026-08-06T00:00:00Z",
                    "ruling": "a test",
                },
                "wip_limit": {
                    "value": 9,
                    "since": "2026-08-06T00:00:00Z",
                    "ruling": "a test",
                },
                "packages": [],
            }
        ),
        encoding="utf-8",
    )
    return queue_dir


def read_manifest(record: dict[str, object]) -> guidance.GuidanceRecord:
    """Read through the lane registry and the production record parser."""
    lane_name = record.get("lane")
    lane = dispatch.LANES.get(lane_name) if isinstance(lane_name, str) else None
    return guidance.manifest_from_record(record, None if lane is None else lane.runner_family)


def test_match_records_sources_and_hashes_without_prompt_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = git_root(tmp_path)
    launch = write_sources(root, (b"root\n", b"leaf\n"), nested=True)
    expected = "root\n\n\nleaf\n"
    fake = install_fake(
        monkeypatch,
        root,
        (b"root\n", b"leaf\n"),
        global_body="global\n",
    )
    result = guidance.verify_delivery(context(launch))

    assert isinstance(result, guidance.GuidanceProof)
    assert result.sources[0].path == "AGENTS.md"
    assert result.sources[1].path == "nested/AGENTS.md"
    assert result.expected_project_bytes == len(expected.encode())
    assert result.delivered_project_sha256 == result.expected_project_sha256
    assert result.global_expected_sha256 == result.global_delivered_sha256
    rendered = json.dumps(result.document())
    assert expected not in rendered
    assert fake.calls[1][1] == launch
    assert fake.calls[1][2]["CTI_SENTINEL"] == "not-output"

    manifest = result.manifest().document()
    assert manifest["schema"] == guidance.GUIDANCE_MANIFEST_SCHEMA
    assert manifest["state"] == guidance.GUIDANCE_STATE_VERIFIED
    assert manifest["harness"] == "codex"
    assert manifest["source_provenance"] == "expected_chain_only"
    assert manifest["loader_outcome"] == "matched"
    assert manifest["delivery"] == result.document()
    assert expected not in json.dumps(manifest)
    assert (
        read_manifest(
            {"lane": "codex", "worktree": str(launch), "guidance_manifest": manifest}
        ).document()
        == manifest
    )


def test_guidance_proof_cannot_be_constructed_with_unchecked_values() -> None:
    with pytest.raises(TypeError):
        guidance.GuidanceProof(
            codex_version="arbitrary prompt text",
            launch_directory="arbitrary prompt text",
            project_doc_max_bytes=-1,
            sources=(),
            raw_project_bytes=-1,
            expected_project_bytes=-1,
            expected_project_sha256="arbitrary prompt text",
            delivered_project_bytes=-1,
            delivered_project_sha256="arbitrary prompt text",
            global_expected_bytes=-1,
            global_expected_sha256="arbitrary prompt text",
            global_delivered_bytes=-1,
            global_delivered_sha256="arbitrary prompt text",
            combined_delivered_sha256="arbitrary prompt text",
        )


@pytest.mark.parametrize("field", ["codex_version", "launch_directory"])
def test_legacy_proof_prompt_text_in_launch_metadata_is_unclassified_without_leaking(
    tmp_path: Path,
    field: str,
) -> None:
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    proof = codex_guidance_proof_document(guidance, worktree)
    sentinel = (
        "codex-cli 1.2.3-AGENTS.md.instructions.guidance-secret"
        if field == "codex_version"
        else str(worktree / "AGENTS.md" / "instructions" / "guidance-secret")
    )
    proof[field] = sentinel
    parsed = read_manifest(
        {
            "lane": "codex",
            "worktree": str(worktree),
            "instruction_delivery": proof,
        }
    )

    assert parsed.document()["state"] == guidance.GUIDANCE_STATE_UNCLASSIFIED
    assert sentinel not in json.dumps(parsed.document())


def test_overlong_numeric_codex_version_is_unclassified_not_an_exception(
    tmp_path: Path,
) -> None:
    worktree = tmp_path / "worktree"
    proof = codex_guidance_proof_document(guidance, worktree)
    proof["codex_version"] = f"codex-cli {'9' * 10_000}.0.0"

    parsed = read_manifest(
        {
            "lane": "codex",
            "worktree": str(worktree),
            "instruction_delivery": proof,
        }
    )

    assert parsed.document()["state"] == guidance.GUIDANCE_STATE_UNCLASSIFIED


def test_explicit_unknown_manifest_is_unclassified_because_presence_is_evidence() -> None:
    explicit_unknown = {
        "schema": guidance.GUIDANCE_MANIFEST_SCHEMA,
        "state": guidance.GUIDANCE_STATE_UNKNOWN,
        "harness": None,
        "source_provenance": "not_available",
        "loader_outcome": "not_available",
        "reason": "historical_manifest_absent",
        "sources": None,
        "launch_context": {},
    }

    parsed = read_manifest({"lane": "codex", "guidance_manifest": explicit_unknown})

    assert isinstance(parsed, guidance.UnclassifiedGuidanceRecord)
    assert parsed.document()["state"] == guidance.GUIDANCE_STATE_UNCLASSIFIED


def test_a_legacy_proof_constructs_a_verified_manifest_variant(tmp_path: Path) -> None:
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    manifest = read_manifest(
        {
            "lane": "codex",
            "worktree": str(worktree),
            "instruction_delivery": codex_guidance_proof_document(guidance, worktree),
        }
    )

    assert isinstance(manifest, guidance.VerifiedGuidanceManifest)
    assert manifest.document()["state"] == guidance.GUIDANCE_STATE_VERIFIED


def test_a_legacy_launch_directory_is_not_resolved_against_an_untrusted_worktree(
    tmp_path: Path,
) -> None:
    worktree = tmp_path / "gone" / "worktree"
    proof = codex_guidance_proof_document(guidance, worktree)
    proof["launch_directory"] = str(tmp_path / "gone" / ".." / "gone" / "worktree")

    manifest = read_manifest(
        {
            "lane": "codex",
            "worktree": str(worktree),
            "instruction_delivery": proof,
        }
    )

    assert isinstance(manifest, guidance.UnclassifiedGuidanceRecord)


def test_an_unbounded_harness_is_explicitly_unattributable_not_empty(tmp_path: Path) -> None:
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    launch_directory = guidance.ResolvedLaunchDirectory.in_repository(worktree, worktree)
    assert launch_directory is not None
    manifest = guidance.UnattributableGuidanceManifest(launch_directory).document()

    assert manifest["state"] == guidance.GUIDANCE_STATE_UNATTRIBUTABLE
    assert manifest["loader_outcome"] == "not_observable"
    assert manifest["source_provenance"] == "not_exposed"
    assert manifest["sources"] is None
    assert manifest["reason"] == "no bounded capture"
    assert (
        read_manifest(
            {
                "lane": "claude-native",
                "worktree": str(worktree),
                "guidance_manifest": manifest,
            }
        ).document()
        == manifest
    )


@pytest.mark.parametrize(
    ("lane", "variant"),
    [("codex", "missing"), ("claude-native", "unattributable"), ("codex", "empty")],
)
def test_each_recorded_non_success_variant_round_trips_as_its_own_type(
    tmp_path: Path, lane: str, variant: str
) -> None:
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    launch_directory = guidance.ResolvedLaunchDirectory.in_repository(worktree, worktree)
    assert launch_directory is not None
    variants = {
        "missing": guidance.MissingGuidanceManifest(launch_directory),
        "unattributable": guidance.UnattributableGuidanceManifest(launch_directory),
        "empty": guidance.EmptyGuidanceManifest(launch_directory),
    }
    manifest = variants[variant]

    parsed = read_manifest(
        {
            "lane": lane,
            "worktree": str(worktree),
            "guidance_manifest": manifest.document(),
        }
    )

    assert type(parsed) is type(manifest)
    assert parsed.document() == manifest.document()


def test_incoherent_non_success_fields_are_unclassified() -> None:
    missing = {
        "schema": guidance.GUIDANCE_MANIFEST_SCHEMA,
        "state": guidance.GUIDANCE_STATE_MISSING,
        "harness": "codex",
        "source_provenance": "not_available",
        "loader_outcome": "not_run",
        "reason": "missing_preflight_manifest",
        "sources": None,
        "launch_context": {"launch_directory": "/fixture"},
    }
    relabelled = {**missing, "state": guidance.GUIDANCE_STATE_UNATTRIBUTABLE}

    empty = {
        "schema": guidance.GUIDANCE_MANIFEST_SCHEMA,
        "state": guidance.GUIDANCE_STATE_EMPTY,
        "harness": "codex",
        "source_provenance": "not_exposed",
        "loader_outcome": "not_observable",
        "reason": "unattributable_loader",
        "sources": [],
        "launch_context": {"launch_directory": "/fixture"},
    }
    wrong_lane = {**missing}

    for lane, manifest in (
        ("codex", relabelled),
        ("codex", empty),
        ("claude-native", wrong_lane),
    ):
        parsed = read_manifest(
            {"lane": lane, "worktree": "/fixture", "guidance_manifest": manifest}
        )
        assert parsed.document()["state"] == guidance.GUIDANCE_STATE_UNCLASSIFIED


@pytest.mark.parametrize(
    "record",
    [
        {"lane": "codex", "guidance_manifest": None},
        {"lane": "codex", "instruction_delivery": None},
    ],
)
def test_explicit_null_guidance_evidence_is_unclassified(record: dict[str, object]) -> None:
    assert read_manifest(record).document()["state"] == guidance.GUIDANCE_STATE_UNCLASSIFIED


def test_claude_dispatch_records_unattributable_guidance_without_faking_sources(
    tmp_path: Path,
) -> None:
    queue_dir = open_queue(tmp_path)
    args = dispatch.parse_args(
        [
            "--lane",
            "claude-native",
            "--profile",
            "opus-high",
            "--seat",
            "implementer",
            "--issue",
            "223",
            "--worktree",
            str(REPO),
            "--dispatch-dir",
            str(tmp_path / "dispatches"),
            "--breaker-dir",
            str(tmp_path / "breaker"),
            "--issue-body",
            str(READY_BODY),
            "--queue-dir",
            str(queue_dir),
            "--queue-root",
            str(tmp_path / "queue-root"),
        ]
    )
    plan, _brief, refusal = dispatch.plan_dispatch(
        args, REPO, dispatch.datetime.now(tz=dispatch.UTC)
    )

    assert refusal is None
    assert plan is not None
    manifest = plan.document()["guidance_manifest"]
    assert manifest["state"] == guidance.GUIDANCE_STATE_UNATTRIBUTABLE
    assert manifest["harness"] == "claude-code"
    assert manifest["sources"] is None


def test_exact_limit_excludes_inter_file_separators(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = git_root(tmp_path)
    launch = write_sources(root, (b"abc", b"de"), nested=True)
    install_fake(monkeypatch, root, (b"abc", b"de"))

    result = guidance.verify_delivery(context(launch, max_bytes=5))

    assert isinstance(result, guidance.GuidanceProof)
    assert result.raw_project_bytes == 5
    assert result.expected_project_bytes == 7
    assert result.delivered_project_bytes == 7


@pytest.mark.parametrize(
    ("source_size", "expected_reason"),
    [(98_303, None), (98_304, None), (98_305, "instruction_delivery_mismatch")],
)
def test_containment_boundary_is_measured_in_source_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source_size: int,
    expected_reason: str | None,
) -> None:
    root = git_root(tmp_path)
    raw = b"x" * source_size
    (root / "AGENTS.md").write_bytes(raw)
    install_fake(monkeypatch, root, (raw,))

    result = guidance.verify_delivery(context(root, guidance.CODEX_PROJECT_DOC_CONTAINMENT_BYTES))

    if expected_reason is None:
        assert isinstance(result, guidance.GuidanceProof)
        assert result.delivered_project_bytes == source_size
    else:
        assert isinstance(result, guidance.GuidanceFailure)
        assert result.reason == expected_reason
        assert result.evidence is not None
        assert (
            result.evidence.delivered_project_bytes == guidance.CODEX_PROJECT_DOC_CONTAINMENT_BYTES
        )


def test_multibyte_character_crossing_limit_is_a_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = git_root(tmp_path)
    launch = write_sources(root, (b"abcd\xc3\xa9",))
    install_fake(monkeypatch, root, (b"abcd\xc3\xa9",))

    result = guidance.verify_delivery(context(launch, max_bytes=5))

    assert isinstance(result, guidance.GuidanceFailure)
    assert result.reason == "instruction_delivery_mismatch"
    assert result.evidence is not None
    assert result.evidence.expected_project_bytes == 6
    assert result.evidence.delivered_project_bytes == 4


def test_reversed_root_and_nested_capture_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = git_root(tmp_path)
    launch = write_sources(root, (b"root", b"leaf"), nested=True)
    install_fake(monkeypatch, root, (b"root", b"leaf"), mode="reversed")

    result = guidance.verify_delivery(context(launch))

    assert isinstance(result, guidance.GuidanceFailure)
    assert result.reason == "instruction_delivery_mismatch"


def test_override_wins_beside_agents(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = git_root(tmp_path)
    (root / "AGENTS.md").write_text("ordinary", encoding="utf-8")
    (root / "AGENTS.override.md").write_text("override", encoding="utf-8")
    install_fake(monkeypatch, root, (b"override",))

    result = guidance.verify_delivery(context(root))

    assert isinstance(result, guidance.GuidanceProof)
    assert [source.path for source in result.sources] == ["AGENTS.override.md"]


def test_missing_intermediate_document_contributes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = git_root(tmp_path)
    launch = root / "nested" / "leaf"
    launch.mkdir(parents=True)
    (root / "AGENTS.md").write_text("root", encoding="utf-8")
    install_fake(monkeypatch, root, (b"root",))

    result = guidance.verify_delivery(context(launch))

    assert isinstance(result, guidance.GuidanceProof)
    assert [source.path for source in result.sources] == ["AGENTS.md"]


def test_whitespace_only_nested_document_is_discarded_like_codex(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = git_root(tmp_path)
    launch = write_sources(root, (b"root", b" \t\r\n"), nested=True)
    install_fake(monkeypatch, root, (b"root", b" \t\r\n"))

    result = guidance.verify_delivery(context(launch))

    assert isinstance(result, guidance.GuidanceProof)
    assert [source.path for source in result.sources] == ["AGENTS.md", "nested/AGENTS.md"]
    assert result.expected_project_bytes == len(b"root")
    assert result.delivered_project_bytes == result.expected_project_bytes


def test_missing_root_contract_refuses_before_codex_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = git_root(tmp_path)
    fake = install_fake(monkeypatch, root, ())

    result = guidance.verify_delivery(context(root))

    assert isinstance(result, guidance.GuidanceFailure)
    assert result.reason == "missing_source"
    assert len(fake.calls) == 1


def test_invalid_utf8_refuses_without_rendering_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = git_root(tmp_path)
    (root / "AGENTS.md").write_bytes(b"bad\xff")
    fake = install_fake(monkeypatch, root, (b"bad\xff",))

    result = guidance.verify_delivery(context(root))

    assert isinstance(result, guidance.GuidanceFailure)
    assert result.reason == "invalid_utf8"
    assert len(fake.calls) == 1


def test_unreadable_source_refuses_before_codex_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = git_root(tmp_path)
    (root / "AGENTS.md").write_text("source", encoding="utf-8")
    fake = install_fake(monkeypatch, root, (b"source",))
    original_read_bytes = guidance.Path.read_bytes

    def unreadable(path: guidance.Path) -> bytes:
        if path == root / "AGENTS.md":
            message = "test unreadable source"
            raise PermissionError(message)
        return original_read_bytes(path)

    monkeypatch.setattr(guidance.Path, "read_bytes", unreadable)

    result = guidance.verify_delivery(context(root))

    assert isinstance(result, guidance.GuidanceFailure)
    assert result.reason == "unreadable_source"
    assert "AGENTS.md" in result.source_paths
    assert len(fake.calls) == 1


@pytest.mark.parametrize(
    ("mode", "reason"),
    [
        ("nonzero", "loader_exit"),
        ("timeout", "loader_timeout"),
        ("invalid_json", "invalid_json"),
        ("missing_wrapper", "missing_wrapper"),
        ("duplicate_wrapper", "duplicate_wrapper"),
    ],
)
def test_loader_failures_are_typed_and_do_not_leak_child_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    reason: str,
) -> None:
    root = git_root(tmp_path)
    (root / "AGENTS.md").write_text("source", encoding="utf-8")
    fake = install_fake(monkeypatch, root, (b"source",), mode=mode)

    result = guidance.verify_delivery(context(root))

    assert isinstance(result, guidance.GuidanceFailure)
    assert result.reason == reason
    assert "secret child error" not in "\n".join((*result.lines(), result.action))
    assert fake.calls[0][0][:3] == ("git", "rev-parse", "--show-toplevel")


def test_unreadable_global_only_capture_has_its_own_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = git_root(tmp_path)
    (root / "AGENTS.md").write_text("source", encoding="utf-8")
    install_fake(monkeypatch, root, (b"source",), global_body="global", mode="global_unreadable")

    result = guidance.verify_delivery(context(root))

    assert isinstance(result, guidance.GuidanceFailure)
    assert result.reason == "unreadable_global_only_result"


def test_secret_sentinel_is_absent_from_failure_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = git_root(tmp_path)
    sentinel = "sentinel-" + ("x" * 120)
    (root / "AGENTS.md").write_text("expected", encoding="utf-8")
    install_fake(
        monkeypatch,
        root,
        (b"expected",),
        global_body=sentinel,
        fixed_project="wrong",
    )

    result = guidance.verify_delivery(context(root))

    assert isinstance(result, guidance.GuidanceFailure)
    assert sentinel not in "\n".join((*result.lines(), result.action))


def test_containment_and_retirement_constants_are_explicit() -> None:
    assert guidance.CODEX_PROJECT_DOC_CONTAINMENT_BYTES == 96 * 1024
    assert guidance.CODEX_PROJECT_CHAIN_RETIREMENT_BYTES == 24 * 1024


def test_fake_current_checkout_matrix_proves_default_truncation_and_containment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = (REPO / "AGENTS.md").read_bytes()
    assert len(raw) == 67_149
    assert len(raw) > guidance.CODEX_PROJECT_CHAIN_RETIREMENT_BYTES
    fake = install_fake(monkeypatch, REPO, (raw,))

    default = guidance.verify_delivery(context(REPO, guidance.CODEX_PROJECT_DOC_DEFAULT_BYTES))
    assert isinstance(default, guidance.GuidanceFailure)
    assert default.reason == "instruction_delivery_mismatch"
    assert default.evidence is not None
    assert default.evidence.expected_project_bytes == 67_149
    assert default.evidence.delivered_project_bytes == 32_768

    contained = guidance.verify_delivery(
        context(REPO, guidance.CODEX_PROJECT_DOC_CONTAINMENT_BYTES)
    )
    assert isinstance(contained, guidance.GuidanceProof)
    assert contained.delivered_project_bytes == 67_149
    assert contained.delivered_project_sha256 == contained.expected_project_sha256
    assert len(fake.calls) == 8


def test_real_codex_current_checkout_tripwire_proves_default_truncation_and_containment() -> None:
    """The permanent tripwire must exercise Codex's loader, not only its fake harness."""
    executable = shutil.which("codex")
    assert executable is not None, "the current-checkout tripwire requires the Codex binary"
    raw = (REPO / "AGENTS.md").read_bytes()
    assert len(raw) > guidance.CODEX_PROJECT_DOC_DEFAULT_BYTES
    assert len(raw) > guidance.CODEX_PROJECT_CHAIN_RETIREMENT_BYTES

    codex_home = tempfile.mkdtemp(prefix=".codex-home-", dir=REPO)
    environment = dict(os.environ)
    environment["CODEX_HOME"] = codex_home

    def live_context(max_bytes: int) -> guidance.LaunchContext:
        return guidance.LaunchContext(
            executable=executable,
            cwd=REPO,
            environment=environment,
            loader_config=guidance.loader_overrides(max_bytes),
        )

    try:
        default = guidance.verify_delivery(live_context(guidance.CODEX_PROJECT_DOC_DEFAULT_BYTES))
        assert isinstance(default, guidance.GuidanceFailure)
        assert default.reason == "instruction_delivery_mismatch"
        assert default.evidence is not None
        assert default.evidence.expected_project_bytes == len(raw)
        assert default.evidence.delivered_project_bytes == guidance.CODEX_PROJECT_DOC_DEFAULT_BYTES

        contained = guidance.verify_delivery(
            live_context(guidance.CODEX_PROJECT_DOC_CONTAINMENT_BYTES)
        )
        assert isinstance(contained, guidance.GuidanceProof)
        assert contained.delivered_project_bytes == len(raw)
        assert contained.delivered_project_sha256 == contained.expected_project_sha256
    finally:
        shutil.rmtree(codex_home)


def test_codex_argv_carries_only_a_scoped_project_document_override(tmp_path: Path) -> None:
    argv = dispatch.build_argv(
        dispatch.LANES["codex"],
        dispatch.PROFILES["codex-luna-max"],
        "acceptEdits",
        tmp_path,
        None,
    )
    for override in guidance.loader_overrides():
        assert any(
            argv[index : index + 2] == ("--config", override) for index in range(len(argv) - 1)
        )
    assert f"project_doc_max_bytes={guidance.CODEX_PROJECT_DOC_DEFAULT_BYTES}" not in argv


def test_public_dispatch_seam_types_preflight_failure_before_record_or_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worktree = git_root(tmp_path)
    (worktree / "AGENTS.md").write_text("secret-source", encoding="utf-8")
    subprocess.run(
        ["git", "add", "AGENTS.md"],  # noqa: S607 — fixed git setup command
        cwd=worktree,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-qm", "instructions"],  # noqa: S607 — fixed git setup command
        cwd=worktree,
        check=True,
        capture_output=True,
    )
    queue_dir = tmp_path / "queue"
    queue_dir.mkdir()
    (queue_dir / "policy.json").write_text(
        json.dumps(
            {
                "version": 1,
                "freeze": {
                    "state": "open",
                    "since": "2026-08-06T00:00:00Z",
                    "ruling": "a test",
                },
                "wip_limit": {
                    "value": 9,
                    "since": "2026-08-06T00:00:00Z",
                    "ruling": "a test",
                },
                "packages": [],
            }
        ),
        encoding="utf-8",
    )
    args = type(
        "Args",
        (),
        {
            "lane": "codex",
            "profile": "codex-luna-max",
            "seat": "implementer",
            "issue": 223,
            "worktree": str(worktree),
            "brief_file": "",
            "base_sha": "",
            "permission_mode": "acceptEdits",
            "reviewing": "",
            "dispatch_dir": str(tmp_path / "dispatches"),
            "review_root": str(tmp_path / "review"),
            "credentials": str(tmp_path / "credentials.env"),
            "breaker_dir": str(tmp_path / "breaker"),
            "issue_body": str(READY_BODY),
            "queue_dir": str(queue_dir),
            "queue_root": str(tmp_path / "queue-root"),
        },
    )()
    plan, _brief, refusal = dispatch.plan_dispatch(
        args,
        REPO,
        dispatch.datetime.now(tz=dispatch.UTC),
    )
    assert refusal is None
    assert plan is not None
    install_fake(monkeypatch, worktree, (b"secret-source",))
    verified, verification_refusal = dispatch.instruction_preflight(plan, os.environ)
    assert verification_refusal is None
    assert verified is not None
    document = verified.document()
    record = json.dumps(document)
    assert "instruction_delivery" in record
    assert "secret-source" not in record
    assert document["guidance_manifest"] == read_manifest(document).document()
    assert document["guidance_manifest"]["delivery"] == document["instruction_delivery"]

    failure = guidance.GuidanceFailure("loader_exit")
    monkeypatch.setattr(dispatch.codex_guidance, "verify_delivery", lambda _context: failure)

    preflighted, preflight_refusal = dispatch.instruction_preflight(verified, os.environ)

    assert preflighted is None
    assert preflight_refusal is not None
    assert preflight_refusal.kind == "instruction_preflight_unavailable"
    assert preflight_refusal.failure_class == "infra_unavailable"
    assert not plan.record.exists()


def test_public_dispatch_seam_types_unavailable_preflight_before_record_or_child(
    tmp_path: Path,
) -> None:
    worktree = git_root(tmp_path)
    (worktree / "AGENTS.md").write_text("source", encoding="utf-8")
    subprocess.run(
        ["git", "add", "AGENTS.md"],  # noqa: S607 — fixed git setup command
        cwd=worktree,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-qm", "instructions"],  # noqa: S607 — fixed git setup command
        cwd=worktree,
        check=True,
        capture_output=True,
    )
    codex_bin = tmp_path / "codex-bin"
    codex_bin.mkdir()
    (codex_bin / "codex").write_text(
        """#!/usr/bin/env python3
import json
import os
import sys

args = sys.argv[1:]
if args == ["--version"]:
    print("codex-cli 0.147.0")
    raise SystemExit(0)
if args[:2] == ["debug", "prompt-input"]:
    maximum = next(
        int(value.split("=", 1)[1])
        for value in args
        if value.startswith("project_doc_max_bytes=")
    )
    if maximum == 0:
        print("{}")
    else:
        payload = {
            "text": "# AGENTS.md instructions for /fixture\\n\\n<INSTRUCTIONS>\\n"
            + "\\n--- project-doc ---\\n\\nsource\\n"
            + "</INSTRUCTIONS>"
        }
        print(json.dumps([payload]))
    raise SystemExit(0)
if args and args[0] == "exec":
    open(os.environ["CTI_CHILD_MARKER"], "w").close()
    raise SystemExit(0)
raise SystemExit(91)
""",
        encoding="utf-8",
    )
    (codex_bin / "codex").chmod(0o755)
    queue_dir = open_queue(tmp_path)
    record_root = tmp_path / "dispatches"
    child_marker = tmp_path / "child-ran"
    environment = dict(os.environ)
    environment.update(
        {
            "PATH": f"{codex_bin}:{environment['PATH']}",
            "CTI_BREAKER_DIR": str(tmp_path / "breaker"),
            "CTI_READINESS_BODY": str(READY_BODY),
            "CTI_QUEUE_DIR": str(queue_dir),
            "CTI_QUEUE_ROOT": str(tmp_path / "queue-root"),
            "CTI_CHILD_MARKER": str(child_marker),
        }
    )

    result = subprocess.run(  # noqa: S603 — public dispatch seam with fixed test arguments
        [
            str(SEAM),
            "--lane",
            "codex",
            "--profile",
            "codex-luna-max",
            "--seat",
            "implementer",
            "--issue",
            "223",
            "--worktree",
            str(worktree),
            "--dispatch-dir",
            str(record_root),
        ],
        cwd=REPO,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == dispatch.EXIT_REFUSED, result.stderr
    assert "refusal=instruction_preflight_unavailable" in result.stderr
    assert "class=infra_unavailable" in result.stderr
    assert "record=" not in result.stdout
    assert not record_root.exists()
    assert not child_marker.exists()


def test_real_dispatch_command_refuses_codex_mismatch_before_forking(
    tmp_path: Path,
) -> None:
    worktree = git_root(tmp_path)
    sentinel = "secret-source"
    (worktree / "AGENTS.md").write_text(sentinel, encoding="utf-8")
    subprocess.run(
        ["git", "add", "AGENTS.md"],  # noqa: S607 — fixed git setup command
        cwd=worktree,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-qm", "instructions"],  # noqa: S607 — fixed git setup command
        cwd=worktree,
        check=True,
        capture_output=True,
    )
    codex_bin = tmp_path / "codex-bin"
    codex_bin.mkdir()
    (codex_bin / "codex").write_text(
        """#!/usr/bin/env python3
import json
import os
import sys

args = sys.argv[1:]
if args == ["--version"]:
    print("codex-cli 0.147.0")
    raise SystemExit(0)
if args[:2] == ["debug", "prompt-input"]:
    maximum = next(
        int(value.split("=", 1)[1])
        for value in args
        if value.startswith("project_doc_max_bytes=")
    )
    body = "" if maximum == 0 else "\\n--- project-doc ---\\n\\nwrong\\n"
    payload = {
        "text": "# AGENTS.md instructions for /fixture\\n\\n<INSTRUCTIONS>\\n"
        + body
        + "</INSTRUCTIONS>"
    }
    print(json.dumps([payload]))
    raise SystemExit(0)
if args and args[0] == "exec":
    open(os.environ["CTI_FAKE_CODEX_EXEC"], "w").close()
    raise SystemExit(0)
raise SystemExit(91)
""",
        encoding="utf-8",
    )
    (codex_bin / "codex").chmod(0o755)
    queue_dir = tmp_path / "queue"
    queue_dir.mkdir()
    (queue_dir / "policy.json").write_text(
        json.dumps(
            {
                "version": 1,
                "freeze": {
                    "state": "open",
                    "since": "2026-08-06T00:00:00Z",
                    "ruling": "a test",
                },
                "wip_limit": {
                    "value": 9,
                    "since": "2026-08-06T00:00:00Z",
                    "ruling": "a test",
                },
                "packages": [],
            }
        ),
        encoding="utf-8",
    )
    record_root = tmp_path / "dispatches"
    child_marker = tmp_path / "child-ran"
    environment = dict(os.environ)
    environment.update(
        {
            "PATH": f"{codex_bin}:{environment['PATH']}",
            "CTI_BREAKER_DIR": str(tmp_path / "breaker"),
            "CTI_READINESS_BODY": str(READY_BODY),
            "CTI_QUEUE_DIR": str(queue_dir),
            "CTI_QUEUE_ROOT": str(tmp_path / "queue-root"),
            "CTI_FAKE_CODEX_EXEC": str(child_marker),
        }
    )

    result = subprocess.run(  # noqa: S603 — the test invokes the repository's public seam
        [
            str(SEAM),
            "--lane",
            "codex",
            "--profile",
            "codex-luna-max",
            "--seat",
            "implementer",
            "--issue",
            "223",
            "--worktree",
            str(worktree),
            "--dispatch-dir",
            str(record_root),
        ],
        cwd=REPO,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == dispatch.EXIT_REFUSED, result.stderr
    assert "refusal=instruction_delivery_mismatch" in result.stderr
    assert "class=infra_unavailable" in result.stderr
    assert "record=" not in result.stdout
    assert not record_root.exists()
    assert not child_marker.exists()
    assert sentinel not in result.stdout + result.stderr


def test_successful_dispatch_record_and_log_do_not_leak_environment_secret(
    tmp_path: Path,
) -> None:
    worktree = git_root(tmp_path)
    (worktree / "AGENTS.md").write_text("source", encoding="utf-8")
    subprocess.run(
        ["git", "add", "AGENTS.md"],  # noqa: S607 — fixed git setup command
        cwd=worktree,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-qm", "instructions"],  # noqa: S607 — fixed git setup command
        cwd=worktree,
        check=True,
        capture_output=True,
    )
    codex_bin = tmp_path / "codex-bin"
    codex_bin.mkdir()
    (codex_bin / "codex").write_text(
        """#!/usr/bin/env python3
import json
import os
import sys

args = sys.argv[1:]
if args == ["--version"]:
    print("codex-cli 0.147.0")
    raise SystemExit(0)
if args[:2] == ["debug", "prompt-input"]:
    maximum = next(
        int(value.split("=", 1)[1])
        for value in args
        if value.startswith("project_doc_max_bytes=")
    )
    if maximum == 0:
        print("[]")
    else:
        payload = {
            "text": "# AGENTS.md instructions for /fixture\\n\\n<INSTRUCTIONS>\\n"
            + "\\n--- project-doc ---\\n\\nsource\\n"
            + "</INSTRUCTIONS>"
        }
        print(json.dumps([payload]))
    raise SystemExit(0)
if args and args[0] == "exec":
    open(os.environ["CTI_CHILD_MARKER"], "w").close()
    raise SystemExit(0)
raise SystemExit(91)
""",
        encoding="utf-8",
    )
    (codex_bin / "codex").chmod(0o755)
    queue_dir = open_queue(tmp_path)
    record_root = tmp_path / "dispatches"
    child_marker = tmp_path / "child-ran"
    sentinel = "environment-secret-sentinel-" + ("x" * 80)
    environment = dict(os.environ)
    environment.update(
        {
            "PATH": f"{codex_bin}:{environment['PATH']}",
            "CTI_BREAKER_DIR": str(tmp_path / "breaker"),
            "CTI_READINESS_BODY": str(READY_BODY),
            "CTI_QUEUE_DIR": str(queue_dir),
            "CTI_QUEUE_ROOT": str(tmp_path / "queue-root"),
            "CTI_CHILD_MARKER": str(child_marker),
            "CTI_SECRET_FIXTURE": sentinel,
        }
    )

    result = subprocess.run(  # noqa: S603 — public dispatch seam with fixed test arguments
        [
            str(SEAM),
            "--lane",
            "codex",
            "--profile",
            "codex-luna-max",
            "--seat",
            "implementer",
            "--issue",
            "223",
            "--worktree",
            str(worktree),
            "--permission-mode",
            "plan",
            "--dispatch-dir",
            str(record_root),
        ],
        cwd=REPO,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    record_line = next(line for line in result.stdout.splitlines() if line.startswith("record="))
    record = Path(record_line.partition("=")[2])
    result_file = record / "result.json"
    deadline = time.monotonic() + 10
    while not result_file.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert result_file.exists()
    assert json.loads(result_file.read_text(encoding="utf-8"))["status"] == "child_finished"

    dispatch_record = (record / "dispatch.json").read_text(encoding="utf-8")
    dispatch_log = (record / "dispatch.log").read_text(encoding="utf-8")
    assert sentinel not in dispatch_record
    assert sentinel not in dispatch_log
    assert child_marker.exists()
