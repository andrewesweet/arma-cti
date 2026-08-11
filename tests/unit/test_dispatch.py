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
admission = load_tool("admission")

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
UNREADY_BODY = "The dispatcher feels slow lately and somebody should have a look.\n"


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
    # Same reason for the admission records (#224): a seam run must not read, and must
    # not write, this box's real standing for a foreign profile.
    env["CTI_ADMISSION_DIR"] = str(tmp_path / "admission")
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
    now = overrides.pop("now", None) or datetime.now(tz=UTC)
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
        "admission_dir": str(tmp_path / "admission"),
        "issue_body": str(ROUTING_ELIGIBLE_BODY),
        "queue_dir": str(open_policy(tmp_path)),
        "queue_root": str(tmp_path / "queue-root"),
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
    assert "zai-glm52-max" in dispatch.PROFILES
    assert "codex-sol-xhigh" in dispatch.PROFILES


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
    assert sorted(resolved) == ["glm-4.7", "glm-5.2"]
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
    assert lane.foreign is False


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


def test_an_unknown_seat_is_refused_rather_than_mis_attributed() -> None:
    refusal = dispatch.resolve_selection("claude-native", "opus-high", "implemeter")
    assert refusal is not None
    assert refusal.kind == "unknown_seat"


# -------------------------------------------------------- the standing retro allowance
# The human's ruling of 2026-08-09 (#299) supersedes the time-boxed allowance of
# 2026-08-06 (#217, #270) that would have lapsed at 2026-08-10T14:00Z: retros may run as
# the `fable` seat on `codex`/`codex-sol-xhigh` with no expiry. So these tests no longer
# inject a clock — there is nothing time-dependent left to prove — and they assert
# instead that the allowance is exactly one triple and widens to nothing else.
#
# "Or above" in the ruling is deliberately not a comparison this module makes: profiles
# are opaque `(lane, model, effort)` tokens and no cross-provider effort scale exists
# (ADR-0061 decision 5), so a higher profile joins by being named, by the human.


@pytest.mark.parametrize("profile", ["codex-sol-xhigh", "codex-sol-max"])
def test_the_standing_allowance_lets_fable_dispatch_on_each_ruled_foreign_profile(
    profile: str,
) -> None:
    assert dispatch.resolve_selection("codex", profile, "fable") is None


def test_the_real_planning_path_admits_the_standing_allowance(tmp_path: Path) -> None:
    plan, _, refusal = plan_for(
        tmp_path,
        lane="codex",
        profile="codex-sol-xhigh",
        seat="fable",
    )
    assert refusal is None
    assert plan is not None


@pytest.mark.parametrize(
    ("lane", "profile"),
    [
        ("codex", "codex-sol-high"),
        ("codex", "codex-terra-medium"),
        ("codex", "codex-terra-low"),
        ("zai", "zai-glm52-max"),
        ("zai", "zai-glm47-max"),
    ],
)
def test_the_seat_allowance_does_not_widen_beyond_the_ruled_routes(lane: str, profile: str) -> None:
    # Two foreign routes only. Every other fable-on-foreign combination stays barred —
    # including `codex-sol-high`, which is *below* the ruled levels and is the case a
    # careless "or above" reading would have admitted.
    refusal = dispatch.resolve_selection(lane, profile, "fable")
    assert refusal is not None
    assert refusal.kind == "seat_not_eligible"
    # A refusal, not a failure class — nothing was found about a provider or about code.
    assert refusal.failure_class == ""
    assert not any(line.startswith("class=") for line in refusal.lines())


@pytest.mark.parametrize("lane", ["codex", "zai"])
def test_the_orchestrator_seat_stays_barred_on_every_foreign_lane(lane: str) -> None:
    # The ruling touches fable alone; the orchestrator seat never leaves Claude.
    profile = "codex-sol-xhigh" if lane == "codex" else "zai-glm52-max"
    refusal = dispatch.resolve_selection(lane, profile, "orchestrator")
    assert refusal is not None
    assert refusal.kind == "seat_not_eligible"


def test_every_retro_approved_profile_is_registered() -> None:
    """The human's list names profiles; a name with no profile is undispatchable.

    Five of the nine did not exist when the list was ruled (2026-08-09) and were added
    with it. A later edit that drops one would leave the ruling naming a route nobody
    can take, which is the failure this asserts against.
    """
    for name in dispatch.RETRO_APPROVED_PROFILES:
        assert name in dispatch.PROFILES, name


