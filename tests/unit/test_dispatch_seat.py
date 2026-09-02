"""Seat resolution: `just dispatch --seat S` picks the profile (#321, ADR-0071 ruling 2).

Every claim here is made through the planning entry point — `plan_dispatch`, or `main`
where the criterion names the command line — and never through the resolver's internals.
That is the issue's own instruction and it is the right one: what a caller gets is a plan
or a refusal, and a resolver that returned the right token while the ladder below it
refused the route would satisfy an internal test and none of the criteria.

The arrangements are built to be **clock-free**. A seat's list is walked past by staging
the world into refusing an entry, and the two stages used here — a tripped breaker and an
absent lane credential — hold at any hour, where staging z.ai's off-peak band would make
the suite's answer depend on when it ran. The one case that must exercise the human's
off-peak rule passes an explicit peak moment, exactly as the dispatcher's own tests do.
"""

from __future__ import annotations

import json
import subprocess
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

import pytest
from conftest import REPO, load_tool

if TYPE_CHECKING:
    from pathlib import Path

dispatch = load_tool("dispatch")
breaker = load_tool("breaker")
attribute_registry = load_tool("attribute_registry")

READY_BODY = REPO / "tests" / "fixtures" / "routing-eligible.md"

# z.ai's published peak band is Mon-Fri 14:00-18:00 SGT (UTC+8); 2026-08-05 is a Wednesday,
# so 07:00 UTC is 15:00 SGT and inside it.
PEAK = datetime(2026, 8, 5, 7, 0, tzinfo=UTC)
# The same Wednesday at 20:00 UTC is 04:00 SGT and outside the band, so z.ai is refused
# for the absent credential rather than for the hour — which is what the criterion-1
# arrangements below are claiming (#341).
OFF_PEAK = datetime(2026, 8, 5, 20, 0, tzinfo=UTC)

FAKE_TOKEN = "zai-" + "test-" * 6


# --------------------------------------------------------------------------- helpers


def git_worktree(tmp_path: Path) -> Path:
    """Make a real git repository: the plan reads a real HEAD out of the assigned tree."""
    root = tmp_path / "tree"
    root.mkdir(parents=True)
    for args in (
        ("init", "-q", "-b", "main"),
        ("config", "user.email", "t@example.invalid"),
        ("config", "user.name", "t"),
    ):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)  # noqa: S603, S607
    (root / "README.md").write_text("t\n", encoding="utf-8")
    for args in (("add", "-A"), ("commit", "-qm", "t")):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)  # noqa: S603, S607
    return root


def open_policy(tmp_path: Path) -> Path:
    """Write a queue policy of this test's own: dispatch open, a limit nothing here reaches."""
    directory = tmp_path / "queue"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "policy.json").write_text(
        json.dumps(
            {
                "version": 1,
                "freeze": {"state": "open", "since": "2026-08-06T00:00:00Z", "ruling": "a test"},
                "wip_limit": {"value": 9, "since": "2026-08-06T00:00:00Z", "ruling": "a test"},
                "packages": [],
            }
        ),
        encoding="utf-8",
    )
    return directory


def trip(tmp_path: Path, lane: str, outcome: str, count: int) -> None:
    """Stage a lane's breaker into a state that refuses, without touching this box's own."""
    store = breaker.Store(directory=tmp_path / "breaker", endpoint="http://127.0.0.1:2999/v1/logs")
    for step in range(count):
        breaker.record_outcome(store, lane, breaker.Outcome(outcome), time.time() + step)


