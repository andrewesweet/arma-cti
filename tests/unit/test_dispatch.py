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
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest
from conftest import REPO, load_tool

if TYPE_CHECKING:
    from types import ModuleType

dispatch = load_tool("dispatch")
breaker = load_tool("breaker")
brief = load_tool("brief")
readiness = load_tool("readiness")
routing_policy = load_tool("routing_policy")

SEAM = REPO / "tools" / "dispatch.sh"
JUSTFILE = REPO / "justfile"

# A stand-in token: distinctive enough that the tests can assert on exactly where it
# does and does not appear, and *low entropy on purpose*, because `just check` now runs
# gitleaks over this file and a realistic-looking literal here would red the gate that
# this issue added. The vacuity test below builds a high-entropy one at run time instead.
FAKE_TOKEN = "zai-" + "test-" * 6

# z.ai's published peak band is Mon-Fri 14:00-18:00 SGT (UTC+8). 2026-08-05 is a
# Wednesday, so 07:00 UTC is 15:00 SGT and inside the band, and 20:00 UTC the same day is
# 04:00 SGT on Thursday and outside it.
PEAK = datetime(2026, 8, 5, 7, 0, tzinfo=UTC)
OFF_PEAK = datetime(2026, 8, 5, 20, 0, tzinfo=UTC)

# The readiness rung (#241) reads the issue, so every test below has to say which issue
# body it is reading. #223's own body serves: it is the issue these seam tests dispatch
# against, it is vendored verbatim in the corpus the rung was measured on, and it clears
# every sub-check — so a test about environments stays a test about environments rather
# than becoming a test about GitHub being reachable from this box.
READY_BODY = REPO / "tests" / "fixtures" / "readiness-corpus" / "223.md"
ROUTING_ELIGIBLE_BODY = REPO / "tests" / "fixtures" / "routing-eligible.md"
# Same shape, scope naming a gate path: a class-6 body, kept for the classification tests.
# It stopped being a *refusing* arrangement when ADR-0073 retired that row's bar (#406).
ROUTING_ELIGIBLE_GATES_BODY = REPO / "tests" / "fixtures" / "routing-eligible-gates.md"
# Same shape again, declaring ADR authorship: the body the seam arrangement now refuses on,
# because class 3 is the row this branch does not touch (see the seam test's own docstring).
ROUTING_ELIGIBLE_ADR_BODY = REPO / "tests" / "fixtures" / "routing-eligible-adr.md"
UNREADY_BODY = "The dispatcher feels slow lately and somebody should have a look.\n"

# A review dispatch declares the profile whose work it reviews (#322), so every arrangement
# below that uses the `review` seat — several of which are really about environments,
# breakers or windows and reach for it only because it reviews — names one. It
# is a native profile on purpose: every such arrangement dispatches a z.ai profile, so the
# subject differs from the dispatched profile in both name and lane and the same-profile
# refusal is never what those tests are measuring.
REVIEWED = "opus-high"


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
    # The accident this whole design exists to prevent: a parent that already carries
    # another provider's base URL. Every child must come out the same whether or not this
    # is here.
    env["ANTHROPIC_BASE_URL"] = "https://poisoned.invalid"
    # The seam forks a real process, so its breaker has to be pointed somewhere of this
    # test's own: a run whose result depended on what this box's lanes were doing would
    # be a test of the machine rather than of the dispatcher (#226).
    env["CTI_BREAKER_DIR"] = str(tmp_path / "breaker")
    # And the same reason again for the issue body (#241): a forked seam must not reach
    # GitHub to find out whether #223 is ready, or the whole suite would be a test of this
    # box's network. `--issue-body` is the surface triage uses on a draft; here it is the
    # surface that keeps the tier offline.
    env["CTI_READINESS_BODY"] = str(ROUTING_ELIGIBLE_BODY)
    # And once more for the dispatch policy (#250). A seam run must read a policy this test
    # wrote, never this box's real freeze — and it must read *a* policy, because an absent one
    # refuses rather than reading as open. `CTI_QUEUE_ROOT` points the in-flight derivation at
    # an empty tree, so the count is this test's and not whatever is in flight on the box.
    env["CTI_QUEUE_DIR"] = str(open_policy(tmp_path))
    env["CTI_QUEUE_ROOT"] = str(tmp_path / "queue-root")
    env.update(extra)
    return env


def open_policy(tmp_path: Path, limit: int = 9, packages: list[dict] | None = None) -> Path:
    """Write a policy of this test's own: dispatch open, and a limit nothing here reaches."""
    directory = tmp_path / "queue"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "policy.json").write_text(
        json.dumps(
            {
                "version": 1,
                "freeze": {"state": "open", "since": "2026-08-06T00:00:00Z", "ruling": "a test"},
                "wip_limit": {
                    "value": limit,
                    "since": "2026-08-06T00:00:00Z",
                    "ruling": "a test",
                },
                "packages": packages or [],
            }
        ),
        encoding="utf-8",
    )
    return directory


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
    """Plan a dispatch over a real worktree without writing a record.

    `now` defaults to the clock, because the breaker rung reasons about reset times a
    test writes in real time. A `zai` test that expects to get past #238's off-peak rung
    passes an explicitly off-peak moment instead — there is no override that would let it
    do anything else, which is the point of that rung.
    """
    injected = overrides.pop("now", None)
    now = datetime.now(tz=UTC) if injected is None else injected
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
        "issue_body": str(ROUTING_ELIGIBLE_BODY),
        "queue_dir": str(open_policy(tmp_path)),
        "queue_root": str(tmp_path / "queue-root"),
        # Empty is what a non-review dispatch passes (#322), and it is also the fail-closed
        # value: a review seat reaching resolution with no declared subject refuses rather
        # than resolving to the head the implementer would have taken. The review-seat
        # arrangements below override it with `REVIEWED`.
        "reviewing": "",
        # This test's own declaration root, for `--dispatch-dir`'s reason (#402): the
        # review arrangements here must not read whatever this box has declared.
        "review_root": str(tmp_path / "review"),
    }
    request.update(overrides)
    args = _namespace(**request)
    return dispatch.plan_dispatch(args, REPO, now)


def _namespace(**fields: object) -> object:
    """Stand in for argparse's Namespace, so a test states only what it varies."""
    return type("Args", (), fields)()


# --------------------------------------------------------------------------- registry


def test_every_profile_belongs_to_a_registered_lane() -> None:
    for profile in dispatch.PROFILES.values():
        assert profile.lane in dispatch.LANES, profile.name


def test_the_registry_carries_every_landed_lane_and_a_named_profile_from_each() -> None:
    # Named exhaustively rather than counted, so that adding a lane is a deliberate edit
    # here and never an accident somewhere else. `codex` joined in #243.
    assert set(dispatch.LANES) == {"claude-native", "zai", "codex"}
    assert "opus-high" in dispatch.PROFILES
    assert "zai-glm53-max" in dispatch.PROFILES
    assert "codex-sol-xhigh" in dispatch.PROFILES


def test_the_zai_lane_carries_z_ais_published_mirror_configuration() -> None:
    lane = dispatch.LANES["zai"]
    assert lane.runner == "claude"
    assert lane.base_url == "https://api.z.ai/api/anthropic"
    assert lane.credential == "ZAI_API_KEY"
    assert dict(lane.model_slots) == {
        "ANTHROPIC_DEFAULT_OPUS_MODEL": "glm-5.3",
        "ANTHROPIC_DEFAULT_SONNET_MODEL": "glm-5.3",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": "glm-4.7",
    }


def test_the_zai_lane_registers_one_arm_per_model_and_never_one_per_effort() -> None:
    # #225's collapse, as a registry invariant rather than a comment. The endpoint
    # ignores `thinking.budget_tokens` (measured: budget 1,024 and budget 32,000 both
    # thought past 9,000 tokens and both stopped on `max_tokens` —
    # docs/research/zai-lane-live-findings.md §2), and Claude Code's five effort levels
    # differ only in the budget they send. So two profiles here must never resolve to
    # one model under two effort names: that would be two names for one configuration,
    # which is exactly what ADR-0061 Decision 5's opaque token exists to prevent.
    slots = dict(dispatch.LANES["zai"].model_slots)
    resolved = [
        slots[f"ANTHROPIC_DEFAULT_{profile.model.upper()}_MODEL"]
        for profile in dispatch.PROFILES.values()
        if profile.lane == "zai"
    ]
    assert sorted(resolved) == ["glm-4.7", "glm-5.3"]
    assert len(resolved) == len(set(resolved))


def test_every_zai_profile_selects_a_model_the_lane_actually_maps() -> None:
    # A profile whose `--model` had no slot would reach z.ai asking for `opus`, which is
    # not a model it serves. The registry is the only place this can be caught.
    slots = dict(dispatch.LANES["zai"].model_slots)
    for profile in dispatch.PROFILES.values():
        if profile.lane != "zai":
            continue
        assert f"ANTHROPIC_DEFAULT_{profile.model.upper()}_MODEL" in slots, profile.name


def test_the_zai_lane_declares_what_its_plan_meters_and_which_schedule_discounts_it() -> None:
    schedule = breaker.LANE_SCHEDULES["zai"]
    assert schedule.meter == "prompts"
    assert schedule.name == "zai-off-peak"


def test_the_published_window_has_exactly_one_home_and_the_dispatcher_reads_it() -> None:
    # #238's one-home constraint: the dispatcher restates no part of z.ai's schedule. If
    # the window moves in `tools/breaker.py`, everything the dispatcher says about it
    # moves with it — the refusal, the registry print and the priced record alike.
    body = (REPO / "tools" / "dispatch.py").read_text(encoding="utf-8")
    for restated in ("14:00", "18:00", "SGT", "UTC+8", "devpack/overview"):
        assert restated not in body, restated


def test_the_native_lane_supplies_no_credential_and_no_base_url() -> None:
    lane = dispatch.LANES["claude-native"]
    assert lane.base_url == ""
    assert lane.credential == ""


def test_an_unknown_lane_is_refused_by_name() -> None:
    # `codex` stood here as the unknown lane until #243 registered it; the claim is about
    # an unknown name, so the name moved.
    refusal = dispatch.resolve_selection("gemini", "opus-high", "implementer")
    assert refusal is not None
    assert refusal.kind == "unknown_lane"
    assert "known=claude-native codex zai" in refusal.found


def test_an_unknown_profile_is_refused_by_name() -> None:
    refusal = dispatch.resolve_selection("claude-native", "opus-turbo", "implementer")
    assert refusal is not None
    assert refusal.kind == "unknown_profile"


def test_a_profile_dispatched_on_another_lane_is_refused() -> None:
    refusal = dispatch.resolve_selection("claude-native", "zai-glm53-max", "implementer")
    assert refusal is not None
    assert refusal.kind == "profile_lane_mismatch"
    assert "profile_lane=zai" in refusal.found


def test_a_registered_selection_is_not_refused() -> None:
    assert dispatch.resolve_selection("claude-native", "opus-high", "implementer") is None
    assert dispatch.resolve_selection("zai", "zai-glm53-max", "review") is None


# ------------------------------------- ADR-0071 ruling 1: the carve-out, and nothing else
#
# Ruling 1 rescinds ADR-0061's graded eligibility ladder, so what replaced the Decision 2
# block below is one survivor and a walk. The survivor is the orchestrator carve-out;
# the walk is the proof that it is this ladder's only provenance refusal — the routing
# rung's class 6 bridge is the other lane-selected one, and lives in another table — and —
# because it crosses three providers' profiles under one seat — the proof that no verdict
# anywhere in the ladder is a function of a model or an effort token (ADR-0061 decision 5:
# a profile is one opaque token, and no cross-provider effort scale exists to infer).


def test_an_unknown_seat_is_refused_rather_than_mis_attributed() -> None:
    refusal = dispatch.resolve_selection("claude-native", "opus-high", "implemeter")
    assert refusal is not None
    assert refusal.kind == "unknown_seat"


@pytest.mark.parametrize("lane", ["codex", "zai"])
def test_the_orchestrator_carve_out_refuses_on_every_other_lane(lane: str) -> None:
    # ADR-0071 ruling 1's one survivor: orchestration runs on Claude with a Claude model
    # until a tested alternative exists. Of this ladder's refusals it is the only
    # provenance-shaped one; the routing rung holds the other lane-selected refusal, class
    # 6's bridge, one rung up and pinned in test_routing_policy.py.
    profile = "codex-sol-xhigh" if lane == "codex" else "zai-glm53-max"
    refusal = dispatch.resolve_selection(lane, profile, "orchestrator")
    assert refusal is not None
    assert refusal.kind == "orchestrator_claude_only"
    assert "ADR-0071 ruling 1" in refusal.action
    assert "claude-native" in refusal.action
    # A refusal, not a failure class — nothing was found about a provider or about code.
    assert refusal.failure_class == ""
    assert not any(line.startswith("class=") for line in refusal.lines())


def test_the_orchestrator_seat_still_dispatches_on_claude_native() -> None:
    # The carve-out names where orchestration runs; it does not retire the seat.
    assert dispatch.resolve_selection("claude-native", "opus-xhigh", "orchestrator") is None


def test_every_seat_walks_every_lane_with_the_verdict_named_for_each() -> None:
    """The carve-out is this ladder's only provenance refusal; no verdict reads a tier token.

    The routing rung's class 6 bridge is the other lane-selected refusal the project holds,
    and it lives in a different table with its own walk (review round 2, claim 3).

    Every seat in the registry against every registered profile on every lane — the
    exhaustive walk, with the expected verdict asserted for each combination rather than
    for the ones that came to mind. Three refusals exist at this rung and only these:
    `unknown_*` cannot appear (every name comes from the registries),
    `profile_lane_mismatch` cannot appear (every profile runs on its own lane), the
    carve-out fires for `orchestrator` off `claude-native`, and `pair_block` fires for
    the pairs `SEAT_PROFILE_BLOCKS` names. Anything else — `fable`, the seat Decision 2
    barred from every non-Claude lane until #327 — clears, on every provider.

    That is also the opaque-profile-token proof (ADR-0061 decision 5, surviving ruling 1):
    the walk spans `medium`/`high`/`xhigh`/`max` across three providers under one seat,
    and asserts the verdict is a function of `(seat, lane)` alone. Code that inferred a
    cross-provider ordering — the "or above" reading #300's ruling forbade — would have
    to make some `(lane, profile, seat)` verdict differ by effort token, and every
    combination's verdict is pinned here.
    """
    for lane_name, lane_profiles in _profiles_by_lane().items():
        for profile in lane_profiles:
            for seat in dispatch.SEATS:
                refusal = dispatch.resolve_selection(lane_name, profile.name, seat)
                expected = _expected_selection_refusal(lane_name, profile.name, seat)
                assert (refusal.kind if refusal else None) == expected, (
                    f"{lane_name}/{profile.name}/{seat}: {refusal}"
                )


