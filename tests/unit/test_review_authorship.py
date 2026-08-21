"""The interactive authorship record, and the deadlock it closes (#398).

#294 bars a dispatched session from writing under `.claude/`, so a change there is
authored interactively by construction — and an interactive session writes no dispatch
record, so `just land`'s never-alone rung read an empty author set and refused every
such landing (`authorship_unrecorded`). Both halves were right; together they left no
route, which is where #330 sat at `c380689`: five review rounds, verdict recorded,
gates green, refused at the landing.

What is asserted here is the whole of the fix and, more importantly, that it is not a
weakening of the rung it unblocks:

- the record's own reader and writer, including every way a stored record refuses to
  be read — an author set is what the never-alone check runs against, so a record that
  will not open is an unperformable read rather than an empty answer (#41);
- the merge, which only ever *adds* names and clears the "no records" states without
  ever clearing `records_unreadable`;
- both ends of the landing rung: an interactively authored change reaching a clearance,
  **and the same-session arrangement still refused** — a declared author reviewing its
  own diff meets `review_same_profile` exactly as a dispatched one does.
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import threading
from typing import TYPE_CHECKING, Final

import pytest
from conftest import REPO, load_tool

if TYPE_CHECKING:
    from pathlib import Path

dispatch = load_tool("dispatch")
review_loop = load_tool("review_loop")
land_review = load_tool("land_review")

ISSUE: Final = 398
SHA: Final = "c" * 40
DIFF_ID: Final = "c" * 64
STAMP: Final = "20260817T0000Z"
AUTHOR: Final = "opus-high"
REVIEWER: Final = "codex-luna-max"


def _record(root: Path, issue: int, document: object) -> Path:
    """Plant a stored authorship record by hand, the shape a hand-edit would leave it."""
    target = review_loop.authorship_path(root, issue)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document), encoding="utf-8")
    return target


def _author(root: Path, profile: str = AUTHOR, *, issue: int = ISSUE) -> bool:
    """Declare one interactive author through the writer under test."""
    return review_loop.store_authorship(root, issue, profile, SHA, STAMP)


# ------------------------------------------------------------------ the record's own reader


def test_a_declaration_reads_back_as_the_author_it_named(tmp_path: Path) -> None:
    """The round trip, through the writer and the reader a landing calls."""
    assert _author(tmp_path) is True

    assert review_loop.recorded_authors(tmp_path, ISSUE) == (AUTHOR,)


def test_no_record_at_all_is_an_answer_rather_than_a_gap(tmp_path: Path) -> None:
    """Most issues are authored through a dispatch and carry no such record."""
    assert review_loop.recorded_authors(tmp_path, ISSUE) == ()


def test_declaring_the_same_profile_twice_records_it_once(tmp_path: Path) -> None:
    """The same claim twice is the same claim: idempotent, not a refusal and not two rows."""
    assert _author(tmp_path) is True
    assert _author(tmp_path) is False

    assert review_loop.recorded_authors(tmp_path, ISSUE) == (AUTHOR,)
    stored = json.loads(review_loop.authorship_path(tmp_path, ISSUE).read_text(encoding="utf-8"))
    assert len(stored["authors"]) == 1


def test_a_second_profile_joins_the_first(tmp_path: Path) -> None:
    """Two interactive sessions on one issue are two authors, and both exclude a reviewer."""
    _author(tmp_path)
    _author(tmp_path, "opus-xhigh")

    assert review_loop.recorded_authors(tmp_path, ISSUE) == (AUTHOR, "opus-xhigh")


def test_a_re_declaration_at_a_new_commit_keeps_both(tmp_path: Path) -> None:
    """A rebase is the ordinary second declaration, and appending is the only true answer.

    Dropping it leaves the trail naming a commit that is not the one landed; overwriting
    erases a declaration that was made. The claim is the `(profile, sha)` pair, so a new
    commit is a new claim — and it costs the check nothing, because the set a reviewer is
    excluded against deduplicates on profile.
    """
    rebased = "d" * 40
    assert _author(tmp_path) is True
    assert review_loop.store_authorship(tmp_path, ISSUE, AUTHOR, rebased, STAMP) is True

    stored = json.loads(review_loop.authorship_path(tmp_path, ISSUE).read_text(encoding="utf-8"))
    assert [entry["sha"] for entry in stored["authors"]] == [SHA, rebased]
    assert review_loop.recorded_authors(tmp_path, ISSUE) == (AUTHOR,)


def test_two_declarations_racing_on_one_issue_lose_neither(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A lost entry is a profile the never-alone check stops excluding — the one bad direction.

    The read, the append and the write are one locked act, and the lock is what this
    asserts: both writers are held at the barrier the instant they have read, so without it
    both append to the same empty record and the second `replace` wins with the first
    author gone. With it, only one writer ever reaches the barrier, which breaks on its own
    timeout and lets the pair through in series.
    """
    gate = threading.Barrier(2, timeout=0.2)
    read = review_loop._authorship_entries  # noqa: SLF001 — the interleave under test is inside it

    def read_then_meet(root: Path, issue: int) -> tuple[dict[str, object], ...]:
        entries = read(root, issue)
        with contextlib.suppress(threading.BrokenBarrierError):
            gate.wait()
        return entries

    monkeypatch.setattr(review_loop, "_authorship_entries", read_then_meet)
    racing = [
        threading.Thread(target=_author, args=(tmp_path, profile))
        for profile in (AUTHOR, "opus-xhigh")
    ]
    for thread in racing:
        thread.start()
    for thread in racing:
        thread.join(timeout=10)

    assert sorted(review_loop.recorded_authors(tmp_path, ISSUE)) == [AUTHOR, "opus-xhigh"]


