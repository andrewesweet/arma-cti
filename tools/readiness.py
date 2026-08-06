"""Definition of ready, mechanically: what a dispatch reads off an issue body (#241).

Readiness existed only implicitly — a `ready-for-agent` label and whatever criteria the
body happened to carry. Nothing checked that criteria exist, that they can be counted
off, or that any of them names the evidence that would settle them. Vague criteria are
where audit quality dies first, so this is the check, and `tools/dispatch.py` is the rung
that reads it beside admission, the breaker and the off-peak rule.

**The remedy is always an issue edit, by a human or by triage.** Nothing here rewrites an
issue, proposes replacement wording, or files anything. A tool that repaired the body it
was judging would be marking its own homework, and the whole value of a readiness gate is
that a person had to think about what "done" means before a lane was spent on it.

**Lane-blind.** `assess` takes a body and nothing else — no lane, no profile, no seat. A
foreign lane meets exactly the refusal `claude-native` meets, which is ADR-0061's rule for
every gate in this project and the one property that makes the check worth having at all.

## The three sub-checks

Each is judged independently and each is named separately, because they fail for different
reasons and their measured error rates turned out to be different too.

- **`criteria_absent`** — the body says nothing that reads as "here is what to do" or "here
  is what done looks like": no countable criteria unit *and* no directive lead.
- **`criteria_not_enumerable`** — criteria are there, but fewer than two of them can be
  counted off. A reader cannot tick them, and neither can a close audit.
- **`criteria_without_evidence_shape`** — nothing anywhere in the body names a gate, a
  test, a verdict or an artefact, so no criterion can be settled by pointing at something.

## The definitions, pre-registered

These were written down before the corpus was run, for #224's reason: a threshold chosen
after seeing the numbers is a threshold fitted to the answer somebody wanted. What the
measurement was then allowed to decide was *which sub-checks refuse*, not what they mean.

A **criteria unit** is one of, counted over the body with fenced code blocks removed:

1. a task-list item (`- [ ]`, `- [x]`);
2. a markdown list item, bulleted or ordered;
3. a table body row — every row of a table past its header and separator;
4. an inline enumerator run: `(1)`, `(2)`, … present from 1 upwards, counted to the
   highest consecutive marker. Two or more are needed before any of them counts, so a
   lone "(1)" in prose enumerates nothing.

A **directive lead** is a line opening a heading, a bold label or a colon-led clause from a
fixed vocabulary — `Acceptance`, `Scope`, `What`, `Build`, `Fix`, `Requirements`, `Tests`,
`Method`, `Constraints`, and the rest of `DIRECTIVE_LEADS`. The vocabulary is a corpus
reading, not a convention this file is imposing: it is what the last twenty dispatched
issues actually wrote, and an issue is not obliged to use any of it as long as it carries
countable units instead.

An **evidence shape** is a mechanical thing a criterion could be settled against: a `just`
recipe, test or assertion vocabulary, a gate colour, a verdict or failure class, a probe or
the corpus, a file path, or a commit SHA.

## What the corpus measured

The population is the twenty most recently dispatched issues at the time of writing —
every issue closed between #207 and #243 — vendored verbatim under
`tests/fixtures/readiness-corpus/` so the measurement is re-run by `just unit` rather than
remembered. Every one of the twenty was dispatched and landed, so *every* refusal the
check makes on that corpus is a false positive by construction. That is the whole method:
the false-positive rate of a sub-check is the fraction of the twenty it refuses.

| Sub-check | Refused | Rate | Strictness |
|---|---|---|---|
| `criteria_absent` | 0/20 | 0% | **hard** |
| `criteria_without_evidence_shape` | 0/20 | 0% | **hard** |
| `criteria_not_enumerable` | 3/20 | **15%** | advisory |

Per shape, which is where the 15% comes from and why it is not a number to average away:

| Shape | n | `not_enumerable` false positives |
|---|---:|---|
| feature / build | 13 | 0 (0%) |
| experiment / decision | 3 | 0 (0%) |
| ruling execution | 3 | 2 — #238, #232 (67%) |
| defect repair | 1 | 1 — #231 (100%) |

The reason is structural rather than incidental, which is why enumerability is advisory
and not merely un-tuned. A ruling execution's criteria *are* the ruling: #238 is the
human's off-peak rule, #232 is #220's metric definition, #231 is the repair a defect's own
sequence dictates. Those arrive as prose and are transcribed rather than restated, because
enumerating them would mean paraphrasing a ruling — the one thing a ruling execution must
not do. A gate that demands a checklist there is asking the wrong shape of issue to become
a different shape, and #137's lesson is the opposite: fit the gate to what the corpus
actually contains. So the check still *says* an issue is unenumerable, on every issue and
every lane, and never refuses on it alone.

## What this check does not cover, stated rather than hidden

- **Evidence is searched over the whole body, not over the criteria.** Locating "the
  criteria" inside a prose body is the same problem enumerability just failed at, so a
  body whose background prose mentions a test and whose criteria name nothing would pass.
  The check catches bodies with no evidence vocabulary at all; it does not check that the
  evidence named belongs to the criterion beside it.
- **Nothing here reads quality.** Two counted units may both be vague. This is a shape
  gate, and a shape gate is worth having only because the shapes it rejects are ones no
  close audit could ever settle.
- **A body that cannot be read is not a body that passed** (#41). The fetch failure is the
  caller's to classify; this module returns the reason and never a verdict.
- **`criteria_absent` has no true positive in the corpus.** It refused none of the twenty,
  which is what earned it a hard refusal, and it also means the population contains no
  example of the thing it is for. Its only demonstrated firings are the synthetic unready
  bodies in `tests/unit/test_readiness.py`. That is a weaker footing than a sub-check with
  a live example either way, and it is the first thing to re-measure when the corpus next
  grows.
"""

