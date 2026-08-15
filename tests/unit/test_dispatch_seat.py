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
from typing import TYPE_CHECKING, Any

import pytest
from conftest import REPO, load_tool

if TYPE_CHECKING:
    from pathlib import Path

dispatch = load_tool("dispatch")
breaker = load_tool("breaker")

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

    The credentials file is deliberately absent by default. That is what makes the
    `implementer` list deterministic here: its Codex head is blocked for the seat and its
    z.ai entry cannot be reached without a key, so the native tail is what a box with no
    z.ai credential resolves to at any hour.
    """
    injected = overrides.pop("now", None)
    now = datetime.now(tz=UTC) if injected is None else injected
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
        "credentials": str(tmp_path / "credentials.env"),
        "breaker_dir": str(tmp_path / "breaker"),
        "admission_dir": str(tmp_path / "admission"),
        "issue_body": str(READY_BODY),
        "queue_dir": str(open_policy(tmp_path)),
        "queue_root": str(tmp_path / "queue-root"),
        # #322: what a non-review dispatch passes, and the fail-closed value for a review
        # one. The review arrangements below override it.
        "reviewing": "",
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
        "--admission-dir",
        str(tmp_path / "admission"),
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


def test_the_implementer_list_is_the_adrs_order_head_first() -> None:
    # Ordered, not a set: ADR-0071 ruling 2 gives the list head-first and resolution walks
    # it in exactly that order, so the sequence is the claim.
    assert dispatch.SEATS["implementer"].preference == (
        "codex-luna-max",
        "zai-glm52-max",
        "opus-low",
    )
    assert dispatch.SEATS["implementer"].escalation == ("codex-sol-high", "opus-high")


def test_the_review_seat_shares_the_implementers_list_and_its_escalation_head() -> None:
    # "The implementer's list" is a fact about one list, not two lists that happen to agree
    # today: shared rather than copied, so an edit to one cannot leave the other behind.
    assert dispatch.SEATS["review"].preference == dispatch.SEATS["implementer"].preference
    assert dispatch.SEATS["review"].escalation == dispatch.SEATS["implementer"].escalation[:1]


def test_the_retro_and_orchestrator_rows_carry_the_escalation_entries_the_adr_tables() -> None:
    """#361: for one commit the ADR named these and the registry gave them none.

    Ordered, and the order is the claim: ruling 4 takes the *head*, so a tuple that agreed as
    a set and disagreed on order would resolve a different arbiter. `retro`'s head is not
    `fable-high` and `orchestrator`'s is not `opus-xhigh` — each seat's own preference head,
    and the profile most likely to have authored what the arbiter would adjudicate.
    """
    assert dispatch.SEATS["retro"].escalation == ("opus-max", "fable-max")
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
    assert dispatch.escalation_head("retro") == "opus-max"
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
    admission = load_tool("admission")
    assert "mechanical" not in dispatch.SEATS
    assert "mechanical" not in ledger.SEAT_LANDS
    assert "mechanical" not in admission.SEAT_BARS


# --------------------------------------------------------------- resolution, criterion 1


def test_naming_only_a_seat_resolves_a_profile_and_plans_the_dispatch(tmp_path: Path) -> None:
    plan, _, refusal = plan_for(tmp_path)
    assert refusal is None
    assert plan is not None
    assert plan.identity.profile == "opus-low"
    assert plan.identity.lane == "claude-native"
    assert plan.route.named is False


def test_the_dry_run_prints_the_resolved_profile_and_why_that_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Criterion 1, through the command line the criterion names.

    The instant is injected for the module docstring's reason: the z.ai entry must be
    walked past on its absent credential, and inside the published peak band it would be
    walked past on the hour instead, which is a different claim (#341).
    """
    worktree = git_worktree(tmp_path)
    code = dispatch.main(seat_only_argv(tmp_path, worktree, "--dry-run"), now=OFF_PEAK)
    printed = capsys.readouterr().out
    assert code == 0, printed
    assert "route=seat seat=implementer" in printed
    assert "route_chosen=opus-low lane=claude-native" in printed
    # The reason is which entries were passed over and on what — not a bare "chosen".
    assert "route_passed_over=codex-luna-max refusal=profile_blocked_for_seat" in printed
    assert "route_passed_over=zai-glm52-max refusal=credentials_missing" in printed


def test_the_blocked_head_is_stepped_past_rather_than_dispatched(tmp_path: Path) -> None:
    """The pair block is a skip for a resolver and a refusal for a caller who names it."""
    plan, _, refusal = plan_for(tmp_path)
    assert refusal is None
    assert plan is not None
    assert ("codex-luna-max", "profile_blocked_for_seat") in walked_past(plan.route.passed_over)


