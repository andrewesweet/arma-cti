# Fixed

`just brief` now derives flake lines from the committed `quarantined: #N <node id>` markers under `tests/` as well as from open issues, so a quarantine still cites its issue after `just land` closes it. A marker read wins over the open-issue scan for the same issue number, and a marker carrying no node ID stays prose and is unread.
