"""An unreadable `git rev-list --count` is not a count of zero (#568).

`counted` answers `int | None`, and four call sites in `tools/land.py` spent
that answer with `or 0`: an unreadable count became "no incoming commits",
"no commit of yours to review" and "the rebase left nothing". Nothing landed
wrongly — a zero count refuses, fail-closed — but the refusal's words sent an
operator looking for uncommitted work while git had failed to count, and the
`rebase=already_current` line, which is read to decide whether a review verdict
still binds, was printed on a base whose movement was never established.

These tests stage the failure as a real one: the seam stands at `land.git`, and
every `rev-list --count` it sees is run for real with one option git rejects, so
git exits non-zero, `check=False` returns git's (empty) stdout, and `counted`
returns the `None` a live failure produces. Nothing else is stood in for — the
repositories, the fetch, the merge-base and the rebase are real, because the
claim under test is about ordering: which read refuses, and what the words it
refuses with say.

Each test that matters contrasts its unreadable run with the genuine zero over
the same tree, because a test asserting only "no crash" is what #568 was filed
against: the two runs must part company in kind, not in silence.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING, Any

import pytest
from conftest import load_tool

if TYPE_CHECKING:
    from pathlib import Path

# `land` imports `worktree` as a sibling script, so the sibling is loaded first
# and registered under its own name for that import to find.
worktree = load_tool("worktree")
land = load_tool("land")


def _git(*args: str, cwd: Path) -> str:
    # S603/S607: fixed literals and tmp_path-derived paths, and `git` off PATH on
    # purpose — the same reasoning as the tool under test.
    return subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def _commit(path: Path, name: str, body: str) -> None:
    target = path / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    _git("add", name, cwd=path)
    _git("commit", "-m", f"feat: {name}", cwd=path)


@pytest.fixture
def repo(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Build a bare `origin`, a main checkout on `main`, and one linked worktree.

    `test_land.py`'s arrangement, minus the policy and corpus probes: every rung
    that reads them sits behind the counts these tests break, so a leaner origin
    states exactly what the arrangement is rather than what it never reaches.
    """
    origin = tmp_path / "origin.git"
    _git("init", "--bare", "--initial-branch=main", str(origin), cwd=tmp_path)
    main = tmp_path / "repo"
    _git("clone", str(origin), str(main), cwd=tmp_path)
    _git("config", "user.email", "t@example.com", cwd=main)
    _git("config", "user.name", "T", cwd=main)
    _commit(main, "README.md", "one\n")
    _git("push", "origin", "main", cwd=main)

    here = main / ".claude" / "worktrees" / "issue-568"
    _git("worktree", "add", str(here), "origin/main", "--detach", cwd=main)
    return origin, main, here


def _failing_counts(monkeypatch: pytest.MonkeyPatch, after: int = 0) -> list[str]:
    """Make `rev-list --count` genuinely fail in `land`, from the Nth call on.

    Each call is the real command with one option git rejects, so git exits
    non-zero and `check=False` hands back the empty stdout a live failure
    produces — the staged failure travels the same bytes as an unsimulated one.
    `after` defers the break past the calls a test wants to succeed (the
    post-rebase recount is a land run's third count). The ranges it saw are
    returned, in order, so a test can name which read refused.
    """
    seen: list[str] = []
    real = land.git

    def _git(
        *args: str,
        cwd: Path,
        **kwargs: Any,  # noqa: ANN401 — forwarded to `tools/git`, whose signature is not importable
    ) -> str:
        if args[:2] == ("rev-list", "--count"):
            seen.append(" ".join(args[2:]))
            if len(seen) > after:
                return real(
                    "rev-list",
                    "--count",
                    *args[2:],
                    "--cti-staged-failure",
                    cwd=cwd,
                    **kwargs,
                )
        return real(*args, cwd=cwd, **kwargs)

    monkeypatch.setattr(land, "git", _git)
    return seen


