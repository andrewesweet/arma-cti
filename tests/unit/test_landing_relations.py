"""Qualified object relations on the landing, so never-alone is record-checkable (#491).

The spec's own highest-value case is the one this module pins: a landing touching
an author dispatch and a reviewing dispatch, the two distinguishable by qualifier
alone. Everything else hangs off that — the closed vocabularies one home in
`attribute_registry`, the counting grain split across two tables, the historical
line that parses without any of this, and the fail-open emission that never fails
a landing.

Each test's arrangement exists to falsify one claim:

- **The vocabularies are closed and stated once.** A qualifier or type outside
  the set refuses at construction, and the store's reader derives both sets from
  the registry rather than holding a second spelling.
- **Both author sources are expressible.** A dispatched author relates as a
  `dispatch`, a declared one (#398) as an `authorship_declaration`, and the #548
  shape — a declared author alongside a dispatched implementer — carries both
  objects on one landing. A relation set that only named dispatches would exempt
  exactly the changes the declaration exists to cover.
- **The check reads the record, not the printed line.** The cookbook's
  never-alone query, run against a rebuilt store, finds a landing whose reviewer
  profile an author relation also names — hand-staged, because the rung itself
  refuses that arrangement; the check exists for the record the rung missed.
- **One event over several objects multiplies nothing.** `landings` counts
  landings, `landing_relations` counts objects, and a duplicate event shows as
  the two event counts disagreeing rather than as a second landing.
- **Absence is an answer.** A line with no relation attributes parses with an
  empty set and is named uncheckable, never read as clear; damage is malformed.
- **Emission never fails the landing.** A refused export still journals, with
  `exported: false` and a detail, and the recorder's answer is unchanged.
"""

from __future__ import annotations

import json
import re
import subprocess
from typing import TYPE_CHECKING, Any, Final

import pytest
from conftest import REPO, load_tool

if TYPE_CHECKING:
    from pathlib import Path

attribute_registry = load_tool("attribute_registry")
land_review = load_tool("land_review")
observatory = load_tool("observatory")
review_loop = load_tool("review_loop")

ISSUE: Final = 491
OTHER_ISSUE: Final = 492
REVIEWER: Final = "codex-luna-max"
AUTHOR: Final = "zai-glm53-max"
DECLARED: Final = "opus-xhigh"
SHA: Final = "a" * 40
OTHER_SHA: Final = "b" * 40
STAMP: Final = "20260824T0000Z"
REVIEW_DISPATCH: Final = "d-20260824-000001-review"
AUTHOR_DISPATCH: Final = "d-20260824-000002-author"

RESULT: Final = json.dumps({"returncode": 0, "outcome": "ok", "ended_at": STAMP})


def cookbook_blocks() -> list[str]:
    """Every SQL block the shipped cookbook carries, in document order."""
    cookbook = (REPO / "docs" / "observatory" / "cookbook.md").read_text(encoding="utf-8")
    return re.findall(r"```sql\n(.*?)```", cookbook, flags=re.DOTALL)


# --------------------------------------------------------------------- staging


def _dispatch_record(  # noqa: PLR0913 — one parameter per field of the record under test
    root: Path,
    dispatch_id: str,
    *,
    seat: str,
    profile: str,
    lane: str,
    issue: int = ISSUE,
    base_sha: str = "0" * 40,
) -> None:
    """Lay down one dispatch record the way `just dispatch` leaves one.

    `base_sha` defaults to the never-bindable placeholder: a review dispatch binds
    the commit its `base_sha` names, so the reviewer staging passes the SHA under
    test and everything else lands nowhere.
    """
    record = root / dispatch_id
    record.mkdir(parents=True, exist_ok=True)
    (record / "dispatch.json").write_text(
        json.dumps(
            {
                "seat": seat,
                "issue": issue,
                "base_sha": base_sha,
                "profile": profile,
                "lane": lane,
                "planned_at": STAMP,
                "dispatch_id": dispatch_id,
            }
        ),
        encoding="utf-8",
    )
    (record / "result.json").write_text(RESULT, encoding="utf-8")