def test_the_ruled_foreign_routes_are_a_subset_of_the_approved_list() -> None:
    # The allowance suspends Decision 2; it must never admit a route the human did not
    # approve for retros at all.
    for _seat, _lane, profile in dispatch.RETRO_ALLOWANCE:
        assert profile in dispatch.RETRO_APPROVED_PROFILES, profile


def test_the_standing_allowance_is_visible_in_the_dispatch_registry() -> None:
    # A standing exception is stated wherever the registry is read: silence would let a
    # reader believe `SEATS` governs without exception, which is the thing that is false.
    lines = dispatch.registry_lines()
    visible = [line for line in lines if line.startswith("seat_allowance=")]
    assert len(visible) == 2
    assert all(line.startswith("seat_allowance=standing seat=fable lane=codex") for line in visible)
    assert {line.split("profile=")[1].split()[0] for line in visible} == {
        "codex-sol-xhigh",
        "codex-sol-max",
    }
    assert all("expires_at" not in line for line in visible)
    approved = [line for line in lines if line.startswith("retro_approved_profiles=")]
    assert len(approved) == 1
    assert approved[0].split("=", 1)[1].split() == list(dispatch.RETRO_APPROVED_PROFILES)


# ---------------------------------------------- ADR-0071: new profiles and the pair block
# Luna enters on publication — a named exception to the measure-before-building rule — and
# its implementer head is blocked by #265's measured gate ceiling. The block attaches to
# the (profile, seat) pair, so a read-only seat keeps the profile and the implementer seat
# does not. See `SEAT_PROFILE_BLOCKS` and `pair_block` in tools/dispatch.py.


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


def test_codex_luna_max_blocked_for_implementer_names_the_gate_ceiling() -> None:
    refusal = dispatch.resolve_selection("codex", "codex-luna-max", "implementer")
    assert refusal is not None
    assert refusal.kind == "profile_blocked_for_seat"
    # A refusal, not a failure class — nothing was found about a provider or about code.
    assert refusal.failure_class == ""
    assert not any(line.startswith("class=") for line in refusal.lines())
    # The pair and the ceiling it waits on are machine-visible in `found`.
    assert "profile=codex-luna-max" in refusal.found
    assert "seat=implementer" in refusal.found
    assert "ceiling=#265" in refusal.found
    # The action names the ceiling so a reader knows what would clear it.
    assert "#265" in refusal.action
    assert "writable_roots" in refusal.action
    assert "gate" in refusal.action


def test_the_pair_block_is_the_one_home_a_seat_resolver_will_share() -> None:
    # ADR-0071 ruling 2: the refusal attaches to the pair, not to how the profile was
    # chosen. `resolve_selection` (the `--profile` path) and `pair_block` (the function a
    # future seat resolver calls, #321) are the same check, so a resolver consults this and
    # not a second copy of the list.
    direct = dispatch.pair_block("implementer", "codex-luna-max")
    via_selection = dispatch.resolve_selection("codex", "codex-luna-max", "implementer")
    assert direct is not None
    assert via_selection is not None
    assert direct == via_selection


def test_codex_luna_max_dispatches_normally_on_the_read_only_recon_seat(tmp_path: Path) -> None:
    # The pair matters: a profile blocked for a seat that must commit and gate is not
    # thereby blocked for a read-only seat that does neither. Selection clears it ...
    assert dispatch.resolve_selection("codex", "codex-luna-max", "recon") is None
    # ... and so does the full planning ladder. The codex lane is not off-peak-ruled, the
    # profile is on probation (which dispatches), and recon is Decision-2-eligible.
    plan, _, refusal = plan_for(
        tmp_path,
        lane="codex",
        profile="codex-luna-max",
        seat="recon",
    )
    assert refusal is None
    assert plan is not None


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


def test_the_cheap_zai_profile_reaches_the_other_glm_through_the_haiku_slot() -> None:
    child = assembled("zai", "zai-glm47-max", {"HOME": "/home/t"}, FAKE_TOKEN)
    assert child["ANTHROPIC_DEFAULT_HAIKU_MODEL"] == "glm-4.7"
    assert dispatch.PROFILES["zai-glm47-max"].model == "haiku"


