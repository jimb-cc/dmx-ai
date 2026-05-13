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

import scenes
from enttec import EnttecUSBPro, SimOutput
from fixtures import CHANNELS, DEFAULT_ADDRESSES, build_rig
from overlays import OverlayStack
from scene import lift_floor
from scheduler import MOODS, SceneScheduler
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

# Built in main() once we know the rig size.
scheduler: SceneScheduler | None = None
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


@app.post("/api/tempo")
def api_tempo():
    val = (request.get_json(silent=True) or {}).get("bpm", ctx.bpm)
    ctx.set_bpm(val)
    return jsonify(ok=True, bpm=ctx.bpm)


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


@app.get("/api/frame")
def api_frame():
    return jsonify(
        frames_sent=_frame_count[0],
        scene=scheduler.current_name if scheduler else None,
        master=ctx.master,
        raw_mode=ctx.raw is not None,
        overlays=overlays.active_names(),
        ch1_64=list(_last_frame[:64]),
    )


# --------------------------------------------------------------------------- main

def main():
    global scheduler, rig
    p = argparse.ArgumentParser(description="DMX controller for 4× Betopper LPC1818")
    p.add_argument("--port", help="serial port for the Enttec (auto-detect if omitted)")
    p.add_argument("--sim", action="store_true", help="no hardware — draw to terminal")
    p.add_argument("--http-port", type=int, default=8080)
    p.add_argument("--addresses", default=",".join(map(str, DEFAULT_ADDRESSES)),
                   help="comma-separated DMX base addresses (default 1,17,33,49)")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    addresses = tuple(int(a) for a in args.addresses.split(","))
    rig = build_rig(addresses)
    scheduler = SceneScheduler(len(rig), scenes.REGISTRY, ctx)
    scheduler.set_auto("mixed")

    if args.sim:
        out = SimOutput(addresses, CHANNELS)
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
