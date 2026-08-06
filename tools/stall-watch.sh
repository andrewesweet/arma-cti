#!/usr/bin/env bash
# The stall watcher's process seam (#198, ADR-0049).
#
# Everything here is the shell being the actual subject: detaching from the
# turn that armed the watch, holding a poll loop nobody is billed for, running
# `git` and `kill -0`, and reading mtimes. Every *decision* — has the run
# finished, is the agent parked, what should the prod say — belongs to
# `tools/stall_watch.py`, which pytest can reach.
#
# The point of the detachment is #195's measurement: an agent turn that blocks
# past five minutes throws away its prompt cache and pays about 179,000 tokens
# to rebuild it, so a waiting turn is ~110x a working one. This loop waits
# instead, at zero tokens, and leaves one line where the next orchestrator turn
# reads it. It never messages the agent — prodding stays a judgement.
#
# Usage:
#   tools/stall-watch.sh arm --name <name> --worktree <path> [options]
#   tools/stall-watch.sh loop --name <name> [--watch-dir <d>] [--interval <s>]
#
# `arm` returns immediately, having forked `loop` into its own session.

set -euo pipefail

SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOL="tools/stall_watch.py"

# Every `uv run` the watcher makes is bounded, like every one the tier makes
# (#144, ADR-0049): a typer that hangs must not become a watcher that hangs.
UV_TIMEOUT="${CTI_WATCH_UV_TIMEOUT:-60}"
# The poll cadence. Sixty seconds against a ten-minute grace is ample
# resolution, and it keeps a four-hour watch to ~240 sub-second invocations.
DEFAULT_INTERVAL=60
# `CTI_WATCH_DIR` is the same seam `tools/stall_watch.py` reads (#249). Both halves
# honour it or neither does: a caller that points the read at another tree and still
# has the arming half write to the real one has moved the leak, not closed it.
DEFAULT_WATCH_DIR="${CTI_WATCH_DIR:-$HOME/.arma-cti/watch}"

die() {
    printf 'stall-watch: %s\n' "$1" >&2
    exit 2
}

# ---------------------------------------------------------------------------
# arm

