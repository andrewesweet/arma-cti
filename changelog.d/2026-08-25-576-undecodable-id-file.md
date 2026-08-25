### Fixed

- **An id file holding invalid UTF-8 no longer crashes the gate-clock recorder (#576
  round 3).** `read_failed_file` caught only `OSError`, so a `UnicodeDecodeError` escaped
  after the leg's run and before its record — losing the whole row the recorder exists to
  keep. An undecodable file is now the same "could not tell" as a missing one: the leg
  records with no `failed_tests` key, and the gate's own outcome is untouched.
