"""Light shows.

Each scene is a generator function `scene(rig, fps, ctx)` that runs forever,
writing into the fixtures each frame and `yield`ing once per tick.
The render loop drives it at a steady frame rate.

`ctx` carries shared live state — currently just `.bpm`, set from the
phone UI's tap-tempo / tempo slider. Beat-locked scenes re-read it at the
top of every beat so tempo changes take effect immediately.

To add a scene: write a generator, add it to SCENES, add a button in
static/index.html.
"""

from __future__ import annotations

import math
import random


# Saturated, stage-friendly colours. (r, g, b) — white/amber/uv used directly
# in the few scenes that want them.
PALETTE_ROCK = [
    (255, 0, 0),       # red
    (0, 40, 255),      # blue
    (255, 0, 110),     # magenta
    (255, 70, 0),      # orange
    (0, 210, 255),     # cyan
    (160, 0, 255),     # purple
    (0, 255, 60),      # green
    (255, 255, 255),   # white
]

PALETTE_COOL = [
    (0, 40, 255),
    (0, 210, 255),
    (160, 0, 255),
    (255, 0, 110),
    (40, 0, 200),
]


def _all(rig, fn):
    for f in rig:
        fn(f)


def _beat_frames(ctx, fps, beats=1.0):
    """Frames per `beats` at the current tempo. Re-read each beat so
    tap-tempo changes take effect on the next downbeat."""
    bpm = max(30.0, min(240.0, float(getattr(ctx, "bpm", 120.0))))
    return max(1, int((60.0 / bpm) * beats * fps))


# ---------------------------------------------------------------------------
# Scenes
# ---------------------------------------------------------------------------

def blackout(rig, fps, ctx):
    while True:
        _all(rig, lambda f: f.off())
        yield


def warm_wash(rig, fps, ctx):
    """Warm amber/white glow with a slow drift. Between songs, banter."""
    phases = [random.random() * math.tau for _ in rig]
    t = 0.0
    while True:
        for i, f in enumerate(rig):
            k = 0.5 + 0.5 * math.sin(t * 0.35 + phases[i])
            f.set_color(r=200 + 55 * k, g=70 + 50 * k, b=0,
                        w=20 + 20 * k, a=140 + 90 * k)
            f.set_strobe(0)
        t += 1.0 / fps
        yield


def slow_fade(rig, fps, ctx):
    """Slow random colour cross-fades, each fixture independent. Ballads.
    Fade length is 4 bars at the current tempo so it breathes with the song."""
    pal = PALETTE_COOL
    cur = [random.choice(pal) for _ in rig]
    nxt = [random.choice(pal) for _ in rig]
    while True:
        steps = _beat_frames(ctx, fps, beats=16)  # 4 bars of 4
        for s in range(steps):
            k = s / steps
            for i, f in enumerate(rig):
                f.set_color(
                    r=cur[i][0] + (nxt[i][0] - cur[i][0]) * k,
                    g=cur[i][1] + (nxt[i][1] - cur[i][1]) * k,
                    b=cur[i][2] + (nxt[i][2] - cur[i][2]) * k,
                )
                f.set_strobe(0)
            yield
        cur, nxt = nxt, [random.choice(pal) for _ in rig]


def color_pop(rig, fps, ctx):
    """Hard random colour cuts on the beat. Mid/up-tempo rock."""
    while True:
        col = random.choice(PALETTE_ROCK)
        roll = random.random()
        if roll < 0.25:
            tgt = random.randrange(len(rig))
            for i, f in enumerate(rig):
                f.set_color(*(col if i == tgt else (0, 0, 0)))
        elif roll < 0.45:
            col2 = random.choice(PALETTE_ROCK)
            for i, f in enumerate(rig):
                f.set_color(*(col if i % 2 == 0 else col2))
        else:
            _all(rig, lambda f: f.set_color(*col))
        _all(rig, lambda f: f.set_strobe(0))
        for _ in range(_beat_frames(ctx, fps, beats=1)):
            yield


def chase(rig, fps, ctx):
    """Single colour ping-pongs across the rig with a dim tail.
    One step per half-beat."""
    n = len(rig)
    order = list(range(n)) + list(range(n - 2, 0, -1))  # 0 1 2 3 2 1 ...
    while True:
        col = random.choice(PALETTE_ROCK)
        for pos in order:
            for i, f in enumerate(rig):
                if i == pos:
                    f.set_color(*col)
                elif abs(i - pos) == 1:
                    f.set_color(*(c // 5 for c in col))
                else:
                    f.set_color(0, 0, 0)
                f.set_strobe(0)
            for _ in range(_beat_frames(ctx, fps, beats=0.5)):
                yield


def pulse(rig, fps, ctx):
    """Whole rig breathes in one colour, snapping to a new one each bar.
    Sharp attack, long decay — feels like a kick drum."""
    while True:
        col = random.choice(PALETTE_ROCK)
        beat = _beat_frames(ctx, fps, beats=1)
        for b in range(4):  # one bar
            for s in range(beat):
                phase = s / beat
                k = max(0.15, math.exp(-phase * 4.0))
                _all(rig, lambda f, k=k: f.set_color(
                    r=col[0] * k, g=col[1] * k, b=col[2] * k))
                _all(rig, lambda f: f.set_strobe(0))
                yield


def strobe_burst(rig, fps, ctx):
    """Full white hardware strobe. Hold-to-fire from the UI."""
    while True:
        _all(rig, lambda f: f.set_color(r=255, g=255, b=255, w=255))
        _all(rig, lambda f: f.set_strobe(230))
        yield


def uv_haze(rig, fps, ctx):
    """Deep blue + UV wash with a slow shimmer. Spooky intros."""
    phases = [random.random() * math.tau for _ in rig]
    t = 0.0
    while True:
        for i, f in enumerate(rig):
            k = 0.5 + 0.5 * math.sin(t * 0.5 + phases[i])
            f.set_color(r=0, g=0, b=60 + 40 * k, uv=180 + 75 * k)
            f.set_strobe(0)
        t += 1.0 / fps
        yield


def auto(rig, fps, ctx):
    """Hands-off mode. Rotates random scenes every 20–40 s, never strobes."""
    pool = [warm_wash, slow_fade, color_pop, chase, pulse, uv_haze]
    weights = [1, 2, 3, 2, 2, 1]  # favour the punchier ones
    while True:
        scene_fn = random.choices(pool, weights=weights, k=1)[0]
        inner = scene_fn(rig, fps, ctx)
        for _ in range(int(random.uniform(20, 40) * fps)):
            next(inner)
            yield


SCENES = {
    "auto": auto,
    "warm": warm_wash,
    "chill": slow_fade,
    "pulse": pulse,
    "pop": color_pop,
    "chase": chase,
    "uv": uv_haze,
    "strobe": strobe_burst,
    "blackout": blackout,
}
