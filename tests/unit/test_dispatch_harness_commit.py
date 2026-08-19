"""The session gates and the harness commits, which is how Codex becomes an implementer (#405).

Codex's sandbox enforces `<root>/.git` as a read-only path inside every writable root — it is
protecting git history from the agent, deliberately — so a session can commit only if its git
directory is a writable root, and naming one makes the sandbox create the `.git` it means to
protect, which libgit2 then opens instead of the real layout. Six arrangements were measured
against that and none escaped it; the seventh reading is that there is nothing to escape. With
no git directory named, `cog check` returns `No errored commits`: the session runs the gate,
which is the whole of the binary capability rule's demand, and the commit belongs to the
dispatcher, which is not sandboxed.

So the claims here are about the seam between the two halves — `CODEX_COMMIT_MESSAGE` — and
about the states either side of it can end in: the pre-launch refusals that stop a stale
predecessor being absorbed into a fresh run, and the end states `harness_finish` reaches.
They are made against real git repositories
rather than a mocked `git`, because every one of them is a claim about what git did: a commit
that exists, a tree left untouched, a `commit-msg` hook that refused. A stubbed git would let
all of them pass over code that never committed anything.

The push half is `review_exchange.exchange`'s and is asserted through a real remote, so the
"pushed commit" the acceptance evidence asks for is a fact about a ref rather than about a
call. `harness_commits` — which dispatches decide by — is asserted per lane and per permission
mode, because a predicate that answered "yes" on the Claude family would have the harness
committing over a session that commits its own work.

The brief's half of the seam is claimed in `test_dispatch_seat.py` rather than here, with the
rest of the planning ladder: reaching it means planning a whole dispatch, and a module that
executes the ladder is a module whose mutation sample is planted across code these tests
cannot pin.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from conftest import load_tool

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

dispatch = load_tool("dispatch")

MESSAGE = "feat(x): a session's own message\n\nrefs #405\n"


def _git(*args: str, cwd: Path) -> str:
    """Run one git command and hand back stdout, failing the test on git's own error."""
    done = subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


def _repository(path: Path, *, bare: bool = False) -> Path:
    """Make a git repository the harness can really commit into."""
    path.mkdir(parents=True)
    _git("init", "-q", "-b", "main", *(("--bare",) if bare else ()), cwd=path)
    if not bare:
        _git("config", "user.email", "t@example.invalid", cwd=path)
        _git("config", "user.name", "t", cwd=path)
    return path


def _tree_with_a_remote(tmp_path: Path) -> tuple[Path, Path]:
    """Build a worktree with one commit and an `origin` a push can really reach."""
    remote = _repository(tmp_path / "remote.git", bare=True)
    tree = _repository(tmp_path / "tree")
    (tree / "README.md").write_text("t\n", encoding="utf-8")
    _git("add", "-A", cwd=tree)
    _git("commit", "-qm", "chore: base", cwd=tree)
    _git("remote", "add", "origin", str(remote), cwd=tree)
    return tree, remote


def _record(tmp_path: Path) -> Path:
    """Make the dispatch record directory the message is kept beside."""
    record = tmp_path / "record"
    record.mkdir(parents=True, exist_ok=True)
    return record


def _edited(tree: Path, message: str | None = MESSAGE) -> None:
    """Stage the tree the way a sandboxed session leaves it: an edit, and maybe a message."""
    (tree / "edited.txt").write_text("what the session wrote\n", encoding="utf-8")
    if message is not None:
        (tree / dispatch.CODEX_COMMIT_MESSAGE).write_text(message, encoding="utf-8")


# ------------------------------------------------------- which dispatches this applies to


def test_only_a_writable_codex_sandbox_hands_its_commit_to_the_harness() -> None:
    # The whole reason the harness commits is that this one sandbox will not let the
    # session do it. Every other lane's session commits its own work, and a harness that
    # committed over it would be committing whatever that session had not finished.
    assert dispatch.harness_commits(dispatch.LANES["codex"], "acceptEdits") is True
    assert dispatch.harness_commits(dispatch.LANES["claude-native"], "acceptEdits") is False
    assert dispatch.harness_commits(dispatch.LANES["zai"], "acceptEdits") is False


