"""What `just prereqs` decides, refuses and writes (#230, refs #221, #229).

The collector fixture is this box's real `/etc/otelcol-contrib/config.yaml`,
copied in verbatim on 2026-08-05, because the whole job of the merge is reading
a document it did not write.

Three properties carry most of the weight and are asserted structurally rather
than by inspection: a pasted key never reaches stdout, stderr or argv; the
status-line chain preserves the existing command's output byte for byte, which
is checked by running the real tap over a real downstream script; and the
generated root script is generated and not run.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from conftest import REPO, load_tool

prereqs = load_tool("prereqs")

COLLECTOR_FIXTURE = REPO / "tests" / "fixtures" / "otelcol" / "config.yaml"
CAVEMAN = 'bash "/home/andre/.claude/plugins/cache/caveman/caveman/655b/caveman-statusline.sh"'


def layout_in(home: Path, *, collector: Path | None = None) -> Any:  # noqa: ANN401 - a dynamically loaded tool module has no static type
    """Build a whole Layout rooted at a temporary home, repo pointing at ours."""
    base = prereqs.Layout.under(home, REPO)
    return base._replace(
        collector_config=collector or (home / "etc" / "config.yaml"),
        ledger_dir=home / "var" / "dispatches",
    )


def args(*argv: str) -> Any:  # noqa: ANN401 - see layout_in
    """Build a namespace through the real CLI surface, never by hand."""
    return prereqs.parse_args(list(argv))


# --------------------------------------------------------------- collector merge


def test_the_merge_adds_every_ledger_leg_to_the_real_config() -> None:
    merged = prereqs.merge_collector_config(COLLECTOR_FIXTURE.read_text())
    assert merged.added == (
        "processors.filter/cti",
        "exporters.file/ledger",
        "service.pipelines.traces",
        "service.pipelines.metrics/ledger",
        "service.pipelines.logs/ledger",
        "service.pipelines.traces/ledger",
    )


def test_the_merge_leaves_every_existing_line_of_the_real_config_in_place() -> None:
    current = COLLECTOR_FIXTURE.read_text()
    merged = prereqs.merge_collector_config(current)
    # Every original line survives, in its original order: the change is additive
    # and the diagnostics skill's rotating capture is not being edited.
    remaining = iter(merged.text.splitlines())
    assert all(line in remaining for line in current.splitlines())


def test_the_merge_is_idempotent() -> None:
    once = prereqs.merge_collector_config(COLLECTOR_FIXTURE.read_text())
    twice = prereqs.merge_collector_config(once.text)
    assert twice.added == ()
    assert twice.text == once.text


def test_the_merge_completes_a_partly_installed_config() -> None:
    once = prereqs.merge_collector_config(COLLECTOR_FIXTURE.read_text())
    without_traces = "\n".join(
        line for line in once.text.splitlines() if "traces/ledger" not in line
    )
    again = prereqs.merge_collector_config(without_traces + "\n")
    assert again.added == ("service.pipelines.traces/ledger",)


def test_the_filter_is_written_in_the_inverted_drop_if_true_form() -> None:
    # filterprocessor conditions are DROP-if-true. Written the intuitive way
    # round, this exports the complement and no gate would catch it.
    merged = prereqs.merge_collector_config(COLLECTOR_FIXTURE.read_text())
    assert merged.text.count('resource.attributes["cti.dispatch_id"] == nil') == 3
    assert "!= nil" not in merged.text


def test_the_ledger_export_does_not_rotate_and_appends() -> None:
    merged = prereqs.merge_collector_config(COLLECTOR_FIXTURE.read_text())
    exporter = merged.text.split("file/ledger:")[1].split("service:")[0]
    assert "append: true" in exporter
    assert "rotation" not in exporter
    assert "resource_attribute: cti.dispatch_id" in exporter


def test_the_merge_refuses_a_config_it_cannot_read_rather_than_guessing() -> None:
    with pytest.raises(prereqs.MergeRefusedError) as refusal:
        prereqs.merge_collector_config("receivers:\n  otlp:\n")
    assert refusal.value.reason == "collector_config_unrecognised"
    assert "processors" in refusal.value.detail


# ------------------------------------------------------------------- sudo script


def generated_script(home: Path) -> tuple[Any, Path]:
    """Run the real generator against the real collector fixture."""
    layout = layout_in(home, collector=COLLECTOR_FIXTURE)
    report = prereqs.action_sudo_script(layout, args("sudo-script"))
    return report, layout.generated_dir / "install-telemetry-root.sh"


def test_the_sudo_script_is_generated_and_never_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(*_args: object, **_kwargs: object) -> None:
        message = "generation must not run a subprocess"
        raise AssertionError(message)

    monkeypatch.setattr(subprocess, "run", explode)
    report, script = generated_script(tmp_path)
    assert report.code == 0
    assert report.lines[0] == "ok=sudo_script_generated"
    assert script.exists()
    assert stat.S_IMODE(script.stat().st_mode) == 0o700


def test_the_sudo_script_refuses_a_config_that_moved_since_generation(tmp_path: Path) -> None:
    _, script = generated_script(tmp_path)
    body = script.read_text()
    expected = hashlib.sha256(COLLECTOR_FIXTURE.read_bytes()).hexdigest()
    assert f"EXPECTED_SHA256={expected}" in body
    assert "refused=collector_config_moved" in body


def test_the_sudo_script_carries_the_whole_desired_config_verbatim(tmp_path: Path) -> None:
    _, script = generated_script(tmp_path)
    desired = prereqs.merge_collector_config(
        COLLECTOR_FIXTURE.read_text(), tmp_path / "var" / "dispatches"
    ).text
    body = script.read_text()
    assert desired.rstrip() in body
    assert f"DESIRED_SHA256={hashlib.sha256(desired.encode()).hexdigest()}" in body


def test_the_sudo_script_does_the_three_root_acts_and_nothing_else(tmp_path: Path) -> None:
    body = generated_script(tmp_path)[1].read_text()
    for required in (
        "${EUID} -ne 0",  # refuses to run as anyone but root
        "sha256sum",  # the drift guard
        'cp -a -- "${CONFIG}" "${backup}"',  # backup before write
        "validate --config=",  # validate before restart
        "install -d -o",  # the export directory
        'systemctl restart "${SERVICE}"',
    ):
        assert required in body, required
    for forbidden in ("curl", "wget", "apt-get", "pip install", "useradd", "rm -rf"):
        assert forbidden not in body, forbidden


def test_the_sudo_script_restores_the_backup_when_it_cannot_validate(tmp_path: Path) -> None:
    body = generated_script(tmp_path)[1].read_text()
    # A check that could not run is not a check that passed (#41's shape), and
    # the script must not restart on a config it never validated.
    cannot = body.split("refused=cannot_validate")[0]
    assert 'cp -a -- "${backup}" "${CONFIG}"' in cannot.rsplit("if !", 1)[1]


def test_the_generator_refuses_when_there_is_no_collector_config(tmp_path: Path) -> None:
    layout = layout_in(tmp_path, collector=tmp_path / "absent.yaml")
    report = prereqs.action_sudo_script(layout, args("sudo-script"))
    assert report.code == prereqs.EXIT_COULD_NOT_LOOK
    assert report.lines[0] == "refused=no_collector_config"


# ------------------------------------------------------------------- credentials


def test_a_value_survives_a_round_trip_through_the_file_format() -> None:
    hostile = "sk-'quote'-and \"double\" and $VAR and \\backslash"
    rendered = prereqs.render_credentials({"ZAI_API_KEY": hostile})
    assert prereqs.parse_credentials(rendered)["ZAI_API_KEY"] == hostile


def test_the_rendered_file_cannot_be_re_read_as_shell_syntax() -> None:
    rendered = prereqs.render_credentials({"ZAI_API_KEY": "a$(touch ./pwned)b"})
    body = [line for line in rendered.splitlines() if line and not line.startswith("#")]
    assert body == ["ZAI_API_KEY='a$(touch ./pwned)b'"]


@pytest.mark.parametrize(
    "paste",
    ["", "one\ntwo", "with\ttab", "with\x00null"],
)
def test_a_paste_that_is_not_a_key_is_refused(paste: str) -> None:
    assert prereqs.classify_secret(paste) is not None


def test_a_plain_key_is_accepted() -> None:
    assert prereqs.classify_secret("2f1a.aBc-123") is None


def test_writing_refuses_to_overwrite_a_recorded_name_without_force() -> None:
    existing = prereqs.render_credentials({"ZAI_API_KEY": "old"})
    plan, detail = prereqs.plan_credentials(existing, "ZAI_API_KEY", force=False)
    assert plan is None
    assert "already recorded" in detail


def test_force_replaces_and_a_new_name_is_a_create() -> None:
    existing = prereqs.render_credentials({"ZAI_API_KEY": "old"})
    assert prereqs.plan_credentials(existing, "ZAI_API_KEY", force=True)[0] == "replace"
    assert prereqs.plan_credentials(existing, "OTHER", force=False)[0] == "create"
    assert prereqs.plan_credentials(None, "ZAI_API_KEY", force=False)[0] == "create"


def paste(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    """Feed one secret the way the real seam takes it: never through argv."""
    monkeypatch.setattr(prereqs, "read_secret", lambda _prompt: value)


def test_the_key_reaches_the_file_at_0600_and_reaches_nothing_else(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    pasted = "zai-not-a-real-key-9f3a"
    paste(monkeypatch, pasted)
    layout = layout_in(tmp_path)
    report = prereqs.action_credentials(layout, args("credentials"))
    for line in report.lines:
        sys.stdout.write(line + "\n")
    printed = capsys.readouterr()
    assert report.code == 0
    assert pasted in layout.credentials.read_text()
    assert stat.S_IMODE(layout.credentials.stat().st_mode) == 0o600
    assert pasted not in printed.out
    assert pasted not in printed.err
    assert not any(pasted in line for line in report.lines)


def test_the_credentials_file_lands_outside_every_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paste(monkeypatch, "zai-key")
    layout = layout_in(tmp_path)
    prereqs.action_credentials(layout, args("credentials"))
    assert prereqs.STATE_DIR_NAME in layout.credentials.parts
    assert ".claude/worktrees" not in str(layout.credentials)
    probe = subprocess.run(  # noqa: S603
        ["git", "-C", str(layout.credentials.parent), "rev-parse", "--is-inside-work-tree"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    assert probe.stdout.strip() != "true"


def test_a_credentials_path_inside_a_work_tree_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(prereqs, "inside_git_repository", lambda _path: True)
    report = prereqs.action_credentials(layout_in(tmp_path), args("credentials"))
    assert report.lines[0] == "refused=credentials_inside_repository"


def test_a_second_run_refuses_and_changes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    layout = layout_in(tmp_path)
    paste(monkeypatch, "first-key")
    prereqs.action_credentials(layout, args("credentials"))
    before = layout.credentials.read_text()
    paste(monkeypatch, "second-key")
    report = prereqs.action_credentials(layout, args("credentials"))
    assert report.code == prereqs.EXIT_REFUSED
    assert report.lines[0] == "refused=credential_exists"
    assert layout.credentials.read_text() == before


def test_force_replaces_one_name_and_keeps_the_others(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    layout = layout_in(tmp_path)
    paste(monkeypatch, "zai-first")
    prereqs.action_credentials(layout, args("credentials"))
    paste(monkeypatch, "other-secret")
    prereqs.action_credentials(layout, args("credentials", "--name", "OTHER_KEY"))
    paste(monkeypatch, "zai-second")
    report = prereqs.action_credentials(layout, args("credentials", "--force"))
    recorded = prereqs.parse_credentials(layout.credentials.read_text())
    assert report.lines[0] == "ok=credential_replace"
    assert recorded == {"ZAI_API_KEY": "zai-second", "OTHER_KEY": "other-secret"}


def test_a_bad_paste_writes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paste(monkeypatch, "")
    layout = layout_in(tmp_path)
    report = prereqs.action_credentials(layout, args("credentials"))
    assert report.lines[0] == "refused=bad_paste"
    assert not layout.credentials.exists()


def test_no_flag_anywhere_takes_a_secret_on_argv() -> None:
    # The paste comes off the terminal with echo off, so it is not in the shell's
    # history and not in `ps`. Nothing may offer a second way in.
    parser_options = {
        option for action in prereqs.parse_args(["credentials"]).__dict__ for option in [action]
    }
    assert parser_options == {"action", "name", "force"}
    with pytest.raises(SystemExit):
        prereqs.parse_args(["credentials", "--value", "leaked"])


def test_the_secret_seam_reads_the_terminal_with_echo_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(prereqs.getpass, "getpass", lambda _prompt: "from-the-tty")
    assert prereqs.read_secret("prompt: ") == "from-the-tty"


# --------------------------------------------------------------------- statusline


def test_chaining_keeps_the_existing_command_verbatim() -> None:
    tap = Path("/repo/tools/quota_tap.sh")
    chained = prereqs.chain_command(CAVEMAN, tap)
    assert chained.startswith(f"bash {tap} ")
    assert prereqs.unwrap_command(chained) == CAVEMAN


def test_chaining_twice_changes_nothing() -> None:
    tap = Path("/repo/tools/quota_tap.sh")
    once = prereqs.chain_command(CAVEMAN, tap)
    assert prereqs.chain_command(once, tap) == once


def test_a_moved_checkout_rechains_rather_than_nesting_two_taps() -> None:
    old = prereqs.chain_command(CAVEMAN, Path("/old/tools/quota_tap.sh"))
    new = prereqs.chain_command(old, Path("/new/tools/quota_tap.sh"))
    assert new.count("quota_tap.sh") == 1
    assert prereqs.unwrap_command(new) == CAVEMAN


def test_planning_refuses_a_status_line_it_cannot_chain() -> None:
    tap = Path("/repo/tools/quota_tap.sh")
    with pytest.raises(prereqs.MergeRefusedError) as refusal:
        prereqs.plan_statusline({"statusLine": {"type": "static", "text": "hi"}}, tap)
    assert refusal.value.reason == "unsupported_statusline"


def settings_at(path: Path, command: str | None = CAVEMAN) -> None:
    """Write a settings document shaped like the real one."""
    document: dict[str, object] = {"model": "opus", "permissions": {"allow": ["Bash"]}}
    if command is not None:
        document["statusLine"] = {"type": "command", "command": command}
    document["theme"] = "dark"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2))


def test_the_recipe_chains_backs_up_and_leaves_the_rest_of_settings_alone(
    tmp_path: Path,
) -> None:
    layout = layout_in(tmp_path)
    settings_at(layout.settings)
    before = json.loads(layout.settings.read_text())
    report = prereqs.action_statusline(layout, args("statusline"))
    after = json.loads(layout.settings.read_text())
    assert report.lines[0] == "ok=statusline_chained"
    assert {k: v for k, v in after.items() if k != "statusLine"} == {
        k: v for k, v in before.items() if k != "statusLine"
    }
    assert list(after) == list(before)
    assert prereqs.unwrap_command(after["statusLine"]["command"]) == CAVEMAN
    backups = list(tmp_path.rglob("settings.json.bak-*"))
    assert len(backups) == 1
    assert json.loads(backups[0].read_text()) == before


def test_a_second_chain_is_a_no_op(tmp_path: Path) -> None:
    layout = layout_in(tmp_path)
    settings_at(layout.settings)
    prereqs.action_statusline(layout, args("statusline"))
    written = layout.settings.read_text()
    report = prereqs.action_statusline(layout, args("statusline"))
    assert report.lines[0] == "ok=already_chained"
    assert layout.settings.read_text() == written


def test_a_dry_run_writes_nothing(tmp_path: Path) -> None:
    layout = layout_in(tmp_path)
    settings_at(layout.settings)
    before = layout.settings.read_text()
    report = prereqs.action_statusline(layout, args("statusline", "--dry-run"))
    assert report.lines[0] == "ok=dry_run"
    assert layout.settings.read_text() == before
    assert not list(tmp_path.rglob("settings.json.bak-*"))


def test_the_recipe_states_the_governance_weakness_in_its_own_output(tmp_path: Path) -> None:
    layout = layout_in(tmp_path)
    settings_at(layout.settings)
    report = prereqs.action_statusline(layout, args("statusline", "--dry-run"))
    body = "\n".join(report.lines)
    assert "outside this repository" in body
    assert "429" in body


def test_the_recipe_will_not_rewrite_settings_it_cannot_parse(tmp_path: Path) -> None:
    layout = layout_in(tmp_path)
    layout.settings.parent.mkdir(parents=True)
    layout.settings.write_text("{not json")
    report = prereqs.action_statusline(layout, args("statusline"))
    assert report.lines[0] == "refused=settings_unparseable"
    assert layout.settings.read_text() == "{not json"


# ------------------------------------------------------ the tap, run for real


def run_tap(
    payload: str,
    downstream: str,
    spool: Path,
    *,
    oauth: bool = False,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Drive the real tap script the way Claude Code drives a status line."""
    return subprocess.run(  # noqa: S603
        ["bash", str(REPO / "tools" / "quota_tap.sh"), downstream],  # noqa: S607
        input=payload,
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "CTI_QUOTA_SPOOL": str(spool),
            "CTI_QUOTA_OAUTH": "1" if oauth else "0",
            **(extra_env or {}),
        },
    )


