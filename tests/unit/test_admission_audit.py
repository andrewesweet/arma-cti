"""`just admission audit`: the close audit the bar today asks an agent to assert (#252).

`just admission record` demands a choice on every Part A criterion and cross-checks two of
them against git in the refusing direction only. Everything else is asserted by whoever
runs it. Most of that is computable, and this is the computation — so what these tests
have to hold is not only that the sums are right but that the two refusals to overclaim
survive:

- a quoted gate block is `quoted` and never green. A test here asserts that no audit,
  whatever it found, ever fills `fast_green`;
- the changelog check is `undecidable` and no input makes it `ok`. Its function takes no
  argument at all, and the sweep below holds that over whole audits rather than only over
  the check, because a mutant that reached into `criteria_from_audit` would not be caught
  by testing the check alone.

And one structural claim, which is the issue's sixth criterion: the window tests — a
commit descends from the dispatch's base and postdates its start — are `tools/ledger.py`'s
from 7bc3f72 and are *called*. Two guards, one behavioural (the audit is spied on making
the call) and one textual (the strings a second copy would have to contain are in
`ledger.py` and not in `admission.py`), because either alone can be satisfied by a copy
that also delegates.

Every repo here is a `tmp_path` of the test's own with its own `refs/remotes/origin/main`,
so nothing reads this checkout's history, and every dispatch record is written into a
`tmp_path` root rather than into `~/.arma-cti/dispatches`. No test reaches GitHub: the
close is always read through `--close-file`, which is the seam that exists for it.
"""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING, Any

import pytest
from conftest import load_tool

if TYPE_CHECKING:
    from pathlib import Path
    from types import ModuleType

admission: ModuleType = load_tool("admission")
ledger: ModuleType = load_tool("ledger")

# The real numbers from the row 7bc3f72 was written for: a review dispatch armed at
# 22:17:43Z credited with `e066b3c`, committed 21:01:17Z, seventy-six minutes earlier.
DISPATCH_ARMED = "2026-08-05T22:17:43.676672+00:00"
COMMIT_BEFORE_IT = "2026-08-05T21:01:17+00:00"
COMMIT_AFTER_IT = "2026-08-05T22:32:26+00:00"

LANE = "zai"
PROFILE = "zai-glm52-max"

# A port nothing listens on, so a record's export fails the way a stopped collector fails.
DEAD_ENDPOINT = "http://127.0.0.1:2997/v1/logs"


