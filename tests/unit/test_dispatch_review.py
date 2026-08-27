"""The review seat cannot review its own profile or affect the reviewed ref (#322, ADR-0071).

Two halves of one invariant: no single model instance may both propose a change and produce
the verdict that clears it. The first half is resolution — the profile under review is an
input, it is removed before the list is walked, and a different lane goes first among what
is left. The second is containment — the seat forces `plan`, runs in a dispatch-owned
disposable tree, and never lands that tree, on both runner families.

Claims are made through `plan_dispatch` or `main` wherever the criterion is about a dispatch,
following `test_dispatch_seat.py`'s rule: what a caller gets is a plan or a refusal, and a
resolver that returned the right token while the ladder below refused the route would satisfy
an internal test and none of the criteria.

**The lane-ordering rule is observable against the real registry, and is claimed there.**
`--reviewing` takes any registered profile and not only an entry of the seat's own
preference, so a subject from outside it leaves all three entries in the list and reorders
them: reviewing `codex-sol-high` puts the two non-Codex entries first, and a box with no
z.ai key therefore answers `opus-medium` where the seat's unmodified order would have
answered `codex-sol-xhigh`. An earlier draft of this module asserted the opposite — that three
distinct lanes made the rule unobservable end to end — and that was simply wrong. The
substituted-seat claims below are kept because they exercise the ordering *within* each
half, which the real three-entry preference is too short to show; they are not a stand-in
for a real-registry arrangement that does not exist.

**What the records support is a potential-author set, and the claims say so.** A dispatch
record is written at plan time and names a profile, a seat and an issue; nothing on it names
the commits a run produced. So the profiles read off this issue's records are the ones the
box cannot rule out, every one of them is removed from the candidate list — over-excluding
costs a resolution step, under-excluding costs the invariant — and the route records the
subject as *checked* rather than *verified*. The claims below are made in that vocabulary
deliberately: an earlier draft called the same set "the authors", and a superset presented as
a derivation is how a coauthor came to be eligible to review its own work.

Arrangements that need that read plant dispatch records of their own, under this test's
`--dispatch-dir` and never this box's, so the suite's answer never depends on what was
dispatched here today.

Arrangements are **clock-free** for `test_dispatch_seat.py`'s reason: entries are walked past
by tripping a breaker or withholding a lane credential, both of which hold at any hour, where
staging z.ai's published band would make the suite's answer depend on when it ran.

**A renamed profile's old name is a subject and never a route** (#413). The dispatch records
carry the name the work ran under, forever; after #399 renamed `zai-glm52-max` there is no
answer `--reviewing` could give that both resolves and matches the records. The retirement
table in `tools/dispatch.py` resolves the old name for reading — the subject check, the
candidate ordering, the exclusion set — while `--profile` keeps reading `PROFILES` alone and
refusing the dead name. The claims are in that vocabulary: a retired name is *carried by the
records*, and its successor is *excluded like the author it replaced*.
"""

from __future__ import annotations

import json
import subprocess
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final

import pytest
from conftest import REPO, load_tool

if TYPE_CHECKING:
    from pathlib import Path

dispatch = load_tool("dispatch")
breaker = load_tool("breaker")
queue_policy = load_tool("queue_policy")
review_loop = load_tool("review_loop")

READY_BODY = REPO / "tests" / "fixtures" / "routing-eligible.md"

# The profile whose work is under review in the arrangements that do not vary it. Native,
# and deliberately not one of the review seat's own preference entries, so that a test about
# containment or about the record is not also a test about exclusion.
REVIEWED = "opus-high"


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


def trip(tmp_path: Path, lane: str, count: int = 3) -> None:
    """Stage a lane's breaker into a state that refuses, without touching this box's own."""
    store = breaker.Store(directory=tmp_path / "breaker", endpoint="http://127.0.0.1:2999/v1/logs")
    for step in range(count):
        breaker.record_outcome(
            store, lane, breaker.Outcome(breaker.GATE_FAILED), time.time() + step
        )


def dispatch_record(  # noqa: PLR0913 — one keyword per field of the record the scan reads; folding them into a dict would hide which field each arrangement varies
    tmp_path: Path,
    dispatch_id: str = "d-20260812-000000-aaaaaa",
    *,
    issue: int = 322,
    seat: str = "implementer",
    profile: str = "opus-high",
    refusal: str = "",
    lane: str = "",
) -> Path:
    """Plant a dispatch record of the shape `just dispatch` writes, for the scan to read.

    Named for what it is rather than for what it might have done: nothing this helper writes
    says the run produced a commit, because nothing on a real record says so either.

    The worktree is deliberately not the review's own. An implementer works in `issue-<n>`
    and a review in a tree of its own, and pointing both at one path would trip the occupancy
    rung (#308) rather than exercise the scan.

    `lane` is for a profile the registry no longer carries (#413): a retired name has no
    `PROFILES` entry to derive a lane from, and the record still states the lane it ran on —
    the scan reads only the profile, but the record stays the shape the writer writes.
    """
    directory = tmp_path / "dispatches" / dispatch_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "dispatch.json").write_text(
        json.dumps(
            {
                "dispatch_id": dispatch_id,
                "lane": lane or dispatch.PROFILES[profile].lane,
                "profile": profile,
                "seat": seat,
                "issue": issue,
                "worktree": str(tmp_path / f"authored-by-{dispatch_id}"),
            }
        ),
        encoding="utf-8",
    )
    if refusal:
        (directory / "result.json").write_text(
            json.dumps({"dispatch_id": dispatch_id, "refusal": refusal}), encoding="utf-8"
        )
    return directory


def plan_for(tmp_path: Path, **overrides: object) -> tuple[Any, str, Any]:
    """Plan a review dispatch over a real worktree, writing nothing.

    The credentials file is absent by default, which is what makes the arrangements
    deterministic: the z.ai entry cannot be reached without a key at any hour, so a review
    resolves over the Codex and native entries alone unless a test says otherwise.
    """
    injected = overrides.pop("now", None)
    now = datetime.now(tz=UTC) if injected is None else injected
    worktree = overrides.pop("worktree", None) or git_worktree(tmp_path)
    request = {
        "lane": "",
        "profile": "",
        "seat": "review",
        "reviewing": REVIEWED,
        "issue": 322,
        "worktree": str(worktree),
        "brief_file": "",
        "base_sha": "",
        # The writable default the dispatcher really has. Every containment claim below is
        # made against this value, because "without the caller passing anything" is the
        # criterion and passing `plan` here would test the caller rather than the seat.
        "permission_mode": "acceptEdits",
        "dispatch_dir": str(tmp_path / "dispatches"),
        # The declaration root is this test's own, for `--dispatch-dir`'s reason: a suite
        # whose author set depended on what this box declared today would not be a suite.
        "review_root": str(tmp_path / "review"),
        "credentials": str(tmp_path / "credentials.env"),
        "breaker_dir": str(tmp_path / "breaker"),
        "issue_body": str(READY_BODY),
        "queue_dir": str(open_policy(tmp_path)),
        "queue_root": str(tmp_path / "queue-root"),
    }
    request.update(overrides)
    return dispatch.plan_dispatch(type("Args", (), request)(), REPO, now)


def substitute_review_seat(
    monkeypatch: pytest.MonkeyPatch, *preference: str, escalation: tuple[str, ...] = ()
) -> None:
    """Give the `review` seat a preference list this test chose, keeping its other columns.

    Used where the claim is about ordering *within* one half of the reordering, or about a
    list the registry does not carry — three entries cannot show a two-entry half staying in
    order. `reviews` and `permission_mode` are carried across from the registered seat rather
    than restated, so a substitution cannot accidentally test a seat that reviews nothing.
    """
    real = dispatch.SEATS["review"]
    monkeypatch.setitem(
        dispatch.SEATS,
        "review",
        real._replace(preference=preference, escalation=escalation),
    )