def test_a_declaration_carries_its_provenance_and_its_commit(tmp_path: Path) -> None:
    """`declared` is on the record as well as on the clearance; the SHA is the audit trail."""
    _author(tmp_path)

    entry = json.loads(review_loop.authorship_path(tmp_path, ISSUE).read_text(encoding="utf-8"))
    assert entry["authors"][0]["source"] == review_loop.DECLARED
    assert entry["authors"][0]["sha"] == SHA
    assert entry["authors"][0]["recorded_at"] == STAMP


def test_a_declaration_with_no_commit_in_hand_omits_the_field(tmp_path: Path) -> None:
    """A record says what it knows: an absent SHA is absent, never an empty claim."""
    review_loop.store_authorship(tmp_path, ISSUE, AUTHOR, "", STAMP)

    entry = json.loads(review_loop.authorship_path(tmp_path, ISSUE).read_text(encoding="utf-8"))
    assert "sha" not in entry["authors"][0]


@pytest.mark.parametrize(
    ("document", "described"),
    [
        ({"version": 2, "issue": ISSUE, "authors": [{"profile": AUTHOR}]}, "another version"),
        ({"version": 1, "issue": ISSUE + 1, "authors": [{"profile": AUTHOR}]}, "another issue"),
        ({"version": 1, "issue": ISSUE, "authors": []}, "no author at all"),
        ({"version": 1, "issue": ISSUE, "authors": [{"profile": ""}]}, "a blank profile"),
        ({"version": 1, "issue": ISSUE, "authors": [{"profile": None}]}, "no profile"),
        ({"version": 1, "issue": ISSUE, "authors": [AUTHOR]}, "an entry that is not an object"),
        ({"version": 1, "issue": ISSUE}, "no authors key"),
        ([{"profile": AUTHOR}], "a document that is not an object"),
    ],
)
def test_a_record_this_tool_did_not_write_is_never_read_as_an_answer(
    tmp_path: Path, document: object, described: str
) -> None:
    """Validated, never coerced: `str(None)` in an author set is an author nobody can be.

    Each of these would otherwise clear the never-alone check by supplying an author the
    reviewer is guaranteed not to be — the failure `recorded_arbiter` documents, arriving
    at the record that decides whether the check has a set to run against at all.
    """
    _record(tmp_path, ISSUE, document)

    with pytest.raises(review_loop.ExternalError, match=f"#{ISSUE}"):
        review_loop.recorded_authors(tmp_path, ISSUE)
    assert described  # the parametrisation's own label, kept in the failure output


def test_a_record_that_will_not_parse_is_unperformable_rather_than_empty(tmp_path: Path) -> None:
    """A truncated record could be naming this reviewer; nothing is taken from it."""
    target = review_loop.authorship_path(tmp_path, ISSUE)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('{"version": 1, "issue"', encoding="utf-8")

    with pytest.raises(review_loop.ExternalError, match="will not read"):
        review_loop.recorded_authors(tmp_path, ISSUE)