def run_git(repo: Path, *argv: str, when: str = "") -> str:
    """Run one git command in a scratch repo, optionally at a fixed commit date."""
    env = None
    if when:
        env = {"GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when, "PATH": "/usr/bin:/bin"}
    # S603/S607: fixed literals and this test's own strings, and `git` resolves off PATH
    # on purpose — the same reasoning `tools/admission.py` records for its own helper.
    return subprocess.run(  # noqa: S603
        ["git", *argv],  # noqa: S607
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env=env,
    ).stdout.strip()


def commit(repo: Path, paths: dict[str, str], message: str, when: str = "") -> str:
    """Write files into a scratch repo, commit them at `when`, and return the SHA."""
    if not (repo / ".git").is_dir():
        repo.mkdir(parents=True, exist_ok=True)
        run_git(repo, "init", "-q")
        run_git(repo, "config", "user.email", "t@example.invalid")
        run_git(repo, "config", "user.name", "t")
    for name, body in paths.items():
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-q", "-m", message, when=when)
    sha = run_git(repo, "rev-parse", "HEAD")
    # The audit's default ref, made real here rather than worked around with `--ref`, so
    # the tests exercise the branch name a landing is actually held against.
    run_git(repo, "update-ref", "refs/remotes/origin/main", sha)
    return sha


def dispatch_record(  # noqa: PLR0913 — one parameter per field of the record under test
    root: Path,
    dispatch_id: str,
    *,
    issue: int,
    base_sha: str,
    seat: str = "implementer",
    planned_at: str = DISPATCH_ARMED,
    started_at: str | None = DISPATCH_ARMED,
) -> Path:
    """Write one dispatch record in the shape `tools/dispatch.py` writes it."""
    directory = root / dispatch_id
    directory.mkdir(parents=True, exist_ok=True)
    plan: dict[str, Any] = {
        "dispatch_id": dispatch_id,
        "lane": LANE,
        "profile": PROFILE,
        "seat": seat,
        "issue": issue,
        "base_sha": base_sha,
    }
    if planned_at:
        plan["planned_at"] = planned_at
    (directory / "dispatch.json").write_text(json.dumps(plan), encoding="utf-8")
    result: dict[str, Any] = {"dispatch_id": dispatch_id, "returncode": 0, "outcome": "ok"}
    if started_at:
        result["started_at"] = started_at
    (directory / "result.json").write_text(json.dumps(result), encoding="utf-8")
    return directory


def audit_of(
    repo: Path,
    close: str,
    *,
    issue: int = 92,
    dispatch_root: Path | None = None,
) -> Any:  # noqa: ANN401 — a tools/ module loads dynamically, so its types are Unknown here
    """Audit one close, against a dispatch root that is empty unless the test wrote one."""
    root = dispatch_root if dispatch_root is not None else repo / "no-dispatches"
    return admission.audit(repo, issue, close, dispatch_root=root, source="file=test")


def landed_setup(tmp_path: Path, *, issue: int = 92, when: str = COMMIT_AFTER_IT) -> Any:  # noqa: ANN401 — same
    """Build a base, a landing that references the issue, and a dispatch armed before it."""
    repo = tmp_path / "repo"
    base = commit(repo, {"docs/note.md": "before\n"}, "docs: the base", when=COMMIT_BEFORE_IT)
    landing = commit(repo, {"docs/note.md": "after\n"}, f"docs: a landing\n\nrefs #{issue}", when)
    root = tmp_path / "dispatches"
    dispatch_record(root, "d-20260805-221743-8957c3", issue=issue, base_sha=base)
    return repo, base, landing, root


# ----------------------------------------------------------------- the SHA on the branch


def test_a_close_naming_its_dispatch_s_landing_audits_ok(tmp_path: Path) -> None:
    repo, _, landing, root = landed_setup(tmp_path)
    result = audit_of(repo, f"Landed at {landing[:7]}.", dispatch_root=root)
    assert result.verdict_of("sha_on_main") == admission.AUDIT_OK
    assert result.verdict_of("dispatch_window") == admission.AUDIT_OK
    assert result.sha == landing
    assert result.dispatch_id == "d-20260805-221743-8957c3"
    assert ("close_names_sha", admission.MET) in admission.criteria_from_audit(result)


def test_a_close_naming_no_commit_this_checkout_knows_audits_absent(tmp_path: Path) -> None:
    repo, _, _, root = landed_setup(tmp_path)
    # An md5 is thirty-two hex characters and matches the token shape exactly. #92's own
    # close quotes one, so this is the live case rather than a contrived one.
    close = "byte-identical (md5 05dc2cff28a6b69aaf9ec54e49215942 both sides)"
    result = audit_of(repo, close, dispatch_root=root)
    assert result.verdict_of("sha_on_main") == admission.AUDIT_ABSENT
    assert result.sha == ""
    assert ("close_names_sha", admission.NOT_MET) in admission.criteria_from_audit(result)


def test_a_commit_that_is_not_on_the_branch_audits_not_on_main(tmp_path: Path) -> None:
    repo, _, _, root = landed_setup(tmp_path)
    run_git(repo, "checkout", "-q", "-b", "sidetrack")
    aside = commit(repo, {"docs/aside.md": "x\n"}, "docs: off to one side", when=COMMIT_AFTER_IT)
    # `commit` moved origin/main onto it, which is exactly what this test must undo.
    run_git(repo, "update-ref", "refs/remotes/origin/main", f"{aside}~1")
    result = audit_of(repo, f"Landed at {aside}.", dispatch_root=root)
    assert result.verdict_of("sha_on_main") == admission.AUDIT_NOT_ON_MAIN
    assert ("close_names_sha", admission.NOT_MET) in admission.criteria_from_audit(result)


def test_one_commit_spelt_twice_resolves_once(tmp_path: Path) -> None:
    repo, _, landing, _ = landed_setup(tmp_path)
    resolved = admission.resolved_commits(repo, f"{landing[:7]} and again in full {landing}")
    assert resolved == (landing,)


# ---------------------------------------------------------------------------- the window


def test_the_7bc3f72_case_replayed_audits_outside_window(tmp_path: Path) -> None:
    """A commit made before its dispatch was armed is not that dispatch's work.

    The row this replays credited `d-20260805-221743-8957c3`, armed at 22:17:43Z, with
    `e066b3c`, committed 21:01:17Z. Here the seat is `implementer` rather than the real
    case's `review`, because the seat rule answers first and would hide the date test;
    the test below holds the real case as it stands.
    """
    repo = tmp_path / "repo"
    base = commit(repo, {"docs/a.md": "a\n"}, "docs: the base", when="2026-08-05T20:00:00+00:00")
    early = commit(repo, {"docs/b.md": "b\n"}, "docs: refs #227", when=COMMIT_BEFORE_IT)
    root = tmp_path / "dispatches"
    dispatch_record(root, "d-20260805-221743-8957c3", issue=227, base_sha=base)
    result = admission.audit(repo, 227, f"Landed at {early}.", dispatch_root=root, source="t")
    assert result.verdict_of("sha_on_main") == admission.AUDIT_OK
    assert result.verdict_of("dispatch_window") == admission.AUDIT_OUTSIDE_WINDOW
    assert "predate this dispatch's start" in result.checks[1].detail
    assert ("close_names_sha", admission.NOT_MET) in admission.criteria_from_audit(result)


def test_the_real_case_s_review_seat_leaves_the_window_unbounded(tmp_path: Path) -> None:
    """The real `d-20260805-221743-8957c3` is a review seat, and review lands nothing.

    ADR-0061 Decision 3 admits `review` to a foreign lane because its output is claims, so
    bounding a landing by its window is a category error rather than a weak answer (#245).
    An issue whose only dispatch is a review seat therefore has no window at all.
    """
    repo = tmp_path / "repo"
    base = commit(repo, {"docs/a.md": "a\n"}, "docs: the base", when="2026-08-05T20:00:00+00:00")
    early = commit(repo, {"docs/b.md": "b\n"}, "docs: refs #227", when=COMMIT_BEFORE_IT)
    root = tmp_path / "dispatches"
    dispatch_record(root, "d-20260805-221743-8957c3", issue=227, base_sha=base, seat="review")
    result = admission.audit(repo, 227, f"Landed at {early}.", dispatch_root=root, source="t")
    assert result.verdict_of("dispatch_window") == admission.AUDIT_UNBOUNDED
    assert result.dispatch_id == ""
    assert not [state for key, state in admission.criteria_from_audit(result) if key == "x"]
    assert ("close_names_sha", admission.NOT_MET) not in admission.criteria_from_audit(result)
    assert ("close_names_sha", admission.MET) not in admission.criteria_from_audit(result)


def test_no_dispatch_record_at_all_leaves_the_window_unbounded(tmp_path: Path) -> None:
    repo, _, landing, _ = landed_setup(tmp_path)
    result = audit_of(repo, f"Landed at {landing}.")
    assert result.verdict_of("dispatch_window") == admission.AUDIT_UNBOUNDED
    assert "no dispatch record" in result.checks[1].detail


def test_a_dispatch_carrying_no_start_leaves_the_window_unbounded(tmp_path: Path) -> None:
    """A window the view cannot bound is not a window that admits everything (#245)."""
    repo, base, landing, _ = landed_setup(tmp_path)
    root = tmp_path / "startless"
    dispatch_record(root, "d-startless", issue=92, base_sha=base, planned_at="", started_at=None)
    result = audit_of(repo, f"Landed at {landing}.", dispatch_root=root)
    assert result.verdict_of("dispatch_window") == admission.AUDIT_UNBOUNDED
    assert "no start time" in result.checks[1].detail


def test_a_dispatch_carrying_no_base_leaves_the_window_unbounded(tmp_path: Path) -> None:
    repo, _, landing, _ = landed_setup(tmp_path)
    root = tmp_path / "baseless"
    dispatch_record(root, "d-baseless", issue=92, base_sha="")
    result = audit_of(repo, f"Landed at {landing}.", dispatch_root=root)
    assert result.verdict_of("dispatch_window") == admission.AUDIT_UNBOUNDED
    assert "no base SHA" in result.checks[1].detail


def test_a_close_with_no_sha_asks_no_window_question(tmp_path: Path) -> None:
    repo, _, _, root = landed_setup(tmp_path)
    result = audit_of(repo, "No SHA anywhere in this close.", dispatch_root=root)
    assert result.verdict_of("dispatch_window") == admission.AUDIT_UNDECIDABLE


def test_the_latest_landing_dispatch_is_the_one_the_window_comes_from(tmp_path: Path) -> None:
    """A re-dispatched issue is bounded by the run that could have made the landing.

    The ids carry their own UTC stamp, so the ordering is the ids' and not a second
    reading of the record's clock.
    """
    repo, base, landing, _ = landed_setup(tmp_path)
    root = tmp_path / "two"
    dispatch_record(root, "d-20260805-190000-aaaaaa", issue=92, base_sha=base)
    dispatch_record(root, "d-20260805-221743-8957c3", issue=92, base_sha=base)
    result = audit_of(repo, f"Landed at {landing}.", dispatch_root=root)
    assert result.dispatch_id == "d-20260805-221743-8957c3"


def test_another_issue_s_dispatch_is_not_this_issue_s_window(tmp_path: Path) -> None:
    repo, base, landing, _ = landed_setup(tmp_path)
    root = tmp_path / "elsewhere"
    dispatch_record(root, "d-elsewhere", issue=93, base_sha=base)
    result = audit_of(repo, f"Landed at {landing}.", dispatch_root=root)
    assert result.verdict_of("dispatch_window") == admission.AUDIT_UNBOUNDED


# ------------------------------------------------------------------------- the corpus row


def test_an_in_world_landing_owes_a_corpus_verdict(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    base = commit(repo, {"docs/a.md": "a\n"}, "docs: base", when=COMMIT_BEFORE_IT)
    landing = commit(repo, {"addons/main/fn_x.sqf": "// x\n"}, "feat: refs #92", COMMIT_AFTER_IT)
    root = tmp_path / "dispatches"
    dispatch_record(root, "d-in-world", issue=92, base_sha=base)
    result = audit_of(repo, f"Landed at {landing}.", dispatch_root=root)
    assert result.verdict_of("corpus_owed") == admission.AUDIT_OWED
    assert "addons/main/fn_x.sqf" in result.checks[2].detail


def test_a_landing_off_the_surface_list_owes_none(tmp_path: Path) -> None:
    repo, _, landing, root = landed_setup(tmp_path)
    result = audit_of(repo, f"Landed at {landing}.", dispatch_root=root)
    assert result.verdict_of("corpus_owed") == admission.AUDIT_NOT_OWED
    # And `not_owed` is never a waiver: that judgement stays the recorder's.
    assert "corpus_verdict" not in dict(admission.criteria_from_audit(result))


def test_a_close_naming_no_landing_cannot_decide_what_it_touched(tmp_path: Path) -> None:
    repo, _, _, root = landed_setup(tmp_path)
    result = audit_of(repo, "Nothing resolvable here.", dispatch_root=root)
    assert result.verdict_of("corpus_owed") == admission.AUDIT_UNDECIDABLE


# ----------------------------------------------------------------------- the evidence path


def pool(directory: Path, worst_class: str) -> Path:
    """Write one evidence directory carrying a `pool.json` of the given worst class."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "pool.json").write_text(json.dumps({"worst_class": worst_class}), encoding="utf-8")
    return directory


def test_a_quoted_evidence_path_that_does_not_resolve_audits_path_missing(tmp_path: Path) -> None:
    """#219's failure mode: a plausible path that resolves to nothing, asserted not assumed."""
    repo, _, landing, root = landed_setup(tmp_path)
    absent = tmp_path / "runs" / ".arma-cti" / "runs" / "20260806T000000Z-pool"
    result = audit_of(repo, f"{landing} evidence {absent}", dispatch_root=root)
    assert result.verdict_of("evidence") == admission.AUDIT_PATH_MISSING
    assert "does not exist" in result.checks[3].detail


def test_a_quoted_directory_carrying_no_pool_json_audits_path_missing(tmp_path: Path) -> None:
    repo, _, landing, root = landed_setup(tmp_path)
    hollow = tmp_path / "h" / ".arma-cti" / "runs" / "20260806T000000Z-pool"
    hollow.mkdir(parents=True)
    result = audit_of(repo, f"{landing} evidence {hollow}", dispatch_root=root)
    assert result.verdict_of("evidence") == admission.AUDIT_PATH_MISSING
    assert "carries no pool.json" in result.checks[3].detail


def test_a_quoted_pool_that_is_not_json_audits_path_missing(tmp_path: Path) -> None:
    repo, _, landing, root = landed_setup(tmp_path)
    broken = tmp_path / "b" / ".arma-cti" / "runs" / "20260806T000000Z-pool"
    broken.mkdir(parents=True)
    (broken / "pool.json").write_text("{not json", encoding="utf-8")
    result = audit_of(repo, f"{landing} evidence {broken}", dispatch_root=root)
    assert result.verdict_of("evidence") == admission.AUDIT_PATH_MISSING


def test_a_quoted_green_pool_audits_ok(tmp_path: Path) -> None:
    repo, _, landing, root = landed_setup(tmp_path)
    green = pool(tmp_path / "g" / ".arma-cti" / "runs" / "20260806T000000Z-pool", "pass")
    result = audit_of(repo, f"{landing} evidence {green}", dispatch_root=root)
    assert result.verdict_of("evidence") == admission.AUDIT_OK
    assert "worst_class=pass" in result.checks[3].detail


def test_a_quoted_red_pool_audits_red(tmp_path: Path) -> None:
    repo, _, landing, root = landed_setup(tmp_path)
    red = pool(tmp_path / "r" / ".arma-cti" / "runs" / "20260806T000000Z-pool", "assertion_failed")
    result = audit_of(repo, f"{landing} evidence {red}", dispatch_root=root)
    assert result.verdict_of("evidence") == admission.AUDIT_RED
    assert "worst_class=assertion_failed" in result.checks[3].detail


def test_the_worst_of_several_quoted_pools_is_the_verdict(tmp_path: Path) -> None:
    repo, _, landing, root = landed_setup(tmp_path)
    green = pool(tmp_path / "g" / ".arma-cti" / "runs" / "20260806T000000Z-pool", "pass")
    red = pool(tmp_path / "r" / ".arma-cti" / "runs" / "20260806T010000Z-pool", "timeout")
    result = audit_of(repo, f"{landing} first {green} then {red}", dispatch_root=root)
    assert result.verdict_of("evidence") == admission.AUDIT_RED


def test_a_close_quoting_no_run_directory_audits_absent(tmp_path: Path) -> None:
    repo, _, landing, root = landed_setup(tmp_path)
    result = audit_of(repo, f"Landed at {landing}.", dispatch_root=root)
    assert result.verdict_of("evidence") == admission.AUDIT_ABSENT


def test_an_owed_corpus_with_no_evidence_computes_not_met(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    base = commit(repo, {"docs/a.md": "a\n"}, "docs: base", when=COMMIT_BEFORE_IT)
    landing = commit(repo, {"missions/cti/init.sqf": "// x\n"}, "feat: refs #92", COMMIT_AFTER_IT)
    root = tmp_path / "dispatches"
    dispatch_record(root, "d-owed", issue=92, base_sha=base)
    result = audit_of(repo, f"Landed at {landing}.", dispatch_root=root)
    assert dict(admission.criteria_from_audit(result))["corpus_verdict"] == admission.NOT_MET


def test_an_owed_corpus_with_a_green_pool_is_still_the_recorder_s_call(tmp_path: Path) -> None:
    """`pool.json` records no filter, so a green pool cannot be shown to be the full corpus."""
    repo = tmp_path / "repo"
    base = commit(repo, {"docs/a.md": "a\n"}, "docs: base", when=COMMIT_BEFORE_IT)
    landing = commit(repo, {"extension/src/lib.rs": "// x\n"}, "feat: refs #92", COMMIT_AFTER_IT)
    root = tmp_path / "dispatches"
    dispatch_record(root, "d-owed", issue=92, base_sha=base)
    green = pool(tmp_path / "g" / ".arma-cti" / "runs" / "20260806T000000Z-pool", "pass")
    result = audit_of(repo, f"{landing} evidence {green}", dispatch_root=root)
    assert result.verdict_of("evidence") == admission.AUDIT_OK
    assert "corpus_verdict" not in dict(admission.criteria_from_audit(result))


def test_a_home_relative_run_path_is_read_against_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    pool(tmp_path / "home" / ".arma-cti" / "runs" / "20260806T000000Z-pool", "pass")
    assert admission.evidence_check("evidence ~/.arma-cti/runs/20260806T000000Z-pool").verdict == (
        admission.AUDIT_OK
    )


# ------------------------------------------------------------------- the two non-overclaims


def test_a_gate_block_is_quoted_and_never_green(tmp_path: Path) -> None:
    repo, _, landing, root = landed_setup(tmp_path)
    close = f"{landing}\n\ngate=green (just fast)\npushed={landing} origin/main\n"
    result = audit_of(repo, close, dispatch_root=root)
    assert result.verdict_of("gate_quoted") == admission.AUDIT_QUOTED
    assert admission.GATE_QUOTED_CAVEAT in result.checks[4].detail
    # The whole point: the strongest possible gate paste still fills nothing.
    assert "fast_green" not in dict(admission.criteria_from_audit(result))


def test_a_close_quoting_no_gate_output_audits_absent(tmp_path: Path) -> None:
    repo, _, landing, root = landed_setup(tmp_path)
    result = audit_of(repo, f"Landed at {landing}, and that is all.", dispatch_root=root)
    assert result.verdict_of("gate_quoted") == admission.AUDIT_ABSENT


CLOSES_THAT_MIGHT_TEMPT_A_CHANGELOG_PASS = (
    "",
    "CHANGELOG.md updated in the same commit.",
    "CHANGELOG.md ok=yes verdict=ok changelog=met",
    "No user-visible effect, so no entry was owed.",
    "diff --git a/CHANGELOG.md b/CHANGELOG.md\n+### Added\n+- a thing\n",
)


@pytest.mark.parametrize("close", CLOSES_THAT_MIGHT_TEMPT_A_CHANGELOG_PASS)
def test_no_close_makes_the_changelog_check_pass(tmp_path: Path, close: str) -> None:
    repo, _, landing, root = landed_setup(tmp_path)
    result = audit_of(repo, f"{landing}\n{close}", dispatch_root=root)
    assert result.verdict_of("changelog") == admission.AUDIT_UNDECIDABLE
    assert result.verdict_of("changelog") != admission.AUDIT_OK
    assert admission.AUDIT_UNDECIDABLE not in admission.CRITERION_STATES


def test_the_changelog_check_takes_no_input_to_be_swayed_by() -> None:
    """Nullary by construction, which is why "no input makes it `ok`" needs no sweep."""
    assert admission.changelog_check() == admission.changelog_check()
    assert admission.changelog_check().verdict == admission.AUDIT_UNDECIDABLE


def test_undecidable_is_never_one_of_part_a_s_passing_states() -> None:
    assert admission.AUDIT_UNDECIDABLE not in (admission.MET, admission.NOT_APPLICABLE)


# --------------------------------------------------------------- called, never reimplemented

# The strings a second implementation of the window tests would have to contain. Asserted
# present in `ledger.py` as well as absent from `admission.py`, so a rename in the ledger
# reds this guard rather than silently emptying it.
LEDGER_ONLY = ("--ancestry-path", "planned_at", "started_at", "%H%x1f%cI%x1f%B%x1e")


def test_the_window_tests_live_only_in_the_ledger() -> None:
    ledger_source = (admission.Path(ledger.__file__)).read_text(encoding="utf-8")
    audit_source = (admission.Path(admission.__file__)).read_text(encoding="utf-8")
    for marker in LEDGER_ONLY:
        assert marker in ledger_source, f"{marker} has moved: this guard now anchors on nothing"
        assert marker not in audit_source, f"{marker} is a second copy of the ledger's window"


def test_the_audit_calls_the_ledger_s_window_tests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, _, landing, root = landed_setup(tmp_path)
    called: list[str] = []
    real_landed = admission.ledger.landed
    real_start = admission.ledger.dispatch_start

    def spy_landed(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401 — a pass-through spy
        called.append("landed")
        return real_landed(*args, **kwargs)

    def spy_start(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401 — same
        called.append("dispatch_start")
        return real_start(*args, **kwargs)

    monkeypatch.setattr(admission.ledger, "landed", spy_landed)
    monkeypatch.setattr(admission.ledger, "dispatch_start", spy_start)
    result = audit_of(repo, f"Landed at {landing}.", dispatch_root=root)
    assert result.verdict_of("dispatch_window") == admission.AUDIT_OK
    assert called == ["dispatch_start", "landed"]


def test_the_pool_reading_is_pool_merge_s(tmp_path: Path, monkeypatch: Any) -> None:  # noqa: ANN401 — same
    repo, _, landing, root = landed_setup(tmp_path)
    green = pool(tmp_path / "g" / ".arma-cti" / "runs" / "20260806T000000Z-pool", "pass")
    monkeypatch.setattr(admission.pool_merge, "pool_reads_green", lambda _document: False)
    result = audit_of(repo, f"{landing} evidence {green}", dispatch_root=root)
    assert result.verdict_of("evidence") == admission.AUDIT_RED


# ------------------------------------------------------------------ which close was audited


def test_the_close_is_the_last_comment_written_before_the_close() -> None:
    """#92's thread carries a review posted the day after its close; the close is the close."""
    comments = [
        {"id": 1, "created_at": "2026-08-02T23:16:20Z", "body": "an audit"},
        {"id": 2, "created_at": "2026-08-05T21:47:46Z", "body": "Closed."},
        {"id": 3, "created_at": "2026-08-06T03:17:17Z", "body": "a review, afterwards"},
    ]
    assert admission.select_close(comments, "2026-08-05T21:47:46Z")["id"] == 2


def test_an_open_issue_has_no_close_to_audit() -> None:
    comments = [{"id": 1, "created_at": "2026-08-02T23:16:20Z", "body": "a comment"}]
    assert admission.select_close(comments, "") is None


def test_an_issue_closed_with_no_comment_before_it_has_no_close() -> None:
    comments = [{"id": 1, "created_at": "2026-08-06T03:17:17Z", "body": "afterwards"}]
    assert admission.select_close(comments, "2026-08-05T21:47:46Z") is None


# --------------------------------------------------------------------- record --from-audit


def close_file(tmp_path: Path, body: str) -> Path:
    """Write a close for the audit to read, which is the seam that keeps this tier offline."""
    path = tmp_path / "close.md"
    path.write_text(body, encoding="utf-8")
    return path


def record_argv(tmp_path: Path, repo: Path, root: Path, close: Path, *extra: str) -> list[str]:
    """Build the argv for one `record --from-audit`, with the criteria left to the caller."""
    return [
        "--admission-dir",
        str(tmp_path / "admission"),
        "--otlp-endpoint",
        DEAD_ENDPOINT,
        "record",
        "--lane",
        LANE,
        "--profile",
        PROFILE,
        "--seat",
        "implementer",
        "--issue",
        "92",
        "--repo",
        str(repo),
        "--dispatch-dir",
        str(root),
        "--close-file",
        str(close),
        "--from-audit",
        *extra,
    ]


def test_from_audit_still_demands_an_explicit_choice_on_the_rest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo, _, landing, root = landed_setup(tmp_path)
    close = close_file(tmp_path, f"Landed at {landing}. gate=green (just fast)")
    code = admission.main(record_argv(tmp_path, repo, root, close))
    printed = capsys.readouterr().err
    assert code == admission.EXIT_REFUSED
    assert "refusal=criteria_missing" in printed
    # The audit computed one criterion; the two it cannot compute are still required.
    assert "from_audit=close_names_sha=met" in printed
    assert "fast_green" in printed
    assert "hooks_clean" in printed
    assert "close_names_sha" not in printed.split("missing=")[1]


def test_from_audit_completes_once_the_rest_are_given(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo, _, landing, root = landed_setup(tmp_path)
    close = close_file(tmp_path, f"Landed at {landing}. gate=green (just fast)")
    code = admission.main(
        record_argv(
            tmp_path,
            repo,
            root,
            close,
            "--fast-green",
            admission.MET,
            "--hooks-clean",
            admission.MET,
            "--corpus-verdict",
            admission.NOT_APPLICABLE,
        )
    )
    printed = capsys.readouterr().out
    assert code == 0
    assert "from_audit=close_names_sha=met" in printed
    assert f"from_audit=sha={landing}" in printed
    assert "from_audit=dispatch=d-20260805-221743-8957c3" in printed
    assert "assessed=1/10" in printed


def test_from_audit_never_overrides_a_choice_the_recorder_made(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo, _, landing, root = landed_setup(tmp_path)
    close = close_file(tmp_path, f"Landed at {landing}.")
    code = admission.main(
        record_argv(
            tmp_path,
            repo,
            root,
            close,
            "--close-names-sha",
            admission.NOT_MET,
            "--fast-green",
            admission.MET,
            "--hooks-clean",
            admission.MET,
            "--corpus-verdict",
            admission.NOT_APPLICABLE,
        )
    )
    printed = capsys.readouterr().out
    assert code == 0
    assert "from_audit=close_names_sha" not in printed
    record = json.loads(
        (tmp_path / "admission" / f"{LANE}.{PROFILE}.implementer.json").read_text(encoding="utf-8")
    )
    criteria = record["attempts"][0]["assessments"][0]["criteria"]
    assert criteria["close_names_sha"] == admission.NOT_MET


def test_a_close_nobody_could_read_refuses_rather_than_auditing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo, _, _, root = landed_setup(tmp_path)
    missing = tmp_path / "nowhere" / "close.md"
    code = admission.main(
        [
            "audit",
            "--issue",
            "92",
            "--repo",
            str(repo),
            "--dispatch-dir",
            str(root),
            "--close-file",
            str(missing),
        ]
    )
    assert code == admission.EXIT_REFUSED
    assert "refusal=close_unreadable" in capsys.readouterr().err


def test_the_audit_verb_prints_every_check_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo, _, landing, root = landed_setup(tmp_path)
    close = close_file(tmp_path, f"Landed at {landing}. gate=green (just fast)")
    store = tmp_path / "admission"
    code = admission.main(
        [
            "--admission-dir",
            str(store),
            "audit",
            "--issue",
            "92",
            "--repo",
            str(repo),
            "--dispatch-dir",
            str(root),
            "--close-file",
            str(close),
        ]
    )
    printed = capsys.readouterr().out
    assert code == 0
    for name in admission.AUDIT_CHECKS:
        assert f"check={name} " in printed
    assert "explicit=fast_green corpus_verdict hooks_clean" in printed
    # An audit is evidence for a record, never a record: nothing on disk moved.
    assert not store.exists()


def test_an_audit_that_found_a_defect_still_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A verdict is a finding to read, not a gate: an exit code would make it one."""
    repo, _, _, root = landed_setup(tmp_path)
    close = close_file(tmp_path, "Nothing here resolves to a commit.")
    code = admission.main(
        [
            "audit",
            "--issue",
            "92",
            "--repo",
            str(repo),
            "--dispatch-dir",
            str(root),
            "--close-file",
            str(close),
        ]
    )
    assert code == 0
    assert f"check=sha_on_main verdict={admission.AUDIT_ABSENT}" in capsys.readouterr().out
