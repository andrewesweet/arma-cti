"""`just prereqs` — the multi-provider setup that does not need a human (#230).

#229 was written as a fifteen-item human checklist. Six items genuinely need a
human — hold two subscriptions, paste one key, run one root script, rule on two
sets of terms, sign off two issues. The rest were mislabelled, and this is the
rest: setup performed by an agent reading a checklist is setup that will be done
differently next time (#195, seed idea 3).

Six actions, each its own subcommand:

- ``check``       every item's true state, one line each. A check that could not
                  run reports ``unknown`` and is never a pass (#41's shape).
- ``credentials`` create ``~/.arma-cti/credentials.env`` at 0600, outside every
                  worktree, and take the key the human pastes. The value never
                  reaches argv, stdout, a log or a committed file.
- ``sudo-script`` *generate* the one root script this initiative needs, and print
                  its path. It is never run from here.
- ``statusline``  chain #226's quota tap ahead of the existing status line in
                  ``~/.claude/settings.json``, passing its output through unchanged.
- ``tools``       install ``gitleaks`` user-local, and write the Codex config that
                  disables its off-box metrics exporter *before first use*.
- ``plan-tier``   read the z.ai plan tier if anything on this box records it, and
                  otherwise say plainly that it could not be read.

Per ADR-0049 the decisions live here under pytest; the shell keeps only the
seams it owns (``tools/quota_tap.sh``, and the generated root script, which is a
document for a human to read rather than code this repo runs).

Output is the tier's ``key=value`` line format. Exit 0 is done, 1 is a named
refusal or a missing prerequisite, 3 is "I could not look" — never a silent pass.
"""

from __future__ import annotations

import argparse
import contextlib
import getpass
import grp
import hashlib
import json
import os
import pwd
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, NamedTuple, NoReturn

EXIT_OK: Final = 0
EXIT_REFUSED: Final = 1
EXIT_COULD_NOT_LOOK: Final = 3

COULD_NOT_RUN: Final = "A check that could not run is not a check that passed."

PRIVATE_MODE: Final = 0o600
PRIVATE_DIR_MODE: Final = 0o700
QUOTED_TOKEN_MIN: Final = 2
CHECKSUM_FIELDS: Final = 2
ASCII_CONTROL_CEILING: Final = 0x20
ASCII_DELETE: Final = 0x7F

# Where every generated and recorded artefact lives, outside every worktree.
STATE_DIR_NAME: Final = ".arma-cti"
LEDGER_DIR: Final = Path("/var/log/claude-otel/dispatches")
COLLECTOR_CONFIG: Final = Path("/etc/otelcol-contrib/config.yaml")
COLLECTOR_SERVICE: Final = "otelcol-contrib"
COLLECTOR_USER: Final = "otelcol-contrib"

ZAI_KEY_NAME: Final = "ZAI_API_KEY"
TAP_BASENAME: Final = "quota_tap.sh"

# The GLM Coding Plan's published caps: prompts per five-hour window and per
# seven days, per tier. Off-peak usage is charged at 50%; peak is Mon-Fri
# 14:00-18:00 SGT. Primary source read, https://docs.z.ai/devpack/overview, via
# docs/research/multi-provider-routing-substrates.md. #226's estimator needs
# these numbers and there is no machine-readable source for which tier is held.
ZAI_TIERS: Final = {
    "lite": (2_000, 10_000),
    "pro": (12_000, 60_000),
    "max": (28_000, 140_000),
}


class Report(NamedTuple):
    """What one action decided, and what it exits."""

    lines: tuple[str, ...]
    code: int

    @staticmethod
    def refused(
        reason: str,
        detail: tuple[str, ...],
        action: str,
        code: int = EXIT_REFUSED,
    ) -> Report:
        """Build a named refusal: what was found, and what to do about it."""
        return Report((f"refused={reason}", *detail, f"action={action}"), code)


class Layout(NamedTuple):
    """Every path an action touches, so a test can put them all in a tmp_path."""

    state_dir: Path
    credentials: Path
    plan_tier: Path
    generated_dir: Path
    quota_spool: Path
    settings: Path
    collector_config: Path
    ledger_dir: Path
    codex_config: Path
    local_bin: Path
    repo: Path

    @staticmethod
    def under(home: Path, repo: Path) -> Layout:
        """Build the real layout, or a whole fake one rooted at a temporary home."""
        state = home / STATE_DIR_NAME
        codex_home = Path(os.environ.get("CODEX_HOME") or (home / ".codex"))
        return Layout(
            state_dir=state,
            credentials=state / "credentials.env",
            plan_tier=state / "plan-tier.json",
            generated_dir=state / "prereqs",
            quota_spool=state / "quota" / "statusline.jsonl",
            settings=home / ".claude" / "settings.json",
            collector_config=COLLECTOR_CONFIG,
            ledger_dir=LEDGER_DIR,
            codex_config=codex_home / "config.toml",
            local_bin=home / ".local" / "bin",
            repo=repo,
        )

    @property
    def tap(self) -> Path:
        """Locate the quota tap in the main checkout — worktrees come and go."""
        return self.repo / "tools" / TAP_BASENAME


class StepRefusedError(Exception):
    """A step refused, carrying the report the caller should return."""

    def __init__(self, report: Report) -> None:
        """Carry the whole report, so no caller re-invents the refusal's name."""
        super().__init__(report.lines[0])
        self.report = report


def raise_refusal(
    reason: str,
    detail: tuple[str, ...],
    action: str,
    code: int = EXIT_REFUSED,
    cause: BaseException | None = None,
) -> NoReturn:
    """Stop a ladder with a named refusal, carrying the report the caller returns."""
    refusal = StepRefusedError(Report.refused(reason, detail, action, code))
    if cause is not None:
        raise refusal from cause
    raise refusal


# --------------------------------------------------------------- collector config

# The three blocks the collector gains, exactly the shape that validated and ran
# on 0.157.0 in docs/research/agent-observability-and-cost-ledgers.md. Additive
# only: nothing existing is edited, so the diagnostics skill's rotating capture
# at /var/log/claude-otel/claude-telemetry.jsonl is untouched.

FILTER_BLOCK: Final = """\
  # NEW (#227, ADR-0061 durability). Used only by the ledger pipelines below.
  #
  # filterprocessor conditions are DROP-if-true and ORed together, so "keep only
  # cti-tagged records" is written INVERTED, as "drop everything whose resource
  # block has no cti.dispatch_id". Getting this backwards silently exports the
  # complement of what was wanted and no gate would catch it.
  filter/cti:
    error_mode: ignore
    log_conditions:
      - resource.attributes["cti.dispatch_id"] == nil
    metric_conditions:
      - resource.attributes["cti.dispatch_id"] == nil
    trace_conditions:
      - resource.attributes["cti.dispatch_id"] == nil
"""

EXPORTER_BLOCK: Final = """\
  # NEW (#227). Non-rotating — note there is no `rotation:` key at all, because a
  # bare one enables rotation at defaults — append-only so the record survives a
  # collector restart, and split one file per dispatch through the `*` wildcard.
  file/ledger:
    path: {ledger_dir}/dispatch-*.jsonl
    format: json
    append: true
    flush_interval: 1s
    create_directory: true
    group_by:
      enabled: true
      resource_attribute: cti.dispatch_id
      max_open_files: 20
"""