def test_the_tap_passes_the_downstream_output_through_byte_for_byte(tmp_path: Path) -> None:
    downstream = tmp_path / "status.sh"
    downstream.write_text("#!/usr/bin/env bash\nprintf 'MODEL %s | ctx\\n' \"$(cat)\"\n")
    payload = '{"model":{"display_name":"Opus"},"cost":{"total_cost_usd":1.5}}'
    command = f"bash {downstream}"

    alone = subprocess.run(  # noqa: S603
        ["bash", "-c", command],  # noqa: S607
        input=payload,
        capture_output=True,
        text=True,
        check=False,
    )
    chained = run_tap(payload, command, tmp_path / "spool.jsonl")

    assert chained.returncode == alone.returncode == 0
    assert chained.stdout == alone.stdout
    # The spooled line is the #488 envelope: the payload byte-identical under
    # `payload`, beside a timestamp the reader can place it by.
    spooled = json.loads((tmp_path / "spool.jsonl").read_text())
    assert spooled["payload"] == json.loads(payload)
    assert datetime.fromisoformat(spooled["ts"])


def test_the_tap_fails_open_when_it_cannot_spool(tmp_path: Path) -> None:
    downstream = tmp_path / "status.sh"
    downstream.write_text("#!/usr/bin/env bash\ncat >/dev/null; printf 'still here\\n'\n")
    unwritable = tmp_path / "locked"
    unwritable.mkdir(mode=0o500)
    result = run_tap("{}", f"bash {downstream}", unwritable / "deep" / "spool.jsonl")
    assert result.returncode == 0
    assert result.stdout == "still here\n"


