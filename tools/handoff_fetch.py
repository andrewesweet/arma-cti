"""Print the newest handoff comment on an issue, and nothing else (#210).

A continuation's first read. #208 measured that 85.6% of a subagent's
first-ten-turn state reconstruction is GitHub-thread reading, and that everything
a successor reads on turn 1 is billed about 12.55× over a median 114-turn agent's
life (`docs/research/continuation-economics.md`). That is why the handoff goes in
an issue comment — a continuation is already looking there — and it is equally why
the retrieval needs a tool: `gh issue view --comments` on a long thread returns the
whole thread, and fetching a 1,500-character handoff by reading a 40,000-character
one defeats the point of having written it. So the thread is filtered here and only
the matched body is printed. Nothing else reaches a context window.

The marker is a `Handoff-for:` line, which must *open* a line — the template's own
shape (`docs/agents/handoff.md`), so a comment merely mentioning the convention in
prose is not a handoff.

**Where the selection lives, and why not in `--jq` as #210 sketched it.** The
sketched filter, `[.[] | select(.body | test("^Handoff-for:"; "m"))] | last | .body`,
fails open: on a thread carrying no handoff, `last` of an empty array is `null` and
`gh` prints an empty line and exits 0. An empty result reads as "no state to carry"
when it may mean "wrong issue number" — the #168/#183 shape, and the one thing #210
asks this tool not to do. A jq predicate also cannot be asserted in the no-Arma tier
at all, and #210 asks for exactly that assertion. So `gh` stays the transport and the
projection, while the selection and its refusal are Python under pytest (ADR-0049;
the #83 precedent that a classification bug should be a red `just unit` rather than
a discovery).

Exit codes separate a negative result from no result, the way the failure-class
table does: `1` is "this issue carries no handoff", `3` is "I could not look".
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    Fetch = Callable[[int], str]

# The template's marker, anchored to the start of a line (`re.M`), which is jq's
# `test("^Handoff-for:"; "m")` semantics and the reason a mention inside a
# sentence does not count.
MARKER: Final = re.compile(r"^Handoff-for:", re.MULTILINE)

# One comment body per line, JSON-encoded. `@json` escapes the newlines a
# markdown body is full of, so a page reads back as JSON Lines rather than as an
# ambiguous run of bodies — and nothing but the bodies crosses the pipe.
PROJECTION: Final = ".[] | .body | @json"

# `gh` fills `{owner}` and `{repo}` from the checkout's remote, so the endpoint
# carries no hard-coded slug to go stale on a fork or a rename.
PLACEHOLDERS: Final = "repos/{owner}/{repo}"

# A network call that never returns is a held turn. Bounded like every other
# call this project makes out of a recipe (#144).
TIMEOUT_S: Final = 60

# "This issue carries no handoff" — a result, and a negative one.
NO_HANDOFF: Final = 1
# "I could not look" — not a result (the failure-class table's
# `infra_unavailable` row in a smaller place). Distinct on purpose: a caller
# must be able to tell the two apart without reading prose.
NO_RESULT: Final = 3


class FetchError(RuntimeError):
    """`gh` could not be run, refused the request, or answered unreadably."""


def endpoint(issue: int) -> str:
    """Return the comments endpoint, with gh's own placeholders left for gh."""
    return f"{PLACEHOLDERS}/issues/{issue}/comments"


def command(issue: int) -> list[str]:
    """Return the argv that fetches every comment body on one issue.

    `--paginate` is load-bearing rather than defensive: page one is the *oldest*
    thirty comments, so a long thread without it would answer from the wrong end
    and miss the newest handoff entirely.
    """
    return ["gh", "api", endpoint(issue), "--paginate", "--jq", PROJECTION]


def bodies(payload: str) -> list[str]:
    """Return the comment bodies in one `gh --jq` payload, oldest first."""
    lines = [line for line in payload.splitlines() if line.strip()]
    try:
        return [json.loads(line) for line in lines]
    except json.JSONDecodeError as broken:
        message = f"gh answered with something that is not JSON Lines: {broken}"
        raise FetchError(message) from broken


def select(comments: Iterable[str]) -> str | None:
    """Return the newest body carrying a `Handoff-for:` line, or `None`.

    Newest is last: the comments endpoint returns a thread in ascending creation
    order, and `--paginate` concatenates its pages in that same order.
    """
    carried = [body for body in comments if MARKER.search(body)]
    return carried[-1] if carried else None


def fetch_comments(issue: int) -> str:
    """Return `gh`'s payload for one issue's comments, or raise `FetchError`."""
    try:
        completed = subprocess.run(  # noqa: S603 — fixed argv, no shell, no interpolation
            command(issue),
            capture_output=True,
            text=True,
            check=False,
            timeout=TIMEOUT_S,
        )
    except FileNotFoundError as missing:
        message = "`gh` is not on PATH, so no handoff could be looked for."
        raise FetchError(message) from missing
    except subprocess.TimeoutExpired as slow:
        message = f"`gh` did not answer within {TIMEOUT_S}s, so no handoff could be looked for."
        raise FetchError(message) from slow
    if completed.returncode != 0:
        detail = completed.stderr.strip() or f"exit {completed.returncode}"
        message = f"`gh` could not read the comments on #{issue}: {detail}"
        raise FetchError(message)
    return completed.stdout


def issue_number(raw: str) -> int:
    """Parse an issue reference, with or without the `#` an agent types."""
    text = raw.strip().removeprefix("#")
    if not text.isdigit() or int(text) <= 0:
        message = f"not an issue number: {raw!r}"
        raise argparse.ArgumentTypeError(message)
    return int(text)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """One door: the issue whose handoff to print."""
    parser = argparse.ArgumentParser(description="Print an issue's newest handoff comment.")
    parser.add_argument("issue", type=issue_number, help="issue number, e.g. 210")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, *, fetch: Fetch = fetch_comments) -> int:
    """Print the handoff, or refuse loudly. Never print the thread."""
    args = parse_args(argv)
    try:
        comments = bodies(fetch(args.issue))
    except FetchError as failure:
        print(f"[handoff] {failure}", file=sys.stderr)  # noqa: T201 — a CLI's refusal channel
        return NO_RESULT
    handoff = select(comments)
    if handoff is None:
        print(  # noqa: T201 — a CLI's refusal channel
            f"[handoff] no handoff on #{args.issue}: {len(comments)} comment(s) scanned,"
            " none opens a line with `Handoff-for:`.",
            file=sys.stderr,
        )
        print(  # noqa: T201 — a CLI's refusal channel
            "[handoff] Either none was written, or this is the wrong issue."
            " Template: docs/agents/handoff.md",
            file=sys.stderr,
        )
        return NO_HANDOFF
    print(handoff)  # noqa: T201 — the handoff IS this script's output
    return 0


if __name__ == "__main__":
    sys.exit(main())