# Each new pipeline, keyed by the line that proves it is already there.
PIPELINE_BLOCKS: Final = (
    (
        "    traces:",
        """\
    # NEW (#227). The OTLP receiver accepts a signal only where a pipeline
    # consumes it, and opencode carries its token counts as spans and nothing
    # else — so without this leg that lane's spend is invisible. Unfiltered,
    # mirroring the existing metrics and logs legs.
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [file/claude]
""",
    ),
    (
        "    metrics/ledger:",
        """\
    metrics/ledger:
      receivers: [otlp]
      processors: [filter/cti, batch]
      exporters: [file/ledger]
""",
    ),
    (
        "    logs/ledger:",
        """\
    logs/ledger:
      receivers: [otlp]
      processors: [filter/cti, batch]
      exporters: [file/ledger]
""",
    ),
    (
        "    traces/ledger:",
        """\
    traces/ledger:
      receivers: [otlp]
      processors: [filter/cti, batch]
      exporters: [file/ledger]
""",
    ),
)


class MergeRefusedError(Exception):
    """The document is not the shape this merge knows how to extend."""

    def __init__(self, reason: str, detail: str) -> None:
        """Carry the refusal's own name, so the caller does not invent one."""
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


def raise_unrecognised(reason: str, detail: str) -> NoReturn:
    """Stop a merge that cannot find its anchor, by that refusal's own name."""
    refusal = MergeRefusedError(reason, detail)
    raise refusal


class MergeResult(NamedTuple):
    """The config as it should be on disk, and what this merge added to get there."""

    text: str
    added: tuple[str, ...]


def _block_bounds(lines: list[str], header: str, indent: int) -> tuple[int, int] | None:
    """Find ``header`` at ``indent``, and one past the last line of its body.

    The body ends at the first following non-blank line indented no further than
    the header — which means a comment at the header's own indentation ends the
    block, and so stays attached to whatever it introduces rather than being
    swallowed by the block above it.
    """
    want = " " * indent + header
    start = next((i for i, line in enumerate(lines) if line.rstrip() == want), None)
    if start is None:
        return None
    for i in range(start + 1, len(lines)):
        if not lines[i].strip():
            continue
        if len(lines[i]) - len(lines[i].lstrip()) <= indent:
            return start, i
    return start, len(lines)


def _insert_point(lines: list[str], end: int) -> int:
    """Walk ``end`` back over trailing blank lines, so the gap stays a gap."""
    point = end
    while point > 0 and not lines[point - 1].strip():
        point -= 1
    return point


def _add_section_block(lines: list[str], section: str, block: str) -> None:
    """Append ``block`` to the end of a top-level ``section``'s body."""
    bounds = _block_bounds(lines, section, 0)
    if bounds is None:
        raise_unrecognised(
            "collector_config_unrecognised",
            f"no `{section.rstrip(':')}` section at the top level of the config",
        )
    point = _insert_point(lines, bounds[1])
    lines[point:point] = block.splitlines()


def _add_pipeline(lines: list[str], block: str) -> None:
    """Append one pipeline to the end of ``service.pipelines``."""
    service = _block_bounds(lines, "service:", 0)
    if service is None:
        raise_unrecognised("collector_config_unrecognised", "no `service` section in the config")
    pipelines = _block_bounds(lines[service[0] : service[1]], "pipelines:", 2)
    if pipelines is None:
        raise_unrecognised("collector_config_unrecognised", "no `pipelines` block under `service`")
    point = _insert_point(lines, service[0] + pipelines[1])
    lines[point:point] = block.splitlines()


def merge_collector_config(current: str, ledger_dir: Path = LEDGER_DIR) -> MergeResult:
    """Add the ledger filter, exporter and pipelines to a collector config.

    Idempotent per block: each is added only if its key is absent, so a config
    that already carries some of them converges rather than duplicating. Raises
    `MergeRefusedError` rather than guessing when a section it needs is not
    there — a merge that cannot find its anchor is not a merge that succeeded.
    """
    lines = current.splitlines()
    added: list[str] = []

    if "filter/cti:" not in current:
        _add_section_block(lines, "processors:", FILTER_BLOCK)
        added.append("processors.filter/cti")
    if "file/ledger:" not in current:
        _add_section_block(lines, "exporters:", EXPORTER_BLOCK.format(ledger_dir=ledger_dir))
        added.append("exporters.file/ledger")
    for marker, block in PIPELINE_BLOCKS:
        if any(line.rstrip() == marker for line in lines):
            continue
        _add_pipeline(lines, block)
        added.append(f"service.pipelines.{marker.strip().rstrip(':')}")

    return MergeResult("\n".join(lines) + "\n", tuple(added))


# ------------------------------------------------------------------- sudo script


