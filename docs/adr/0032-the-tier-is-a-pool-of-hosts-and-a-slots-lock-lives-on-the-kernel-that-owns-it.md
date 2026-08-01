# The tier becomes a pool of hosts, a slot's lock lives on the kernel that owns its state, and the second machine is a client host before it is a slot farm

Delegated-decision: yes
Date: 2026-08-01
Reviewed-by-human: pending
Stood-in-for: human sign-off on a new ADR (#50, fable research task directed by the human). The purchases §3 of the research recommends — the machine rebuild and any licence — are the human's and are not taken here; nor is any CLAUDE.md Contract change (machine B's ports need none: the [2400,3000) grant is per-machine address space).

Decided on issue #50, from docs/research/second-machine.md. The numbers cited are ADR-0028's and docs/regression-tier.md's measurements, not new ones.

## The second machine's role: capability, not throughput

A pool's pass is bounded below by `max(total/N, longest probe)`, and `campaign-end` at ~390 s makes every slot past N=4 idle (ADR-0028). The second machine is therefore **not** adopted to shorten a pass. Its roles, in order: host the tier's own headed client, so the human's machine leaves the tier's client path entirely (today a live play session turns `client-port` — and with it the whole corpus — `infra_unavailable`); provide the second concurrent headed client that #8, #25, #21's residual gaps and two-human-Commander tests need and that no single machine can provide; run a second concurrent *full pass*, so agents queue less on the tier; and keep the tier available when the play machine is not.

**Splitting one corpus pass across machines is explicitly not built.** Scheduling policy: server-only probes take local slots first and spill; headed-client probes route to the client host; concurrent full passes take a whole host each.

## The lock: `ssh <host> flock`, never a local proxy for a remote slot

ADR-0016 chose `flock(2)` because the kernel frees a dead holder's lock; ADR-0028 made it one flock per slot. Cross-machine, that property survives only where the lock and the state share a kernel. So a remote slot is acquired as `ssh <host> flock -n ~/.arma-cti/slots/N.lock <command>`: the flock is held on the owning host, by the SSH session's process; the initiating agent's death drops the session and the owning kernel frees the slot. A lock held on the initiating machine for a remote slot is forbidden — it frees while the remote server still runs, which is the stale-holder failure the flock exists to prevent, rebuilt one level up.

Lock release still does not kill a dead holder's processes; ADR-0022's rule is the backstop, per slot per host, with SSH hands: no `verdict.json` in the slot's evidence directory means interrupted, and the next holder clears that slot's leftovers (kill by port binding and install path, remove staging) over SSH before launching.

## The seam is built now; the plumbing waits for the metal

#47's pool runner routes every host-touching operation — launch, wait, kill, stat, guard, stage, evidence path, cleanup — through a host handle with, today, one value: the local host, null transport. `verdict.json` carries a `host` field from day one. The host guard runs per-host, and only on hosts marked `human` — machine B's client is the tier's own. The SSH transport, host registry (`~/.arma-cti/hosts.toml`, machine-scoped), remote cleanup and evidence pull-back are built only once the machine exists, because none of them can be tested before it does.

Evidence stays written on the executing host (machine-scoped, as ADR-0016 argued) and is pulled back to the initiating machine's `~/.arma-cti/runs/`; the durable record stays the issue comment, now host-qualified. Cross-host runs require the hosts' engine builds to agree; a mismatch is a stop (`infra_unavailable` — fix by updating, never interpret).

## What would overturn this

- **The capability-first role**, if `campaign-end` shrinks enough that total-work becomes the bound again at practical N — then cross-machine slot union is worth revisiting, and ADR-0028's own overturning row fires first.
- **The SSH-held lock**, if measured SSH session teardown proves unreliable at freeing remote flocks (e.g. sshd keeping orphaned sessions alive past client death beyond keepalive bounds) — then the design needs an explicit TTL or heartbeat, which this ADR deliberately avoided, and that is a redesign rather than a patch.
- **The seam**, if #47's implementation finds the host handle distorting the runner it is threaded through — a seam that costs structure before its second implementation exists is speculation, and should shrink to the `host` field in `verdict.json` alone.
- **Holding at one licence**, the moment an unattended two-headed-client probe is written — the research names that as the trigger for the second, and the trigger firing is the plan working rather than a surprise.
