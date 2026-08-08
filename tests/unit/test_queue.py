"""The dispatch queue's policy file, its refusals, and the rung it puts on `just dispatch` (#250).

Three layers, all in the no-Arma tier.

The pure functions come first, because the rulings are what they encode: a policy entry that
cannot quote its ruling is refused, an unreadable policy is not a policy that permits, and the
in-flight count follows the list rather than the other way round (ADR-0051).

Under them sit the writers and the CLI over a temporary queue directory, and then the rung
itself, asserted through `dispatch.main(["--dry-run", ...])`. That last layer is the one the
issue exists for: a freeze recorded in a file must refuse a dispatch by name, launch nothing,
carry no failure class, and be reachable by no flag, argument or environment variable.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from conftest import REPO, load_tool

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

queue = load_tool("queue_policy")
dispatch = load_tool("dispatch")

# #241's readiness rung sits above this one on the ladder, and it reads the issue from
# GitHub unless it is handed a body. Every dispatch below is handed this one, so what these
# tests assert is the queue rung's answer and never this box's network.
READY_BODY = REPO / "tests" / "fixtures" / "readiness-corpus" / "223.md"

RULING = "human, 2026-08-05T10:15:47Z; recorded #217"
WIP_RULING = "human, 2026-08-04; the underlying limit of three"
WHEN = "2026-08-05T10:15:47Z"


def policy_document(
    *,
    state: str = "frozen",
    limit: int = 3,
    packages: list[dict] | None = None,
) -> dict:
    """Build the smallest well-formed policy, so a test states only what it varies."""
    return {
        "version": 1,
        "freeze": {"state": state, "since": WHEN, "ruling": RULING},
        "wip_limit": {"value": limit, "since": WHEN, "ruling": WIP_RULING},
        "packages": packages or [],
    }


def package_document(**overrides: object) -> dict:
    """One carve-out entry, well formed."""
    block = {
        "name": "initiative",
        "issues": [221, 222],
        "exempt_from_freeze": True,
        "wip_reserved": 0,
        "since": WHEN,
        "ruling": "human at close-down 2026-08-05; recorded #217 17:12Z",
        "note": "",
    }
    block.update(overrides)
    return block


def parsed(**kwargs: Any) -> Any:  # noqa: ANN401 — a tools/ module loads dynamically, so its types are not names here
    """Parse a well-formed policy and hand back the object, asserting it parsed."""
    policy, refusal = queue.parse_policy(policy_document(**kwargs))
    assert refusal is None
    assert policy is not None
    return policy


def in_flight_of(*issues: int, github: str = "read") -> Any:  # noqa: ANN401 — same
    """Build an in-flight set naming these issues, each held by one worktree."""
    return queue.InFlight(
        holders=tuple(
            queue.Holder(issue, (f"worktree:/w/issue-{issue}",), Path(f"/w/issue-{issue}"))
            for issue in issues
        ),
        owed=(),
        github=github,
    )


def store_at(tmp_path: Path) -> Any:  # noqa: ANN401 — same
    """Build a store over a directory of this test's own, with no collector named."""
    return queue.Store(directory=tmp_path / "queue")


def seeded(tmp_path: Path, document: dict | None = None) -> Any:  # noqa: ANN401 — same
    """Write a policy document straight to disk, the way a hand-edit would."""
    store = store_at(tmp_path)
    store.directory.mkdir(parents=True, exist_ok=True)
    store.policy_path.write_text(
        json.dumps(document if document is not None else policy_document()), encoding="utf-8"
    )
    return store


def nothing_closed(numbers: Sequence[int]) -> tuple[frozenset[int], str]:
    """Stand in for a tracker that reports every issue open."""
    return frozenset(), "read" if numbers else "not-needed"


def fake_github(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    candidates: Sequence[dict[str, object]],
) -> None:
    """Put a deterministic `gh` tracker boundary on PATH for a CLI-level queue read."""
    executable = tmp_path / "bin" / "gh"
    executable.parent.mkdir(parents=True)
    executable.write_text(
        "#!/bin/sh\n"
        'if [ "${CTI_TEST_GH_FAIL:-}" = "1" ]; then exit 1; fi\n'
        'if [ "${CTI_TEST_GH_VIEW_FAIL:-}" = "1" ] && [ "$1 $2" = "issue view" ]; '
        "then exit 1; fi\n"
        'if [ "$1 $2" = "issue list" ]; then printf \'%s\\n\' "$CTI_TEST_CANDIDATES"; '
        "else printf 'OPEN\\n'; fi\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", f"{executable.parent}:{os.environ['PATH']}")
    monkeypatch.setenv("CTI_TEST_CANDIDATES", json.dumps(candidates))


def unfinished_dispatches(directory: Path, *issues: int) -> None:
    """Write unfinished records in the public on-disk shape `just dispatch` produces."""
    for issue in issues:
        record = directory / f"d-{issue}"
        record.mkdir(parents=True)
        (record / "dispatch.json").write_text(json.dumps({"issue": issue}), encoding="utf-8")


# ------------------------------------------------------------------ the document, read strictly


def test_a_well_formed_policy_parses_into_the_entries_it_states() -> None:
    policy = parsed(state="frozen", limit=3, packages=[package_document(wip_reserved=2)])
    assert policy.version == 1
    assert policy.freeze.state == "frozen"
    assert policy.freeze.frozen is True
    assert policy.freeze.ruling == RULING
    assert policy.wip_limit.value == 3
    assert policy.wip_limit.ruling == WIP_RULING
    assert len(policy.packages) == 1
    assert policy.packages[0].name == "initiative"
    assert policy.packages[0].issues == (221, 222)
    assert policy.packages[0].exempt_from_freeze is True
    assert policy.packages[0].wip_reserved == 2