from __future__ import annotations

import re
import subprocess
from typing import Final, NamedTuple

REPO_SLUG: Final = "andrewesweet/arma-cti"

# `gh` is a network call on the dispatch path, so it is bounded like every other
# subprocess a seam makes (#144, ADR-0049). A readiness read that hangs must not become a
# `just dispatch` that hangs.
FETCH_TIMEOUT_SECONDS: Final = 30

# Which sub-checks refuse a dispatch and which only say so. Set by the corpus measurement
# in this module's docstring and by nothing else: a sub-check earns `HARD` by refusing
# none of the twenty issues that were dispatched and landed.
HARD: Final = frozenset({"criteria_absent", "criteria_without_evidence_shape"})
ADVISORY: Final = frozenset({"criteria_not_enumerable"})

# Two units, not one. One unit is a sentence; two is a list a reader can tick and a close
# audit can walk. The corpus is unambiguous about the boundary: the three issues this
# refuses carry **zero** units and the thinnest issue it clears carries **three** (#210),
# so the whole population sits in a gap around this number rather than near it. Any value
# in 1..3 measures identically, which is the reason to state the number rather than tune
# it — nothing was fitted here, because there was nothing to fit it to.
ENUMERABLE_UNITS: Final = 2

# Fenced code blocks are removed before units are counted: a shell snippet's flags and a
# config file's keys are not criteria, and #210's body carries both.
_FENCE = re.compile(r"^\s*(```|~~~).*?^\s*\1", re.MULTILINE | re.DOTALL)

_TASK_ITEM = re.compile(r"^\s{0,7}[-*+]\s+\[[ xX]\]\s+\S")
_LIST_ITEM = re.compile(r"^\s{0,7}(?:[-*+]|\d{1,2}[.)])\s+\S")
_TABLE_ROW = re.compile(r"^\s{0,3}\|.*\|\s*$")
_TABLE_RULE = re.compile(r"^\s{0,3}\|[\s:|-]+\|\s*$")
_INLINE_ENUM = re.compile(r"\((\d{1,2})\)")

