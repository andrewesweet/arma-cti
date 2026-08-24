## Added

- Every landing the review rung clears now records one `cti.landing.reviewed`
  event in a per-issue landings journal beside the stage journal, naming the
  objects it touched and the role each played: the issue as `subject`, the landed
  commit as `produced`, every profile the records place on the work as `author`,
  and the reviewing dispatch as `reviewer` (#491) — an exempted clearance, which
  consults no record, journals the subject and the commit alone and is named
  uncheckable by the rebuild rather than read as clear. An author a dispatch record
  placed relates as a `dispatch` object; one an interactive session declared
  (#398) relates as an `authorship_declaration` whose id is the profile — so the
  declared-author and dispatched-author shapes are both inside a check a record
  can run, and a profile that both dispatched and declared keeps its dispatch
  relation. Qualifiers and object types each come from one closed set in
  `tools/attribute_registry.py`, as does the four-value gate-review cause
  vocabulary, whose spellings the landing's printed `gate_review=` lines now
  derive from rather than duplicate. A gate landing's event carries the cause its
  verdict rode, because two of the four causes rest on lane bars read live at
  landing time. Recording is fail-open and deduplicated on the produced commit,
  and a historical journal line without relation attributes parses with an empty
  relation set.
- The observatory store gains `landings` and `landing_relations` tables — one row
  per distinct landing, one per object its event touched — so the never-alone
  rule is checked by a query over the record (the cookbook carries it) rather
  than by reading the `gate_review=` line a landing prints about itself, and one
  landing touching several objects counts once as a landing and once per object
  as relations, never once per object as landings. The rebuild names any journalled
  landing whose relation set carries no author in `landings_without_authors`,
  because that landing cannot be checked and a stated gap is never a silent
  clearance. The store schema moves to `cti.observatory/7`.