def test_an_open_policy_is_not_frozen() -> None:
    assert parsed(state="open").freeze.frozen is False


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda d: d.update(surprise=1), "unknown_keys=surprise"),
        (lambda d: d.update(version=2), "version=2"),
        (lambda d: d.pop("version"), "version=None"),
        (lambda d: d.pop("freeze"), "entry=freeze"),
        (lambda d: d.pop("wip_limit"), "entry=wip_limit"),
        (lambda d: d["freeze"].pop("ruling"), "ruling=missing"),
        (lambda d: d["freeze"].update(ruling="   "), "ruling=missing"),
        (lambda d: d["wip_limit"].pop("ruling"), "ruling=missing"),
        (lambda d: d["freeze"].update(state="paused"), "state='paused'"),
        (lambda d: d["freeze"].update(thawed=True), "unknown_keys=thawed"),
        (lambda d: d["wip_limit"].update(value="three"), "value='three'"),
        (lambda d: d["wip_limit"].update(value=-1), "value=-1"),
        (lambda d: d["wip_limit"].update(value=True), "value=True"),
        (lambda d: d.update(packages={}), "entry=packages"),
        (lambda d: d.update(freeze=[]), "entry=freeze"),
    ],
)
def test_every_hand_edit_the_file_could_carry_refuses_policy_invalid(
    mutate: Callable[[dict], object], expected: str
) -> None:
    """A policy nobody can parse is not a policy that permits, and it says which key."""
    document = policy_document()
    mutate(document)
    policy, refusal = queue.parse_policy(document)
    assert policy is None
    assert refusal is not None
    assert refusal.kind == "policy_invalid"
    assert expected in " ".join(refusal.found), refusal.found


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"ruling": ""}, "ruling=missing"),
        ({"name": ""}, "name=missing"),
        ({"issues": "221-230"}, "issues='221-230'"),
        ({"issues": [221, "222"]}, "issues=[221, '222']"),
        ({"wip_reserved": -1}, "wip_reserved=-1"),
        ({"exempt_from_freeze": "yes"}, "exempt_from_freeze='yes'"),
        ({"scope": "wide"}, "unknown_keys=scope"),
    ],
)
def test_a_malformed_carve_out_refuses_and_names_the_entry(overrides: dict, expected: str) -> None:
    policy, refusal = queue.parse_policy(policy_document(packages=[package_document(**overrides)]))
    assert policy is None
    assert refusal is not None
    assert refusal.kind == "policy_invalid"
    found = " ".join(refusal.found)
    assert "packages[0]" in found
    assert expected in found


def test_a_policy_that_is_not_an_object_refuses_rather_than_reading_as_open() -> None:
    policy, refusal = queue.parse_policy([1, 2, 3])
    assert policy is None
    assert refusal is not None
    assert refusal.kind == "policy_invalid"
    assert "type=list" in refusal.found


def test_no_refusal_the_policy_reader_makes_carries_a_failure_class() -> None:
    """CLAUDE.md's table types what a run found; none of these found anything about code."""
    _, refusal = queue.parse_policy({})
    assert refusal is not None
    assert refusal.failure_class == ""
    assert "class=" not in " ".join(refusal.lines())


def test_a_hand_corrupted_policy_file_refuses_on_read_and_is_not_treated_as_open(
    tmp_path: Path,
) -> None:
    """Acceptance criterion 2, at the file rather than at the document."""
    store = store_at(tmp_path)
    store.directory.mkdir(parents=True)
    store.policy_path.write_text('{"version": 1, "freeze": {"state": "op', encoding="utf-8")
    policy, refusal = queue.read_policy(store)
    assert policy is None
    assert refusal is not None
    assert refusal.kind == "policy_invalid"
    assert f"path={store.policy_path}" in refusal.found


def test_an_absent_policy_refuses_by_its_own_name_and_says_how_to_seed_it(
    tmp_path: Path,
) -> None:
    policy, refusal = queue.read_policy(store_at(tmp_path))
    assert policy is None
    assert refusal is not None
    assert refusal.kind == "policy_absent"
    assert "just queue open" in refusal.action
    assert "just queue wip" in refusal.action


def test_a_policy_round_trips_through_the_document_it_writes(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    original = parsed(state="frozen", limit=2, packages=[package_document(note="and retros")])
    queue.write_policy(store, original)
    again, refusal = queue.read_policy(store)
    assert refusal is None
    assert again == original


# ------------------------------------------------------------------------- deriving in flight


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("issue-250", 250),
        ("issue-7", 7),
        ("agent-a1008b7334df4afdc", None),
        ("bridge-cse_01FdwWnEDXP9zveZ61tZ16qR", None),
        ("retro-25", None),
        ("issue-", None),
        ("issue-250-extra", None),
        ("Issue-250", None),
    ],
)
def test_only_an_issue_named_tree_names_an_issue(name: str, expected: int | None) -> None:
    """93 registrations against 6 dispatch records is why this exclusion is stated (#242)."""
    assert queue.issue_of_tree(name) == expected


def test_the_derivation_unions_both_sources_and_names_each_one() -> None:
    found = queue.derive_in_flight(
        [Path("/w/issue-241"), Path("/w/agent-abc123"), Path("/w/issue-250")],
        [(250, "d-1", False), (170, "d-2", False), (999, "d-3", True)],
        nothing_closed,
    )
    assert found.issues == (170, 241, 250)
    rows = {holder.issue: holder.sources for holder in found.holders}
    assert rows[241] == ("worktree:/w/issue-241",)
    assert rows[250] == ("worktree:/w/issue-250", "dispatch:d-1")
    assert rows[170] == ("dispatch:d-2",)


def test_a_dispatch_record_with_a_result_is_finished_and_not_in_flight() -> None:
    found = queue.derive_in_flight([], [(310, "d-9", True)], nothing_closed)
    assert found.issues == ()


def test_a_closed_issue_with_a_lingering_tree_is_dropped_and_reported_as_owed() -> None:
    """The fixture acceptance criterion 5 asks for: closed, tree still there."""

    def closed(numbers: Sequence[int]) -> tuple[frozenset[int], str]:
        assert set(numbers) == {170, 241}
        return frozenset({170}), "read"

    found = queue.derive_in_flight([Path("/w/issue-170"), Path("/w/issue-241")], [], closed)
    assert found.issues == (241,)
    assert [holder.issue for holder in found.owed] == [170]
    assert f"worktree_done_owed.170={Path('/w/issue-170')}" in found.lines()


def test_an_unreadable_tracker_keeps_every_issue_in_the_count_and_says_so() -> None:
    """The refusing direction: a check that could not run is not a check that passed."""
    found = queue.derive_in_flight(
        [Path("/w/issue-170")], [], lambda _: (frozenset(), "unreadable:no-gh")
    )
    assert found.issues == (170,)
    assert "github=unreadable:no-gh" in found.lines()


def test_the_count_follows_the_list_and_is_printed_as_a_floor() -> None:
    """ADR-0051 read in #209's direction: here the list is the evidence."""
    lines = in_flight_of(170, 241).lines()
    assert lines.index("in_flight.170=worktree:/w/issue-170") < lines.index("in_flight=2 floor=yes")
    assert lines[-1] == "in_flight=2 floor=yes"