def _profiles_by_lane() -> dict[str, list[dispatch.Profile]]:
    grouped: dict[str, list[dispatch.Profile]] = {}
    for profile in dispatch.PROFILES.values():
        grouped.setdefault(profile.lane, []).append(profile)
    return grouped


def _expected_selection_refusal(lane: str, profile: str, seat: str) -> str | None:
    """Name the refusal this ladder may return for registered names, and why each is typed."""
    if seat == "orchestrator" and lane != dispatch.CLAUDE_LANE:
        return "orchestrator_claude_only"
    if (seat, profile) in dispatch.SEAT_PROFILE_BLOCKS:
        return "profile_blocked_for_seat"
    return None


def test_the_carve_out_is_one_seats_column_not_a_rule_about_seats() -> None:
    # The walk above pins verdicts per combination; this pins the property the walk's
    # enumeration rests on, so a future seat cannot arrive outside it. `claude_only` is a
    # column the carve-out owns: one seat carries it, and the selection ladder reads no
    # other per-seat provenance. Narrowed from the round-1 reading — "no seat but
    # `orchestrator` is ever refused on provenance grounds" — which overreached this
    # ladder: the routing table refuses seats by lane on its own rung, and that walk is
    # test_routing_policy.py's (review round 2, claim 3).
    assert {seat.name for seat in dispatch.SEATS.values() if seat.claude_only} == {"orchestrator"}


def test_the_fable_seat_has_a_dispatchable_profile_on_claude_native() -> None:
    # #269: the seat drop removed the inheritance that used to supply the fable seat a
    # session. Fable acts are *dispatched* (#242 ruling 1), so the seat needs a
    # claude-native profile that runs the fable model — without one `--seat fable`
    # dispatches at whatever model some other profile names, which is the hole. Assert the
    # property, not a profile name: a rename that kept the model would still serve the seat,
    # and a removal that took it would reopen this silently. The seat has always been
    # dispatchable on claude-native (the test above); what it lacked was a profile that
    # delivers the fable model, so this is the invariant the hole broke.
    fable_profiles = [
        profile
        for profile in dispatch.PROFILES.values()
        if profile.lane == "claude-native" and profile.model == "fable"
    ]
    assert fable_profiles, (
        "the fable seat has no claude-native profile running the fable model, so a fable "
        "act cannot be dispatched at fable (#269)"
    )
    for profile in fable_profiles:
        # Registered for the model is not enough; it must clear the selection ladder for the
        # fable seat too, so a profile that exists but is refused leaves the hole open.
        assert dispatch.resolve_selection("claude-native", profile.name, "fable") is None, (
            profile.name
        )


def test_the_real_planning_path_admits_fable_on_codex(tmp_path: Path) -> None:
    # The rescission's observable end: the seat ADR-0061 Decision 2 barred from every
    # non-Claude lane plans cleanly on `codex` through the real ladder, not only through
    # `resolve_selection`. Until #327 this was the standing retro allowance's one route;
    # ruling 1 removed the bar itself, so there is no allowance left to consult.
    plan, _, refusal = plan_for(
        tmp_path,
        lane="codex",
        profile="codex-sol-xhigh",
        seat="fable",
    )
    assert refusal is None
    assert plan is not None


def test_the_carve_out_is_the_only_provenance_rule_the_registry_states() -> None:
    # One provenance rule survives, and the registry says so wherever it is read: the
    # carve-out line names the seat, and no `foreign`, allowance or approved-list line
    # remains to suggest a second one. The retro allowance's registry lines died with
    # the bar they suspended (ADR-0071 ruling 1; #326 deleted the policy half).
    lines = dispatch.registry_lines()
    assert any(line.startswith("seats_claude_only=orchestrator ") for line in lines)
    assert not any("foreign" in line for line in lines)
    assert not any(line.startswith("seat_allowance=") for line in lines)
    assert not any(line.startswith("retro_approved_profiles=") for line in lines)
    # Stated once, on the seat it reaches: a `claude_only` line on any other seat would
    # be a second provenance rule the registry had grown without a ruling.
    assert [line for line in lines if "claude_only" in line] == [
        "seats_claude_only=orchestrator (ADR-0071 ruling 1: the only provenance rule)",
        (
            "  claude_only=true refusal=orchestrator_claude_only (ADR-0071 ruling 1's"
            " one survivor, ends when a tested alternative exists)"
        ),
    ]


# ---------------------------------------------- ADR-0071: new profiles and the pair block
# Luna enters on publication — a named exception to the measure-before-building rule — and
# heads the implementer preference list. #265's gate ceiling held that pair below the seat
# until #405 lifted it, so the block list now ships empty and the mechanism is exercised
# against a staged entry. See `SEAT_PROFILE_BLOCKS` and `pair_block` in tools/dispatch.py.


def test_the_three_new_profiles_join_the_registry_under_adr_0071() -> None:
    # Luna's slug and default effort are the catalogue's own, read from the CLI's model
    # cache — not the human's shorthand. `medium` is Luna's published default effort.
    luna_max = dispatch.PROFILES["codex-luna-max"]
    assert luna_max.lane == "codex"
    assert luna_max.model == "gpt-5.6-luna"
    assert luna_max.effort == "max"
    luna_medium = dispatch.PROFILES["codex-luna-medium"]
    assert luna_medium.lane == "codex"
    assert luna_medium.model == "gpt-5.6-luna"
    assert luna_medium.effort == "medium"
    # Opus-low is the native tail of the implementer preference list.
    opus_low = dispatch.PROFILES["opus-low"]
    assert opus_low.lane == "claude-native"
    assert opus_low.model == "opus"
    assert opus_low.effort == "low"


def test_the_three_new_profiles_appear_in_the_dispatch_registry() -> None:
    # `just dispatch --list` renders `registry_lines`; a named profile that did not appear
    # there would be undispatchable in practice, however registered.
    lines = dispatch.registry_lines()
    rendered = {
        line.split("profile=", 1)[1].split()[0]: line
        for line in lines
        if line.lstrip().startswith("profile=")
    }
    assert "codex-luna-max" in rendered
    assert "codex-luna-medium" in rendered
    assert "opus-low" in rendered
    # The catalogue slug is rendered, not the human's shorthand, and `medium` is the
    # published default the entry was named for.
    assert "model=gpt-5.6-luna" in rendered["codex-luna-max"]
    assert "effort=max" in rendered["codex-luna-max"]
    assert "effort=medium" in rendered["codex-luna-medium"]


def test_codex_luna_max_takes_the_implementer_seat_now_the_ceiling_is_gone(
    tmp_path: Path,
) -> None:
    # #405: the ceiling that held this pair was #265's — a Codex session could commit or
    # gate, never both — and the division of labour lifts it, because the session runs its
    # own gate and the harness makes the commit. So the block goes, and with it the last
    # entry in the list. Asserted through selection *and* the whole planning ladder,
    # because a pair that clears one and not the other is not dispatchable in practice.
    assert dispatch.SEAT_PROFILE_BLOCKS == {}
    assert dispatch.resolve_selection("codex", "codex-luna-max", "implementer") is None
    assert dispatch.pair_block("implementer", "codex-luna-max") is None
    plan, _, refusal = plan_for(
        tmp_path,
        lane="codex",
        profile="codex-luna-max",
        seat="implementer",
    )
    assert refusal is None
    assert plan is not None


def test_a_blocked_pair_still_refuses_and_still_reaches_the_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The mechanism is ADR-0071 ruling 2's and outlives its entries, so it is tested with
    # one rather than left uncovered while the list ships empty. An entry carries its own
    # ceiling: `pair_block` states what is holding the pair, and the registry line says the
    # same thing, from the same place, so the two cannot drift apart.
    monkeypatch.setattr(dispatch, "SEAT_PROFILE_BLOCKS", {("implementer", "haiku-medium"): "#999"})
    refusal = dispatch.resolve_selection("claude-native", "haiku-medium", "implementer")
    assert refusal is not None
    assert refusal.kind == "profile_blocked_for_seat"
    # A refusal, not a failure class — nothing was found about a provider or about code.
    assert refusal.failure_class == ""
    assert not any(line.startswith("class=") for line in refusal.lines())
    assert "profile=haiku-medium" in refusal.found
    assert "seat=implementer" in refusal.found
    assert "ceiling=#999" in refusal.found
    assert "#999" in refusal.action
    # `resolve_selection` (the `--profile` path) and `pair_block` (what a seat resolver
    # calls, #321) are the same check, so a resolver consults this and not a second copy.
    assert dispatch.pair_block("implementer", "haiku-medium") == refusal
    # And the pair is stated wherever the registry is read, so a reader who paired the two
    # sees the block without attempting the dispatch.
    blocks = [line for line in dispatch.registry_lines() if line.startswith("seat_profile_block=")]
    assert blocks == [
        "seat_profile_block=adr0071 seat=implementer profile=haiku-medium ceiling=#999"
    ]


def test_the_block_list_ships_empty_so_the_registry_states_no_block() -> None:
    # The other half of the pair above: with no entry, the registry says nothing rather
    # than saying something stale about a ceiling that has been lifted.
    assert not any(line.startswith("seat_profile_block=") for line in dispatch.registry_lines())


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
        "profile": "zai-glm53-max",
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
    child = assembled("zai", "zai-glm53-max", {"HOME": "/home/t"}, FAKE_TOKEN)
    assert child["ANTHROPIC_BASE_URL"] == "https://api.z.ai/api/anthropic"
    assert child["ANTHROPIC_AUTH_TOKEN"] == FAKE_TOKEN
    assert child["ANTHROPIC_DEFAULT_OPUS_MODEL"] == "glm-5.3"


def test_the_cheap_zai_profile_reaches_the_other_glm_through_the_haiku_slot() -> None:
    child = assembled("zai", "zai-glm47-max", {"HOME": "/home/t"}, FAKE_TOKEN)
    assert child["ANTHROPIC_DEFAULT_HAIKU_MODEL"] == "glm-4.7"
    assert dispatch.PROFILES["zai-glm47-max"].model == "haiku"


@pytest.mark.parametrize(
    ("lane", "profile"), [("zai", "zai-glm53-max"), ("claude-native", "opus-high")]
)
def test_no_lane_inherits_a_cache_ttl_switch_from_the_shell(lane: str, profile: str) -> None:
    # `ENABLE_PROMPT_CACHING_1H` changes what the child asks a provider for, so it is
    # lane-owned like a base URL: a lane's behaviour must not be a property of whoever
    # dispatched it. No lane sets it — on `claude-native` a `claude -p` main session
    # already carries the one-hour TTL (#218), and on `zai` it is measured inert, since
    # prefix caching there happens identically with and without `cache_control`
    # (docs/research/zai-lane-live-findings.md §3).
    parent = {"HOME": "/home/t", "ENABLE_PROMPT_CACHING_1H": "1"}
    assert "ENABLE_PROMPT_CACHING_1H" not in assembled(lane, profile, parent, FAKE_TOKEN)


def test_a_zai_dispatch_records_the_band_it_was_charged_in() -> None:
    # Peak is Mon-Fri 14:00-18:00 SGT, so 07:00 UTC on a Wednesday is inside it and
    # 20:00 UTC the same day is 04:00 SGT on Thursday, outside. The band and its
    # multiplier are written down rather than left to be recomputed, because both are
    # functions of a published schedule that can move (#226).
    lane = dispatch.LANES["zai"]
    peak = dispatch.plan_charge(lane, datetime(2026, 8, 5, 7, 0, tzinfo=UTC))
    off_peak = dispatch.plan_charge(lane, datetime(2026, 8, 5, 20, 0, tzinfo=UTC))
    weekend = dispatch.plan_charge(lane, datetime(2026, 8, 8, 7, 0, tzinfo=UTC))
    assert peak is not None
    assert off_peak is not None
    assert weekend is not None
    assert (peak["peak"], peak["multiplier"]) == (True, 1.0)
    assert (off_peak["peak"], off_peak["multiplier"]) == (False, 0.5)
    assert (weekend["peak"], weekend["multiplier"]) == (False, 0.5)
    assert peak["meter"] == "prompts"
    assert peak["window"] == "Mon-Fri 14:00-18:00 SGT (UTC+8)"


def test_a_lane_with_no_time_of_day_term_records_no_multiplier_at_all() -> None:
    # Not 1.0. A block asserting a multiplier would read as "measured, and it was peak"
    # where the truth is that the question does not arise on this lane.
    assert dispatch.plan_charge(dispatch.LANES["claude-native"], datetime.now(tz=UTC)) is None


def test_a_zai_dispatch_with_no_token_exports_no_empty_one() -> None:
    # An empty `ANTHROPIC_AUTH_TOKEN` outranks the subscription OAuth in Claude Code's
    # credential ladder, so exporting a blank one is worse than exporting none.
    child = assembled("zai", "zai-glm53-max", {"HOME": "/home/t"}, "")
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
        "ANTHROPIC_DEFAULT_OPUS_MODEL": "glm-5.3",
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
    zai = assembled("zai", "zai-glm53-max", parent, FAKE_TOKEN)
    native = assembled("claude-native", "opus-high", parent)
    assert parent == before
    assert zai["ANTHROPIC_BASE_URL"] == "https://api.z.ai/api/anthropic"
    assert "ANTHROPIC_BASE_URL" not in native
    assert FAKE_TOKEN not in native.values()


def test_the_child_carries_its_assignment_for_anything_downstream_to_re_assert() -> None:
    child = assembled("zai", "zai-glm53-max", {"HOME": "/home/t"}, FAKE_TOKEN)
    assert child["CTI_DISPATCH_LANE"] == "zai"
    assert child["CTI_DISPATCH_SEAT"] == "review"
    assert child["CTI_DISPATCH_ISSUE"] == "223"