def plan_for(tmp_path: Path, **overrides: object) -> tuple[Any, str, Any]:
    """Plan a dispatch that names a seat and no profile, over a real worktree.

    The credentials file is deliberately absent by default, which makes the `implementer`
    list deterministic from its head down: since the human's ruling of 2026-08-27 that head
    is a z.ai profile, and no z.ai entry can be reached without a key, so a box without one
    walks it past at any hour. The Codex entry behind it resolves unless an arrangement
    stages it away — it needs no credential from this file, Codex reading its own
    `~/.codex/auth.json` — and since #405 nothing else holds it back, so a test that wants
    the list *walked* trips the codex breaker rather than relying on a block that no longer
    exists.
    """
    injected = overrides.pop("now", None)
    now = datetime.now(tz=UTC) if injected is None else injected
    dry_run = bool(overrides.pop("dry_run", False))
    worktree = overrides.pop("worktree", None) or git_worktree(tmp_path)
    request = {
        "lane": "",
        "profile": "",
        "seat": "implementer",
        "issue": 223,
        "worktree": str(worktree),
        "brief_file": "",
        "base_sha": "",
        "permission_mode": "acceptEdits",
        "dispatch_dir": str(tmp_path / "dispatches"),
        # This test's own declaration root, for `--dispatch-dir`'s reason (#402, #423):
        # the review arrangements here must not read whatever this box has declared.
        "review_root": str(tmp_path / "review"),
        "credentials": str(tmp_path / "credentials.env"),
        "breaker_dir": str(tmp_path / "breaker"),
        "issue_body": str(READY_BODY),
        "queue_dir": str(open_policy(tmp_path)),
        "queue_root": str(tmp_path / "queue-root"),
        # #322: what a non-review dispatch passes, and the fail-closed value for a review
        # one. The review arrangements below override it.
        "reviewing": "",
        "dry_run": dry_run,
    }
    request.update(overrides)
    return dispatch.plan_dispatch(type("Args", (), request)(), REPO, now)


def walked_past(entries: tuple[Any, ...]) -> list[tuple[str, str]]:
    """Fold a route's passed-over entries into the (profile, refusal) pairs a test reads."""
    return [(entry.profile, entry.refusal) for entry in entries]


def seat_only_argv(tmp_path: Path, worktree: Path, *extra: str) -> list[str]:
    """Build a whole command line naming a seat and an issue and no route at all.

    Shared rather than written twice, because two criteria make a claim about *this* argv:
    that resolution reaches the command line, and that leaving both route options out is a
    complete request. Every state directory is this test's own, for `plan_for`'s reasons.
    """
    return [
        "--seat",
        "implementer",
        "--issue",
        "223",
        "--worktree",
        str(worktree),
        "--issue-body",
        str(READY_BODY),
        "--dispatch-dir",
        str(tmp_path / "dispatches"),
        "--credentials",
        str(tmp_path / "credentials.env"),
        "--breaker-dir",
        str(tmp_path / "breaker"),
        "--queue-dir",
        str(open_policy(tmp_path)),
        "--queue-root",
        str(tmp_path / "queue-root"),
        *extra,
    ]


# ------------------------------------------------------- the table the ADR transcribed


def test_every_seat_carries_a_preference_list_of_registered_profiles() -> None:
    """A seat with an unregistered entry is a route that refuses the moment it is walked."""
    for seat in dispatch.SEATS.values():
        assert seat.preference, seat.name
        for name in (*seat.preference, *seat.escalation):
            assert name in dispatch.PROFILES, f"{seat.name}: {name}"


def test_the_landers_are_exactly_the_seats_the_rulings_name() -> None:
    """#345: the `lands` column holds the rulings' own words, pinned as a set.

    Ruling 2 makes the implementer "carry the work out … and land it" and the planner
    "neither gates nor lands"; A4 makes the retro's journal entry "land under ruling 4
    like any other change". No ruling names `fable` or the `orchestrator` as any route's
    lander, so they sit outside the set rather than defaulting in. What a set pin
    cannot see is an *omitted* column — a default would have answered `False` before
    any assertion ran, the gap the cross-lane review found in the re-implementation —
    so decidability is refused at the registry's own construction by the test below,
    and this pin holds the decided answers against the rulings' words.
    """
    assert {name for name, seat in dispatch.SEATS.items() if seat.lands} == {
        "implementer",
        "retro",
    }


def test_a_seat_omitting_the_lands_column_refuses_rather_than_defaulting() -> None:
    """#345: the column has no working default, so a new seat arrives decided or not at all.

    The guard runs at import over both registries; this calls it directly on a seat
    spelling neither `True` nor `False`, which is the arrival the set pin above cannot
    distinguish from a decided `False`. That covers the omitted column and, since the
    review round that widened the guard, the misspelled one too: the annotation
    `bool | None` enforces nothing at runtime, and the guard's first spelling refused
    only `is None`, so a truthy `1` passed it into the registry — read into the lander
    set by truthiness, composed as a non-lander by `brief.Seat.lands`'s `is True`, the
    disagreement the review blocked on. `cast`, not a `type: ignore`, because the wrong
    type is the arrangement rather than a check to silence.
    """
    undecided = dispatch.Seat("new", claude_only=False, preference=("opus-low",))
    with pytest.raises(TypeError, match="lands"):
        dispatch.refuse_undecided_lands({"new": undecided})
    for misspelled in (1, "false"):
        seat = dispatch.Seat(
            "new",
            claude_only=False,
            preference=("opus-low",),
            lands=cast("bool | None", misspelled),
        )
        with pytest.raises(TypeError, match="lands"):
            dispatch.refuse_undecided_lands({"new": seat})