def _verdict(
    *,
    issue: int = ISSUE,
    sha: str = SHA,
    dispatch: str = REVIEW_DISPATCH,
    profile: str = REVIEWER,
) -> str:
    """One verdict record, written the shape `review_exchange.record_verdict` writes it."""
    return json.dumps(
        {
            "version": 1,
            "issue": issue,
            "reviewed_sha": sha,
            "diff_id": "c" * 64,
            "review_dispatch": dispatch,
            "reviewer_profile": profile,
            "reviewer_lane": "codex",
            "findings": [],
            "recorded_at": STAMP,
            "alternates": [],
        }
    )


def _stage_rung(
    tmp_path: Path,
    *,
    author: str | None = AUTHOR,
    declared: tuple[str, ...] = (),
) -> tuple[Path, Path]:
    """Stage the roots a clearing rung reads: a bound clean review over authored work.

    `author=None` with `declared` is #524's shape — no implementer dispatch at all,
    an interactive author the declaration alone places — and both together are
    #548's, a declared orchestrator amend beside a dispatched implementer.
    """
    dispatch_root = tmp_path / "dispatches"
    review_root = tmp_path / "review"
    dispatch_root.mkdir(parents=True, exist_ok=True)
    review_root.mkdir(parents=True, exist_ok=True)
    if author is not None:
        _dispatch_record(
            dispatch_root,
            AUTHOR_DISPATCH,
            seat="implementer",
            profile=author,
            lane="zai",
        )
    _dispatch_record(
        dispatch_root,
        REVIEW_DISPATCH,
        seat="review",
        profile=REVIEWER,
        lane="codex",
        base_sha=SHA,
    )
    (dispatch_root / REVIEW_DISPATCH / "verdict.json").write_text(_verdict(), encoding="utf-8")
    if declared:
        target = review_loop.authorship_path(review_root, ISSUE)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {
                    "version": 1,
                    "issue": ISSUE,
                    "authors": [{"profile": profile} for profile in declared],
                }
            ),
            encoding="utf-8",
        )
    return dispatch_root, review_root


def _landing_event_document(  # noqa: PLR0913 — one keyword per field of the line under test
    *,
    issue: int = ISSUE,
    commit: str = SHA,
    authors: tuple[tuple[str, str], ...] = (("dispatch", AUTHOR_DISPATCH),),
    reviewer: str = REVIEW_DISPATCH,
    gate_cause: str | None = None,
    at: float = 1_800_000_000.0,
) -> str:
    """One landings-journal line, in the shape `otel_event.journal_line` renders it."""
    relations = [
        attribute_registry.relation("subject", "issue", str(issue)),
        attribute_registry.relation("produced", "commit", commit),
        attribute_registry.relation("reviewer", "dispatch", reviewer),
        *(attribute_registry.relation("author", kind, named) for kind, named in authors),
    ]
    event = attribute_registry.landing_event(relations, at, gate_cause=gate_cause or "")
    return (
        json.dumps(
            {
                "event": event.name,
                "at": event.at,
                "attributes": dict(event.attributes),
                "resource": dict(event.resource),
                "exported": False,
                "export_detail": "unreachable:ConnectionRefusedError",
            },
            sort_keys=True,
        )
        + "\n"
    )


def _git_repo(path: Path) -> Path:
    """Build a real repository with one commit, because `ledger.landed` reads git."""
    path.mkdir(parents=True, exist_ok=True)
    for argv in (
        ("git", "init", "-q"),
        ("git", "config", "user.email", "test@example.com"),
        ("git", "config", "user.name", "test"),
    ):
        subprocess.run(argv, cwd=path, check=True)  # noqa: S603 — fixed argv, PATH git as everywhere in tools/
    (path / "README").write_text("repo\n", encoding="utf-8")
    subprocess.run(("git", "add", "README"), cwd=path, check=True)  # noqa: S607
    subprocess.run(("git", "commit", "-qm", "init"), cwd=path, check=True)  # noqa: S607
    return path