def test_the_writer_refuses_to_append_to_a_record_it_cannot_read(tmp_path: Path) -> None:
    """A declaration must not silently overwrite the authors a broken record still names."""
    _record(tmp_path, ISSUE, {"version": 1, "issue": ISSUE, "authors": [{"profile": 12}]})

    with pytest.raises(review_loop.ExternalError):
        _author(tmp_path)


# ------------------------------------------------------------------ the command surface


def _author_repo(root: Path) -> tuple[Path, str]:
    repo = root / "repo"
    repo.mkdir()
    review_loop.git("init", "-q", "-b", "main", cwd=repo)
    review_loop.git("config", "user.email", "t@example.invalid", cwd=repo)
    review_loop.git("config", "user.name", "t", cwd=repo)
    (repo / "README").write_text("base\n", encoding="utf-8")
    review_loop.git("add", "README", cwd=repo)
    review_loop.git("commit", "-q", "-m", "base", cwd=repo)
    return repo, review_loop.git("rev-parse", "HEAD", cwd=repo).strip()


def _author_command(
    root: Path,
    repo: Path,
    profile: str = AUTHOR,
    *,
    issue: int = ISSUE,
    sha: str | None = None,
) -> int:
    named = sha or review_loop.git("rev-parse", "HEAD", cwd=repo).strip()
    return review_loop.main(
        [
            "author",
            "--issue",
            str(issue),
            "--root",
            str(root),
            "--profile",
            profile,
            "--sha",
            named,
            "--repo",
            str(repo),
        ],
        now=lambda: 0.0,
    )


def test_the_command_records_the_declaration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The route the refusal names, end to end from the command line."""
    monkeypatch.delenv("CTI_DISPATCH_ID", raising=False)

    repo, _head = _author_repo(tmp_path)

    assert _author_command(tmp_path, repo) == review_loop.OK
    assert review_loop.recorded_authors(tmp_path, ISSUE) == (AUTHOR,)


def test_a_dispatched_session_may_not_declare_interactive_authorship(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The one provenance fact this command can actually check, and it checks it.

    A dispatched session's profile is already on its own dispatch record, and the work
    this record exists for is work #294 says a dispatched session must not have done —
    so a declaration from inside a dispatch is a second author nothing corroborates.
    """
    monkeypatch.setenv("CTI_DISPATCH_ID", "d-20260817-000000-abc123")

    repo, _head = _author_repo(tmp_path)

    assert _author_command(tmp_path, repo) == review_loop.REFUSED
    assert review_loop.recorded_authors(tmp_path, ISSUE) == ()


def test_an_unregistered_profile_is_refused_rather_than_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A typo names an author no reviewer could ever be, which clears the check silently."""
    monkeypatch.delenv("CTI_DISPATCH_ID", raising=False)

    repo, _head = _author_repo(tmp_path)

    assert _author_command(tmp_path, repo, "opus-hihg") == review_loop.REFUSED
    assert review_loop.recorded_authors(tmp_path, ISSUE) == ()


def test_the_command_refuses_a_sha_that_names_no_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("CTI_DISPATCH_ID", raising=False)
    repo, _head = _author_repo(tmp_path)

    assert _author_command(tmp_path, repo, sha="f" * 40) == review_loop.REFUSED
    assert "refusal=commit_not_found" in capsys.readouterr().err
    assert review_loop.recorded_authors(tmp_path, ISSUE) == ()


def test_the_command_pins_the_shared_invalid_sha_refusal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("CTI_DISPATCH_ID", raising=False)
    repo, head = _author_repo(tmp_path)

    assert _author_command(tmp_path, repo, sha=head[:32]) == review_loop.REFUSED
    assert (
        "action=Name the reviewed commit in full — a commit is named by its full"
        " 40-character SHA, never a shortened form."
    ) in capsys.readouterr().err
    assert review_loop.recorded_authors(tmp_path, ISSUE) == ()


# ------------------------------------------------------------------ the merge


def test_a_declaration_fills_the_set_the_dispatch_records_left_empty() -> None:
    """The deadlock's mechanism: an empty scan plus a declaration is a complete read."""
    merged = dispatch.with_declared_authors(
        dispatch.Authorship(why=dispatch.NO_AUTHORING_DISPATCH), (AUTHOR,), "record.json"
    )

    assert merged.potential == (AUTHOR,)
    assert merged.records == ("record.json",)
    assert merged.complete is True


