#!/usr/bin/env bash
# The quota tap: refresh Claude's binding limit, spool the status-line payload,
# then hand it on unchanged (#261, #230, for #226's quota feed).
#
# Claude Code renders the status line by piping a JSON payload — which carries
# the session's token and cost totals — into one command. That payload is the
# fallback quota state. This script also asks `/api/oauth/usage` for its active
# `limits[]` entry in a detached, single-flight refresh. The endpoint can rate
# limit its reader; tools/breaker.py persists `retry-after` as the next boundary
# and will not ask again before it. This script sits *ahead* of whatever command
# was already configured, appends the payload to a spool file, and runs the
# original command with the same payload on its stdin.
#
# Two properties are load-bearing, and both are why this is bash rather than
# Python (ADR-0049: the shell is the actual subject here — stdin, a pipe, and an
# exec):
#
#   1. **stdout is never touched.** The downstream command's output is this
#      script's output, byte for byte. Nothing is prepended, appended or
#      filtered. The human's existing status line survives verbatim.
#   2. **The tap fails open.** `set -e` is deliberately *not* on. A spool
#      directory that cannot be created, a full disk, a read-only home — none of
#      those may take the human's status line down with them. A tap that stops
#      spooling degrades #226's breaker to reacting to 429s, which is a
#      documented weakness (see `just prereqs statusline`), not an outage.
#
# Usage:  quota_tap.sh [DOWNSTREAM_COMMAND]
#
# DOWNSTREAM_COMMAND is one argument, run with `bash -c`. `just prereqs
# statusline` builds it by shell-quoting whatever was in `~/.claude/settings.json`
# before, so the original command reaches `bash -c` exactly as it was written.
# With no argument the tap spools and prints nothing, which is what an unset
# status line looked like anyway.
#
# Environment:
#   CTI_QUOTA_SPOOL   spool file (default ~/.arma-cti/quota/statusline.jsonl)
#   CTI_QUOTA_MAX     roll the spool over at this size in bytes (default 8388608)
#   CTI_QUOTA_OAUTH   set to 0 to disable the endpoint refresh (default 1)

set -uo pipefail

spool="${CTI_QUOTA_SPOOL:-${HOME}/.arma-cti/quota/statusline.jsonl}"
max_bytes="${CTI_QUOTA_MAX:-8388608}"
downstream="${1-}"
oauth="${CTI_QUOTA_OAUTH:-1}"

# Read the payload once. Claude Code sends one JSON object; `$(cat)` strips the
# trailing newline, and the spool line and the downstream copy each get one back.
payload="$(cat)"

# Spool, fail-open: every step is guarded and the whole block is `|| true`, so a
# tap that cannot write is a tap that stayed out of the way.
{
    if mkdir -p -- "$(dirname -- "${spool}")" 2>/dev/null; then
        # Single rollover rather than unbounded growth: the status line re-renders
        # on every conversation update, and this file lives in the human's home.
        # #226 owns retention; this only stops the tap being a disk-filler.
        size="$(stat -c %s -- "${spool}" 2>/dev/null || echo 0)"
        if [[ "${size}" -gt "${max_bytes}" ]]; then
            mv -f -- "${spool}" "${spool}.1" 2>/dev/null || true
        fi
        printf '%s\n' "${payload}" >>"${spool}" 2>/dev/null || true
    fi
} || true

# Refresh in the background so a slow endpoint can never delay the human's
# status line. `flock -n` makes renders single-flight; the Python reader owns
# every decision, including the provider-published retry boundary.
if [[ "${oauth}" != "0" ]]; then
    breaker="${CTI_QUOTA_BREAKER:-$(dirname -- "$0")/breaker.py}"
    python="${CTI_QUOTA_PYTHON:-python3}"
    breaker_dir="${CTI_BREAKER_DIR:-${HOME}/.arma-cti/breaker}"
    lock="${CTI_QUOTA_LOCK:-${HOME}/.arma-cti/quota/oauth.lock}"
    if mkdir -p -- "$(dirname -- "${lock}")" 2>/dev/null; then
        (
            printf '%s\n' "${payload}" | flock -n -- "${lock}" \
                "${python}" "${breaker}" --breaker-dir "${breaker_dir}" \
                tap --lane claude-native --oauth-usage
        ) >/dev/null 2>&1 &
    fi
fi

if [[ -z "${downstream}" ]]; then
    exit 0
fi

# The original command, with the original payload on stdin and nothing between
# its stdout and ours.
printf '%s\n' "${payload}" | bash -c "${downstream}"
