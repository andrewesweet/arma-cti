"""The dispatcher's registry, refusals, environment assembly and detached seam (#223).

Three layers, all in the no-Arma tier.

The pure functions come first, because ADR-0061's rulings are what they encode: a
profile is one opaque token (Decision 5), a seat's eligibility is a property of the
surface (Decision 2), and a dispatch's identity is six `cti.*` attributes (Decision 1's
metering). Each refusal is asserted by its own name and its own class.

Under them sit end-to-end runs through the real `tools/dispatch.sh`, against a real
temporary git worktree and a **fake `claude` on `PATH`**. The fake is not a stub of our
own code: the registry's runner is the bare name `claude`, resolved off `PATH` like
every other tool this project shells out to, so a test that puts a different `claude`
first exercises the whole seam — plan, fork, worktree assertion, environment assembly,
stdin brief, result file — with nothing mocked. That matters here more than usual,
because the claim this issue exists to make is about an *environment*, and an
environment is exactly what a mocked launcher would not carry.

The heaviest claims are the negative ones, and they are made against a parent
environment that is deliberately poisoned: a parent already carrying
`ANTHROPIC_BASE_URL` must not be able to reach a `claude-native` child, a `zai` dispatch
must not leave one behind in the parent, and a `claude-native` dispatch run immediately
after a `zai` one on the same parent must come up clean. "It set the right variables" is
half the assertion; "and nothing else can see them" is the half this issue is for.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from conftest import REPO, load_tool

if TYPE_CHECKING:
    from types import ModuleType

dispatch = load_tool("dispatch")
breaker = load_tool("breaker")

SEAM = REPO / "tools" / "dispatch.sh"
JUSTFILE = REPO / "justfile"

# A stand-in token: distinctive enough that the tests can assert on exactly where it
# does and does not appear, and *low entropy on purpose*, because `just check` now runs
# gitleaks over this file and a realistic-looking literal here would red the gate that
# this issue added. The vacuity test below builds a high-entropy one at run time instead.
FAKE_TOKEN = "zai-" + "test-" * 6


# --------------------------------------------------------------------------- helpers


def credentials_file(tmp_path: Path, body: str, mode: int = 0o600) -> Path:
    """Write a credentials file at a chosen mode, which is half of what is under test."""
    path = tmp_path / "credentials.env"
    path.write_text(body, encoding="utf-8")
    path.chmod(mode)
    return path


def git_worktree(tmp_path: Path, name: str = "tree") -> Path:
    """Make a real git repository, because the worktree assertion's subject is real git."""
    root = tmp_path / name
    root.mkdir(parents=True)
    for args in (
        ("init", "-q", "-b", "main"),
        ("config", "user.email", "t@example.invalid"),
        ("config", "user.name", "t"),
    ):
        # S603/S607: fixed literals, and `git` resolves off PATH like everywhere else.
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)  # noqa: S603, S607
    (root / "README.md").write_text("t\n", encoding="utf-8")
    for args in (("add", "-A"), ("commit", "-qm", "t")):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)  # noqa: S603, S607
    return root


def fake_claude(tmp_path: Path) -> Path:
    """Put a `claude` on `PATH` that records its argv, environment and stdin, and exits 0.

    The registry names its runner as the bare word `claude`, so this is the real
    resolution path and not a seam the test invented.
    """
    bindir = tmp_path / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    runner = bindir / "claude"
    runner.write_text(
        """#!/usr/bin/env bash
{
  printf 'argv=%s\\n' "$*"
  printf 'cwd=%s\\n' "$PWD"
  printf 'stdin=%s\\n' "$(cat | tr '\\n' ' ')"
  env
} >"$CTI_FAKE_CLAUDE_OUT"
""",
        encoding="utf-8",
    )
    runner.chmod(0o755)
    return bindir


def seam_env(tmp_path: Path, capture: Path, **extra: str) -> dict[str, str]:
    """Build the parent environment a seam run inherits — deliberately poisoned."""
    env = dict(os.environ)
    env["PATH"] = f"{fake_claude(tmp_path)}:{env['PATH']}"
    env["CTI_FAKE_CLAUDE_OUT"] = str(capture)
    # The accident this whole design exists to prevent: a parent that already carries a
    # foreign base URL. Every child must come out the same whether or not this is here.
    env["ANTHROPIC_BASE_URL"] = "https://poisoned.invalid"
    # The seam forks a real process, so its breaker has to be pointed somewhere of this
    # test's own: a run whose result depended on what this box's lanes were doing would
    # be a test of the machine rather than of the dispatcher (#226).
    env["CTI_BREAKER_DIR"] = str(tmp_path / "breaker")
    env.update(extra)
    return env


