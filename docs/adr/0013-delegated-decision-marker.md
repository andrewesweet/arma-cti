# Delegated decisions carry a greppable marker, indexed only in docs/adr/

Delegated-decision: yes
Date: 2026-07-31
Stood-in-for: human sign-off on process-doc changes (the marker's exact form; the authorisation itself is the human's)
Reviewed-by-human: pending

On 2026-07-31 the human granted standing authorisation: agents may decide in their stead where CLAUDE.md would otherwise require sign-off, provided every such decision is recorded in an ADR and is straightforwardly findable when they ask "tell me all decisions made on my behalf".

Convention (amended by ADR-0019): an ADR recording such a decision carries, immediately under its title, a four-line field block —

```
Delegated-decision: yes
Date: <ISO date the decision was taken>
Stood-in-for: <the CLAUDE.md gate it discharged, plus the issue or context>
Reviewed-by-human: <pending, until the human replaces it with the review date — never an agent>
```

— and states, in its body, what evidence would overturn each decision it takes (ADR-0019: that statement is what makes a ratification auditable rather than self-sealing).

A decision the human takes directly may be recorded in the same index by an agent
scribe (added by ADR-0042, after 0039–0041 improvised the form identically): it
carries `Delegated-decision: no`, optionally with the reason on the same line, and a
`Reviewed-by-human:` line naming the in-session decision instead of `pending`. The
`yes` grep below remains the complete delegation set; the `no` form exists so the
human's own decisions sit findably beside it rather than outside the scheme.

`docs/adr/` is the single index. `grep -rl "^Delegated-decision: yes" docs/adr/` returns the complete set, and `grep -rl "^Reviewed-by-human: pending" docs/adr/` the human's outstanding-review worklist; no other file, label, or log is authoritative for either. A decision taken under the authorisation but not recorded this way is out of policy, and the fix is to write the missing ADR, not to widen the index.
