## Added

- A landing that introduces a `tools/`, `src/` or `.claude/hooks/` Python module
  no test module measures is now a red rather than a silence (#370). `just
  mutation` selected the *test* modules a diff adds or rewrites, so a diff that
  added `tools/x.py` with no `tests/unit/test_x.py` selected nothing at all: no
  subject, no verdict, no floor, and every rung of `just fast` green on a module
  the gate had never looked at. Three instances landed that way in one cycle
  (#324, #338, #346). The gate now reads the diff a second way: every product
  module a landing introduces — added, or renamed to a name that was not at the
  base — must come out of the run as a verdict's subject, and one that no
  verdict selected is a red carrying the class `no_test_module`, naming both the
  test module to write and the escape. The check is bound to what the run
  measured rather than to filenames, because a `test_new_cases.py` that
  exercises only existing code clears any filename check while its mutants go
  elsewhere. It asks only about introductions, never edits: eleven of this
  tree's modules are tested under a name that does not reach them, so asking the
  same of an edit would red a docstring fix. The escape is `NO_TEST_MODULE`,
  ADR-0064's named-list shape with its reason beside it, shipping empty — and a
  blank reason on an entry of either escape list now refuses the gate outright,
  because an escape whose reason can be left blank is an escape with its cost
  removed.
