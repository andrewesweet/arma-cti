## Fixed

- The mutation gate scored a mutant-caused collection error by matching an
  `ERROR collecting` banner for the module in the judged run's stdout — a token
  in a stream that also carries the captured output of the tests themselves,
  which in this repository can run pytest inside pytest and quote a banner
  naming the module from a run that is not the judged one. The kill now comes
  from a dedicated `--collect-only` run of the module, whose exit code is about
  collecting that module and nothing else; an odd exit code the collect-only
  question cannot confirm still refuses loudly rather than scoring.