def test_the_implementer_list_is_the_rulings_order_head_first() -> None:
    # Ordered, not a set: ADR-0071 ruling 2 gives the list head-first and resolution walks
    # it in exactly that order, so the sequence is the claim. The human's ruling of
    # 2026-08-27 replaced both tuples — GLM-5.3-Flash heads the preference, and the
    # escalation entry gained a z.ai rung between its two ends.
    assert dispatch.SEATS["implementer"].preference == (
        "zai-glm53flash-max",
        "codex-luna-max",
        "opus-low",
    )
    assert dispatch.SEATS["implementer"].escalation == (
        "codex-sol-high",
        "zai-glm53-max",
        "opus-high",
    )


def test_the_review_seat_carries_its_own_list_rather_than_the_implementers() -> None:
    # ADR-0071 ruling 2 gave `review` the implementer's list and the implementer's
    # escalation head, and the registry shared one object so the two could not drift. The
    # human's ruling of 2026-08-27 separates them, so the claim inverts: the review seat's
    # tuples are its own, and agreeing with the implementer's would now be the bug.
    assert dispatch.SEATS["review"].preference == (
        "codex-sol-xhigh",
        "zai-glm53-max",
        "opus-medium",
    )
    assert dispatch.SEATS["review"].escalation == ("codex-sol-max", "opus-xhigh")
    assert dispatch.SEATS["review"].preference != dispatch.SEATS["implementer"].preference
    assert dispatch.SEATS["review"].escalation != dispatch.SEATS["implementer"].escalation


def test_the_retro_and_orchestrator_rows_carry_the_escalation_entries_the_adr_tables() -> None:
    """#361: for one commit the ADR named these and the registry gave them none.

    Ordered, and the order is the claim: ruling 4 takes the *head*, so a tuple that agreed as
    a set and disagreed on order would resolve a different arbiter. `retro`'s head is not
    `fable-high` and `orchestrator`'s is not `opus-xhigh` — each seat's own preference head,
    and the profile most likely to have authored what the arbiter would adjudicate.
    """
    assert dispatch.SEATS["retro"].escalation == ("fable-xhigh", "opus-max")
    assert dispatch.SEATS["orchestrator"].escalation == ("opus-max", "fable-xhigh")
    assert dispatch.SEATS["retro"].escalation[0] != dispatch.SEATS["retro"].preference[0]
    assert (
        dispatch.SEATS["orchestrator"].escalation[0] != dispatch.SEATS["orchestrator"].preference[0]
    )


def test_the_orchestrator_arbiters_stay_on_the_lane_its_carve_out_names() -> None:
    """Ruling 1 keeps orchestration on Claude; an arbiter off it would be a way round that."""
    seat = dispatch.SEATS["orchestrator"]
    assert seat.claude_only
    for name in seat.escalation:
        assert dispatch.PROFILES[name].lane == "claude-native", name


def test_the_arbiter_is_the_implementing_seats_head_and_never_the_implementers_for_all() -> None:
    """ADR-0071 ruling 4 as A1 amends it: whichever seat did the work, not the `implementer` row.

    The reading A1 reversed answered every seat with `codex-sol-high`, which is what
    `tools/brief.py` emitted for a retro brief until #361.
    """
    assert dispatch.escalation_head("retro") == "fable-xhigh"
    assert dispatch.escalation_head("orchestrator") == "opus-max"
    assert dispatch.escalation_head("implementer") == "codex-sol-high"
    assert dispatch.escalation_head("planner") == "fable-high"


def test_a_seat_with_no_escalation_entry_resolves_to_no_arbiter_rather_than_a_default() -> None:
    """A1 struck the blanket `fable-high`, so an empty cell refuses rather than defaulting.

    `recon` is empty because it never escalates and `fable` because it is absent from the
    table; the registry spells both `()`, and neither may reach a profile nobody chose. An
    unknown seat is the same answer for the same reason — deriving an arbiter for a name that
    resolves to no row is the invention the amendment exists to stop.
    """
    assert dispatch.escalation_head("recon") is None
    assert dispatch.escalation_head("fable") is None
    assert dispatch.escalation_head("implemeter") is None