def test_an_unreadable_ahead_count_refuses_naming_the_read_not_a_zero(
    repo: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The refusal Low 5 was about, in the unreadable half it never covered.

    A genuine zero on this tree refuses `nothing_to_land` and tells the lander to
    check they committed — correct words for a tree with no commits. An
    unreadable count must not wear them: the operator is sent hunting for
    uncommitted work when the failure is git's. The two runs part in kind, and
    the unreadable one names the range that could not be read.
    """
    origin, main, here = repo
    tip = _git("rev-parse", "main", cwd=origin).strip()

    genuine = land.stage(main, here)
    assert genuine.lines[0] == "refusal=nothing_to_land"
    assert f"ahead=0 commits over {land.BASE}" in genuine.lines

    seen = _failing_counts(monkeypatch, after=1)
    with pytest.raises(worktree.GitError) as refused:
        land.stage(main, here)

    assert len(seen) == 2
    assert seen[0].endswith(f"..{land.BASE}")
    assert seen[1] == f"{land.BASE}..HEAD"
    assert f"{land.BASE}..HEAD" in str(refused.value)
    assert "could not be read" in str(refused.value)
    # Nothing moved on either run: the refusal fired before the rebase.
    assert _git("rev-parse", "HEAD", cwd=here).strip() == tip


def test_an_unreadable_incoming_count_never_claims_the_base_did_not_move(
    repo: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`rebase=already_current` is a claim about `origin/main`; it needs the count.

    The sibling's landing moved the base, so a healthy run replays onto it and
    says so. An unreadable incoming count used to print `already_current` here —
    a positive claim the count never established, read downstream to decide
    whether a review verdict still binds. It must refuse before the rebase
    instead, leaving the tree exactly where it stood.
    """
    _origin, main, here = repo
    _commit(main, "sibling.txt", "landed first\n")
    _git("push", "origin", "main", cwd=main)
    _commit(here, "feature.txt", "work\n")
    before = _git("rev-parse", "HEAD", cwd=here).strip()

    healthy = land.stage(main, here)
    assert healthy.lines[0] == "ok=staged"
    assert "rebase=replayed onto 1 new commits" in healthy.lines
    replayed = _git("rev-parse", "HEAD", cwd=here).strip()
    assert replayed != before

    # A second tree at the pre-replay point, so the unreadable run faces the
    # same moved base the healthy one did.
    _git("reset", "--hard", before, cwd=here)
    seen = _failing_counts(monkeypatch)
    with pytest.raises(worktree.GitError) as refused:
        land.stage(main, here)

    assert len(seen) == 1
    assert seen[0].endswith(f"..{land.BASE}")
    assert refused.value.args_run == ("rev-list", "--count", seen[0])
    assert "could not be read" in str(refused.value)
    assert _git("rev-parse", "HEAD", cwd=here).strip() == before


def test_an_unreadable_recount_after_the_replay_is_not_a_dropped_branch(
    repo: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Refuse the post-rebase recount's unreadable half without a dropped branch's words.

    The branch keeps its commit through the replay, so a genuine recount says
    `commits=1` and stages; a genuine zero refuses `nothing_to_land`. Breaking
    only the third count — the recount, after incoming and ahead succeeded —
    must refuse naming the read, not report the branch empty of work its lander
    did commit.
    """
    _origin, main, here = repo
    _commit(here, "feature.txt", "work\n")
    before = _git("rev-parse", "HEAD", cwd=here).strip()

    seen = _failing_counts(monkeypatch, after=2)
    with pytest.raises(worktree.GitError) as refused:
        land.stage(main, here)

    assert len(seen) == 3
    assert seen[2] == f"{land.BASE}..HEAD"
    assert f"rev-list --count {land.BASE}..HEAD could not be read" in str(refused.value)
    # The rebase was the one act this tool performs, and with no incoming
    # commits it left HEAD where it was.
    assert _git("rev-parse", "HEAD", cwd=here).strip() == before


def test_the_recipe_names_the_failed_read_in_its_own_bytes(
    repo: tuple[Path, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """What an operator reads on the failing run: `git_failed`, naming the count.

    The dry run is the one output a foreign-lane seat is briefed to read, so the
    unreadable count's refusal is asserted where it is consumed — printed by
    `main`, not raised out of `land` — and it must say `git_failed` with the
    range, never `nothing_to_land`'s "check you committed it".
    """
    _origin, _main, here = repo
    _commit(here, "feature.txt", "work\n")
    _failing_counts(monkeypatch)
    monkeypatch.chdir(here)

    code = land.main(["--dry-run"])

    out = capsys.readouterr().out
    assert code == 1
    assert "refusal=git_failed" in out
    assert "command=git rev-list --count" in out
    assert "could not be read" in out
    assert "nothing_to_land" not in out
