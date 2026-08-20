# A changelog.d fragment is reviewed as a claim, not as prose

Delegated-decision: no
Date: 2026-08-20
Supersedes: none
Reviewed-by-human: the human's instruction of 2026-08-20 on #460 — "Make the changelog
fragment rule change" — given after a session in which five fragments claimed more than
their diff delivered
Claimed: 0077 — after `git fetch origin` (`docs/adr/` on `origin/main` topping at 0076, at
`95f7beb`) and a scan of every open issue body, which returned no ADR number at or above
0077. Comment search was unavailable to this session: both `gh search issues` and the
repository comments API were refused, so the blind window AGENTS.md records is wider here
than the usual one — a claim living only in a comment would not have been seen, and the
landing rebase is the backstop

The rule, ruled by the human and recorded here rather than left as an unmarked edit to a
sign-off-gated file:

> A `changelog.d/` fragment is reviewed as a claim, not as prose: every sentence is checked
> against the diff exactly as a code comment is, and a fragment claiming more than landed
> blocks the landing rather than being filed as a follow-up.

## Why a fragment is not ordinary prose

Three mechanics, together: `scriv collect` folds a fragment **verbatim** into `CHANGELOG.md`
at the next `cog bump`; `just check`'s fragment leg is **content-blind**, verifying that a
fragment exists rather than that it is true (#429); and a released changelog entry is never
re-read the way a code comment is when someone next edits the function. So a false sentence
in a fragment is the one kind of claim in this repository that ships without ever being
checked again.

## The evidence

One session, 2026-08-19/20. Five fragments claimed more than their diff delivered, each
caught by a cross-lane review: #433 asserted two GLM 5.3 names *"behave identically today"*
on a mechanism the installed runner disproves; #425 said `archive`, `restore` and `exchange`
*"cannot hang on the same bad afternoon"* when only `archive` was true; #424/#435 said
selection *"no longer reads the clock at all"* while the method's own docstring admitted two
reads; #445's fragment was a revision behind its own code (#459); and #442 claimed a `unit`
movement from 191.7 s to 134.6 s, where the record shows 191.67 s was a green **`fast`** row
and the only 191.7 s `unit` row was red. Three of those blocked a landing under the rule as
applied. The counter-example is why the rule is discriminating rather than merely
obstructive: #446's fragment was checked sentence by sentence and found accurate.

## What this does not decide

It does not make the fragment gate verify content. Nothing here asks `just check` to judge
whether a sentence is true — #429 records that gap deliberately, and a checker that guessed
would be the token-versus-thing class #458 carries eight instances of. The rule is enforced
by a reviewer reading, and the change that applies it only makes sure the reviewer knows to
read and the implementer knows they will be read.

## One home, three surfaces

The wording lives once, in `tools/brief.py`'s `CHANGELOG_CLAIM_RULE`. `AGENTS.md` states it
normatively, `docs/review-dispatch.md` states the reviewer's obligation beside the gate-paste
contract and in the brief template, and the composed brief renders it to the implementer who
writes the fragment and to the reviewer who judges it. Tests read the constant and assert it
into each surface, so the three cannot drift: #445's finding 3 was exactly the other
arrangement — a sentence built in a tool, retyped in the document and retyped again in the
template, with each test asserting against its own literal.

The implementer's copy is the load-bearing one. #445 landed because the sampled-or-exhaustive
sentence lived only in the review contract, so implementers who had never read that document
kept omitting it. A rule only reviewers know produces findings; a rule the implementer meets
in their brief produces compliance.

## What would overturn it

A run of fragments blocked under this rule that a later reading finds were accurate — the
rule catching prose it should have passed — or a measured cost in review attention that buys
nothing, meaning fragments that were already reliably true. The decision is the human's to
revisit either way; this record exists so a revisit has something to argue with.
