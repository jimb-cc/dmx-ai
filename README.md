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

Three tabs:

- **Inventory** — fixture profiles. Create/edit by hand, import a QLC+
  `.qxf`, or search the Open Fixture Library. Imports are flagged
  *unverified* until you've run a hardware sweep — manuals lie. Verified
  profiles get an **⬆ OFL** button that exports an OFL-format JSON to
  upstream to the Open Fixture Library.
- **Rigging** — top-down stage plot. Click a profile in the palette to add
  it, drag to position, drag the rotation handle to aim. Side panel for
  address / mode / groups; patch table below highlights conflicts in red.
  Auto-patch reassigns addresses footprint-spaced. **Print sheet** gives a
  one-page cheat sheet for the rigging crew. **Export package** bundles
  the rig + its profiles + the setlist into a zip — extract into
  `show/data/` on the Pi and restart.
- **Setlist** — desktop editor for `show/setlist.yaml` with a live preview.
  Pick a song, assign scene / hue / BPM / mover choreography, see what it
  actually looks like — the backend runs the real Show app scene code
  against the rig and animates the result on a stage plot. Saves straight
  to the YAML the Pi reads.

```bash
# on the Pi
unzip gravelaxe-package.zip -d ~/dmx-ai/show/data/
sudo systemctl restart dmx-lights
```

## Fixture setup (current GravelAxe rig)

`data/rigs/gravelaxe.json` — 4 pars + 2 movers, all on universe 1, patched
16 apart:

| ID   | Fixture                 | Mode  | DMX     | Display |
|------|-------------------------|-------|---------|---------|
| FL   | Betopper LPC1818        | 10ch  | 1–16    | `A001`  |
| FR   | Betopper LPC1818        | 10ch  | 17–32   | `A017`  |
| BL   | Betopper LPC1818        | 10ch  | 33–48   | `A033`  |
| BR   | Betopper LPC1818        | 10ch  | 49–64   | `A049`  |
| MOV1 | UKing LED Spot 100W     | 9ch   | 65–80   | `065`   |
| MOV2 | UKing LED Spot 100W     | 9ch   | 81–96   | `081`   |

The same table prints from the Rigging tab's **Print sheet** button.

> **Why 16 apart and not 10?** The LPC1818 manual says A001 mode is 10
> channels. It isn't — the fixture also reads CH11 as a colour-temperature
> override. We zero CH11-16 explicitly and patch 16 apart so adjacent
> fixtures can't tread on it. The profile carries this as `"footprint": 16`
> and a `"lock": true` on CH11. The UKing profile is **unverified** until
> someone runs a sweep — its colour wheel, gobo, and "auto" channels are
> locked at 0 in the meantime.

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

## Movers — choreography layer

Scenes only think about colour. Pan/tilt for movers is driven by a separate
**choreography layer** (`show/choreography.py`) that runs after the scene
scheduler — same idea as the overlays. A small library of patterns (home,
wash, sweep, fan, scan, crossfire, beat snap, circle), each carrying its own
intensity envelope so movers read as accents, not constant light. Auto mode
rotates patterns based on the running scene's mood; pick one manually from
the **Movers** row in the Show UI; pin one per song with a `choreo:` field
in the setlist.

Patterns work in degrees-from-home and convert to channel values using each
profile's `pan_range_deg` / `tilt_range_deg`, so a 30° sweep looks the same
on a 540°-pan mover and a 270°-pan mover. Travel is clamped clear of the
end-stops — slamming a cheap mover against its limit mid-show is loud.
The home aim is tunable from the API without a restart.

The choreo row only shows up if the rig has movers; without them the layer
is a no-op.

## Future / roadmap

Done: repo split, profile-driven encoder, Inventory tab, Rigging tab + show
package export, mover choreography layer, Setlist tab + scene preview, OFL
write-back.

Next:
- **Hardware verification** — sweep the UKing mover with `/test`, flip
  `"verified": true` once the channel map's confirmed; soundcheck the
  choreography home aim (`POST /api/choreo {"home_pan": .., "home_tilt": ..}`).
- **Sound reactivity** — mixer line-out → beat detection. Clean seam in
  `scheduler.py` if/when there's a reliable audio feed.
