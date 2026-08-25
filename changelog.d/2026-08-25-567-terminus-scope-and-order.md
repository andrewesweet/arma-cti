### Fixed

- **Three queue-report readings from #556's review (#567).** A damaged `loop.json`'s
  `review_terminus=unreadable` line said `repair review state before relying on closeout prompt` —
  the whole-root wording, which distrusts every prompt beside it; it now says
  `repair this loop before relying on its closeout prompt`, scoping the distrust to the loop the
  path names while the readable `due` and `blocked` prompts stand. The human-ruling read is now
  fail-open end to end: `sample()` computes it above its per-queue catch, so an exception escaping
  the walk's own `(OSError, ValueError)` ladder used to abort the whole sampler before any queue
  was journalled, despite the docstring's every-queue promise — it now renders that one queue
  unreadable and the terminus absent. And terminus prompts render in numeric issue order rather than lexicographic directory
  order, which put issue 1000 before issue 999.
