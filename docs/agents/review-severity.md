# Review severity: what the four levels mean

Every finding in a never-alone review carries one of four severities, and the loop's
stop condition reads them. Without anchors the four words are inter-rater noise: a
reviewer on one model family and an arbiter on another can agree perfectly and mean
different things, and the drift measurement built on top of them would be agreement on
an undefined scale.

Binding: ADR-0071 ruling 4, which requires these anchors before **the first review run
under that ruling** — that is, before never-alone operates, which is sequencing step 7.
They did not precede ADR-0071's own reviews, which ran while the ruling was still being
drafted; those reviews are what produced them. The first, on `codex-sol-xhigh`, had to
invent four definitions before it could report, and its wording is kept here rather than
replaced — an independent instance's scale is a better starting point than the author's.

Each level carries one worked example from this repository's own history, because a
level defined only in the abstract is a level every reader calibrates privately.

## Critical — a core safety invariant can be bypassed

The change admits a state the design says cannot happen, and nothing downstream would
notice. Not "serious bug": *invariant defeated*.

**Worked example.** ADR-0071's first draft stated "no single model instance may both
propose and land a change" and then mandated identity separation only for the reviewer,
leaving the proposing instance free to run `just land` itself. The invariant was
asserted in the same document that left it unimplemented, and every gate would have
stayed green.

## High — a binding contradiction, or a silent enforcement failure with broad reach

Two rules that cannot both be followed, or a mechanism that fails open across a whole
class of work without saying so. The distinguishing property against Medium is
**silence and reach**: nobody finds out, and it applies to more than the case in hand.

**Worked example.** #44's first two-slot regression run had isolated ports, directories,
installs and daemons, and the two worlds still merged on a `CTI_DAEMON_ADDR` nobody had
set. The run did not assert on it, so it went green. Isolation was believed rather than
established, across every future run of that tier, and the gate said nothing.

Its sibling is ADR-0068's pair of declaration surfaces — `.claude/agents/` definitions
and skill frontmatter, both on Claude Code — which fail open in the same way: an effort
level that does not exist, or a key that has drifted below the top level, leaves the seat
at the session's tier and reports nothing. That is why `just check-seats` asserts the
pair rather than trusting it.

## Medium — a material but contained defect

Real, worth fixing, and its blast radius is the thing in front of you. A wrong fact, a
design that will not extend, a check that misses a case — where the miss does not
generalise into a silent class-wide failure.

**Worked example.** #157's hand-maintained probe list defended itself against a rename
and was blind to addition: four later issues had grown the corpus from two to six and
the list did not know. Contained — one list, one kind of staleness — and fixed by
deriving the list from the probe headers.

## Low — a localised factual, naming or counting error

Wrong in a way a reader can see and correct without changing a decision. It still gets
reported: filtering by severity is a separate pass, never the reviewer's to perform.

**Worked example.** The `validated ×N` count lagging its appended exemplar list. The
fourteenth retro's lag was caught by the fifteenth; the fifteenth's own lag was then
propagated by the sixteenth and seventeenth reading the log rather than the file, and
caught only by the eighteenth — which is why it earned a mechanical check (#186). A Low
finding that survives four readings is still Low: it changed what no rule meant.

## How the levels are used

- The **reviewer** assigns a severity to every finding it reports. It never withholds a
  finding on the grounds that it is minor.
- The **implementer** may dispute a finding's correctness and its severity.
- The **implementer** may also adjudicate a finding at **Medium or below**
  **accepted and filed**: agree it is real, state why the fix does not belong in
  this diff, and file it as an issue on the originating item **before** landing.
  The landing record carries it like any other adjudication, naming the issue it
  became. Not available above Medium **by default**, and not available at any
  severity where the defect is in the diff under review rather than conditional
  on work outside it — "it only bites if someone later does X" is the test, and X
  must be named. The Medium ceiling binds the implementer, not the human who set
  it: a **human ruling quoted on the finding** lifts it for that one finding, and
  the ruling's own words are stored beside the adjudication so a reader checks
  the citation rather than trusting the admission. It lifts the ceiling and
  excuses nothing else — the filed issue and the named condition are still both
  required, and a ruling given without words is refused (human ruling of
  2026-08-30 on #643, amending ADR-0071 ruling 4 as amendment A11; #651).
  Conditional
  harm does not re-grade the finding to Low: these levels anchor on blast radius
  and silence, not likelihood, and a latent design defect graded Low would
  understate it permanently in the landing record (human ruling of 2026-08-14 on
  #334, amending ADR-0071 ruling 4; written by `just review-loop adjudicate
  --route accepted_and_filed`).

  **Worked example.** A review finds that a helper will misbehave if a future
  caller passes a value no current caller passes. Real, worth fixing, and
  nothing in this diff can trigger it. Accepted and filed — not a fix round.
- An **arbiter** — one rule with one answer — rules once per finding, and that ruling binds.
  It is resolved from the **implementing** seat, whichever one did the work, not the
  `implementer` row for every seat (ADR-0071 ruling 4 as amended by A1, #361). The
  resolution is `tools/arbiter.py`, reached by `just review-loop escalate`, and **what that
  walk does is stated there and nowhere else, this document included** — the version of it
  that stood here listed one exclusion rung where the code has four, until round 3 of #361
  (#390).
- The loop's stop condition is that nothing above **Low** remains unadjudicated. Low
  findings do not block; they are recorded.

## What these anchors are not

They are not calibrated. Nobody has measured whether two instances given this document
agree more than two instances given the bare words, and this document does not claim
they do. It is a starting scale with worked examples, published so that disagreement is
about a shared reference rather than about private ones.

They are also **not revised on the arbiter-versus-reviewer comparison**, tempting as that
is. An arbiter sees only findings that were disputed, and sees the reviewer's rating when
it rules — a selected, unblinded subset (ADR-0071 ruling 6). Treating its disagreements as
calibration evidence would read selection and anchoring effects as drift. What would
justify revising these anchors is a blind classifier over an unselected sample, which
ADR-0071 files as separate work.
