# Issue tracker: GitHub

Issues and PRDs for this repo live as GitHub issues. Use the `gh` CLI for all operations.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`. Use a heredoc for multi-line bodies.
- **Read an issue**: `gh issue view <number> --comments`, filtering comments by `jq` and also fetching labels.
- **List issues**: `gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'` with appropriate `--label` and `--state` filters.
- **Comment on an issue**: `gh issue comment <number> --body "..."`
- **Apply / remove labels**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **Close**: `gh issue close <number> --comment "..."`

Infer the repo from `git remote -v` — `gh` does this automatically when run inside a clone.

## Closing an issue that carries acceptance criteria

Close it in the same session that lands its work, with a comment addressing every acceptance criterion: evidence for each criterion met, and for any criterion not met as written, a pointer to the recorded decision (ADR or issue) that superseded it — a prose note is not a supersession, and commit titles are not evidence. If you inherit an issue whose work landed in an earlier session, audit every criterion against the tree before closing: that audit on #12 found an architectural pivot (callback-push to poll-and-ack) shipped but decided nowhere, and stopped it closing as "done".

A `Closes #N` commit trailer closes the issue on push and skips this audit entirely: #89
was auto-closed with two acceptance boxes unticked and had to be reopened by its own
agent, and #24 repeated it despite this paragraph — its criterion-by-criterion comment
was written and posted, but the trailer skipped the gate rather than passing it. On an
issue carrying acceptance criteria, reference the commit without a closing keyword and
close by hand with the criterion-by-criterion comment. Two self-corrected instances
against a written rule is the document-vs-mechanism shape ADR-0038 named, so the check
is becoming mechanical: #129 puts a closing-keyword deny in the commit-msg gate,
matching exactly the syntax GitHub acts on.

## Decision tickets

A design question that gates implementation travels as its own issue and closes with **no code**: an ADR (with any CONTEXT.md term changes in the same commit) plus implementation issues in dependency order, each carrying acceptance criteria precise enough to implement without a clarifying question. The closing comment names the decision, the issues it spawned, and their ordering rationale. Exemplar: #31 → ADR-0020 + #32–#35; three implementing agents ran concurrently off those criteria and none needed to ask anything. Raise one when a build ticket flags a decision as "not the scorer's to route around" — the flag is the trigger, and the decision ticket is what keeps the build ticket honest about its scope.

## Directed review passes

A whole-project review runs as a set of parallel review tickets, one lens per ticket (a
named skill or book), each review-only. First run 2026-08-01 (#55–#58 + #95): four
concurrent fable reviews plus one extension, ~45 findings, the first seven fixed the same
day — the shape below is what all five independently held to, so reuse it rather than
re-inventing the ticket.

Each ticket carries: **scope** (the surfaces by name), the **lens**, and **deliverables**
— a rubric self-assessment per dimension with evidence against a stated numeric target;
every finding filed as a severity-tagged backlog issue in house style, full sweep before
severity filtering per CLAUDE.md; and a priority ordering of the findings against the
open backlog in the summary comment. No code changes in a review ticket.

Two disciplines concurrency makes load-bearing: a reviewer **notes** a neighbouring
lens's finding rather than re-filing it (each review names which remit a noted item
belongs to), and where a fix agent is already in flight on the same ground, the review
cites the in-flight issue as evidence rather than filing over it (#95 did both).

Scope the production surfaces explicitly: a review scoped to the test infrastructure
reviews the test infrastructure (#58), and the play path a human sits inside for hours
needed its own extension ticket — which produced the cycle's worst score (#95, ~5/10)
on exactly the surface no automated tier exercises.

A pass does not need a whole-project occasion: a single concrete observation is a
sufficient trigger for a supplemental single-lens ticket, scoped tightly to the
observation's own dimension and held to the same deliverable contract. Run twice on
2026-08-02: two asides about engine idioms became #107 (the systematic
engine-replaceable sweep #56 had not run — six firm hits) and one sighting of a
hand-rolled `isServer` guard became #111 (none of the addon's 22 server guards can
fire, and two probes green with their client leg unexercised, #116). The observation
supplies the scope; do not widen the ticket beyond it.

## Pull requests as a triage surface

**PRs as a request surface: no.** _(Set to `yes` if this repo treats external PRs as feature requests; `/triage` reads this flag.)_

When set to `yes`, PRs run through the same labels and states as issues, using the `gh pr` equivalents:

- **Read a PR**: `gh pr view <number> --comments` and `gh pr diff <number>` for the diff.
- **List external PRs for triage**: `gh pr list --state open --json number,title,body,labels,author,authorAssociation,comments` then keep only `authorAssociation` of `CONTRIBUTOR`, `FIRST_TIME_CONTRIBUTOR`, or `NONE` (drop `OWNER`/`MEMBER`/`COLLABORATOR`).
- **Comment / label / close**: `gh pr comment`, `gh pr edit --add-label`/`--remove-label`, `gh pr close`.

GitHub shares one number space across issues and PRs, so a bare `#42` may be either — resolve with `gh pr view 42` and fall back to `gh issue view 42`.

## When a skill says "publish to the issue tracker"

Create a GitHub issue.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --comments`.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a single issue with **child** issues as tickets.

- **Map**: a single issue labelled `wayfinder:map`, holding the Notes / Decisions-so-far / Fog body. `gh issue create --label wayfinder:map`.
- **Child ticket**: an issue linked to the map as a GitHub sub-issue (`gh api` on the sub-issues endpoint). Where sub-issues aren't enabled, add the child to a task list in the map body and put `Part of #<map>` at the top of the child body. Labels: `wayfinder:<type>` (`research`/`prototype`/`grilling`/`task`). Once claimed, the ticket is assigned to the driving dev.
- **Blocking**: GitHub's **native issue dependencies** — the canonical, UI-visible representation. Add an edge with `gh api --method POST repos/<owner>/<repo>/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`, where `<blocker-db-id>` is the blocker's numeric **database id** (`gh api repos/<owner>/<repo>/issues/<n> --jq .id`, _not_ the `#number` or `node_id`). GitHub reports `issue_dependencies_summary.blocked_by` (open blockers only — the live gate). Where dependencies aren't available, fall back to a `Blocked by: #<n>, #<n>` line at the top of the child body. A ticket is unblocked when every blocker is closed.
- **Frontier query**: list the map's open children (`gh issue list --state open`, scoped to the map's sub-issues / task list), drop any with an open blocker (`issue_dependencies_summary.blocked_by > 0`, or an open issue in the `Blocked by` line) or an assignee; first in map order wins.
- **Claim**: `gh issue edit <n> --add-assignee @me` — the session's first write.
- **Resolve**: `gh issue comment <n> --body "<answer>"`, then `gh issue close <n>`, then append a context pointer (gist + link) to the map's Decisions-so-far.