def render_sudo_script(
    *,
    current_config: str,
    desired_config: str,
    layout: Layout,
    reader_user: str,
    generated_at: str,
) -> str:
    """Render the one root script this initiative needs, written to be read.

    Three root acts in one reviewable file: the collector config change, the
    restart, and the durable export directory. It refuses to run unless the
    config on disk is byte-identical to the one this generation was computed
    from, which is what makes "generated to be read, not trusted" mechanical
    rather than a hope — a config that moved since generation stops the script
    instead of being overwritten from a stale premise.
    """
    expected = hashlib.sha256(current_config.encode()).hexdigest()
    desired = hashlib.sha256(desired_config.encode()).hexdigest()
    return f"""\
#!/usr/bin/env bash
#
# GENERATED by `just prereqs sudo-script` at {generated_at}.
# DO NOT EDIT — regenerate. Read it before you run it; it is generated to be
# read, not trusted.
#
# This is the only sudo in the multi-provider dispatch initiative (#221, #229).
# It performs exactly three root acts and nothing else:
#
#   1. Rewrites {layout.collector_config} to add a `traces`
#      pipeline and a filtered, non-rotating, per-dispatch export of records
#      carrying `cti.*` resource attributes (ADR-0061, durability). The existing
#      metrics and logs pipelines and the rotating capture the WSL diagnostics
#      skill reads are NOT edited — every change is additive, and the whole file
#      as it will be on disk is in the heredoc below, so there is nothing to
#      infer about what changes.
#   2. Restarts {COLLECTOR_SERVICE}, and only if step 1 changed anything.
#   3. Creates {layout.ledger_dir}, writable by the
#      collector's user `{COLLECTOR_USER}` and readable by `{reader_user}`.
#
# It does NOT: install packages, fetch anything from the network, touch any
# other unit, create users, or write outside the two paths named above.
#
# Safety properties, all checkable by reading:
#   * It refuses unless the config on disk is byte-identical to the one this
#     script was generated from (EXPECTED_SHA256). If it has changed since, the
#     script stops and asks you to regenerate rather than overwriting from a
#     stale premise.
#   * It is idempotent. Run twice and the second run changes nothing and
#     restarts nothing.
#   * It backs the config up before writing, to a timestamped file beside it.
#   * It runs `{COLLECTOR_SERVICE} validate` before restarting, and restores the
#     backup if validation fails. A validate that could not run is not a
#     validate that passed, so a missing binary stops the script (#41's shape).
#
# Run it with:   sudo bash {layout.generated_dir}/install-telemetry-root.sh

set -euo pipefail

CONFIG={shlex.quote(str(layout.collector_config))}
LEDGER_DIR={shlex.quote(str(layout.ledger_dir))}
SERVICE={shlex.quote(COLLECTOR_SERVICE)}
COLLECTOR_USER={shlex.quote(COLLECTOR_USER)}
READER_GROUP={shlex.quote(reader_user)}
EXPECTED_SHA256={expected}
DESIRED_SHA256={desired}

if [[ ${{EUID}} -ne 0 ]]; then
    echo "refused=not_root  This script must run as root: sudo bash $0" >&2
    exit 1
fi

changed=0

# ---------------------------------------------------------------- 1. the config

if [[ ! -f "${{CONFIG}}" ]]; then
    echo "refused=no_collector_config  ${{CONFIG}} does not exist." >&2
    exit 1
fi

current="$(sha256sum -- "${{CONFIG}}" | cut -d' ' -f1)"

if [[ "${{current}}" == "${{DESIRED_SHA256}}" ]]; then
    echo "ok=config_already_installed"
elif [[ "${{current}}" != "${{EXPECTED_SHA256}}" ]]; then
    echo "refused=collector_config_moved" >&2
    echo "  ${{CONFIG}} is neither what this script was generated from" >&2
    echo "  (${{EXPECTED_SHA256}}) nor what it would write" >&2
    echo "  (${{DESIRED_SHA256}}). It has changed since generation." >&2
    echo "  Nothing has been written." >&2
    echo "  action=Re-run 'just prereqs sudo-script' and read the new script." >&2
    exit 1
else
    backup="${{CONFIG}}.bak-$(date -u +%Y%m%dT%H%M%SZ)"
    cp -a -- "${{CONFIG}}" "${{backup}}"
    echo "ok=config_backed_up backup=${{backup}}"

    cat >"${{CONFIG}}" <<'CTI_COLLECTOR_CONFIG_EOF'
{desired_config.rstrip()}
CTI_COLLECTOR_CONFIG_EOF
    chown root:root -- "${{CONFIG}}"
    chmod 644 -- "${{CONFIG}}"

    if ! command -v "${{SERVICE}}" >/dev/null 2>&1; then
        cp -a -- "${{backup}}" "${{CONFIG}}"
        echo "refused=cannot_validate  ${{SERVICE}} is not on root's PATH, so the" >&2
        echo "  new config could not be validated. The backup has been restored" >&2
        echo "  and nothing was restarted. A check that could not run is not a" >&2
        echo "  check that passed." >&2
        exit 1
    fi
    if ! "${{SERVICE}}" validate --config="file:${{CONFIG}}"; then
        cp -a -- "${{backup}}" "${{CONFIG}}"
        echo "refused=invalid_config  The generated config failed validation." >&2
        echo "  The backup has been restored and nothing was restarted." >&2
        exit 1
    fi
    echo "ok=config_written sha256=${{DESIRED_SHA256}}"
    changed=1
fi

# ------------------------------------------------------- 2. the export directory

# `install -d` is idempotent and sets owner, group and mode in one act. The
# setgid bit is what makes the collector's own output group-readable by
# ${{READER_GROUP}} without the collector knowing anything about it.
install -d -o "${{COLLECTOR_USER}}" -g "${{READER_GROUP}}" -m 2750 -- "${{LEDGER_DIR}}"
echo "ok=ledger_dir owner=${{COLLECTOR_USER}} group=${{READER_GROUP}} path=${{LEDGER_DIR}}"

# ------------------------------------------------------------------ 3. the unit

if [[ "${{changed}}" -eq 1 ]]; then
    systemctl restart "${{SERVICE}}"
    sleep 1
    if systemctl is-active --quiet "${{SERVICE}}"; then
        echo "ok=restarted service=${{SERVICE}}"
    else
        echo "refused=service_not_active  ${{SERVICE}} did not come back up." >&2
        echo "  action=journalctl -u ${{SERVICE}} -n 50 --no-pager" >&2
        exit 1
    fi
else
    echo "ok=no_restart_needed"
fi

echo "ok=done"
"""


# ------------------------------------------------------------------- credentials

CREDENTIALS_HEADER: Final = (
    "# arma-cti lane credentials — written by `just prereqs credentials` (#221,",
    "# ADR-0061's secrets ruling). Mode 0600, outside every worktree.",
    "#",
    "# Sourced per invocation and never globally:",
    "#     set -a; . ~/.arma-cti/credentials.env; set +a",
    "#",
    "# Keys reach a child process by environment, never on argv. Stated limit: this",
    "# protects against git, not against an agent, which runs as the same user.",
    "#",
    "# Edit through the recipe rather than by hand — the recipe is what keeps the",
    "# mode and refuses to overwrite a key by accident.",
)


def quote_env_value(value: str) -> str:
    """Quote a value in always-single-quoted form, so none can be re-read as syntax."""
    return "'" + value.replace("'", "'\"'\"'") + "'"


def dequote(token: str) -> str:
    """Undo `shlex.quote`/`quote_env_value`; leave an unquoted token alone."""
    if len(token) >= QUOTED_TOKEN_MIN and token.startswith("'") and token.endswith("'"):
        return token[1:-1].replace("'\"'\"'", "'")
    if len(token) >= QUOTED_TOKEN_MIN and token.startswith('"') and token.endswith('"'):
        return token[1:-1]
    return token


def parse_credentials(text: str) -> dict[str, str]:
    """Read the file back into names and values, comments and blanks ignored."""
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name, sep, value = line.partition("=")
        if not sep or not name.strip():
            continue
        values[name.strip().removeprefix("export ").strip()] = dequote(value.strip())
    return values


def render_credentials(values: dict[str, str]) -> str:
    """Render the whole file, header included, from names to values."""
    body = [f"{name}={quote_env_value(value)}" for name, value in sorted(values.items())]
    return "\n".join([*CREDENTIALS_HEADER, "", *body]) + "\n"


def classify_secret(value: str) -> str | None:
    """Say why this paste cannot be a credential, or None if it can be."""
    if not value:
        return "the paste was empty"
    if any(ch in value for ch in "\n\r\t"):
        return "the paste contains a newline or tab — paste the key alone"
    if any(ord(ch) < ASCII_CONTROL_CEILING or ord(ch) == ASCII_DELETE for ch in value):
        return "the paste contains control characters"
    return None


def plan_credentials(
    existing: str | None, name: str, *, force: bool
) -> tuple[str, str] | tuple[None, str]:
    """Decide what writing ``name`` does, without ever seeing the value.

    Returns ``(action, detail)`` where action is ``create`` or ``replace``, or
    ``(None, reason)`` when it must refuse. Refuse-not-overwrite is the default:
    a key already recorded is not silently replaced by a re-run.
    """
    if existing is None:
        return "create", "the file does not exist yet"
    if name not in parse_credentials(existing):
        return "create", "the file exists and does not carry this name"
    if force:
        return "replace", "--force given, replacing the recorded value"
    return None, f"{name} is already recorded in this file"


