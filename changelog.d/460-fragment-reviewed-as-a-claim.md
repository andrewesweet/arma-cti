### Changed

- **A `changelog.d/` fragment is reviewed as a claim, not as prose (#460; the human's ruling
  of 2026-08-20, recorded as ADR-0077).** Every sentence is checked against the diff exactly
  as a code comment is, and a fragment claiming more than landed blocks the landing rather
  than being filed as a follow-up. What makes a fragment different from ordinary prose is
  mechanical: `scriv collect` folds it verbatim into `CHANGELOG.md` at the next `cog bump`,
  `just check`'s fragment leg is content-blind — it verifies that a fragment exists, never
  that it is true (#429) — and a released changelog entry is never re-read the way a code
  comment is when someone next edits the function, so a false sentence there is the one claim
  in this repository that ships without ever being checked again. The evidence is one
  session: five fragments claimed more than their diff delivered and #446's, read sentence by
  sentence, was accurate. Three surfaces state the rule and read one string to do it —
  `AGENTS.md` normatively, `docs/review-dispatch.md` as the reviewer's obligation beside the
  gate-paste contract and again in the brief template it hands out, and `tools/brief.py`,
  whose new `CHANGELOG_CLAIM_RULE` is that string. The composed brief renders it to the
  implementer who writes the fragment and to the reviewer who judges it; `recon`, which
  writes none and judges none, is the one seat it is silent for. Two tests hold the surfaces to
  the constant rather than to their own literals — one counting its copies in `AGENTS.md` and
  `docs/review-dispatch.md`, one binding every rendered brief — which is #445's finding 3 not
  repeated in the change that codifies reviewing claims. A third uses its own literals
  deliberately, to pin that the constant's own wording says the gate is content-blind.

- **No mechanical content check comes with it, and none is proposed.** `just check`'s fragment
  leg is untouched: it still asks whether a fragment exists and never whether a sentence is
  true, the gap #429 records deliberately. The rule is enforced by a reviewer reading, and
  what landed only puts it where the reviewer and the implementer each meet it — in the brief
  as well as in the review contract, because #445 landed with an omission whose rule lived
  only in a document its implementer had no obligation to read.
