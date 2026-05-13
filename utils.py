"""Small math/easing/stochastics utilities for scene authoring.

Pure functions, no dependencies. Vendored rather than pulling in
opensimplex/numpy — at four fixtures and 30 fps the visible difference
between simplex noise and a couple of dephased sine LFOs is nil.

This is a scene-author's library: not every function is in use today, but
they're the standard building blocks for the kinds of scenes this rig runs.
Trim if the project never grows past the current catalogue.
"""

from __future__ import annotations

import colorsys
import math


# ---------------------------------------------------------------------------
# Interpolation & easing (input/output 0..1 unless noted)
# ---------------------------------------------------------------------------

def clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def smoothstep(edge0: float, edge1: float, x: float) -> float:
    t = clamp01((x - edge0) / (edge1 - edge0)) if edge1 != edge0 else 0.0
    return t * t * (3.0 - 2.0 * t)


def in_sine(t: float) -> float:
    return 1.0 - math.cos(t * math.pi / 2.0)


def out_sine(t: float) -> float:
    return math.sin(t * math.pi / 2.0)


def in_out_sine(t: float) -> float:
    return 0.5 - 0.5 * math.cos(math.pi * t)


def in_cubic(t: float) -> float:
    return t * t * t


def out_cubic(t: float) -> float:
    u = 1.0 - t
    return 1.0 - u * u * u


def in_out_cubic(t: float) -> float:
    return 4 * t * t * t if t < 0.5 else 1 - ((-2 * t + 2) ** 3) / 2


def out_back(t: float, s: float = 1.70158) -> float:
    u = t - 1.0
    return 1.0 + u * u * ((s + 1.0) * u + s)


# ---------------------------------------------------------------------------
# Waves (period in seconds, returns 0..1)
# ---------------------------------------------------------------------------

def sine01(t: float, period: float, phase: float = 0.0) -> float:
    return 0.5 - 0.5 * math.cos(2.0 * math.pi * (t / period + phase))


def triangle_wave(t: float, period: float) -> float:
    p = (t / period) % 1.0
    return 2.0 * p if p < 0.5 else 2.0 * (1.0 - p)


def saw_wave(t: float, period: float) -> float:
    return (t / period) % 1.0


def pulse_train(t: float, period: float, duty: float = 0.5) -> float:
    return 1.0 if ((t / period) % 1.0) < duty else 0.0


# ---------------------------------------------------------------------------
# Cheap "noise": sum of dephased sines.  Not actual Perlin/Simplex, but at
# 4 fixtures / 30 fps the audience cannot tell — and it has zero dependencies.
# Returns 0..1 with a roughly noise-like spectrum.
# ---------------------------------------------------------------------------

def noise1d(t: float, seed: float = 0.0) -> float:
    s = seed * 12.9898
    v = (
        math.sin(t * 1.000 + s * 1.0)
        + 0.6 * math.sin(t * 2.137 + s * 2.3 + 1.7)
        + 0.4 * math.sin(t * 3.971 + s * 3.1 + 4.2)
        + 0.2 * math.sin(t * 7.523 + s * 4.7 + 0.6)
    ) / 2.2
    return 0.5 + 0.5 * v


# ---------------------------------------------------------------------------
# Stochastics
# ---------------------------------------------------------------------------

def poisson_event(rng, dt: float, mean_interval: float) -> bool:
    """Bernoulli per-tick approximation. Fine when dt << mean_interval."""
    if mean_interval <= 0:
        return False
    return rng.random() < dt / mean_interval


def next_exponential(rng, mean_interval: float) -> float:
    """Exponentially-distributed interarrival time."""
    return -mean_interval * math.log(max(1e-9, 1.0 - rng.random()))


# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------

def hue_shift_rgb(r: float, g: float, b: float, deg: float) -> tuple[float, float, float]:
    """Rotate an RGB triple's hue by `deg` degrees (HSV space)."""
    if deg == 0.0 or (r == 0.0 and g == 0.0 and b == 0.0):
        return (r, g, b)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    h = (h + deg / 360.0) % 1.0
    return colorsys.hsv_to_rgb(h, s, v)
