"""Scene preview renderer.

Runs the Show app's scene code server-side and returns per-fixture screen
RGB approximations so the Design app can show "what does Embers with hue
200 look like on my rig" without setting up the hardware.

Imports `show/scenes/` directly — the Design backend lives on the laptop
next to the show app, never on the Pi, so the cross-package import is fine.
The render loop here is the same shape as `show/app.py`'s but with no
hardware, no overlays, and no choreography: a 2-D colour preview can't show
pan/tilt anyway, and overlays are gig-time.
"""

from __future__ import annotations

import os
import random
import sys
from types import SimpleNamespace

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_show = os.path.join(_root, "show")
for p in (_root, _show):
    if p not in sys.path:
        sys.path.insert(0, p)

import choreography  # noqa: E402  (show/choreography.py)
import scenes  # noqa: E402  (show/scenes/)
from choreography import Choreographer  # noqa: E402
from fixtures import build_rig_from_file  # noqa: E402  (show/fixtures.py)
from scene import FixtureState, lift_floor  # noqa: E402

# Same fold as enttec.SimOutput — secondary emitters → screen RGB.
_BLEND = {
    "white":  (0.95, 0.95, 0.95),
    "lime":   (0.55, 0.95, 0.10),
    "amber":  (1.00, 0.55, 0.00),
    "uv":     (0.30, 0.00, 0.95),
    "dimmer": (0.95, 0.85, 0.70),  # colour-wheel mover, locked to open white
}


def catalogue() -> list[dict]:
    """Pass the Show app's scene catalogue through verbatim."""
    return scenes.catalogue()


def choreo_catalogue() -> list[dict]:
    return choreography.catalogue()


def render(scene_name: str, *, hue: float = 0.0, bpm: float = 120.0,
           floor: float = 0.12, secs: float = 6.0, fps: int = 12,
           choreo: str | None = None, rig_path: str | None = None) -> dict:
    """Run a scene (and optionally a choreography pattern) for `secs` seconds
    and return per-fixture screen colours.

    Returns: {fixtures: [{id, type, x, y, mover}], frames: [[[r,g,b]/fixture]],
              fps, beam: [[(pan,tilt,inten)/mover]]}
    Frames are 0..255 ints. `beam` is per-frame mover pan/tilt/intensity in
    0..1 channel space so the frontend can swing the beam cones; empty if
    the rig has no movers or choreo is "home"/None.
    Raises KeyError on an unknown scene.
    """
    if scene_name not in scenes.REGISTRY:
        raise KeyError(scene_name)
    cls, mut = scenes.REGISTRY[scene_name]
    fixtures, rig = build_rig_from_file(rig_path)
    n = len(fixtures)
    ctx = SimpleNamespace(bpm=float(bpm))
    rng = random.Random(0xDEADBEEF)  # deterministic so the preview loops cleanly
    sc = cls(n, rng, ctx, mutator=mut, hue=float(hue) % 360.0)
    sc.name = scene_name

    # Choreography in manual mode — pin one pattern for the preview. Without
    # it, auto mode would immediately auto-rotate to a random pattern (the
    # initial _auto_until is 0). If no pattern is given, hold "home" so
    # movers show as dark accents, not constant light.
    pat = choreo if choreo in choreography.PATTERNS else "home"
    chor = Choreographer(fixtures, ctx, default=pat)
    chor.set_pattern(pat)  # forces manual mode and starts the xfade from rest
    mover_idx = [m.index for m in chor.movers]

    # Per-fixture: which FixtureState attrs map to screen colour.
    colours = [f.colour_channels for f in fixtures]
    fx_meta = [{"id": f.id, "type": f.profile.type,
                "x": rf.x, "y": rf.y, "mover": f.is_mover}
               for f, rf in zip(fixtures, rig.fixtures)]

    # The scheduler gives us a separate blend buffer; here we make our own so
    # choreo/floor mutations don't feed back into the scene's own state and
    # accumulate frame-over-frame (multiplicative dimmer decay was the bug).
    states = [FixtureState() for _ in range(n)]
    eff_floor = floor if cls.respects_floor else 0.0

    n_frames = max(1, int(secs * fps))
    dt = 1.0 / fps
    frames: list[list[list[int]]] = []
    beams: list[list[list[float]]] = []
    for _ in range(n_frames):
        sc.step(dt)
        for i in range(n):
            states[i].copy_from(sc.fx[i])
        chor.apply(states, dt, sc.mood)
        lift_floor(states, eff_floor)
        frame = []
        for i, st in enumerate(states):
            r = g = b = 0.0
            for attr in colours[i]:
                v = getattr(st, attr, 0.0)
                if attr == "r":
                    r += v
                elif attr == "g":
                    g += v
                elif attr == "b":
                    b += v
                else:
                    br, bg, bb = _BLEND.get(attr, (0, 0, 0))
                    r += v * br
                    g += v * bg
                    b += v * bb
            frame.append([min(255, int(r * 255)), min(255, int(g * 255)), min(255, int(b * 255))])
        frames.append(frame)
        beams.append([[round(states[i].pan, 3), round(states[i].tilt, 3),
                       round(states[i].dimmer, 3)] for i in mover_idx])

    return {"fixtures": fx_meta, "frames": frames, "beams": beams, "fps": fps,
            "scene": scene_name, "hue": float(hue), "bpm": float(bpm),
            "choreo": chor.pattern, "movers": mover_idx}
