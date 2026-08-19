### Fixed

- **`just review-loop escalate`'s three reads of `origin` are bounded by a 60 s deadline (#425).**
  The routing rung #391 added reads the branch under review with an `ls-remote` and two `fetch`es
  and bounded none of them, so a wedged remote could hold an escalation for as long as git cared
  to wait — on a lane whose provider had returned a 529 twice and exhausted a five-hour quota twice
  in one day. `worktree.git` takes a `timeout` that kills the child at its deadline, the same
  whole-call property `bounded_request` buys for HTTP reads; the expiry is a `GitError` naming the
  bound and lands in the escalation's existing could-not-read refusal. The local reads
  (`rev-parse`, `show`, `diff`) carry no deadline, having no network to stall on.
  `worktree.remote_ref_sha` — every call of which dials `origin` — now defaults to the same finite
  bound rather than leaving it opt-in, so `just worktree archive`, `just worktree restore` and
  `just review exchange` cannot hang on the same bad afternoon.
- **The escalate suite's hermeticity is enforced rather than incidental (#425).** The tests were
  online-proof only while the chdir'd scratch clone stayed what `Path.cwd()` resolved to; nothing
  pinned that, and a harmless-looking reordering could point a `fetch` at this box's real remote
  and stay green — the scratch origin's policy is byte-identical to the shipped one, so no result
  assertion can tell. Every network-shaped git verb the module drives through `review_loop` now
  names its `origin` first and refuses anything outside the test's own scratch directory, red
  rather than online, and refuses a network-shaped read that has lost its deadline. The refusal
  itself demands an absolute local path: a URL-shaped origin is a *relative* path to `Path`, whose
  resolution prefixed the caller's cwd and passed containment from inside the scratch tree — the
  first review's Medium, the fifth check-this-week that compared a token rather than the thing.
- **The `review-loop` recipe no longer describes the retired `--routing-refusal` contract (#425).**
  It told the caller to pass routing refusals in; since #391 the walk derives them itself, and an
  operational copy describing the old rule is the failure that has sent branches back for an extra
  round. The exchange ref's name also has one spelling again — `review_exchange.review_ref`, not a
  second literal in `review_loop` — and `ROUTING_INPUTS_ERROR` names the failure it quotes rather
  than pointing at a "reason above" that is not there.
