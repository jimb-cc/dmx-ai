"""Entry point: render loop + Flask web UI.

    python3 app.py            # auto-detect Enttec, web UI on :8080
    python3 app.py --sim      # no hardware, draw the rig in the terminal
    python3 app.py --port /dev/ttyUSB0 --http-port 80
"""

from __future__ import annotations

import argparse
import logging
import threading
import time

from flask import Flask, jsonify, request, send_from_directory

import choreography
import scenes
from choreography import Choreographer
from enttec import EnttecUSBPro, SimOutput
from fixtures import DEFAULT_RIG, build_rig_from_addresses, build_rig_from_file
from overlays import OverlayStack
from scene import lift_floor
from scheduler import MOODS, SceneScheduler
from setlist import Setlist
from utils import clamp01

FPS = 30
DEFAULT_MASTER = 0.35  # these fixtures are *bright* — start gentle
DEFAULT_FLOOR = 0.12   # min ambient lift so the band is never in the dark
DEFAULT_BPM = 120.0
GAMMA = 1.8            # makes the master fader feel perceptually linear
_ZEROS = bytes(512)

app = Flask(__name__, static_folder="static")
log = logging.getLogger("dmx")


class Ctx:
    """Shared mutable knobs: bpm, master, floor. Read by scenes via scheduler."""

    def __init__(self):
        self.lock = threading.Lock()
        self.bpm = DEFAULT_BPM
        self.master = DEFAULT_MASTER
        self.master_gamma = DEFAULT_MASTER ** GAMMA  # cached for the hot loop
        self.floor = DEFAULT_FLOOR
        self.raw: dict[int, int] | None = None       # test mode

    def set_master(self, v):
        with self.lock:
            self.master = clamp01(float(v))
            self.master_gamma = self.master ** GAMMA

    def set_floor(self, v):
        with self.lock:
            self.floor = clamp01(float(v))

    def set_bpm(self, v):
        with self.lock:
            self.bpm = max(30.0, min(240.0, float(v)))

    def set_raw(self, channels):
        with self.lock:
            if channels is None:
                self.raw = None
            else:
                self.raw = {int(k): max(0, min(255, int(v)))
                            for k, v in channels.items() if 1 <= int(k) <= 512}


ctx = Ctx()
overlays = OverlayStack()
stop_event = threading.Event()
_last_frame = bytearray(512)
_frame_count = [0]

# Built in main() once we know the rig size and setlist path.
scheduler: SceneScheduler | None = None
setlist: Setlist | None = None
choreo: Choreographer | None = None
rig = []


def render_loop(out):
    frame = bytearray(512)
    raw_buf = bytearray(512)
    for f in rig:
        f.init_frame(frame)
    interval = 1.0 / FPS
    last = time.monotonic()
    err_logged = False

    while not stop_event.is_set():
        t0 = time.monotonic()
        dt = min(0.2, t0 - last)
        last = t0

        if ctx.raw is not None:
            raw_buf[:] = _ZEROS
            for ch, val in ctx.raw.items():
                raw_buf[ch - 1] = val
            wire = raw_buf
        else:
            states = scheduler.tick(dt)
            # Mover choreography: drives pan/tilt + intensity for movers only,
            # before floor lift (which never touches dimmer) and overlays
            # (which can still kill the movers — blackout calls off()).
            cur = scheduler.current
            choreo.apply(states, dt, cur.mood if cur else "mixed")
            # Floor lift before overlays so a held blackout still goes dark.
            lift_floor(states, ctx.floor * scheduler.floor_k)
            overlays.apply(states)
            k = ctx.master_gamma
            for i, f in enumerate(rig):
                f.encode(states[i], k, frame)
            wire = frame

        try:
            out.send(wire)
            err_logged = False
        except Exception as e:
            if not err_logged:
                log.error("DMX send failed: %s (will keep retrying)", e)
                err_logged = True
        _last_frame[:] = wire
        _frame_count[0] += 1

        elapsed = time.monotonic() - t0
        if elapsed < interval:
            time.sleep(interval - elapsed)


# --------------------------------------------------------------------------- API

@app.get("/")
def index():
    return send_from_directory("static", "index.html")


@app.get("/test")
def test_page():
    return send_from_directory("static", "test.html")


@app.get("/api/state")
def api_state():
    s = scheduler.status()
    return jsonify(
        **s,
        master=ctx.master,
        floor=ctx.floor,
        bpm=ctx.bpm,
        overlays=overlays.active_names(),
        moods=list(MOODS),
        scenes=scenes.catalogue(),
        choreo=choreo.status(),
        choreos=choreography.catalogue() if choreo.has_movers else [],
    )


