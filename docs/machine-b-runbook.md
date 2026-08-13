# Machine B commissioning runbook

This is the operator record for issues #52–#54. Machine B is a native Ubuntu
Arma 3 server and an X11/Proton headed-client host; Proton is never used for the
server. The laptop remains the build and initiating host. Human gates are not
hidden inside automation.

## Recorded baseline

| fact | commissioned target |
|---|---|
| logical/system name | `bravo` / `arma-cti-b` |
| OS | Ubuntu Desktop 24.04.4; kernel `7.0.0-28` at audit |
| capacity | intentionally 16 GiB RAM; root has 135.9 GiB available after server commissioning |
| client filesystem | ext4, 419.5 GiB, mounted at `/home/cti/SteamLibrary`; UUID stays in the machine-local configuration |
| Steam library root | `/home/cti/SteamLibrary/SteamLibrary` (Steam's registered root inside that filesystem) |
| CPU / GPU | Intel i5-3570K; GTX 1650; NVIDIA 595.84 |
| LAN | wired reservations required; actual addresses stay in the machine-local configuration |
| tier | one pool: UDP 2402–2406, 2502–2506, 2602–2606 |
| daemon | TCP 9099–9101, loopback only |
| reserved | 2302–2306: no listener, UFW rule, or router forward |
| client | app 107410 public branch build `24672225`, 168 GiB directory; Proton `1785139158 proton-10.0-4b`; GDM X11 |
| server | native app 233780 public branch, `/home/cti/arma3server` |

The measured memory preflight is authoritative. Sixteen GiB never authorizes a
second concurrent pool on B.

## External configuration

Create `~/.arma-cti/machine-b.toml` mode 0600. Replace angle-bracket values with
console-verified facts. The file is non-secret but machine-local; never add
passwords, Guard codes, private keys, sentry data, Tailscale state, server
passwords, or client profiles.

The example below is publication-safe: its LAN values are from RFC 5737's
documentation-only `192.0.2.0/24` network, its UUID is synthetic, and
`commissioner` is an example administrative account. Replace all of them with
the locally verified values; `host.admin_user` is required and has no default.

```toml
wake_broadcast = "192.0.2.255"

[host]
logical_name = "bravo"
system_hostname = "arma-cti-b"
lan_address = "192.0.2.167"
tailscale_address = "<B Tailscale IPv4>"
wired_mac = "<B wired MAC>"
wired_interface = "<B wired interface>"
network_connection = "<B NetworkManager connection>"
ssh_alias_lan = "bravo-lan"
ssh_alias_tail = "bravo-tail"
admin_ssh_target = "192.0.2.167"
admin_user = "commissioner"
runtime_user = "cti"
slots = 3
headed_client = true
human = false

[laptop]
lan_address = "192.0.2.36"
tailscale_address = "<laptop Tailscale IPv4>"
wsl_proxy_source = "<Windows-side WSL gateway IPv4>"
wired_mac = "<laptop wired MAC>"
ssh_port = 22
tailscale_ssh_port = 22
peer_user = "cti-peer"
identity_to_bravo = "/home/commissioner/.ssh/id_ed25519_bravo"
ssh_alias_lan = "cti-laptop-lan"
ssh_alias_tail = "cti-laptop-tail"

[onepassword]
vault = "<vault available to both machines>"
item = "arma-cti machine-b SSH bootstrap"
# account = "<account shorthand>" # add only when `op` has multiple accounts
trust_file = "/home/commissioner/.arma-cti/machine-b-trust.json"
known_hosts_file = "/home/commissioner/.ssh/known_hosts.d/arma-cti-machine-b"

[steam]
server_app_id = 233780
client_app_id = 107410
proton_version = "10.0-4"
server_install = "/home/cti/arma3server"
library_uuid = "11111111-2222-4333-8444-555555555555"
library_mount = "/home/cti/SteamLibrary"
library_root = "/home/cti/SteamLibrary/SteamLibrary"
client_install = "/home/cti/SteamLibrary/SteamLibrary/steamapps/common/Arma 3"
```

Create `~/.arma-cti/hosts.toml` mode 0600. Only `bravo-lan` is the execution
target; Tailscale is a control path, never an automatic fallback.

```toml
version = 1
[hosts.local]
ssh_target = ""
server_slots = 6
headed_client = true
human = true
client_driver = "windows"
remote_root = ""

[hosts.bravo]
ssh_target = "bravo-lan"
server_slots = 3
headed_client = true
human = false
client_driver = "proton"
remote_root = "/home/cti/.arma-cti/staging"
```

## Human gates before apply

1. Reserve both LAN addresses in the router by wired MAC. Add no forwarding.
2. In ASRock firmware set `Advanced → ACPI Configuration → PCI Devices Power
   On = Enabled`, `Advanced → South Bridge Configuration → Deep Sleep =
   Disabled`, and `Restore on AC/Power Loss = Power On`.
3. Confirm the configured administrative target and interactive sudo work.

## 1Password SSH bootstrap

The machines must already be signed into the same trusted 1Password vault.
Authenticate `op` interactively; never create or save a service-account token
for commissioning. The shared item contains only public keys and their derived
fingerprints. The two automation private keys remain on the machines that
created them, and unattended SSH never depends on 1Password or its SSH agent.
Run `op account list` first. If it reports no configured account—as it currently
does on B—enable the desktop app integration or run `op account add`, then use
`op signin`; repeat the check independently in laptop WSL.

At Machine B's local console, publish its installed Ed25519 host public key:

```text
op signin
just machine-b bootstrap publish \
  --vault "<shared vault>" \
  --item "arma-cti machine-b SSH bootstrap"
```

Add `--account <shorthand>` if `op` has multiple accounts. The command refuses
an SSH session, derives the fingerprint from the local public-key blob, and
creates or idempotently updates the Secure Note. It never reads the host private
key.

On the laptop in local WSL, create the external TOML above with the same vault
and item, then pull the trust record:

```text
op signin
just machine-b bootstrap pull
```

`pull` cryptographically derives and compares B's published fingerprint,
verifies the laptop's local host public key, creates the independent
`id_ed25519_bravo` key if absent, and publishes only the laptop host and
automation public keys. It atomically writes a mode-0600 trust cache, a
dedicated `known_hosts` file, and bounded `bravo-lan` / `bravo-tail` aliases.
There is no `ssh-keyscan`, fingerprint transcription, or manual key copying.
Inside WSL the command prefers native `op` when it is configured there, avoiding
the Windows interop boundary; Windows `op.exe` remains the fallback when native
`op` is absent. On B it uses native Linux `op`.

Return to B's local console and authorize the newly published laptop public key
for the initial administrative hop:

```text
just machine-b --config ~/.arma-cti/laptop-machine-b.toml bootstrap authorize
```

`authorize` re-derives both machines' fingerprints, requires B's published host
key to match the key installed on this console, and writes one marked,
idempotent `from=` plus `restrict` block to the configured administrator's
`authorized_keys`. The playbook retains that bounded block so later
administrative maintenance remains key-only. No private key crosses machines
or enters 1Password.
Deleting or rotating any participating key requires rerunning `bootstrap
publish` on B, `bootstrap pull` on the laptop, and `bootstrap authorize` on B
before `apply`.

```text
just machine-b audit --out ~/.arma-cti/machine-b-before.json
just machine-b apply
```

`apply` runs syntax/lint and check mode, commissions B through the configured
administrator, then the
laptop WSL endpoint, and repeats both playbooks. A second-pass change fails
idempotence. After B creates its reverse automation key, `apply` records that
public key in the same 1Password item before authorizing it on the laptop. The
sudo password is interactive only. `cti` is non-admin; its one
sudoers grant is the exact read-only `/usr/sbin/ufw status verbose` audit.
The `cti-peer` reverse identity receives the same read-only grant in WSL so
`verify` can inspect both firewalls. B is a dedicated host, so its inherited
UFW rules are cleared once before the commissioned allow-list is installed.
The `cti` password remains locked: Ubuntu's `gdm-autologin` PAM path does not
need a password, and SSH remains public-key-only. A change to the GDM autologin
configuration restarts GDM once at the end of `apply`; the live one-variable
commissioning test proved that reload is sufficient even while AccountsService
continues to report `Locked=true` and `AutomaticLogin=false`. The restart is
disruptive to graphical sessions, so run a first or repairing apply only when
the physical display is at the greeter or its session may be discarded.

Ubuntu's Steam packages require a human licence decision and are never
preseeded by the playbook. Before the first apply, run `sudo apt-get install
steamcmd steam-installer` at B's local console and accept or decline the Steam
agreement yourself. A declined or absent agreement is a named apply refusal,
not an unattended acceptance. If an earlier apt transaction stopped at that
gate, run `sudo apt-get -f install` locally to resume it and make the decision.

## Steam library storage gate

The dedicated client library is the ext4 filesystem whose UUID is recorded in
the machine-local configuration, not a device name: a name such as `/dev/sdXN`
is only the current kernel enumeration. Generate the reviewed root handoff
without running it:

```text
just machine-b steam-library-script \
  --uuid 11111111-2222-4333-8444-555555555555 \
  --output /home/commissioner/.arma-cti/mount-steam-library.sh
```

The generated mode-0700 script resolves `/dev/disk/by-uuid`, requires the UUID
and existing filesystem type `ext4`, refuses an active Steam process, a
non-empty mountpoint, an alternate existing mount, or any conflicting fstab
row. It contains no formatting, partitioning, resizing, or deletion operation.
It keeps the first `/etc/fstab` as
`/etc/fstab.arma-cti-before-steam-library`, validates a candidate fstab before
an atomic replacement, and rolls back this invocation's mount and fstab edit
on failure. The persistent row is:

```text
UUID=11111111-2222-4333-8444-555555555555 /home/cti/SteamLibrary ext4 rw,exec,nosuid,nodev 0 2
```

`exec` is load-bearing: Steam tests that a library can execute content and can
otherwise create `steamapps` yet silently reject the library. At Machine B's
local console, review the script and then run it once with `sudo`. Retain its
single `steam-library=ready ...` evidence line. Do not use Disks, GParted,
`mkfs`, or a format prompt for this already-ext4 filesystem.

The filesystem mount and Steam's registered library root are deliberately two
configuration values. The completed GUI setup registered
`/home/cti/SteamLibrary/SteamLibrary`; app manifests, common applications,
compatdata, and Proton therefore live beneath that nested root. Mount checks
continue to target `/home/cti/SteamLibrary` and must never infer the fstab
mountpoint from Steam's directory layout.

## WSL and Steam gates

The commissioned laptop keeps Windows OpenSSH on 2222 and WSL sshd on 22.
From laptop WSL, run `just machine-b windows-firewall` and approve its Windows
UAC prompt. The command reads B's two addresses from the external TOML and runs
the repository's PowerShell policy, permitting WSL port 22 through both Windows
and Hyper-V firewalls only from those sources. Where mirrored networking does
not bind WSL directly to the laptop's LAN address, it also owns the exact
LAN-address port proxy from port 22 to WSL localhost 22. It does not alter
Windows OpenSSH on port 2222. If mirrored networking does not expose WSL port 22
through Tailscale, use a source-restricted Windows forward on a distinct port
and record that external port as `tailscale_ssh_port`; do not weaken the WSL
listener or UFW. The Windows port-2222 host key is not the WSL trust anchor.

The port proxy replaces the original network source with the Windows-side WSL
gateway. Record that exact gateway as `laptop.wsl_proxy_source`; WSL UFW allows
only that translated source in addition to B's two direct addresses, while the
outer Windows rule continues to admit only B. Never use a subnet or `Anywhere`
for this exception.

At B's console, as `cti`, run
`/home/cti/.local/libexec/install-arma-server`. Enter the no-purchase account,
password, and Guard response only into SteamCMD. Confirm app 233780 and native
`arma3server_x64`.

In the autologged-in `cti` X11 desktop, open Steam and log in with the licensed
test account. Complete Guard and disable unneeded sharing. In **Settings →
Storage**, use **Add Drive** (`+`) to add `/home/cti/SteamLibrary`, then make it
the install destination. Steam may display that selected drive while registering
its actual library root one level beneath it; record the root shown by the
resulting `libraryfolders.vdf` and app manifest. On this host it is
`/home/cti/SteamLibrary/SteamLibrary`. Install app 107410 there. Under Arma 3 **Properties →
Betas**, select no beta; under **Properties → Compatibility**, force **Proton
10.0-4**. Do not select Experimental, Next, Hotfix, GE, or an Arma beta. Let
Steam finish both Arma and the numbered Proton download, then exit Steam
cleanly. Verification requires the app manifest, client executable, and Proton
version beneath the configured registered root, proves that root is on the
configured mounted filesystem, and requires an app-specific `107410` →
`proton_10` mapping. The commissioned read-only facts on 2026-08-12 were
`StateFlags 4`, build `24672225`, size-on-disk `179456235933`, Proton
`1785139158 proton-10.0-4b`, no downloading entries, and 114 GiB free. Valve's
[Storage workflow](https://help.steampowered.com/en/faqs/view/4BD4-4528-6B2E-8327)
uses the same Settings → Storage surface; the Steam for Linux issue tracker
records why a library mount must remain executable.

## Verification and acceptance

```text
just machine-b verify --out ~/.arma-cti/machine-b-verified.json
```

The command emits typed `os`, `identity`, `ssh`, `firewall`, `power`, `gpu`,
`steam`, `engine`, `port`, or `client` failures and checks non-interactive SSH
in all four LAN/Tailscale and forward/reverse paths. Every operational B target
is explicitly `cti@bravo-lan` or `cti@bravo-tail`; only `apply` uses the
configured commissioning identity. This is load-bearing for facts beneath the
mode-0750 `/home/cti`: a manual administrator stat may correctly be denied and
is not the verifier's observer. Retain the following manual evidence in a dated
`~/.arma-cti/runs/` directory:

- password, root, forwarding, wrong-key, unchecked-key, and wrong-source SSH
  attempts fail;
- an unrelated LAN device sees SSH and all tier ports closed; the laptop sees
  only authorized SSH and the three UDP blocks;
- no listener, UFW allowance, or router forwarding exists for 2302–2306;
- a bounded 60-second sequenced UDP exchange receives continuously both ways;
- machine A joins a native server over LAN and A/B engine builds agree;
- killing the initiating SSH holder releases its remote `flock`; the next holder
  clears only that slot and pulls evidence back;
- `just machine-b wake --wait 300` recovers both paths after shutdown;
- one empty-state AC cut/restoration boots B; a no-suspend soak exceeds the old
  idle window while the monitor powers down;
- the three-slot corpus records peak tier RSS and least available memory.

After a green Machine B verify, leave the existing VNC observer attached for
the first attended run and start only the smallest headed-client probe from
laptop WSL:

```text
just regress --host bravo --slots 1 client-port
```

Do not start Steam separately. The harness starts and stops the owned service;
after reviewing its pulled-back evidence and clean teardown, repeat the same
command unattended from laptop WSL.

The per-run `cti-arma-client.service` owns Steam, Proton, and Arma in one user
cgroup, refuses a configured install outside the registered Steam root, uses
`-noLauncher` and `PROTON_LOG=1`, and captures its journal/status, Proton log,
RPT, process tree/cgroup, install paths, manifests, versions, GPU/OS facts, and
exit status. Success, forced failure, timeout, cancellation, and initiator loss
must all leave the service inactive and cgroup empty; broad `pkill wine` or
`killall steam` is forbidden. Finish with every headed-client probe and a full
three-slot pass through `bravo` while the human plays on machine A.

Hardware controls follow the [ASRock manual](https://download.asrock.com/Manual/Z77%20Extreme6.pdf)
and [Ubuntu WOL guidance](https://help.ubuntu.com/community/WakeOnLan). Port
geometry follows vendored `topics/Arma_3_Dedicated_Server.wiki`. The client pin
follows Valve's [Proton versions](https://github.com/ValveSoftware/Proton/wiki/Proton-Versions)
and [10.0-4 release](https://github.com/ValveSoftware/Proton/releases/tag/proton-10.0-4c).
