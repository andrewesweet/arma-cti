## Fixed

- Post-landing review dispatch now restores a landed commit when `just land` recorded a
  clean rebase from the exchange ref and the exact diff identity is unchanged; a moved
  review ref without that proof, or with an altered diff, still refuses until it is
  re-exchanged (#657).
- Dispatch plan-file recovery now timestamps its child window with Linux's filesystem-
  compatible realtime clock, so a child-created plan is not omitted at the window's
  lower boundary because the precise clock is briefly ahead.