def test_redaction_replaces_the_token_and_leaves_everything_else_verbatim() -> None:
    child = assembled("zai", "zai-glm53-max", {"HOME": "/home/t"}, FAKE_TOKEN)
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


# --------------------------------------------------------- the Codex lane's sandbox


def _codex_argv_from_a_linked_worktree(
    tmp_path: Path, permission_mode: str, name: str = "checkout"
) -> tuple[tuple[str, ...], Path, Path]:
    """Build a Codex argv from inside a linked worktree, the arrangement dispatch uses.

    The linked worktree is the whole point: its git metadata lives under the *main*
    checkout's `.git/worktrees/`, so a sandbox rooted at the session's cwd cannot write
    it. Any assertion made against a plain repository would pass while the real
    arrangement failed, which is what dispatch `d-20260806-163129-479a57` measured.
    """
    root = git_worktree(tmp_path, name=name)
    linked = root / ".claude" / "worktrees" / "issue-259"
    add = ("worktree", "add", "-q", "--detach", str(linked))
    subprocess.run(["git", *add], cwd=root, check=True, capture_output=True)  # noqa: S603, S607
    argv = dispatch.build_argv(
        dispatch.LANES["codex"],
        dispatch.PROFILES["codex-sol-high"],
        permission_mode,
        linked,
    )
    return argv, root, linked


def _writable_roots(argv: tuple[str, ...]) -> str:
    found = [part for part in argv if part.startswith("sandbox_workspace_write.writable_roots=")]
    assert len(found) == 1, argv
    return found[0]


def test_no_git_directory_is_ever_a_codex_writable_root(tmp_path: Path) -> None:
    # #405's finding, and the one assertion that stops it regressing. Codex enforces
    # `<root>/.git` read-only inside every writable root to protect git history from the
    # agent; where the named root *is* a git directory it creates the `.git` it means to
    # protect, and libgit2 opens that empty directory instead of the real layout — which is
    # `cog check` dying on `could not find repository` and the whole of #265. Six
    # arrangements were measured and every one that named a git directory lost the gate, so
    # none is named: not the per-worktree directory, not the common one, not the main
    # checkout that contains one.
    argv, root, linked = _codex_argv_from_a_linked_worktree(tmp_path, "acceptEdits")
    roots = _writable_roots(argv)
    assert ".git" not in roots
    assert f'"{root}"' not in roots
    assert f'"{root / ".git" / "worktrees" / linked.name}"' not in roots
    # The session's own worktree is cwd, which `workspace-write` already grants; a root
    # naming it would be noise claiming to be a grant.
    assert f'"{linked}"' not in roots
    assert argv[argv.index("--sandbox") + 1] == "workspace-write"


def test_a_plain_checkout_names_no_git_directory_either(tmp_path: Path) -> None:
    # The layout is not the variable — `d-20260818-080724-50f2be` ran the same failure in a
    # standalone clone — so a plain checkout gets the same answer as a linked worktree.
    root = git_worktree(tmp_path, name="plain")
    argv = dispatch.build_argv(
        dispatch.LANES["codex"], dispatch.PROFILES["codex-sol-high"], "acceptEdits", root
    )
    assert ".git" not in _writable_roots(argv)


def test_a_cache_the_box_does_not_exercise_is_not_granted_for_being_likely(
    tmp_path: Path,
) -> None:
    # `~/.cache/ansible-lint` was granted on a derivation from ansible-lint's source and
    # dropped on review: the installed copy reports INSTALLER=uv, returns before reaching
    # the version check the derivation rested on, and the directory does not exist. A
    # grant nothing exercises is surface without evidence, so the root list names exactly
    # the two measured caches.
    argv, _root, _linked = _codex_argv_from_a_linked_worktree(tmp_path, "acceptEdits")
    assert "ansible-lint" not in _writable_roots(argv)


def test_the_writable_roots_are_exactly_the_tool_caches_the_walk_found(tmp_path: Path) -> None:
    # The root list is an assertion surface, not a discovery: every entry is a tool cache
    # a gate stage was measured red to need — `~/.cache/uv`, where `uv` locks before any
    # test runs, and `~/.ansible/tmp`, where `check-machine-b`'s syntax check writes — so
    # a future gate stage, or a future removal, changes this line and shows in the diff.
    # The whole override block is asserted, not just the roots, so a grant arriving here
    # without a root (or a root without its reason landing in `dispatch.py`) is the same
    # visible diff. Resolved, because that is what a Codex child is handed.
    argv, _root, _linked = _codex_argv_from_a_linked_worktree(tmp_path, "acceptEdits")
    home = Path.home()
    roots = (
        "sandbox_workspace_write.writable_roots="
        f'["{(home / ".cache" / "uv").resolve()}", '
        f'"{(home / ".ansible" / "tmp").resolve()}"]'
    )
    assert argv[-6:] == (
        "--config",
        roots,
        "--config",
        "sandbox_workspace_write.network_access=true",
        "--sandbox",
        "workspace-write",
    )


# -------------------------------------------------- the environment cannot reach the grant


def test_no_environment_variable_moves_a_writable_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Three review rounds found the same defect in a new place, because the grant read a
    # path from the environment and then tried to prove it safe: `UV_CACHE_DIR=/` granting
    # the whole box, a linked worktree's git directory bought through `ANSIBLE_LOCAL_TEMP`,
    # and — round three — a relative root that passed validation as canonical and was then
    # reinterpreted from the child's cwd, which is the assigned worktree. Round four
    # deletes the override, so the hostile values and the honest ones now share one answer:
    # the two home-derived constants, absolute and resolved, and no refusal to reason
    # about. A relocation this box genuinely needs is an edit to those constants.
    for variable, value in (
        ("UV_CACHE_DIR", "/"),
        ("XDG_CACHE_HOME", str(git_worktree(tmp_path, "foreign-cache"))),
        ("ANSIBLE_LOCAL_TEMP", "../../../../.cache/uv"),
        ("ANSIBLE_HOME", str(REPO / ".claude")),
    ):
        monkeypatch.setenv(variable, value)
    plan, _brief, refusal = plan_for(tmp_path, lane="codex", profile="codex-sol-high")
    assert refusal is None
    assert plan is not None
    home = Path.home()
    assert _writable_roots(plan.argv) == (
        "sandbox_workspace_write.writable_roots="
        f'["{(home / ".cache" / "uv").resolve()}", '
        f'"{(home / ".ansible" / "tmp").resolve()}"]'
    )


def test_a_home_that_will_not_canonicalise_refuses_rather_than_granting_it_unresolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The one failure left once nothing external is admitted, and the round-three review's
    # second finding: where a resolution fails, refuse — never fall back to the unresolved
    # path, which is a grant nothing has canonicalised. Asked of `Path.resolve` directly
    # because this box will not fail on demand; what is under test is the branch.
    def refuse_to_resolve(_self: Path, _strict: bool = False) -> Path:  # noqa: FBT001, FBT002 — `Path.resolve`'s own signature
        message = "too many levels of symbolic links"
        raise OSError(message)

    monkeypatch.setattr(Path, "resolve", refuse_to_resolve)
    refusal = dispatch.writable_root_refusal(tmp_path)
    assert refusal is not None
    assert refusal.kind == "writable_root_refused"
    assert "reason=the granted cache roots would not canonicalise on this box" in refusal.found


# ------------------------------------- the stale-predecessor rung is wired where it runs


@pytest.mark.parametrize(
    ("left_behind", "kind"),
    [
        ("message", "dispatch_message_present"),
        ("edits", "dirty_tree"),
    ],
)
def test_the_child_launches_nothing_over_a_tree_a_predecessor_left(
    tmp_path: Path, left_behind: str, kind: str
) -> None:
    # Review round three's Medium: the stale-predecessor rung had tests only against
    # `harness_start_refusal` itself, so nothing proved `run_dispatch`'s wiring asked it —
    # a rung asked nowhere refuses nowhere, and the predecessor's work would have ridden
    # this run's commit. These go through the record the way the detached child does, and
    # the refusal's clean exit is itself the proof nothing launched: the argv names
    # `codex`, which this box does not carry, so a launch would have died mid-run with
    # no `result.json` rather than refused with one.
    plan, brief, refusal = plan_for(tmp_path, lane="codex", profile="codex-sol-high")
    assert refusal is None
    assert plan is not None
    assert plan.argv[0] == "codex"
    dispatch.write_record(plan, brief)
    if left_behind == "message":
        (plan.worktree / dispatch.CODEX_COMMIT_MESSAGE).write_text(
            "fix(x): a predecessor's own message\n\nrefs #404\n", encoding="utf-8"
        )
    else:
        (plan.worktree / "edited.txt").write_text("someone's edit\n", encoding="utf-8")

    code, lines = dispatch.run_dispatch(plan.record, {"HOME": str(tmp_path)})
    assert code == dispatch.EXIT_REFUSED
    assert f"refusal={kind}" in lines
    # The refusal is recorded — which is what releases the worktree's occupancy — and
    # the tree is untouched, because the evidence is still evidence (#105).
    result = json.loads((plan.record / "result.json").read_text(encoding="utf-8"))
    assert result["refusal"] == kind
    assert "returncode" not in result
    if left_behind == "edits":
        assert (plan.worktree / "edited.txt").exists()
    else:
        assert (plan.worktree / dispatch.CODEX_COMMIT_MESSAGE).exists()


@pytest.mark.parametrize("mode", ["plan", "default", "somethingUnmapped"])
def test_a_read_only_codex_seat_names_no_writable_root_and_nothing_else(
    tmp_path: Path, mode: str
) -> None:
    # The read-only branch's exact answer, not just its missing roots: #415's half of the
    # gap is which caches a read-only seat is granted, and whatever that answer lands on,
    # `network_access` must not arrive with it — a reviewer needs the cache, not the
    # network. The sandbox flags are `build_argv`'s tail, so an exact tail is an exact
    # answer, and any addition here is a visible diff too.
    argv, _root, _linked = _codex_argv_from_a_linked_worktree(tmp_path, mode)
    assert argv[-2:] == ("--sandbox", "read-only")


def test_the_codex_grant_stops_at_what_was_measured_necessary(tmp_path: Path) -> None:
    # `~/.cargo` is deliberately absent: the gate ran green without it, so it goes
    # ungranted however plausible it looked. `$HOME` and `/` are the two roots that would
    # turn a widening into the bypass the human declined, and neither is here.
    argv, _root, _linked = _codex_argv_from_a_linked_worktree(tmp_path, "acceptEdits")
    roots = _writable_roots(argv)
    assert ".cargo" not in roots
    assert f'"{Path.home()}"' not in roots
    assert '"/"' not in roots


def test_a_codex_workspace_write_session_can_reach_the_network_the_gate_needs(
    tmp_path: Path,
) -> None:
    # `sandbox_workspace_write.network_access` defaults to disabled while the gate reads
    # `gh` and `uv` may fetch. This is the override with no counterpart on the `zai` lane,
    # where only the allowlisted `just land` and `gh` reach the network at all.
    argv, _root, _linked = _codex_argv_from_a_linked_worktree(tmp_path, "acceptEdits")
    assert "sandbox_workspace_write.network_access=true" in argv


@pytest.mark.parametrize("mode", ["plan", "default", "somethingUnmapped"])
def test_a_read_only_codex_seat_is_widened_by_neither_override(tmp_path: Path, mode: str) -> None:
    # A review seat has nothing to commit and nothing to land, so neither override buys
    # it anything, and a mode-by-mode mapping that widened every mode would be no mapping.
    # The unmapped mode is here because it falls through to `default`, and a fall-through
    # that landed on the wide branch would be the quietest possible way to widen every seat.
    argv, _root, _linked = _codex_argv_from_a_linked_worktree(tmp_path, mode)
    assert argv[argv.index("--sandbox") + 1] == "read-only"
    assert not [part for part in argv if part.startswith("sandbox_workspace_write.")]


def test_the_declined_bypass_flag_gains_nothing_from_the_widening(tmp_path: Path) -> None:
    # `--dangerously-bypass-approvals-and-sandbox` was put to the human on #221 and
    # declined: it disables the sandbox rather than widening it. It keeps its own
    # mapping, and the two overrides — which only mean anything to a live sandbox — stay
    # off it, so nothing here quietly makes the declined option the wider one.
    argv, _root, _linked = _codex_argv_from_a_linked_worktree(tmp_path, "bypassPermissions")
    assert "--dangerously-bypass-approvals-and-sandbox" in argv
    assert "--sandbox" not in argv
    assert not [part for part in argv if part.startswith("sandbox_workspace_write.")]


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
        issue_body=str(ROUTING_ELIGIBLE_BODY),
        queue_dir=str(open_policy(tmp_path)),
        queue_root=str(tmp_path / "queue-root"),
        reviewing="",
    )
    _, _, refusal = dispatch.plan_dispatch(args, REPO, datetime.now(tz=UTC))
    assert refusal is not None
    assert f"worktree={REPO / '.claude' / 'worktrees' / 'issue-999'}" in refusal.found


def test_the_record_names_the_credential_key_and_never_its_value(tmp_path: Path) -> None:
    credentials_file(tmp_path, f"ZAI_API_KEY={FAKE_TOKEN}\n")
    plan, brief, refusal = plan_for(
        tmp_path,
        lane="zai",
        profile="zai-glm53-max",
        seat="review",
        reviewing=REVIEWED,
        now=OFF_PEAK,
    )
    assert refusal is None
    assert plan is not None
    dispatch.write_record(plan, brief)

    document = json.loads((plan.record / "dispatch.json").read_text(encoding="utf-8"))
    assert document["credential"] == "ZAI_API_KEY"
    for path in sorted(plan.record.rglob("*")):
        if path.is_file():
            assert FAKE_TOKEN not in path.read_text(encoding="utf-8"), path
    assert FAKE_TOKEN not in " ".join(plan.argv)