@pytest.mark.parametrize(
    ("lane", "profile"), [("zai", "zai-glm52-max"), ("claude-native", "opus-high")]
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


def test_a_codex_workspace_write_session_can_write_the_repositorys_git_metadata(
    tmp_path: Path,
) -> None:
    # #259: under plain `--sandbox workspace-write` the first `git add` died on
    # "Unable to create '<main>/.git/worktrees/issue-259-codex/index.lock': Read-only
    # file system", so the commit half of the human's ruling was unreachable. The main
    # checkout is a root because `just land`'s ff-only merge writes it — and `.git` is a
    # root **of its own**, because Codex holds `.git` read-only even when its parent is
    # writable: probe `d-20260806-164858-905eb2` wrote a file beside `.git` and was
    # refused inside it, in one command. Naming the repository alone is not enough, and
    # this test is what stops that regressing back to the version that measured red.
    argv, root, linked = _codex_argv_from_a_linked_worktree(tmp_path, "acceptEdits")
    roots = _writable_roots(argv)
    assert f'"{root}"' in roots
    assert f'"{root / ".git"}"' in roots
    # And the linked worktree's *own* git directory, which is the one that actually
    # carries its index, HEAD and FETCH_HEAD. Naming the common directory alone was
    # measured insufficient: `.git/topA` was created while
    # `.git/worktrees/issue-259-codex/subB` was refused in the same command.
    assert f'"{root / ".git" / "worktrees" / linked.name}"' in roots
    # The session's own worktree is cwd, which `workspace-write` already grants; a root
    # naming it would be noise claiming to be a grant.
    assert f'"{linked}"' not in roots
    assert argv[argv.index("--sandbox") + 1] == "workspace-write"


def test_a_plain_checkout_names_its_one_git_directory_once(tmp_path: Path) -> None:
    # `--absolute-git-dir` and `--git-common-dir` coincide outside a linked worktree, and a
    # root repeated is a reader wondering which of the two is doing the work.
    root = git_worktree(tmp_path, name="plain")
    argv = dispatch.build_argv(
        dispatch.LANES["codex"], dispatch.PROFILES["codex-sol-high"], "acceptEdits", root
    )
    roots = _writable_roots(argv)
    assert roots.count(f'"{root / ".git"}"') == 1


def test_a_codex_workspace_write_session_can_write_the_cache_the_gate_locks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Measured: without this root, `just check`, `just unit` and `just fast` all died at
    # `check-generated` on "Could not create temporary file … Read-only file system" in
    # `~/.cache/uv`, before a single test ran. Read from the environment the way `uv`
    # reads it, so a box that relocates its cache does not silently lose the gate.
    monkeypatch.setenv("UV_CACHE_DIR", "/somewhere/else/uv")
    argv, _root, _linked = _codex_argv_from_a_linked_worktree(tmp_path, "acceptEdits")
    assert '"/somewhere/else/uv"' in _writable_roots(argv)

    monkeypatch.delenv("UV_CACHE_DIR")
    monkeypatch.setenv("XDG_CACHE_HOME", "/xdg/cache")
    argv, _root, _linked = _codex_argv_from_a_linked_worktree(tmp_path, "acceptEdits", "second")
    assert '"/xdg/cache/uv"' in _writable_roots(argv)


def test_the_codex_grant_stops_at_what_was_measured_necessary(tmp_path: Path) -> None:
    # `~/.cargo` is deliberately absent: the gate ran green without it, so it goes
    # ungranted however plausible it looked. `$HOME` and `/` are the two roots that would
    # turn a widening into the bypass the human declined, and neither is here.
    argv, _root, _linked = _codex_argv_from_a_linked_worktree(tmp_path, "acceptEdits")
    roots = _writable_roots(argv)
    assert ".cargo" not in roots
    assert f'"{Path.home()}"' not in roots
    assert '"/"' not in roots


def test_a_codex_workspace_write_session_can_reach_the_network_just_land_needs(
    tmp_path: Path,
) -> None:
    # `sandbox_workspace_write.network_access` defaults to disabled and `just land`
    # fetches and pushes. This is the override with no counterpart on the `zai` lane,
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
        admission_dir=str(tmp_path / "admission"),
        issue_body=str(ROUTING_ELIGIBLE_BODY),
        queue_dir=str(open_policy(tmp_path)),
        queue_root=str(tmp_path / "queue-root"),
    )
    _, _, refusal = dispatch.plan_dispatch(args, REPO, datetime.now(tz=UTC))
    assert refusal is not None
    assert f"worktree={REPO / '.claude' / 'worktrees' / 'issue-999'}" in refusal.found