@app.post("/api/scene")
def api_scene():
    name = (request.get_json(silent=True) or {}).get("scene", "")
    ctx.set_raw(None)
    ok = scheduler.goto(name)
    return jsonify(ok=ok, scene=scheduler.current_name), (200 if ok else 400)


@app.post("/api/auto")
def api_auto():
    mood = (request.get_json(silent=True) or {}).get("mood", "mixed")
    ctx.set_raw(None)
    scheduler.set_auto(mood)
    return jsonify(ok=True, mode="auto", mood=scheduler.auto_mood)


@app.post("/api/master")
def api_master():
    val = (request.get_json(silent=True) or {}).get("master", ctx.master)
    ctx.set_master(val)
    return jsonify(ok=True, master=ctx.master)


@app.post("/api/floor")
def api_floor():
    val = (request.get_json(silent=True) or {}).get("floor", ctx.floor)
    ctx.set_floor(val)
    return jsonify(ok=True, floor=ctx.floor)


@app.post("/api/hue")
def api_hue():
    deg = float((request.get_json(silent=True) or {}).get("hue", 0.0))
    scheduler.set_hue(deg)
    return jsonify(ok=True, hue=scheduler.status()["hue"])


@app.post("/api/tempo")
def api_tempo():
    val = (request.get_json(silent=True) or {}).get("bpm", ctx.bpm)
    ctx.set_bpm(val)
    return jsonify(ok=True, bpm=ctx.bpm)


@app.post("/api/choreo")
def api_choreo():
    """Set a mover choreography pattern, switch to auto, or tune the home aim.
    Body: {"pattern": "sweep"} | {"auto": true} | {"home_pan": .5, "home_tilt": .4}"""
    body = request.get_json(silent=True) or {}
    if not choreo.has_movers:
        return jsonify(ok=False, error="no movers in this rig"), 400
    if body.get("auto"):
        choreo.set_auto()
    elif "pattern" in body:
        if not choreo.set_pattern(body["pattern"]):
            return jsonify(ok=False, error="unknown pattern"), 400
    if any(k in body for k in ("home_pan", "home_tilt", "spread")):
        choreo.set_home(body.get("home_pan"), body.get("home_tilt"), body.get("spread"))
    return jsonify(ok=True, choreo=choreo.status())


@app.post("/api/overlay")
def api_overlay():
    body = request.get_json(silent=True) or {}
    name = body.get("name", "")
    if bool(body.get("active", True)):
        if not overlays.push(name, body.get("args", {})):
            return jsonify(ok=False, error="unknown overlay"), 400
    else:
        overlays.pop(name)
    return jsonify(ok=True, overlays=overlays.active_names())


@app.post("/api/raw")
def api_raw():
    body = request.get_json(silent=True) or {}
    ctx.set_raw(body.get("channels"))
    return jsonify(ok=True)


@app.get("/api/rig")
def api_rig():
    """Static rig description for the test page — fixtures with their channel
    functions so the sweeper can label sliders and group by fixture."""
    out = []
    for f in rig:
        mode = f.profile.mode(f.mode_id)
        by_off = {c.offset: c for c in mode.channels}
        locked = dict(f.locked)
        chans = []
        for i in range(f.footprint):
            c = by_off.get(i)
            chans.append({
                "ch": f.address + i,
                "function": c.function if c else "—",
                "label": c.label if c else "",
                "lock": locked.get(i),
            })
        out.append({"id": f.id, "label": f.label, "address": f.address,
                    "footprint": f.footprint, "profile": f.profile.id,
                    "model": f"{f.profile.manufacturer} {f.profile.model}".strip(),
                    "type": f.profile.type, "is_mover": f.is_mover,
                    "verified": f.profile.verified, "channels": chans})
    return jsonify(fixtures=out, max_channel=max((f.address + f.footprint - 1 for f in rig), default=16))


@app.get("/api/frame")
def api_frame():
    return jsonify(
        frames_sent=_frame_count[0],
        scene=scheduler.current_name if scheduler else None,
        master=ctx.master,
        raw_mode=ctx.raw is not None,
        overlays=overlays.active_names(),
        # Per-fixture footprint dumps — easier to read than a flat 512-byte slice.
        fixtures=[{
            "id": f.id,
            "address": f.address,
            "profile": f.profile.id,
            "channels": list(_last_frame[f.base:f.base + f.footprint]),
        } for f in rig],
    )