def test_a_read_only_codex_seat_has_nothing_for_the_harness_to_commit() -> None:
    # `plan` and `default` are the read-only branch of the sandbox map, which is what the
    # recon and review seats force. Nothing was edited, so nothing is committed — and the
    # unrecognised mode falls to the same read-only default rather than to the writable one.
    for mode in ("plan", "default", "read-only-ish-nonsense"):
        assert dispatch.harness_commits(dispatch.LANES["codex"], mode) is False


# ------------------------------------------------------------------ the four end states


def test_the_harness_commits_what_the_session_edited_with_the_message_it_left(
    tmp_path: Path,
) -> None:
    tree, remote = _tree_with_a_remote(tmp_path)
    record = _record(tmp_path)
    _edited(tree)
    lines, code = dispatch.harness_finish(tree, 405, record)
    assert code == 0, lines
    assert "harness_commit=committed" in lines
    # The commit is real, carries the session's message verbatim, and holds its edit.
    assert _git("log", "-1", "--pretty=%B", cwd=tree).strip() == MESSAGE.strip()
    assert _git("show", "--name-only", "--pretty=", "HEAD", cwd=tree) == "edited.txt"
    # And the message file itself is never in it: it is moved to the record before anything
    # is staged, so a reader of the run's evidence sees what the session asked for.
    assert not (tree / dispatch.CODEX_COMMIT_MESSAGE).exists()
    assert (record / "commit-message.txt").read_text(encoding="utf-8") == MESSAGE
    # The push is the exchange's, on the ref the review loop already reads, and the remote
    # really resolves this exact commit.
    head = _git("rev-parse", "HEAD", cwd=tree)
    assert f"commit={head}" in lines
    assert _git("rev-parse", "refs/heads/issue-405", cwd=remote) == head


def test_a_tree_the_session_left_clean_is_not_a_commit_and_not_a_refusal(
    tmp_path: Path,
) -> None:
    # A dispatch that read, searched or found nothing to change is a legitimate run. An
    # empty commit invented for it would record an act nobody performed.
    tree, remote = _tree_with_a_remote(tmp_path)
    before = _git("rev-parse", "HEAD", cwd=tree)
    lines, code = dispatch.harness_finish(tree, 405, _record(tmp_path))
    assert code == 0
    assert "harness_commit=nothing_to_commit" in lines
    assert _git("rev-parse", "HEAD", cwd=tree) == before
    assert _git("branch", "--list", cwd=remote) == ""


def test_edits_with_no_message_refuse_by_name_and_leave_the_tree_alone(
    tmp_path: Path,
) -> None:
    # The issue's own instruction: a refusal that names the missing file beats a commit
    # nobody wrote a message for. The edits stay exactly as the session left them, because
    # the alternative — a message the harness made up — is unreviewable, and resetting the
    # tree is the one thing #105 forbids.
    tree, _remote = _tree_with_a_remote(tmp_path)
    _edited(tree, message=None)
    before = _git("rev-parse", "HEAD", cwd=tree)
    lines, code = dispatch.harness_finish(tree, 405, _record(tmp_path))
    assert code == dispatch.EXIT_REFUSED
    assert "refusal=commit_message_absent" in lines
    assert f"expected={tree / dispatch.CODEX_COMMIT_MESSAGE}" in lines
    # What was found is named, not counted: the reader has to decide whose file it is.
    assert "untracked=?? edited.txt" in lines
    assert _git("rev-parse", "HEAD", cwd=tree) == before
    assert (tree / "edited.txt").exists()


def test_a_message_that_is_only_whitespace_is_no_message(tmp_path: Path) -> None:
    # `git commit` would refuse an empty message anyway; refusing it here is what makes the
    # refusal name the file rather than quote git at a reader who cannot act on it.
    tree, _remote = _tree_with_a_remote(tmp_path)
    _edited(tree, message="   \n\n")
    lines, code = dispatch.harness_finish(tree, 405, _record(tmp_path))
    assert code == dispatch.EXIT_REFUSED
    assert "refusal=commit_message_absent" in lines


