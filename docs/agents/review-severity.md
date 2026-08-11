# Review severity: what the four levels mean

Every finding in a never-alone review carries one of four severities, and the loop's
stop condition reads them. Without anchors the four words are inter-rater noise: a
reviewer on one model family and an arbiter on another can agree perfectly and mean
different things, and the drift measurement built on top of them would be agreement on
an undefined scale.

Binding: ADR-0071 ruling 4, which makes these anchors a prerequisite the first review
cannot run without. The drafting is owed to ADR-0071's own first review, run on
`codex-sol-xhigh`, which had to invent four definitions before it could report and
whose wording is kept here rather than replaced — an independent instance's scale is a
better starting point than the author's.

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

**Worked example.** The seat surfaces fail open on both harnesses (ADR-0068): an effort
level that does not exist, or a key that has drifted below the top level, leaves the
seat at the session's tier and reports nothing. That is why `just check-seats` asserts
the pair rather than trusting it. The z.ai lane's first live run has the same shape —
it executed the host's global hooks and never entered this repository's, so every
denial the project relies on was absent and no verdict said so (#225).

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

**Worked example.** The `validated ×N` count lagging its appended exemplar list in two
consecutive retro commits — each caught only by the next retro reading the log, and
neither changing what any rule meant (#186).

## How the levels are used

- The **reviewer** assigns a severity to every finding it reports. It never withholds a
  finding on the grounds that it is minor.
- The **implementer** may dispute a finding's correctness and its severity.
- An **arbiter** from the escalation set rules once per finding, and that ruling binds.
- The loop's stop condition is that nothing above **Low** remains unadjudicated. Low
  findings do not block; they are recorded.

## What these anchors are not

They are not calibrated. Nobody has measured whether two instances given this document
agree more than two instances given the bare words, and this document does not claim
they do. It is a starting scale with worked examples, published so that disagreement is
about a shared reference rather than about private ones — and the first thing to revise
if the reviewer-versus-arbiter comparison shows the levels are being read differently.