# --------------------------------------------------------------------- statusline

_CHAIN = re.compile(r"^bash (?P<tap>'[^']*'|\S+) (?P<inner>.*)$", re.DOTALL)


def chain_command(existing: str, tap: Path) -> str:
    """Put the tap in front of ``existing``, without ever nesting two taps."""
    return f"bash {shlex.quote(str(tap))} {shlex.quote(unwrap_command(existing))}"


def unwrap_command(command: str) -> str:
    """Recover the command as it was before any tap was chained in front of it."""
    match = _CHAIN.match(command.strip())
    if match is None:
        return command
    if not dequote(match["tap"]).endswith(TAP_BASENAME):
        return command
    return dequote(match["inner"].strip())


class StatuslinePlan(NamedTuple):
    """What chaining would do to one settings document."""

    action: str
    settings: dict[str, object]
    before: str
    after: str


def _configured_command(settings: dict[str, object]) -> str:
    """Read the configured status-line command, refusing a shape it cannot chain."""
    configured = settings.get("statusLine")
    if configured is None:
        return ""
    if not isinstance(configured, dict):
        raise_unrecognised("unsupported_statusline", "`statusLine` is not an object")
    if configured.get("type") != "command":
        raise_unrecognised(
            "unsupported_statusline",
            f"`statusLine.type` is {configured.get('type')!r}, not 'command'",
        )
    return str(configured.get("command", ""))


def plan_statusline(settings: dict[str, object], tap: Path) -> StatuslinePlan:
    """Chain the tap ahead of whatever status line is configured.

    Raises `MergeRefusedError` on a shape this cannot chain safely — a
    `statusLine` that is not a command, or a command that already mentions a tap
    in a form this cannot take apart. Refusing beats guessing: replacing rather
    than chaining would silently remove the human's status line.
    """
    before = _configured_command(settings)
    if TAP_BASENAME in unwrap_command(before):
        raise_unrecognised(
            "chain_unrecognised",
            f"the configured command already mentions {TAP_BASENAME} in a form this "
            "cannot take apart, so chaining again would nest two taps",
        )
    after = chain_command(before, tap)
    if after == before:
        action = "unchanged"
    elif TAP_BASENAME in before:
        action = "rechained"
    else:
        action = "chained"
    updated = dict(settings)
    updated["statusLine"] = {"type": "command", "command": after}
    return StatuslinePlan(action, updated, before, after)


GOVERNANCE_WEAKNESS: Final = (
    (
        "note=~/.claude/settings.json is outside this repository. Nothing here can "
        "enforce or test that the tap stays wired: no hook governs that file, no "
        "gate reads it, and a Claude Code upgrade or a plugin that rewrites the "
        "status line removes the tap silently."
    ),
    (
        "note=If the tap disappears, #226's breaker degrades to reacting to 429s "
        "rather than to a quota reading. `just prereqs check` is the only detector, "
        "so run it before trusting a quota number."
    ),
)


# -------------------------------------------------------------------- codex config

CODEX_CONFIG: Final = """\
# arma-cti Codex lane configuration — written by `just prereqs tools` (#230,
# refs #221, ADR-0061). Written BEFORE first use, deliberately: doing it after
# means telemetry has already left the box.
#
# Why this file exists at all: Codex's `metrics_exporter` does not default to
# off. It defaults to `Statsig`, an OpenAI-internal ingestion exporter with a
# built-in endpoint (https://ab.chatgpt.com/otlp/v1/metrics) and a built-in API
# key, read from `codex-rs/core/src/config/otel.rs`. A Codex lane left at
# defaults therefore exports its metrics off-box and nothing to our loopback
# collector. `exporter` and `trace_exporter` do default to none.
#
# UNVERIFIED, and stated rather than hidden: the `[otel]` table is absent from
# Codex's public `docs/config.md`, so these key spellings come from reading the
# Rust struct and not from a documented schema, and the serde renames on
# `OtelConfigToml` were not resolvable
# (docs/research/agent-observability-and-cost-ledgers.md, "What I could not
# verify"). `just prereqs check` therefore reports this file as written but
# unverified while Codex is not installed, and never as a pass. Verify on the
# day Codex lands by running the lane once with `ss`/`tcpdump` watching for
# ab.chatgpt.com, or by whatever config dump the CLI offers by then.

[otel]
# The whole point of the file.
metrics_exporter = "none"

# Already the default; asserted rather than assumed, because it governs whether
# prompt text leaves the process at all.
log_user_prompt = false
"""


# ------------------------------------------------------------------------ gitleaks


class ReleaseAsset(NamedTuple):
    """The two files a gitleaks release download needs."""

    version: str
    tarball: str
    checksums: str


def release_assets(tag: str) -> ReleaseAsset:
    """Name the assets for a release tag, e.g. ``v8.30.0`` for linux x64."""
    version = tag.lstrip("v")
    return ReleaseAsset(
        version=version,
        tarball=f"gitleaks_{version}_linux_x64.tar.gz",
        checksums=f"gitleaks_{version}_checksums.txt",
    )


def expected_digest(checksums: str, asset: str) -> str | None:
    """Read the sha256 a checksums.txt records for one asset, or None if it has none."""
    for line in checksums.splitlines():
        parts = line.split()
        if len(parts) == CHECKSUM_FIELDS and parts[1].lstrip("*") == asset:
            return parts[0].lower()
    return None


# ---------------------------------------------------------------------- the probes


class Probe(NamedTuple):
    """One fact about the box. ``present=None`` means the check could not run."""

    present: bool | None
    detail: str


class Facts(NamedTuple):
    """Everything ``check`` reads, gathered at the seam so the ladder stays pure."""

    gitleaks: Probe
    codex_cli: Probe
    credentials: Probe
    zai_key: Probe
    collector: Probe
    ledger_dir: Probe
    statusline: Probe
    plan_tier: Probe
    codex_config: Probe


def _read(path: Path) -> tuple[str | None, str]:
    """Read a file's text, or None with the reason it could not be read."""
    try:
        return path.read_text(), ""
    except FileNotFoundError:
        return None, "does not exist"
    except OSError as failure:
        return None, f"unreadable: {failure.strerror}"


def probe_binary(name: str, local_bin: Path) -> Probe:
    """Look for a user-local binary, on PATH or in ``~/.local/bin``."""
    found = shutil.which(name) or (str(local_bin / name) if (local_bin / name).exists() else None)
    if found:
        return Probe(present=True, detail=found)
    return Probe(present=False, detail=f"not on PATH and not at {local_bin / name}")