def test_a_declaration_never_repairs_a_record_that_would_not_open() -> None:
    """#41's rule survives the fix: an unread record stays unread whatever anybody declares."""
    merged = dispatch.with_declared_authors(
        dispatch.Authorship(("opus-xhigh",), ("d-1",), why=dispatch.RECORDS_UNREADABLE),
        (AUTHOR,),
        "record.json",
    )

    assert merged.potential == ("opus-xhigh", AUTHOR)
    assert merged.why == dispatch.RECORDS_UNREADABLE
    assert merged.complete is False


def test_a_declaration_of_a_profile_the_records_already_place_adds_nothing() -> None:
    """One profile, one entry: the set is what a reviewer is checked against, not a tally."""
    scanned = dispatch.Authorship((AUTHOR,), ("d-1",))

    assert dispatch.with_declared_authors(scanned, (AUTHOR,), "record.json") == scanned


def test_no_declaration_leaves_the_scan_exactly_as_it_stood() -> None:
    """Every issue authored through a dispatch reads as it did before #398."""
    empty = dispatch.Authorship(why=dispatch.NO_DISPATCH_RECORDS)

    assert dispatch.with_declared_authors(empty, (), "record.json") == empty


# ------------------------------------------------------------------ the landing rung, both ends


def _stage(tmp_path: Path, *, reviewer: str = REVIEWER, authoring: str = "") -> tuple[Path, Path]:
    """Stage a bound, completed, clean review over work no dispatch record claims.

    The #330 arrangement exactly: the review is dispatched and on the record, and the
    implementing work is not, because it was written under `.claude/` in an interactive
    session.

    `authoring` puts an implementing dispatch record beside the review's, which is the one
    variation that changes what a *lost* declaration does: with the set non-empty the
    landing's empty-set refusal cannot fire, so the loss has nothing else to catch it (#398
    round 2).
    """
    dispatch_root = tmp_path / "dispatches"
    review_root = tmp_path / "review"
    record = dispatch_root / "d-review-1"
    record.mkdir(parents=True, exist_ok=True)
    (record / "dispatch.json").write_text(
        json.dumps(
            {
                "seat": "review",
                "issue": ISSUE,
                "base_sha": SHA,
                "profile": reviewer,
                "lane": "codex",
                "planned_at": STAMP,
                "dispatch_id": "d-review-1",
            }
        ),
        encoding="utf-8",
    )
    (record / "result.json").write_text(
        json.dumps({"returncode": 0, "outcome": "ok", "ended_at": STAMP}), encoding="utf-8"
    )
    (record / "verdict.json").write_text(
        json.dumps(
            {
                "version": 1,
                "issue": ISSUE,
                "reviewed_sha": SHA,
                "diff_id": DIFF_ID,
                "review_dispatch": "d-review-1",
                "reviewer_profile": reviewer,
                "reviewer_lane": "codex",
                "findings": [],
                "recorded_at": STAMP,
                "alternates": [],
            }
        ),
        encoding="utf-8",
    )
    if authoring:
        implementing = dispatch_root / "d-implement-1"
        implementing.mkdir(parents=True, exist_ok=True)
        (implementing / "dispatch.json").write_text(
            json.dumps(
                {
                    "seat": "implementer",
                    "issue": ISSUE,
                    "base_sha": SHA,
                    "profile": authoring,
                    "lane": "zai",
                    "planned_at": STAMP,
                    "dispatch_id": "d-implement-1",
                }
            ),
            encoding="utf-8",
        )
        (implementing / "result.json").write_text(
            json.dumps({"returncode": 0, "outcome": "ok", "ended_at": STAMP}), encoding="utf-8"
        )
    return dispatch_root, review_root


def _rung(roots: tuple[Path, Path]) -> land_review.Outcome:
    """Call the rung over a `.claude/` skill change — interactive by #294, and not a gate.

    `gate_paths=()` is the honest read for this diff: routing class 6 names `.claude/hooks/`
    and `.claude/settings.json`, and a skill file is neither, so ADR-0073's cross-lane
    predicate has nothing to say about these landings and the declaration rungs below are
    what they were.
    """
    dispatch_root, review_root = roots
    return land_review.review_finding(
        ISSUE, SHA, (".claude/skills/retro/SKILL.md",), (), None, dispatch_root, review_root
    )