# ------------------------------------------- criterion 1: never the profile under review


@pytest.mark.parametrize("reviewed", dispatch.SEATS["review"].preference)
def test_a_review_never_resolves_to_the_profile_whose_work_it_reviews(
    tmp_path: Path, reviewed: str
) -> None:
    """Criterion 1, over every entry the seat could otherwise have taken."""
    plan, _, refusal = plan_for(tmp_path, reviewing=reviewed)
    assert refusal is None, refusal
    assert plan is not None
    assert plan.identity.profile != reviewed


def test_removing_the_head_resolves_to_the_next_entry_rather_than_refusing(
    tmp_path: Path,
) -> None:
    plan, _, refusal = plan_for(tmp_path, reviewing="codex-sol-xhigh")
    assert refusal is None
    assert plan is not None
    # The z.ai entry needs a key this arrangement withholds, so the native tail is what a
    # box with no z.ai credential resolves to once the Codex head is the subject.
    assert plan.identity.profile == "opus-medium"
    assert plan.route.reviewed == "codex-sol-xhigh"


def test_the_removed_profile_is_not_recorded_as_passed_over(tmp_path: Path) -> None:
    """It was never a candidate, and "walked past on a refusal" would be a different fact.

    A reader reconciling a route reads `route_preference` against the passed-over entries;
    recording the subject as though a rung had refused it would attribute the exclusion to
    the breaker, the credential or the block, none of which said anything about it.
    """
    plan, _, _ = plan_for(tmp_path, reviewing="codex-sol-xhigh")
    assert plan is not None
    assert "codex-sol-xhigh" not in [entry.profile for entry in plan.route.passed_over]


# ------------------------------------------------- criterion 2: preferring a different lane


def test_a_different_lane_is_preferred_over_the_seats_own_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Criterion 2, end to end, on a list whose head shares the reviewed profile's lane."""
    substitute_review_seat(monkeypatch, "opus-xhigh", "opus-low", "codex-sol-high")
    plan, _, refusal = plan_for(tmp_path, reviewing=REVIEWED)
    assert refusal is None, refusal
    assert plan is not None
    # Without the lane preference the head `opus-xhigh` would have resolved: it is not the
    # subject, it is not blocked, and nothing here refuses it. The only reason the answer is
    # the Codex entry is that the two native entries share the reviewed profile's lane.
    assert plan.identity.profile == "codex-sol-high"
    assert plan.identity.lane == "codex"


def test_a_different_lane_is_preferred_against_the_real_registry(tmp_path: Path) -> None:
    """Criterion 2, end to end on the registered seat with nothing substituted.

    Reviewing `codex-sol-high` leaves all three preference entries in the list — the subject
    is not one of them — and only reorders them, putting the two non-Codex entries first.
    This arrangement withholds the z.ai key, so the answer is `opus-medium`. The seat's
    unmodified order would have answered `codex-sol-xhigh`: it is registered, it is not
    blocked for *this* seat, and the Codex lane needs no credential of ours, so it would have
    been dispatchable at the head. The two orders therefore disagree here, and the assertions
    below are the ordering rule and nothing else.
    """
    plan, _, refusal = plan_for(tmp_path, reviewing="codex-sol-high")
    assert refusal is None, refusal
    assert plan is not None
    assert plan.identity.profile == "opus-medium"
    assert plan.identity.lane == "claude-native"
    assert "route_preference=zai-glm53-max opus-medium codex-sol-xhigh" in plan.route.lines()
    # The Codex head was never reached, rather than reached and refused: only the z.ai entry
    # ahead of the answer was walked past, which is what the reordering did.
    assert [entry.profile for entry in plan.route.passed_over] == ["zai-glm53-max"]


def test_the_lane_preference_is_an_ordering_and_never_a_filter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The case the ADR's one word leaves open: only same-lane entries left, so one is used.

    Refusing here would confuse ruling 4's invariant — which is about the instance producing
    the verdict — with the provider it is reached through, and would refuse a genuinely
    different model for sharing an endpoint with the one under review.
    """
    substitute_review_seat(monkeypatch, "opus-xhigh", "opus-low")
    plan, _, refusal = plan_for(tmp_path, reviewing=REVIEWED)
    assert refusal is None, refusal
    assert plan is not None
    assert plan.identity.profile == "opus-xhigh"
    assert plan.identity.lane == "claude-native"


def test_the_seats_own_order_survives_inside_each_half() -> None:
    """Head-first is the ADR's ranking of the work, and the lane rule does not re-rank it."""
    seat = dispatch.SEATS["review"]._replace(
        preference=("opus-xhigh", "codex-sol-high", "opus-low", "codex-sol-max")
    )
    assert dispatch.review_candidates(seat, "opus-high") == (
        "codex-sol-high",
        "codex-sol-max",
        "opus-xhigh",
        "opus-low",
    )


def test_a_seat_that_reviews_nothing_walks_its_preference_untouched() -> None:
    """Every other seat's resolution is the function it always was."""
    for name, seat in dispatch.SEATS.items():
        if seat.reviews:
            continue
        assert dispatch.review_candidates(seat, "") == seat.preference, name
        # Even handed a subject, which nothing does: the column decides, not the argument.
        assert dispatch.review_candidates(seat, "opus-high") == seat.preference, name


# ------------------------------------- criterion 3: read-only, forced, on both runners


def test_a_claude_lane_review_runs_read_only_without_the_caller_passing_anything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    substitute_review_seat(monkeypatch, "opus-low")
    plan, _, refusal = plan_for(tmp_path)
    assert refusal is None, refusal
    assert plan is not None
    assert plan.identity.lane == "claude-native"
    assert plan.permission_mode == "plan"
    assert "--permission-mode" in plan.argv
    assert plan.argv[plan.argv.index("--permission-mode") + 1] == "plan"
    assert "acceptEdits" not in plan.argv


def test_a_codex_lane_review_runs_in_the_disposable_tree_without_the_caller_passing_anything(
    tmp_path: Path,
) -> None:
    """The other runner family, whose vocabulary for the same thing is a sandbox policy."""
    plan, _, refusal = plan_for(tmp_path, reviewing="opus-low")
    assert refusal is None, refusal
    assert plan is not None
    assert plan.identity.lane == "codex"
    assert plan.permission_mode == "plan"
    assert "--sandbox" in plan.argv
    assert plan.argv[plan.argv.index("--sandbox") + 1] == "workspace-write"
    assert [part for part in plan.argv if part.startswith("sandbox_workspace_write.")]
    assert "--dangerously-bypass-approvals-and-sandbox" not in plan.argv


@pytest.mark.parametrize("asked", ["acceptEdits", "bypassPermissions", "default"])
def test_the_seat_overrides_whatever_permission_mode_the_caller_typed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asked: str
) -> None:
    """Forced, not defaulted: a containment a caller can switch off with a flag is a default."""
    substitute_review_seat(monkeypatch, "opus-low")
    plan, _, refusal = plan_for(tmp_path, permission_mode=asked)
    assert refusal is None, refusal
    assert plan is not None
    assert plan.permission_mode == "plan"


def test_the_forcing_is_recorded_rather_than_silent(tmp_path: Path) -> None:
    """A reader who typed a writable mode and got a read-only run can see who overrode them."""
    plan, _, _ = plan_for(tmp_path)
    assert plan is not None
    lines = plan.route.lines()
    assert "route_permission_mode=plan forced_by_seat=review (no caller override)" in lines
    assert f"route_reviewing={REVIEWED} (never resolved to)" in lines


