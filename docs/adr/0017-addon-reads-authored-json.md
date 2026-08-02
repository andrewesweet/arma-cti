# The addon reads the authored JSON; generation survives only where there is no authored file to ship

Delegated-decision: yes
Date: 2026-08-01
Stood-in-for: human sign-off on a new ADR and on amending ADR-0012; issue #22's explicit "confirm it with a human before ripping the pipeline out" flag
Reviewed-by-human: 2026-08-02

Decided 2026-08-01 on issue #22. Amends ADR-0012's clause "SQF constructors are derived from the
same source, following #11's manifest→generated-SQF precedent."

**Shipping the authored JSON serves ADR-0012's intent better than generating SQF does.** The intent
is one source and no drift. Generation delivers one *source* but two *artefacts*, held in step by a
tool and a `schema_stale` gate — so "they agree" is a check that has to keep passing, and every
check is a standing promise that somebody ran `just generate`. `loadFile` + `fromJSON` delivers one
source and one artefact: the addon reads the same bytes the author wrote and the daemon parses.
Drift is not caught there, it is unrepresentable, which is the stronger form of the same guarantee.
The clause above also records a constraint that was never true: it was written believing SQF had no
JSON parser, when `fromJSON` has been engine-native since 2.18 and the server runs 2.20. It
documented a workaround as if it were a preference.

Second, smaller gain: the deleted code was the escaping-prone half. Rendering SQF string literals,
numbers and nested `createHashMapFromArray` by hand is a quoting problem nobody needs to own, and a
display name with an apostrophe or a `//` in it was always one authoring slip from a broken world.

**Generation survives where there is no authored file to ship.** The Command catalogue, the effect
catalogue and the rejection codes live in Python (`cti_daemon.commands`, `cti_daemon.port`), not in
an authored document, so something must still write them out for SQF. `tools/export_command_schema.py`
does, `just generate` still runs it, and `just check` still fails a stale copy as `schema_stale`.
What changed there is only the rendering: `json.dumps` instead of hand-built SQF literals, read back
with the same two scripting commands. The map manifests keep no generator at all.

**The manifest's lookup key is now its filename.** The addon resolves one from `worldName` alone —
world `Stratis` is `stratis.json` — because a packed PBO offers no directory listing to search. That
rule is enforced in `manifest.load_all`, the only reader that sees the whole directory, so a
manifest the game could never find fails `just unit` rather than producing an empty world on a
server. The authored files moved to `addons/main/manifests/` for the same reason the decision holds
at all: the addon ships them, and the daemon reads that same directory. One copy, one location.

**What would overturn this.** Any of:

- **`loadFile` stops reaching inside a packed PBO.** This is the load-bearing engine fact, and the
  one the wiki does not state plainly — its only note on the subject is about `-filePatching` and
  unpacked files. It was verified in-world rather than assumed (`spike/probes/json-manifest.sqf`,
  server 2.20.152984). If a future build changes it, that is `engine_drift` and the generated path
  was strictly more predictable, because compiled SQF is loaded by a mechanism we are not choosing.
- **Parse cost at mission start becomes visible.** Stratis is 2.3 KB and parses inside the existing
  bring-up window. A campaign-scale manifest that measurably delays `world_built` would argue for
  precompiled data again.
- **SQF needs something JSON cannot express** — code, macros, config classes. That piece goes back
  through a generator; this ADR is about data, and only data.

**A coupling worth naming.** The daemon and the addon now read literally the same file, so the
obvious way to stage "the manifest is missing" no longer works: removing it takes the daemon down
before the mission ever asks. That was tried on 2026-08-01 and the run stopped at
`infra_unavailable`, never reaching the addon's guard. The guard is therefore exercised by asking it
for a world with no manifest, and `spike/probes/manifest-missing.sqf` is red by design — its
expected verdict is `assertion_failed` carrying `no_manifest_for_world=Altis`.

Rejected: **keeping the generated SQF as a fallback** for a `loadFile` that fails — two artefacts
again, with the fallback the copy nobody exercises, and a world that half-builds off stale data
instead of refusing. **Moving the manifests into the mission** — ADR-0007 puts world data in the
addon and keeps the mission thin, and a per-mission copy is the drift this ADR exists to remove.