def test_the_tap_with_no_downstream_prints_nothing_and_still_spools(tmp_path: Path) -> None:
    spool = tmp_path / "spool.jsonl"
    result = subprocess.run(  # noqa: S603
        ["bash", str(REPO / "tools" / "quota_tap.sh")],  # noqa: S607
        input='{"a":1}',
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "CTI_QUOTA_SPOOL": str(spool), "CTI_QUOTA_OAUTH": "0"},
    )
    assert result.returncode == 0
    assert result.stdout == ""
    spooled = json.loads(spool.read_text())
    assert spooled["payload"] == {"a": 1}
    assert datetime.fromisoformat(spooled["ts"])


def test_the_tap_rolls_over_rather_than_growing_without_bound(tmp_path: Path) -> None:
    spool = tmp_path / "spool.jsonl"
    spool.write_text("x" * 200)
    result = subprocess.run(  # noqa: S603
        ["bash", str(REPO / "tools" / "quota_tap.sh")],  # noqa: S607
        input='{"a":1}',
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "CTI_QUOTA_SPOOL": str(spool),
            "CTI_QUOTA_MAX": "100",
            "CTI_QUOTA_OAUTH": "0",
        },
    )
    assert result.returncode == 0
    assert json.loads(spool.read_text())["payload"] == {"a": 1}
    assert (tmp_path / "spool.jsonl.1").read_text() == "x" * 200


