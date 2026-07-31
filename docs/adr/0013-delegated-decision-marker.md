# Delegated decisions carry a greppable marker, indexed only in docs/adr/

Delegated-decision: yes
Date: 2026-07-31
Stood-in-for: human sign-off on process-doc changes (the marker's exact form; the authorisation itself is the human's)

On 2026-07-31 the human granted standing authorisation: agents may decide in their stead where CLAUDE.md would otherwise require sign-off, provided every such decision is recorded in an ADR and is straightforwardly findable when they ask "tell me all decisions made on my behalf".

Convention: an ADR recording such a decision carries, immediately under its title, a three-line field block —

```
Delegated-decision: yes
Date: <ISO date the decision was taken>
Stood-in-for: <the CLAUDE.md gate it discharged, plus the issue or context>
```

`docs/adr/` is the single index. `grep -rl "^Delegated-decision: yes" docs/adr/` returns the complete set; no other file, label, or log is authoritative for it. A decision taken under the authorisation but not recorded this way is out of policy, and the fix is to write the missing ADR, not to widen the index.