# The vocabulary the last twenty dispatched issues actually used to open a directive. A
# lead is a heading, a bold label, or a colon-led clause at the start of a line.
DIRECTIVE_LEADS: Final = (
    "acceptance",
    "arms",
    "build",
    "constraint",
    "criteri",
    "deliver",
    "done when",
    "fix",
    "gate",
    "method",
    "not in scope",
    "plan",
    "requirement",
    "scope",
    "step",
    "task",
    "test",
    "what",
)
_LEAD = re.compile(
    r"^\s{0,3}(?:#{1,6}\s+)?[*_]{0,2}\s*(" + "|".join(DIRECTIVE_LEADS) + r")",
    re.IGNORECASE | re.MULTILINE,
)

# CLAUDE.md's failure-class table, spelled here because an issue that names the class its
# work should produce has named an evidence shape as concretely as one naming a recipe.
FAILURE_CLASSES: Final = (
    "assertion_failed",
    "timeout",
    "node_crashed",
    "oracle_disagreement",
    "infra_unavailable",
    "engine_drift",
    "schema_stale",
    "flake_quarantine",
    "quota_exhausted",
    "provider_refused",
)

# What a criterion could be settled against. Every entry is something mechanical that
# exists or does not: a recipe that runs, a test that reds, a class a verdict carries, a
# file that is on disk, a commit that is on main.
EVIDENCE_SHAPES: Final[tuple[tuple[str, str], ...]] = (
    ("recipe", r"\bjust\s+[a-z][a-z-]{2,}"),
    ("test", r"\b(?:pytest|hypothesis|tests?|tested|testing|assert\w*|fixtures?)\b"),
    ("gate", r"\b(?:gate|gates|gated|green|red)\b"),
    ("verdict", r"\b(?:verdict|verdicts|probe|probes|corpus|failure class|regression)\b"),
    ("class", r"\b(?:" + "|".join(FAILURE_CLASSES) + r")\b"),
    ("path", r"[\w.\-]+/[\w.\-]+\.[A-Za-z]{1,5}\b"),
    ("sha", r"\b[0-9a-f]{7,40}\b"),
)
_EVIDENCE = tuple((name, re.compile(pattern, re.IGNORECASE)) for name, pattern in EVIDENCE_SHAPES)


class Finding(NamedTuple):
    """One sub-check that did not clear, and the counts behind it."""

    kind: str
    detail: str

    @property
    def hard(self) -> bool:
        """Whether this finding refuses a dispatch rather than only reporting."""
        return self.kind in HARD


class Assessment(NamedTuple):
    """What one issue body was found to carry, and which sub-checks it failed."""

    units: int
    leads: tuple[str, ...]
    evidence: tuple[str, ...]
    findings: tuple[Finding, ...]

    @property
    def blocking(self) -> tuple[Finding, ...]:
        """The findings that refuse a dispatch."""
        return tuple(found for found in self.findings if found.hard)

    @property
    def advisory(self) -> tuple[Finding, ...]:
        """The findings that are reported and never refuse."""
        return tuple(found for found in self.findings if not found.hard)

    def lines(self) -> tuple[str, ...]:
        """Render the counts a caller prints, in the tier's `key=value` form."""
        return (
            f"criteria_units={self.units}",
            f"directive_leads={','.join(self.leads) or 'none'}",
            f"evidence_shapes={','.join(self.evidence) or 'none'}",
        )


def strip_code(body: str) -> str:
    """Drop fenced code blocks, which carry flags and keys rather than criteria."""
    return _FENCE.sub("\n", body)


def count_units(body: str) -> int:
    """Count the criteria units in a body: list items, table rows, inline enumerators.

    List items and table rows are counted per line; the inline run is counted once for the
    body, so `(1)`…`(5)` in one paragraph is five units and not five plus the lines it sits
    on. Table headers and separator rules are not criteria and are excluded, which is why
    the row count subtracts the two lines that open each table.
    """
    text = strip_code(body)
    lines = text.splitlines()
    listed = sum(1 for line in lines if _LIST_ITEM.match(line) or _TASK_ITEM.match(line))

    rows = 0
    in_table = False
    for line in lines:
        if _TABLE_RULE.match(line):
            in_table = True
            continue
        if _TABLE_ROW.match(line):
            rows += 1 if in_table else 0
        else:
            in_table = False
    # A table's header row matched `_TABLE_ROW` before its rule was seen, so it was never
    # counted; the rule line is skipped above. What `rows` holds is body rows only.

    return listed + rows + count_inline_enumerators(text)


