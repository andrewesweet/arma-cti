## Fixed

- Post-landing review dispatch now restores a landed commit when `just land` recorded a
  clean rebase from the exchange ref and the exact diff identity is unchanged; a moved
  review ref without that proof, or with an altered diff, still refuses until it is
  re-exchanged (#657).
