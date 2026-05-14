# dmx-ai

DMX lighting controller for a pub rock band. Two apps, two machines:

- **Show app** (`show/`) — runs on a Raspberry Pi at the gig, web UI for a
  phone or tablet, drives the rig over an Enttec DMX USB Pro Mk2. Designed
  to run offline once the show starts.
- **Design app** (`design/`) — runs on a laptop pre-show, React + Vite, for
  building the fixture inventory, the rigging plan, and the show package
  that gets pushed to the Pi.

```
laptop (design/)  ──── show package ────▶  Pi (show/)
React + Vite + Flask       JSON              Flask + Enttec
```

## Layout

```
show/      ← gig-time app (Pi). Flask + scenes + scheduler + Enttec driver.
design/    ← pre-show planning app (laptop). React + Vite frontend, Flask backend.
shared/    ← code both apps need: profile schema, rig schema, channel-map builder.
data/      ← Design app's working files: fixture profiles, rigs, setlists (JSON).
docs/      ← internal design docs (gitignored).
```

## Run the Show app

```bash
cd show
python3 app.py --sim     # no hardware — terminal preview
python3 app.py           # with the Enttec plugged in
```
Then open <http://localhost:8080> on a phone (same wifi). `/setlist` for the
song list, `/test` for the per-channel sweeper.

## Deploy the Show app to the Pi

```bash
make deploy PI=pi@<pi-ip>
ssh pi@<pi-ip>
  sudo apt install python3-flask python3-serial python3-yaml
  sudo cp dmx-ai/show/dmx-lights.service /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable --now dmx-lights
```

The deploy ships only `show/`, `shared/`, and `requirements.txt` — `design/`
and `node_modules/` never touch the Pi.

## Run the Design app

```bash
make design          # Flask backend on :5050
make design-front    # Vite dev server on :5173 (proxies /api → :5050)
```

## Fixture setup (current GravelAxe rig)

4× Betopper LPC1818, 10-channel mode, addresses on the rear display:

| Light | Display |
|-------|---------|
| FL    | `A001`  |
| FR    | `A017`  |
| BL    | `A033`  |
| BR    | `A049`  |

> **Why 16 apart and not 10?** The manual says A001 mode is 10 channels.
> It isn't — the fixture also reads CH11 as a colour-temperature override.
> We zero CH11-16 explicitly and patch 16 apart so adjacent fixtures can't
> tread on it. The `data/profiles/betopper-lpc1818.json` profile carries
> this as `"footprint": 16` and a `"lock": true` on CH11.

## Show app: scenes, overlays, faders

~28 scenes (15 base + 13 mutator variants) tagged by mood for auto-rotation.
Scene changes crossfade over 2.5 s. **Auto** rotates with a recency penalty
and a mood filter; ~50% of auto loads get a random hue shift for variety.

Hold-to-fire **overlays** compose on top of the running scene: ⚡ Strobe,
🔮 UV, 💡 Blinder, 🎨 Flash, ⬛ Blackout. Leased — release within ~1.5s if
the phone drops wifi.

**Master** fader scales colour in software (CH1 pinned at 255 — the LPC1818's
hardware dimmer is choppy). **Floor** fader sets a minimum ambient lift so the
band is never in the dark on a pulse-y scene. **Hue** slider re-colours the
running scene live. **Tap tempo** drives the beat-locked scenes.

## Future / roadmap

The Design app is being built phase by phase — see the design docs.
Sound reactivity (mixer line-out → beat detection) is a clean seam in
`scheduler.py` if/when there's a reliable audio feed.
