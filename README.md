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

| Button   | What it does |
|----------|--------------|
| Auto     | Hands-off — rotates random scenes every 20–40 s. Default on boot. |
| Warm     | Amber/white wash with slow drift. Between songs. |
| Chill    | Slow random colour cross-fades. Ballads. |
| Pulse    | Whole rig breathes in one colour, kick-drum decay. |
| Pop      | Hard random colour cuts on a beat clock. Rock. |
| Chase    | Colour ping-pongs across the four lights. |
| UV       | Deep blue + UV shimmer. Spooky intros. |
| Strobe   | **Hold to fire.** Full white hardware strobe; releases to previous scene. |
| Blackout | Everything off, instantly. |

The **Master** slider sets CH1 (hardware dimmer) on all four fixtures.
Defaults to 35% — these things are blinding in a small room.

## Tuning

- DMX addresses: `python3 app.py --addresses 1,17,33,49`
- Scene timing/colours: edit `scenes.py` (each scene is ~15 lines, plain Python).
- Strobe speed: `set_strobe(230)` in `scenes.py` — lower = slower.

## Future: sound-reactive

There's a clean seam for it: a thread reading a USB/line-in audio source can
call `state.set_scene(...)` and bump a shared BPM value that `pop`/`pulse`/
`chase` read instead of their hardcoded defaults. Not built yet because the
mixer line-out isn't a sure thing.
