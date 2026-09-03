# Fixed

A `just brief` flake line now quotes the selector a quarantine marker actually names:
the one live marker had inherited the issue title's module-level name instead of its
test's exact node ID, and round five's marker-wins merge then re-rendered the fiction
round one rendered. A wrong marker is now impossible to land: a unit check walks every
committed `quarantined:` marker and refuses one whose node ID names no test collected
from its own file, or whose module is not that file. Marker node IDs are read by one
shared parser beside the `NODE_ID` grammar, shared with the open-issue body scan.
