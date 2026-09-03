# Fixed

- A Work Run concluded terminal by recovery now releases its Work Item scheduling slot whatever `failure_class` its delivery carried; a class outside `NON_RESULT_CLASSES` (for example `assertion_failed`) survived recovery's preserve-existing branch and held the slot permanently (#690). Queue-holder matching now asks the same liveness rule as capacity accounting, so a live run behind an unrecognised state no longer gains a duplicate synthetic run.