def test_the_record_names_the_credential_key_and_never_its_value(tmp_path: Path) -> None:
    credentials_file(tmp_path, f"ZAI_API_KEY={FAKE_TOKEN}\n")
    plan, brief, refusal = plan_for(
        tmp_path, lane="zai", profile="zai-glm52-max", seat="review", now=OFF_PEAK
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
        tmp_path, lane="zai", profile="zai-glm52-max", seat="review", now=OFF_PEAK
    )
    assert refusal is None
    assert plan is not None
    dispatch.write_record(plan, brief)

    document = json.loads((plan.record / "dispatch.json").read_text(encoding="utf-8"))
    charge = document["plan_charge"]
    assert charge["meter"] == "prompts"
    assert (charge["peak"], charge["multiplier"]) == (False, 0.5)
    assert charge["schedule"] == "zai-off-peak"
    # The record cites the published terms rather than the module that copied them: a
    # file path stops answering "priced against what?" the moment the file moves.
    assert charge["window_source"] == "https://docs.z.ai/devpack/overview"


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
        tmp_path, lane="zai", profile="zai-glm52-max", seat="review", now=now
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
    # is a harness bug by that table's own rule. `admission_escalated` carries none for
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
    for profile in ("zai-glm52-max", "zai-glm47-max"):
        _, _, refusal = plan_for(
            tmp_path,
            lane="zai",
            profile=profile,
            seat="review",
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
        profile="zai-glm52-max",
        seat="review",
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
    found nothing about any code under test — `admission_refusal`'s reasoning exactly.
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


def test_readiness_outranks_admission_the_breaker_and_the_window(tmp_path: Path) -> None:
    """The ladder's ordering: no clock and no provider will ever clear an unready issue.

    Every rung below this one is arranged to refuse as well — the profile has spent both
    admission attempts, the lane's breaker is tripped, and the clock is inside the peak
    band — and the answer is still the one whose remedy a person can start on now.
    """
    state = admission.Store(directory=tmp_path / "admission")
    for issue in (1, 2):
        admission.append(
            state,
            "zai",
            "zai-glm52-max",
            "review",
            admission.Assessment(
                issue=issue,
                dispatch_id=f"d-test-{issue}",
                criteria=(("close_names_sha", "met"), ("fast_green", "not_met")),
            ),
        )
    trip(tmp_path, "zai", breaker.GATE_FAILED, 3)
    _, _, refusal = plan_for(
        tmp_path,
        lane="zai",
        profile="zai-glm52-max",
        seat="review",
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
    `--breaker-dir` and `--admission-dir` exist because a forked seam test needs its own
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
            "zai-glm52-max",
            "--seat",
            "review",
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
        tmp_path, lane="zai", profile="zai-glm52-max", seat="review", now=OFF_PEAK
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
    foreign = run_seam(
        ["--lane", "zai", "--profile", "zai-glm52-max", *common],
        parent,
    )
    if before_band != breaker.zai_is_peak(time.time()):
        pytest.skip("the run straddled z.ai's band boundary; neither outcome is the claim")
    if before_band:
        # #238's rule is running and there is deliberately no clock override that would
        # let a test dispatch through it, so the claim available in this band is the rule
        # itself, asserted through the same real seam.
        assert foreign.returncode == dispatch.EXIT_REFUSED
        assert "refusal=lane_peak_hours" in foreign.stderr
        assert not (tmp_path / "zai-ran.txt").exists(), "and the runner was never reached"
        assert parent == before
        return
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
    assert "refusal=routing_policy_advisory" in done.stderr
    assert "routing_class=3:retros_and_adr_authorship" in done.stderr
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


def test_the_seam_refuses_a_profile_that_has_spent_both_admission_attempts(
    tmp_path: Path,
) -> None:
    """End to end through the real seam: #224's far end, and `CTI_ADMISSION_DIR` reaching it."""
    state = admission.Store(directory=tmp_path / "admission")
    for issue in (1, 2):
        admission.append(
            state,
            "zai",
            "zai-glm52-max",
            "implementer",
            admission.Assessment(
                issue=issue,
                dispatch_id=f"d-test-{issue}",
                criteria=(("close_names_sha", "met"), ("fast_green", "not_met")),
            ),
        )
    assert not admission.standing_for(state, "zai", "zai-glm52-max", "implementer").dispatchable

    capture = tmp_path / "capture.txt"
    done = run_seam(
        [
            "--lane",
            "zai",
            "--profile",
            "zai-glm52-max",
            "--seat",
            "implementer",
            "--issue",
            "224",
            "--worktree",
            str(git_worktree(tmp_path)),
            "--dispatch-dir",
            str(tmp_path / "dispatches"),
            "--credentials",
            str(credentials_file(tmp_path, f"ZAI_API_KEY={FAKE_TOKEN}\n")),
        ],
        seam_env(tmp_path, capture),
    )
    assert done.returncode == 1
    assert "refusal=admission_escalated" in done.stderr
    assert "state=escalated" not in done.stdout
    assert not (tmp_path / "dispatches").exists(), "nothing was written for a run that never was"
    assert not capture.exists(), "and the runner was never reached"