# ------------------------------------------------------------------------------- the freeze


def test_a_frozen_policy_refuses_an_issue_outside_every_carve_out() -> None:
    policy = parsed(state="frozen", packages=[package_document()])
    refusal = queue.freeze_refusal(policy, 249)
    assert refusal is not None
    assert refusal.kind == "dispatch_frozen"
    found = " ".join(refusal.found)
    assert "issue=249" in found
    assert f"ruling={RULING}" in found
    assert f"since={WHEN}" in found
    assert "carve_out.initiative=issues=221-222 exempt=True" in found


def test_a_frozen_policy_lets_a_carved_out_issue_through() -> None:
    policy = parsed(state="frozen", packages=[package_document(issues=[221, 222, 250])])
    assert queue.freeze_refusal(policy, 250) is None
    assert queue.freeze_refusal(policy, 251) is not None


def test_a_package_that_is_not_exempt_carves_nothing_out() -> None:
    policy = parsed(
        state="frozen", packages=[package_document(issues=[250], exempt_from_freeze=False)]
    )
    refusal = queue.freeze_refusal(policy, 250)
    assert refusal is not None
    assert "carve_out.initiative=issues=250 exempt=False" in " ".join(refusal.found)


def test_an_open_policy_refuses_nothing_on_the_freeze_rung() -> None:
    assert queue.freeze_refusal(parsed(state="open"), 249) is None


def test_the_freeze_refusal_names_the_un_mechanisable_half_of_the_ruling() -> None:
    """A ruling's `and retros` half has no issue number, so it is carried as a note."""
    policy = parsed(state="frozen", packages=[package_document(note="and retros, per the ruling")])
    refusal = queue.freeze_refusal(policy, 249)
    assert refusal is not None
    assert "carve_out_note.initiative=and retros, per the ruling" in refusal.found


def test_a_freeze_with_no_carve_outs_says_so_rather_than_printing_nothing() -> None:
    refusal = queue.freeze_refusal(parsed(state="frozen"), 249)
    assert refusal is not None
    assert "carve_outs=none" in refusal.found


def test_the_freeze_refusal_carries_no_failure_class() -> None:
    """#238's precedent exactly: nothing was found about any provider, lane or code."""
    refusal = queue.freeze_refusal(parsed(state="frozen"), 249)
    assert refusal is not None
    assert refusal.failure_class == ""
    assert "class=" not in " ".join(refusal.lines())


def test_the_freeze_refusal_says_there_is_no_override_and_who_amends_it() -> None:
    refusal = queue.freeze_refusal(parsed(state="frozen"), 249)
    assert refusal is not None
    assert "no override" in refusal.action
    assert "only they amend it" in refusal.action


# ---------------------------------------------------------------------------------- the WIP


@pytest.mark.parametrize(("held", "refused"), [(0, False), (1, False), (2, False), (3, True)])
def test_the_ruled_limit_binds_at_its_own_boundary(held: int, *, refused: bool) -> None:
    policy = parsed(state="open", limit=3)
    in_flight = in_flight_of(*range(100, 100 + held))
    assert (queue.wip_refusal(policy, 249, in_flight) is not None) is refused


def test_an_issue_already_in_flight_does_not_count_against_itself() -> None:
    """A resumption after a crash (ADR-0024) must not be refused its own slot."""
    policy = parsed(state="open", limit=1)
    assert queue.wip_refusal(policy, 170, in_flight_of(170)) is None
    assert queue.wip_refusal(policy, 249, in_flight_of(170)) is not None


def test_the_wip_refusal_prints_the_list_the_limit_was_derived_from() -> None:
    refusal = queue.wip_refusal(parsed(state="open", limit=2), 249, in_flight_of(170, 241))
    assert refusal is not None
    assert refusal.kind == "wip_reached"
    found = " ".join(refusal.found)
    assert "in_flight.170=worktree:/w/issue-170" in found
    assert "in_flight.241=worktree:/w/issue-241" in found
    assert "limit=2" in found
    assert f"ruling={WIP_RULING}" in found
    assert "in_flight=2 floor=yes" in found


def test_a_reservation_holds_slots_open_against_an_issue_outside_the_package() -> None:
    policy = parsed(
        state="open", limit=3, packages=[package_document(wip_reserved=2, issues=[221, 222])]
    )
    # One slot taken, two reserved elsewhere: an outsider sees nothing free.
    assert queue.wip_refusal(policy, 249, in_flight_of(170)) is not None
    # The package's own issue may take it.
    assert queue.wip_refusal(policy, 221, in_flight_of(170)) is None


def test_a_reservation_shrinks_as_the_package_takes_its_own_slots() -> None:
    policy = parsed(
        state="open", limit=3, packages=[package_document(wip_reserved=2, issues=[221, 222])]
    )
    # 221 in flight consumes one of the two reserved, leaving one held back: 3 - 1 - 1 = 1.
    assert queue.wip_refusal(policy, 249, in_flight_of(221)) is None
    # Both reserved slots taken: the reservation holds nothing back, 3 - 2 = 1 free.
    assert queue.wip_refusal(policy, 249, in_flight_of(221, 222)) is None
    assert queue.wip_refusal(policy, 249, in_flight_of(221, 222, 170)) is not None


def test_the_wip_refusal_names_the_reservation_that_held_the_slot() -> None:
    policy = parsed(
        state="open", limit=2, packages=[package_document(wip_reserved=2, issues=[221])]
    )
    refusal = queue.wip_refusal(policy, 249, in_flight_of())
    assert refusal is not None
    assert "reserved.initiative=2" in refusal.found


def test_the_wip_refusal_carries_no_failure_class() -> None:
    refusal = queue.wip_refusal(parsed(state="open", limit=1), 249, in_flight_of(170))
    assert refusal is not None
    assert refusal.failure_class == ""


# ------------------------------------------------------------------------ the surface conflict


def test_two_in_flight_trees_writing_the_same_paths_refuse_by_name() -> None:
    refusal = queue.surface_refusal(
        250, ["tools/dispatch.py", "justfile"], {250: ["tools/dispatch.py"], 241: ["justfile"]}
    )
    assert refusal is not None
    assert refusal.kind == "surface_conflict"
    assert "holder=241" in refusal.found
    assert "paths=justfile" in refusal.found


def test_a_tree_never_conflicts_with_itself() -> None:
    assert queue.surface_refusal(250, ["justfile"], {250: ["justfile"]}) is None


