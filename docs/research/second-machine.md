# A second machine for the tier

> **Commissioning update, 2026-08-10:** this issue #50 research predates the
> rebuilt machine and preserves its Windows/WSL proposal as history. Issues
> #52–#54 selected Ubuntu Desktop 24.04.4 on the metal, a native Linux server,
> and only the headed client under pinned Proton 10.0-4. The machine remains at
> 16 GiB and supplies one measured three-slot pool. A dedicated 419.5 GiB ext4
> filesystem was added for the `cti` Steam library on 2026-08-11; it does not
> change the memory-derived pool limit. The executable design and
> fact record are in [the Machine B runbook](../machine-b-runbook.md); where this
> research says Windows, 32 GiB, or “not yet built”, the runbook supersedes it.

**Recommendation: accept the machine; buy one licence now, hold the other two.** The rebuilt 32 GB desktop is worth having, but not for the reason its RAM suggests. Raw slots are worthless past N=4 — `campaign-end` at ~390 s is the whole schedule from there (ADR-0028), and the corpus at N=3 on the current machine already runs inside nine minutes. What the second machine actually buys, in order of value: the human's play machine leaves the tier's client path entirely (today a live play session makes `client-port` `infra_unavailable`, and `infra_unavailable` abandons the whole corpus — docs/regression-tier.md); a second headed client, which is the only way to reach #8's witness reproduction, #25's squad-leader slot against a live Commander, two-human-Commander tests, and #21's two residual gaps; a second *full pass* running concurrently with the first, so agents stop queueing on the tier lock; and durability — the tier survives the play machine being used, patched, or rebuilt.

Issue #50. Written 2026-08-01. Measured numbers are cited from ADR-0028, docs/regression-tier.md and the #44 exploration rather than re-derived; web claims are cited per section, and each is marked read-from-source or inferred.

## 1. Would this be useful? Which parts?