def test_the_retired_mechanical_seat_is_gone_from_every_roster() -> None:
    """ADR-0071 ruling 2 retires it, and story 11 asks for gone rather than lingering."""
    ledger = load_tool("ledger")
    assert "mechanical" not in dispatch.SEATS
    assert "mechanical" not in ledger.SEAT_LANDS
    # The admission bar's `SEAT_BARS` was the third roster this asserted against. #328
    # dropped that bar, so the roster is gone rather than the seat merely absent from it.
    assert not hasattr(load_tool("trial"), "SEAT_BARS")


# --------------------------------------------------------------- resolution, criterion 1


def test_naming_only_a_seat_resolves_a_profile_and_plans_the_dispatch(tmp_path: Path) -> None:
    # The human's ruling of 2026-08-27 puts GLM-5.3-Flash in front of Luna, and this
    # arrangement carries no z.ai credential, so the head is walked past for the reason the
    # module docstring prefers — absent key, not the hour — and Luna is what a bare `--seat`
    # reaches. The instant is injected so the *reason* is the credential at any hour.
    plan, _, refusal = plan_for(tmp_path, now=OFF_PEAK)
    assert refusal is None
    assert plan is not None
    assert plan.identity.profile == "codex-luna-max"
    assert plan.identity.lane == "codex"
    assert plan.route.named is False
    assert walked_past(plan.route.passed_over) == [
        ("zai-glm53flash-max", "credentials_missing"),
    ]


