#!/usr/bin/env bash
# The human's own Arma install, as something this harness borrows (#153).
# Sourced, never executed.
#
# A run that sends the headed client has to put `@cti` inside the real Steam
# install on the Windows host, because `-mod=` resolves against the game
# directory and CfgFunctions compiles per machine. That folder is not the tier's:
# it is the one the human's evening plays out of. So the failure mode is not a
# red run, it is a person launching Arma at 9 p.m. and finding a broken mod, with
# nothing automated that repairs it.
#
# It used to be `rm -rf @cti` and then `cp -r`, which meant the play install was
# modless for the whole of the delete and half-staged for the whole of the copy —
# seconds to minutes across the WSL/Windows boundary — and a run killed inside
# that window left the damage behind for the next play session to discover.
#
#   cti_play_install_repair <arma-dir> <mod>          put an interrupted swap right
#   cti_play_install_stage  <arma-dir> <mod> <src>    stage, verify, swap in
#
# The rule the two of them keep, and the acceptance criterion on #153: at every
# instant `<arma-dir>/<mod>` is either the previous good copy or a verified new
# one, and never a copy in progress. Nothing writes *into* the live folder. The
# new copy is built beside it under `<mod>.staging`, checked against its source,
# and moved in by rename; the old one is moved aside to `<mod>.previous` first
# and deleted only once the new one is in place.
#
# That leaves exactly one interruptible instant — between the two renames — and
# it is a metadata operation rather than a copy. `cti_play_install_repair` closes
# it from both sides: `spike/run.sh` calls it on the way out through its teardown
# trap, and calls it again on the way in before the next stage, so even a run
# killed with -9 in that instant is repaired without a human touching anything.
#
# A `cp` orphaned by a signal that reached the shell but not its children keeps
# writing, and that is safe rather than merely tolerated: everything it writes is
# under `<mod>.staging`, and the moment the swap renames that directory away the
# orphan's own paths stop resolving, so it errors out rather than landing files
# in the live folder. What it can leave is litter, which the next repair clears.
#
# Only a run that holds the machine-wide Windows client lock may call either of
# these. Repair reads and writes paths a concurrent stage is renaming, and two
# runs doing that at once would undo each other; the lock is what makes "the
# previous copy is mine to restore" true. `spike/run.sh` gates its teardown call
# on having staged, which only happens under the lock.

cti_play_install_log() { printf '[play-install] %s\n' "$*" >&2; }

# `<relative path>\t<size>` for every file under a tree, in a stable order.
# Sizes rather than checksums on purpose: this runs over the WSL/Windows
# filesystem boundary on hundreds of megabytes of PBO, and what it has to catch
# is a copy that stopped early or ran out of disk, which changes a size. A
# content check would cost a second full read of both trees to catch a class of
# corruption `cp`'s own return status already covers.
cti_play_install_manifest() {
    local root="$1"
    [[ -d "$root" ]] || return 1
    (
        cd "$root" || exit 1
        find . -type f -printf '%p\t%s\n' | LC_ALL=C sort
    )
}

# The three states an interrupted run can leave behind, and the one answer to
# each. Idempotent and cheap — two stats when there is nothing to do — because it
# runs on the way out of every run that staged, including the ones that succeeded.
cti_play_install_repair() {
    local dir="$1" mod="$2" live prev stage
    [[ -n "$dir" && -n "$mod" ]] || return 2
    live="$dir/$mod"
    prev="$dir/$mod.previous"
    stage="$dir/$mod.staging"

    # Killed between the two renames: the live folder is gone and the previous
    # copy is sitting beside it under its own name. This is the only state in
    # which the play install is actually broken, and putting it back is the whole
    # of the repair.
    if [[ ! -e "$live" && -d "$prev" ]]; then
        mv "$prev" "$live" || {
            cti_play_install_log "could not put $prev back as $live — the play install has no $mod"
            return 1
        }
        cti_play_install_log "restored the previous $mod: a run was interrupted mid-swap"
    fi

    # Killed anywhere else: the live folder is good and what is beside it is
    # litter — a half-built staging tree, or a previous copy whose deletion did
    # not finish. Cleared here rather than left, so the next stage starts from a
    # known state and the human's install does not accumulate copies of the mod.
    if [[ -e "$live" ]]; then
        rm -rf "${prev:?}" "${stage:?}" 2>/dev/null
    fi
    return 0
}

# Stage `<src>` (the built mod's `addons` directory) into `<arma-dir>/<mod>`.
# 0 on success. On failure the reason is one line on stdout for the caller to
# quote into its typed verdict, and the play install is left exactly as it was.
cti_play_install_stage() {
    local dir="$1" mod="$2" src="$3" live prev stage leaf
    [[ -n "$dir" && -n "$mod" && -n "$src" ]] || {
        printf 'cti_play_install_stage needs an install directory, a mod name and a source\n'
        return 2
    }
    live="$dir/$mod"
    prev="$dir/$mod.previous"
    stage="$dir/$mod.staging"
    leaf="$(basename "$src")"

    [[ -d "$src" ]] || {
        printf 'nothing to stage: %s is not a directory\n' "$src"
        return 1
    }
    cti_play_install_repair "$dir" "$mod" || {
        printf 'the play install at %s was left mid-swap by an earlier run and could not be repaired\n' "$live"
        return 1
    }

    rm -rf "${stage:?}" 2>/dev/null
    mkdir -p "$stage" || {
        printf 'could not create the staging directory %s\n' "$stage"
        return 1
    }
    # The long operation, and the whole reason for the staging directory: the
    # live folder is untouched for every second of it.
    cp -r "$src" "$stage/" || {
        rm -rf "${stage:?}" 2>/dev/null
        printf 'could not copy %s into %s (disk full, or the Windows host went away mid-copy)\n' "$src" "$stage"
        return 1
    }
    if [[ "$(cti_play_install_manifest "$src")" != "$(cti_play_install_manifest "$stage/$leaf")" ]]; then
        rm -rf "${stage:?}" 2>/dev/null
        printf 'the staged copy under %s does not match %s file for file; the play install was left alone\n' "$stage" "$src"
        return 1
    fi

    # The swap. Two renames, and the only instant in which the play install has
    # no mod; `cti_play_install_repair` is what closes it.
    if [[ -e "$live" ]]; then
        mv "$live" "$prev" || {
            rm -rf "${stage:?}" 2>/dev/null
            printf 'could not move the existing %s aside; it is untouched and nothing was staged\n' "$live"
            return 1
        }
    fi
    if ! mv "$stage" "$live"; then
        # Put the previous copy straight back rather than leave the swap open:
        # the run is about to fail anyway, and the human's install must not be
        # the thing that carries the failure.
        [[ -d "$prev" ]] && mv "$prev" "$live" 2>/dev/null
        printf 'could not move the staged copy into place as %s\n' "$live"
        return 1
    fi
    rm -rf "${prev:?}" 2>/dev/null
    return 0
}
