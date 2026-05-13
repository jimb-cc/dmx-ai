# dmx-ai

Quick-and-dirty DMX controller for a pub rock band.
4× Betopper LPC1818 → Enttec DMX USB Pro Mk2 → Raspberry Pi → phone web UI.

## Fixture setup (do this once on each light)

Set each LPC1818 to **10-channel mode** with these addresses on the rear display:

| Light | Display |
|-------|---------|
| 1     | `A001`  |
| 2     | `A017`  |
| 3     | `A033`  |
| 4     | `A049`  |

(`A` prefix = 10-ch mode. Daisy-chain DMX from the Enttec → light 1 → 2 → 3 → 4,
terminator on the last one if you have it.)

> **Why 16 apart and not 10?** The manual says A001 mode is 10 channels. It isn't.
> The fixture also reads **CH11 as a colour-temperature override** which, when
> non-zero, ignores the RGB channels entirely. We zero CH11-16 explicitly and
> patch fixtures 16 apart so they can't tread on each other.

## Run on your Mac (dev)

```bash
pip3 install -r requirements.txt
python3 app.py --sim     # no hardware — shows the rig as colour blocks in terminal
python3 app.py           # with the Enttec plugged in
```

Then open <http://localhost:8080> on your phone (same wifi).

## Deploy to the Pi

```bash
make deploy PI=pi@<pi-ip>
ssh pi@<pi-ip>
  sudo apt install python3-flask python3-serial   # or pip install -r requirements.txt
  sudo cp dmx-ai/dmx-lights.service /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable --now dmx-lights
```

It now starts at boot. Plug the Pi + Enttec in at the venue, join the band's
wifi on your phone, go to `http://<pi-ip>/`.

## Scenes

~28 scenes (15 base + 13 mutator variants), each tagged with a mood for the
auto-rotation filter:

- **ambient** — Warm, Chill, Embers, Indie Chill, Storm Chill, Ember Pulse
- **driving** — Pop, Pulse, Chase, Hard Cuts, Riot, Marquee + variants
- **spectacle** — Sun Rise, Heartbeat, Headlights, Moonrise
- **atmospheric** — UV, Storm (thunderstorm), Heart Stop

Switching scenes crossfades over 2.5 s. **Auto** mode rotates random scenes
every 25–90 s with a recency penalty (never repeats back-to-back, avoids the
last 4) and a mood filter so it doesn't run a slow ambient under a punk number.

## Overlays (hold to fire, sticky bottom row)

These compose **on top of** the running scene — release and the scene is
still there. Leased: if your phone drops wifi mid-hold, the overlay
auto-releases within ~1.5 s.

| Button   | What it does |
|----------|--------------|
| ⚡ Strobe   | Full white hardware strobe. |
| 🔮 UV       | Adds a UV layer. Lights up white shirts. |
| 💡 Blinder  | Front pair to full warm white. The "big chorus" button. |
| 🎨 Flash    | All fixtures to the picked swatch colour. |
| ⬛ Black    | Hard blackout while held. (There's also a Blackout scene for sustained darkness.) |

Priority: blackout > strobe > blinder > flash > UV — so holding blackout +
strobe gives you blackout, and holding flash + strobe gives a coloured strobe.

## Master & tempo

The **Master** fader scales the colour channels in software (CH1 is pinned
at 255 — the hardware dimmer is choppy with a dead zone). Gamma-corrected
so the slider feels linear. Defaults to 35% — these fixtures are blinding.

**Tap tempo** or the **BPM slider** drives the beat-locked scenes (Pop,
Chase, Pulse, Hard Cuts, Marquee). Changes lock in on the next beat.

## Tuning

- DMX addresses: `python3 app.py --addresses 1,17,33,49`
- Scene timing/colours: edit `scenes.py` (each scene is ~15 lines, plain Python).
- Strobe speed: `set_strobe(230)` in `scenes.py` — lower = slower.

## Future: sound-reactive

There's a clean seam for it: a thread reading a USB/line-in audio source can
call `state.set_scene(...)` and bump a shared BPM value that `pop`/`pulse`/
`chase` read instead of their hardcoded defaults. Not built yet because the
mixer line-out isn't a sure thing.
