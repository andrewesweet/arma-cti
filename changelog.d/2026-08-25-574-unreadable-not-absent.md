### Fixed

- **`just observatory` reports a committed projection that exists but cannot be read as
  `previous=unreadable` instead of `previous=absent` (#574).** The regeneration read the
  previous projection under `except OSError`, so a permissions or I/O failure on an
  existing file took the same branch as no file at all: the row-change record claimed
  `previous=absent removed=0`, and removals went uncounted behind a false absence.
  `FileNotFoundError` alone now means absent; any other `OSError` lets the regeneration
  complete and qualifies its counts under `previous=unreadable`, and a projection whose
  bytes are not valid UTF-8 still fails loudly before the rebuild runs. The landing also
  pins the narrowing pattern's `(?<![\w#])` lookbehind with a swapped-roles collision
  test — a message admitted for #555 through its possessive cannot land #555 through a
  `prose#555` token — whose failure the guard's removal now causes.