arm_watch() {
    local name="" worktree="" subject="pool" issue="" await_path="" pid=0
    local grace="" deadline="" runs_dir="" watch_dir="$DEFAULT_WATCH_DIR"
    local interval="$DEFAULT_INTERVAL"
    local -a activity=()

    while (($# > 0)); do
        # Every option takes a value, and a missing one says so: `set -u`
        # would otherwise report it as "$2: unbound variable" from a line
        # number, which is the shape of an error nobody can act on. The
        # commonest way to get here is `--issue #198` inside a `just` recipe,
        # where `#` opens a shell comment and eats the value — hence the hint.
        [[ $# -ge 2 ]] || die "$1 takes a value (an issue is '--issue 198', no '#')"
        case "$1" in
        --name) name="$2" ;;
        --worktree) worktree="$2" ;;
        --subject) subject="$2" ;;
        --issue) issue="$2" ;;
        --await-path) await_path="$2" ;;
        --pid) pid="$2" ;;
        --grace) grace="$2" ;;
        --deadline) deadline="$2" ;;
        --runs-dir) runs_dir="$2" ;;
        --watch-dir) watch_dir="$2" ;;
        --interval) interval="$2" ;;
        --activity) activity+=("$2") ;;
        *) die "unknown option $1" ;;
        esac
        shift 2
    done

    [[ -n "$name" ]] || die "--name is required"
    [[ -n "$worktree" ]] || die "--worktree is required"
    [[ -d "$worktree" ]] || die "no worktree at $worktree"

    # The baseline the stall predicate's third conjunct is measured against.
    # A worktree whose HEAD cannot be read is not a watch worth arming: the
    # predicate would be blind from its first pass.
    local head
    head="$(git -C "$worktree" rev-parse HEAD 2>/dev/null || printf '')"
    [[ -n "$head" ]] || die "cannot read HEAD in $worktree"

    # Default the activity paths to the worktree itself, which is where an
    # agent that is still working leaves mtimes.
    ((${#activity[@]})) || activity=("$worktree")

    local -a arm_args=(
        --name "$name" --worktree "$worktree" --baseline-head "$head"
        --subject "$subject" --issue "$issue" --pid "$pid"
    )
    # `x && y` would return 1 whenever x is false, which `set -e` reads as the
    # script failing — so each optional flag gets its own `if`.
    if [[ -n "$await_path" ]]; then arm_args+=(--await-path "$await_path"); fi
    if [[ -n "$grace" ]]; then arm_args+=(--grace "$grace"); fi
    if [[ -n "$deadline" ]]; then arm_args+=(--deadline "$deadline"); fi
    if [[ -n "$runs_dir" ]]; then arm_args+=(--runs-dir "$runs_dir"); fi

    local out spec=""
    out="$(cd "$REPO" && timeout "$UV_TIMEOUT" uv run --quiet python "$TOOL" \
        --watch-dir "$watch_dir" arm "${arm_args[@]}")" ||
        die "could not write the watch spec"
    while IFS='=' read -r key value; do
        if [[ "$key" == spec ]]; then spec="$value"; fi
    done <<<"$out"
    [[ -n "$spec" ]] || die "the spec writer named no spec file"

    local log="${spec%.spec.json}.log" path
    local -a forward=()
    for path in "${activity[@]}"; do forward+=(--activity "$path"); done

    setsid nohup "$SELF" loop --name "$name" --watch-dir "$watch_dir" \
        --interval "$interval" "${forward[@]}" >>"$log" 2>&1 </dev/null &
    local watcher=$!
    disown "$watcher" 2>/dev/null || true

    printf 'watch=%s\n' "$name"
    printf 'spec=%s\n' "$spec"
    printf 'watcher_pid=%s\n' "$watcher"
    printf 'log=%s\n' "$log"
}

# ---------------------------------------------------------------------------
# loop

# The newest mtime under the activity paths, as whole seconds. `sort` does the
# ranking so the shell does no arithmetic; an empty answer is 0, which the
# predicate reads as "no activity observed" rather than as life.
newest_mtime() {
    local newest
    newest="$(find "$@" -name .git -prune -o -printf '%T@\n' 2>/dev/null |
        sort -rn | head -1 || true)"
    printf '%s' "${newest%%.*}"
}

# The watcher's own failure, written where a finding goes. Fail-closed, the
# same move `regress.sh` makes when its verdict typer dies (ADR-0049): a
# watcher that says nothing is indistinguishable from an agent that is fine.
broken_finding() {
    local finding="$1" name="$2" detail="$3"
    detail="$(printf '%s' "$detail" | tr '\n\t"' '   ' | cut -c1-400)"
    mkdir -p "$(dirname "$finding")"
    cat >"$finding" <<JSON
{
  "name": "$name",
  "state": "watch_broken",
  "terminal": true,
  "headline": "BROKEN $name — the stall watcher's own assessor failed, so this agent is unwatched; look by hand: $detail",
  "prod": "none — the watcher broke, not the agent. Assess by hand before prodding.",
  "acknowledged_at": 0
}
JSON
}

loop_watch() {
    local name="" watch_dir="$DEFAULT_WATCH_DIR" interval="$DEFAULT_INTERVAL"
    local -a activity=()
    while (($# > 0)); do
        [[ $# -ge 2 ]] || die "$1 takes a value"
        case "$1" in
        --name) name="$2" ;;
        --watch-dir) watch_dir="$2" ;;
        --interval) interval="$2" ;;
        --activity) activity+=("$2") ;;
        *) die "unknown option $1" ;;
        esac
        shift 2
    done
    [[ -n "$name" ]] || die "--name is required"

    local worktree="" subject="" pid=0 finding=""
    while IFS='=' read -r key value; do
        case "$key" in
        worktree) worktree="$value" ;;
        subject) subject="$value" ;;
        pid) pid="$value" ;;
        finding) finding="$value" ;;
        esac
    done < <(cd "$REPO" && timeout "$UV_TIMEOUT" uv run --quiet python "$TOOL" \
        --watch-dir "$watch_dir" spec-env --name "$name")
    [[ -n "$worktree" && -n "$finding" ]] || die "no watch named $name"
    ((${#activity[@]})) || activity=("$worktree")

    local porcelain
    porcelain="$(mktemp)"
    # Expanded now, not at exit: the variable is function-local and `set -u`
    # would make the trap itself the loop's last error.
    # shellcheck disable=SC2064
    trap "rm -f '$porcelain'" EXIT

    while :; do
        # `git` refusing is data, not an error: a vanished worktree is one of
        # the recorded death modes (#105), and the assessor types it BLIND.
        local head alive="unknown" seen
        head="$(git -C "$worktree" rev-parse HEAD 2>/dev/null || printf '')"
        # `--untracked-files=all` because the default collapses an untracked
        # directory to one entry, and "5 files uncommitted" is the prod's
        # sharpest fact (#149).
        git -C "$worktree" status --porcelain --untracked-files=all >"$porcelain" \
            2>/dev/null || : >"$porcelain"
        if [[ -n "$pid" && "$pid" != 0 ]]; then
            if kill -0 "$pid" 2>/dev/null; then alive="true"; else alive="false"; fi
        fi
        seen="$(newest_mtime "${activity[@]}")"

        local out
        if ! out="$(cd "$REPO" && timeout "$UV_TIMEOUT" uv run --quiet python "$TOOL" \
            --watch-dir "$watch_dir" assess --name "$name" --head "$head" \
            --porcelain-file "$porcelain" --activity-epoch "${seen:-0}" \
            --process-alive "$alive" 2>&1)"; then
            broken_finding "$finding" "$name" "$out"
            return 0
        fi

        local terminal="false" line=""
        while IFS='=' read -r key value; do
            case "$key" in
            terminal) terminal="$value" ;;
            line) line="$value" ;;
            esac
        done <<<"$out"

        if [[ "$terminal" == "true" ]]; then
            printf '%s\n' "$line"
            return 0
        fi
        sleep "$interval"
    done
}

case "${1:-}" in
arm)
    shift
    arm_watch "$@"
    ;;
loop)
    shift
    loop_watch "$@"
    ;;
*)
    die "usage: stall-watch.sh {arm|loop} [options]"
    ;;
esac
