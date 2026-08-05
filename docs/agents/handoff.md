# Handing work to a continuation

> Status: validated ×1 — First use (2026-08-05): #208's own research agent, which
> produced this convention, ended by writing the handoff below onto #208 for whoever
> takes the adoption ruling forward. The template was written before that handoff and
> not adjusted to fit it; the one field it exercised hardest was *Ruled out*, which
> carries three options priced and rejected that a successor would otherwise re-price.

Why this exists: #204 proposes that an agent facing a long wait **ends** rather than
sitting through it, worth a measured ~6% of the bill. That rule creates continuations,
and a continuation is only safe if the ending agent left the right thing behind. This
is the right thing. Full arithmetic and citations: `docs/research/continuation-economics.md`.

## When to write one

1. **Before ending in front of a long gate** — the #204 shape: work committed, `just regress`
   or another long recipe dispatched, agent returns rather than waiting.
2. **On a blocker you cannot clear** — anything you would otherwise report and stop on.
3. **When told to wrap up** — session limits, conservation windows, a dispatch freeze.

Not for a finished, landed issue. A closed issue's record is its commits and its close
comment; a handoff there is ceremony.

## Where it goes

**A comment on the issue you were working**, opening with a `Handoff-for:` line so it can
be found without reading the thread. Not a file in the worktree: the worktree is removed,
and an agent that dies takes its scratch with it — the same reasoning ADR-0022 applies to
evidence. Not the final report alone either: the report goes to the orchestrator, and 85.6%
of a successor's opening state reconstruction is issue-thread reading, so the issue is where
a successor is already looking at its own expense.

## The template

```
Handoff-for: #NNN

State:      <one line — what is true right now>
SHA:        <sha> on <branch/worktree>, pushed|unpushed
Gates:      <verdict, quoted from the run — or "not run">
Evidence:   <path under ~/.arma-cti/runs/, or "none">
Next:       <the single next action, imperative>
Ruled out:  <what a successor would otherwise retry, and why it failed>
Risks:      <what is unverified and could bite>
Do not:     <anything plausible that would destroy work>
```

Omit a line only by writing `none` — a missing field reads as an oversight, and
`Gates: not run` is information a successor needs.

## Two rules that make it worth reading

**Quote the deterministic fields; never recall them.** `SHA`, `Gates` and `Evidence` come
from a command you ran in this session — `git rev-parse HEAD`, the verdict line, the
evidence path — not from memory. Measured summarisation fabricates factual claims at
24–39%, and file-and-artifact state is the single worst dimension in every compaction
method independently evaluated. If you cannot quote a gate result, write `not run`. A
handoff that asserts green without evidence is worse than no handoff.

**Stay under ~1,500 characters.** Anything a successor reads on turn 1 is billed about
12.55× over a median agent's life (one cache write plus a re-read on each of 113 later
turns), so a handoff is not free and a long one stops paying. Carry the *conclusion*
inline and the *pointer* beside it: `corpus 22/22 green at 5c407c6, evidence
~/.arma-cti/runs/2026-08-05T…` costs a line, where a bare path costs the successor a
directory listing, a file read, and the amplification on both.

`Ruled out` is the field to protect if you are running out of room. Everything else is
recoverable from git or the thread; an elimination is not, and CLAUDE.md's own
elimination-context rule says a result holds only in the context it was tested — an
elimination that does not travel gets re-run at full price.

## Reading one

A continuation reads the handoff **before** the issue body and before any `git log`. If
the handoff and the repo disagree, the repo wins and you say so in your own handoff:
the predecessor may have died between writing and pushing. Verify `SHA` with
`git rev-parse HEAD` and `Gates` against the evidence path rather than trusting either.

## How this differs from `/handoff`, and why

The global `/handoff` skill covers session→session handoff for a human-attended
successor. Two of its rules do not transfer, and the skill is global and shared across
projects, so it is not edited — the divergence is recorded here instead.

- It saves to the OS temporary directory, "not the current workspace". Right for a
  session; wrong for an agent, whose artifact must outlive a removed worktree.
- It says "Do not duplicate content already captured in other artifacts… Reference them
  by path or URL instead." Under 12.55× amplification that inverts. Measured here:
  briefings carrying a SHA correlate with **more** state reconstruction, not less
  (median 26,209 characters against 9,938). A pointer says *go and look*, and looking is
  what costs. Conclusion inline, pointer beside it.

What does transfer: compact rather than narrate, redact secrets, and end with what the
successor should do next.