def count_inline_enumerators(text: str) -> int:
    """Count an inline `(1)`, `(2)`, … run, or zero if there is no run to count.

    A run must start at 1 and is counted to its highest consecutive marker, so the "(1)"
    that opens a sentence with no "(2)" after it enumerates nothing, and a stray "(3)" in
    prose cannot conjure a run out of nothing either. A run shorter than `ENUMERABLE_UNITS`
    counts as no run at all, which is the same sentence the caller applies to the total:
    fewer than two of anything is not an enumeration.
    """
    seen = {int(match.group(1)) for match in _INLINE_ENUM.finditer(text)}
    highest = 0
    while highest + 1 in seen:
        highest += 1
    return highest if highest >= ENUMERABLE_UNITS else 0


def find_leads(body: str) -> tuple[str, ...]:
    """Name the directive leads the body opens a line with, in the vocabulary's order."""
    text = strip_code(body)
    found = {match.group(1).lower() for match in _LEAD.finditer(text)}
    return tuple(lead for lead in DIRECTIVE_LEADS if any(hit.startswith(lead) for hit in found))


def find_evidence(body: str) -> tuple[str, ...]:
    """Name which evidence shapes the body mentions anywhere, deduplicated and in order."""
    return tuple(name for name, pattern in _EVIDENCE if pattern.search(body))


def assess(body: str) -> Assessment:
    """Judge one issue body. Lane-blind by construction: there is nothing else to pass in.

    `criteria_absent` subsumes `criteria_not_enumerable` and is reported alone when it
    fires, because "there are no criteria" and "the criteria cannot be counted" are the
    same sentence twice and the second one is noise beside the first.
    """
    units = count_units(body)
    leads = find_leads(body)
    evidence = find_evidence(body)

    findings: list[Finding] = []
    if units == 0 and not leads:
        findings.append(
            Finding("criteria_absent", "nothing in the body states what to do or what done means")
        )
    elif units < ENUMERABLE_UNITS:
        findings.append(
            Finding(
                "criteria_not_enumerable",
                f"units={units} needed={ENUMERABLE_UNITS} leads={','.join(leads) or 'none'}",
            )
        )
    if not evidence:
        findings.append(
            Finding(
                "criteria_without_evidence_shape",
                "no gate, test, verdict, class, path or SHA is named anywhere in the body",
            )
        )
    return Assessment(units=units, leads=leads, evidence=evidence, findings=tuple(findings))


def fetch_body(issue: int, repo: str = REPO_SLUG) -> tuple[str, str]:
    """Read an issue body through `gh`, returning `(body, "")` or `("", reason)`.

    The reason is handed back rather than raised, and rather than being turned into a
    verdict here, because what an unreadable issue means for a dispatch is the
    dispatcher's ruling to make and CLAUDE.md's table is where it is made.
    """
    # S603/S607: fixed literals plus an integer issue number; `gh` resolves off PATH like
    # every other tool this project shells out to.
    try:
        done = subprocess.run(  # noqa: S603
            [  # noqa: S607
                "gh",
                "issue",
                "view",
                str(issue),
                "--repo",
                repo,
                "--json",
                "body",
                "--jq",
                ".body",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=FETCH_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        return "", "gh is not on PATH"
    except subprocess.TimeoutExpired:
        return "", f"gh did not answer within {FETCH_TIMEOUT_SECONDS}s"
    if done.returncode != 0:
        return "", (done.stderr.strip() or f"gh exited {done.returncode}").splitlines()[0]
    if not done.stdout.strip():
        return "", "the issue body is empty"
    return done.stdout, ""