def test_no_other_seat_has_its_permission_mode_taken_away_from_the_caller(
    tmp_path: Path,
) -> None:
    """The default is still the default everywhere it was right: seats that commit and gate."""
    plan, _, refusal = plan_for(tmp_path, seat="implementer", reviewing="")
    assert refusal is None, refusal
    assert plan is not None
    assert plan.permission_mode == "acceptEdits"


def test_a_review_is_not_refused_for_the_surface_it_was_sent_to_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#339: the queue's surface rung read the implementer's tree as the review's writes.

    Two implementer trees in flight, both writing the same paths, and a review of one of
    them — the observed refusal fired exactly there, on the critical path every landing now
    takes (ADR-0071 ruling 4). The containment this file's criterion 3 forces is what makes
    "this dispatch writes nothing" derivable, so the surface rung reads an empty surface for
    such a seat rather than the issue's, and the refusal returns only without the column.
    """
    holders = (
        queue_policy.Holder(322, ("dispatch:d-1",), tmp_path / "issue-322"),
        queue_policy.Holder(324, ("dispatch:d-2",), tmp_path / "issue-324"),
    )
    surfaces = {
        322: ("CHANGELOG.md", "tools/dispatch.py"),
        324: ("CHANGELOG.md", "tools/dispatch.py"),
    }
    monkeypatch.setattr(
        dispatch.queue_policy, "gather", lambda *_: queue_policy.InFlight(holders, (), "read")
    )
    monkeypatch.setattr(dispatch.queue_policy, "surfaces_of", lambda _ignored: surfaces)
    tree = git_worktree(tmp_path)
    # 324, not 322: the lower-numbered holder is the one that makes the conflict observable.
    plan, _, refusal = plan_for(tmp_path, worktree=tree, issue=324)
    assert refusal is None, refusal
    assert plan is not None
    # The control: strip the column that derives emptiness and the rung sees the conflict
    # again, which is what pins the exemption to the registry rather than to a removed rung.
    monkeypatch.setitem(
        dispatch.SEATS,
        "review",
        dispatch.SEATS["review"]._replace(permission_mode=""),
    )
    plan, _, refusal = plan_for(tmp_path, worktree=tree, issue=324)
    assert plan is None
    assert refusal is not None
    assert refusal.kind == "surface_conflict"


# ----------------------------------------- criterion 4: it refuses rather than proceeding


def test_naming_the_reviewed_profile_is_refused_rather_than_dispatched(tmp_path: Path) -> None:
    """`--profile` is a way of choosing, never a way around (ADR-0071 ruling 2)."""
    plan, _, refusal = plan_for(
        tmp_path, lane="claude-native", profile="opus-low", reviewing="opus-low"
    )
    assert plan is None
    assert refusal is not None
    assert refusal.kind == "review_same_profile"
    assert "why=named" in refusal.found
    assert refusal.failure_class == ""


def test_a_list_offering_nothing_but_the_reviewed_profile_refuses_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Criterion 4's own case: removal empties the list, so there is no route but the subject."""
    substitute_review_seat(monkeypatch, "opus-low")
    plan, _, refusal = plan_for(tmp_path, reviewing="opus-low")
    assert plan is None
    assert refusal is not None
    assert refusal.kind == "review_same_profile"
    assert "why=list_offers_nothing_else" in refusal.found
    assert "candidates=none" in refusal.found
    # The refusal is the point of the ticket, so it says so rather than reading as a fault.
    assert "this refusal is the point" in refusal.action