def test_a_zai_record_carries_the_plan_charge_block_the_estimator_will_read(
    tmp_path: Path,
) -> None:
    credentials_file(tmp_path, f"ZAI_API_KEY={FAKE_TOKEN}\n")
    plan, brief, refusal = plan_for(
        tmp_path,
        lane="zai",
        profile="zai-glm53-max",
        seat="review",
        reviewing=REVIEWED,
        now=OFF_PEAK,
    )
    assert refusal is None
    assert plan is not None
    dispatch.write_record(plan, brief)

    document = json.loads((plan.record / "dispatch.json").read_text(encoding="utf-8"))
    charge = document["plan_charge"]
    assert charge["meter"] == "prompts"
    assert (charge["peak"], charge["multiplier"]) == (False, 0.5)
    assert charge["schedule"] == "zai-off-peak"
    assert document["planned_at"] == OFF_PEAK.isoformat()
    # The record cites the published terms rather than the module that copied them: a
    # file path stops answering "priced against what?" the moment the file moves.
    assert charge["window_source"] == "https://docs.z.ai/devpack/overview"


@pytest.mark.parametrize("moment", [PEAK, OFF_PEAK])
def test_the_record_is_stamped_with_the_injected_instant_not_the_clock(
    tmp_path: Path, moment: datetime
) -> None:
    """A caller that injects `now` is entitled to a record built from *that* instant (#341).

    The two named symptoms are time-dependent by construction — they were the four hours a
    day `just fast` was red — so they pin the day rather than the property. This pins the
    property: both instants are asserted at whatever hour the suite runs, so it is the same
    test at 07:00 and at 22:00, and a second wall-clock read added to `document()` tomorrow
    reds it on one of the two.
    """
    plan, brief, refusal = plan_for(tmp_path, now=moment)
    assert refusal is None
    assert plan is not None
    assert plan.planned_at == moment
    dispatch.write_record(plan, brief)
    document = json.loads((plan.record / "dispatch.json").read_text(encoding="utf-8"))
    assert document["planned_at"] == moment.isoformat()


@pytest.mark.parametrize(("moment", "priced"), [(PEAK, (True, 1.0)), (OFF_PEAK, (False, 0.5))])
def test_the_plan_charge_prices_the_carried_instant(
    tmp_path: Path, moment: datetime, priced: tuple[bool, float]
) -> None:
    """The priced band follows the record's own instant, not the hour it was rendered in.

    Both bands, and that is the whole discriminating force of this test (#341). One row
    alone cannot tell a `document()` that reads `self.planned_at` from one that re-reads
    the clock, because at some hour of the day the clock agrees with whichever single
    instant was substituted — off-peak for twenty hours, peak for four. With both rows
    asserted, one of them disagrees with the wall clock at every hour, so this is the same
    test at 07:00 and at 22:00. The round that dropped the peak row left the wiring pinned
    only by tests that happen to plan off-peak, which is the four-hours-a-day shape this
    issue exists to remove.

    A peak `planned_at` is reached by writing the record and substituting the field on
    disk, for one reason and not a grander one: `plan_for` refuses a peak z.ai dispatch
    (#238), so there is no other way to get a peak instant onto a record at all. Nothing
    in production re-prices a stored instant — `document()`'s only production caller is
    `write_record`, and the detached child calls `load_record` and never `document()` on
    what it gets back — which is the property `plan_charge`'s own docstring argues for,
    since a record that re-priced itself would silently restate its history the first time
    the published band moved. This route exercises the wiring; it does not imitate a
    caller.
    """
    credentials_file(tmp_path, f"ZAI_API_KEY={FAKE_TOKEN}\n")
    plan, brief, refusal = plan_for(
        tmp_path,
        lane="zai",
        profile="zai-glm53-max",
        seat="review",
        reviewing=REVIEWED,
        now=OFF_PEAK,
    )
    assert refusal is None
    assert plan is not None
    dispatch.write_record(plan, brief)
    path = plan.record / "dispatch.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["planned_at"] = moment.isoformat()
    path.write_text(json.dumps(document), encoding="utf-8")

    charge = dispatch.load_record(plan.record).document()["plan_charge"]
    assert isinstance(charge, dict)
    assert (charge["peak"], charge["multiplier"]) == priced


def test_a_native_record_carries_no_plan_charge_block(tmp_path: Path) -> None:
    plan, brief, _ = plan_for(tmp_path)
    assert plan is not None
    dispatch.write_record(plan, brief)
    document = json.loads((plan.record / "dispatch.json").read_text(encoding="utf-8"))
    assert document["plan_charge"] is None


def test_a_written_record_reads_back_as_the_same_plan(tmp_path: Path) -> None:
    plan, brief, _ = plan_for(tmp_path)
    assert plan is not None
    dispatch.write_record(plan, brief)
    assert dispatch.load_record(plan.record) == plan


def test_a_record_without_planned_at_is_an_error_not_an_invented_instant(tmp_path: Path) -> None:
    """No fallback. `planned_at` has been on every record since `dispatch.json` existed.

    The fallback this replaces preferred the field over the dispatch id, which for exactly
    the records it claimed to serve was the *less* true copy: before #341 the id came from
    the injected `now` and the field from the wall clock. Rather than reorder a preference
    over a shape that has never been written, the read is strict.
    """
    plan, brief, _ = plan_for(tmp_path)
    assert plan is not None
    dispatch.write_record(plan, brief)
    path = plan.record / "dispatch.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    del document["planned_at"]
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(KeyError):
        dispatch.load_record(plan.record)


def test_planned_at_reads_back_from_the_z_spelling(tmp_path: Path) -> None:
    # `Z` and `+00:00` are the same instant, and `datetime.fromisoformat` has read both
    # since 3.11, which this project pins past. Pinned because it is the spelling records
    # are written in when something other than this module writes them — not because it
    # discriminates between two implementations.
    plan, brief, _ = plan_for(tmp_path, now=OFF_PEAK)
    assert plan is not None
    dispatch.write_record(plan, brief)
    path = plan.record / "dispatch.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["planned_at"] = OFF_PEAK.isoformat().replace("+00:00", "Z")
    path.write_text(json.dumps(document), encoding="utf-8")

    assert dispatch.load_record(plan.record).planned_at == OFF_PEAK


@pytest.mark.parametrize(
    ("field", "value"),
    [
        # One row per way the read-back was measured to fail. The two registry rows are the
        # likely ones — profiles and lanes are retired here as a matter of routine — and
        # they were the ones that used to raise, because the lookups sat outside the guard.
        ("planned_at", "not-an-instant"),
        ("issue", {"number": 341}),
        ("argv", 7),
        ("profile", "opus-retired"),
        ("lane", "gone"),
    ],
)
def test_an_unreadable_record_refuses_rather_than_raising_into_the_detached_child(
    tmp_path: Path, field: str, value: object
) -> None:
    """The child has no caller to raise at, so it refuses with a class and records it."""
    plan, brief, _ = plan_for(tmp_path)
    assert plan is not None
    dispatch.write_record(plan, brief)
    path = plan.record / "dispatch.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document[field] = value
    path.write_text(json.dumps(document), encoding="utf-8")

    code, lines = dispatch.run_dispatch(plan.record, {"HOME": str(tmp_path)})
    assert code == dispatch.EXIT_REFUSED
    assert "refusal=dispatch_unreadable" in lines
    assert "class=infra_unavailable" in lines
    result = json.loads((plan.record / "result.json").read_text(encoding="utf-8"))
    assert result["refusal"] == "dispatch_unreadable"
    assert result["failure_class"] == "infra_unavailable"


@pytest.mark.parametrize("missing", ["dispatch.json", "brief.md"])
def test_a_record_missing_a_file_refuses_rather_than_raising(tmp_path: Path, missing: str) -> None:
    """An absent half of the record is the same condition: `OSError`, refused by name."""
    plan, brief, _ = plan_for(tmp_path)
    assert plan is not None
    dispatch.write_record(plan, brief)
    (plan.record / missing).unlink()

    code, lines = dispatch.run_dispatch(plan.record, {"HOME": str(tmp_path)})
    assert code == dispatch.EXIT_REFUSED
    assert "refusal=dispatch_unreadable" in lines
    result = json.loads((plan.record / "result.json").read_text(encoding="utf-8"))
    assert result["refusal"] == "dispatch_unreadable"


def test_a_record_directory_that_does_not_exist_refuses_and_writes_nothing(tmp_path: Path) -> None:
    """There is nowhere to leave a `result.json` when the record itself is absent.

    The refusal still reaches the caller, and nothing is created beside a path that was
    never a record — which is what the `is_dir()` guard in the refusal is for.
    """
    absent = tmp_path / "dispatches" / "d-20260813-120000-abcdef"

    code, lines = dispatch.run_dispatch(absent, {"HOME": str(tmp_path)})
    assert code == dispatch.EXIT_REFUSED
    assert "refusal=dispatch_unreadable" in lines
    assert not absent.exists()


def test_an_incomplete_request_names_what_is_missing(capsys: pytest.CaptureFixture[str]) -> None:
    code = dispatch.main(["--lane", "claude-native"])
    assert code == dispatch.EXIT_REFUSED
    printed = capsys.readouterr().err
    assert "refusal=incomplete_request" in printed
    assert "--profile" in printed
    assert "--seat" in printed
    assert "--issue" in printed