def test_a_seat_whose_head_is_live_resolves_to_it_and_passes_nothing_over(
    tmp_path: Path,
) -> None:
    # `recon` is read-only, so #265's gate ceiling does not reach it and Luna heads the
    # list unimpeded. The same profile, a different seat, a different answer — which is
    # ADR-0071 ruling 2's point about the block attaching to the pair.
    plan, _, refusal = plan_for(tmp_path, seat="recon")
    assert refusal is None
    assert plan is not None
    assert plan.identity.profile == "codex-luna-medium"
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
    assert plan.identity.profile == "codex-sol-xhigh"
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
    plan, _, refusal = plan_for(tmp_path, now=PEAK)
    assert refusal is None
    assert plan is not None
    assert plan.identity.profile == "opus-low", "the z.ai entry is skipped inside the peak band"
    assert ("zai-glm52-max", "lane_peak_hours") in walked_past(plan.route.passed_over)


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
    assert "preference=fable-high opus-xhigh codex-sol-xhigh" in found
    for name in ("fable-high", "opus-xhigh", "codex-sol-xhigh"):
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
    # `codex-sol-high` and `opus-high` are the implementer's escalation and are named in
    # the refusal as something the reader may choose — never as something already chosen.
    assert "escalation=codex-sol-high opus-high" in refusal.found
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
    assert "escalation entry is codex-sol-high opus-high" in refusal.action
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
    tmp_path: Path,
) -> None:
    """`--profile` is a way of choosing, never a way around a `(profile, seat)` block."""
    plan, _, refusal = plan_for(tmp_path, lane="codex", profile="codex-luna-max")
    assert plan is None
    assert refusal is not None
    assert refusal.kind == "profile_blocked_for_seat"


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
    plan, brief, refusal = plan_for(tmp_path)
    assert refusal is None
    assert plan is not None
    dispatch.write_record(plan, brief)
    document = json.loads((plan.record / "dispatch.json").read_text(encoding="utf-8"))
    assert document["profile"] == "opus-low"
    assert document["route"]["named"] is False
    assert document["route"]["seat"] == "implementer"
    assert document["route"]["chosen"] == "opus-low"
    assert [entry["profile"] for entry in document["route"]["passed_over"]] == [
        "codex-luna-max",
        "zai-glm52-max",
    ]


def test_a_recorded_route_reads_back_as_the_route_that_was_written(tmp_path: Path) -> None:
    plan, brief, _ = plan_for(tmp_path)
    assert plan is not None
    dispatch.write_record(plan, brief)
    assert dispatch.load_record(plan.record) == plan


def test_a_record_written_before_routes_existed_reads_back_as_the_named_route_it_was(
    tmp_path: Path,
) -> None:
    """Every dispatch before #321 named its profile, because naming it was the only way."""
    plan, brief, _ = plan_for(tmp_path, lane="claude-native", profile="opus-high")
    assert plan is not None
    dispatch.write_record(plan, brief)
    path = plan.record / "dispatch.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    del document["route"]
    path.write_text(json.dumps(document), encoding="utf-8")
    route = dispatch.load_record(plan.record).route
    assert route.named is True
    assert route.profile == "opus-high"
    assert route.passed_over == ()


# ------------------------------------------------------------------ the registry listing


def test_the_registry_listing_prints_each_seats_preference_and_marks_the_escalation(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert dispatch.main(["--list"]) == 0
    printed = capsys.readouterr().out
    assert "preference=codex-luna-max zai-glm52-max opus-low" in printed
    assert "escalation=codex-sol-high opus-high (not resolved into)" in printed
    # `fable` and `recon` are the rows that still register none; #361 filled `retro`'s and
    # `orchestrator`'s, and the listing is the surface that said `none` while the ADR named a
    # profile. Both halves are asserted so a future fill cannot quietly empty this claim.
    assert "escalation=none (not resolved into)" in printed
    assert "escalation=opus-max fable-max (not resolved into)" in printed
    assert "escalation=opus-max fable-xhigh (not resolved into)" in printed


def test_a_block_the_registry_carries_and_the_refusal_clears_is_raised_not_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#320's recorded finding: the branch failed open where its assertion had failed loudly.

    The divergence cannot be staged through the block set alone — `pair_block` reads the
    same constant, so patching it keeps the two halves in agreement, which is exactly why
    the branch is unreachable in the real registry. Staged through the refusal instead: a
    `pair_block` that clears a member is precisely the disagreement the branch exists for,
    and the listing must say so rather than print a registry with the block missing.
    """
    monkeypatch.setattr(dispatch, "pair_block", lambda _seat, _profile: None)
    with pytest.raises(ValueError, match="pair_block cleared it"):
        dispatch.registry_lines()