def test_the_same_profile_refusal_carries_no_failure_class(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing was found about a provider, a lane or the code under test (CLAUDE.md's table)."""
    substitute_review_seat(monkeypatch, "opus-low")
    _, _, refusal = plan_for(tmp_path, reviewing="opus-low")
    assert refusal is not None
    assert refusal.failure_class == ""


def test_a_review_that_declares_no_subject_refuses_rather_than_taking_the_head(
    tmp_path: Path,
) -> None:
    """The absent case is a refusal, because the alternative is a silent same-model review."""
    plan, _, refusal = plan_for(tmp_path, reviewing="")
    assert plan is None
    assert refusal is not None
    assert refusal.kind == "review_subject_unknown"
    assert "--reviewing <profile>" in refusal.action


def test_a_subject_the_registry_does_not_carry_is_refused_rather_than_ignored(
    tmp_path: Path,
) -> None:
    """A typo would resolve past nothing, which is the same-model review wearing a flag."""
    plan, _, refusal = plan_for(tmp_path, reviewing="opus-hgih")
    assert plan is None
    assert refusal is not None
    assert refusal.kind == "unknown_reviewed_profile"


def test_declaring_a_subject_on_a_seat_that_reviews_nothing_is_refused(tmp_path: Path) -> None:
    """An option that silently decides nothing is one a caller will believe did something."""
    plan, _, refusal = plan_for(tmp_path, seat="implementer", reviewing=REVIEWED)
    assert plan is None
    assert refusal is not None
    assert refusal.kind == "reviewing_without_review_seat"


# ------------------ criterion 4, again: the subject is checked, not merely declared


def test_a_declaration_the_issues_records_contradict_is_refused(tmp_path: Path) -> None:
    """The defeat the first review found: two registered names satisfied every check.

    `--profile opus-high --reviewing codex-luna-max` names two profiles the registry carries,
    so the equality check passes and the implementing instance produces the verdict on its
    own work while the record names somebody else. The issue's own records carry a different
    profile, so the declaration a complete read of them contradicts is the half that loses.
    """
    dispatch_record(tmp_path, profile="opus-high")
    plan, _, refusal = plan_for(
        tmp_path, lane="claude-native", profile="opus-high", reviewing="codex-luna-max"
    )
    assert plan is None
    assert refusal is not None
    assert refusal.kind == "review_subject_contradicted"
    assert "potential_authors=opus-high" in refusal.found
    assert "records=d-20260812-000000-aaaaaa" in refusal.found
    # Nothing was found about a provider, a lane or the code under test (CLAUDE.md's table).
    assert refusal.failure_class == ""


def test_the_contradiction_is_refused_on_a_resolved_route_too(tmp_path: Path) -> None:
    """Naming no profile at all does not buy a false subject: the check is above both routes."""
    dispatch_record(tmp_path, profile="opus-high")
    plan, _, refusal = plan_for(tmp_path, reviewing="codex-luna-max")
    assert plan is None
    assert refusal is not None
    assert refusal.kind == "review_subject_contradicted"


def test_a_declaration_the_records_carry_is_recorded_as_checked_and_not_as_verified(
    tmp_path: Path,
) -> None:
    """The positive answer, in the only vocabulary the records support.

    `checked` says the declared subject is among the profiles this box's records place on the
    issue and that every one of them was excluded. It deliberately does not say any of them
    wrote a line: nothing on a dispatch record names the commits a run produced, and a
    landing check reading `verified` here would be reading a guarantee nobody made.
    """
    dispatch_record(tmp_path, profile="opus-high")
    plan, brief, refusal = plan_for(tmp_path, reviewing="opus-high")
    assert refusal is None, refusal
    assert plan is not None
    assert plan.route.authorship.potential == ("opus-high",)
    assert plan.route.authorship.complete
    assert (
        "route_reviewing_checked=yes potential_authors=opus-high"
        " records=d-20260812-000000-aaaaaa"
        " (all excluded from the candidate list; not a finding that any of them"
        " wrote the diff)" in plan.route.lines()
    )
    dispatch.write_record(plan, brief)
    document = json.loads((plan.record / "dispatch.json").read_text(encoding="utf-8"))
    assert document["route"]["reviewing_checked"] is True
    assert document["route"]["reviewing_potential_authors"] == ["opus-high"]
    # The old spelling is gone rather than kept beside the new one: two names for one fact is
    # two facts that can disagree, and `verified` is the one that overstated it.
    assert "reviewing_verified" not in document["route"]


def test_an_unchecked_subject_is_recorded_as_unchecked_rather_than_as_a_pass(
    tmp_path: Path,
) -> None:
    """Where nothing can be read the declaration stands, and says so on the record.

    That is what ADR-0071 ruling 4's landing check (#334) refuses on: a field the proposer
    controls, marked as one, rather than a guarantee the dispatcher did not make.

    `excluded_anyway` is the declared subject even with nothing read, because the declaration
    is excluded whether or not a record confirms it. It used to say `none` here, which is the
    printed route disagreeing with the exclusion the code performed.
    """
    plan, brief, refusal = plan_for(tmp_path)
    assert refusal is None, refusal
    assert plan is not None
    assert not plan.route.authorship.complete
    assert (
        f"route_reviewing_checked=no why=no_dispatch_records excluded_anyway={REVIEWED}"
        " (the caller's declaration, unchecked; ADR-0071 ruling 4's landing check"
        " refuses on this)" in plan.route.lines()
    )
    dispatch.write_record(plan, brief)
    document = json.loads((plan.record / "dispatch.json").read_text(encoding="utf-8"))
    assert document["route"]["reviewing_checked"] is False
    assert document["route"]["reviewing_unchecked_why"] == "no_dispatch_records"


def test_a_review_of_the_same_issue_is_never_counted_among_the_potential_authors(
    tmp_path: Path,
) -> None:
    """Otherwise a second review would read the first one off the records and review it."""
    dispatch_record(tmp_path, seat="review", profile="codex-sol-xhigh")
    plan, _, refusal = plan_for(tmp_path, reviewing=REVIEWED)
    assert refusal is None, refusal
    assert plan is not None
    assert plan.route.authorship.potential == ()
    assert plan.route.authorship.why == "no_authoring_dispatch"


def test_a_dispatch_that_refused_before_it_ran_could_not_have_worked_on_anything(
    tmp_path: Path,
) -> None:
    """A refusal is written instead of a run, so that record's profile reached no lane."""
    dispatch_record(tmp_path, profile="opus-xhigh", refusal="worktree_mismatch")
    plan, _, refusal = plan_for(tmp_path, reviewing=REVIEWED)
    assert refusal is None, refusal
    assert plan is not None
    assert plan.route.authorship.why == "no_authoring_dispatch"


def test_another_issues_records_say_nothing_about_this_one(tmp_path: Path) -> None:
    """The issue is the join, and a record for a different one is not evidence about this one."""
    dispatch_record(tmp_path, issue=999, profile="opus-xhigh")
    plan, _, refusal = plan_for(tmp_path, reviewing=REVIEWED)
    assert refusal is None, refusal
    assert plan is not None
    assert plan.route.authorship.why == "no_authoring_dispatch"


def test_a_branch_two_dispatches_touched_carries_both(tmp_path: Path) -> None:
    """Either name is an honest subject, so declaring either passes the check.

    Which of them a review should be resolved past when they differ is #333's adjudication
    and is deliberately not decided here. What this landing owes is that a name neither of
    them carries is refused, and that **both** are excluded — see the claims below.
    """
    dispatch_record(tmp_path, "d-20260812-000000-aaaaaa", profile="opus-high")
    dispatch_record(tmp_path, "d-20260812-000001-bbbbbb", profile="opus-low")
    plan, _, refusal = plan_for(tmp_path, reviewing="opus-low")
    assert refusal is None, refusal
    assert plan is not None
    assert plan.route.authorship.potential == ("opus-high", "opus-low")
    assert plan.identity.profile != "opus-low"


# ------------------------- claim 1: every potential author is excluded, not only the declared


def test_a_profile_the_records_carry_is_excluded_even_when_another_is_declared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Critical: excluding the declared subject alone enforces "not the one you named".

    Two dispatches touched this issue, `codex-luna-max` and `opus-low`, and the caller
    declares `opus-low`. Excluding the declaration alone leaves `codex-luna-max` at the head
    of the list, dispatchable — the Codex lane needs no credential of ours — so a profile
    that may have coauthored the change would produce the verdict clearing it. The substituted
    list carries a third entry so the claim is about the exclusion rather than about running
    out of profiles.
    """
    substitute_review_seat(monkeypatch, "codex-luna-max", "opus-low", "opus-xhigh")
    dispatch_record(tmp_path, "d-20260812-000000-aaaaaa", profile="codex-luna-max")
    dispatch_record(tmp_path, "d-20260812-000001-bbbbbb", profile="opus-low")
    plan, _, refusal = plan_for(tmp_path, reviewing="opus-low")
    assert refusal is None, refusal
    assert plan is not None
    assert plan.identity.profile == "opus-xhigh"
    assert "route_preference=opus-xhigh" in plan.route.lines()


def test_the_exclusion_reaches_the_real_registry_rather_than_a_substituted_seat(
    tmp_path: Path,
) -> None:
    """The same claim with nothing substituted, where the exclusion costs the whole list.

    The registered preference is `codex-sol-xhigh zai-glm53-max opus-medium`. With both
    Codex and native entries on the issue's records, only the z.ai entry survives the
    exclusion, and this arrangement withholds its key — so the honest answer is the
    exhaustion refusal, and the refusal prints what was removed. Excluding the declared
    subject alone would have resolved to `codex-sol-xhigh` and dispatched.
    """
    dispatch_record(tmp_path, "d-20260812-000000-aaaaaa", profile="codex-sol-xhigh")
    dispatch_record(tmp_path, "d-20260812-000001-bbbbbb", profile="opus-medium")
    plan, _, refusal = plan_for(tmp_path, reviewing="opus-medium")
    assert plan is None
    assert refusal is not None
    assert refusal.kind == "seat_list_exhausted"
    assert "excluded=codex-sol-xhigh opus-medium" in refusal.found
    assert "walked=zai-glm53-max" in refusal.found


def test_naming_a_profile_the_records_carry_is_refused_even_when_it_is_not_the_subject(
    tmp_path: Path,
) -> None:
    """`--profile` is a way of choosing, and the choice is checked against the whole set.

    Reusing `review_same_profile` rather than opening a second refusal: the finding is the
    same one — this dispatch would have a profile that worked on the change clear it — and
    `why=` says which way it was arrived at.
    """
    dispatch_record(tmp_path, "d-20260812-000000-aaaaaa", profile="codex-luna-max")
    dispatch_record(tmp_path, "d-20260812-000001-bbbbbb", profile="opus-low")
    plan, _, refusal = plan_for(
        tmp_path, lane="codex", profile="codex-luna-max", reviewing="opus-low"
    )
    assert plan is None
    assert refusal is not None
    assert refusal.kind == "review_same_profile"
    assert "why=named_author" in refusal.found
    assert "profile=codex-luna-max" in refusal.found
    assert "excluded=codex-luna-max opus-low" in refusal.found
    assert refusal.failure_class == ""


def test_an_exclusion_that_empties_the_list_reuses_the_existing_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Emptied by a coauthor rather than by the subject, and it is still one finding.

    A second refusal kind here would mean two strings to grep for the thing the ticket is
    about; what differs is the action, which names the whole removed set rather than the
    subject alone.
    """
    substitute_review_seat(monkeypatch, "opus-low", "opus-xhigh")
    dispatch_record(tmp_path, "d-20260812-000000-aaaaaa", profile="opus-xhigh")
    dispatch_record(tmp_path, "d-20260812-000001-bbbbbb", profile="opus-low")
    plan, _, refusal = plan_for(tmp_path, reviewing="opus-low")
    assert plan is None
    assert refusal is not None
    assert refusal.kind == "review_same_profile"
    assert "why=list_offers_nothing_else" in refusal.found
    assert "candidates=none" in refusal.found
    assert "opus-low and opus-xhigh leaves it with nothing" in refusal.action
    # Round 3's claim 2: the refusal says what the records support and no more. The whole
    # potential-author vocabulary exists because they cannot establish that anyone wrote the
    # change, so the sentence that claimed one did is the one thing here that must not return.
    assert "None of those profiles can be ruled out as an author of this change" in refusal.action
    assert "is a profile that worked on the change" not in refusal.action


# --------------------- claim 2: a potential author, because the record cannot say more


def test_a_seat_that_may_have_written_nothing_is_still_excluded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The narrowing, stated as what the record supports rather than guessed at.

    Nothing on a dispatch record says which run produced a commit, so a `planner` on this
    issue is indistinguishable here from the implementer that wrote the diff — as are a
    recon, a stopped run, a successful no-op and a dispatch against a superseded branch. The
    honest answer is a superset, and a superset is exactly right for an exclusion: the
    planner's profile is removed, and the route still says `checked` rather than `verified`.
    """
    substitute_review_seat(monkeypatch, "codex-luna-max", "opus-low", "opus-xhigh")
    dispatch_record(tmp_path, "d-20260812-000000-aaaaaa", seat="planner", profile="codex-luna-max")
    dispatch_record(tmp_path, "d-20260812-000001-bbbbbb", profile="opus-low")
    plan, _, refusal = plan_for(tmp_path, reviewing="opus-low")
    assert refusal is None, refusal
    assert plan is not None
    assert plan.route.authorship.potential == ("codex-luna-max", "opus-low")
    assert plan.identity.profile == "opus-xhigh"


def test_a_stopped_run_stays_in_the_set_because_its_result_carries_no_refusal(
    tmp_path: Path,
) -> None:
    """The case the record cannot narrow, pinned so that narrowing it later is a decision.

    `write_result`'s refusal path is decisive — that dispatch never reached a lane. A stop
    deliberately writes no refusal, so a stopped run is indistinguishable from a completed
    one here and stays in the set. Closing that needs the record to say what a run produced,
    which is #333's and not this ticket's.
    """
    directory = dispatch_record(tmp_path, profile="opus-low")
    (directory / "result.json").write_text(
        json.dumps({"dispatch_id": "d-20260812-000000-aaaaaa", "outcome": "stopped"}),
        encoding="utf-8",
    )
    plan, _, refusal = plan_for(tmp_path, reviewing="opus-low")
    assert refusal is None, refusal
    assert plan is not None
    assert plan.route.authorship.potential == ("opus-low",)


# ------------------------- claim 3: a read that could not complete is not a read that passed


def test_one_unreadable_record_leaves_the_whole_scan_unchecked(tmp_path: Path) -> None:
    """#41 head-on: the readable record still excludes, and still does not clear the check.

    Round 1 discarded the unreadable record and reported `derived` off the readable one, so a
    coauthor sitting in the record that would not open was invisible *and* the route said the
    subject had been checked. Both halves are fixed, and they are separable: the profile that
    was read is still removed, because an incomplete superset is still a superset.
    """
    dispatch_record(tmp_path, "d-20260812-000000-aaaaaa", profile="opus-low")
    broken = tmp_path / "dispatches" / "d-20260812-000001-bbbbbb"
    broken.mkdir(parents=True)
    (broken / "dispatch.json").write_text("{ not json", encoding="utf-8")
    plan, brief, refusal = plan_for(tmp_path, reviewing="opus-low")
    assert refusal is None, refusal
    assert plan is not None
    assert plan.route.authorship.potential == ("opus-low",)
    assert not plan.route.authorship.complete
    assert plan.route.authorship.why == "records_unreadable"
    assert (
        "route_reviewing_checked=no why=records_unreadable excluded_anyway=opus-low"
        " (the caller's declaration, unchecked; ADR-0071 ruling 4's landing check"
        " refuses on this)" in plan.route.lines()
    )
    assert plan.identity.profile != "opus-low"
    dispatch.write_record(plan, brief)
    document = json.loads((plan.record / "dispatch.json").read_text(encoding="utf-8"))
    assert document["route"]["reviewing_checked"] is False


def test_a_dispatch_directory_with_no_plan_in_it_is_a_record_that_could_not_be_read(
    tmp_path: Path,
) -> None:
    """It cannot be skipped: with the issue as the only key, an unopened record is unclassified."""
    dispatch_record(tmp_path, "d-20260812-000000-aaaaaa", profile="opus-low")
    (tmp_path / "dispatches" / "d-20260812-000001-bbbbbb").mkdir(parents=True)
    plan, _, refusal = plan_for(tmp_path, reviewing="opus-low")
    assert refusal is None, refusal
    assert plan is not None
    assert plan.route.authorship.why == "records_unreadable"


def test_an_unreadable_result_leaves_the_scan_incomplete_and_keeps_the_profile(
    tmp_path: Path,
) -> None:
    """The other half of a partial read: "did this one refuse before it ran" went unanswered.

    Keeping the profile is the safe direction for an exclusion; marking the scan incomplete is
    the safe direction for the record. Both, rather than a choice between them.
    """
    directory = dispatch_record(tmp_path, profile="opus-low")
    (directory / "result.json").write_text("{ not json", encoding="utf-8")
    plan, _, refusal = plan_for(tmp_path, reviewing="opus-low")
    assert refusal is None, refusal
    assert plan is not None
    assert plan.route.authorship.potential == ("opus-low",)
    assert plan.route.authorship.why == "records_unreadable"


def test_a_partial_read_does_not_refuse_a_declaration_it_could_not_check(tmp_path: Path) -> None:
    """The direction the fail-closed rule actually points, stated so it is a decision.

    An unreadable record could be the one naming the declared subject, so calling the
    declaration contradicted would turn a gap in the scan into an accusation about the caller.
    The subject is recorded unchecked instead — which is what #334 refuses on — and every
    profile that *was* read is still excluded, so the invariant does not rest on this.

    `opus-high` against a readable record naming `opus-low` is exactly the arrangement the
    contradiction refusal fires on when the read is complete; the unreadable record beside it
    is the whole difference.
    """
    dispatch_record(tmp_path, "d-20260812-000000-aaaaaa", profile="opus-low")
    broken = tmp_path / "dispatches" / "d-20260812-000001-bbbbbb"
    broken.mkdir(parents=True)
    (broken / "dispatch.json").write_text("{ not json", encoding="utf-8")
    plan, _, refusal = plan_for(tmp_path, reviewing="opus-high")
    assert refusal is None, refusal
    assert plan is not None
    assert plan.route.authorship.why == "records_unreadable"
    assert plan.identity.profile not in {"opus-high", "opus-low"}


def test_the_printed_route_prints_the_exclusion_the_code_performed(tmp_path: Path) -> None:
    """Round 3's Medium: one home for the exclusion, the printed route included.

    `subject_line` derived its own set from the potential authors alone, so the declared
    subject was excluded by resolution and missing from the line a reader gets — two
    computations of one set, free to drift. This is the arrangement where they differ: the
    read is partial, so the potential set is `opus-low` alone while the exclusion is
    `opus-high` as well, and the line must carry both.
    """
    dispatch_record(tmp_path, "d-20260812-000000-aaaaaa", profile="opus-low")
    broken = tmp_path / "dispatches" / "d-20260812-000001-bbbbbb"
    broken.mkdir(parents=True)
    (broken / "dispatch.json").write_text("{ not json", encoding="utf-8")
    plan, _, refusal = plan_for(tmp_path, reviewing="opus-high")
    assert refusal is None, refusal
    assert plan is not None
    printed = next(
        line for line in plan.route.lines() if line.startswith("route_reviewing_checked")
    )
    assert "excluded_anyway=opus-high opus-low" in printed
    excluded = dispatch.excluded_from_review("opus-high", plan.route.authorship)
    assert f"excluded_anyway={' '.join(sorted(excluded))}" in printed


def test_an_unreadable_record_leaves_the_subject_unchecked_and_names_why(
    tmp_path: Path,
) -> None:
    """Not raised on, and reported rather than counted as an answer."""
    directory = tmp_path / "dispatches" / "d-20260812-000002-cccccc"
    directory.mkdir(parents=True)
    (directory / "dispatch.json").write_text("{ not json", encoding="utf-8")
    plan, _, refusal = plan_for(tmp_path, reviewing=REVIEWED)
    assert refusal is None, refusal
    assert plan is not None
    assert plan.route.authorship.why == "records_unreadable"


def plan_without_a_profile(tmp_path: Path, dispatch_id: str, profile: object) -> None:
    """Plant a plan that parses and carries this issue, with the profile field this test names.

    Deliberately not `dispatch_record`: that helper resolves the profile against the registry
    to fill in the lane, which is exactly the field these arrangements withhold.
    """
    directory = tmp_path / "dispatches" / dispatch_id
    directory.mkdir(parents=True, exist_ok=True)
    document: dict[str, object] = {"dispatch_id": dispatch_id, "issue": 322, "seat": "implementer"}
    if profile is not None:
        document["profile"] = profile
    (directory / "dispatch.json").write_text(json.dumps(document), encoding="utf-8")


def test_a_plan_that_does_not_name_its_profile_is_a_record_that_could_not_be_read(
    tmp_path: Path,
) -> None:
    """Round 3's Critical: the same failure entering through a narrower door.

    A plan carrying `issue` and no `profile` parses, is about this issue, and is *readable*
    in every sense but the one this scan wants. Beside one good record the scan reported
    itself complete while that dispatch's profile — unknown, therefore possibly the author —
    was excluded nowhere, which puts an unknown potential author outside the never-alone
    floor. The rule adjudicated in round 2 applies unchanged: a record that cannot name its
    profile has not been read for this purpose, so the scan is incomplete.
    """
    dispatch_record(tmp_path, "d-20260812-000000-aaaaaa", profile="opus-low")
    plan_without_a_profile(tmp_path, "d-20260812-000001-bbbbbb", None)
    plan, brief, refusal = plan_for(tmp_path, reviewing="opus-low")
    assert refusal is None, refusal
    assert plan is not None
    assert plan.route.authorship.why == "records_unreadable"
    assert not plan.route.authorship.complete
    # The other half, unchanged: the profile that *was* read is still excluded.
    assert plan.route.authorship.potential == ("opus-low",)
    assert plan.identity.profile != "opus-low"
    dispatch.write_record(plan, brief)
    document = json.loads((plan.record / "dispatch.json").read_text(encoding="utf-8"))
    assert document["route"]["reviewing_checked"] is False


@pytest.mark.parametrize("profile", ["", "   ", 7, ["opus-low"], None])
def test_no_shape_of_unusable_profile_field_clears_the_scan(
    tmp_path: Path, profile: object
) -> None:
    """Every structurally readable but uninformative shape, decided rather than defaulted.

    A blank or whitespace name is absent wearing a string, and a number or a list is not a
    profile name at all — `str()` would have turned each into a plausible-looking token that
    matches no preference entry and silently cleared the check. They land together because
    the caller acts on them identically: this record did not say who ran.
    """
    dispatch_record(tmp_path, "d-20260812-000000-aaaaaa", profile="opus-low")
    plan_without_a_profile(tmp_path, "d-20260812-000001-bbbbbb", profile)
    plan, _, refusal = plan_for(tmp_path, reviewing="opus-low")
    assert refusal is None, refusal
    assert plan is not None
    assert plan.route.authorship.why == "records_unreadable"
    assert plan.route.authorship.potential == ("opus-low",)


def test_a_profile_the_registry_no_longer_carries_is_a_read_record_and_is_excluded(
    tmp_path: Path,
) -> None:
    """The neighbouring shape, decided the other way and on purpose.

    A retired profile names itself, so the record answers the question this scan asks. It is
    excluded like any other name — the exclusion is a set of strings, and a name outside the
    registry simply matches no preference entry — and the scan stays complete. Calling it
    unread would make every later scan of the issue partial over a fact its record states.
    """
    directory = tmp_path / "dispatches" / "d-20260812-000000-aaaaaa"
    directory.mkdir(parents=True)
    (directory / "dispatch.json").write_text(
        json.dumps(
            {
                "dispatch_id": "d-20260812-000000-aaaaaa",
                "issue": 322,
                "seat": "implementer",
                "profile": "opus-retired",
            }
        ),
        encoding="utf-8",
    )
    dispatch_record(tmp_path, "d-20260812-000001-bbbbbb", profile="opus-high")
    plan, _, refusal = plan_for(tmp_path, reviewing="opus-high")
    assert refusal is None, refusal
    assert plan is not None
    assert plan.route.authorship.potential == ("opus-retired", "opus-high")
    assert plan.route.authorship.complete
    assert "opus-retired" in dispatch.excluded_from_review("opus-high", plan.route.authorship)


def test_a_checked_route_reads_back_off_the_record_as_checked(tmp_path: Path) -> None:
    dispatch_record(tmp_path, profile="opus-high")
    plan, brief, _ = plan_for(tmp_path, reviewing="opus-high")
    assert plan is not None
    dispatch.write_record(plan, brief)
    assert dispatch.load_record(plan.record) == plan
    assert dispatch.load_record(plan.record).route.authorship.complete


def test_an_unchecked_route_reads_back_off_the_record_carrying_its_reason(
    tmp_path: Path,
) -> None:
    """`complete` is `potential` and `why` together, so a partial read must survive the trip.

    Reading back only the profiles would turn an incomplete scan into a complete one the
    moment a record was reloaded, which is the same overstatement one indirection later.
    """
    dispatch_record(tmp_path, "d-20260812-000000-aaaaaa", profile="opus-low")
    broken = tmp_path / "dispatches" / "d-20260812-000001-bbbbbb"
    broken.mkdir(parents=True)
    (broken / "dispatch.json").write_text("{ not json", encoding="utf-8")
    plan, brief, _ = plan_for(tmp_path, reviewing="opus-low")
    assert plan is not None
    dispatch.write_record(plan, brief)
    reloaded = dispatch.load_record(plan.record).route.authorship
    assert reloaded.potential == ("opus-low",)
    assert reloaded.why == "records_unreadable"
    assert not reloaded.complete


# ------------------------------------------------- criterion 5: the negative, pinned hard


@pytest.mark.parametrize("reviewed", sorted(dispatch.PROFILES))
def test_no_registered_profile_can_ever_be_returned_as_its_own_reviewer(
    tmp_path: Path, reviewed: str
) -> None:
    """Criterion 5, across the whole registry and both outcomes.

    Either a route resolves and it is somebody else, or the dispatch refuses. There is no
    third answer, and in particular there is no arrangement in which the resolver's honest
    reading of the world produces the profile under review.
    """
    plan, _, refusal = plan_for(tmp_path, reviewing=reviewed)
    if plan is None:
        assert refusal is not None
        return
    assert plan.identity.profile != reviewed


@pytest.mark.parametrize("reviewed", dispatch.SEATS["review"].preference)
def test_the_reviewed_profile_is_not_a_fallback_when_it_is_the_last_lane_conducting(
    tmp_path: Path, reviewed: str
) -> None:
    """The arrangement that would tempt a fallback: every other lane refused.

    Each other candidate's lane is tripped, so the reviewed profile's own lane is the only
    one still conducting and the reviewed profile is the only registered entry on it that
    the seat's list carries. A resolver that treated the subject as a last resort would
    dispatch here; this one refuses, and the refusal names what it removed.
    """
    seat = dispatch.SEATS["review"]
    subject_lane = dispatch.PROFILES[reviewed].lane
    for name in seat.preference:
        lane = dispatch.PROFILES[name].lane
        if lane != subject_lane:
            trip(tmp_path, lane)
    plan, _, refusal = plan_for(tmp_path, reviewing=reviewed)
    assert plan is None, plan
    assert refusal is not None
    assert refusal.kind == "seat_list_exhausted"
    assert f"reviewing={reviewed} (removed before the walk)" in refusal.found
    assert all(not line.startswith(f"refused={reviewed} ") for line in refusal.found)


def test_the_exhaustion_refusal_distinguishes_the_registered_list_from_the_walked_one(
    tmp_path: Path,
) -> None:
    """A reader counting refusals against `preference=` would otherwise find one missing."""
    for lane in ("claude-native", "codex", "zai"):
        trip(tmp_path, lane)
    _, _, refusal = plan_for(tmp_path, reviewing="codex-sol-xhigh")
    assert refusal is not None
    assert "preference=codex-sol-xhigh zai-glm53-max opus-medium" in refusal.found
    assert "walked=zai-glm53-max opus-medium" in refusal.found


# ------------------------------------------------ the command line, the record, the listing


def test_the_subject_reaches_the_dispatcher_from_the_command_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--reviewing` is a real option on the real parser, not a namespace field tests set."""
    worktree = git_worktree(tmp_path)
    code = dispatch.main(
        [
            "--seat",
            "review",
            "--reviewing",
            "codex-luna-max",
            "--issue",
            "322",
            "--worktree",
            str(worktree),
            "--issue-body",
            str(READY_BODY),
            "--dispatch-dir",
            str(tmp_path / "dispatches"),
            "--review-root",
            str(tmp_path / "review"),
            "--credentials",
            str(tmp_path / "credentials.env"),
            "--breaker-dir",
            str(tmp_path / "breaker"),
            "--queue-dir",
            str(open_policy(tmp_path)),
            "--queue-root",
            str(tmp_path / "queue-root"),
            "--dry-run",
        ]
    )
    printed = capsys.readouterr()
    assert code == 0, printed.err
    assert "route_reviewing=codex-luna-max (never resolved to)" in printed.out
    assert "route_permission_mode=plan forced_by_seat=review" in printed.out
    assert "route_chosen=opus-medium lane=claude-native" in printed.out
    # The list the dispatch actually walked, the reviewed profile's lane last.
    assert "route_preference=zai-glm53-max opus-medium" in printed.out
    assert "--permission-mode plan" in printed.out


def test_the_record_names_the_profile_under_review(tmp_path: Path) -> None:
    """ADR-0071 ruling 4's landing check reads records, so the subject has to be in one."""
    plan, brief, refusal = plan_for(tmp_path)
    assert refusal is None
    assert plan is not None
    dispatch.write_record(plan, brief)
    document = json.loads((plan.record / "dispatch.json").read_text(encoding="utf-8"))
    assert document["route"]["reviewing"] == REVIEWED
    assert document["permission_mode"] == "plan"


def test_a_recorded_review_route_reads_back_as_the_route_that_was_written(
    tmp_path: Path,
) -> None:
    plan, brief, _ = plan_for(tmp_path)
    assert plan is not None
    dispatch.write_record(plan, brief)
    assert dispatch.load_record(plan.record) == plan


def test_a_record_written_before_this_landed_reads_back_with_no_subject(
    tmp_path: Path,
) -> None:
    """No review before #322 declared one, which is the finding the ADR records."""
    plan, brief, _ = plan_for(tmp_path)
    assert plan is not None
    dispatch.write_record(plan, brief)
    path = plan.record / "dispatch.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    del document["route"]["reviewing"]
    path.write_text(json.dumps(document), encoding="utf-8")
    assert dispatch.load_record(plan.record).route.reviewed == ""


def test_the_registry_listing_states_both_halves_of_the_rule(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A reader asking "what can I dispatch?" is told what this seat does differently."""
    assert dispatch.main(["--list"]) == 0
    printed = capsys.readouterr().out
    assert (
        "  reviews=true resolves_past=--reviewing-and-every-potential-author"
        " prefers=a-different-lane refusal=review_same_profile" in printed
    )
    assert "  permission_mode=plan forced=true (no caller override)" in printed
    assert (
        "  review_subject=checked-against-dispatch-records"
        " refusal=review_subject_contradicted unchecked=recorded-unchecked" in printed
    )


def test_the_review_seat_is_the_only_one_that_reviews_and_not_the_only_one_contained() -> None:
    """`reviews` is ruling 4's and stays this seat's; `permission_mode` was never only this seat's.

    #322 landed both columns together for the seat ruling 4 names, and this claim used to read
    them as one thing. #407 separated them: `recon` is read-only in ADR-0071's own table and in
    the reasoning that admits it cheaply, so it forces the same mode, and a claim that the
    review seat is the only contained one would now be a claim that the recon gap is still open.
    """
    assert [name for name, seat in dispatch.SEATS.items() if seat.reviews] == ["review"]
    assert sorted(name for name, seat in dispatch.SEATS.items() if seat.permission_mode) == [
        "recon",
        "review",
    ]


# ------------------ #413: a renamed profile's old name resolves for reading, never for routing


def test_the_retirement_table_resolves_into_the_live_registry() -> None:
    """The map's own ground: every successor is live, and no retired name still is.

    A retired name left in `PROFILES` would be dispatchable by `--profile`, which is
    criterion 2's refusal gone; a successor missing from it would make every read of the
    retired name unplaceable, which is the strand criterion 1 exists to close.
    """
    assert dispatch.RETIRED_PROFILES
    for retired, entry in dispatch.RETIRED_PROFILES.items():
        assert retired not in dispatch.PROFILES
        assert entry.successor in dispatch.PROFILES
        assert entry.retired_on


def test_the_chain_walk_resolves_a_rename_and_stops_at_the_live_name() -> None:
    """`retired_names` states the lineage one function, because three rungs read it."""
    assert dispatch.retired_names("opus-high") == ("opus-high",)
    assert dispatch.retired_names("zai-glm52-max") == ("zai-glm52-max", "zai-glm53-max")
    assert dispatch.resolved_profile("zai-glm52-max") == dispatch.PROFILES["zai-glm53-max"]
    assert dispatch.resolved_profile("zai-glm54-max") is None


def test_no_registered_name_is_also_claimed_by_retired_names() -> None:
    """A name both tables claim would route and read as two different profiles (#433).

    `retired_names` on a registered name must stop at the name itself: a registered name
    that is also a retirement-table key is dispatchable by `--profile` (which reads
    `PROFILES`) while `resolved_profile` and every review rung resolve it away to its
    successor, so the same dispatch would be two profiles depending on who reads it.
    #433 adds two names the retirement table must never swallow; this holds for every
    future name too, which is why the loop is over the registry and not over the two.
    """
    for name in dispatch.PROFILES:
        assert dispatch.retired_names(name) == (name,), name


def test_a_retired_name_is_a_subject_a_review_may_declare_and_not_a_route_it_may_take(
    tmp_path: Path,
) -> None:
    """Criterion 4's pair (#413): the records may carry the name, a dispatch may not.

    This is #404's arrangement exactly — work authored under `zai-glm52-max`, the rename
    landed after, the review owed. The old name declares the subject the records carry;
    the ladder still refuses it as a route, because `resolve_selection` reads `PROFILES`
    and never the retirement table.
    """
    dispatch_record(tmp_path, profile="zai-glm52-max", lane="zai")
    tree = str(git_worktree(tmp_path))
    plan, _, refusal = plan_for(tmp_path, reviewing="zai-glm52-max", worktree=tree)
    assert refusal is None, refusal
    assert plan is not None
    assert plan.route.reviewed == "zai-glm52-max"
    assert plan.route.profile == "codex-sol-xhigh"
    # The old name never dispatches: on the ladder it is an unknown profile, not a retired
    # one, because the distinction between the two tables is the whole mechanism.
    _, _, named = plan_for(
        tmp_path,
        seat="implementer",
        lane="zai",
        profile="zai-glm52-max",
        reviewing="",
        worktree=tree,
    )
    assert named is not None
    assert named.kind == "unknown_profile"


def test_the_successor_a_rename_left_is_excluded_like_the_author_it_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The conservative side of `excluded_from_review`'s trade, resolved through the chain.

    The records carry `zai-glm52-max`; the candidate list carries `zai-glm53-max`. A plain
    string comparison between the two sets never meets, so the successor would review its
    predecessor's work unrefused. Removal from the list is asserted as an absence from
    `passed_over` rather than as a skipped head, because a credential-withheld skip and an
    exclusion both end the walk one entry later.
    """
    dispatch_record(tmp_path, profile="zai-glm52-max", lane="zai")
    substitute_review_seat(monkeypatch, "zai-glm53-max", "opus-low")
    plan, _, refusal = plan_for(tmp_path, reviewing="zai-glm52-max")
    assert refusal is None, refusal
    assert plan is not None
    assert plan.route.profile == "opus-low"
    assert plan.route.passed_over == ()


def test_a_subject_declared_in_the_new_name_still_contradicts_old_name_records(
    tmp_path: Path,
) -> None:
    """The strict half, stated as a test so it reads as a choice and not an oversight.

    The retirement map makes the old name readable; it does not rewrite what the records
    say. A caller declaring `zai-glm53-max` over `zai-glm52-max` records controls the half
    the refusal names, and has a valid alternative: the name the records carry.
    """
    dispatch_record(tmp_path, profile="zai-glm52-max", lane="zai")
    plan, _, refusal = plan_for(tmp_path, reviewing="zai-glm53-max")
    assert plan is None
    assert refusal is not None
    assert refusal.kind == "review_subject_contradicted"
    assert "potential_authors=zai-glm52-max" in refusal.found


# ------------------------------------- the declared record, read by this seat too (#402)

# #398 gave the author set a second source — the interactive declaration, because #294
# bars a dispatched session from writing under `.claude/` and such a change leaves no
# dispatch record at all. `just land`'s rung reads both sources; the review seat's
# resolution read only the first, so an interactively authored change could have its review
# dispatched onto the very profile that wrote it — the dispatch spent, the review run, and
# `review_same_profile` refused at the landing on a record the dispatcher never saw. The
# claims below hold the two consumers to one merge.


DECLARED_SHA: Final = "c" * 40
DECLARED_STAMP: Final = "20260818T0000Z"


def _declare(tmp_path: Path, profile: str) -> Path:
    """Declare one interactive author under this test's own review root, via the real writer."""
    review_root = tmp_path / "review"
    review_loop.store_authorship(review_root, 322, profile, DECLARED_SHA, DECLARED_STAMP)
    return review_root


def test_the_profile_the_walk_would_take_is_not_taken_once_it_is_declared(
    tmp_path: Path,
) -> None:
    """The refusal half of the criterion: a declared author is never the reviewer resolved.

    The #402 arrangement exactly: the issue's dispatched records place the subject
    (`opus-high`, honestly declared as `--reviewing`), and the interactive half of the same
    branch is declared as `codex-sol-xhigh` — the seat's head, and so the profile the walk
    takes on this subject. Before #402 the scan placed nobody else, the walk spent the
    dispatch on the author, and `review_same_profile` refused at the landing on the record
    the dispatcher never saw.
    """
    dispatch_record(tmp_path)
    _declare(tmp_path, "codex-sol-xhigh")

    plan, _, refusal = plan_for(tmp_path)

    assert refusal is None, refusal
    assert plan is not None
    assert plan.identity.profile != "codex-sol-xhigh"
    # The walk continued down the seat's own list rather than refusing: the exclusion
    # costs a resolution step — past the z.ai entry this arrangement withholds a key for —
    # never the dispatch.
    assert plan.identity.profile == "opus-medium"


def test_a_declared_profile_the_walk_was_not_going_to_take_changes_nothing(
    tmp_path: Path,
) -> None:
    """The passing half: the same declaration discriminates on the profile it names.

    A guard that refused every declaration would pass the claim above while excluding
    nothing, which is not a guard. The same dispatched record, a declaration naming a
    profile the walk never considers, and the resolution stands where it stood — the seat's
    head, exactly the answer the claim above refuses.
    """
    dispatch_record(tmp_path)
    _declare(tmp_path, "opus-xhigh")

    plan, _, refusal = plan_for(tmp_path)

    assert refusal is None, refusal
    assert plan is not None
    assert plan.identity.profile == "codex-sol-xhigh"


def test_the_route_records_the_merged_set_and_its_declared_record(
    tmp_path: Path,
) -> None:
    """`reviewing_checked` answers over the merged set, not the dispatch records alone.

    The scan the dispatcher performs and the scan the landing performs must agree: complete
    over both sources, carrying the declared profile beside the dispatched one, and naming
    each name's record — dispatch id for one, the authorship record's path for the other —
    so the record this dispatch writes can no longer overstate what was checked.
    """
    dispatch_record(tmp_path)
    review_root = _declare(tmp_path, "codex-luna-max")
    record = review_loop.authorship_path(review_root, 322)

    plan, _, refusal = plan_for(tmp_path)

    assert refusal is None, refusal
    assert plan is not None
    assert plan.route.authorship.potential == (REVIEWED, "codex-luna-max")
    assert plan.route.authorship.records == ("d-20260812-000000-aaaaaa", str(record))
    assert plan.route.authorship.complete is True
    document = plan.route.document()
    assert document["reviewing_checked"] is True
    assert document["reviewing_potential_authors"] == [REVIEWED, "codex-luna-max"]
    assert document["reviewing_potential_author_records"] == [
        "d-20260812-000000-aaaaaa",
        str(record),
    ]
    assert (
        f"route_reviewing_checked=yes potential_authors=codex-luna-max {REVIEWED}"
        f" records=d-20260812-000000-aaaaaa {record}" in "\n".join(plan.route.lines())
    )


def test_a_declaration_that_will_not_read_refuses_rather_than_resolving(
    tmp_path: Path,
) -> None:
    """The entry that would not open could name the profile this dispatch would resolve.

    Before #402 the dispatcher never opened the record at all; reading it must not trade
    that silence for a crash or for a set that overstates what was checked — the refusal
    is fail-closed, and it reuses the landing's own name for the same fact.
    """
    review_root = tmp_path / "review"
    record = review_loop.authorship_path(review_root, 322)
    record.parent.mkdir(parents=True)
    record.write_text('{"version": 1, "issue"', encoding="utf-8")

    plan, _, refusal = plan_for(tmp_path)

    assert plan is None
    assert refusal is not None
    assert refusal.kind == "authorship_unreadable"
    assert f"record={record}" in refusal.found
    assert "Nothing was dispatched" in refusal.action


def test_a_lost_declaration_refuses_rather_than_narrowing_the_set(
    tmp_path: Path,
) -> None:
    """A record gone beside the lock only the writer creates is a narrowing, not an answer.

    `escalate` refuses the same absence for the same reason (#398 round 2); before #402
    this seat could not, because it never read the record the loss removed.
    """
    review_root = _declare(tmp_path, "opus-low")
    review_loop.authorship_path(review_root, 322).unlink()

    plan, _, refusal = plan_for(tmp_path)

    assert plan is None
    assert refusal is not None
    assert refusal.kind == "authorship_lost"
    lost = review_loop.authorship_path(review_root, 322)
    assert f"record={lost}" in refusal.found
    assert f"lock={lost.with_name(review_loop.AUTHORSHIP_LOCK)}" in refusal.found
    assert "just review-loop author" in refusal.action
