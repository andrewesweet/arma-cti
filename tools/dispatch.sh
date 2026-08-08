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
#   tools/dispatch.sh --dry-run --lane zai --profile zai-glm52-max --seat review --issue 223

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
timeout "$UV_TIMEOUT" uv run --quiet python tools/dispatch_follow.py --arm-record "$record" --runner-pid "$child" --runner-pipe "$completion_pipe"

printf 'pid=%s\n' "$child"
printf 'log=%s\n' "$log"
printf 'dispatched=%s\n' "$dispatch"