def test_disjoint_surfaces_do_not_conflict() -> None:
    assert queue.surface_refusal(250, ["a.py"], {241: ["b.py"]}) is None


def test_a_candidate_that_has_written_nothing_yet_cannot_be_seen_to_conflict() -> None:
    """The stated limit: a fresh worktree has touched nothing, so this rung sees nothing."""
    assert queue.surface_refusal(250, [], {241: ["justfile"]}) is None


# ---------------------------------------------------------------------------- the whole rung


def test_the_freeze_is_heard_before_the_limit_because_it_lasts_longer() -> None:
    policy = parsed(state="frozen", limit=1)
    refusal = queue.check_refusal(policy, 249, in_flight_of(170, 241), {})
    assert refusal is not None
    assert refusal.kind == "dispatch_frozen"


def test_the_limit_is_heard_before_a_surface_conflict() -> None:
    policy = parsed(state="open", limit=1)
    refusal = queue.check_refusal(
        policy, 249, in_flight_of(170), {249: ["justfile"], 170: ["justfile"]}
    )
    assert refusal is not None
    assert refusal.kind == "wip_reached"


def test_a_clear_issue_clears_every_rung() -> None:
    assert queue.check_refusal(parsed(state="open", limit=3), 249, in_flight_of(170), {}) is None


# ------------------------------------------------------------------------------- selection


def blocked(body: str) -> int | None:
    """Read what `Blocked-by:` this body carries, if any."""
    return queue.Candidate(1, "t", body).blocked_by


def test_the_optional_blocked_by_line_is_read_where_it_exists() -> None:
    assert blocked("Some text\nBlocked-by: #241\nmore") == 241
    assert blocked("Blocked-by: #7") == 7
    assert blocked("no such line") is None
    assert blocked("see Blocked-by: #241 inline") is None


def test_selection_drops_each_candidate_with_the_reason_beside_it() -> None:
    policy = parsed(state="open", limit=3)
    selection = queue.select(
        policy,
        [
            queue.Candidate(241, "readiness"),
            queue.Candidate(170, "transport"),
            queue.Candidate(249, "watch seam", "Blocked-by: #241"),
        ],
        in_flight_of(170),
        count=5,
    )
    assert [c.issue for c in selection.chosen] == [241]
    assert "considered.170=already-in-flight" in selection.considered
    assert "considered.241=eligible" in selection.considered
    assert "considered.249=blocked-by-241" in selection.considered


def test_selection_under_a_freeze_refuses_with_the_freeze_rather_than_going_quiet() -> None:
    policy = parsed(state="frozen", packages=[package_document()])
    selection = queue.select(policy, [queue.Candidate(249, "x")], in_flight_of(), count=1)
    assert selection.chosen == ()
    assert selection.refusal is not None
    assert selection.refusal.kind == "dispatch_frozen"
    assert "considered.249=frozen-and-not-carved-out" in selection.considered


def test_a_carved_out_candidate_survives_the_freeze() -> None:
    policy = parsed(state="frozen", packages=[package_document(issues=[250])])
    selection = queue.select(policy, [queue.Candidate(250, "queue")], in_flight_of(), count=1)
    assert [c.issue for c in selection.chosen] == [250]
    assert selection.refusal is None


def test_an_empty_ready_list_refuses_no_ready_issue() -> None:
    selection = queue.select(parsed(state="open"), [], in_flight_of(), count=1)
    assert selection.refusal is not None
    assert selection.refusal.kind == "no_ready_issue"
    assert "open=0" in " ".join(selection.refusal.found)


def test_every_candidate_dropped_for_a_non_freeze_reason_refuses_no_ready_issue() -> None:
    selection = queue.select(
        parsed(state="open"),
        [queue.Candidate(249, "x", "Blocked-by: #241")],
        in_flight_of(),
        count=1,
    )
    assert selection.refusal is not None
    assert selection.refusal.kind == "no_ready_issue"
    assert "considered.249=blocked-by-241" in " ".join(selection.refusal.found)


def test_selection_never_returns_more_than_the_limit_leaves_room_for() -> None:
    policy = parsed(state="open", limit=3)
    candidates = [queue.Candidate(n, f"issue {n}") for n in (301, 302, 303)]
    selection = queue.select(policy, candidates, in_flight_of(170, 241), count=3)
    assert [c.issue for c in selection.chosen] == [301]


def test_selection_refuses_wip_reached_when_the_limit_leaves_no_room_at_all() -> None:
    policy = parsed(state="open", limit=2)
    selection = queue.select(policy, [queue.Candidate(301, "x")], in_flight_of(170, 241), count=1)
    assert selection.chosen == ()
    assert selection.refusal is not None
    assert selection.refusal.kind == "wip_reached"


def test_count_bounds_how_many_are_chosen() -> None:
    policy = parsed(state="open", limit=9)
    candidates = [queue.Candidate(n, "x") for n in (301, 302, 303)]
    assert len(queue.select(policy, candidates, in_flight_of(), count=1).chosen) == 1
    assert len(queue.select(policy, candidates, in_flight_of(), count=2).chosen) == 2


# ---------------------------------------------------------------------------------- writing