def test_the_tap_refreshes_oauth_usage_off_the_status_line_path(tmp_path: Path) -> None:
    marker = tmp_path / "oauth-call"
    fake = tmp_path / "fake-breaker.sh"
    fake.write_text(
        '#!/usr/bin/env bash\npayload="$(cat)"\n'
        'printf \'%s\\n%s\\n\' "$*" "${payload}" >"${CTI_QUOTA_MARKER}"\n'
    )
    payload = '{"model":{"display_name":"Opus"}}'

    done = run_tap(
        payload,
        "cat",
        tmp_path / "spool.jsonl",
        oauth=True,
        extra_env={
            "CTI_QUOTA_BREAKER": str(fake),
            "CTI_QUOTA_PYTHON": "bash",
            "CTI_QUOTA_MARKER": str(marker),
            "CTI_QUOTA_LOCK": str(tmp_path / "oauth.lock"),
            "CTI_BREAKER_DIR": str(tmp_path / "breaker"),
        },
    )
    deadline = time.monotonic() + 2
    while not marker.exists() and time.monotonic() < deadline:
        time.sleep(0.01)

    assert done.stdout == f"{payload}\n"
    called = marker.read_text(encoding="utf-8")
    assert "tap --lane claude-native --oauth-usage" in called
    assert called.endswith(f"{payload}\n")