def _world(tmp_path: Path) -> dict[str, Path]:
    """Every directory the rebuild reads, present and empty where unused."""
    world = {
        "dispatch_root": tmp_path / "dispatches",
        "export_dir": tmp_path / "exports",
        "review_root": tmp_path / "review",
        "spool": tmp_path / "spool" / "statusline.jsonl",
        "repo": tmp_path / "repo",
        "store_dir": tmp_path / "store",
    }
    for key in ("dispatch_root", "export_dir", "review_root"):
        world[key].mkdir(parents=True, exist_ok=True)
    world["spool"].parent.mkdir(parents=True, exist_ok=True)
    world["spool"].write_text("", encoding="utf-8")
    _git_repo(world["repo"])
    return world


def _rebuild(world: dict[str, Path]) -> dict[str, Any]:
    return observatory.rebuild(
        world["dispatch_root"],
        world["export_dir"],
        world["review_root"],
        world["spool"],
        world["repo"],
        world["store_dir"],
    )


# ------------------------------------------------------------- the closed sets


def test_the_vocabularies_are_closed_at_construction() -> None:
    """A qualifier, type or id outside the set is a programming error, by raise."""
    attribute_registry.relation("author", "dispatch", "d-1")
    with pytest.raises(ValueError, match="qualifier not in the closed set"):
        attribute_registry.relation("authored", "dispatch", "d-1")
    with pytest.raises(ValueError, match="object type not in the closed set"):
        attribute_registry.relation("author", "profile", "d-1")
    for named in ("has space", "has:colon", ""):
        with pytest.raises(ValueError, match="no whitespace or colon"):
            attribute_registry.relation("author", "dispatch", named)
    with pytest.raises(ValueError, match="gate cause not in the closed vocabulary"):
        attribute_registry.landing_event((), 1.0, gate_cause="crossed_lanes")


def test_relations_round_trip_through_the_flat_attribute_encoding() -> None:
    """Several authors share one attribute value and survive the read back."""
    relations = (
        attribute_registry.relation("subject", "issue", str(ISSUE)),
        attribute_registry.relation("produced", "commit", SHA),
        attribute_registry.relation("reviewer", "dispatch", REVIEW_DISPATCH),
        attribute_registry.relation("author", "dispatch", AUTHOR_DISPATCH),
        attribute_registry.relation("author", "authorship_declaration", DECLARED),
    )
    event = attribute_registry.landing_event(relations, 1.0, gate_cause="cross_lane")
    attributes = dict(event.attributes)
    assert attributes["cti.issue"] == ISSUE
    assert attributes["cti.relation.author"] == (
        f"dispatch:{AUTHOR_DISPATCH} authorship_declaration:{DECLARED}"
    )
    assert attributes["cti.relation.reviewer"] == f"dispatch:{REVIEW_DISPATCH}"
    assert attributes["cti.landing.gate_cause"] == "cross_lane"
    # The read back is the same set. The flat encoding groups by qualifier and so
    # carries no cross-qualifier order — order within one qualifier is preserved,
    # which the attribute string above already pins — so the round trip is a set
    # claim, never a tuple-order one.
    read = attribute_registry.relations_from_attributes(attributes)
    assert len(read) == len(relations)
    assert set(read) == set(relations)


# ------------------------------------------------------- both author sources


def test_the_rung_relates_a_dispatched_author_and_the_reviewer_by_qualifier_alone(
    tmp_path: Path,
) -> None:
    """#491's third criterion: author and reviewer are both dispatches, told apart by role."""
    dispatch_root, review_root = _stage_rung(tmp_path)
    outcome = land_review.review_finding(
        ISSUE, SHA, ("tools/worker.py",), (), None, dispatch_root, review_root
    )
    assert outcome.refusal is None
    relations = outcome.relations
    authors = [named for named in relations if named.qualifier == "author"]
    reviewers = [named for named in relations if named.qualifier == "reviewer"]
    assert authors == [attribute_registry.Relation("author", "dispatch", AUTHOR_DISPATCH)]
    assert reviewers == [attribute_registry.Relation("reviewer", "dispatch", REVIEW_DISPATCH)]
    # Distinguishable by qualifier alone: same object type, different role.
    assert authors[0].object_type == reviewers[0].object_type == "dispatch"
    assert outcome.gate_cause == "", "a non-gate landing carries no cause"


