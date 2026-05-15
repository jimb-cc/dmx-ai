"""Scene base class, fixture state, and the mutator system.

A Scene is an object with a `tick(dt)` method that mutates a list of
`FixtureState` floats. The scheduler crossfades between two Scenes by
running both and lerping their fixture states.

Mutators are post-processing transforms applied to a Scene's output:
hue rotation, time scaling, brightness inversion, palette substitution.
They let one scene class produce several catalogue entries.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from utils import clamp01, hue_shift_rgb


@dataclass
class FixtureState:
    """Floating-point fixture state, 0..1 linear (except strobe, raw byte).
    The scheduler converts to DMX bytes after crossfade + overlays + master.
    Scenes write colour fields; only mover-aware scenes touch pan/tilt."""

    r: float = 0.0
    g: float = 0.0
    b: float = 0.0
    white: float = 0.0
    lime: float = 0.0
    amber: float = 0.0
    uv: float = 0.0
    strobe: int = 0    # raw DMX byte; not crossfaded, not mutated
    pan: float = 0.5   # 0..1, 0.5 = centre. Encoder maps to pan + pan_fine.
    tilt: float = 0.5
    dimmer: float = 1.0

    def set(self, r=0.0, g=0.0, b=0.0, lime=0.0, amber=0.0, uv=0.0, white=0.0) -> None:
        self.r, self.g, self.b = clamp01(r), clamp01(g), clamp01(b)
        self.lime, self.amber, self.uv = clamp01(lime), clamp01(amber), clamp01(uv)
        self.white = clamp01(white)

    def set_rgb(self, r: float, g: float, b: float) -> None:
        self.set(r, g, b)

    def set_pan_tilt(self, pan: float, tilt: float) -> None:
        self.pan, self.tilt = clamp01(pan), clamp01(tilt)

    def off(self) -> None:
        self.r = self.g = self.b = self.white = 0.0
        self.lime = self.amber = self.uv = 0.0
        self.strobe = 0
        self.dimmer = 0.0  # mover's only intensity channel — off means off
        # leave pan/tilt — a mover going dark shouldn't snap to centre

    def copy_from(self, other: "FixtureState") -> None:
        self.r, self.g, self.b, self.white = other.r, other.g, other.b, other.white
        self.lime, self.amber, self.uv = other.lime, other.amber, other.uv
        self.strobe = other.strobe
        self.pan, self.tilt, self.dimmer = other.pan, other.tilt, other.dimmer


def lerp_states(a: FixtureState, b: FixtureState, k: float, out: FixtureState) -> None:
    """Blend two fixture states into `out`. Strobe does not crossfade — held
    off mid-fade, snaps to the incoming scene's value once the fade completes."""
    inv = 1.0 - k
    out.r = a.r * inv + b.r * k
    out.g = a.g * inv + b.g * k
    out.b = a.b * inv + b.b * k
    out.white = a.white * inv + b.white * k
    out.lime = a.lime * inv + b.lime * k
    out.amber = a.amber * inv + b.amber * k
    out.uv = a.uv * inv + b.uv * k
    out.pan = a.pan * inv + b.pan * k
    out.tilt = a.tilt * inv + b.tilt * k
    out.dimmer = a.dimmer * inv + b.dimmer * k
    out.strobe = b.strobe if k >= 1.0 else (a.strobe if k <= 0.0 else 0)


def lift_floor(states: list[FixtureState], floor: float) -> None:
    """Remap each visible colour channel from [0,1] to [floor,1] so the rig
    never goes fully dark on a pulse/pop scene. UV is left alone — adding UV
    to the ambient floor reads as a purple haze, not 'the band is lit'."""
    if floor <= 0.0:
        return
    span = 1.0 - floor
    for s in states:
        s.r = floor + s.r * span
        s.g = floor + s.g * span
        s.b = floor + s.b * span
        s.white = floor + s.white * span
        s.lime = floor + s.lime * span
        s.amber = floor + s.amber * span


