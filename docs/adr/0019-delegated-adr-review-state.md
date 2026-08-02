# A delegated-decision ADR carries its review state and its overturning evidence

Delegated-decision: yes
Date: 2026-08-01
Stood-in-for: human sign-off on process-doc changes — this retro's amendments to CLAUDE.md, docs/agents/issue-tracker.md, ADR-0013's convention, and the probe headers (scheduled retro, 2026-08-01; the retro skill itself was left untouched — its proposed amendments are in the process log for the human)
Reviewed-by-human: 2026-08-02

Decided at the 2026-08-01 retro, after auditing the six delegated-decision ADRs the phase
produced (0013–0018) as ADR-0013 intends the human to be able to.

**The audit's verdict on the six.** They are genuine decisions, not write-ups: each weighs
alternatives it rejects (asymmetric weights in 0015, folding into #5 in 0016, a generated-SQF
fallback in 0017, the push path in 0018), and each ratifies built work while saying so plainly —
which is what a sign-off on a flagged judgement call is. Two gaps, both fixed here:

1. **The set could not answer "which of these have I since reviewed."** The marker's grep returns
   every delegated decision ever taken, a set that only grows, so the human's audit worklist had
   to be reconstructed from memory. The field block gains a fourth line, `Reviewed-by-human:`,
   written `pending` by the agent and flipped to a date only by the human — never by an agent.
   `grep -rl "^Reviewed-by-human: pending" docs/adr/` is now the outstanding-review worklist, and
   the complete-set grep is unchanged.
2. **One of the six (ADR-0015) stated no overturning evidence.** Five did, and that is what makes
   a post-hoc ratification auditable rather than self-sealing: the reviewer can disagree with the
   decision by pointing at the evidence it named. The convention now requires it — a
   delegated-decision ADR states what evidence would overturn each decision it takes — and 0015
   is retrofitted in this commit.

ADR-0013 is amended in place (its convention block now shows four lines and the
overturning-evidence requirement), and 0013–0018 are retrofitted with `Reviewed-by-human:
pending`, all in this commit, so the worklist is complete from its first grep.

**One convention extension noted rather than decided at length:** `spike/probes/` now holds a
red-by-design probe (`manifest-missing.sqf`, whose green run is the bug), which ADR-0016's corpus
definition — "everything under `spike/probes/`" gated green — did not anticipate. Its header
gains a fourth machine-readable line, `// expect: assertion_failed`; a probe with no `expect:`
line expects `PASS`. #23's runner honours it.

**What would overturn this.** The `Reviewed-by-human:` field earns its line only if the human
uses it: if reviews happen in conversation and the field sits at `pending` across two retros for
decisions the human has plainly already engaged with, it is ceremony, and the fix is to drop the
field rather than to nag the human into grepping. The overturning-evidence requirement is
overturned by a delegated decision that genuinely has none — none has appeared yet; if one does,
the honest form is a stated "nothing would overturn this short of X" rather than silence.