def test_a_declared_author_relates_as_a_declaration_not_a_dispatch(tmp_path: Path) -> None:
    """#524's shape: no implementer dispatch at all, an interactive author declared."""
    dispatch_root, review_root = _stage_rung(tmp_path, author=None, declared=(DECLARED,))
    outcome = land_review.review_finding(
        ISSUE, SHA, ("tools/worker.py",), (), None, dispatch_root, review_root
    )
    assert outcome.refusal is None
    authors = [named for named in outcome.relations if named.qualifier == "author"]
    assert authors == [attribute_registry.Relation("author", "authorship_declaration", DECLARED)], (
        "the declaration is the author object, and its id is the profile"
    )


def test_a_declared_author_beside_a_dispatched_one_carries_both_objects(tmp_path: Path) -> None:
    """#548's shape: an orchestrator amend declared beside a dispatched implementer."""
    dispatch_root, review_root = _stage_rung(tmp_path, declared=(DECLARED,))
    outcome = land_review.review_finding(
        ISSUE, SHA, ("tools/worker.py",), (), None, dispatch_root, review_root
    )
    assert outcome.refusal is None
    authors = [named for named in outcome.relations if named.qualifier == "author"]
    assert authors == [
        attribute_registry.Relation("author", "dispatch", AUTHOR_DISPATCH),
        attribute_registry.Relation("author", "authorship_declaration", DECLARED),
    ]


def test_a_profile_that_both_dispatched_and_declared_keeps_its_dispatch_relation(
    tmp_path: Path,
) -> None:
    """The record is the stronger evidence: the same profile, dispatched, stays a dispatch.

    `with_declared_authors` never re-adds a name a dispatch record placed, so the
    declaration of a profile that also dispatched changes nothing in the author
    set — and the relation must not relabel that author a declaration, because its
    dispatch id is the object a reader of the record joins `dispatches` on.
    """
    dispatch_root, review_root = _stage_rung(tmp_path, author=DECLARED, declared=(DECLARED,))
    outcome = land_review.review_finding(
        ISSUE, SHA, ("tools/worker.py",), (), None, dispatch_root, review_root
    )
    assert outcome.refusal is None
    authors = [named for named in outcome.relations if named.qualifier == "author"]
    assert authors == [
        attribute_registry.Relation("author", "dispatch", AUTHOR_DISPATCH),
    ], "the dispatched record placed the profile, and the relation names that record"


# ------------------------------------------------------------------- recording


def test_record_landing_deduplicates_on_the_produced_commit(tmp_path: Path) -> None:
    """The landing's identity is the commit: a re-record of one is already recorded."""
    relations = (
        attribute_registry.relation("subject", "issue", str(ISSUE)),
        attribute_registry.relation("produced", "commit", SHA),
        attribute_registry.relation("reviewer", "dispatch", REVIEW_DISPATCH),
        attribute_registry.relation("author", "dispatch", AUTHOR_DISPATCH),
    )
    root = tmp_path / "review"
    assert attribute_registry.record_landing(relations, root, 1.0) == (
        attribute_registry.LANDING_RECORDED
    )
    assert attribute_registry.record_landing(relations, root, 2.0) == (
        attribute_registry.LANDING_ALREADY_RECORDED
    )
    # A different commit is a different landing and records.
    moved = (*relations[:1], attribute_registry.relation("produced", "commit", OTHER_SHA))
    assert attribute_registry.record_landing(moved, root, 3.0) == (
        attribute_registry.LANDING_RECORDED
    )
    lines = attribute_registry
    journal = root / str(ISSUE) / attribute_registry.LANDING_JOURNAL
    assert len(journal.read_text(encoding="utf-8").splitlines()) == 2
    assert lines.LANDING_JOURNAL == "landings.jsonl"


