#!/usr/bin/env bash
# The dispatcher's process seam (#223, ADR-0049).
#
# Everything here is the shell being the actual subject: detaching a dispatch from
# the turn that armed it, and nothing else. Every *decision* — which lane, which
# profile, whether the seat may leave Claude, what the child's environment is, whether
# the worktree matches its assignment — belongs to `tools/dispatch.py`, which pytest
# can reach.
#
# The point of the detachment is CLAUDE.md's five-minute rule and #195's measurement
# behind it: an agent turn that blocks past five minutes throws away its prompt cache
# and pays about 179,000 tokens to rebuild it. So `just dispatch` returns a dispatch id
# at once and the dispatched run outlives the turn.
#
# This script parses no flags of its own. It hands every argument to the planner and
# then reads the planner's own output: a request that produced a `record=` line is a
# dispatch to fork, and one that did not — `--list`, `--dry-run`, or any refusal — is
# already finished. That is the whole of the branch, and it means adding an option to
# the dispatcher never touches this file.
#
#   tools/dispatch.sh --lane claude-native --profile opus-high --seat implementer --issue 223
#   tools/dispatch.sh --list
#   tools/dispatch.sh --dry-run --seat review --reviewing opus-high --issue 223
#
# The review example names no lane or profile because the seat resolves its own, past the
# profile under review; `--reviewing` is required there and a review dispatched without it
# is refused `review_subject_unknown` (#322, ADR-0071 ruling 4).

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOL="tools/dispatch.py"

# Every `uv run` a seam makes is bounded, like every one the tier makes (#144,
# ADR-0049): a planner that hangs must not become a `just dispatch` that hangs.
UV_TIMEOUT="${CTI_DISPATCH_UV_TIMEOUT:-120}"

planned="$(cd "$REPO" && timeout "$UV_TIMEOUT" uv run --quiet python "$TOOL" "$@")" || {
    # The planner already printed its named refusal on stderr; nothing was dispatched
    # and nothing here should paper over that with a second message.
    exit $?
}

record=""
dispatch=""
while IFS='=' read -r key value; do
    case "$key" in
    record) record="$value" ;;
    dispatch) dispatch="$value" ;;
    esac
done <<<"$planned"

printf '%s\n' "$planned"

# No record means the planner answered the question itself: `--list`, `--dry-run`.
[[ -n "$record" ]] || exit 0

log="$record/dispatch.log"
cd "$REPO"
completion_pipe="$record/runner.pipe"
mkfifo "$completion_pipe"
exec {completion_fd}<>"$completion_pipe"
setsid nohup uv run --quiet python "$TOOL" --run "$record" >>"$log" 2>&1 </dev/null &
child=$!
exec {completion_fd}>&-
disown "$child" 2>/dev/null || true

# Record the exact runner identity and paths before returning. The helper
# owns the JSON decision under pytest; this shell retains only the process seam.
timeout "$UV_TIMEOUT" uv run --quiet python tools/dispatch_follow.py --arm-record "$record" --launcher-pid "$child" --runner-pipe "$completion_pipe"

# No `pid=` line, deliberately, and this is the one place the omission has to be
# explained (#308, from #105's sixth instance). `$child` is the *launcher* — the
# `uv run … --run` process this script forks. The session it starts is a
# grandchild that reparents, so killing `$child` and seeing `ps -p` come back
# empty reads exactly like success while a `claude --print` carries on working;
# that is what put two agents in one worktree for half an hour. A published pid
# that does not identify the work invites that check, so it is not published.
# The launcher pid stays on the record under the name it deserves, and the handle
# that does identify a dispatch's processes — its worktree — is what `--stop`
# resolves to.
printf 'log=%s\n' "$log"
printf 'dispatched=%s\n' "$dispatch"
printf 'stop=just dispatch --stop %s\n' "$dispatch"