@pytest.mark.parametrize(
    "argv",
    [
        ["freeze"],
        ["open"],
        ["wip", "--limit", "3"],
        ["package", "add", "--name", "x", "--issues", "1"],
        ["package", "drop", "--name", "x"],
        ["freeze", "--ruling", "   "],
    ],
)
def test_a_write_without_a_ruling_is_refused(
    tmp_path: Path, argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    """Acceptance criterion 1. An entry with no ruling is an inference recorded as a decision."""
    code = queue.main(["--queue-dir", str(tmp_path / "queue"), *argv])
    assert code == queue.EXIT_REFUSED
    assert "refusal=ruling_required" in capsys.readouterr().err
    assert not (tmp_path / "queue" / "policy.json").exists()


def test_the_writers_build_a_policy_one_ruling_at_a_time(tmp_path: Path) -> None:
    directory = str(tmp_path / "queue")
    assert queue.main(["--queue-dir", directory, "open", "--ruling", RULING]) == 0
    # Half a policy is not a policy: the limit has not been ruled yet.
    policy, refusal = queue.read_policy(store_at(tmp_path))
    assert policy is None
    assert refusal is not None
    assert "entry=wip_limit" in refusal.found

    assert queue.main(["--queue-dir", directory, "wip", "--limit", "3", "--ruling", RULING]) == 0
    policy, refusal = queue.read_policy(store_at(tmp_path))
    assert refusal is None
    assert policy is not None
    assert policy.freeze.state == "open"
    assert policy.wip_limit.value == 3
    assert policy.wip_limit.ruling == RULING


def test_every_write_appends_a_transition_beside_the_file(tmp_path: Path) -> None:
    directory = str(tmp_path / "queue")
    queue.main(["--queue-dir", directory, "freeze", "--ruling", RULING])
    queue.main(["--queue-dir", directory, "wip", "--limit", "3", "--ruling", WIP_RULING])
    journal = (tmp_path / "queue" / "transitions.jsonl").read_text(encoding="utf-8")
    rows = [json.loads(line) for line in journal.splitlines()]
    assert len(rows) == 2
    assert rows[0]["attributes"]["cti.queue.verb"] == "freeze:frozen"
    assert rows[0]["attributes"]["cti.queue.ruling"] == RULING
    assert rows[1]["attributes"]["cti.queue.verb"] == "wip"
    assert rows[1]["attributes"]["cti.queue.value"] == 3


def test_freeze_and_open_move_the_state_and_keep_the_rest(tmp_path: Path) -> None:
    directory = str(tmp_path / "queue")
    queue.main(["--queue-dir", directory, "freeze", "--ruling", RULING])
    queue.main(["--queue-dir", directory, "wip", "--limit", "3", "--ruling", WIP_RULING])
    queue.main(["--queue-dir", directory, "open", "--ruling", "human, later"])
    policy, refusal = queue.read_policy(store_at(tmp_path))
    assert refusal is None
    assert policy is not None
    assert policy.freeze.state == "open"
    assert policy.freeze.ruling == "human, later"
    assert policy.wip_limit.value == 3


def test_a_package_is_recorded_with_its_issues_reservation_and_ruling(tmp_path: Path) -> None:
    directory = str(tmp_path / "queue")
    queue.main(["--queue-dir", directory, "freeze", "--ruling", RULING])
    queue.main(["--queue-dir", directory, "wip", "--limit", "3", "--ruling", WIP_RULING])
    code = queue.main(
        [
            "--queue-dir",
            directory,
            "package",
            "add",
            "--name",
            "initiative",
            "--issues",
            "221-230,238",
            "--exempt-freeze",
            "--reserve",
            "2",
            "--note",
            "and retros",
            "--ruling",
            "human at close-down 2026-08-05",
        ]
    )
    assert code == 0
    policy, refusal = queue.read_policy(store_at(tmp_path))
    assert refusal is None
    assert policy is not None
    package = policy.packages[0]
    assert package.issues == (221, 222, 223, 224, 225, 226, 227, 228, 229, 230, 238)
    assert package.exempt_from_freeze is True
    assert package.wip_reserved == 2
    assert package.note == "and retros"


def test_adding_a_package_twice_replaces_it_rather_than_doubling_it(tmp_path: Path) -> None:
    directory = str(tmp_path / "queue")
    for issues in ("221", "221-222"):
        queue.main(
            [
                "--queue-dir",
                directory,
                "package",
                "add",
                "--name",
                "initiative",
                "--issues",
                issues,
                "--ruling",
                RULING,
            ]
        )
    document = json.loads((tmp_path / "queue" / "policy.json").read_text(encoding="utf-8"))
    assert len(document["packages"]) == 1
    assert document["packages"][0]["issues"] == [221, 222]


def test_dropping_a_package_the_policy_does_not_carry_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = str(tmp_path / "queue")
    queue.main(
        [
            "--queue-dir",
            directory,
            "package",
            "add",
            "--name",
            "a",
            "--issues",
            "1",
            "--ruling",
            RULING,
        ]
    )
    code = queue.main(
        ["--queue-dir", directory, "package", "drop", "--name", "b", "--ruling", RULING]
    )
    assert code == queue.EXIT_REFUSED
    err = capsys.readouterr().err
    assert "refusal=no_such_package" in err
    assert "known=a" in err


def test_dropping_a_package_removes_exactly_that_one(tmp_path: Path) -> None:
    directory = str(tmp_path / "queue")
    for name in ("a", "b"):
        queue.main(
            [
                "--queue-dir",
                directory,
                "package",
                "add",
                "--name",
                name,
                "--issues",
                "1",
                "--ruling",
                RULING,
            ]
        )
    assert (
        queue.main(["--queue-dir", directory, "package", "drop", "--name", "a", "--ruling", RULING])
        == 0
    )
    document = json.loads((tmp_path / "queue" / "policy.json").read_text(encoding="utf-8"))
    assert [block["name"] for block in document["packages"]] == ["b"]


def test_a_write_never_overwrites_a_policy_it_could_not_read(tmp_path: Path) -> None:
    """The evidence of what was in a corrupt file survives the next write."""
    store = store_at(tmp_path)
    store.directory.mkdir(parents=True)
    store.policy_path.write_text("not json at all", encoding="utf-8")
    code = queue.main(["--queue-dir", str(store.directory), "open", "--ruling", RULING])
    assert code == queue.EXIT_REFUSED
    assert store.policy_path.read_text(encoding="utf-8") == "not json at all"


def test_a_write_refuses_a_document_carrying_a_key_nobody_wrote(tmp_path: Path) -> None:
    store = seeded(tmp_path, {**policy_document(), "smuggled": True})
    code = queue.main(["--queue-dir", str(store.directory), "open", "--ruling", RULING])
    assert code == queue.EXIT_REFUSED
    assert "smuggled" in store.policy_path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("221", (221,)),
        ("221-223", (221, 222, 223)),
        ("221-222,238", (221, 222, 238)),
        (" 238 , 221 ", (221, 238)),
        ("221,221", (221,)),
    ],
)
def test_an_issue_list_reads_numbers_and_ranges(text: str, expected: tuple[int, ...]) -> None:
    issues, refusal = queue.parse_issues(text)
    assert refusal is None
    assert issues == expected


@pytest.mark.parametrize("text", ["", "  ", "abc", "221-", "230-221", "#221", "221..230"])
def test_anything_else_in_an_issue_list_is_refused(text: str) -> None:
    issues, refusal = queue.parse_issues(text)
    assert issues == ()
    assert refusal is not None
    assert refusal.kind == "bad_issue_list"