def probe_credentials(path: Path) -> tuple[Probe, Probe]:
    """Read the credentials file's mode, and whether it carries a z.ai key.

    Names only, never values: this answers "is the key there", and the value
    never leaves the parse.
    """
    try:
        mode = path.stat().st_mode & 0o777
    except FileNotFoundError:
        return (
            Probe(present=False, detail=f"{path} does not exist"),
            Probe(present=False, detail="no credentials file to carry it"),
        )
    except OSError as failure:
        unknown = Probe(present=None, detail=f"{path}: {failure.strerror}. {COULD_NOT_RUN}")
        return unknown, unknown
    file_probe = (
        Probe(present=True, detail=f"{path} mode 0600")
        if mode == PRIVATE_MODE
        else Probe(present=False, detail=f"{path} is mode {mode:04o}, not 0600")
    )
    text, why = _read(path)
    if text is None:
        return file_probe, Probe(present=None, detail=f"{path}: {why}. {COULD_NOT_RUN}")
    names = sorted(parse_credentials(text))
    return file_probe, Probe(
        present=ZAI_KEY_NAME in names,
        detail=f"names recorded: {', '.join(names) or 'none'}",
    )


def probe_collector(path: Path) -> Probe:
    """Read whether the collector already carries the ledger legs."""
    text, why = _read(path)
    if text is None:
        return Probe(present=None, detail=f"{path}: {why}. {COULD_NOT_RUN}")
    wanted = ("filter/cti:", "file/ledger:", "    traces:", "    traces/ledger:")
    missing = [key.strip() for key in wanted if key not in text]
    if missing:
        return Probe(present=False, detail=f"{path} lacks: {', '.join(missing)}")
    return Probe(present=True, detail=f"{path} carries the ledger filter, exporter and pipelines")


def probe_ledger_dir(path: Path) -> Probe:
    """Read whether the durable export directory exists with the ownership it needs."""
    try:
        stat = path.stat()
    except FileNotFoundError:
        return Probe(present=False, detail=f"{path} does not exist")
    except OSError as failure:
        return Probe(present=None, detail=f"{path}: {failure.strerror}. {COULD_NOT_RUN}")
    try:
        owner = pwd.getpwuid(stat.st_uid).pw_name
        group = grp.getgrgid(stat.st_gid).gr_name
    except KeyError:
        return Probe(present=None, detail=f"{path}: uid/gid not resolvable. {COULD_NOT_RUN}")
    if owner != COLLECTOR_USER:
        return Probe(present=False, detail=f"{path} is owned by {owner}, not {COLLECTOR_USER}")
    mode = stat.st_mode & 0o7777
    return Probe(present=True, detail=f"{path} owner={owner} group={group} mode={mode:04o}")


def probe_statusline(path: Path, tap: Path) -> Probe:
    """Read whether the tap is chained ahead of the configured status line."""
    text, why = _read(path)
    if text is None:
        return Probe(present=None, detail=f"{path}: {why}. {COULD_NOT_RUN}")
    try:
        settings = json.loads(text)
    except json.JSONDecodeError as failure:
        return Probe(present=None, detail=f"{path}: not valid JSON ({failure}). {COULD_NOT_RUN}")
    configured = settings.get("statusLine")
    command = str(configured.get("command", "")) if isinstance(configured, dict) else ""
    if command.startswith(f"bash {shlex.quote(str(tap))} "):
        return Probe(present=True, detail=f"chained ahead of {unwrap_command(command)!r}")
    if TAP_BASENAME in command:
        return Probe(present=False, detail=f"a tap is chained, but not this one: {command!r}")
    return Probe(present=False, detail=f"not chained; configured command is {command!r}")


def probe_plan_tier(path: Path) -> Probe:
    """Read whether a z.ai plan tier has been recorded for #226's estimator."""
    text, why = _read(path)
    if text is None:
        return Probe(present=False, detail=f"{path}: {why}")
    try:
        record = json.loads(text)
    except json.JSONDecodeError as failure:
        return Probe(present=None, detail=f"{path}: not valid JSON ({failure}). {COULD_NOT_RUN}")
    tier = record.get("tier")
    if tier in ZAI_TIERS:
        return Probe(present=True, detail=f"tier={tier} source={record.get('source', 'unknown')}")
    return Probe(present=False, detail=f"{path} records no known tier (got {tier!r})")


def probe_codex_config(path: Path) -> Probe:
    """Read whether the off-box metrics exporter is disabled before Codex's first use."""
    text, why = _read(path)
    if text is None:
        return Probe(present=False, detail=f"{path}: {why}")
    if 'metrics_exporter = "none"' in text:
        return Probe(present=True, detail=f'{path} sets metrics_exporter = "none"')
    return Probe(present=False, detail=f"{path} does not disable the off-box metrics exporter")


def gather(layout: Layout) -> Facts:
    """Read the box once, so the decision ladder below is pure."""
    credentials, zai_key = probe_credentials(layout.credentials)
    return Facts(
        gitleaks=probe_binary("gitleaks", layout.local_bin),
        codex_cli=probe_binary("codex", layout.local_bin),
        credentials=credentials,
        zai_key=zai_key,
        collector=probe_collector(layout.collector_config),
        ledger_dir=probe_ledger_dir(layout.ledger_dir),
        statusline=probe_statusline(layout.settings, layout.tap),
        plan_tier=probe_plan_tier(layout.plan_tier),
        codex_config=probe_codex_config(layout.codex_config),
    )


# ------------------------------------------------------------------------- check


class Item(NamedTuple):
    """One reported prerequisite."""

    name: str
    state: str
    blocks: str
    detail: str
    action: str
    deferred: bool


def _state(probe: Probe) -> str:
    """Map a probe onto its reported state. ``unknown`` is never a pass."""
    if probe.present is None:
        return "unknown"
    return "ok" if probe.present else "missing"


SUDO_ACTION: Final = "just prereqs sudo-script, then a human runs it"
CODEX_ACTION: Final = "just prereqs tools --codex, then `codex login` (human)"


def evaluate(facts: Facts) -> tuple[Item, ...]:
    """Decide every prerequisite's state. Nothing here reads the box."""
    rows = (
        ("gitleaks", facts.gitleaks, "221", "just prereqs tools", False),
        ("credentials_file", facts.credentials, "225", "just prereqs credentials", False),
        ("zai_key", facts.zai_key, "225", "just prereqs credentials (the human pastes)", False),
        ("collector_ledger", facts.collector, "226,227", SUDO_ACTION, False),
        ("ledger_dir", facts.ledger_dir, "227", SUDO_ACTION, False),
        ("statusline_tap", facts.statusline, "226", "just prereqs statusline", False),
        ("plan_tier", facts.plan_tier, "226", "just prereqs plan-tier", False),
        ("codex_config", facts.codex_config, "codex-lane", "just prereqs tools", True),
        ("codex_cli", facts.codex_cli, "codex-lane", CODEX_ACTION, True),
    )
    return tuple(
        Item(name, _state(probe), blocks, probe.detail, action, deferred)
        for name, probe, blocks, action, deferred in rows
    )


def render_check(items: tuple[Item, ...]) -> Report:
    """Render one line per item, then the summary and the exit this earns."""
    lines = [
        f"item={item.name} state={item.state} blocks={item.blocks} detail={item.detail}"
        + (f" action={item.action}" if item.state != "ok" else "")
        for item in items
    ]
    blocking = [item for item in items if not item.deferred]
    unmet = [item for item in blocking if item.state != "ok"]
    unknown = [item for item in items if item.state == "unknown"]
    met = sum(1 for item in blocking if item.state == "ok")
    lines.append(
        f"summary={met}/{len(blocking)} week-one prerequisites met, "
        f"{len(items) - len(blocking)} deferred to the Codex lane"
    )
    if unknown:
        lines.append(
            f"note={len(unknown)} check(s) could not run and are reported unknown, "
            f"never as a pass. {COULD_NOT_RUN}"
        )
    if not unmet:
        return Report((*lines, "ok=prereqs_met"), EXIT_OK)
    lines.append("refused=prereqs_missing")
    lines.append("action=" + "; ".join(f"{item.name}: {item.action}" for item in unmet))
    return Report(tuple(lines), EXIT_REFUSED)