def test_an_interactively_authored_change_is_refused_until_it_is_declared(
    tmp_path: Path,
) -> None:
    """The deadlock, and the refusal now naming the route out of it."""
    refusal = _rung(_stage(tmp_path)).refusal

    assert refusal.kind == "authorship_unrecorded"
    assert "just review-loop author" in refusal.action
    assert "#294" in refusal.action


def test_a_declared_author_clears_the_landing_the_records_could_not(tmp_path: Path) -> None:
    """The acceptance criterion: a `.claude/` change reaches `origin/main` through `just land`."""
    roots = _stage(tmp_path)
    _author(roots[1])

    outcome = _rung(roots)

    assert outcome.refusal is None
    assert f"authorship=checked potential={AUTHOR} declared={AUTHOR}" in outcome.cleared
    assert land_review.DECLARED_AUTHOR_LIMIT in outcome.cleared


def test_the_declared_author_reviewing_its_own_diff_is_still_refused(tmp_path: Path) -> None:
    """The failure mode this fix must not have: clearing the deadlock by clearing the check.

    One instance authors the change in its own session and dispatches the review on its
    own profile. The declaration is the only record of the authorship, and it is the
    record that catches it — `review_same_profile`, the same refusal a dispatched author
    would have met.
    """
    roots = _stage(tmp_path, reviewer=AUTHOR)
    _author(roots[1])

    refusal = _rung(roots).refusal

    assert refusal.kind == "review_same_profile"
    assert f"reviewer_profile={AUTHOR}" in refusal.found


# ------------------------------------------------------------------ the arbiter's walk


def _escalate(tmp_path: Path, issue: int) -> dict[str, object]:
    """Open a loop and resolve its arbiter, returning the record `escalate` wrote."""
    assert _escalate_run(tmp_path, issue) == review_loop.OK
    root = tmp_path / "review"
    return json.loads((root / str(issue) / review_loop.ESCALATION_FILE).read_text(encoding="utf-8"))


def _escalate_run(tmp_path: Path, issue: int) -> int:
    """Open a loop and run the arbiter's walk, returning `escalate`'s own exit code.

    Split from `_escalate` so a refusal is a case this suite can state rather than an
    assertion failure inside a helper (#398 round 2).
    """
    root = tmp_path / "review"
    credentials = tmp_path / "credentials.env"
    credentials.write_text("# no keys the walk reads\n", encoding="utf-8")
    credentials.chmod(0o600)
    clock = iter(range(1, 100))
    base = ["--root", str(root), "--journal", str(tmp_path / "journal.jsonl")]
    assert (
        review_loop.main(
            ["open", "--issue", str(issue), *base, "--finding", "F1=critical"],
            now=lambda: float(next(clock)),
        )
        == review_loop.OK
    )
    return review_loop.main(
        [
            *["escalate", "--issue", str(issue), *base],
            *["--seat", "implementer", "--dispatch-dir", str(tmp_path / "dispatches")],
            *["--admission-dir", str(tmp_path / "admission")],
            *["--breaker-dir", str(tmp_path / "breaker")],
            *["--credentials", str(credentials)],
            *["--conditions", str(REPO / "config/escalation-conditions.json")],
        ],
        now=lambda: float(next(clock)),
    )