def test_a_relation_set_that_names_no_commit_records_nothing(tmp_path: Path) -> None:
    """A landing that cannot say what it landed has no record to write."""
    relations = (attribute_registry.relation("subject", "issue", str(ISSUE)),)
    assert attribute_registry.record_landing(relations, tmp_path / "review", 1.0) == (
        attribute_registry.LANDING_UNRECORDABLE
    )
    assert not (tmp_path / "review").exists()


def test_emission_stays_fail_open_and_journals_the_refused_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A collector that refuses the post is a journalled fact, never a failed landing."""
    calls: list[object] = []

    def refused(document: object, _endpoint: str = "", _timeout: float = 2.0) -> tuple[bool, str]:
        calls.append(document)
        return False, "http_503"

    monkeypatch.setattr(attribute_registry.otel_event, "post", refused)
    relations = (
        attribute_registry.relation("subject", "issue", str(ISSUE)),
        attribute_registry.relation("produced", "commit", SHA),
    )
    root = tmp_path / "review"
    assert attribute_registry.record_landing(relations, root, 1.0) == (
        attribute_registry.LANDING_RECORDED
    )
    assert calls, "the export was attempted"
    line = json.loads(
        (root / str(ISSUE) / attribute_registry.LANDING_JOURNAL)
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )
    assert line["exported"] is False
    assert line["export_detail"] == "http_503"
    assert line["attributes"]["cti.relation.produced"] == f"commit:{SHA}"


# ------------------------------------------------------------- the store reads


def _stage_store(tmp_path: Path) -> dict[str, Path]:
    """Stage a world with two landings journalled and the dispatches they relate."""
    world = _world(tmp_path)
    _dispatch_record(
        world["dispatch_root"], AUTHOR_DISPATCH, seat="implementer", profile=AUTHOR, lane="zai"
    )
    # The forged reviewer: a dispatch record whose profile is the author's, which
    # the rung would refuse — the record the never-alone query exists to catch.
    _dispatch_record(
        world["dispatch_root"],
        REVIEW_DISPATCH,
        seat="review",
        profile=AUTHOR,
        lane="zai",
    )
    clean = world["dispatch_root"] / "d-clean-review"
    clean.mkdir(parents=True, exist_ok=True)
    (clean / "dispatch.json").write_text(
        json.dumps(
            {
                "seat": "review",
                "issue": OTHER_ISSUE,
                "base_sha": "0" * 40,
                "profile": REVIEWER,
                "lane": "codex",
                "planned_at": STAMP,
                "dispatch_id": "d-clean-review",
            }
        ),
        encoding="utf-8",
    )
    one = attribute_registry.landing_journal(ISSUE, world["review_root"])
    one.parent.mkdir(parents=True, exist_ok=True)
    one.write_text(
        _landing_event_document(gate_cause="cross_lane")
        + _landing_event_document(gate_cause="cross_lane", at=1_800_000_100.0),
        encoding="utf-8",
    )
    two = attribute_registry.landing_journal(OTHER_ISSUE, world["review_root"])
    two.parent.mkdir(parents=True, exist_ok=True)
    two.write_text(
        _landing_event_document(
            issue=OTHER_ISSUE,
            commit=OTHER_SHA,
            authors=(("dispatch", AUTHOR_DISPATCH),),
            reviewer="d-clean-review",
        ),
        encoding="utf-8",
    )
    return world


def test_the_never_alone_rule_is_a_query_not_a_printed_line(tmp_path: Path) -> None:
    """The cookbook's check finds the forged reviewer and clears the honest one."""
    world = _stage_store(tmp_path)
    _rebuild(world)
    block = next(found for found in cookbook_blocks() if "reviewer_profile" in found)
    rows = observatory.query(world["store_dir"], block.strip().rstrip(";"))
    assert rows == ((f"{ISSUE}/{SHA}", AUTHOR),), "the author-profile reviewer is caught"
    # The clean landing is absent from the violations, and its own profile is the
    # reviewer's, resolved through the join rather than restated.
    per_landing = next(found for found in cookbook_blocks() if "objects_touched" in found)
    touched = observatory.query(world["store_dir"], per_landing.strip().rstrip(";"))
    assert dict(touched)[f"{ISSUE}/{SHA}"] == 4
    assert dict(touched)[f"{OTHER_ISSUE}/{OTHER_SHA}"] == 4


