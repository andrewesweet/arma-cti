### Changed

- **A same-dispatch observation can no longer rebind a recorded Work Run's Work Item,
  issue or worktree in the System-of-Work controller (#630).** The merge's branches
  disagreed: some preferred the fresh observation's binding whenever it was present,
  others retained the recorded one, so delivery evidence could silently re-point a
  run at another item. The controller's recorded
  binding is now authoritative: the prior value is retained, an observation fills only
  a field the record left empty, and a present-and-differing value is recorded as a
  delivery conflict rather than adopted.