# ------------------------------------------------------------------ codex config


def test_the_codex_config_disables_the_off_box_metrics_exporter() -> None:
    body = prereqs.CODEX_CONFIG
    assert "[otel]" in body
    assert 'metrics_exporter = "none"' in body
    # It must say what it is disabling, or a reader cannot judge whether it worked.
    assert "ab.chatgpt.com" in body
    assert "Statsig" in body
    assert "log_user_prompt = false" in body


def test_the_codex_config_admits_the_key_spelling_is_unverified() -> None:
    assert "UNVERIFIED" in prereqs.CODEX_CONFIG


def test_the_tools_action_writes_the_codex_config_before_any_first_use(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        prereqs.shutil, "which", lambda name: "/usr/bin/gitleaks" if name == "gitleaks" else None
    )
    layout = layout_in(tmp_path)
    report = prereqs.action_tools(layout, args("tools"))
    assert report.code == 0
    assert prereqs.probe_codex_config(layout.codex_config).present is True
    assert stat.S_IMODE(layout.codex_config.stat().st_mode) == 0o600
    assert any(line.startswith("skipped=codex_cli") for line in report.lines)


# ------------------------------------------------------------------------ gitleaks


def test_the_release_asset_names_follow_the_tag() -> None:
    assets = prereqs.release_assets("v8.30.1")
    assert assets.version == "8.30.1"
    assert assets.tarball == "gitleaks_8.30.1_linux_x64.tar.gz"
    assert assets.checksums == "gitleaks_8.30.1_checksums.txt"