def test_one_event_over_several_objects_multiplies_nothing(tmp_path: Path) -> None:
    """Landings count landings; relation rows count objects; duplicates disagree loudly."""
    world = _stage_store(tmp_path)
    store = _rebuild(world)
    assert store["coverage"]["landing_events"] == 3, "two events for one commit, one for the other"
    assert store["coverage"]["landings"] == 2, "the duplicate is one landing, not two"
    assert store["coverage"]["landing_relations"] == 8, "four objects per winning event"
    landings = {row["landing"]: row for row in store["landings"]}
    assert landings[f"{ISSUE}/{SHA}"]["relations"] == 4
    assert landings[f"{ISSUE}/{SHA}"]["gate_cause"] == "cross_lane"
    assert landings[f"{OTHER_ISSUE}/{OTHER_SHA}"]["gate_cause"] is None
    assert landings[f"{OTHER_ISSUE}/{OTHER_SHA}"]["gate_cause_reason"] == (
        observatory.NO_GATE_CAUSE_REASON
    )
    # The newest event won the duplicate pair.
    assert landings[f"{ISSUE}/{SHA}"]["at"] == 1_800_000_100.0
    causes = next(found for found in cookbook_blocks() if "gate_cause, COUNT" in found)
    assert observatory.query(world["store_dir"], causes.strip().rstrip(";")) == (("cross_lane", 1),)


def test_a_line_without_relations_parses_and_is_named_uncheckable(tmp_path: Path) -> None:
    """The historical shape: absence is an answer, and never a silent clearance."""
    world = _world(tmp_path)
    journal = attribute_registry.landing_journal(ISSUE, world["review_root"])
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text(
        json.dumps(
            {
                "event": attribute_registry.LANDING_EVENT,
                "at": 1.0,
                "attributes": {"cti.issue": ISSUE},
                "resource": {"service.name": "arma-cti-landing"},
                "exported": True,
                "export_detail": "http_200",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    store = _rebuild(world)
    assert store["coverage"]["landings"] == 1
    assert store["coverage"]["landing_relations"] == 0
    assert store["coverage"]["landings_without_authors"] == [f"{ISSUE}/"]
    row = store["landings"][0]
    assert row["produced_commit"] is None
    assert row["produced_commit_reason"] == observatory.NO_COMMIT_RELATION_REASON
    assert row["boundary"] == observatory.LANDING_BOUNDARY


def test_damage_is_malformed_and_survived(tmp_path: Path) -> None:
    """A token outside the closed type set is counted, never read as the set."""
    world = _world(tmp_path)
    journal = attribute_registry.landing_journal(ISSUE, world["review_root"])
    journal.parent.mkdir(parents=True, exist_ok=True)
    healthy = json.loads(_landing_event_document())
    forged = dict(healthy)
    forged["attributes"] = {
        "cti.issue": ISSUE,
        "cti.relation.author": f"human:{AUTHOR_DISPATCH}",
    }
    journal.write_text(
        json.dumps(forged, sort_keys=True) + "\n" + _landing_event_document(),
        encoding="utf-8",
    )
    store = _rebuild(world)
    assert {"file": f"{ISSUE}/landings.jsonl", "lines": 1} in store["malformed"]
    assert store["coverage"]["landings"] == 1, "the healthy line loaded"
    assert store["coverage"]["landing_relations"] == 4
