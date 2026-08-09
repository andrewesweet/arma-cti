"""`just check-seats`: a seat's model and effort are declared, and declared validly.

Effort becomes real only through a definition file. The Agent tool carries no effort
parameter and a subagent silently inherits its dispatcher's model unless overridden,
which is how every implementation agent of 2026-08-04 ran on fable and consumed the
bulk of a weekly budget. `.claude/agents/` exists to make the (model, effort) pair a
declared fact; #255 added a second place the same pair can be declared, the frontmatter
of a user-invoked skill.

Both places fail **open**. A misspelled key, an effort level that does not exist, an
indented line that is no longer top-level frontmatter — none of them refuse. Claude
Code loads the definition with whatever metadata it could parse and the seat runs at
the session's model and effort, which is exactly the failure the definition file was
introduced to prevent, and it is invisible: the seat answers, the work lands, and the
only trace is a cheaper tier than the one the mapping ratified.

So the pair is asserted rather than assumed. Every agent definition declares both from
the ratified sets; a skill declares neither (inheriting the session, as the project's
three existing skills do) or both, validly. `inherit` is the skill frontmatter's own
spelling for "keep the active model" and is accepted there, never in an agent seat,
where inheriting is the defect.

Scope is this repository's `.claude/` only. A personal seat under `~/.claude/agents/`
is the human's and no gate of this project's reaches it.
"""

from __future__ import annotations

import sys
from pathlib import Path

FENCE = "---"
AGENT_MODELS = frozenset({"opus", "sonnet", "haiku", "fable"})
SKILL_MODELS = AGENT_MODELS | {"inherit"}
EFFORTS = frozenset({"low", "medium", "high", "xhigh", "max"})


def frontmatter(text: str) -> dict[str, str] | None:
    """Return the top-level `key: value` scalars, or None when the fences are not there.

    Deliberately not a YAML parse: the thing being checked is that a value survives to
    the loader as a top-level scalar, so a parser generous enough to recover an indented
    or malformed key would read past the defect this exists to catch.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != FENCE:
        return None
    try:
        end = lines.index(FENCE, 1)
    except ValueError:
        return None
    found: dict[str, str] = {}
    for line in lines[1:end]:
        if not line or line[0].isspace() or ":" not in line:
            continue
        key, _, value = line.partition(":")
        found[key.strip()] = value.strip()
    return found


def _pair_failures(where: str, front: dict[str, str], models: frozenset[str]) -> list[str]:
    """Name each half of the pair that is absent or outside its set."""
    found: list[str] = []
    model, effort = front.get("model"), front.get("effort")
    if model is None:
        found.append(f"{where}: no `model:` — the seat would inherit its dispatcher's")
    elif model not in models:
        found.append(f"{where}: model `{model}` is not one of {sorted(models)}")
    if effort is None:
        found.append(f"{where}: no `effort:` — the seat would inherit the session's")
    elif effort not in EFFORTS:
        found.append(f"{where}: effort `{effort}` is not one of {sorted(EFFORTS)}")
    return found


def agent_failures(root: Path) -> list[str]:
    """Every agent seat declares a ratified model and effort."""
    found: list[str] = []
    for path in sorted((root / ".claude" / "agents").glob("*.md")):
        where = path.relative_to(root).as_posix()
        front = frontmatter(path.read_text(encoding="utf-8"))
        if front is None:
            found.append(f"{where}: no `---` frontmatter block — the whole file is body")
            continue
        found.extend(_pair_failures(where, front, AGENT_MODELS))
    return found


def skill_failures(root: Path) -> list[str]:
    """Require a skill declaring either half of the pair to declare both, validly."""
    found: list[str] = []
    for path in sorted((root / ".claude" / "skills").glob("*/SKILL.md")):
        where = path.relative_to(root).as_posix()
        front = frontmatter(path.read_text(encoding="utf-8"))
        if front is None:
            found.append(f"{where}: no `---` frontmatter block — the whole file is body")
            continue
        if "model" not in front and "effort" not in front:
            continue
        found.extend(_pair_failures(where, front, SKILL_MODELS))
    return found


def failures(root: Path) -> list[str]:
    """Every way a declared seat can be silently not the seat it names."""
    return agent_failures(root) + skill_failures(root)


def main() -> int:
    """Print each failure, or nothing at all when every seat declares itself."""
    root = Path(__file__).resolve().parents[1]
    found = failures(root)
    for line in found:
        print(line, file=sys.stderr)  # noqa: T201 — the check speaks to its runner
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