def test_the_dry_run_prints_the_resolved_profile_and_why_that_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Criterion 1, through the command line the criterion names.

    The instant is injected for the module docstring's reason: the z.ai entry must be
    walked past on its absent credential, and inside the published peak band it would be
    walked past on the hour instead, which is a different claim (#341). The codex rung is
    tripped so that the list is walked at all — since #405 it resolves, and a criterion
    about *which entries were passed over and why* needs a list with something in front of
    the answer.
    """
    worktree = git_worktree(tmp_path)
    trip(tmp_path, "codex", breaker.GATE_FAILED, 3)
    code = dispatch.main(seat_only_argv(tmp_path, worktree, "--dry-run"), now=OFF_PEAK)
    printed = capsys.readouterr().out
    assert code == 0, printed
    assert "route=seat seat=implementer" in printed
    assert "route_chosen=opus-low lane=claude-native" in printed
    # The reason is which entries were passed over and on what — not a bare "chosen".
    assert "route_passed_over=codex-luna-max refusal=lane_breaker_open" in printed
    assert "route_passed_over=zai-glm53flash-max refusal=credentials_missing" in printed


def test_a_blocked_entry_is_stepped_past_rather_than_dispatched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pair block is a skip for a resolver and a refusal for a caller who names it.

    Staged, because the list ships empty since #405 — the mechanism is ADR-0071 ruling 2's
    and outlives the one entry it was built for, so the claim is made against an entry this
    test supplies rather than dropped with the ceiling that supplied the last one.
    """
    monkeypatch.setattr(dispatch, "SEAT_PROFILE_BLOCKS", {("implementer", "codex-luna-max"): "#1"})
    plan, _, refusal = plan_for(tmp_path)
    assert refusal is None
    assert plan is not None
    assert ("codex-luna-max", "profile_blocked_for_seat") in walked_past(plan.route.passed_over)


def test_a_seat_whose_head_is_live_resolves_to_it_and_passes_nothing_over(
    tmp_path: Path,
) -> None:
    # GLM-5.3-Flash heads the `recon` list since the human's ruling of 2026-08-27, so a
    # seat's head is what a bare `--seat` resolves to when the world is not staged against
    # it — which for a z.ai head means a key on disk and an hour outside the published peak
    # band, both supplied here rather than left to the clock.
    (tmp_path / "credentials.env").write_text(f"ZAI_API_KEY={FAKE_TOKEN}\n", encoding="utf-8")
    (tmp_path / "credentials.env").chmod(0o600)
    plan, _, refusal = plan_for(tmp_path, seat="recon", now=OFF_PEAK)
    assert refusal is None
    assert plan is not None
    assert plan.identity.profile == "zai-glm53flash-high"
    assert walked_past(plan.route.passed_over) == []


# ------------------------------------------------ the breaker, criterion 2, and off-peak


def test_a_breaker_refused_head_resolves_to_the_next_entry_and_the_record_says_so(
    tmp_path: Path,
) -> None:
    """Criterion 2, on the seat whose list spans two lanes."""
    trip(tmp_path, "claude-native", breaker.GATE_FAILED, 3)
    plan, _, refusal = plan_for(tmp_path, seat="retro")
    assert refusal is None
    assert plan is not None
    assert plan.identity.profile == "codex-sol-max"
    assert walked_past(plan.route.passed_over) == [
        ("fable-high", "lane_breaker_open"),
        ("opus-xhigh", "lane_breaker_open"),
    ]


def test_a_passed_over_entry_keeps_the_failure_class_its_own_refusal_carried(
    tmp_path: Path,
) -> None:
    # A quality trip is `provider_refused` and a quota trip is `quota_exhausted`; the
    # record must carry which, because "the head was unavailable" is not a fact anyone can
    # act on later.
    trip(tmp_path, "claude-native", breaker.GATE_FAILED, 3)
    plan, _, _ = plan_for(tmp_path, seat="retro")
    assert plan is not None
    assert [entry.failure_class for entry in plan.route.passed_over] == [
        "provider_refused",
        "provider_refused",
    ]


def test_the_off_peak_rule_walks_the_zai_entry_past_rather_than_overriding_it(
    tmp_path: Path,
) -> None:
    """The human's hard rule of 2026-08-05 is a rung here too, and resolution never lifts it."""
    (tmp_path / "credentials.env").write_text(f"ZAI_API_KEY={FAKE_TOKEN}\n", encoding="utf-8")
    (tmp_path / "credentials.env").chmod(0o600)
    trip(tmp_path, "codex", breaker.GATE_FAILED, 3)
    plan, _, refusal = plan_for(tmp_path, now=PEAK)
    assert refusal is None
    assert plan is not None
    assert plan.identity.profile == "opus-low", "the z.ai entry is skipped inside the peak band"
    assert ("zai-glm53flash-max", "lane_peak_hours") in walked_past(plan.route.passed_over)


# ------------------------------------------------------------- exhaustion, criterion 3


def test_a_seat_whose_whole_list_is_unavailable_refuses_by_name(tmp_path: Path) -> None:
    trip(tmp_path, "claude-native", breaker.GATE_FAILED, 3)
    trip(tmp_path, "codex", breaker.GATE_FAILED, 3)
    plan, _, refusal = plan_for(tmp_path, seat="retro")
    assert plan is None
    assert refusal is not None
    assert refusal.kind == "seat_list_exhausted"
    found = " ".join(refusal.found)
    assert "seat=retro" in found
    assert "preference=fable-high opus-xhigh codex-sol-max" in found
    for name in ("fable-high", "opus-xhigh", "codex-sol-max"):
        assert f"refused={name} refusal=lane_breaker_open" in found


def test_exhaustion_never_falls_back_to_the_escalation_entry(tmp_path: Path) -> None:
    """An escalation is a judgement about the work, and resolution must not spend one for you."""
    trip(tmp_path, "claude-native", breaker.GATE_FAILED, 3)
    trip(tmp_path, "codex", breaker.GATE_FAILED, 3)
    trip(tmp_path, "zai", breaker.GATE_FAILED, 3)
    plan, _, refusal = plan_for(tmp_path)
    assert plan is None
    assert refusal is not None
    assert refusal.kind == "seat_list_exhausted"
    # The implementer's escalation entry is named in the refusal as something the reader
    # may choose — never as something already chosen.
    assert "escalation=codex-sol-high zai-glm53-max opus-high" in refusal.found
    assert all(not line.startswith("refused=codex-sol-high") for line in refusal.found)


def test_the_exhaustion_refusal_carries_no_failure_class_of_its_own(tmp_path: Path) -> None:
    """Its constituents' classes travel with them; a flattened one would be a wrong one."""
    trip(tmp_path, "claude-native", breaker.GATE_FAILED, 3)
    trip(tmp_path, "codex", breaker.GATE_FAILED, 3)
    _, _, refusal = plan_for(tmp_path, seat="retro")
    assert refusal is not None
    assert refusal.failure_class == ""
    assert any("class=provider_refused" in line for line in refusal.found)


def test_the_exhaustion_remedy_is_a_command_line_the_cli_actually_accepts(
    tmp_path: Path,
) -> None:
    """#321's review, finding 1: the old remedy named `--profile` and the CLI refuses that.

    The claim is about a command line, so it is made against the parser and the
    required-option check rather than through planning: what a reader types is refused or
    accepted before any route is resolved, and `incomplete_request missing=--lane` is
    exactly what the superseded wording earned.
    """
    for lane in ("claude-native", "codex", "zai"):
        trip(tmp_path, lane, breaker.GATE_FAILED, 3)
    _, _, refusal = plan_for(tmp_path)
    assert refusal is not None
    template = next(part for part in refusal.action.split("`") if part.startswith("just dispatch "))
    typed = (
        template.removeprefix("just dispatch ")
        .replace("<lane>", "claude-native")
        .replace("<profile>", "opus-high")
        .replace("<n>", "223")
        .split()
    )
    assert dispatch.missing_required(dispatch.parse_args(typed)) == ()


def test_the_exhaustion_remedy_names_the_escalation_entry_beside_its_lane(
    tmp_path: Path,
) -> None:
    """An escalation is only typeable with the lane it lives on, since the pair travels."""
    for lane in ("claude-native", "codex", "zai"):
        trip(tmp_path, lane, breaker.GATE_FAILED, 3)
    _, _, refusal = plan_for(tmp_path)
    assert refusal is not None
    assert "escalation entry is codex-sol-high zai-glm53-max opus-high" in refusal.action
    assert "--lane codex --profile codex-sol-high" in refusal.action


def test_a_seat_with_no_escalation_entry_is_told_so_rather_than_offered_a_non_thing(
    tmp_path: Path,
) -> None:
    """`recon` registers none, and the old text put `none registered` where a name goes.

    `retro` carried this pin until the human ruling on #361 (2026-08-14) filled its cell:
    every seat that can run a review loop out of rounds now names its arbiter, and the
    only empty columns left are the ones that ruling marked not-applicable.
    """
    trip(tmp_path, "claude-native", breaker.GATE_FAILED, 3)
    trip(tmp_path, "codex", breaker.GATE_FAILED, 3)
    _, _, refusal = plan_for(tmp_path, seat="recon")
    assert refusal is not None
    assert "escalation=none" in refusal.found
    assert "none registered" not in refusal.action
    assert "The recon seat registers no escalation entry" in refusal.action


def test_an_unknown_seat_is_refused_before_any_list_is_walked(tmp_path: Path) -> None:
    _, _, refusal = plan_for(tmp_path, seat="implemeter")
    assert refusal is not None
    assert refusal.kind == "unknown_seat"


# ------------------------------------------------- naming a profile, criteria 4 and 6/7


def test_naming_a_profile_still_dispatches_and_is_recorded_as_the_callers_choice(
    tmp_path: Path,
) -> None:
    plan, _, refusal = plan_for(tmp_path, lane="claude-native", profile="opus-high")
    assert refusal is None
    assert plan is not None
    assert plan.identity.profile == "opus-high"
    assert plan.route.named is True
    assert plan.route.passed_over == ()


def test_naming_a_blocked_profile_is_refused_rather_than_resolved_around(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--profile` is a way of choosing, never a way around a `(profile, seat)` block.

    Staged like its sibling above, for the same reason: the list ships empty since #405 and
    the rule it enforces is the ADR's rather than that one entry's.
    """
    monkeypatch.setattr(dispatch, "SEAT_PROFILE_BLOCKS", {("implementer", "codex-luna-max"): "#1"})
    plan, _, refusal = plan_for(tmp_path, lane="codex", profile="codex-luna-max")
    assert plan is None
    assert refusal is not None
    assert refusal.kind == "profile_blocked_for_seat"


def test_naming_the_codex_rung_for_the_implementer_seat_now_dispatches(tmp_path: Path) -> None:
    """#405: the pair that was the block list's only entry is an ordinary dispatch now.

    And its brief carries the seam the sandbox forces — the session gates, the harness
    commits, and the path between them is named once in code. Claimed here rather than
    beside `harness_finish` because reaching it means planning a whole dispatch, which is
    what this module is for. A session told to commit would spend its run against a sandbox
    that refuses; a session told nothing would leave a tree the harness refuses.
    """
    plan, brief, refusal = plan_for(tmp_path, lane="codex", profile="codex-luna-max")
    assert refusal is None
    assert plan is not None
    assert plan.identity.profile == "codex-luna-max"
    assert plan.route.named is True
    assert dispatch.CODEX_COMMIT_MESSAGE in brief
    assert "you gate, the harness commits" in brief


def test_a_brief_for_a_session_that_can_commit_says_none_of_the_seam(tmp_path: Path) -> None:
    """The protocol is a property of one sandbox, not of this project.

    Both halves are asserted — the writable Codex mode carries it above, and neither a
    Claude-family dispatch nor a read-only Codex seat does — because a brief that carried it
    everywhere would tell sessions that commit their own work not to.
    """
    worktree = git_worktree(tmp_path)
    _plan, claude_brief, refusal = plan_for(
        tmp_path, worktree=worktree, lane="claude-native", profile="opus-low"
    )
    assert refusal is None
    assert dispatch.CODEX_COMMIT_MESSAGE not in claude_brief
    _plan, recon_brief, refusal = plan_for(
        tmp_path, worktree=worktree, lane="codex", profile="codex-luna-medium", seat="recon"
    )
    assert refusal is None
    assert dispatch.CODEX_COMMIT_MESSAGE not in recon_brief


def test_naming_a_profile_without_its_lane_is_refused_rather_than_completed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = dispatch.main(["--seat", "implementer", "--issue", "223", "--profile", "opus-high"])
    assert code == dispatch.EXIT_REFUSED
    printed = capsys.readouterr().err
    assert "refusal=incomplete_request" in printed
    assert "missing=--lane" in printed


def test_a_request_with_neither_lane_nor_profile_is_complete(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The whole point of the seat: naming one, with an issue, is a whole request.

    Deliberately **not** `--list`. `answer_directly` serves the registry before
    `missing_required` runs at all, so a `--list` arrangement would stay green if seat-only
    dispatch started demanding a lane again — it never reaches the check it names (#321's
    review, finding 3). A dry run is the cheapest command line that passes required-option
    validation and then goes on to plan the dispatch the request describes.
    """
    worktree = git_worktree(tmp_path)
    code = dispatch.main(seat_only_argv(tmp_path, worktree, "--dry-run"))
    printed = capsys.readouterr()
    assert code == 0, printed.err
    assert "refusal=incomplete_request" not in printed.err
    assert "seat=implementer" in printed.out


# --------------------------------------------------------- the record, criteria 3 and 5


def test_the_record_names_the_chosen_profile_and_what_it_walked_past(tmp_path: Path) -> None:
    # Tripped so the walk has something to record: the record's claim is about entries that
    # were passed over, which needs a list that was actually walked (#405).
    trip(tmp_path, "codex", breaker.GATE_FAILED, 3)
    plan, brief, refusal = plan_for(tmp_path)
    assert refusal is None
    assert plan is not None
    dispatch.write_record(plan, brief, tmp_path / "review")
    document = json.loads((plan.record / "dispatch.json").read_text(encoding="utf-8"))
    assert document["profile"] == "opus-low"
    assert document["route"]["named"] is False
    assert document["route"]["seat"] == "implementer"
    assert document["route"]["chosen"] == "opus-low"
    assert [entry["profile"] for entry in document["route"]["passed_over"]] == [
        "zai-glm53flash-max",
        "codex-luna-max",
    ]


def test_a_recorded_route_reads_back_as_the_route_that_was_written(tmp_path: Path) -> None:
    plan, brief, _ = plan_for(tmp_path)
    assert plan is not None
    dispatch.write_record(plan, brief, tmp_path / "review")
    assert dispatch.load_record(plan.record) == plan


def test_a_record_written_before_routes_existed_reads_back_as_the_named_route_it_was(
    tmp_path: Path,
) -> None:
    """Every dispatch before #321 named its profile, because naming it was the only way."""
    plan, brief, _ = plan_for(tmp_path, lane="claude-native", profile="opus-high")
    assert plan is not None
    dispatch.write_record(plan, brief, tmp_path / "review")
    path = plan.record / "dispatch.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    del document["route"]
    path.write_text(json.dumps(document), encoding="utf-8")
    route = dispatch.load_record(plan.record).route
    assert route.named is True
    assert route.profile == "opus-high"
    assert route.passed_over == ()


# ------------------------------------------------- the record as a stage arrival (#490)


def test_writing_an_implementer_record_arrives_at_implementation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The record laid down is the implementation stage reached (#490)."""
    root = tmp_path / "review"
    monkeypatch.setenv("CTI_REVIEW_DIR", str(root))
    attribute_registry.record_stage_arrival("brief", 223, root, PEAK.timestamp())
    plan, brief, _ = plan_for(tmp_path)
    assert plan is not None
    dispatch.write_record(plan, brief, tmp_path / "review")
    rows = [
        json.loads(line)
        for line in (root / "223" / attribute_registry.STAGE_JOURNAL)
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert [row["attributes"]["cti.stage.name"] for row in rows] == ["brief", "implementation"]
    assert rows[-1]["attributes"]["cti.dispatch_id"] == plan.identity.dispatch_id


def test_writing_a_review_record_arrives_at_review_not_implementation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stage is `review`, and the arrival lands at the root the caller named (#677).

    The environment deliberately names a different root: since #677 the arrival
    follows `write_record`'s parameter — one decision per process, the caller's root
    over the environment's — so the journal is read from the parameter's root and the
    environment's stays empty.
    """
    environment_root = tmp_path / "review"
    parameter_root = tmp_path / "review-records"
    monkeypatch.setenv("CTI_REVIEW_DIR", str(environment_root))
    plan, brief, _ = plan_for(
        tmp_path, seat="review", reviewing="opus-high", review_root=str(parameter_root)
    )
    assert plan is not None
    dispatch.write_record(plan, brief, parameter_root)
    (row,) = [
        json.loads(line)
        for line in (parameter_root / "223" / attribute_registry.STAGE_JOURNAL)
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert row["attributes"]["cti.stage.name"] == "review"
    assert not (environment_root / "223").exists()


def test_a_planner_dispatch_records_no_arrival(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A planner dispatch is not a pass through the work-item pipeline."""
    root = tmp_path / "review"
    monkeypatch.setenv("CTI_REVIEW_DIR", str(root))
    plan, brief, _ = plan_for(tmp_path, seat="planner")
    assert plan is not None
    dispatch.write_record(plan, brief, tmp_path / "review")
    assert not (root / "223").exists()


# ------------------------------------------------------------------ the registry listing


def test_the_registry_listing_prints_each_seats_preference_and_marks_the_escalation(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert dispatch.main(["--list"]) == 0
    printed = capsys.readouterr().out
    assert "preference=zai-glm53flash-max codex-luna-max opus-low" in printed
    # The mark names *which* resolution passes the entry by (#361 review round 2, claim 3): a
    # flat "not resolved into" was false from the moment `tools/arbiter.py`'s walk landed at
    # `d351a3f`, since that walk starts at this very entry.
    mark = "(not a dispatch route; walked first by the arbiter)"
    assert f"escalation=codex-sol-high zai-glm53-max opus-high {mark}" in printed
    # `fable` and `recon` are the rows that still register none; #361 filled `retro`'s and
    # `orchestrator`'s, and the listing is the surface that said `none` while the ADR named a
    # profile. Both halves are asserted so a future fill cannot quietly empty this claim. An
    # empty row takes the *other* mark: there is nothing for the arbiter to walk first, so the
    # row that says so would be asserting a walk it does not get (#361, round 4).
    assert "escalation=none (no arbiter; escalation refuses by name)" in printed
    assert f"escalation=none {mark}" not in printed
    assert f"escalation=fable-xhigh opus-max {mark}" in printed
    assert f"escalation=opus-max fable-xhigh {mark}" in printed
    assert "not resolved into" not in printed


def test_a_blocked_pair_reaches_the_listing_from_the_same_entry_the_refusal_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#320's finding, answered by shape rather than by a guard (#405).

    The disagreement that finding was about — a listed block the refusal clears — was
    possible while the ceiling was a string inside `pair_block` and the membership a set
    beside it, so the branch that raised on it earned its place. An entry now *is* its
    ceiling, so the listing and the refusal read the same value out of the same mapping and
    there is nothing left for the two halves to disagree about. The claim that replaces the
    guard is this: whatever the entry says, both surfaces say.
    """
    monkeypatch.setattr(dispatch, "SEAT_PROFILE_BLOCKS", {("implementer", "opus-low"): "#77"})
    listed = [line for line in dispatch.registry_lines() if line.startswith("seat_profile_block=")]
    refusal = dispatch.pair_block("implementer", "opus-low")
    assert refusal is not None
    assert listed == ["seat_profile_block=adr0071 seat=implementer profile=opus-low ceiling=#77"]
    assert "ceiling=#77" in refusal.found