def action_check(layout: Layout, _args: argparse.Namespace) -> Report:
    """Report every item's true state."""
    return render_check(evaluate(gather(layout)))


# ------------------------------------------------------------------- write actions


def write_private(
    path: Path, text: str, mode: int = PRIVATE_MODE, parent_mode: int | None = PRIVATE_DIR_MODE
) -> None:
    """Write ``text`` to ``path`` at ``mode``, atomically, never world-readable.

    The temporary file is given its final mode before anything is written to it,
    so the content is never on disk under a wider one, not even for an instant.
    ``parent_mode`` is None where the directory belongs to something else — the
    human's ``~/.claude`` is not this recipe's to tighten.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if parent_mode is not None:
        with contextlib.suppress(OSError):
            path.parent.chmod(parent_mode)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".prereqs-")
    scratch = Path(temporary)
    try:
        os.fchmod(handle, mode)
        with os.fdopen(handle, "w") as stream:
            stream.write(text)
        scratch.replace(path)
    except BaseException:
        with contextlib.suppress(OSError):
            scratch.unlink()
        raise
    path.chmod(mode)


def read_secret(prompt: str) -> str:
    """Take a pasted secret without echoing it and without it reaching argv.

    `getpass` reads from the controlling terminal with echo off, so the value is
    not in the shell's history, not in `ps`, and not on the screen. A piped stdin
    is honoured for a non-interactive caller, which is how the tests drive it.
    """
    if sys.stdin.isatty():
        return getpass.getpass(prompt)
    return sys.stdin.readline().rstrip("\n")


def _run(argv: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run one subprocess, so the install ladders read as ladders."""
    return subprocess.run(  # noqa: S603
        argv, capture_output=True, text=True, check=False, cwd=cwd
    )


def inside_git_repository(path: Path) -> bool:
    """Say whether ``path`` would live inside a git work tree."""
    probe = _run(["git", "-C", str(path.parent), "rev-parse", "--is-inside-work-tree"])
    return probe.returncode == 0 and probe.stdout.strip() == "true"


def action_credentials(layout: Layout, args: argparse.Namespace) -> Report:
    """Take one pasted key into ``~/.arma-cti/credentials.env`` at 0600."""
    try:
        return _write_credential(layout, args)
    except StepRefusedError as refusal:
        return refusal.report


def _write_credential(layout: Layout, args: argparse.Namespace) -> Report:
    """Run the credentials ladder, raising each refusal by its own name."""
    path = layout.credentials
    if inside_git_repository(path):
        raise_refusal(
            "credentials_inside_repository",
            (f"path={path}", "detail=this path is inside a git work tree"),
            "Credentials live outside every worktree. Do not move them into one.",
        )
    existing, why = _read(path)
    if existing is None and why != "does not exist":
        raise_refusal(
            "credentials_unreadable",
            (f"path={path}", f"detail={why}. {COULD_NOT_RUN}"),
            "Read the file's permissions yourself. Nothing has been written.",
            EXIT_COULD_NOT_LOOK,
        )
    plan, detail = plan_credentials(existing, args.name, force=args.force)
    if plan is None:
        raise_refusal(
            "credential_exists",
            (f"name={args.name}", f"path={path}", f"detail={detail}"),
            f"Re-run with --force to replace it: "
            f"just prereqs credentials --force --name {args.name}",
        )
    secret = read_secret(f"Paste the value for {args.name} (input is hidden): ").strip()
    bad = classify_secret(secret)
    if bad is not None:
        raise_refusal(
            "bad_paste",
            (f"name={args.name}", f"detail={bad}"),
            "Nothing has been written. Run the recipe again and paste the key alone.",
        )
    values = parse_credentials(existing or "")
    values[args.name] = secret
    del secret
    write_private(path, render_credentials(values))
    return Report(
        (
            f"ok=credential_{plan}",
            f"name={args.name}",
            f"path={path}",
            "mode=0600",
            f"names={', '.join(sorted(values))}",
            (
                "note=The value was never echoed, never put on a command line and is "
                "written nowhere else. It is read per invocation, never exported "
                "globally."
            ),
            f"detail={detail}",
        ),
        EXIT_OK,
    )