def run_seam(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run `tools/dispatch.sh` exactly as `just dispatch` does."""
    return subprocess.run(  # noqa: S603
        [str(SEAM), *args],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def read_lines(text: str) -> dict[str, str]:
    """Fold the tier's `key=value` output into a mapping, last value winning."""
    found: dict[str, str] = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            found[key.strip()] = value
    return found


def await_file(path: Path, seconds: float = 90.0) -> bool:
    """Wait for the detached child to land a file, bounded, polling rather than sleeping.

    A dispatch is detached by design, so the test's subject genuinely arrives later than
    the call that armed it. The window is sized to `uv run`'s cold start plus a bash
    script, not stretched until something passes.
    """
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if path.exists():
            return True
        time.sleep(0.1)
    return False


def plan_for(tmp_path: Path, **overrides: object) -> tuple[Any, str, Any]:
    """Plan a dispatch over a real worktree without writing a record."""
    worktree = overrides.pop("worktree", None) or git_worktree(tmp_path)
    request = {
        "lane": "claude-native",
        "profile": "opus-high",
        "seat": "implementer",
        "issue": 223,
        "worktree": str(worktree),
        "brief_file": "",
        "base_sha": "",
        "permission_mode": "acceptEdits",
        "dispatch_dir": str(tmp_path / "dispatches"),
        "credentials": str(tmp_path / "credentials.env"),
        "breaker_dir": str(tmp_path / "breaker"),
    }
    request.update(overrides)
    args = _namespace(**request)
    return dispatch.plan_dispatch(args, REPO, datetime.now(tz=UTC))


def _namespace(**fields: object) -> object:
    """Stand in for argparse's Namespace, so a test states only what it varies."""
    return type("Args", (), fields)()


# --------------------------------------------------------------------------- registry


def test_every_profile_belongs_to_a_registered_lane() -> None:
    for profile in dispatch.PROFILES.values():
        assert profile.lane in dispatch.LANES, profile.name


def test_week_one_registers_both_lanes_and_the_two_named_profiles() -> None:
    assert set(dispatch.LANES) == {"claude-native", "zai"}
    assert "opus-high" in dispatch.PROFILES
    assert "zai-glm52-max" in dispatch.PROFILES


def test_the_zai_lane_carries_z_ais_published_mirror_configuration() -> None:
    lane = dispatch.LANES["zai"]
    assert lane.runner == "claude"
    assert lane.base_url == "https://api.z.ai/api/anthropic"
    assert lane.credential == "ZAI_API_KEY"
    assert dict(lane.model_slots) == {
        "ANTHROPIC_DEFAULT_OPUS_MODEL": "glm-5.2",
        "ANTHROPIC_DEFAULT_SONNET_MODEL": "glm-5.2",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": "glm-4.7",
    }


def test_the_native_lane_supplies_no_credential_and_no_base_url() -> None:
    lane = dispatch.LANES["claude-native"]
    assert lane.base_url == ""
    assert lane.credential == ""
    assert lane.foreign is False


def test_an_unknown_lane_is_refused_by_name() -> None:
    refusal = dispatch.resolve_selection("codex", "opus-high", "implementer")
    assert refusal is not None
    assert refusal.kind == "unknown_lane"
    assert "known=claude-native zai" in refusal.found


def test_an_unknown_profile_is_refused_by_name() -> None:
    refusal = dispatch.resolve_selection("claude-native", "opus-turbo", "implementer")
    assert refusal is not None
    assert refusal.kind == "unknown_profile"


def test_a_profile_dispatched_on_another_lane_is_refused() -> None:
    refusal = dispatch.resolve_selection("claude-native", "zai-glm52-max", "implementer")
    assert refusal is not None
    assert refusal.kind == "profile_lane_mismatch"
    assert "profile_lane=zai" in refusal.found


def test_a_registered_selection_is_not_refused() -> None:
    assert dispatch.resolve_selection("claude-native", "opus-high", "implementer") is None
    assert dispatch.resolve_selection("zai", "zai-glm52-max", "review") is None


# ------------------------------------------------------------- Decision 2 eligibility


def test_a_foreign_lane_refuses_the_seats_no_gate_covers() -> None:
    for seat in ("fable", "orchestrator"):
        refusal = dispatch.resolve_selection("zai", "zai-glm52-max", seat)
        assert refusal is not None, seat
        assert refusal.kind == "seat_not_eligible"
        assert "Decision 2" in refusal.action


def test_the_same_seats_dispatch_freely_on_claude_native() -> None:
    # Nothing is leaving Claude on this lane, so Decision 2 does not bind.
    assert dispatch.resolve_selection("claude-native", "opus-xhigh", "fable") is None


def test_an_unknown_seat_is_refused_rather_than_mis_attributed() -> None:
    refusal = dispatch.resolve_selection("claude-native", "opus-high", "implemeter")
    assert refusal is not None
    assert refusal.kind == "unknown_seat"


# ---------------------------------------------------------------------- identity/OTel


def test_a_minted_dispatch_id_stays_inside_the_required_alphabet() -> None:
    minted = dispatch.mint_dispatch_id(datetime(2026, 8, 5, 18, 30, 1, tzinfo=UTC), "a1b2c3")
    assert minted == "d-20260805-183001-a1b2c3"
    assert dispatch.ID_ALPHABET.fullmatch(minted)


def identity(**overrides: object) -> object:
    """One identity, so the attribute tests state only what they vary."""
    fields = {
        "dispatch_id": "d-20260805-183001-a1b2c3",
        "lane": "zai",
        "profile": "zai-glm52-max",
        "seat": "review",
        "issue": 223,
        "base_sha": "22b985e",
    }
    fields.update(overrides)
    return dispatch.Identity(**fields)


def test_the_six_cti_attributes_are_all_present() -> None:
    rendered = dispatch.resource_attributes(identity(), "")
    keys = [pair.split("=", 1)[0] for pair in rendered.split(",")]
    assert keys == [
        "cti.dispatch_id",
        "cti.lane",
        "cti.profile",
        "cti.seat",
        "cti.issue",
        "cti.base_sha",
    ]


def test_resource_attributes_are_ascii_and_space_free() -> None:
    rendered = dispatch.resource_attributes(identity(seat="a seat with spaces"), "")
    assert " " not in rendered
    assert rendered.isascii()
    assert "cti.seat=a%20seat%20with%20spaces" in rendered


def test_the_parents_own_attributes_survive_and_its_cti_ones_do_not() -> None:
    inherited = "team.id=platform,cti.dispatch_id=d-somebody-elses,cost_center=eng-123"
    rendered = dispatch.resource_attributes(identity(), inherited)
    assert rendered.startswith("team.id=platform,cost_center=eng-123,")
    assert "d-somebody-elses" not in rendered
    assert rendered.count("cti.dispatch_id=") == 1


# ------------------------------------------------------- environment, per invocation


def assembled(lane: str, profile: str, parent: dict[str, str], token: str = "") -> dict[str, str]:
    """Assemble one child environment, so the leak tests read as the claims they make."""
    return dispatch.assemble_environment(
        parent, dispatch.PROFILES[profile], identity(lane=lane, profile=profile), token
    )


def test_the_zai_lane_reaches_z_ai_and_carries_its_token_in_the_environment() -> None:
    child = assembled("zai", "zai-glm52-max", {"HOME": "/home/t"}, FAKE_TOKEN)
    assert child["ANTHROPIC_BASE_URL"] == "https://api.z.ai/api/anthropic"
    assert child["ANTHROPIC_AUTH_TOKEN"] == FAKE_TOKEN
    assert child["ANTHROPIC_DEFAULT_OPUS_MODEL"] == "glm-5.2"


def test_a_foreign_lane_with_no_token_exports_no_empty_one() -> None:
    # An empty `ANTHROPIC_AUTH_TOKEN` outranks the subscription OAuth in Claude Code's
    # credential ladder, so exporting a blank one is worse than exporting none.
    child = assembled("zai", "zai-glm52-max", {"HOME": "/home/t"}, "")
    assert "ANTHROPIC_AUTH_TOKEN" not in child


def test_the_native_lane_sets_no_base_url_and_no_token() -> None:
    child = assembled("claude-native", "opus-high", {"HOME": "/home/t"})
    assert "ANTHROPIC_BASE_URL" not in child
    assert "ANTHROPIC_AUTH_TOKEN" not in child


def test_a_poisoned_parent_cannot_reach_a_native_child() -> None:
    parent = {
        "HOME": "/home/t",
        "ANTHROPIC_BASE_URL": "https://poisoned.invalid",
        "ANTHROPIC_AUTH_TOKEN": "leaked",
        "ANTHROPIC_DEFAULT_OPUS_MODEL": "glm-5.2",
    }
    child = assembled("claude-native", "opus-high", parent)
    for key in ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_DEFAULT_OPUS_MODEL"):
        assert key not in child, key


def test_every_lane_owned_variable_is_stripped_before_the_lane_adds_its_own() -> None:
    parent = dict.fromkeys(dispatch.LANE_OWNED, "inherited")
    child = assembled("claude-native", "opus-high", parent)
    assert not [key for key in dispatch.LANE_OWNED if child.get(key) == "inherited"]


def test_assembly_never_mutates_the_parent_and_a_sibling_lane_comes_up_clean() -> None:
    parent = {"HOME": "/home/t"}
    before = dict(parent)
    zai = assembled("zai", "zai-glm52-max", parent, FAKE_TOKEN)
    native = assembled("claude-native", "opus-high", parent)
    assert parent == before
    assert zai["ANTHROPIC_BASE_URL"] == "https://api.z.ai/api/anthropic"
    assert "ANTHROPIC_BASE_URL" not in native
    assert FAKE_TOKEN not in native.values()


def test_the_child_carries_its_assignment_for_anything_downstream_to_re_assert() -> None:
    child = assembled("zai", "zai-glm52-max", {"HOME": "/home/t"}, FAKE_TOKEN)
    assert child["CTI_DISPATCH_LANE"] == "zai"
    assert child["CTI_DISPATCH_SEAT"] == "review"
    assert child["CTI_DISPATCH_ISSUE"] == "223"


def test_redaction_replaces_the_token_and_leaves_everything_else_verbatim() -> None:
    child = assembled("zai", "zai-glm52-max", {"HOME": "/home/t"}, FAKE_TOKEN)
    shown = dispatch.redacted(child, FAKE_TOKEN)
    assert shown["ANTHROPIC_AUTH_TOKEN"] == "<redacted>"  # noqa: S105 — that is the point
    assert shown["HOME"] == "/home/t"
    assert FAKE_TOKEN not in "".join(shown.values())


# ------------------------------------------------------------------------ credentials


def test_a_missing_credentials_file_is_a_typed_refusal_not_a_crash(tmp_path: Path) -> None:
    # The z.ai lane's week-one shape: the registry entry lands, the key does not exist
    # yet (#229), and asking for it says so in the tier's own vocabulary.
    token, refusal = dispatch.lane_credential(dispatch.LANES["zai"], tmp_path / "nothing.env")
    assert token == ""
    assert refusal is not None
    assert refusal.kind == "credentials_missing"
    assert refusal.failure_class == "infra_unavailable"
    assert "class=infra_unavailable" in refusal.lines()


def test_a_world_readable_credentials_file_is_refused(tmp_path: Path) -> None:
    path = credentials_file(tmp_path, f"ZAI_API_KEY={FAKE_TOKEN}\n", mode=0o644)
    _, refusal = dispatch.lane_credential(dispatch.LANES["zai"], path)
    assert refusal is not None
    assert refusal.kind == "credentials_mode"
    assert "mode=0644" in refusal.found


def test_a_credentials_file_without_this_lanes_key_is_refused(tmp_path: Path) -> None:
    path = credentials_file(tmp_path, "OTHER_KEY=x\n")
    _, refusal = dispatch.lane_credential(dispatch.LANES["zai"], path)
    assert refusal is not None
    assert refusal.kind == "credential_absent"
    assert "key=ZAI_API_KEY" in refusal.found


def test_a_lane_needing_no_credential_reads_no_file(tmp_path: Path) -> None:
    token, refusal = dispatch.lane_credential(
        dispatch.LANES["claude-native"], tmp_path / "absent.env"
    )
    assert (token, refusal) == ("", None)


def test_the_credentials_format_is_read_not_executed(tmp_path: Path) -> None:
    path = credentials_file(
        tmp_path,
        "\n".join(
            (
                "# a comment",
                "",
                f'export ZAI_API_KEY="{FAKE_TOKEN}"',
                "OTHER='quoted'",
                "$(touch /tmp/pwned)",  # the point is that this stays inert text
            )
        ),
    )
    values, refusal = dispatch.read_credentials(path)
    assert refusal is None
    assert values["ZAI_API_KEY"] == FAKE_TOKEN
    assert values["OTHER"] == "quoted"


# -------------------------------------------------------------- worktree assertion


def test_a_matching_top_level_passes(tmp_path: Path) -> None:
    root = git_worktree(tmp_path)
    assert dispatch.assert_worktree(root, str(root)) is None


def test_a_top_level_somewhere_else_refuses_loudly(tmp_path: Path) -> None:
    refusal = dispatch.assert_worktree(tmp_path / "assigned", str(tmp_path / "elsewhere"))
    assert refusal is not None
    assert refusal.kind == "worktree_mismatch"
    assert "#105" in refusal.action
    assert any(line.startswith("actual=") for line in refusal.found)


def test_a_path_git_cannot_read_is_infra_unavailable(tmp_path: Path) -> None:
    refusal = dispatch.assert_worktree(tmp_path / "assigned", "")
    assert refusal is not None
    assert refusal.kind == "worktree_unreadable"
    assert refusal.failure_class == "infra_unavailable"


def test_a_dispatch_whose_worktree_does_not_exist_is_refused_before_planning(
    tmp_path: Path,
) -> None:
    plan, _, refusal = plan_for(tmp_path, worktree=tmp_path / "never-created")
    assert plan is None
    assert refusal is not None
    assert refusal.kind == "worktree_missing"
    assert "just worktree add issue-223" in refusal.action


# ------------------------------------------------------------------ plan and record


def test_a_plan_carries_the_profiles_flags_and_no_secret(tmp_path: Path) -> None:
    plan, brief, refusal = plan_for(tmp_path)
    assert refusal is None
    assert plan is not None
    assert plan.argv[0] == "claude"
    assert "--model" in plan.argv
    assert plan.argv[plan.argv.index("--model") + 1] == "opus"
    assert plan.argv[plan.argv.index("--effort") + 1] == "high"
    assert f"#{plan.identity.issue}" in brief


def test_the_default_root_is_the_main_checkout_even_from_inside_a_worktree(
    tmp_path: Path,
) -> None:
    # A dispatch armed from a worktree defaults its assignment to a *sibling* under the
    # main checkout. Read the naive way — `rev-parse --show-toplevel` — the default
    # would be `<this worktree>/.claude/worktrees/issue-N`, which is nowhere. Asserted
    # against a real linked worktree, the only arrangement where the two readings differ.
    root = git_worktree(tmp_path, name="checkout")
    linked = root / ".claude" / "worktrees" / "issue-1"
    add = ("worktree", "add", "-q", "--detach", str(linked))
    subprocess.run(["git", *add], cwd=root, check=True, capture_output=True)  # noqa: S603, S607
    assert dispatch.git("rev-parse", "--show-toplevel", cwd=linked) == str(linked)
    assert dispatch.main_checkout(linked) == root
    assert dispatch.main_checkout(root) == root


def test_the_default_worktree_is_the_one_just_worktree_add_makes(tmp_path: Path) -> None:
    args = _namespace(
        lane="claude-native",
        profile="opus-high",
        seat="implementer",
        issue=999,
        worktree="",
        brief_file="",
        base_sha="",
        permission_mode="acceptEdits",
        dispatch_dir=str(tmp_path / "d"),
        credentials=str(tmp_path / "c.env"),
        breaker_dir=str(tmp_path / "breaker"),
    )
    _, _, refusal = dispatch.plan_dispatch(args, REPO, datetime.now(tz=UTC))
    assert refusal is not None
    assert f"worktree={REPO / '.claude' / 'worktrees' / 'issue-999'}" in refusal.found


def test_the_record_names_the_credential_key_and_never_its_value(tmp_path: Path) -> None:
    credentials_file(tmp_path, f"ZAI_API_KEY={FAKE_TOKEN}\n")
    plan, brief, refusal = plan_for(tmp_path, lane="zai", profile="zai-glm52-max", seat="review")
    assert refusal is None
    assert plan is not None
    dispatch.write_record(plan, brief)

    document = json.loads((plan.record / "dispatch.json").read_text(encoding="utf-8"))
    assert document["credential"] == "ZAI_API_KEY"
    for path in sorted(plan.record.rglob("*")):
        if path.is_file():
            assert FAKE_TOKEN not in path.read_text(encoding="utf-8"), path
    assert FAKE_TOKEN not in " ".join(plan.argv)


def test_a_written_record_reads_back_as_the_same_plan(tmp_path: Path) -> None:
    plan, brief, _ = plan_for(tmp_path)
    assert plan is not None
    dispatch.write_record(plan, brief)
    assert dispatch.load_record(plan.record) == plan


def test_an_incomplete_request_names_what_is_missing(capsys: pytest.CaptureFixture[str]) -> None:
    code = dispatch.main(["--lane", "claude-native"])
    assert code == dispatch.EXIT_REFUSED
    printed = capsys.readouterr().err
    assert "refusal=incomplete_request" in printed
    assert "--profile" in printed
    assert "--seat" in printed
    assert "--issue" in printed


def test_the_registry_listing_names_both_lanes_and_the_barred_seats(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert dispatch.main(["--list"]) == 0
    printed = capsys.readouterr().out
    assert "lane=claude-native" in printed
    assert "lane=zai" in printed
    assert "profile=zai-glm52-max" in printed
    assert "seats_claude_native_only=fable orchestrator" in printed


# ------------------------------------------------------- the detached child, in python


def test_the_child_refuses_a_worktree_that_is_not_its_assignment(tmp_path: Path) -> None:
    plan, brief, _ = plan_for(tmp_path)
    assert plan is not None
    dispatch.write_record(plan, brief)
    # Move the assignment to a directory that is not a git top level, which is what a
    # harness handing the agent the wrong tree looks like from inside the child.
    document = json.loads((plan.record / "dispatch.json").read_text(encoding="utf-8"))
    stray = tmp_path / "stray"
    stray.mkdir()
    document["worktree"] = str(stray)
    (plan.record / "dispatch.json").write_text(json.dumps(document), encoding="utf-8")

    code, lines = dispatch.run_dispatch(plan.record, {"HOME": str(tmp_path)})
    assert code == dispatch.EXIT_REFUSED
    assert any("refusal=worktree_" in line for line in lines)
    result = json.loads((plan.record / "result.json").read_text(encoding="utf-8"))
    assert result["failure_class"] == "infra_unavailable"
    assert "returncode" not in result


def test_the_zai_lane_refuses_at_the_recipe_while_its_key_does_not_exist(
    tmp_path: Path,
) -> None:
    """Week one's z.ai shape: the lane is registered and cannot be exercised (#229)."""
    plan, _, refusal = plan_for(
        tmp_path,
        lane="zai",
        profile="zai-glm52-max",
        seat="review",
        credentials=str(tmp_path / "absent.env"),
    )
    assert plan is None
    assert refusal is not None
    assert refusal.kind == "credentials_missing"
    assert refusal.failure_class == "infra_unavailable"


def test_the_child_re_checks_the_credential_the_plan_already_checked(tmp_path: Path) -> None:
    """Defence in depth: the file can go between the plan and the launch."""
    credentials = credentials_file(tmp_path, f"ZAI_API_KEY={FAKE_TOKEN}\n")
    plan, brief, _ = plan_for(tmp_path, lane="zai", profile="zai-glm52-max", seat="review")
    assert plan is not None
    dispatch.write_record(plan, brief)
    credentials.unlink()

    code, lines = dispatch.run_dispatch(plan.record, {"HOME": str(tmp_path)})
    assert code == dispatch.EXIT_REFUSED
    assert "refusal=credentials_missing" in lines
    assert "class=infra_unavailable" in lines


# --------------------------------------------------------------- the seam, end to end


def test_the_seam_returns_a_dispatch_id_at_once_and_the_child_runs_detached(
    tmp_path: Path,
) -> None:
    worktree = git_worktree(tmp_path)
    capture = tmp_path / "claude-ran.txt"
    started = time.monotonic()
    done = run_seam(
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
            str(worktree),
            "--dispatch-dir",
            str(tmp_path / "dispatches"),
        ],
        seam_env(tmp_path, capture),
    )
    elapsed = time.monotonic() - started
    assert done.returncode == 0, done.stderr
    printed = read_lines(done.stdout)
    assert printed["dispatch"].startswith("d-")
    assert dispatch.ID_ALPHABET.fullmatch(printed["dispatch"])
    assert int(printed["pid"]) > 0
    # The five-minute rule's whole point: the recipe hands back an id, it does not wait
    # for the run. Ten seconds is a ceiling on `uv run`'s cold start, not a measurement.
    assert elapsed < 10

    record = Path(printed["record"])
    assert await_file(record / "result.json"), (record / "dispatch.log").read_text(encoding="utf-8")
    result = json.loads((record / "result.json").read_text(encoding="utf-8"))
    assert result["returncode"] == 0
    assert result["dispatch_id"] == printed["dispatch"]

    ran = read_lines(capture.read_text(encoding="utf-8"))
    assert ran["cwd"] == str(worktree.resolve())
    assert "--model opus --effort high" in ran["argv"]
    assert "#223" in ran["stdin"]
    attributes = ran["OTEL_RESOURCE_ATTRIBUTES"]
    assert f"cti.dispatch_id={printed['dispatch']}" in attributes
    assert "cti.lane=claude-native" in attributes
    assert "cti.profile=opus-high" in attributes
    assert "cti.seat=implementer" in attributes
    assert "cti.issue=223" in attributes
    assert "cti.base_sha=" in attributes
    # The poisoned parent did not reach the child.
    assert "ANTHROPIC_BASE_URL" not in ran


def test_a_zai_dispatch_leaks_into_neither_the_parent_nor_the_next_lane(
    tmp_path: Path,
) -> None:
    worktree = git_worktree(tmp_path)
    credentials = credentials_file(tmp_path, f"ZAI_API_KEY={FAKE_TOKEN}\n")
    parent = seam_env(tmp_path, tmp_path / "zai-ran.txt")
    before = dict(parent)

    common = [
        "--seat",
        "review",
        "--issue",
        "223",
        "--worktree",
        str(worktree),
        "--dispatch-dir",
        str(tmp_path / "dispatches"),
        "--credentials",
        str(credentials),
    ]
    foreign = run_seam(
        ["--lane", "zai", "--profile", "zai-glm52-max", *common],
        parent,
    )
    assert foreign.returncode == 0, foreign.stderr
    foreign_record = Path(read_lines(foreign.stdout)["record"])
    assert await_file(foreign_record / "result.json")
    foreign_env = read_lines((tmp_path / "zai-ran.txt").read_text(encoding="utf-8"))
    assert foreign_env["ANTHROPIC_BASE_URL"] == "https://api.z.ai/api/anthropic"
    assert foreign_env["ANTHROPIC_AUTH_TOKEN"] == FAKE_TOKEN
    assert foreign_env["ANTHROPIC_DEFAULT_OPUS_MODEL"] == "glm-5.2"

    # The parent mapping this test handed the seam is untouched, and so is this
    # process's own environment: nothing was exported anywhere.
    assert parent == before
    assert os.environ.get("ANTHROPIC_AUTH_TOKEN") is None

    parent["CTI_FAKE_CLAUDE_OUT"] = str(tmp_path / "native-ran.txt")
    native = run_seam(
        ["--lane", "claude-native", "--profile", "sonnet-high", *common],
        parent,
    )
    assert native.returncode == 0, native.stderr
    native_record = Path(read_lines(native.stdout)["record"])
    assert await_file(native_record / "result.json")
    native_env = read_lines((tmp_path / "native-ran.txt").read_text(encoding="utf-8"))
    assert "ANTHROPIC_BASE_URL" not in native_env
    assert "ANTHROPIC_AUTH_TOKEN" not in native_env
    assert "ANTHROPIC_DEFAULT_OPUS_MODEL" not in native_env
    assert FAKE_TOKEN not in "".join(native_env.values())


def test_the_seam_forks_nothing_for_a_dry_run(tmp_path: Path) -> None:
    worktree = git_worktree(tmp_path)
    capture = tmp_path / "must-not-run.txt"
    done = run_seam(
        [
            "--dry-run",
            "--lane",
            "zai",
            "--profile",
            "zai-glm52-max",
            "--seat",
            "review",
            "--issue",
            "223",
            "--worktree",
            str(worktree),
            "--credentials",
            str(credentials_file(tmp_path, f"ZAI_API_KEY={FAKE_TOKEN}\n")),
            "--dispatch-dir",
            str(tmp_path / "dispatches"),
        ],
        seam_env(tmp_path, capture),
    )
    assert done.returncode == 0, done.stderr
    assert "pid=" not in done.stdout
    assert not capture.exists()
    assert not (tmp_path / "dispatches").exists()
    assert "env_child.ANTHROPIC_AUTH_TOKEN=<redacted>" in done.stdout
    assert FAKE_TOKEN not in done.stdout
    assert "env_stripped.ANTHROPIC_BASE_URL" not in done.stdout  # this lane sets its own


def test_the_seam_passes_a_refusal_through_without_forking(tmp_path: Path) -> None:
    done = run_seam(
        [
            "--lane",
            "zai",
            "--profile",
            "zai-glm52-max",
            "--seat",
            "fable",
            "--issue",
            "223",
            "--dispatch-dir",
            str(tmp_path / "dispatches"),
        ],
        seam_env(tmp_path, tmp_path / "must-not-run.txt"),
    )
    assert done.returncode == dispatch.EXIT_REFUSED
    assert "refusal=seat_not_eligible" in done.stderr
    assert not (tmp_path / "dispatches").exists()


# ------------------------------------------------------------------ the command surface


def test_the_justfile_carries_the_dispatch_recipe_over_the_seam() -> None:
    text = JUSTFILE.read_text(encoding="utf-8")
    assert re.search(r"^dispatch \*args:\n\s+\./tools/dispatch\.sh", text, re.MULTILINE)


def test_gitleaks_is_a_dependency_of_just_check() -> None:
    text = JUSTFILE.read_text(encoding="utf-8")
    check = next(line for line in text.splitlines() if line.startswith("check:"))
    assert "check-secrets" in check
    assert re.search(r"^check-secrets:\n(?:.*\n)*?\s+gitleaks dir \.", text, re.MULTILINE)


@pytest.mark.skipif(shutil.which("gitleaks") is None, reason="gitleaks not installed (#230)")
def test_the_secrets_gate_is_not_vacuous(tmp_path: Path) -> None:
    """A planted credential is caught, so a green `check-secrets` means something.

    The plant is derived at run time rather than written here as a literal, because a
    literal that trips gitleaks would trip it on this very file. It is deterministic —
    a digest, not a random draw — so the test cannot pass or fail by luck of entropy;
    measured at 3.79 against the rule's 3.5 threshold.
    """
    planted = tmp_path / "leak.env"
    planted.write_text(
        "ZAI_API_KEY=" + hashlib.sha256(b"cti-223-vacuity").hexdigest() + "\n",
        encoding="utf-8",
    )
    done = subprocess.run(  # noqa: S603
        [str(shutil.which("gitleaks")), "dir", str(tmp_path), "--no-banner", "--redact"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode != 0
    assert "leaks found" in (done.stdout + done.stderr)


def test_no_module_in_this_repo_exports_a_lane_variable_globally() -> None:
    """The one thing that must never happen: a lane variable set on the parent process.

    Asserted over the sources rather than at runtime, because the damage of the accident
    is that *every* Claude session on the box is redirected — including the one running
    this suite, which would then be too late to notice.
    """
    offenders: list[str] = []
    for path in (*(REPO / "tools").glob("*.py"), *(REPO / "tools").glob("*.sh")):
        text = path.read_text(encoding="utf-8")
        for key in ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN"):
            if re.search(rf"^\s*export {key}=", text, re.MULTILINE):
                offenders.append(f"{path.name}: export {key}")
            if re.search(rf"os\.environ\[[\"']{key}[\"']\]\s*=", text):
                offenders.append(f"{path.name}: os.environ[{key}] =")
    assert offenders == []


def test_the_dispatch_module_is_the_one_place_the_registry_lives() -> None:
    """No caller composes a model with an effort — that is Decision 5's whole content."""
    module: ModuleType = dispatch
    assert set(module.SEATS) >= {"implementer", "mechanical", "recon", "review", "fable"}
    assert module.SEATS["fable"] is False
    assert module.SEATS["review"] is True


# ------------------------------------------------------- the lane breaker, read first (#226)


def trip(
    tmp_path: Path, lane: str, outcome: str, count: int, reset_at: float | None = None
) -> None:
    """Stage a lane's breaker into whatever state a test needs it in."""
    store = breaker.Store(directory=tmp_path / "breaker", endpoint="http://127.0.0.1:2999/v1/logs")
    for step in range(count):
        breaker.record_outcome(
            store, lane, breaker.Outcome(outcome, reset_at=reset_at), time.time() + step
        )


def test_a_dispatch_to_a_lane_that_conducts_is_planned_as_it_always_was(tmp_path: Path) -> None:
    plan, _, refusal = plan_for(tmp_path)
    assert refusal is None
    assert plan is not None


def test_a_dispatch_to_a_quota_exhausted_lane_refuses_with_the_class_and_the_reset(
    tmp_path: Path,
) -> None:
    """The issue's first criterion, and the whole of ADR-0061 Decision 7's response."""
    reset = time.time() + 2 * 3600
    trip(tmp_path, "claude-native", breaker.QUOTA_EXHAUSTED, 1, reset_at=reset)

    plan, _, refusal = plan_for(tmp_path)
    assert plan is None
    assert refusal is not None
    assert refusal.kind == "lane_breaker_open"
    assert refusal.failure_class == "quota_exhausted"
    found = " ".join(refusal.found)
    assert "rule=quota" in found
    assert breaker.iso(reset) in found, "the wait is a published boundary, printed as one"
    assert "queue until the reset" in refusal.action
    assert "backoff" in refusal.action, "and it says explicitly that it is not one"


def test_a_dispatch_to_a_quality_tripped_lane_refuses_with_provider_refused_and_escalates(
    tmp_path: Path,
) -> None:
    trip(tmp_path, "claude-native", breaker.GATE_FAILED, 3)
    plan, _, refusal = plan_for(tmp_path)
    assert plan is None
    assert refusal is not None
    assert refusal.failure_class == "provider_refused"
    assert "just breaker reset --lane claude-native --force" in refusal.action
    assert "until=unknown" in " ".join(refusal.found)


def test_the_breaker_is_read_before_the_worktree_and_the_credentials_are(tmp_path: Path) -> None:
    """Reading the breaker first means before anything else a dispatch would check."""
    trip(tmp_path, "zai", breaker.GATE_FAILED, 3)
    _, _, refusal = plan_for(
        tmp_path,
        lane="zai",
        profile="zai-glm52-max",
        worktree=str(tmp_path / "no-such-tree"),
        credentials=str(tmp_path / "absent.env"),
    )
    assert refusal is not None
    assert refusal.kind == "lane_breaker_open", (
        "a tripped lane is the answer even when the worktree and the credential are also wrong"
    )


def test_a_lane_that_reset_while_nothing_ran_is_dispatchable_again(tmp_path: Path) -> None:
    trip(tmp_path, "claude-native", breaker.QUOTA_EXHAUSTED, 1, reset_at=time.time() - 1)
    plan, _, refusal = plan_for(tmp_path)
    assert refusal is None
    assert plan is not None, "the reader settles the window; nothing had to be running"


def test_one_lanes_trip_never_refuses_another_lanes_dispatch(tmp_path: Path) -> None:
    trip(tmp_path, "zai", breaker.GATE_FAILED, 3)
    plan, _, refusal = plan_for(tmp_path, lane="claude-native", profile="opus-high")
    assert refusal is None
    assert plan is not None


def test_a_finished_runs_log_is_classified_and_fed_back_to_its_lane(tmp_path: Path) -> None:
    """The degraded path: with no quota tap, the 429 the dispatch provoked is the feed."""
    record = tmp_path / "record"
    record.mkdir()
    (record / "dispatch.log").write_text(
        "reading CLAUDE.md\nAPI Error: 429 rate limit exceeded\n", encoding="utf-8"
    )
    outcome, reset_at = dispatch.classify_finished_run(record, 1)
    assert outcome == breaker.QUOTA_EXHAUSTED
    assert reset_at is None


def test_a_run_whose_log_says_nothing_familiar_moves_no_streak(tmp_path: Path) -> None:
    record = tmp_path / "record"
    record.mkdir()
    (record / "dispatch.log").write_text("the agent gave up on the issue\n", encoding="utf-8")
    assert dispatch.classify_finished_run(record, 1)[0] == breaker.UNCLASSIFIED
    assert dispatch.classify_finished_run(record, 0)[0] == breaker.OK


def test_a_missing_log_is_unclassified_rather_than_an_exception(tmp_path: Path) -> None:
    assert dispatch.classify_finished_run(tmp_path / "nothing", 1)[0] == breaker.UNCLASSIFIED


def test_the_seam_refuses_a_tripped_lane_before_it_forks_anything(tmp_path: Path) -> None:
    """End to end through the real `tools/dispatch.sh`: no record, no child, no id."""
    trip(tmp_path, "claude-native", breaker.GATE_FAILED, 3)
    capture = tmp_path / "capture.txt"
    done = run_seam(
        [
            "--lane",
            "claude-native",
            "--profile",
            "opus-high",
            "--seat",
            "implementer",
            "--issue",
            "226",
            "--worktree",
            str(git_worktree(tmp_path)),
            "--dispatch-dir",
            str(tmp_path / "dispatches"),
            "--credentials",
            str(tmp_path / "credentials.env"),
        ],
        seam_env(tmp_path, capture),
    )
    assert done.returncode == 1
    assert "refusal=lane_breaker_open" in done.stderr
    assert "class=provider_refused" in done.stderr
    assert "dispatch=" not in done.stdout
    assert not (tmp_path / "dispatches").exists(), "nothing was written for a run that never was"
    assert not capture.exists(), "and the runner was never reached"