def test_a_message_the_commit_msg_hook_refuses_arrives_as_git_failed(tmp_path: Path) -> None:
    # The harness commit is subject to the repository's own hooks, which is the point: a
    # session's message meets `cog verify` exactly as a Claude-side session's would. Staged
    # with a hook that refuses everything, because what this asserts is that the hook's
    # refusal reaches the reader with git's own words — not that `cog` is installed here.
    tree, _remote = _tree_with_a_remote(tmp_path)
    hook = tree / ".git" / "hooks" / "commit-msg"
    hook.write_text("#!/bin/sh\necho 'not a conventional commit' >&2\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)
    _edited(tree)
    before = _git("rev-parse", "HEAD", cwd=tree)
    record = _record(tmp_path)
    lines, code = dispatch.harness_finish(tree, 405, record)
    assert code == dispatch.EXIT_REFUSED
    assert "refusal=git_failed" in lines
    assert any("not a conventional commit" in line for line in lines)
    assert _git("rev-parse", "HEAD", cwd=tree) == before
    # Review's Medium: the refusal used to claim "the tree is as the session left it",
    # which `git add --all` had already made false — everything staged, message file gone.
    # The text now names what the tree really holds, and these three facts are what make
    # it true rather than polite.
    assert any("staged" in line for line in lines)
    assert any(str(record / "commit-message.txt") in line for line in lines)
    assert (record / "commit-message.txt").read_text(encoding="utf-8") == MESSAGE
    assert _git("status", "--porcelain", cwd=tree).startswith("A  edited.txt")


def test_an_add_that_cannot_stage_refuses_without_claiming_a_staged_tree(
    tmp_path: Path,
) -> None:
    # Review round three's Medium: one `try` over `git add` and `git commit` made the
    # add's refusal carry the commit's text — "every edit is staged" over a tree where
    # the add never completed. Split, so each refusal is true of the git that refused.
    # A stale `index.lock` is the real, deterministic way `git add --all` fails while
    # the `git status` above it still answers: nothing is staged by it and nothing is
    # cleaned away by the harness, so the lock is the reader's to judge.
    tree, _remote = _tree_with_a_remote(tmp_path)
    record = _record(tmp_path)
    _edited(tree)
    (tree / ".git" / "index.lock").write_text("", encoding="utf-8")
    before = _git("rev-parse", "HEAD", cwd=tree)
    lines, code = dispatch.harness_finish(tree, 405, record)
    assert code == dispatch.EXIT_REFUSED
    assert "refusal=git_failed" in lines
    assert "command=git add --all" in lines
    # True of the add: no commit, no push, the edits and the lock untouched, and no
    # claim about a staging state a failed add cannot vouch for.
    assert any("itself was refused" in line for line in lines)
    assert _git("rev-parse", "HEAD", cwd=tree) == before
    assert (tree / "edited.txt").exists()
    assert (tree / ".git" / "index.lock").exists()
    assert (record / "commit-message.txt").read_text(encoding="utf-8") == MESSAGE


def test_a_commit_whose_sha_cannot_be_read_back_refuses_and_never_pushes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Review round three's other Medium: the post-commit `rev-parse` had no test, so
    # nothing pinned that its failure is a named refusal with the push unattempted
    # rather than a traceback or a success. The read-back cannot be made to fail by
    # staging the tree — it runs after a commit that must succeed — so the real `git` is
    # wrapped for exactly that one command and nothing else: status, add and commit run
    # for real, and the assertions below are facts about the tree and the remote, not
    # about the wrapper.
    tree, remote = _tree_with_a_remote(tmp_path)
    _edited(tree)
    record = _record(tmp_path)
    real_git = dispatch.worktree_tool.git

    def refusing_read_back(*args: str, cwd: Path) -> str:
        if args[:2] == ("rev-parse", "HEAD"):
            raise dispatch.worktree_tool.GitError(("rev-parse", "HEAD"), "fatal: HEAD is gone")
        return real_git(*args, cwd=cwd)

    monkeypatch.setattr(dispatch.worktree_tool, "git", refusing_read_back)
    lines, code = dispatch.harness_finish(tree, 405, record)
    assert code == dispatch.EXIT_REFUSED
    assert "refusal=git_failed" in lines
    assert any("HEAD is gone" in line for line in lines)
    # The commit is real and carries the session's message; the push is what the refusal
    # held back, and the remote proves it.
    assert _git("log", "-1", "--pretty=%B", cwd=tree).strip() == MESSAGE.strip()
    assert _git("branch", "--list", cwd=remote) == ""


def test_a_message_that_is_not_utf8_text_is_a_named_refusal_not_a_traceback(
    tmp_path: Path,
) -> None:
    # Review's Medium: a non-UTF-8 message raised an uncaught UnicodeDecodeError, so no
    # named refusal and no result.json — and a worktree left occupied by a crash. Named
    # here, the file left exactly where the session put it, and the reader sent to the
    # run's own log rather than to a traceback nobody actionable can read.
    tree, _remote = _tree_with_a_remote(tmp_path)
    (tree / "edited.txt").write_text("what the session wrote\n", encoding="utf-8")
    (tree / dispatch.CODEX_COMMIT_MESSAGE).write_bytes(b"\xff\xfe not text\r\n\x00")
    before = _git("rev-parse", "HEAD", cwd=tree)
    lines, code = dispatch.harness_finish(tree, 405, _record(tmp_path))
    assert code == dispatch.EXIT_REFUSED
    assert "refusal=commit_message_unreadable" in lines
    assert f"file={tree / dispatch.CODEX_COMMIT_MESSAGE}" in lines
    assert _git("rev-parse", "HEAD", cwd=tree) == before
    assert (tree / dispatch.CODEX_COMMIT_MESSAGE).exists()


# --------------------------------------------------- what must hold before the session runs


def test_a_predecessors_surviving_message_refuses_before_the_session_launches(
    tmp_path: Path,
) -> None:
    # Review's High 2: a finished predecessor's message file and edits survive in the
    # worktree, and `git add --all` in `harness_finish` would sweep them into this run's
    # commit — attributing one run's work to another's issue. The refusal comes before
    # anything launches, and it names the file rather than the tree's dirt, because a
    # surviving `CODEX_COMMIT_MESSAGE` says "uncommitted handover" where a dirty tree
    # alone says "someone is working here".
    tree, _remote = _tree_with_a_remote(tmp_path)
    (tree / "edited.txt").write_text("the predecessor's edit\n", encoding="utf-8")
    (tree / dispatch.CODEX_COMMIT_MESSAGE).write_text(
        "fix(x): the predecessor's own message\n\nrefs #404\n", encoding="utf-8"
    )
    refusal = dispatch.harness_start_refusal(tree)
    assert refusal is not None
    assert refusal.kind == "dispatch_message_present"
    assert f"file={tree / dispatch.CODEX_COMMIT_MESSAGE}" in refusal.found
    # Nothing has been committed, staged or removed by the asking.
    assert (tree / dispatch.CODEX_COMMIT_MESSAGE).exists()
    assert dispatch.harness_start_refusal(tree).kind == "dispatch_message_present"


def test_a_dirty_tree_with_no_message_refuses_before_the_session_launches(
    tmp_path: Path,
) -> None:
    # The other half of High 2: edits with no message file are still files this run did
    # not write, and the harness commit would absorb them. #105's vocabulary is reused
    # rather than invented — `dirty_tree`, with the files named, never counted.
    tree, _remote = _tree_with_a_remote(tmp_path)
    (tree / "edited.txt").write_text("someone's edit\n", encoding="utf-8")
    refusal = dispatch.harness_start_refusal(tree)
    assert refusal is not None
    assert refusal.kind == "dirty_tree"
    assert "untracked=?? edited.txt" in refusal.found
    assert any("harness commit sweeps" in line for line in refusal.lines())


def test_a_clean_tree_with_no_message_launches_without_refusal(tmp_path: Path) -> None:
    # The rung asks a question with a real negative answer, not a blanket stop: the tree
    # `just worktree add` makes is exactly this one, and it must keep launching.
    tree, _remote = _tree_with_a_remote(tmp_path)
    assert dispatch.harness_start_refusal(tree) is None


def test_a_push_that_does_not_land_is_the_exchanges_refusal_and_not_a_silent_success(
    tmp_path: Path,
) -> None:
    # The commit is made either way — it is local work and worth keeping — but the run does
    # not report success on a handover the reviewer cannot reach.
    tree, remote = _tree_with_a_remote(tmp_path)
    _git("remote", "set-url", "origin", str(tmp_path / "nowhere.git"), cwd=tree)
    _edited(tree)
    lines, code = dispatch.harness_finish(tree, 405, _record(tmp_path))
    assert code == dispatch.EXIT_REFUSED
    assert "harness_commit=committed" in lines
    assert "refusal=git_failed" in lines
    assert _git("log", "-1", "--pretty=%B", cwd=tree).strip() == MESSAGE.strip()
    assert _git("branch", "--list", cwd=remote) == ""