@pytest.mark.parametrize(
    ("issues", "rendered"),
    [
        ((), "none"),
        ((221,), "221"),
        ((221, 222, 223), "221-223"),
        ((221, 222, 238), "221-222,238"),
        ((221, 223, 225), "221,223,225"),
    ],
)
def test_an_issue_set_renders_the_way_the_flag_accepts_it_back(
    issues: tuple[int, ...], rendered: str
) -> None:
    assert queue._render_issues(issues) == rendered  # noqa: SLF001 — the renderer is the subject


def test_a_negative_wip_limit_is_refused_and_points_at_freeze(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = queue.main(
        ["--queue-dir", str(tmp_path / "q"), "wip", "--limit", "-1", "--ruling", RULING]
    )
    assert code == queue.EXIT_REFUSED
    assert "refusal=bad_limit" in capsys.readouterr().err


# -------------------------------------------------------------------------------- reading


def test_report_emits_one_underfill_verdict_from_the_live_queue_derivation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    store = seeded(tmp_path, policy_document(state="open", limit=3))
    dispatches = tmp_path / "dispatches"
    unfinished_dispatches(dispatches, 170, 241)
    fake_github(
        tmp_path,
        monkeypatch,
        [
            {"number": 170, "title": "already held", "body": ""},
            {"number": 249, "title": "waits", "body": "Blocked-by: #241"},
            {"number": 301, "title": "first", "body": ""},
            {"number": 302, "title": "second", "body": ""},
        ],
    )

    code = queue.main(
        [
            "--queue-dir",
            str(store.directory),
            "--root",
            str(tmp_path / "empty-root"),
            "--dispatch-dir",
            str(dispatches),
            "report",
        ]
    )

    assert code == 0
    assert capsys.readouterr().out == (
        "queue=underfilled in_flight=2/3 floor=yes room=1 eligible=2 next=301 "
        "action=refill-before-landing\n"
    )


@pytest.mark.parametrize(
    ("held", "candidates"),
    [
        ((170, 241, 278), [{"number": 301, "title": "ready", "body": ""}]),
        ((170,), [{"number": 301, "title": "waits", "body": "Blocked-by: #241"}]),
    ],
)
def test_report_is_silent_when_full_or_when_no_eligible_candidate_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    held: tuple[int, ...],
    candidates: list[dict[str, object]],
) -> None:
    store = seeded(tmp_path, policy_document(state="open", limit=3))
    dispatches = tmp_path / "dispatches"
    unfinished_dispatches(dispatches, *held)
    fake_github(tmp_path, monkeypatch, candidates)

    code = queue.main(
        [
            "--queue-dir",
            str(store.directory),
            "--root",
            str(tmp_path / "empty-root"),
            "--dispatch-dir",
            str(dispatches),
            "report",
        ]
    )

    assert code == 0
    assert capsys.readouterr().out == ""


def test_report_uses_the_same_package_reservation_as_candidate_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    store = seeded(
        tmp_path,
        policy_document(
            state="frozen",
            limit=3,
            packages=[package_document(issues=[301], wip_reserved=2)],
        ),
    )
    dispatches = tmp_path / "dispatches"
    unfinished_dispatches(dispatches, 170)
    fake_github(
        tmp_path,
        monkeypatch,
        [
            {"number": 300, "title": "outside reservation", "body": ""},
            {"number": 301, "title": "inside reservation", "body": ""},
        ],
    )

    code = queue.main(
        [
            "--queue-dir",
            str(store.directory),
            "--root",
            str(tmp_path / "empty-root"),
            "--dispatch-dir",
            str(dispatches),
            "report",
        ]
    )

    assert code == 0
    assert capsys.readouterr().out == (
        "queue=underfilled in_flight=1/3 floor=yes room=2 eligible=1 next=301 "
        "action=refill-before-landing\n"
    )


def test_report_fails_closed_in_one_line_when_the_tracker_is_unreadable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    store = seeded(tmp_path, policy_document(state="open", limit=3))
    fake_github(tmp_path, monkeypatch, [])
    monkeypatch.setenv("CTI_TEST_GH_FAIL", "1")

    code = queue.main(
        [
            "--queue-dir",
            str(store.directory),
            "--root",
            str(tmp_path / "empty-root"),
            "--dispatch-dir",
            str(tmp_path / "dispatches"),
            "report",
        ]
    )

    captured = capsys.readouterr()
    assert code == 0
    assert captured.err == ""
    assert captured.out == (
        "queue=unreadable refill=unknown class=infra_unavailable reason=github_unreadable "
        "action=restore-tracker-read-before-refill\n"
    )


def test_report_never_claims_spare_capacity_when_in_flight_tracker_reads_fail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    store = seeded(tmp_path, policy_document(state="open", limit=3))
    dispatches = tmp_path / "dispatches"
    unfinished_dispatches(dispatches, 170)
    fake_github(
        tmp_path,
        monkeypatch,
        [{"number": 301, "title": "would otherwise be next", "body": ""}],
    )
    monkeypatch.setenv("CTI_TEST_GH_VIEW_FAIL", "1")

    code = queue.main(
        [
            "--queue-dir",
            str(store.directory),
            "--root",
            str(tmp_path / "empty-root"),
            "--dispatch-dir",
            str(dispatches),
            "report",
        ]
    )

    assert code == 0
    assert capsys.readouterr().out == (
        "queue=unreadable refill=unknown class=infra_unavailable reason=github_unreadable "
        "action=restore-tracker-read-before-refill\n"
    )


