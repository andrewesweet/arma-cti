# Playtest 0001 — the Commander seat

**What this session buys.** Two acceptance criteria on #18 that only eyes can discharge — the map
UI as rendered, and a refusal appearing on screen — plus first contact with two placeholder
numbers that are waiting on your feel to be signed off: the `decapitation` weight of 8.0 (#34) and
the 90 s HQ demolition rate (#33).

**Budget: 40 minutes.** Three minutes to bring the world up, half an hour in the seat, the rest
writing terse answers into `docs/playtest/0001-response.md`. Answer in fragments; nothing here
wants a paragraph.

## Before you start

- `just build-shim-windows` — CLAUDE.md asks for it before a play session.
- Close any Arma 3 client you have open. The harness kills `arma3_x64.exe` on teardown, and it
  cannot tell yours from the one it launched.
- The Arma tier is single-occupancy. If the boot line reports the lock held, an agent has the
  tier: that is `infra_unavailable`, not a result, and the answer is to wait rather than to force
  it.

## Boot line

```bash
CTI_AI_SIDE=EAST CTI_AI_SEED=1 CTI_WINDOWS_CLIENT=1 CTI_PROBE_SOAK=1800 \
    just probe spike/playtest/session-hold.sqf 2100
```

That brings up the daemon, the dedicated server on 2402 and your own client, windowed and already
connected — your side of the port space is untouched. EAST comes up under an AI Commander on seed
1, so the session replays if you want it again; WEST comes up under nobody, because a side already
has a Commander refuses your Commands `wrong_side` (ADR-0025). The fixture holds the world for
thirty minutes, or until somebody wins.

In the lobby, take the **NATO Commander** slot. The first thing to check is that the hint says
`Commander — WEST`; if it says EAST, you are in the wrong slot and the port will tell you so.

If you would rather use your own client and profile: Direct Connect to `127.0.0.1` port `2402`,
password `ctispike`, and drop `CTI_WINDOWS_CLIENT=1` from the boot line. Your client needs the
addon — copy `.hemttout/build/addons` into an `@cti` folder in your Arma 3 directory and launch
with `-mod=@cti`.

**This boot line is unverified.** No agent has run it: the tier was in use and a playtest brief is
not a reason to take it. If the fixture is broken the world still stands for the full window and
the run simply ends red afterwards — you lose the verdict, not the session.

## The controls, as they are meant to work

Open the map. Click a Place — an Objective or a Base — to select it; clicking open country selects
nothing on purpose. Then the number row: `1` Capture, `2` Defend, `3` Assault, `4` Reserve,
`5` Rifle Squad, `6` Weapons Squad. `Tab` cycles which of your Squads the next Order names.

Two different clocks share that screen and it is worth knowing which is which before you judge it:
the picture rides the world's 5 s report and is up to five seconds stale, while a judgement on a
Command you just sent comes back on its own and immediately.

## Scenario 1 — read the panel (5 min)

Take the seat, open the map, and read what is on screen before touching anything. You should find
your side, Funds, Squad and Contact counts, the selected Place and Squad, and a key legend, with
your own Squads and your Contacts as markers.

- Could you tell what you had and what you could do, without being told? **y / n**
- Rate the hint panel's legibility. **1–5**
- Rate the markers' legibility — could you tell your Squads from your Contacts at a glance?
  **1–5**
- Did the picture ever look wrong rather than merely late? **y / n** — if yes, what.
- What felt wrong?

## Scenario 2 — buy one, send it (7 min)

Purchase a Rifle Squad, `Tab` to it, click a town, press `1`. Watch the Squad's marker and the
Order text on it. Then give it something else to do.

- Did the click → pick a verb → issued loop read as one action? **y / n**
- Did you ever press a number and not know whether anything had happened? **y / n**
- Where did your eye go for the answer — the hint, the marker, the world? **pick one**
- Did the five-second staleness bother you in play? **not at all / noticed it / it misled me**
- What felt wrong?

## Scenario 3 — get refused, three ways (5 min)

Three refusals, on purpose: Capture a town you already hold (`already_held`), Capture a **Base**
(`wrong_ground`), and buy past your Funds (`insufficient_funds`).

- Did each refusal appear on screen? **y / y / y — or name the one that did not**
- Did you read a reason, or just a red word? **reason / red word**
- Did it tell you what to do instead? **y / n**
- Did you ever have to look at the log to understand a refusal? **y / n**
- What felt wrong?

## Scenario 4 — play it out against EAST (15 min)

Now command properly and let the AI Commander play. It has the same verbs you do. Watch for two
things in particular, and note the in-game minute for each.

The first is when EAST turns for **your Base**. At `decapitation = 8.0` a Squad should raid your HQ
once it has ground to spare, and should not abandon towns to do it — the measured window is
(7.27, 8.87) and above the top of it EAST leaves a town it just took to rush you.

The second is your **HQ under an Assault**, if it happens: an enemy Squad with a man inside the
Order's ground brings the building down at a fixed 90 s.

- Did EAST come for your Base? **y / n** — at what minute.
- If it did: earned or cheap? **earned / cheap / too late to matter**
- Did EAST ever abandon ground it had just taken in order to raid you? **y / n**
- If your HQ was worked on: how did 90 s feel? **too fast / about right / too slow** — and did you
  have time to react?
- Did the Campaign end this session? **y / n** — how.
- Did EAST read as a competent opponent? **1–5**
- What felt wrong?

## Two things this brief does not have

There is no standing perceptual checklist yet. Growing one is a human sign-off gate, so this brief
does not invent it; if anything in the four scenarios above deserves to be looked at in *every*
future session, say so at the bottom of the response and it becomes the first entry.

And there is no scenario for taking an enemy HQ yourself. A Squad marches Stratis end to end in
something like forty minutes, so ordering the Assault and watching it land does not fit in one
session. The 90 s number is therefore only judged here from the receiving end, and only if EAST
obliges.