# ----------------------------------------------------------------------- setlist

@app.get("/setlist")
def setlist_page():
    return send_from_directory("static", "setlist.html")


@app.get("/api/setlist")
def api_setlist():
    setlist.load()  # cheap re-read so SSH edits show without a restart
    return jsonify(**setlist.to_dict(), scenes=scenes.catalogue())


def _apply_preset(preset: dict) -> None:
    scene = preset.get("scene")
    if scene and scene in scenes.REGISTRY:
        scheduler.goto(scene, hue=float(preset.get("hue", 0) or 0))
    if preset.get("bpm"):
        ctx.set_bpm(preset["bpm"])
    # Optional per-song mover choreography. "auto" returns to mood-driven
    # rotation; an unknown name is ignored (don't break a song change on a
    # typo in the YAML).
    ch = preset.get("choreo")
    if ch and choreo.has_movers:
        if ch == "auto":
            choreo.set_auto()
        else:
            choreo.set_pattern(ch)


@app.post("/api/setlist/play")
def api_setlist_play():
    idx = int((request.get_json(silent=True) or {}).get("index", -1))
    song = setlist.song(idx)
    if song is None:
        return jsonify(ok=False, error="bad index"), 400
    setlist.set_current(idx)
    _apply_preset(song)
    return jsonify(ok=True, current=idx, scene=scheduler.current_name)


@app.post("/api/setlist/between")
def api_setlist_between():
    setlist.set_current(-1)
    _apply_preset(setlist.to_dict().get("between", {}))
    return jsonify(ok=True, scene=scheduler.current_name)


@app.post("/api/setlist/edit")
def api_setlist_edit():
    body = request.get_json(silent=True) or {}
    idx = int(body.get("index", -1))
    fields = body.get("fields", {})
    if not setlist.update_song(idx, fields):
        return jsonify(ok=False, error="bad index"), 400
    return jsonify(ok=True, **setlist.to_dict())


# --------------------------------------------------------------------------- main

def main():
    global scheduler, setlist, choreo, rig
    p = argparse.ArgumentParser(description="DMX show controller")
    p.add_argument("--port", help="serial port for the Enttec (auto-detect if omitted)")
    p.add_argument("--sim", action="store_true", help="no hardware — draw to terminal")
    p.add_argument("--http-port", type=int, default=8080)
    p.add_argument("--rig", default=None,
                   help=f"path to a rig JSON (default: {DEFAULT_RIG})")
    p.add_argument("--addresses", default=None,
                   help="quick override: comma-separated DMX addresses, "
                        "all assumed to be LPC1818 10ch (e.g. 1,17,33,49)")
    p.add_argument("--setlist", default="setlist.yaml", help="path to a setlist YAML")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.addresses:
        addresses = tuple(int(a) for a in args.addresses.split(","))
        rig = build_rig_from_addresses(addresses)
        log.info("Rig: %d fixtures from --addresses override", len(rig))
    else:
        rig, rig_def = build_rig_from_file(args.rig)
        log.info("Rig: %s — %d fixtures (%s)", rig_def.name, len(rig),
                 ", ".join(f"{f.id}@{f.address}" for f in rig))

    scheduler = SceneScheduler(len(rig), scenes.REGISTRY, ctx)
    scheduler.set_auto("mixed")
    choreo = Choreographer(rig, ctx)
    if choreo.has_movers:
        choreo.set_auto()
        log.info("Choreography: %d movers (%s) — auto rotation",
                 len(choreo.movers), ", ".join(m.label for m in choreo.movers))
    setlist = Setlist(args.setlist)
    log.info("Setlist: %s (%d songs)", setlist.to_dict()["name"],
             len(setlist.to_dict()["songs"]))

    if args.sim:
        out = SimOutput(rig)
        log.info("Running in simulator mode (terminal preview)")
    else:
        out = EnttecUSBPro(args.port)
        log.info("Connected to Enttec on %s", out.port_name)

    t = threading.Thread(target=render_loop, args=(out,), daemon=True)
    t.start()

    log.info("Web UI: http://0.0.0.0:%d  |  scenes: %d", args.http_port, len(scenes.REGISTRY))
    try:
        app.run(host="0.0.0.0", port=args.http_port, threaded=True, use_reloader=False)
    finally:
        stop_event.set()
        t.join(timeout=1)
        out.close()
        log.info("Blackout sent, bye.")


if __name__ == "__main__":
    main()