def action_sudo_script(layout: Layout, _args: argparse.Namespace) -> Report:
    """Generate the root script and print its path. Never run it."""
    current, why = _read(layout.collector_config)
    if current is None:
        return Report.refused(
            "no_collector_config",
            (f"path={layout.collector_config}", f"detail={why}"),
            "Install otelcol-contrib first, or point this at the right config. "
            "Nothing has been generated.",
            EXIT_COULD_NOT_LOOK,
        )
    try:
        merged = merge_collector_config(current, layout.ledger_dir)
    except MergeRefusedError as refusal:
        return Report.refused(
            refusal.reason,
            (f"path={layout.collector_config}", f"detail={refusal.detail}"),
            "Read the config yourself and say what shape it is. Nothing has been "
            "generated, and no root action has been proposed on a config this "
            "cannot read.",
        )
    reader = pwd.getpwuid(os.getuid()).pw_name
    script = render_sudo_script(
        current_config=current,
        desired_config=merged.text,
        layout=layout,
        reader_user=reader,
        generated_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    path = layout.generated_dir / "install-telemetry-root.sh"
    write_private(path, script, mode=0o700)
    added = ", ".join(merged.added) if merged.added else "nothing (the config already carries it)"
    return Report(
        (
            "ok=sudo_script_generated",
            f"path={path}",
            f"adds={added}",
            f"reader_user={reader}",
            (
                "note=Generated, not run. This agent runs nothing as root, and the "
                "script is written to be read before it is trusted: it refuses "
                f"unless {layout.collector_config} is byte-identical to what this "
                "generation was computed from, backs up before writing, validates "
                "before restarting, and is idempotent."
            ),
            f"action=Review it, then run it once: sudo bash {path}",
        ),
        EXIT_OK,
    )


def action_statusline(layout: Layout, args: argparse.Namespace) -> Report:
    """Chain the quota tap ahead of the existing status line."""
    try:
        return _chain_statusline(layout, args)
    except StepRefusedError as refusal:
        return refusal.report


def _chain_statusline(layout: Layout, args: argparse.Namespace) -> Report:
    """Run the status-line ladder, raising each refusal by its own name."""
    if not layout.tap.exists():
        raise_refusal(
            "no_tap_script",
            (f"path={layout.tap}", "detail=the tap script is not in the main checkout"),
            "This recipe chains a script that must exist. Nothing has been changed.",
        )
    text, why = _read(layout.settings)
    if text is None:
        raise_refusal(
            "no_settings",
            (f"path={layout.settings}", f"detail={why}"),
            "Claude Code writes this file. Nothing has been changed.",
            EXIT_COULD_NOT_LOOK,
        )
    try:
        settings = json.loads(text)
    except json.JSONDecodeError as failure:
        raise_refusal(
            "settings_unparseable",
            (f"path={layout.settings}", f"detail=not valid JSON: {failure}"),
            "Fix the JSON by hand. This recipe will not rewrite a file it cannot read.",
            EXIT_COULD_NOT_LOOK,
            cause=failure,
        )
    try:
        plan = plan_statusline(settings, layout.tap)
    except MergeRefusedError as failure:
        raise_refusal(
            failure.reason,
            (f"path={layout.settings}", f"detail={failure.detail}"),
            "Chaining is the whole point; replacing would remove the human's status "
            "line. Nothing has been changed.",
            cause=failure,
        )
    preview = (
        f"before={plan.before!r}",
        f"after={plan.after!r}",
        (
            "note=The existing command is preserved verbatim inside the chain and "
            "runs with the same payload on its stdin. The tap never touches its "
            "stdout."
        ),
        *GOVERNANCE_WEAKNESS,
    )
    if args.dry_run:
        return Report(("ok=dry_run", f"would={plan.action}", *preview), EXIT_OK)
    if plan.action == "unchanged":
        return Report(("ok=already_chained", *preview), EXIT_OK)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup = layout.settings.with_name(f"{layout.settings.name}.bak-{stamp}")
    shutil.copy2(layout.settings, backup)
    write_private(layout.settings, json.dumps(plan.settings, indent=2) + "\n", parent_mode=None)
    return Report((f"ok=statusline_{plan.action}", f"backup={backup}", *preview), EXIT_OK)


CODEX_EXPORTER_NOTE: Final = (
    'note=metrics_exporter is set to "none" BEFORE Codex\'s first use, because its '
    "default is Statsig -> https://ab.chatgpt.com/otlp/v1/metrics and doing this "
    "afterwards means telemetry has already left the box. The key spelling is read "
    "from the crate, not from a documented schema, so `just prereqs check` reports "
    "it as unverified until the lane is exercised."
)

CODEX_DEFERRED_NOTE: Final = (
    "skipped=codex_cli detail=the Codex lane is explicitly not week one (#229). Its "
    "config is written above so the exporter is off before any first use; add "
    "--codex to install the CLI too."
)


def action_tools(layout: Layout, args: argparse.Namespace) -> Report:
    """Install the user-local tooling, and write the Codex config before first use."""
    write_private(layout.codex_config, CODEX_CONFIG, parent_mode=None)
    lines: list[str] = [
        f"ok=codex_config_written path={layout.codex_config}",
        CODEX_EXPORTER_NOTE,
    ]
    code = EXIT_OK

    found = shutil.which("gitleaks")
    if found:
        lines.append(f"ok=gitleaks_present path={found}")
    else:
        report = install_gitleaks(layout)
        lines.extend(report.lines)
        code = max(code, report.code)

    if args.codex:
        report = install_codex(layout)
        lines.extend(report.lines)
        code = max(code, report.code)
    else:
        lines.append(CODEX_DEFERRED_NOTE)
    return Report(tuple(lines), code)


def install_gitleaks(layout: Layout) -> Report:
    """Fetch the current gitleaks release, verified, into ``~/.local/bin``."""
    try:
        return _install_gitleaks(layout)
    except StepRefusedError as refusal:
        return refusal.report


def _gitleaks_release(area: Path) -> ReleaseAsset:
    """Resolve the current release and download its tarball and checksums."""
    if not shutil.which("gh"):
        raise_refusal(
            "no_gh",
            ("detail=`gh` is not on PATH, so the release could not be fetched.",),
            "Install gh, or fetch gitleaks yourself into ~/.local/bin.",
            EXIT_COULD_NOT_LOOK,
        )
    latest = _run(["gh", "api", "repos/gitleaks/gitleaks/releases/latest", "--jq", ".tag_name"])
    if latest.returncode != 0:
        raise_refusal(
            "release_lookup_failed",
            (f"detail={latest.stderr.strip()}", f"detail={COULD_NOT_RUN}"),
            "Nothing was downloaded or installed.",
            EXIT_COULD_NOT_LOOK,
        )
    assets = release_assets(latest.stdout.strip())
    download = _run(
        [
            "gh",
            "release",
            "download",
            f"v{assets.version}",
            "--repo",
            "gitleaks/gitleaks",
            "--pattern",
            assets.tarball,
            "--pattern",
            assets.checksums,
            "--dir",
            str(area),
        ],
    )
    if download.returncode != 0:
        raise_refusal(
            "download_failed",
            (f"version={assets.version}", f"detail={download.stderr.strip()}"),
            "Nothing was installed.",
            EXIT_COULD_NOT_LOOK,
        )
    return assets


def _verified_payload(area: Path, assets: ReleaseAsset) -> tuple[bytes, str]:
    """Check the tarball against the published checksum, then extract the binary."""
    tarball = area / assets.tarball
    checksums, _ = _read(area / assets.checksums)
    want = expected_digest(checksums or "", assets.tarball)
    got = hashlib.sha256(tarball.read_bytes()).hexdigest()
    if want is None:
        raise_refusal(
            "no_published_checksum",
            (f"asset={assets.tarball}", f"detail={assets.checksums} records no line for it"),
            "Nothing was installed. An unverified download is not a download that passed.",
        )
    if want != got:
        raise_refusal(
            "checksum_mismatch",
            (f"asset={assets.tarball}", f"expected={want}", f"got={got}"),
            "Nothing was installed. Do not install this file.",
        )
    with tarfile.open(tarball) as archive:
        member = next((m for m in archive.getmembers() if Path(m.name).name == "gitleaks"), None)
        extracted = archive.extractfile(member) if member is not None else None
        if extracted is None:
            raise_refusal(
                "no_binary_in_archive",
                (f"asset={assets.tarball}", "detail=no `gitleaks` file member in the tarball"),
                "Nothing was installed.",
            )
        return extracted.read(), got


def _install_gitleaks(layout: Layout) -> Report:
    """Run the gitleaks install ladder, raising each refusal by its own name."""
    with tempfile.TemporaryDirectory(prefix="cti-gitleaks-") as scratch:
        area = Path(scratch)
        assets = _gitleaks_release(area)
        payload, digest = _verified_payload(area, assets)
    target = layout.local_bin / "gitleaks"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    target.chmod(0o755)
    version = _run([str(target), "version"])
    if version.returncode != 0:
        raise_refusal(
            "installed_binary_will_not_run",
            (f"path={target}", f"detail={version.stderr.strip()}"),
            "The file is in place but did not run. Read the error above.",
        )
    return Report(
        (
            f"ok=gitleaks_installed path={target} version={version.stdout.strip()}",
            f"sha256={digest}",
            (
                f"note=Verified against {assets.checksums} before install. No sudo: "
                f"this is a user-local binary in {layout.local_bin}, which must be on "
                "PATH for `just check` to reach it once #221 wires the scan in."
            ),
        ),
        EXIT_OK,
    )


def install_codex(layout: Layout) -> Report:
    """Install the Codex CLI user-local, deliberately without logging it in."""
    manager = shutil.which("npm")
    if manager is None:
        return Report.refused(
            "no_npm",
            ("detail=`npm` is not on PATH.",),
            "Install Node, or install @openai/codex by hand. Nothing was installed.",
            EXIT_COULD_NOT_LOOK,
        )
    install = _run([manager, "install", "--global", "@openai/codex"])
    if install.returncode != 0:
        return Report.refused(
            "codex_install_failed",
            (f"detail={install.stderr.strip()[:400]}",),
            "Nothing else was changed.",
            EXIT_COULD_NOT_LOOK,
        )
    return Report(
        (
            f"ok=codex_installed path={shutil.which('codex') or 'not yet on PATH'}",
            (
                f"note=The lane's config at {layout.codex_config} was written before "
                "this, so the off-box metrics exporter is off before any first use."
            ),
            "action=`codex login` is interactive browser OAuth and is the human's (#229).",
        ),
        EXIT_OK,
    )


# ----------------------------------------------------------------------- plan tier

NO_PUBLISHED_TIER_ENDPOINT: Final = (
    "detail=z.ai publishes no machine-readable quota or plan-tier endpoint that the "
    "prior-art sweep could find — primary source read of the absence at "
    "https://docs.z.ai/devpack/overview, recorded in "
    "docs/research/multi-provider-routing-substrates.md. So there is nothing "
    "documented to query, and this refuses rather than guessing a tier."
)

GUESS_IS_WORSE: Final = (
    "detail=A guessed tier would silently mis-size #226's quota estimator, which is "
    "worse than not having one."
)

PROBE_LIMIT: Final = 400


def probe_endpoint(url: str, token: str) -> str:
    """GET one candidate endpoint and report what it said, verbatim and short."""
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
            return f"{response.status} {response.read(PROBE_LIMIT).decode('utf-8', 'replace')}"
    except urllib.error.HTTPError as failure:
        return f"{failure.code} {failure.read(PROBE_LIMIT).decode('utf-8', 'replace')}"
    except (urllib.error.URLError, OSError, ValueError) as failure:
        return f"no response: {failure}"


def record_plan_tier(layout: Layout, tier: str) -> Report:
    """Record the tier the human holds, with the caps #226's estimator needs."""
    window, weekly = ZAI_TIERS[tier]
    record = {
        "tier": tier,
        "prompts_per_5h": window,
        "prompts_per_7d": weekly,
        "off_peak_multiplier": 0.5,
        "peak_window": "Mon-Fri 14:00-18:00 SGT",
        "source": "human",
        "recorded_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    write_private(
        layout.plan_tier, json.dumps(record, indent=2) + "\n", mode=0o644, parent_mode=None
    )
    return Report(
        (
            "ok=plan_tier_recorded",
            f"path={layout.plan_tier}",
            f"tier={tier} prompts_per_5h={window} prompts_per_7d={weekly}",
            (
                "note=Caps are the published GLM Coding Plan figures, not a reading of "
                "this account. Off-peak is charged at 50%; peak is Mon-Fri "
                "14:00-18:00 SGT."
            ),
        ),
        EXIT_OK,
    )


def action_plan_tier(layout: Layout, args: argparse.Namespace) -> Report:
    """Read the z.ai plan tier if anything records it; otherwise say so plainly."""
    if args.set:
        return record_plan_tier(layout, args.set.lower())

    recorded = probe_plan_tier(layout.plan_tier)
    if recorded.present:
        return Report(("ok=plan_tier_known", f"detail={recorded.detail}"), EXIT_OK)

    credentials, _ = _read(layout.credentials)
    token = parse_credentials(credentials or "").get(ZAI_KEY_NAME)
    if token is None:
        return Report.refused(
            "no_credential",
            (f"detail=no {ZAI_KEY_NAME} in {layout.credentials}",),
            "Run `just prereqs credentials` first — the tier cannot be read without a key.",
        )
    probes = tuple(f"probe={url} -> {probe_endpoint(url, token)}" for url in args.endpoint)
    return Report.refused(
        "plan_tier_unknown",
        (
            NO_PUBLISHED_TIER_ENDPOINT,
            *probes,
            (
                f"detail={len(args.endpoint)} candidate endpoint(s) probed "
                "(--endpoint URL adds one, so a documented endpoint can be tried "
                "without a code change)."
            ),
            GUESS_IS_WORSE,
        ),
        "Ask the human which tier is held, then record it: just prereqs plan-tier "
        f"--set {{{'|'.join(ZAI_TIERS)}}}",
    )


# ------------------------------------------------------------------------ invocation


def main_checkout(cwd: Path) -> Path:
    """Find the main checkout, which is where the tap script lives.

    `git worktree list` puts the main worktree first from any of them, so this
    answers the same from the checkout or from inside one of its worktrees.
    """
    listing = _run(["git", "worktree", "list", "--porcelain"], cwd=cwd)
    for line in listing.stdout.splitlines():
        if line.startswith("worktree "):
            return Path(line.removeprefix("worktree ").strip())
    return cwd


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse one action and the flags that action takes."""
    parser = argparse.ArgumentParser(prog="just prereqs", description=__doc__)
    actions = parser.add_subparsers(dest="action", required=False)

    actions.add_parser("check", help="report every prerequisite's true state")

    credentials = actions.add_parser("credentials", help="take one pasted key at mode 0600")
    credentials.add_argument("--name", default=ZAI_KEY_NAME, help="the variable name to record")
    credentials.add_argument("--force", action="store_true", help="replace a recorded name")

    actions.add_parser("sudo-script", help="generate the root script; never run it")

    statusline = actions.add_parser("statusline", help="chain the quota tap ahead of the line")
    statusline.add_argument(
        "--dry-run", action="store_true", help="print the resulting command and write nothing"
    )

    tools = actions.add_parser("tools", help="install gitleaks; write the Codex config")
    tools.add_argument("--codex", action="store_true", help="also install the Codex CLI")

    plan_tier = actions.add_parser("plan-tier", help="read or record the z.ai plan tier")
    plan_tier.add_argument(
        "--set", choices=sorted(ZAI_TIERS), help="record the tier the human holds"
    )
    plan_tier.add_argument(
        "--endpoint",
        action="append",
        default=[],
        metavar="URL",
        help="a candidate platform endpoint to probe (none is documented)",
    )

    args = parser.parse_args(argv)
    if args.action is None:
        args.action = "check"
    return args


ACTIONS: Final = {
    "check": action_check,
    "credentials": action_credentials,
    "sudo-script": action_sudo_script,
    "statusline": action_statusline,
    "tools": action_tools,
    "plan-tier": action_plan_tier,
}


def main(argv: list[str] | None = None) -> int:
    """Run one action, print its lines, and exit what it decided."""
    args = parse_args(argv)
    layout = Layout.under(Path.home(), main_checkout(Path.cwd()))
    report = ACTIONS[args.action](layout, args)
    stream = sys.stdout if report.code == EXIT_OK else sys.stderr
    for line in report.lines:
        print(line, file=stream)
    return report.code


if __name__ == "__main__":
    sys.exit(main())
