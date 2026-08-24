### Fixed

- **A damaged `result.json` no longer reads as "the run has not ended" (#569).** The ledger's
  `read_json` returned `None` for three different conditions — the file is absent, it is
  damaged, or it parses to something that is not an object — and the end-state typing spent
  that `None` on one sentence: "the run has not ended: no result.json beside the plan". A
  corrupt record reached that sentence, telling a reader the run was live when the record of
  how it ended was merely unreadable; a JSON list beside the plan was furthest from "no
  result.json" of all. `read_json` now names which of the three conditions a `None` is, the
  typing renders `unknown` with a reason that names the damage or the shape, and the
  observatory's end, end-state and terminal readers draw the same reason from the same home.
  The state class never changed — it was already `unknown` — and an absent `result.json`
  keeps the sentence absence earned, byte for byte, so no existing row churns. The bare
  `except` stays: a record is untrusted input, and narrowing it would turn a damaged file
  into a crash.
