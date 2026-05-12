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

FPS = 30
DEFAULT_MASTER = 0.35  # these fixtures are *bright* — start gentle
DEFAULT_BPM = 120.0
GAMMA = 1.8            # makes the master fader feel perceptually linear

app = Flask(__name__, static_folder="static")
log = logging.getLogger("dmx")


class State:
    """Shared between Flask handler threads and the render thread."""

    def __init__(self):
        self.lock = threading.Lock()
        self.scene = "auto"
        self.master = DEFAULT_MASTER
        self.bpm = DEFAULT_BPM
        self._scene_changed = True
        # Raw test mode: when not None, the render loop sends exactly these
        # channel values and ignores scenes/master entirely.
        self.raw = None  # type: dict[int, int] | None

    def set_scene(self, name: str) -> bool:
        if name not in scenes.SCENES:
            return False
        with self.lock:
            self.raw = None
            if name != self.scene:
                self.scene = name
                self._scene_changed = True
        return True

    def set_master(self, val) -> None:
        with self.lock:
            self.master = max(0.0, min(1.0, float(val)))

    def set_bpm(self, val) -> None:
        with self.lock:
            self.bpm = max(30.0, min(240.0, float(val)))

    def set_raw(self, channels: dict | None) -> None:
        with self.lock:
            if channels is None:
                self.raw = None
                self._scene_changed = True  # force scene rebuild on exit
            else:
                self.raw = {int(k): max(0, min(255, int(v)))
                            for k, v in channels.items()
                            if 1 <= int(k) <= 512}

    def snapshot(self):
        with self.lock:
            changed, self._scene_changed = self._scene_changed, False
            return self.scene, self.master, changed, self.raw


state = State()
stop_event = threading.Event()

# Debug: snapshot of the last frame actually handed to the Enttec.
_last_frame = bytearray(512)
_frame_count = [0]


def render_loop(out, addresses):
    # `universe` holds the scene's full-brightness output. `wire` is what we
    # actually send — a master-scaled copy. Keeping them separate means scenes
    # that hold a colour for N frames don't get re-scaled N times.
    universe = bytearray(512)
    wire = bytearray(512)
    raw_buf = bytearray(512)
    rig = build_rig(universe, addresses)
    gen = scenes.SCENES[state.scene](rig, FPS, state)
    interval = 1.0 / FPS
    err_logged = False

    while not stop_event.is_set():
        t0 = time.monotonic()
        name, master, changed, raw = state.snapshot()

        if raw is not None:
            # Test mode: send exactly what the user set, nothing else.
            raw_buf[:] = bytes(512)
            for ch, val in raw.items():
                raw_buf[ch - 1] = val
            frame = raw_buf
        else:
            if changed:
                gen = scenes.SCENES[name](rig, FPS, state)
            next(gen)
            # Software master with a gamma curve so the fader feels linear.
            # CH1 (hardware master) is pinned at 255 in build_rig().
            wire[:] = universe
            k = master ** GAMMA
            for f in rig:
                f.scale_color_into(wire, k)
            frame = wire

        try:
            out.send(frame)
            err_logged = False
        except Exception as e:  # USB hiccup — keep the loop alive
            if not err_logged:
                log.error("DMX send failed: %s (will keep retrying)", e)
                err_logged = True
        _last_frame[:] = frame
        _frame_count[0] += 1
        dt = time.monotonic() - t0
        if dt < interval:
            time.sleep(interval - dt)


# ---------------------------------------------------------------------------
# Web API
# ---------------------------------------------------------------------------

@app.get("/")
def index():
    return send_from_directory("static", "index.html")


@app.get("/api/state")
def api_state():
    return jsonify(scene=state.scene, master=state.master, bpm=state.bpm,
                   scenes=list(scenes.SCENES.keys()))


@app.post("/api/scene")
def api_scene():
    name = (request.get_json(silent=True) or {}).get("scene", "")
    ok = state.set_scene(name)
    return jsonify(ok=ok, scene=state.scene), (200 if ok else 400)


@app.post("/api/master")
def api_master():
    val = (request.get_json(silent=True) or {}).get("master", state.master)
    state.set_master(val)
    return jsonify(ok=True, master=state.master)


@app.post("/api/tempo")
def api_tempo():
    val = (request.get_json(silent=True) or {}).get("bpm", state.bpm)
    state.set_bpm(val)
    return jsonify(ok=True, bpm=state.bpm)


@app.get("/test")
def test_page():
    return send_from_directory("static", "test.html")


@app.post("/api/raw")
def api_raw():
    body = request.get_json(silent=True) or {}
    state.set_raw(body.get("channels"))
    return jsonify(ok=True)


@app.get("/api/frame")
def api_frame():
    """Debug: returns the first 40 channels of the last DMX frame sent."""
    return jsonify(
        frames_sent=_frame_count[0],
        scene=state.scene,
        master=state.master,
        raw_mode=state.raw is not None,
        ch1_40=list(_last_frame[:40]),
    )


# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(description="DMX controller for 4× Betopper LPC1818")
    p.add_argument("--port", help="serial port for the Enttec (auto-detect if omitted)")
    p.add_argument("--sim", action="store_true", help="no hardware — draw to terminal")
    p.add_argument("--http-port", type=int, default=8080)
    p.add_argument("--addresses", default=",".join(map(str, DEFAULT_ADDRESSES)),
                   help="comma-separated DMX base addresses (default 1,11,21,31)")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    addresses = tuple(int(a) for a in args.addresses.split(","))

    if args.sim:
        out = SimOutput(addresses, CHANNELS)
        log.info("Running in simulator mode (terminal preview)")
    else:
        out = EnttecUSBPro(args.port)
        log.info("Connected to Enttec on %s", out.port_name)

    t = threading.Thread(target=render_loop, args=(out, addresses), daemon=True)
    t.start()

    log.info("Web UI: http://0.0.0.0:%d", args.http_port)
    try:
        app.run(host="0.0.0.0", port=args.http_port, threaded=True, use_reloader=False)
    finally:
        stop_event.set()
        t.join(timeout=1)
        out.close()  # sends a blackout frame
        log.info("Blackout sent, bye.")


if __name__ == "__main__":
    main()