def test_a_published_checksum_is_read_and_an_absent_one_is_not_invented() -> None:
    published = (
        "abc123  gitleaks_8.30.1_linux_x64.tar.gz\ndef456 *gitleaks_8.30.1_darwin_x64.tar.gz\n"
    )
    assert prereqs.expected_digest(published, "gitleaks_8.30.1_linux_x64.tar.gz") == "abc123"
    assert prereqs.expected_digest(published, "gitleaks_8.30.1_darwin_x64.tar.gz") == "def456"
    assert prereqs.expected_digest(published, "gitleaks_8.30.1_windows_x64.zip") is None


# ------------------------------------------------------------------------ plan tier


def test_recording_a_tier_writes_the_caps_the_estimator_needs(tmp_path: Path) -> None:
    layout = layout_in(tmp_path)
    report = prereqs.action_plan_tier(layout, args("plan-tier", "--set", "pro"))
    record = json.loads(layout.plan_tier.read_text())
    assert report.code == 0
    assert record["tier"] == "pro"
    assert (record["prompts_per_5h"], record["prompts_per_7d"]) == (12_000, 60_000)
    assert record["source"] == "human"
    assert prereqs.probe_plan_tier(layout.plan_tier).present is True


def test_the_tier_cannot_be_read_without_a_credential(tmp_path: Path) -> None:
    report = prereqs.action_plan_tier(layout_in(tmp_path), args("plan-tier"))
    assert report.lines[0] == "refused=no_credential"


def test_an_unreadable_tier_is_refused_rather_than_guessed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paste(monkeypatch, "zai-key")
    layout = layout_in(tmp_path)
    prereqs.action_credentials(layout, args("credentials"))
    report = prereqs.action_plan_tier(layout, args("plan-tier"))
    body = "\n".join(report.lines)
    assert report.lines[0] == "refused=plan_tier_unknown"
    assert "no machine-readable quota or plan-tier endpoint" in body
    assert not layout.plan_tier.exists()
    # Nothing here asserts a tier: no recorded value, and no line claiming one.
    assert not any(line.startswith(("tier=", "ok=")) for line in report.lines)


def test_a_named_endpoint_is_probed_and_its_answer_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paste(monkeypatch, "zai-key")
    layout = layout_in(tmp_path)
    prereqs.action_credentials(layout, args("credentials"))
    monkeypatch.setattr(prereqs, "probe_endpoint", lambda url, _token: f"404 nothing at {url}")
    report = prereqs.action_plan_tier(
        layout, args("plan-tier", "--endpoint", "https://api.z.ai/whatever")
    )
    assert (
        "probe=https://api.z.ai/whatever -> 404 nothing at https://api.z.ai/whatever"
        in report.lines
    )