def test_the_arbiter_walk_will_not_resolve_to_a_declared_author(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An arbiter that authored the work is the proposer approving itself by another door.

    The walk's own rung excludes the profiles the *records* place on the work, and on an
    interactively authored issue the records place nobody — so this is the only thing
    keeping the arbiter of such an issue off the profile that wrote it. Asserted by
    declaring the profile the walk would otherwise have chosen and watching it choose
    another (#398 round 1: the claim was made in three documents and asserted nowhere).
    """
    policy = review_loop.routing_policy.parse_policy(
        (REPO / review_loop.routing_policy.POLICY_RELATIVE).read_text(encoding="utf-8")
    )
    monkeypatch.setattr(review_loop, "_arbiter_routing_inputs", lambda _issue: (policy, ()))
    unconstrained = str(_escalate(tmp_path, ISSUE)["arbiter"])
    assert unconstrained  # the walk resolves something to exclude in the first place

    review_loop.store_authorship(tmp_path / "review", ISSUE + 1, unconstrained, SHA, STAMP)

    assert _escalate(tmp_path, ISSUE + 1)["arbiter"] != unconstrained


def test_a_declaration_that_will_not_read_refuses_the_landing_by_name(tmp_path: Path) -> None:
    """The record that would not open could be this reviewer's own, so nothing clears."""
    roots = _stage(tmp_path)
    _record(roots[1], ISSUE, {"version": 1, "issue": ISSUE, "authors": [{}]})

    refusal = _rung(roots).refusal

    assert refusal.kind == "authorship_unreadable"
    assert f"record={review_loop.authorship_path(roots[1], ISSUE)}" in refusal.found


# --------------------------------------- the three ways a record stops answering (round 2)
#
# Round 1's subject was "an author the record loses is a reviewer the check stops refusing",
# and it closed the case where the record is *corrupted* — a lost entry under a concurrent
# write, and a document that will not parse. Constructed against the real rung, the third way
# was still open: a record **removed** beside dispatch records that name somebody else clears
# the landing with the declared author simply absent from the set, which is the same silent
# narrowing one door along. These three arrangements are one table on purpose, so a later
# reader meets what each returns rather than the one that happened to be found last.


def _declared_then_removed(tmp_path: Path, **staging: str) -> tuple[Path, Path]:
    """Declare an interactive author, then remove the record the declaration wrote."""
    roots = _stage(tmp_path, **staging)
    _author(roots[1])
    review_loop.authorship_path(roots[1], ISSUE).unlink()
    return roots


def test_a_record_truncated_mid_write_refuses_the_landing_by_name(tmp_path: Path) -> None:
    """Arrangement one: bytes that are not JSON.

    The entry that will not open could be this reviewer's own, so nothing is taken from the
    record and nothing clears.
    """
    roots = _stage(tmp_path)
    _author(roots[1])
    record = review_loop.authorship_path(roots[1], ISSUE)
    record.write_text(record.read_text(encoding="utf-8")[:40], encoding="utf-8")

    refusal = _rung(roots).refusal

    assert refusal.kind == "authorship_unreadable"
    assert any("will not read" in line for line in refusal.found)


def test_a_record_of_the_wrong_shape_refuses_the_landing_and_names_the_fault(
    tmp_path: Path,
) -> None:
    """Arrangement two: valid JSON this tool did not write.

    Validated rather than coerced, so the refusal says which part of the document failed
    rather than only that one did.
    """
    roots = _stage(tmp_path)
    _record(roots[1], ISSUE, {"version": 1, "issue": ISSUE, "authors": [{"recorded_at": STAMP}]})

    refusal = _rung(roots).refusal

    assert refusal.kind == "authorship_unreadable"
    assert any("an entry names profile=None" in line for line in refusal.found)


def test_a_removed_record_over_work_no_dispatch_claims_still_refuses_unrecorded(
    tmp_path: Path,
) -> None:
    """Arrangement three, first half: nothing else places a profile on the work.

    The empty-set refusal fires and already names this loss's repair. Kept as its own case
    because the loss must not *change* the answer where the answer was already right.
    """
    refusal = _rung(_declared_then_removed(tmp_path)).refusal

    assert refusal.kind == "authorship_unrecorded"
    assert "just review-loop author" in refusal.action


def test_a_removed_record_beside_a_dispatch_record_refuses_rather_than_narrowing(
    tmp_path: Path,
) -> None:
    """Arrangement three, second half — the hole round 1 left open.

    A dispatch record names `glm-max`, so the set is not empty and `authorship_unrecorded`
    cannot fire. Before this refusal the rung cleared with `potential=glm-max` and the
    declared author nowhere in it: a reviewer running on the declared profile would have
    been cleared by a check that never saw the author it was supposed to exclude.
    """
    roots = _declared_then_removed(tmp_path, authoring="glm-max")

    refusal = _rung(roots).refusal

    assert refusal.kind == "authorship_lost"
    assert f"record={review_loop.authorship_path(roots[1], ISSUE)}" in refusal.found
    assert "potential=glm-max" in refusal.found
    assert "just review-loop author" in refusal.action


def test_a_landing_that_never_had_a_declaration_is_not_read_as_a_lost_one(
    tmp_path: Path,
) -> None:
    """The control the refusal above is worthless without: an absent record is still an answer.

    Most issues are authored through a dispatch and never declare, and a guard that refused
    those would refuse nearly every landing in the repository.
    """
    outcome = _rung(_stage(tmp_path, authoring="glm-max"))

    assert outcome.refusal is None
    assert "authorship=checked potential=glm-max" in outcome.cleared


def test_the_arbiter_walk_refuses_where_a_declaration_has_been_lost(tmp_path: Path) -> None:
    """The same absence, at the other reader that takes it for an answer.

    `escalate` excludes the profiles the records place on the work, a declared author among
    them. A lost record leaves the author of an interactively written change eligible to
    arbitrate its own findings, so the walk refuses to run rather than resolving against a
    set it cannot trust — exit 3, an act that could not be performed, not a verdict.
    """
    root = tmp_path / "review"
    review_loop.store_authorship(root, ISSUE, AUTHOR, SHA, STAMP)
    review_loop.authorship_path(root, ISSUE).unlink()

    assert review_loop.declaration_lost(root, ISSUE)
    assert _escalate_run(tmp_path, ISSUE) == review_loop.NO_RESULT
    assert not (root / str(ISSUE) / review_loop.ESCALATION_FILE).exists()


# ------------------------------- the declaration and the refusal, in one composition (#398)
#
# Round 2's finding 8: the property below was named by a test that never exercised it.
# `test_the_declared_author_reviewing_its_own_diff_is_still_refused` declares through
# `store_authorship` and asserts the refusal, and the two halves were never joined — so the
# one composition that decides whether the mechanism works, `--profile P` on the command line
# and then the landing rung, was untested. These two drive the real CLI in its own process,
# which is also the only arrangement in which the command's interactive-session refusal is
# genuinely absent rather than monkeypatched away.


def _declare_through_the_command_line(review_root: Path, profile: str) -> str:
    """Declare through `review_loop.py author` as a subprocess, as a human would."""
    environment = {k: v for k, v in os.environ.items() if k != "CTI_DISPATCH_ID"}
    sha = review_loop.git("rev-parse", "HEAD", cwd=REPO).strip()
    done = subprocess.run(  # noqa: S603 — a fixed argv, this repository's own CLI
        [
            sys.executable,
            str(REPO / "tools" / "review_loop.py"),
            "author",
            "--issue",
            str(ISSUE),
            "--root",
            str(review_root),
            "--profile",
            profile,
            "--sha",
            sha,
        ],
        capture_output=True,
        text=True,
        env=environment,
        cwd=REPO,
        check=False,
        timeout=60,
    )
    assert done.returncode == review_loop.OK, done.stderr
    assert f"profile={profile} source={review_loop.DECLARED}" in done.stdout
    return done.stdout


def test_a_command_line_declaration_refuses_the_reviewer_it_names(tmp_path: Path) -> None:
    """The composition, refusing: one instance authors and reviews on one profile.

    Declared through the CLI, checked at the landing rung, and the two joined in one test
    — the arrangement ruling 4 exists to catch, meeting `review_same_profile` by the only
    route an interactively authored change has.
    """
    roots = _stage(tmp_path, reviewer=AUTHOR)
    _declare_through_the_command_line(roots[1], AUTHOR)

    refusal = _rung(roots).refusal

    assert refusal.kind == "review_same_profile"
    assert f"reviewer_profile={AUTHOR}" in refusal.found
    assert f"authored_by={review_loop.authorship_path(roots[1], ISSUE)}" in refusal.found


def test_a_command_line_declaration_clears_a_reviewer_it_does_not_name(tmp_path: Path) -> None:
    """The composition, clearing — and the half that makes the other half mean anything.

    Same declaration, same rung, one profile different, and the landing clears. A guard
    that refused both would refuse everything, which is not a guard; what this asserts is
    that the refusal above **discriminates** on the profile it was given. The clearance
    carries `declared=` and the limit beside it, because nothing derived that name.
    """
    roots = _stage(tmp_path, reviewer=REVIEWER)
    _declare_through_the_command_line(roots[1], AUTHOR)

    outcome = _rung(roots)

    assert outcome.refusal is None
    assert f"authorship=checked potential={AUTHOR} declared={AUTHOR}" in outcome.cleared
    assert land_review.DECLARED_AUTHOR_LIMIT in outcome.cleared