@dataclass
class Mutator:
    """Cheap variant generator: hue-rotate, time-scale, invert, palette-swap."""

    hue_shift_deg: float = 0.0
    time_scale: float = 1.0          # speeds up (>1) or slows down (<1)
    brightness_invert: bool = False
    palette: list | None = None      # overrides scene's self.palette if set

    @property
    def is_identity(self) -> bool:
        return (self.hue_shift_deg == 0.0 and self.time_scale == 1.0
                and not self.brightness_invert and self.palette is None)

    def apply(self, fx: list[FixtureState]) -> None:
        """In-place post-processing of the scene's rendered fixture states."""
        if self.brightness_invert:
            for f in fx:
                f.r, f.g, f.b, f.white = 1.0 - f.r, 1.0 - f.g, 1.0 - f.b, 1.0 - f.white
                f.lime, f.amber = 1.0 - f.lime, 1.0 - f.amber
                # leave UV — inverting it is rarely what you want
        if self.hue_shift_deg:
            d = self.hue_shift_deg
            for f in fx:
                f.r, f.g, f.b = hue_shift_rgb(f.r, f.g, f.b, d)
                # white/lime/amber/UV are off the RGB hue circle — leave them


class Scene:
    """Base class. Subclasses set the class attrs and implement `tick(dt)`."""

    name: str = "scene"
    label: str = "scene"
    mood: str = "ambient"            # one of scheduler.MOODS (minus "mixed")
    weight: float = 1.0              # auto-rotation weight; 0 = never auto-picked
    preferred_duration: tuple[float, float] = (25.0, 45.0)
    is_strobey: bool = False         # excluded from auto unless mood is driving/glitch
    respects_floor: bool = True      # False → floor lift skipped (blackout)
    palette: list | tuple = ()

    def __init__(self, n_fixtures: int, rng: random.Random, ctx,
                 mutator: Mutator | None = None, hue: float = 0.0):
        self.fx = [FixtureState() for _ in range(n_fixtures)]
        self.rng = rng
        self.ctx = ctx               # exposes .bpm
        self.t = 0.0
        self.mutator = mutator or Mutator()
        if self.mutator.palette is not None:
            self.palette = self.mutator.palette
        # Live hue shift — set by the scheduler at instantiation (0 for manual
        # loads, random for ~50% of auto loads) and updatable from the UI.
        # Composes with the mutator's hue shift; only touches RGB.
        self.hue = hue % 360.0
        # Cache mutator behaviour — checked every frame, immutable after init.
        self._dt_scale = abs(self.mutator.time_scale)
        self._mut_active = not self.mutator.is_identity
        self.on_enter()

    # --- subclass hooks ---------------------------------------------------

    def on_enter(self) -> None:
        """Called once at construction. Reset state, seed initial palette."""

    def on_exit(self) -> None:
        """Called once when the scene is being faded out."""

    def tick(self, dt: float) -> None:
        """Mutate self.fx in place. dt is already mutator-time-scaled."""
        self.t += dt

    # --- driven by the scheduler -----------------------------------------

    def step(self, dt: float) -> None:
        # Strobe is opt-in per frame; reset before tick so scenes that want
        # it set it explicitly and the rest never have to think about it.
        for f in self.fx:
            f.strobe = 0
        self.tick(dt * self._dt_scale)
        if self._mut_active:
            self.mutator.apply(self.fx)
        if self.hue:
            for f in self.fx:
                f.r, f.g, f.b = hue_shift_rgb(f.r, f.g, f.b, self.hue)

    # --- helpers for subclasses ------------------------------------------

    @property
    def bpm(self) -> float:
        # ctx.bpm is already clamped at the API boundary.
        return float(getattr(self.ctx, "bpm", 120.0))

    def beat_secs(self, beats: float = 1.0) -> float:
        return (60.0 / self.bpm) * beats

    def all(self, fn) -> None:
        for f in self.fx:
            fn(f)

    def random_phases(self) -> list[float]:
        return [self.rng.random() * math.tau for _ in self.fx]