def test_the_registry_listing_names_both_lanes_and_the_carve_out(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert dispatch.main(["--list"]) == 0
    printed = capsys.readouterr().out
    assert "lane=claude-native" in printed
    assert "lane=zai" in printed
    assert "profile=zai-glm53-max" in printed
    assert "seats_claude_only=orchestrator" in printed
    assert "off_peak_only=true" in printed


# ------------------------------------------------ the off-peak rule, both ways (#238)
#
# The human's hard rule of 2026-08-05: the z.ai lane dispatches only in off-peak hours.
# Both directions are asserted, and so is the boundary, because a rule stated only in the
# direction that refuses is a rule nobody has shown ever lets anything through.


def zai_at(tmp_path: Path, now: datetime) -> tuple[Any, Any]:
    """Plan a z.ai dispatch at a chosen moment, with everything else in order."""
    credentials_file(tmp_path, f"ZAI_API_KEY={FAKE_TOKEN}\n")
    plan, _, refusal = plan_for(
        tmp_path,
        lane="zai",
        profile="zai-glm53-max",
        seat="review",
        reviewing=REVIEWED,
        now=now,
    )
    return plan, refusal


def test_a_zai_dispatch_inside_the_off_peak_window_is_planned_normally(tmp_path: Path) -> None:
    plan, refusal = zai_at(tmp_path, OFF_PEAK)
    assert refusal is None
    assert plan is not None


def test_a_zai_dispatch_in_peak_hours_is_refused_at_the_recipe(tmp_path: Path) -> None:
    plan, refusal = zai_at(tmp_path, PEAK)
    assert plan is None
    assert refusal is not None
    assert refusal.kind == "lane_peak_hours"
    found = " ".join(refusal.found)
    assert "lane=zai" in found
    assert "rule=off-peak-only" in found
    assert "band=peak" in found
    # The refusal names the window, where the window came from, and when it lifts, so a
    # refused dispatcher needs to read nothing else to know what to do.
    assert breaker.ZAI_PEAK_WINDOW in found
    assert f"window_source={breaker.ZAI_TERMS_URL}" in found
    assert f"opens={breaker.iso(breaker.zai_off_peak_opens_at(PEAK.timestamp()))}" in found
    assert "in=3h" in found, "15:00 SGT is three hours short of the band's end"


def test_the_peak_refusal_carries_no_failure_class(tmp_path: Path) -> None:
    # CLAUDE.md's table types what a run found, and this one found nothing: the provider
    # is up, the credential is good, and this project chose not to spend on the lane now.
    # `infra_unavailable` would assert an outage that is not happening, and a wrong class
    # is a harness bug by that table's own rule. The readiness refusal carries none for
    # the same reason.
    _, refusal = zai_at(tmp_path, PEAK)
    assert refusal is not None
    assert refusal.failure_class == ""
    assert "class=" not in " ".join(refusal.lines())


@pytest.mark.parametrize(
    ("hour", "minute", "second", "refused"),
    [
        (13, 59, 59, False),  # one second before the band opens
        (14, 0, 0, True),  # the band is closed at its lower bound
        (17, 59, 59, True),  # and stays closed to the last second
        (18, 0, 0, False),  # and reopens exactly on its upper bound
    ],
)
def test_the_band_is_half_open_at_both_of_its_boundaries(
    tmp_path: Path, hour: int, minute: int, second: int, *, refused: bool
) -> None:
    """The reading taken on #238, stated rather than guessed: peak is [14:00, 18:00) SGT.

    z.ai publishes "14:00-18:00" and says nothing about its endpoints. A closed upper
    bound would put one second of every weekday in both bands, which is the only reading
    that cannot be implemented, so the band is half-open — and that choice is flagged on
    #221 rather than left to be rediscovered from this test.
    """
    # SGT is UTC+8 with no daylight saving, so the UTC hour is the SGT hour less eight.
    at = datetime(2026, 8, 5, hour - 8, minute, second, tzinfo=UTC)
    _, refusal = zai_at(tmp_path, at)
    assert (refusal is not None) is refused


def test_a_weekend_dispatches_at_any_hour_the_band_would_otherwise_cover(
    tmp_path: Path,
) -> None:
    # 2026-08-08 is a Saturday. The band is Mon-Fri, so its hours mean nothing here.
    plan, refusal = zai_at(tmp_path, datetime(2026, 8, 8, 7, 0, tzinfo=UTC))
    assert refusal is None
    assert plan is not None


def test_the_rule_binds_the_lane_and_never_the_hour(tmp_path: Path) -> None:
    # `claude-native` carries no ruling, so peak hours are nothing to it.
    plan, _, refusal = plan_for(tmp_path, now=PEAK)
    assert refusal is None
    assert plan is not None


def test_every_profile_on_a_ruled_lane_is_refused_and_not_merely_the_named_one(
    tmp_path: Path,
) -> None:
    # The ruling is the human's on the lane; a second profile is not a second opinion.
    credentials_file(tmp_path, f"ZAI_API_KEY={FAKE_TOKEN}\n")
    worktree = git_worktree(tmp_path)
    for profile in ("zai-glm53-max", "zai-glm47-max"):
        _, _, refusal = plan_for(
            tmp_path,
            lane="zai",
            profile=profile,
            seat="review",
            reviewing=REVIEWED,
            worktree=str(worktree),
            now=PEAK,
        )
        assert refusal is not None, profile
        assert refusal.kind == "lane_peak_hours", profile


def test_the_window_is_read_before_the_worktree_and_the_credentials_are(tmp_path: Path) -> None:
    """A refused lane is the answer even when everything after it is also wrong."""
    _, _, refusal = plan_for(
        tmp_path,
        lane="zai",
        profile="zai-glm53-max",
        seat="review",
        reviewing=REVIEWED,
        worktree=str(tmp_path / "no-such-tree"),
        credentials=str(tmp_path / "absent.env"),
        now=PEAK,
    )
    assert refusal is not None
    assert refusal.kind == "lane_peak_hours"


def test_a_tripped_breaker_outranks_the_window_because_it_lasts_longer(tmp_path: Path) -> None:
    """The ladder's stated ordering: the refusal that lasts longest is heard first.

    A quality trip reopens only when a human runs the reset; peak hours reopen on a clock
    within four hours and need nobody. Telling a dispatcher about the clock would send it
    back at 18:00 SGT to meet the trip it was never told about.
    """
    trip(tmp_path, "zai", breaker.GATE_FAILED, 3)
    _, refusal = zai_at(tmp_path, PEAK)
    assert refusal is not None
    assert refusal.kind == "lane_breaker_open"


# ------------------------------------------------------------------ readiness (#241)


def unready(tmp_path: Path, text: str = UNREADY_BODY) -> str:
    """Write an issue body that states no criteria, and return its path."""
    path = tmp_path / "unready.md"
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_an_issue_that_states_no_criteria_refuses_the_dispatch(tmp_path: Path) -> None:
    _, _, refusal = plan_for(tmp_path, issue_body=unready(tmp_path))
    assert refusal is not None
    assert refusal.kind == "issue_not_ready"
    assert any("criteria_absent" in line for line in refusal.found)


def test_the_readiness_refusal_carries_no_failure_class(tmp_path: Path) -> None:
    """A readiness refusal is not a verdict about any code.

    The provider is up, the lane is reachable, and the table types what a run found. This
    found nothing about any code under test — `off_peak_refusal`'s reasoning exactly.
    """
    _, _, refusal = plan_for(tmp_path, issue_body=unready(tmp_path))
    assert refusal is not None
    assert refusal.failure_class == ""


def test_the_remedy_is_an_issue_edit_by_a_person_and_never_a_rewrite(tmp_path: Path) -> None:
    """#241's third requirement, asserted on the only surface an agent reads."""
    _, _, refusal = plan_for(tmp_path, issue_body=unready(tmp_path))
    assert refusal is not None
    assert "edit to the issue" in refusal.action
    assert "human or by triage" in refusal.action
    assert "rewrite the issue for you" in refusal.action


def test_the_rung_is_lane_blind(tmp_path: Path) -> None:
    """Every lane and profile meets the same refusal on the same body — ADR-0061's rule."""
    worktree = git_worktree(tmp_path)
    body = unready(tmp_path)
    for profile in dispatch.PROFILES.values():
        # A profile blocked for this seat at selection never reaches the readiness rung, so
        # it cannot testify about the rung's lane-blindness. `codex-luna-max` is blocked for
        # `implementer` by #265's ceiling (ADR-0071 ruling 2); it is skipped for that reason,
        # not for any lane's treatment of readiness.
        if dispatch.pair_block("implementer", profile.name) is not None:
            continue
        _, _, refusal = plan_for(
            tmp_path,
            lane=profile.lane,
            profile=profile.name,
            seat="implementer",
            worktree=str(worktree),
            issue_body=body,
            now=OFF_PEAK,
        )
        assert refusal is not None, profile.name
        assert refusal.kind == "issue_not_ready", profile.name


def test_no_option_on_this_surface_waives_the_readiness_rung() -> None:
    """The remedy is an edit, so a flag that skipped the check would be the remedy's rival."""
    for flag in ("--skip-readiness", "--no-readiness", "--ready", "--force-ready"):
        with pytest.raises(SystemExit):
            dispatch.parse_args([flag])


def test_an_unreadable_issue_refuses_rather_than_passing(tmp_path: Path) -> None:
    """#41: a check that could not run is not a check that passed."""
    _, _, refusal = plan_for(tmp_path, issue_body=str(tmp_path / "no-such-body.md"))
    assert refusal is not None
    assert refusal.kind == "issue_unreadable"
    assert refusal.failure_class == "infra_unavailable"


def test_an_empty_body_file_is_unreadable_rather_than_unready(tmp_path: Path) -> None:
    blank = tmp_path / "blank.md"
    blank.write_text("\n", encoding="utf-8")
    _, _, refusal = plan_for(tmp_path, issue_body=str(blank))
    assert refusal is not None
    assert refusal.kind == "issue_unreadable"


def test_readiness_outranks_the_breaker_and_the_window(tmp_path: Path) -> None:
    """The ladder's ordering: no clock and no provider will ever clear an unready issue.

    Every rung below this one is arranged to refuse as well — the lane's breaker is tripped
    and the clock is inside the peak band — and the answer is still the one whose remedy a
    person can start on now. The admission rung was arranged here too until #328 dropped
    the bar; there is no longer a rung between readiness and the breaker.
    """
    trip(tmp_path, "zai", breaker.GATE_FAILED, 3)
    _, _, refusal = plan_for(
        tmp_path,
        lane="zai",
        profile="zai-glm53-max",
        seat="review",
        reviewing=REVIEWED,
        issue_body=unready(tmp_path),
        now=PEAK,
    )
    assert refusal is not None
    assert refusal.kind == "issue_not_ready"


def test_a_typo_in_the_request_still_outranks_readiness(tmp_path: Path) -> None:
    """The registry keeps its place: a typo is not a state of the world at all."""
    _, _, refusal = plan_for(tmp_path, lane="nosuchlane", issue_body=unready(tmp_path))
    assert refusal is not None
    assert refusal.kind == "unknown_lane"


def test_an_unenumerable_issue_dispatches_and_says_so(tmp_path: Path) -> None:
    """The measured half of the split: 15% of the corpus, so it advises and never refuses."""
    ruling = tmp_path / "ruling.md"
    ruling.write_text(
        "Human ruling, 2026-08-05: the lane dispatches only off-peak.\n\n"
        "Build: a rung that refuses outside the window. Tests both directions.\n",
        encoding="utf-8",
    )
    plan, _, refusal = plan_for(tmp_path, issue_body=str(ruling))
    assert refusal is None
    assert plan is not None
    assert plan.advisories == (
        "advisory=criteria_not_enumerable issue=223 units=0 needed=2 leads=build,test",
    )


def test_an_advisory_is_kept_on_the_dispatch_record(tmp_path: Path) -> None:
    """An advisory is kept, not only printed.

    One nobody kept cannot be counted, and counting them is how the enumerability sub-check
    would ever earn a hard refusal.
    """
    ruling = tmp_path / "ruling.md"
    ruling.write_text("Fix per the close: record cap_fraction in tools/ledger.py.\n", "utf-8")
    plan, brief, refusal = plan_for(tmp_path, issue_body=str(ruling))
    assert refusal is None
    assert plan is not None
    dispatch.write_record(plan, brief)
    document = json.loads((plan.record / "dispatch.json").read_text(encoding="utf-8"))
    assert document["readiness_advisories"] == list(plan.advisories)
    assert dispatch.load_record(plan.record).advisories == plan.advisories


def test_a_ready_issue_leaves_no_advisory_behind(tmp_path: Path) -> None:
    plan, _, refusal = plan_for(tmp_path)
    assert refusal is None
    assert plan is not None
    assert plan.advisories == ()


def test_the_audit_mode_answers_without_dispatching(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Triage's surface: the same verdict a dispatch would meet, before one is armed.

    It names no lane, no profile and no seat — there is nothing lane-shaped to name — and
    a request that would be `incomplete_request` on the dispatch path is a complete
    question here.
    """
    code = dispatch.main(["--readiness", "--issue", "241", "--issue-body", unready(tmp_path)])
    assert code == dispatch.EXIT_REFUSED
    printed = capsys.readouterr()
    assert "refusal=issue_not_ready" in printed.err
    assert "dispatch=" not in printed.out


def test_the_audit_mode_clears_a_ready_issue(capsys: pytest.CaptureFixture[str]) -> None:
    assert dispatch.main(["--readiness", "--issue", "223", "--issue-body", str(READY_BODY)]) == 0
    assert "readiness=ready issue=223" in capsys.readouterr().out


def test_the_audit_mode_needs_an_issue_or_a_body() -> None:
    assert dispatch.main(["--readiness"]) == dispatch.EXIT_REFUSED


def test_a_lane_ruled_off_peak_only_with_no_registered_window_fails_closed() -> None:
    # A rule that cannot be evaluated must not be assumed satisfied. `nowhere` is in no
    # schedule table, so the only safe answer is to refuse and name the registry bug.
    orphan = dispatch.LANES["zai"]._replace(name="nowhere")
    refusal = dispatch.off_peak_refusal(orphan, OFF_PEAK)
    assert refusal is not None
    assert refusal.kind == "off_peak_window_unknown"
    assert "tools/breaker.py" in refusal.action


def test_no_option_on_this_surface_moves_the_clock_or_waives_the_rule() -> None:
    """#238's no-override requirement, asserted where an override would have to appear.

    The rule is the human's, so the dispatcher exposes nothing that could set it aside.
    `--breaker-dir` exists because a forked seam test needs its own
    state; a clock does not have that problem, and a flag that moved it would be the
    override this issue forbids under a duller name.
    """
    for flag in ("--now", "--at", "--peak", "--off-peak", "--force", "--override", "--any-hour"):
        with pytest.raises(SystemExit):
            dispatch.parse_args([flag, "1"])


def test_the_clock_the_rule_is_judged_against_is_the_real_one(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """And the caller cannot supply it: `main` reads the clock and passes what it read."""
    seen: list[datetime] = []

    def capture(_args: object, _root: Path, now: datetime) -> tuple[None, str, Any]:
        seen.append(now)
        return None, "", dispatch.Refusal("stop", (), "")

    monkeypatch.setattr(dispatch, "plan_dispatch", capture)
    dispatch.main(
        [
            "--lane",
            "zai",
            "--profile",
            "zai-glm53-max",
            "--seat",
            "review",
            "--reviewing",
            REVIEWED,
            "--issue",
            "238",
            "--dispatch-dir",
            str(tmp_path / "dispatches"),
        ]
    )
    assert len(seen) == 1
    assert seen[0].tzinfo is not None, "a naive clock would read the band in the box's timezone"
    assert abs((seen[0] - datetime.now(tz=UTC)).total_seconds()) < 5


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


def test_the_child_refuses_a_worktree_that_has_been_removed(tmp_path: Path) -> None:
    """The likeliest shape of all: `just worktree done` ran, and the record outlived the tree.

    `plan.worktree` comes off the record, so a record naming a tree this box no longer has
    reaches the child intact and only fails at `subprocess.run(cwd=…)` — which used to
    raise `FileNotFoundError` before git ran, writing no `result.json` and leaving the
    ledger and `occupancy` with a dispatch that started and never ended. It must be a
    named refusal with a class instead, and specifically `worktree_unreadable`, whose own
    docstring names this case and which nothing could previously reach it by.
    """
    plan, brief, _ = plan_for(tmp_path)
    assert plan is not None
    dispatch.write_record(plan, brief)
    shutil.rmtree(plan.worktree)

    code, lines = dispatch.run_dispatch(plan.record, {"HOME": str(tmp_path)})
    assert code == dispatch.EXIT_REFUSED
    assert "refusal=worktree_unreadable" in lines
    assert "class=infra_unavailable" in lines
    result = json.loads((plan.record / "result.json").read_text(encoding="utf-8"))
    assert result["refusal"] == "worktree_unreadable"
    assert result["failure_class"] == "infra_unavailable"
    # The end-state the raise used to deny the ledger: an `ended_at` and no `returncode`,
    # which is how `type_end_state` tells a refused dispatch from a live one.
    assert "ended_at" in result
    assert "returncode" not in result


def test_git_answers_nothing_when_it_cannot_be_run_at_all(tmp_path: Path) -> None:
    """An absent `cwd` is git giving no answer, not an exception for a caller to catch.

    Both halves of "no answer" collapse to the empty string, and this pins the half that
    never starts the process; `test_a_path_git_cannot_read_is_infra_unavailable` covers
    what the callers then do with it.
    """
    assert dispatch.git("rev-parse", "--show-toplevel", cwd=tmp_path / "never-created") == ""


def test_the_zai_lane_refuses_at_the_recipe_while_its_key_does_not_exist(
    tmp_path: Path,
) -> None:
    """Week one's z.ai shape: the lane is registered and cannot be exercised (#229)."""
    plan, _, refusal = plan_for(
        tmp_path,
        lane="zai",
        profile="zai-glm53-max",
        seat="review",
        reviewing=REVIEWED,
        credentials=str(tmp_path / "absent.env"),
        now=OFF_PEAK,
    )
    assert plan is None
    assert refusal is not None
    assert refusal.kind == "credentials_missing"
    assert refusal.failure_class == "infra_unavailable"


def test_the_child_re_checks_the_credential_the_plan_already_checked(tmp_path: Path) -> None:
    """Defence in depth: the file can go between the plan and the launch."""
    credentials = credentials_file(tmp_path, f"ZAI_API_KEY={FAKE_TOKEN}\n")
    plan, brief, _ = plan_for(
        tmp_path,
        lane="zai",
        profile="zai-glm53-max",
        seat="review",
        reviewing=REVIEWED,
        now=OFF_PEAK,
    )
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
    # No pid is published, and what replaces it is the handle that identifies the work
    # (#308). The seam's `$child` is the launcher; the session reparents away from it, so
    # a caller checking `ps -p <that pid>` learns nothing about whether the dispatch is
    # still running — which is precisely how #105's sixth instance happened.
    assert "pid" not in printed
    assert printed["stop"] == f"just dispatch --stop {printed['dispatch']}"
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
    # Snapshotted rather than asserted absent, because this suite now runs *inside* zai
    # dispatches. See the assertion below for why that is a stronger claim and not a
    # weaker one.
    own_environment_before = dict(os.environ)

    common = [
        "--seat",
        "review",
        "--reviewing",
        REVIEWED,
        "--issue",
        "223",
        "--worktree",
        str(worktree),
        "--dispatch-dir",
        str(tmp_path / "dispatches"),
        "--credentials",
        str(credentials),
    ]
    before_band = breaker.zai_is_peak(time.time())
    zai_run = run_seam(
        ["--lane", "zai", "--profile", "zai-glm53-max", *common],
        parent,
    )
    if before_band != breaker.zai_is_peak(time.time()):
        pytest.skip("the run straddled z.ai's band boundary; neither outcome is the claim")
    if before_band:
        # #238's rule is running and there is deliberately no clock override that would
        # let a test dispatch through it, so the claim available in this band is the rule
        # itself, asserted through the same real seam.
        assert zai_run.returncode == dispatch.EXIT_REFUSED
        assert "refusal=lane_peak_hours" in zai_run.stderr
        assert not (tmp_path / "zai-ran.txt").exists(), "and the runner was never reached"
        assert parent == before
        return
    assert zai_run.returncode == 0, zai_run.stderr
    zai_record = Path(read_lines(zai_run.stdout)["record"])
    assert await_file(zai_record / "result.json")
    zai_env = read_lines((tmp_path / "zai-ran.txt").read_text(encoding="utf-8"))
    assert zai_env["ANTHROPIC_BASE_URL"] == "https://api.z.ai/api/anthropic"
    assert zai_env["ANTHROPIC_AUTH_TOKEN"] == FAKE_TOKEN
    assert zai_env["ANTHROPIC_DEFAULT_OPUS_MODEL"] == "glm-5.3"

    # The parent mapping this test handed the seam is untouched, and so is this
    # process's own environment: nothing was exported anywhere.
    assert parent == before
    # This used to read `os.environ.get("ANTHROPIC_AUTH_TOKEN") is None`, which asserted a
    # *precondition of the box* rather than anything the seam did. #259 made that
    # unrunnable and found it: once a dispatched session can run the gate, `just fast`
    # executes inside a `zai` dispatch, whose own credential the dispatcher legitimately
    # put in the environment before pytest started — so the suite red on the ambient value
    # `4ec07bbe…` while the seam had exported nothing at all (dispatch
    # `d-20260806-163123-e8bed7`). Equality is the claim that was always wanted, it holds
    # in both arrangements, and it is strictly stronger: on a clean box "unchanged from
    # clean" implies "absent", and it also catches an export of any *other* variable that
    # the old single-key check would have missed.
    assert os.environ == own_environment_before
    # And the lane's credential specifically never reaches this process under any name.
    assert FAKE_TOKEN not in "".join(os.environ.values())

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
    before_band = breaker.zai_is_peak(time.time())
    done = run_seam(
        [
            "--dry-run",
            "--lane",
            "zai",
            "--profile",
            "zai-glm53-max",
            "--seat",
            "review",
            "--reviewing",
            REVIEWED,
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
    if before_band != breaker.zai_is_peak(time.time()):
        pytest.skip("the run straddled z.ai's band boundary; neither outcome is the claim")

    # True in either band: nothing forked, nothing written, and no token in the output.
    assert "pid=" not in done.stdout
    assert not capture.exists()
    assert not (tmp_path / "dispatches").exists()
    assert FAKE_TOKEN not in done.stdout + done.stderr

    if before_band:
        # A dry run is refused too. #238's rule takes no exemption for a rehearsal, and
        # a printed plan for a dispatch that would be refused is a plan that misleads.
        assert done.returncode == dispatch.EXIT_REFUSED
        assert "refusal=lane_peak_hours" in done.stderr
        return
    assert done.returncode == 0, done.stderr
    assert "env_child.ANTHROPIC_AUTH_TOKEN=<redacted>" in done.stdout
    assert "env_stripped.ANTHROPIC_BASE_URL" not in done.stdout  # this lane sets its own


def test_the_seam_passes_a_refusal_through_without_forking(tmp_path: Path) -> None:
    """A routing refusal reaches the caller's stderr and nothing forks.

    The arrangement is on class 3, and which class it is on is load-bearing. This test runs
    the **real seam**, so `tools/dispatch.py` reads the routing policy from
    `main_checkout(Path.cwd())` — the parent checkout, not this worktree — and every other
    box dependency in `seam_env` has an override for exactly that reason while the policy has
    none. So an assertion here on a row the branch under test is *editing* is answered by the
    landed policy and is green for the wrong reason: this test asserted the old
    `3:retros_and_adr_authorship`, stayed green through five in-worktree gates, and was red the
    moment #326 reached `origin/main` (review round 1 claim 1). The blindness itself is #364's;
    what belongs here is an arrangement that does not depend on it, which means a row the
    branch under test does not edit.

    **Class 6 was that arrangement and is not any more, and its going is the rule working
    rather than failing** (ADR-0073, #406). It was chosen because it had refused this route
    identically under every policy the window had shipped — and that reasoning holds only in
    the context it was tested, which the human's instruction of 2026-08-18 ended by retiring
    the row's bar. A branch editing class 6 therefore has to move this pair, and moving it
    *before* landing is the point: the assertion would otherwise be answered by the landed
    policy, stay green through every in-worktree gate, and red on `origin/main` — #364's
    blindness in exactly the shape review round 1 claim 1 found it.

    Class 3 is the replacement, and the property that qualifies it is durability, not
    strength: `adr_authorship` refuses `retro` on every lane, has refused it under every
    vintage since #326 founded the row on its seats, and is untouched by the branch that
    moved this pair. Class 2 was the arrangement until #327's second round re-founded it, and
    stays former because class 2 is the row routing issues keep re-founding (#326 re-founded
    it; #327 founded it anew and widened it), so a pair riding it rides the next change. The
    reason lives here on the record rather than in a commit message, which is class 3's own
    remedy's rule (`config/dispatch-routing-policy.json`), so a successor who wants an older
    arrangement back meets why it left (#327 review round 3, claim 5).
    """
    done = run_seam(
        [
            "--lane",
            "zai",
            "--profile",
            "zai-glm53-max",
            "--seat",
            "retro",
            "--issue",
            "223",
            "--dispatch-dir",
            str(tmp_path / "dispatches"),
        ],
        seam_env(
            tmp_path,
            tmp_path / "must-not-run.txt",
            CTI_READINESS_BODY=str(ROUTING_ELIGIBLE_ADR_BODY),
        ),
    )
    assert done.returncode == dispatch.EXIT_REFUSED
    assert "refusal=routing_policy_advisory" in done.stderr
    assert "routing_class=3:adr_authorship" in done.stderr
    assert not (tmp_path / "dispatches").exists()


def _routing_args(*, lane: str = "zai", seat: str = "implementer") -> Any:  # noqa: ANN401
    return SimpleNamespace(lane=lane, profile="zai-glm53-max", seat=seat)


def test_the_cleared_dispatcher_is_told_what_the_clear_read_did_not_check() -> None:
    """Round 2 claim 5: round 1's own argument, applied on the rung it was not.

    Since #326 dispatch is the **only** rung that checks the seat-bound classes — 2 and 3, a
    landing has no seat — so a dispatcher cleared here is cleared by the one check that
    could have caught an ADR or an orchestration issue taken by an unadmitted seat, and
    heard nothing at all about what the table does not cover.
    """
    lines = dispatch.routing_clearance(
        _routing_args(), REPO, dispatch.Readiness(None, body="Something unclassified."), OFF_PEAK
    )
    read = routing_policy.read_policy(REPO / routing_policy.POLICY_RELATIVE)
    assert read.policy is not None
    assert any(line.startswith("routing=clear check=advisory issue declaration") for line in lines)
    assert f"coverage={read.policy.coverage}" in lines


def test_an_excepted_route_is_told_it_was_excepted_rather_than_cleared(tmp_path: Path) -> None:
    """#326 review round 3, claim 2: `advisory_match` returns `None` for two different facts.

    "No row matched" and "a row matched and an exception lifted it" both reached this rung as
    `routing=clear`, which reads as "no class applies to this route". The truth in the second
    case is that a class applies and a standing human allowance lifted it — the same
    "exempted is not cleared" distinction the landing rung was fixed for in #326 round 2, claim 6.
    Planted, because `route_exceptions` is empty today and the shape is fixed by rule rather
    than by nobody having written that row yet: the exception below is exactly the class-3
    route exception `origin/main` carried until this branch emptied the list.
    """
    document = json.loads((REPO / routing_policy.POLICY_RELATIVE).read_text(encoding="utf-8"))
    document[routing_policy.REFOUNDED.route_exceptions] = [
        {
            "class": 3,
            "lane": "codex",
            "profile": "codex-sol-xhigh",
            "seat": "retro",
            "standing": True,
        }
    ]
    root = tmp_path
    (root / routing_policy.POLICY_RELATIVE.parent).mkdir(parents=True)
    (root / routing_policy.POLICY_RELATIVE).write_text(json.dumps(document), encoding="utf-8")

    args = SimpleNamespace(lane="codex", profile="codex-sol-xhigh", seat="retro")
    found = dispatch.Readiness(None, body="ADR authorship for #999.")
    # The route really is unrefused — the exception did lift it — which is what makes the
    # difference between this line and `routing=clear` a difference about the same route.
    assert dispatch.routing_refusal(args, found, root, OFF_PEAK) is None
    lines = dispatch.routing_clearance(args, root, found, OFF_PEAK)
    assert any(line.startswith("routing=excepted check=advisory") for line in lines)
    assert "routing_class=3:adr_authorship" in lines
    assert any("an exception in the policy lifted" in line for line in lines)
    assert not any(line.startswith("routing=clear") for line in lines)


def test_the_unreadable_policy_fallback_on_claude_says_it_is_a_hole(tmp_path: Path) -> None:
    """#326 review round 2, claim 7: the bootstrap still holds, and now it stops being silent.

    The Claude lane dispatches on an unreadable policy so the policy can be repaired on
    Claude. Before #326 that cost nothing — Claude was exempt from every row anyway — but
    classes 2 and 3 are lane-blind, so the fallback silently reverses both rows made to bind
    Claude.
    """
    args = _routing_args(lane="claude-native")
    lines = dispatch.routing_clearance(args, tmp_path, dispatch.Readiness(None, body=""), OFF_PEAK)
    assert "routing=not_checked reason=policy_unreadable" in lines
    assert any(line.startswith("policy=") for line in lines)
    assert any("escapes through it unchecked" in line for line in lines)
    # And the route really is unrefused, which is what makes the line worth printing.
    assert (
        dispatch.routing_refusal(args, dispatch.Readiness(None, body=""), tmp_path, OFF_PEAK)
        is None
    )


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
    assert set(module.SEATS) >= {"implementer", "recon", "review", "fable"}
    # Ruling 1 deleted the eligibility column; what replaced it names one seat, and the
    # walk above proves no other seat is refused on provenance grounds anywhere.
    assert [name for name, seat in module.SEATS.items() if seat.claude_only] == ["orchestrator"]
    # ADR-0071 ruling 2 retires `mechanical`: it named a cheaper tier rather than a
    # different job, and the registry is the enforcing copy of the roster.
    assert "mechanical" not in module.SEATS


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
        profile="zai-glm53-max",
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


def test_no_dispatch_is_refused_by_an_admission_verdict(tmp_path: Path) -> None:
    """#328's first criterion, asserted where it can be seen: the rung is gone, not permissive.

    A permissive rung and an absent one look the same from a green dispatch, so this asserts
    the absence directly — the dispatcher exposes no admission refusal, names no admission
    store, and offers no flag pointing at one. The bar was pre-registered so that observed
    behaviour could not move it and was then dropped without ever adjudicating, which is a
    departure recorded in ADR-0071 ruling 6 and in `tools/trial.py`'s header.
    """
    assert not hasattr(dispatch, "admission_refusal")
    assert not hasattr(dispatch, "admission")
    with pytest.raises(SystemExit):
        dispatch.parse_args(["--admission-dir", str(tmp_path), "--lane", "zai"])


# -------------------------------------------------------------------- the pre-work strata (#323)
#
# The observatory compares profiles, and assignment is not random, so the record carries
# signals knowable *before* the seat starts work — gate tier, routing class, labels —
# never outcomes. Each carries #322's checked flag beside its value: a confident value
# standing alone cannot tell 'the issue has none' from 'nobody could look', and reading
# the two the same is the stratification error #323 was filed to prevent. The tests below
# pin that distinction for each signal; the ones a reviewer should weigh most carefully
# are the absent-versus-unchecked pairs, where a weakened assertion would let a collapse
# through green.

# Bodies that name a surface without depending on any fixture's prose. Each is a path the
# real CONTEXT.md vocabulary and the real routing policy judge, so the assertions pin what
# those authorities actually return rather than a paraphrase of them.
IN_WORLD_BODY = "Implement the change in `addons/main/fn_foo.sqf` and its test.\n"
NON_WORLD_BODY = "Implement the change in `tools/dispatch.py` and its test.\n"
NO_CLASS_BODY = "Implement the change in `tools/worker.py` and its test.\n"
NO_PATH_BODY = "A change to the README prose only, naming no path.\n"


def test_strata_records_an_in_world_issue_as_regress_with_its_class() -> None:
    s = dispatch.capture_strata(IN_WORLD_BODY, 323, REPO, body_from_file=True)
    assert s.gate_tier == dispatch.Stratum.known("regress")
    # Lane-blind: a Claude-native dispatch carries the same class any other lane would. The
    # stable id and the mutable name are kept as two fields, not one `id:name` string.
    assert s.routing_class == dispatch.Stratum.known(
        dispatch.RoutingClass("5", "in_world_landings"),
    )


def test_strata_records_a_non_world_issue_as_fast() -> None:
    s = dispatch.capture_strata(NON_WORLD_BODY, 323, REPO, body_from_file=True)
    assert s.gate_tier == dispatch.Stratum.known("fast")
    # Non-world is about the gate tier, not the routing class: this body is fast *and*
    # carries a class, which is the combination that proves the two signals are independent.
    assert s.routing_class == dispatch.Stratum.known(
        dispatch.RoutingClass("6", "gates_themselves"),
    )


def test_strata_records_no_routing_class_as_a_checked_absence() -> None:
    s = dispatch.capture_strata(NO_CLASS_BODY, 323, REPO, body_from_file=True)
    # No class is RoutingClass("", "") and it is checked: we looked, and the issue declares
    # none. That is the third value #323 names, never collapsed with "could not look".
    assert s.routing_class == dispatch.Stratum.known(dispatch.RoutingClass("", ""))


def test_strata_labels_are_unchecked_when_the_body_came_from_issue_body() -> None:
    # `--issue-body` arms a dispatch where `gh` cannot reach GitHub, so labels are not
    # fetched — not "no labels". The value is None (no answer), and the distinction is the
    # one the observatory depends on.
    s = dispatch.capture_strata(NO_PATH_BODY, 323, REPO, body_from_file=True)
    assert s.labels == dispatch.Stratum.unknown(s.labels.unchecked_why)
    assert s.labels.value is None
    assert s.labels.unchecked_why


def test_strata_labels_are_checked_when_gh_is_reachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(dispatch.readiness, "fetch_labels", lambda *_: (("bug", "ui"), ""))
    s = dispatch.capture_strata(NO_PATH_BODY, 323, REPO, body_from_file=False)
    assert s.labels == dispatch.Stratum.known(("bug", "ui"))


def test_strata_treats_an_empty_label_list_as_a_checked_absence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # An issue that carries no labels is checked-True with an empty tuple — the absence the
    # observatory must not mistake for "could not look", and distinct from None.
    monkeypatch.setattr(dispatch.readiness, "fetch_labels", lambda *_: ((), ""))
    s = dispatch.capture_strata(NO_PATH_BODY, 323, REPO, body_from_file=False)
    assert s.labels == dispatch.Stratum.known(())
    assert s.labels.value == ()


def test_strata_labels_are_unchecked_when_gh_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        dispatch.readiness, "fetch_labels", lambda *_: ((), "gh did not answer within 30s")
    )
    s = dispatch.capture_strata(NO_PATH_BODY, 323, REPO, body_from_file=False)
    assert s.labels == dispatch.Stratum.unknown("gh did not answer within 30s")


def test_strata_gate_is_unchecked_when_the_vocabulary_could_not_be_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # CONTEXT.md unreadable and no in-world path to fall back on: undetermined *because*
    # the check could not run, which is the unchecked state — not a genuine undetermined.
    # Patched on `gate`, which is where capture_strata now reads it (not `brief`).
    monkeypatch.setattr(dispatch.gate, "read_vocabulary", lambda *_: ())
    s = dispatch.capture_strata(NO_PATH_BODY, 323, REPO, body_from_file=True)
    assert s.gate_tier == dispatch.Stratum.unknown(s.gate_tier.unchecked_why)
    assert s.gate_tier.value is None
    assert s.gate_tier.unchecked_why


def test_strata_gate_undetermined_is_checked_when_the_vocabulary_was_readable() -> None:
    # A genuine undetermined (readable vocabulary, no paths) is a stratum, not a failure:
    # the two undetermined-states must not collapse into one.
    s = dispatch.capture_strata(NO_PATH_BODY, 323, REPO, body_from_file=True)
    assert s.gate_tier == dispatch.Stratum.known("undetermined")


def test_strata_routing_class_is_unchecked_when_the_policy_could_not_be_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        dispatch.routing_policy,
        "read_policy",
        lambda *_: routing_policy.ReadResult(None, "policy unreadable"),
    )
    s = dispatch.capture_strata(IN_WORLD_BODY, 323, REPO, body_from_file=True)
    assert s.routing_class == dispatch.Stratum.unknown("policy unreadable")
    assert s.routing_class.value is None


def test_the_dispatch_record_carries_the_strata(tmp_path: Path) -> None:
    # End-to-end through plan_dispatch: the default fixture body (tools/worker.py) is a
    # non-world issue with no routing class, dispatched in --issue-body mode.
    plan, _brief, refusal = plan_for(tmp_path)
    assert refusal is None
    assert plan is not None
    strata = plan.document()["strata"]
    assert strata["gate_tier"] == "fast"
    assert strata["gate_tier_checked"] is True
    assert strata["routing_class_id"] == ""
    assert strata["routing_class_name"] == ""
    assert strata["routing_class_checked"] is True
    assert strata["labels_checked"] is False  # --issue-body mode
    # An unchecked signal writes None for its value, never one a checked run could have
    # written (#323 review finding 1).
    assert strata["labels"] is None


def test_the_dispatch_record_carries_an_in_world_issue_strata(tmp_path: Path) -> None:
    body = tmp_path / "in-world.md"
    body.write_text(
        "## Scope\n\nImplement the change in `addons/main/fn_foo.sqf`.\n\n"
        "## Acceptance criteria\n\n"
        "- [ ] `addons/main/fn_foo.sqf` returns the expected value.\n"
        "- [ ] `just unit` is green.\n",
        encoding="utf-8",
    )
    plan, _brief, refusal = plan_for(tmp_path, issue_body=str(body))
    assert refusal is None
    assert plan is not None
    strata = plan.document()["strata"]
    assert strata["gate_tier"] == "regress"
    assert strata["routing_class_id"] == "5"
    assert strata["routing_class_name"] == "in_world_landings"


def test_a_record_round_trips_its_strata(tmp_path: Path) -> None:
    plan, brief_text, refusal = plan_for(tmp_path)
    assert refusal is None
    assert plan is not None
    dispatch.write_record(plan, brief_text)
    reloaded = dispatch.load_record(plan.record)
    assert reloaded.strata == plan.strata


def test_a_record_written_before_strata_reads_back_unchecked() -> None:
    # A pre-#323 record carries no strata: read_strata returns the honest statement of
    # that — nothing recorded, nothing checked — rather than a guess dressed as a value.
    s = dispatch.read_strata({})
    assert s == dispatch.NO_STRATA
    absent = dispatch.STRATUM_PRE_STRATA_ABSENT
    assert s.gate_tier == dispatch.Stratum.unknown("", absent)
    assert s.routing_class == dispatch.Stratum.unknown("", absent)
    assert s.labels == dispatch.Stratum.unknown("", absent)


# ---------------------------------------------- the findings from review round 1
#
# Each is one test that fails without its fix, so a regression is a named red rather than a
# silent drift. The ones that matter most are the unknowable and malformed cases — the
# shapes a consumer that ignores the flag, or a record the reader cannot make sense of, must
# never turn into a confident value.


def test_document_emits_null_for_every_value_when_no_signal_ran() -> None:
    # #323 review finding 1: an unchecked signal writes None for its value, so a consumer
    # that ignores the checked flag gets no answer rather than a plausible wrong one. The
    # absent-versus-unchecked distinction cannot collapse for any of the three signals.
    unchecked = dispatch.Strata(
        gate_tier=dispatch.Stratum.unknown("vocabulary unreadable"),
        routing_class=dispatch.Stratum.unknown("policy unreadable"),
        labels=dispatch.Stratum.unknown("body from --issue-body"),
    )
    doc = unchecked.document()
    assert doc["gate_tier"] is None
    assert doc["routing_class_id"] is None
    assert doc["routing_class_name"] is None
    assert doc["labels"] is None
    # The flags and reasons survive, so a consumer that does read them still knows what happened.
    assert doc["gate_tier_checked"] is False
    assert doc["labels_unchecked_why"] == "body from --issue-body"


def test_the_routing_class_records_its_stable_id_separately_from_its_mutable_name() -> None:
    # #323 review finding 6: a class rename must not fragment the history the observatory
    # reads, so the stable id and the mutable name are two fields — and the flattened
    # `routing_class` string is gone.
    s = dispatch.capture_strata(IN_WORLD_BODY, 323, REPO, body_from_file=True)
    assert s.routing_class.value == dispatch.RoutingClass("5", "in_world_landings")
    doc = s.document()
    assert doc["routing_class_id"] == "5"
    assert doc["routing_class_name"] == "in_world_landings"
    assert "routing_class" not in doc


def test_read_strata_degrades_a_missing_value_beside_checked_true_to_unchecked() -> None:
    # #323 review finding 2: a checked flag with no value beside it once became a confident
    # empty value; it degrades to unchecked with a reason instead. The value field is absent
    # here, so the reason says the fields are missing rather than that the record is broken —
    # a record valid in an earlier shape must not be accused of being malformed (round 2
    # finding 4).
    s = dispatch.read_strata({"strata": {"gate_tier_checked": True, "gate_tier_unchecked_why": ""}})
    assert s.gate_tier.checked is False
    assert s.gate_tier.value is None
    assert "none of the value fields" in s.gate_tier.unchecked_why


def test_read_strata_does_not_coerce_a_null_into_the_string_none() -> None:
    # str(None) gives "None"; the validator rejects None rather than dressing it as a tier.
    s = dispatch.read_strata(
        {"strata": {"gate_tier": None, "gate_tier_checked": True, "gate_tier_unchecked_why": ""}}
    )
    assert s.gate_tier.checked is False
    assert s.gate_tier.value is None


def test_read_strata_does_not_coerce_the_string_false_into_true() -> None:
    # bool("false") gives True; the validator rejects a checked flag that is not a bool.
    s = dispatch.read_strata(
        {
            "strata": {
                "gate_tier": "fast",
                "gate_tier_checked": "false",
                "gate_tier_unchecked_why": "",
            }
        }
    )
    assert s.gate_tier.checked is False
    assert s.gate_tier.value is None


def test_read_strata_does_not_iterate_a_label_string_into_characters() -> None:
    # "labels": "bug" once became ("b", "u", "g"); the validator wants a list of strings.
    s = dispatch.read_strata(
        {"strata": {"labels": "bug", "labels_checked": True, "labels_unchecked_why": ""}}
    )
    assert s.labels.checked is False
    assert s.labels.value is None


def test_read_strata_tolerates_a_null_label_list_without_raising() -> None:
    # A null label list once raised TypeError inside the reader; it degrades to unchecked.
    s = dispatch.read_strata(
        {"strata": {"labels": None, "labels_checked": True, "labels_unchecked_why": ""}}
    )
    assert s.labels.checked is False
    assert s.labels.value is None


def test_read_strata_degrades_a_routing_class_missing_one_field_to_unchecked() -> None:
    # The id without the name (or vice versa) is not a class this recorder writes.
    s = dispatch.read_strata(
        {
            "strata": {
                "routing_class_id": "5",
                "routing_class_checked": True,
                "routing_class_unchecked_why": "",
            }
        }
    )
    assert s.routing_class.checked is False
    assert s.routing_class.value is None


def test_read_strata_reads_back_a_well_formed_record() -> None:
    # The tolerant reader still reads exactly what a well-formed record writes.
    s = dispatch.read_strata(
        {
            "strata": {
                "gate_tier": "fast",
                "gate_tier_checked": True,
                "gate_tier_unchecked_why": "",
                "routing_class_id": "5",
                "routing_class_name": "in_world_landings",
                "routing_class_checked": True,
                "routing_class_unchecked_why": "",
                "labels": ["bug", "ui"],
                "labels_checked": True,
                "labels_unchecked_why": "",
            }
        }
    )
    assert s.gate_tier == dispatch.Stratum.known("fast")
    assert s.routing_class == dispatch.Stratum.known(
        dispatch.RoutingClass("5", "in_world_landings"),
    )
    assert s.labels == dispatch.Stratum.known(("bug", "ui"))


# ---------------------------------------------- the findings from review round 2
#
# Each is one test that fails without its fix, named for the property it pins. The shared
# thread is the read boundary: what a record that contradicts itself, or that this reader does
# not recognise, leaves behind for the observatory that will one day read it.


def test_an_unchecked_stratum_cannot_be_built_with_a_value() -> None:
    # #323 review round 2 finding 1: F1 ("null whenever unchecked") held only because
    # capture_strata built through Stratum.unknown; the type let any caller put a value beside
    # checked=False. The type refuses that shape now, so document() writes `value`
    # unconditionally without a boundary guard, and no future writer has to remember.
    with pytest.raises(ValueError, match="carries no value"):
        dispatch.Stratum(
            value="fast",
            checked=False,
            unchecked_why="",
            code=dispatch.STRATUM_SOURCE_UNAVAILABLE,
        )
    # The two honest shapes still construct, including a checked empty value (an issue with no
    # labels) and an unchecked no-value (a signal that could not run).
    checked = dispatch.STRATUM_CHECKED
    unavailable = dispatch.STRATUM_SOURCE_UNAVAILABLE
    assert dispatch.Stratum.known("fast") == dispatch.Stratum(
        "fast", checked=True, unchecked_why="", code=checked
    )
    assert dispatch.Stratum.unknown("why") == dispatch.Stratum(
        None, checked=False, unchecked_why="why", code=unavailable
    )
    assert dispatch.Stratum.known(()) == dispatch.Stratum(
        (), checked=True, unchecked_why="", code=checked
    )


@pytest.mark.parametrize("container", [[], None, "x", 7])
def test_read_strata_distinguishes_a_present_non_mapping_from_a_pre_strata_record(
    container: object,
) -> None:
    # #323 review round 2 finding 3: {"strata": []}, {"strata": null} and {"strata": "x"} all
    # returned NO_STRATA — indistinguishable from a record predating the field, and every
    # reason empty. A present non-mapping is a malformed container, not a pre-#323 record, so
    # it gets the same reason on every signal. The comment above that short-circuit claimed the
    # per-field reader handled it, which it could not: a non-dict never reaches it.
    s = dispatch.read_strata({"strata": container})
    assert s != dispatch.NO_STRATA
    assert s.gate_tier.checked is False
    assert s.routing_class.checked is False
    assert s.labels.checked is False
    assert s.gate_tier.unchecked_why == s.routing_class.unchecked_why == s.labels.unchecked_why
    assert "not a mapping" in s.gate_tier.unchecked_why


def test_read_strata_keeps_an_absent_strata_field_as_no_strata() -> None:
    # The pre-#323 record carries no strata field at all: nothing recorded, nothing checked,
    # no reason. Only that case reads back as NO_STRATA — a present container (even an empty
    # dict) does not, so 'nobody recorded anything' stays distinct from 'the recording broke'.
    assert dispatch.read_strata({}) == dispatch.NO_STRATA
    assert dispatch.read_strata({"strata": {}}) != dispatch.NO_STRATA


def test_read_strata_does_not_call_an_earlier_shapes_routing_class_malformed() -> None:
    # #323 review round 2 finding 4: a record written in the unlanded 5ff7f29 shape carried the
    # flattened "id:name" routing_class string. The new reader looks for the split id/name
    # fields, so it reads back unchecked — correctly — but the reason must say the fields are
    # absent, not accuse a record that was valid in the shape it was written in. No migration:
    # that shape never landed.
    s = dispatch.read_strata(
        {
            "strata": {
                "routing_class": "5:in_world_landings",
                "routing_class_checked": True,
                "routing_class_unchecked_why": "",
            }
        }
    )
    assert s.routing_class.checked is False
    assert s.routing_class.value is None
    assert "malformed" not in s.routing_class.unchecked_why
    assert "none of the value fields" in s.routing_class.unchecked_why


def test_read_strata_distinguishes_a_present_wrong_type_from_an_absent_field() -> None:
    # The absent-fields reason (finding 4) is for a value this reader does not carry at all. A
    # value that is present but the wrong type is a different shape and gets its own reason, so
    # the two stay distinguishable rather than collapsing back into one "malformed".
    s = dispatch.read_strata(
        {"strata": {"gate_tier": 7, "gate_tier_checked": True, "gate_tier_unchecked_why": ""}}
    )
    assert s.gate_tier.checked is False
    assert "none of the value fields" not in s.gate_tier.unchecked_why
    assert "not in the shape" in s.gate_tier.unchecked_why


def test_the_gate_derivation_lives_in_a_module_that_imports_neither_dispatcher_nor_brief() -> None:
    # #323 review finding 3: when the body-reading functions lived in `brief`, a capture_strata
    # that imported `brief` closed the ring with brief's module-level `import dispatch` and
    # loaded a second dispatcher under the production `__main__` shape. `gate` owns them now
    # and imports neither, so reaching them costs no cycle. Asserted in a clean subprocess,
    # which is the one place `load_tool('dispatch')` cannot mask the edge.
    probe = (
        "import sys; sys.path.insert(0, 'tools'); import gate; "
        "assert 'dispatch' not in sys.modules, 'gate imported the dispatcher'; "
        "assert 'brief' not in sys.modules, 'gate imported the brief composer'; "
        "print('gate_is_acyclic')"
    )
    result = subprocess.run(  # noqa: S603 — the interpreter and a fixed probe string, not input
        [sys.executable, "-c", probe],
        capture_output=True,
        check=False,
        text=True,
        cwd=REPO,
    )
    assert result.returncode == 0, result.stderr
    assert "gate_is_acyclic" in result.stdout


# ---------------------------------------------- the findings from review round 3
#
# Round 2's contradiction check named a carried value only when the reason was a well-typed
# string; a missing or non-string reason beside `checked: false` hit the type guard first and
# returned the generic "malformed", losing the value F2 exists to surface. The four degradation
# states a record can land in must stay mechanically apart, because #336 will tell them apart by
# reason alone.


@pytest.mark.parametrize(
    ("reason_field", "case"),
    [
        ({}, "the reason is missing"),
        ({"gate_tier_unchecked_why": 7}, "the reason is the wrong type"),
        ({"gate_tier_unchecked_why": ""}, "the reason is empty"),
        ({"gate_tier_unchecked_why": "vocabulary unreadable"}, "the reason is well formed"),
    ],
)
def test_read_strata_names_a_carried_value_whatever_the_reason_is(
    reason_field: dict[str, object], case: str
) -> None:
    # #323 review round 2 finding 2 and round 3 finding 2, as one parametrised test (#347's
    # rider): a record carrying a value beside `checked: false` contradicts F1, which writes
    # None for an unchecked signal. The reader returns unchecked — the right state — names what
    # it saw, and classifies the state the same way whatever the reason field holds. The
    # contradiction is read *before* the reason's type is inspected, so a missing or non-string
    # reason does not collapse the state back into the generic "malformed", losing the carried
    # value F2 exists to surface. Three near-identical tests repeating one setup and four
    # assertions differing only in the reason input are one test over four inputs here.
    s = dispatch.read_strata(
        {"strata": {"gate_tier": "fast", "gate_tier_checked": False, **reason_field}}
    )
    assert s.gate_tier.checked is False, case
    assert s.gate_tier.value is None, case
    assert s.gate_tier.code == dispatch.STRATUM_UNCHECKED_WITH_VALUE, case
    assert "'fast'" in s.gate_tier.unchecked_why, case
    assert "unchecked" in s.gate_tier.unchecked_why, case
    assert "malformed" not in s.gate_tier.unchecked_why, case


# ---------------------------------------------- the typed degradation codes (#347)
#
# Round 3 left the degradation states apart only by their reasons, which is four examples that
# happen not to collide rather than a contract: `Stratum.unknown("")` collided exactly with
# pre-#323 absence, and the carried-value reason varied with `repr`. The code is the contract.
# Every test below reads `code` and never the prose, and the ones that matter most are the
# empty-reason case and the identical-prose case — the two shapes where a reason-keyed consumer
# gets a confident wrong answer and a code-keyed one cannot.


def test_every_degradation_state_carries_a_distinct_code() -> None:
    # The four the ruling names, plus the ordinary states either side of them. Distinct codes,
    # one per state, and the set is exactly as large as the number of states — a drift that
    # merged two would shrink it.
    states = {
        "carried": dispatch.read_strata(
            {"strata": {"gate_tier": "fast", "gate_tier_checked": False}}
        ),
        "non_mapping": dispatch.read_strata({"strata": []}),
        "value_fields_absent": dispatch.read_strata(
            {"strata": {"gate_tier_checked": True, "gate_tier_unchecked_why": ""}}
        ),
        "pre_strata": dispatch.read_strata({}),
        "record_malformed": dispatch.read_strata({"strata": {"gate_tier_checked": "false"}}),
        "value_malformed": dispatch.read_strata(
            {"strata": {"gate_tier": 7, "gate_tier_checked": True, "gate_tier_unchecked_why": ""}}
        ),
        "source_unavailable": dispatch.read_strata(
            {"strata": {"gate_tier_checked": False, "gate_tier_unchecked_why": "no CONTEXT.md"}}
        ),
        "checked": dispatch.read_strata(
            {
                "strata": {
                    "gate_tier": "fast",
                    "gate_tier_checked": True,
                    "gate_tier_unchecked_why": "",
                }
            }
        ),
    }
    codes = {name: s.gate_tier.code for name, s in states.items()}
    assert len(set(codes.values())) == len(codes), codes
    assert codes["carried"] == dispatch.STRATUM_UNCHECKED_WITH_VALUE
    assert codes["non_mapping"] == dispatch.STRATUM_CONTAINER_NOT_MAPPING
    assert codes["value_fields_absent"] == dispatch.STRATUM_VALUE_FIELDS_ABSENT
    assert codes["pre_strata"] == dispatch.STRATUM_PRE_STRATA_ABSENT
    assert codes["record_malformed"] == dispatch.STRATUM_RECORD_MALFORMED
    assert codes["value_malformed"] == dispatch.STRATUM_VALUE_MALFORMED
    assert codes["source_unavailable"] == dispatch.STRATUM_SOURCE_UNAVAILABLE
    assert codes["checked"] == dispatch.STRATUM_CHECKED


def test_an_empty_reason_does_not_collide_with_the_pre_strata_absence() -> None:
    # The collision #347 was filed for. An ordinary unchecked signal whose reason is empty and
    # a record predating the field are the same prose — the empty string — so a consumer keyed
    # on `unchecked_why` cannot tell "the source was unavailable" from "nobody ever recorded
    # anything". The codes differ, and that is the whole contract.
    empty_reason = dispatch.read_strata(
        {"strata": {"gate_tier_checked": False, "gate_tier_unchecked_why": ""}}
    )
    pre_strata = dispatch.read_strata({})
    assert empty_reason.gate_tier.unchecked_why == pre_strata.gate_tier.unchecked_why == ""
    assert empty_reason.gate_tier.code != pre_strata.gate_tier.code
    assert empty_reason.gate_tier.code == dispatch.STRATUM_SOURCE_UNAVAILABLE
    assert pre_strata.gate_tier.code == dispatch.STRATUM_PRE_STRATA_ABSENT


@pytest.mark.parametrize("prose", ["", "vocabulary unreadable", "not a mapping", "malformed"])
def test_classification_does_not_depend_on_the_recorded_prose(prose: str) -> None:
    # The reason is diagnostic and never a grouping key: a record whose prose impersonates
    # another state's — including the exact substrings the round-2 and round-3 tests match on —
    # still classifies by structure. A reason-keyed consumer reads "not a mapping" here and
    # gets the wrong stratum; a code-keyed one cannot.
    s = dispatch.read_strata(
        {"strata": {"gate_tier_checked": False, "gate_tier_unchecked_why": prose}}
    )
    assert s.gate_tier.code == dispatch.STRATUM_SOURCE_UNAVAILABLE
    assert s.gate_tier.unchecked_why == prose


@pytest.mark.parametrize("carried", ["fast", 7, ["fast"], {"tier": "fast"}, None])
def test_the_carried_value_code_does_not_depend_on_repr(carried: object) -> None:
    # The carried-value reason interpolates `{seen!r}`, so it varies with every value a broken
    # record happens to hold — which is why it was never a key. The code is one string across
    # every one of them. `None` is the control: it is not a carried value at all, so it is the
    # ordinary unchecked state and must *not* take this code.
    s = dispatch.read_strata(
        {
            "strata": {
                "gate_tier": carried,
                "gate_tier_checked": False,
                "gate_tier_unchecked_why": "",
            }
        }
    )
    expected = (
        dispatch.STRATUM_SOURCE_UNAVAILABLE
        if carried is None
        else dispatch.STRATUM_UNCHECKED_WITH_VALUE
    )
    assert s.gate_tier.code == expected


@pytest.mark.parametrize(
    ("signal", "row", "expected"),
    [
        (
            "gate_tier",
            {"gate_tier_checked": True, "gate_tier_unchecked_why": ""},
            "value_fields_absent",
        ),
        (
            "routing_class",
            {"routing_class_checked": True, "routing_class_unchecked_why": ""},
            "value_fields_absent",
        ),
        ("labels", {"labels_checked": True, "labels_unchecked_why": ""}, "value_fields_absent"),
        ("gate_tier", {"gate_tier": 7, "gate_tier_checked": True}, "record_malformed"),
        (
            "routing_class",
            {"routing_class_id": "5", "routing_class_checked": True, "routing_class_why": ""},
            "record_malformed",
        ),
        (
            "labels",
            {"labels": "bug", "labels_checked": True, "labels_unchecked_why": ""},
            "value_malformed",
        ),
    ],
)
def test_every_signal_carries_the_same_codes(
    signal: str, row: dict[str, object], expected: str
) -> None:
    # All three signals go through one reader, so all three degrade into the same vocabulary.
    # #336 stratifies on gate tier, routing class and labels alike and must not learn three.
    s = dispatch.read_strata({"strata": row})
    assert getattr(s, signal).code == expected


def test_a_pre_existing_record_is_classified_without_being_rewritten() -> None:
    # The ruling's third requirement: the code is *derived* from raw structure for records
    # predating the field, and nothing rewrites them. The document handed in is compared byte
    # for byte with itself afterwards — reading classifies, it does not migrate.
    document: dict[str, object] = {
        "strata": {
            "routing_class": "5:in_world_landings",
            "routing_class_checked": True,
            "routing_class_unchecked_why": "",
        }
    }
    before = json.dumps(document, sort_keys=True)
    s = dispatch.read_strata(document)
    assert s.routing_class.code == dispatch.STRATUM_VALUE_FIELDS_ABSENT
    assert json.dumps(document, sort_keys=True) == before
    # And the nine landed records that predate the field entirely: no `strata` key at all.
    assert dispatch.read_strata({}).gate_tier.code == dispatch.STRATUM_PRE_STRATA_ABSENT


def test_the_record_carries_the_code_for_every_signal() -> None:
    # The discriminator goes on newly written records, so a consumer reading the raw JSON —
    # rather than through `read_strata` — stratifies on the same key.
    doc = dispatch.Strata(
        gate_tier=dispatch.Stratum.known("fast"),
        routing_class=dispatch.Stratum.unknown("policy unreadable"),
        labels=dispatch.Stratum.unknown("body from --issue-body"),
    ).document()
    assert doc["gate_tier_code"] == dispatch.STRATUM_CHECKED
    assert doc["routing_class_code"] == dispatch.STRATUM_SOURCE_UNAVAILABLE
    assert doc["labels_code"] == dispatch.STRATUM_SOURCE_UNAVAILABLE


def test_a_pre_strata_plan_round_trips_its_code_rather_than_flattening_to_unavailable() -> None:
    # A plan carrying NO_STRATA writes an unchecked signal with an empty reason — structurally
    # identical to an ordinary source-unavailable one. The recorded code is the only thing that
    # tells them apart on the way back, which is why that one branch honours it.
    doc = dispatch.NO_STRATA.document()
    assert dispatch.read_strata({"strata": doc}) == dispatch.NO_STRATA


def test_an_unrecognised_recorded_code_falls_back_to_the_derived_one() -> None:
    # A code this recorder does not write is not trusted: the fallback is the derived state,
    # never the reason's text. A record cannot name itself into a stratum.
    for bogus in ("wat", "", 7, None, dispatch.STRATUM_CHECKED):
        s = dispatch.read_strata(
            {
                "strata": {
                    "gate_tier_checked": False,
                    "gate_tier_unchecked_why": "",
                    "gate_tier_code": bogus,
                }
            }
        )
        assert s.gate_tier.code == dispatch.STRATUM_SOURCE_UNAVAILABLE, bogus


def test_a_stratum_refuses_a_code_its_flag_contradicts() -> None:
    # The flag and the code cannot disagree, so no writer can produce a checked stratum coded
    # as a degradation (or the reverse) for #336 to group on.
    with pytest.raises(ValueError, match="contradicts checked"):
        dispatch.Stratum(
            value="fast", checked=True, unchecked_why="", code=dispatch.STRATUM_RECORD_MALFORMED
        )
    with pytest.raises(ValueError, match="contradicts checked"):
        dispatch.Stratum(value=None, checked=False, unchecked_why="", code=dispatch.STRATUM_CHECKED)
    with pytest.raises(ValueError, match="unknown Stratum code"):
        dispatch.Stratum(value="fast", checked=True, unchecked_why="", code="wat")