**Not the slots.** The arithmetic is ADR-0028's and it is unforgiving: a pool's pass is bounded below by `max(total/N, longest probe)`, the thirteen schedulable probes total 1,547 s serial, and `campaign-end` runs ~390 s. N=3 → 516 s, N=4 → 390 s, N=5+ → 390 s. A 32 GB machine could hold N≈10 by the same ~2.43 GB-per-heavy-slot arithmetic, and eight of those slots would idle. The way below six and a half minutes is to shorten `campaign-end` (#46's conversions), not to add hardware.

**These parts, in order:**

1. **The human's machine out of the tier's client path.** `client-port` is the corpus's one probe that needs a headed Windows client, and since it joined the corpus the host guard's answer is load-bearing for every full pass: a live play session refuses the probe `infra_unavailable`, which abandons the remaining corpus (docs/regression-tier.md, "What runs"). The guard working as designed still means agent testing and the human's play time contend for one machine. A second client host removes that contention *entirely* — the tier stops needing anything from the machine the human plays on. This is the single largest win and it needs one licence.
2. **A second headed client, which is a capability and not a speed-up.** A headless client cannot stand in for a real caller: `remoteExecutedOwner` is 0 from an HC by engine design, and an HC holds no player unit to carry a UID (ADR-0025, #21). Today the corpus owns exactly one headed client — the human's install, on the human's machine. A second unlocks work that is currently unreachable unattended: #8 reproduced with a *witness* client watching while the subject client desyncs; #25's playable squad-leader slot exercised against a live Commander; two-human-Commander tests; and #21's explicitly-unfinished gaps, a client that disconnects mid-exchange and ordering under load.
3. **A genuinely remote client, which sharpens #8's differential.** Every client the tier has ever launched shares a physical machine with its server, crossing only the WSL2 mirrored boundary. #8's cause 3 — mirrored networking failing to sustain bidirectional UDP — cannot be cleanly distinguished from causes 1 and 2 without varying the topology. A client arriving across the real LAN is a different network path; desync present/absent from it is evidence the single-machine setup cannot produce.
4. **Two concurrent full passes, not one faster pass.** The tier lock serialises agents, and the queue is real when several worktrees want their pre-landing gate. A second host is a second pool: two agents each run a full corpus concurrently, one per machine. That is the honest form of the throughput win.
5. **Durability.** Engine updates, Windows updates, and the human's own use of their machine currently all stop the tier. A dedicated host makes the tier's availability independent of the play machine's.

## 2. How would we configure the dedicated host?

Mirror the current machine's shape — Windows 11, WSL2 Ubuntu, mirrored networking — because every fact the tier has measured was measured against that shape, and a second topology would be a second thing to keep true.

- **WSL2, mirrored networking, with the firewall step the current machine never needed.** Mirrored mode's documented benefit is exactly what a remote host needs — "Connect to WSL directly from your local area network (LAN)" — but LAN inbound requires configuring the Hyper-V firewall: `Set-NetFirewallHyperVVMSetting -Name '{40E0AC32-...}' -DefaultInboundAction Allow`, or per-port `New-NetFirewallHyperVRule` entries (read: [Microsoft Learn, WSL networking](https://learn.microsoft.com/en-us/windows/wsl/networking); Hyper-V firewall is on by default since WSL 2.0.9). The current machine never hit this because its clients were local. Commissioning must verify LAN reachability of a tier port empirically before anything depends on it — and #8's cause 3 is a standing reminder that "a datagram crossed" and "a simulation stream is sustained" are different claims.
- **Server install exactly as today.** SteamCMD, app 233780, per docs/research/linux-server-steamcmd.md. The server package is free — "Arma 3 Dedicated server package is available for free (does not require regular Arma 3 to be purchased)" (read: vendored `topics/Arma_3_Dedicated_Server.wiki`, snapshot 2026-05-22; live: community.bistudio.com/wiki/Arma_3:_Dedicated_Server) — but *not* anonymously: this repo measured `+login anonymous +app_update 233780` refused with "No subscription" (linux-server-steamcmd.md §2). A named account with no purchases suffices, and the wiki recommends a dedicated one. Recommend a **second no-purchase SteamCMD account for machine B** rather than reusing machine A's dedicated server account, because one Steam account cannot be logged in from two places at once (read: same wiki page) and install-time contention across machines is not worth having.
- **Port space.** Each machine has its own LAN address, so the `2402 + 100N` slot scheme (ADR-0028) applies per machine, independently. 2302–2306 stay reserved on machine B too — mirrored mode shares the port space between Windows and the VM, and the reservation costs nothing while preventing a class of accident if the human ever plays *on* B.
- **Engine version pinning.** Two hosts is a new way to drift: a SteamCMD update landing on one machine and not the other puts two engine builds in one tier. The verdict already records the Arma version; cross-host scheduling must check the hosts agree before mixing them in one run, and a mismatch is a stop (`infra_unavailable` — the fix is `app_update`, not interpretation), escalating to `engine_drift` handling only when the build changed against *our code's* expectations.
- **Windows side.** OpenSSH Server (see §4); the Arma client, Steam, and a test account only when the licence is bought (§3); power settings that keep the machine awake; and an auto-logged-in desktop session, because a headed client needs an interactive session to render into — the current scripted client join runs in the human's logged-in session, and machine B needs an equivalent. That is a real security trade-off (an always-on logged-in desktop) and it is the human's to accept at commissioning; it is on a home LAN behind key-only SSH, and stating it is cheaper than discovering it.

## 3. Would we want licences — how many, for what?

Per-role facts, each verified rather than assumed:

| role | licences needed | source |
|---|---|---|
| dedicated server | **0** — free package, needs only a no-purchase Steam account for SteamCMD | read: vendored `Arma_3_Dedicated_Server.wiki` ("does not require regular Arma 3 to be purchased"), confirmed empirically in linux-server-steamcmd.md §2.1 |
| headless client | **0** — the tier's HCs are `arma3server -client`, the free server binary; the engine substitutes `HC<pid>` for a Steam ID and `headlessClients[]` whitelisting removes the ticket check | read: vendored `Arma_3_Headless_Client.wiki`; this repo's own logs (headless-client-join.md). The wiki's "requires a valid active Steam account logged in" note is written around the `arma3.exe` path and cites an unreachable forum post; ambiguous there, but moot for our server-binary HCs, which run today with no client licence |
| headed client | **1 per concurrent client, each on its own account** — one account cannot be in-game twice, and Steam Families allows concurrent play of one title only with multiple copies in the library | secondary but consistent: Steam Families FAQ excerpt ("multiple copies … can play at the same time"), community restatement of the one-session rule. No first-party page was directly fetchable; if a lawyer-grade citation is ever needed it is the Steam Subscriber Agreement |

**Recommendation: one licence now, on a new dedicated test account, installed on machine B.** That moves `client-port` off the human's machine and account (today's client runs are the human's install and the human's account — contention in both dimensions), and combined with the human's own copy it gives two concurrent headed clients whenever the human is present, which is enough to *investigate* #8 and to playtest #25.

**A second licence only when a specific probe needs it** — an unattended two-headed-client probe (two-human-Commander in the corpus, #21's ordering-under-load, an #8 witness+subject reproduction with nobody home). None is written today. Be honest about where that second client would run: one Windows session runs one Steam instance, so the second unattended client lands back on the current machine, reintroducing contention for exactly those runs. That is acceptable for occasional investigation probes and is why the licence can wait for the probe.

**No case for a third.** Nothing in the corpus or the open issues wants three concurrent clients. £10 saved is £10.

Price plausibility: Arma 3 sells only via Steam and routinely discounts 75–90% (US$2.99 historic low, Summer 2024 — secondary: gamedeveloper.com, steamdb), so £10 per copy is realistic on a sale. **Purchases are the human's; nothing below assumes one made.**

## 4. How would the agentic team control the remote hosts?

**SSH is the spine, both sides, key-auth only.**

- **Windows endpoint.** OpenSSH Server is a first-party optional feature (`Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0`, `Set-Service sshd -StartupType Automatic`; read: [Microsoft Learn, OpenSSH install](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_install_firstuse)). Password and publickey are the only supported auth methods; set `DefaultShell` to PowerShell via `HKLM:\SOFTWARE\OpenSSH` (read: [Learn, server configuration](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh-server-configuration)). One quirk decides the account design: an administrators-group user's keys live in `%programdata%\ssh\administrators_authorized_keys` with strict ACL requirements (read: same page). Prefer a **dedicated non-admin automation user** — it dodges the ACL trap, and it owns the client processes it launches, so `taskkill` needs no elevation. Every Windows operation the tier already performs locally by interop path (`tasklist.exe` / `taskkill.exe` by absolute path, the scripted client launch) becomes the same command over `ssh win-b`.
- **Linux endpoint.** `sshd` inside machine B's WSL2. Mirrored mode shares one port space with Windows, whose sshd holds 22, so the WSL sshd takes an alternate port (e.g. 2222) on the same LAN address, opened through the Hyper-V firewall like the tier ports. (WSL's on-demand VM lifecycle also needs handling at commissioning — the distro must be started at boot, e.g. a scheduled task running `wsl.exe`, or reached via the Windows endpoint as a fallback.)
- **Address discipline.** docs/research/time-acceleration.md measured the sharp edge here: under mirrored mode the Windows side reaches the VM's daemon on `127.0.0.1` *only*; the VM's LAN address timed out. Loopback facts do not generalise across machines, and machine-B-internal wiring (shim→daemon) stays loopback exactly as today; only genuinely cross-machine traffic (SSH, a remote client joining a server) uses LAN addresses. Nothing about the daemon or shim changes.

## 5. The test-infrastructure piece: a pool of hosts, each a pool of slots

ADR-0028 made the tier a pool of slots on one machine. The second machine generalises it one level, and the generalisation should reuse the primitives that are already proven rather than inventing a coordinator: **SSH, `flock(2)`, and files.** No daemon on the remote host, no message bus, no service.

- **Host registry.** `~/.arma-cti/hosts.toml` on the initiating machine (machine-scoped, like the lock and evidence — worktrees are many and short-lived). One entry per host: name, SSH aliases for its Windows and Linux endpoints (empty for the local host), server-slot count, `headed_client` yes/no, `human` yes/no. The local machine is row 0 with a null transport — not a special case in the runner.
- **Allocation: the slot's lock lives on the kernel that owns the slot's state.** ADR-0016 chose `flock` because the kernel frees a dead holder's lock; ADR-0028 generalised it to one flock per slot. Cross-machine, the property survives only if the lock stays on the owning host: acquisition of a remote slot is `ssh <host> flock -n ~/.arma-cti/slots/N.lock <command>`, so the flock is held by the SSH session's process on the *owning* host's kernel. The initiating agent dying drops the SSH connection, the remote process group ends, the kernel frees the lock. A lock held on the initiating machine "for" a remote slot would instead free while a remote server still runs — the exact stale-holder failure the flock exists to prevent, reintroduced one level up.
- **Stale state: ADR-0022's rule, per slot per host, with SSH hands.** Kernel lock release does not kill a dead holder's *processes*; that was already true locally and the answer does not change: a slot's evidence directory with no `verdict.json` means the previous holder was interrupted, and the next holder of that slot clears its leftovers — kill by the slot's port bindings and install path, remove staging — before launching. Remotely, the same check and the same cleanup run over SSH before the world comes up. This is the remote-death story #50 asks for, and it is deliberately the local story with a transport under it.
- **Scheduling.** Longest-probe-first over the union of free slots, exactly ADR-0028's rule. Two placement constraints: probes with `CTI_WINDOWS_CLIENT=1` route only to `headed_client` hosts, preferring the non-`human` one; the `human` host's client is used only when the host guard passes, unchanged. The guard itself becomes per-host and only hosts marked `human` run it — machine B's client is the tier's own, and guarding it against the tier would be guarding it against itself.
- **Evidence to one place.** Runs write evidence on the executing host, machine-scoped, unchanged — then the runner pulls the directory back (rsync/scp over the same SSH) into the initiating machine's `~/.arma-cti/runs/`, and `verdict.json` gains a `host` field. The durable record stays the issue comment (verdict, class, evidence path, SHA — now host-qualified). One precedent already exists: `client-port` copies the Windows client's RPT across the WSL2 boundary into evidence; this is that, across a bigger boundary.
- **Version agreement.** Before a run mixes hosts, the runner compares their engine builds (already in every verdict); a mismatch stops the run rather than producing a cross-build comparison nobody asked for (§2).

**A slot boundary is only real where something reads it** (ADR-0028) — the rule that governed the single-machine pool governs this design doubly, because a host boundary that nothing reads fails the same way: a green run on the wrong machine. Every per-host value above names its consumer: the registry is read by the scheduler, the lock by the owning kernel, the guard by the launch path, the host field by the human reading the verdict.

## 6. Is any of it useful today, on one machine?

**Yes — one thin slice, and it belongs inside #47's build: the host seam.** The pool runner #47 commissions should route every host-touching operation — launch, wait, kill, stat, guard, stage, evidence path, cleanup — through a host handle that today has exactly one value, the local host with a null transport. That is a shape decision, near-free while #47 is being written and a rewrite afterwards; it is how the pool gains a second host later by adding a registry entry rather than by surgery. Two small companions ride along at the same cost: `verdict.json` carries a `host` field from day one, and the host guard is invoked per-host rather than globally.

**And no further.** The SSH transport, the registry file, remote cleanup, evidence pull-back — none of it is buildable-testable before the machine exists, and building untestable infrastructure ahead of its hardware is how it arrives wrong. The single-machine slice is the seam, not the plumbing.

## 7. How would we load-balance the two setups?

Mostly by not trying. The floor is `campaign-end`: a single pass cannot beat ~390 s at any slot count, and local N=3 is already at 516 s bound — splitting one pass across machines buys at most ~2 minutes and costs SSH latency and cross-host evidence collection on the critical path. The policy that matches the actual needs:

- **Server-only probes: local slots first**, spill to machine B only when local slots are all held. Locality is free; SSH is not.
- **Headed-client probes: machine B always**, once it has a client. The human's machine is the fallback only, gated by the guard as today.
- **Concurrent full passes: one pool per machine.** Two agents each take a whole host rather than interleaving one pass across both — simpler, no cross-host version coupling within a run, and it is the queue (not the pass length) that the second machine actually shortens.
- **2302–2306 untouched on both machines, always.**

## Recommendation and phased plan

**Accept the rebuild. Buy one licence now. Hold two. Build the seam today and the plumbing when the metal exists.**

| phase | needs | delivers |
|---|---|---|
| **0 — now** | nothing new | #47's N=3 pool built with the host seam (§6); ADR-0032 records the multi-host shape so #47's implementer builds against it |
| **1 — machine rebuilt** | the human's rebuild; a second no-purchase SteamCMD account | commissioning (Windows 11 + WSL2 mirrored, both SSH endpoints, Hyper-V firewall, server install, LAN-reachability verified empirically); then remote slots — registry, SSH-held locks, remote cleanup, evidence pull-back; two concurrent full passes |
| **2 — one licence** | £10 + a test Steam account (human's purchase) | Arma client on machine B; `client-port` routed there; the human's machine leaves the tier's client path; #8 investigated with a genuinely remote client; #25 exercisable against a live Commander |
| **3 — conditional** | a written two-client probe, then a second £10 licence | unattended two-headed-client tests (two-human-Commander, #21's ordering-under-load, #8 witness+subject) |

**Costs, honestly.** The rebuild is the human's time, likely a day-plus with driver and update churn. Running costs: a second always-on machine (power, noise, patching), an always-logged-in Windows session (§2's stated trade-off). Engineering: the remote-slot work is roughly another #47 in size, and every SSH hop is a new place for `infra_unavailable` to be right; two hosts also double the surface `engine_drift` can enter by. Wall-clock gained over single-machine N=3: approximately nothing per pass — the gains are availability (any-time client runs), capability (second client), and concurrency (two passes), none of which the single machine can have at any N.

## Sources

- Repo, measured: ADR-0028 (slot costs, port arithmetic, pass bounds), docs/regression-tier.md (corpus, `client-port`'s host-guard coupling), ADR-0016/0022/0024 (lock, stale state, resumption), docs/research/linux-server-steamcmd.md (§2 anonymous refusal, §2.1 no-purchase account), docs/research/headless-client-join.md (HC identity without Steam ID), docs/research/time-acceleration.md (loopback-only daemon reachability), issues #8, #21, #25, #44, #47.
- Vendored first-party wiki: `topics/Arma_3_Dedicated_Server.wiki` (snapshot 2026-05-22), `topics/Arma_3_Headless_Client.wiki` (snapshot 2024-02-12).
- Web, read: Microsoft Learn — [WSL networking / mirrored mode](https://learn.microsoft.com/en-us/windows/wsl/networking), [OpenSSH install](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_install_firstuse), [OpenSSH server configuration](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh-server-configuration).
- Web, secondary (marked so above): Steam Families FAQ (help.steampowered.com/en/faqs/view/054C-3167-DD7F-49D4, via excerpt), one-session-per-account community restatements, Arma 3 sale pricing (gamedeveloper.com, steamdb.info). The `hostAddressLoopback` `.wslconfig` setting was not verified this session and nothing above leans on it.