def test_watch_report_folds_in_the_queue_verdict_without_dispatching(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = seeded(tmp_path, policy_document(state="open", limit=3))
    policy_before = store.policy_path.read_bytes()
    fake_github(
        tmp_path,
        monkeypatch,
        [{"number": 301, "title": "next", "body": ""}],
    )
    environment = {
        **os.environ,
        "CTI_ADMISSION_DIR": str(tmp_path / "admission"),
        "CTI_BREAKER_DIR": str(tmp_path / "breaker"),
        "CTI_DISPATCH_DIR": str(tmp_path / "dispatches"),
        "CTI_QUEUE_DIR": str(store.directory),
        "CTI_QUEUE_ROOT": str(tmp_path / "empty-root"),
        "CTI_WATCH_DIR": str(tmp_path / "watch"),
    }

    done = subprocess.run(
        ["just", "watch-report"],  # noqa: S607 — `just` intentionally resolves off PATH
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )

    assert done.returncode == 0
    assert [line for line in done.stdout.splitlines() if line.startswith("queue=")] == [
        (
            "queue=underfilled in_flight=0/3 floor=yes room=3 eligible=1 next=301 "
            "action=refill-before-landing"
        )
    ]
    assert not (tmp_path / "dispatches").exists(), "the report writes and dispatches nothing"
    assert store.policy_path.read_bytes() == policy_before, "the report does not amend the ruling"


def test_state_prints_every_entry_with_its_ruling_then_the_list_then_the_count(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = seeded(tmp_path, policy_document(packages=[package_document(note="and retros")]))
    code = queue.main(
        [
            "--queue-dir",
            str(store.directory),
            "--root",
            str(tmp_path / "empty-root"),
            "--dispatch-dir",
            str(tmp_path / "no-dispatches"),
            "state",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert f"freeze_ruling={RULING}" in out
    assert f"wip_ruling={WIP_RULING}" in out
    assert "package.initiative.issues=221-222" in out
    assert "package.initiative.wip_reserved=0" in out
    assert "package.initiative.note=and retros" in out
    assert "in_flight=0 floor=yes" in out


def test_check_exits_non_zero_under_a_freeze_and_zero_when_clear(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    frozen = seeded(tmp_path / "a", policy_document(state="frozen"))
    argv = ["--root", str(tmp_path / "empty"), "--dispatch-dir", str(tmp_path / "none")]
    assert queue.main(["--queue-dir", str(frozen.directory), *argv, "check", "--issue", "249"]) == 1
    assert "refusal=dispatch_frozen" in capsys.readouterr().err

    clear = seeded(tmp_path / "b", policy_document(state="open"))
    assert queue.main(["--queue-dir", str(clear.directory), *argv, "check", "--issue", "249"]) == 0
    assert "queue=clear" in capsys.readouterr().out


def test_check_on_an_absent_policy_refuses_rather_than_permitting(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = queue.main(["--queue-dir", str(tmp_path / "nothing"), "check", "--issue", "249"])
    assert code == queue.EXIT_REFUSED
    assert "refusal=policy_absent" in capsys.readouterr().err


def test_the_derivation_reads_this_boxs_real_dispatch_records(tmp_path: Path) -> None:
    """`dispatch_records` against records laid out the way `just dispatch` lays them out."""
    root = tmp_path / "dispatches"
    for name, issue, finished in (("d-1", 250, False), ("d-2", 241, True), ("d-3", 0, False)):
        record = root / name
        record.mkdir(parents=True)
        (record / "dispatch.json").write_text(json.dumps({"issue": issue}), encoding="utf-8")
        if finished:
            (record / "result.json").write_text("{}", encoding="utf-8")
    assert queue.dispatch_records(root) == (
        (250, "d-1", False),
        (241, "d-2", True),
        (0, "d-3", False),
    )
    assert queue.dispatch_records(tmp_path / "absent") == ()


def test_a_dispatch_record_that_cannot_be_read_is_skipped_rather_than_guessed(
    tmp_path: Path,
) -> None:
    root = tmp_path / "dispatches"
    (root / "d-bad").mkdir(parents=True)
    (root / "d-bad" / "dispatch.json").write_text("{", encoding="utf-8")
    (root / "d-none").mkdir(parents=True)
    assert queue.dispatch_records(root) == ()


# ------------------------------------------------------------------------- the dispatch rung


def dry_run(
    tmp_path: Path, queue_dir: Path, issue: int = 249, worktree: Path | None = None
) -> tuple[int, str, str]:
    """Plan a dispatch through `main`, exactly as `just dispatch --dry-run` does."""
    tree = worktree or REPO
    code = dispatch.main(
        [
            "--dry-run",
            "--lane",
            "claude-native",
            "--profile",
            "opus-high",
            "--seat",
            "implementer",
            "--issue",
            str(issue),
            "--worktree",
            str(tree),
            "--dispatch-dir",
            str(tmp_path / "dispatches"),
            "--credentials",
            str(tmp_path / "credentials.env"),
            "--breaker-dir",
            str(tmp_path / "breaker"),
            "--admission-dir",
            str(tmp_path / "admission"),
            "--queue-dir",
            str(queue_dir),
            "--queue-root",
            str(tmp_path / "queue-root"),
            "--issue-body",
            str(READY_BODY),
        ]
    )
    return code, "", ""


def test_a_dry_run_under_a_recorded_freeze_refuses_and_launches_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Acceptance criterion 3, against the dispatcher rather than by hand."""
    store = seeded(tmp_path, policy_document(state="frozen", packages=[package_document()]))
    code, _, _ = dry_run(tmp_path, store.directory, issue=249)
    assert code == dispatch.EXIT_REFUSED
    captured = capsys.readouterr()
    assert captured.out == "", "a refused dispatch prints no plan"
    assert "refusal=dispatch_frozen" in captured.err
    assert f"ruling={RULING}" in captured.err
    assert "carve_out.initiative=issues=221-222 exempt=True" in captured.err
    assert "class=" not in captured.err, "#238's precedent: no failure class"
    assert not (tmp_path / "dispatches").exists(), "nothing was written, so nothing was launched"


def test_a_dry_run_for_a_carved_out_issue_is_planned_normally(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = seeded(
        tmp_path, policy_document(state="frozen", packages=[package_document(issues=[249])])
    )
    code, _, _ = dry_run(tmp_path, store.directory, issue=249)
    assert code == 0
    out = capsys.readouterr().out
    assert "issue=249" in out
    assert "argv=" in out
    assert not (tmp_path / "dispatches").exists(), "a dry run still writes no record"


def test_the_queue_rung_is_climbed_before_the_admission_and_breaker_rungs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """No change of lane, profile or seat clears a freeze, so it is heard first."""
    store = seeded(tmp_path, policy_document(state="frozen"))
    breaker = load_tool("breaker")
    breaker_dir = tmp_path / "breaker"
    breaker_dir.mkdir()
    code = dispatch.main(
        [
            "--dry-run",
            "--lane",
            "claude-native",
            "--profile",
            "opus-high",
            "--seat",
            "implementer",
            "--issue",
            "249",
            "--worktree",
            str(REPO),
            "--dispatch-dir",
            str(tmp_path / "dispatches"),
            "--credentials",
            str(tmp_path / "credentials.env"),
            "--breaker-dir",
            str(breaker_dir),
            "--admission-dir",
            str(tmp_path / "admission"),
            "--queue-dir",
            str(store.directory),
            "--queue-root",
            str(tmp_path / "queue-root"),
            "--issue-body",
            str(READY_BODY),
        ]
    )
    assert breaker is not None
    assert code == dispatch.EXIT_REFUSED
    assert "refusal=dispatch_frozen" in capsys.readouterr().err


def test_readiness_is_heard_before_the_freeze_because_its_remedy_can_start_now(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """#241's rung sits above this one on its own criterion, applied consistently.

    An unready issue can be made ready this minute; a freeze is the one refusal on this
    ladder whose remedy nobody but the human can start. So the dispatcher hears the one it
    can act on, and hears the freeze when it comes back with a ready issue.
    """
    store = seeded(tmp_path, policy_document(state="frozen"))
    body = tmp_path / "unready.md"
    body.write_text(
        "The dispatcher feels slow lately and somebody should have a look.\n", encoding="utf-8"
    )
    code = dispatch.main(
        [
            "--dry-run",
            "--lane",
            "claude-native",
            "--profile",
            "opus-high",
            "--seat",
            "implementer",
            "--issue",
            "249",
            "--worktree",
            str(REPO),
            "--dispatch-dir",
            str(tmp_path / "dispatches"),
            "--credentials",
            str(tmp_path / "credentials.env"),
            "--breaker-dir",
            str(tmp_path / "breaker"),
            "--admission-dir",
            str(tmp_path / "admission"),
            "--queue-dir",
            str(store.directory),
            "--queue-root",
            str(tmp_path / "queue-root"),
            "--issue-body",
            str(body),
        ]
    )
    assert code == dispatch.EXIT_REFUSED
    assert "refusal=issue_not_ready" in capsys.readouterr().err


def test_a_registry_typo_is_still_heard_before_the_freeze(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A typo is not a state of the world at all, so it stays the first rung."""
    store = seeded(tmp_path, policy_document(state="frozen"))
    code = dispatch.main(
        [
            "--dry-run",
            "--lane",
            "nonesuch",
            "--profile",
            "opus-high",
            "--seat",
            "implementer",
            "--issue",
            "249",
            "--queue-dir",
            str(store.directory),
            "--issue-body",
            str(READY_BODY),
        ]
    )
    assert code == dispatch.EXIT_REFUSED
    assert "refusal=unknown_lane" in capsys.readouterr().err


def test_a_dispatch_against_an_absent_policy_refuses_rather_than_dispatching(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _, _ = dry_run(tmp_path, tmp_path / "no-queue-here", issue=249)
    assert code == dispatch.EXIT_REFUSED
    assert "refusal=policy_absent" in capsys.readouterr().err


def test_no_option_argument_or_variable_dispatches_through_a_freeze() -> None:
    """Acceptance criterion 4, on #238's pattern, asserted where an override would appear.

    The two directory options the rung does take move *where the state is read* — the seam
    `CTI_BREAKER_DIR` and `CTI_ADMISSION_DIR` already are for a forked test — and neither can
    turn a recorded freeze into a dispatch, which the tests above assert by using them.
    """
    for flag in (
        "--force",
        "--override",
        "--ignore-freeze",
        "--no-queue",
        "--skip-queue",
        "--thaw",
        "--unfreeze",
        "--emergency",
        "--anyway",
    ):
        with pytest.raises(SystemExit):
            dispatch.parse_args([flag])


def test_the_only_queue_options_the_dispatcher_takes_are_the_two_state_seams() -> None:
    parsed_args = dispatch.parse_args([])
    queue_options = sorted(name for name in vars(parsed_args) if "queue" in name)
    assert queue_options == ["queue_dir", "queue_root"]


def test_the_environment_variables_the_rung_reads_are_the_two_directories(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CTI_QUEUE_DIR", "/somewhere/queue")
    monkeypatch.setenv("CTI_QUEUE_ROOT", "/somewhere/root")
    parsed_args = dispatch.parse_args([])
    assert parsed_args.queue_dir == "/somewhere/queue"
    assert parsed_args.queue_root == "/somewhere/root"


def test_the_dispatcher_carries_the_queues_refusal_across_without_restating_it() -> None:
    original = queue.Refusal("dispatch_frozen", ("issue=1",), "do this")
    carried = dispatch._as_refusal(original)  # noqa: SLF001 — the adapter is the subject
    assert carried is not None
    assert (carried.kind, carried.found, carried.action) == (
        original.kind,
        original.found,
        original.action,
    )
    assert carried.failure_class == ""
    assert dispatch._as_refusal(None) is None  # noqa: SLF001 — the adapter is the subject


def test_the_recipe_runs_the_module_under_its_longer_name() -> None:
    """`queue` would shadow the standard library's, which pytest-xdist itself imports."""
    justfile = (REPO / "justfile").read_text(encoding="utf-8")
    assert 'uv run python tools/queue_policy.py "$@"' in justfile
    assert not (REPO / "tools" / "queue.py").exists()


def test_the_recipe_carries_a_ruling_across_whole_rather_than_word_by_word() -> None:
    """A ruling is a sentence, and `{{ args }}` would splice it in as bare shell words."""
    justfile = (REPO / "justfile").read_text(encoding="utf-8")
    recipe = justfile[justfile.index("[positional-arguments]\nqueue *args:") :]
    assert recipe.startswith("[positional-arguments]\nqueue *args:\n    uv run python")
    assert "{{ args }}" not in recipe.split("\n\n")[0]


def test_a_ruling_made_earlier_is_recorded_at_its_own_moment_not_the_transcriptions(
    tmp_path: Path,
) -> None:
    """A freeze in force since yesterday must not read as having begun this morning."""
    directory = str(tmp_path / "queue")
    queue.main(["--queue-dir", directory, "freeze", "--ruling", RULING, "--since", WHEN])
    queue.main(
        [
            "--queue-dir",
            directory,
            "wip",
            "--limit",
            "3",
            "--ruling",
            WIP_RULING,
            "--since",
            WHEN,
        ]
    )
    policy, refusal = queue.read_policy(store_at(tmp_path))
    assert refusal is None
    assert policy is not None
    assert policy.freeze.since == WHEN
    assert policy.wip_limit.since == WHEN


def test_the_clock_the_writers_stamp_is_the_one_a_reader_can_order_by(tmp_path: Path) -> None:
    directory = str(tmp_path / "queue")
    queue.main(["--queue-dir", directory, "freeze", "--ruling", RULING])
    document = json.loads((tmp_path / "queue" / "policy.json").read_text(encoding="utf-8"))
    stamped = datetime.fromisoformat(document["freeze"]["since"])
    assert stamped.tzinfo is not None
    assert abs((datetime.now(tz=UTC) - stamped).total_seconds()) < 120