def test_the_endpoint_probe_never_sees_the_key_on_a_command_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(*_args: object, **_kwargs: object) -> None:
        message = "the tier probe must not shell out"
        raise AssertionError(message)

    monkeypatch.setattr(subprocess, "run", explode)
    paste(monkeypatch, "zai-key")
    layout = layout_in(tmp_path)
    monkeypatch.setattr(prereqs, "inside_git_repository", lambda _path: False)
    prereqs.action_credentials(layout, args("credentials"))
    monkeypatch.setattr(prereqs, "probe_endpoint", lambda _url, _token: "no response")
    prereqs.action_plan_tier(layout, args("plan-tier", "--endpoint", "https://example.invalid"))


# ---------------------------------------------------------------------------- check


def facts(**overrides: object) -> Any:  # noqa: ANN401 - see layout_in
    """Build a Facts with everything present, then what the test wants missing."""
    present = prereqs.Probe(present=True, detail="present")
    base = dict.fromkeys(prereqs.Facts._fields, present)
    return prereqs.Facts(**{**base, **overrides})


def test_everything_present_is_a_green_check() -> None:
    report = prereqs.render_check(prereqs.evaluate(facts()))
    assert report.code == 0
    assert report.lines[-1] == "ok=prereqs_met"


def test_a_missing_item_names_itself_and_what_to_run() -> None:
    missing = prereqs.Probe(present=False, detail="not on PATH")
    report = prereqs.render_check(prereqs.evaluate(facts(gitleaks=missing)))
    assert report.code == prereqs.EXIT_REFUSED
    assert "item=gitleaks state=missing" in report.lines[0]
    assert "action=just prereqs tools" in report.lines[0]
    assert report.lines[-2] == "refused=prereqs_missing"


def test_a_check_that_could_not_run_is_never_a_pass() -> None:
    unknown = prereqs.Probe(present=None, detail="unreadable: Permission denied")
    report = prereqs.render_check(prereqs.evaluate(facts(collector=unknown)))
    body = "\n".join(report.lines)
    assert report.code == prereqs.EXIT_REFUSED
    assert "item=collector_ledger state=unknown" in body
    assert prereqs.COULD_NOT_RUN in body


def test_the_codex_lane_is_reported_but_does_not_gate_week_one() -> None:
    missing = prereqs.Probe(present=False, detail="absent")
    report = prereqs.render_check(prereqs.evaluate(facts(codex_cli=missing, codex_config=missing)))
    body = "\n".join(report.lines)
    assert report.code == 0
    assert "item=codex_cli state=missing blocks=codex-lane" in body
    assert "2 deferred to the Codex lane" in body


def test_a_written_codex_config_is_reported_unverified_and_never_ok() -> None:
    # The `[otel]` key spelling comes from the crate, not from a schema. A file
    # that says the right thing is not a file that was read the way it intends.
    report = prereqs.render_check(prereqs.evaluate(facts()))
    line = next(line for line in report.lines if line.startswith("item=codex_config"))
    assert "state=unverified" in line
    assert "ab.chatgpt.com" in line
    assert report.code == 0  # deferred: it changes what the line claims, not the exit


def test_every_item_says_what_to_do_about_it() -> None:
    missing = prereqs.Probe(present=False, detail="absent")
    for item in prereqs.evaluate(facts(**dict.fromkeys(prereqs.Facts._fields, missing))):
        assert item.action
        assert item.blocks


def test_the_check_reads_the_box_and_reports_a_line_per_item(tmp_path: Path) -> None:
    layout = layout_in(tmp_path)
    report = prereqs.action_check(layout, args("check"))
    named = [line.split(" ", 1)[0] for line in report.lines if line.startswith("item=")]
    assert named == [
        f"item={item}"
        for item in (
            "gitleaks",
            "credentials_file",
            "zai_key",
            "collector_ledger",
            "ledger_dir",
            "statusline_tap",
            "plan_tier",
            "codex_config",
            "codex_cli",
        )
    ]


def test_no_action_defaults_to_check() -> None:
    assert prereqs.parse_args([]).action == "check"
    assert set(prereqs.ACTIONS) == {
        "check",
        "credentials",
        "sudo-script",
        "statusline",
        "tools",
        "plan-tier",
    }
