"""Scene base class, fixture state, and the mutator system.

A Scene is an object with a `tick(dt)` method that mutates a list of
`FixtureState` floats. The scheduler crossfades between two Scenes by
running both and lerping their fixture states.

Mutators are post-processing transforms applied to a Scene's output:
hue rotation, time scaling, brightness inversion, palette substitution.
They let one scene class produce several catalogue entries.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from utils import clamp01, hue_shift_rgb


# Channel names that crossfade and that mutators touch.
COLOUR_FIELDS = ("r", "g", "b", "lime", "amber", "uv")


@dataclass
class FixtureState:
    """Floating-point colour state for one fixture, 0..1 linear.
    The scheduler converts to DMX bytes after crossfade + overlays + master."""

    r: float = 0.0
    g: float = 0.0
    b: float = 0.0
    lime: float = 0.0
    amber: float = 0.0
    uv: float = 0.0
    strobe: int = 0  # raw DMX byte; not crossfaded, not mutated

    def set(self, r=0.0, g=0.0, b=0.0, lime=0.0, amber=0.0, uv=0.0) -> None:
        self.r, self.g, self.b = clamp01(r), clamp01(g), clamp01(b)
        self.lime, self.amber, self.uv = clamp01(lime), clamp01(amber), clamp01(uv)

    def set_rgb(self, r: float, g: float, b: float) -> None:
        self.r, self.g, self.b = clamp01(r), clamp01(g), clamp01(b)

    def add(self, r=0.0, g=0.0, b=0.0, lime=0.0, amber=0.0, uv=0.0) -> None:
        self.r = clamp01(self.r + r)
        self.g = clamp01(self.g + g)
        self.b = clamp01(self.b + b)
        self.lime = clamp01(self.lime + lime)
        self.amber = clamp01(self.amber + amber)
        self.uv = clamp01(self.uv + uv)

    def scale(self, k: float) -> None:
        for f in COLOUR_FIELDS:
            setattr(self, f, clamp01(getattr(self, f) * k))

    def off(self) -> None:
        self.r = self.g = self.b = self.lime = self.amber = self.uv = 0.0
        self.strobe = 0

    def copy_from(self, other: "FixtureState") -> None:
        self.r, self.g, self.b = other.r, other.g, other.b
        self.lime, self.amber, self.uv = other.lime, other.amber, other.uv
        self.strobe = other.strobe


def lerp_states(a: FixtureState, b: FixtureState, k: float, out: FixtureState) -> None:
    """Blend two fixture states into `out`. Strobe does not crossfade — held
    off mid-fade, snaps to the incoming scene's value once the fade completes."""
    inv = 1.0 - k
    out.r = a.r * inv + b.r * k
    out.g = a.g * inv + b.g * k
    out.b = a.b * inv + b.b * k
    out.lime = a.lime * inv + b.lime * k
    out.amber = a.amber * inv + b.amber * k
    out.uv = a.uv * inv + b.uv * k
    out.strobe = b.strobe if k >= 1.0 else (a.strobe if k <= 0.0 else 0)


@dataclass
class Mutator:
    """Cheap variant generator: hue-rotate, time-scale, invert, palette-swap."""

    hue_shift_deg: float = 0.0
    time_scale: float = 1.0          # negative reverses; <1 slower; >1 faster
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
                f.r, f.g, f.b = 1.0 - f.r, 1.0 - f.g, 1.0 - f.b
                f.lime, f.amber = 1.0 - f.lime, 1.0 - f.amber
                # leave UV — inverting it is rarely what you want
        if self.hue_shift_deg:
            d = self.hue_shift_deg
            for f in fx:
                f.r, f.g, f.b = hue_shift_rgb(f.r, f.g, f.b, d)
                # lime/amber/UV are off the RGB hue circle — leave them


class Scene:
    """Base class. Subclasses set the class attrs and implement `tick(dt)`."""

    name: str = "scene"
    label: str = ""                        # short UI label, defaults to name
    mood: str = "ambient"                  # ambient|driving|spectacle|atmospheric|nature|glitch
    weight: float = 1.0                    # auto-rotation weight
    preferred_duration: tuple[float, float] = (25.0, 45.0)
    is_strobey: bool = False               # exclude from auto unless mood=driving
    palette: list = field(default_factory=list)

    def __init__(self, n_fixtures: int, rng: random.Random, ctx,
                 mutator: Mutator | None = None):
        self.fx = [FixtureState() for _ in range(n_fixtures)]
        self.rng = rng
        self.ctx = ctx        # exposes .bpm
        self.t = 0.0
        self.mutator = mutator or Mutator()
        if self.mutator.palette is not None:
            self.palette = self.mutator.palette
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
        """Apply time scaling, run tick(), apply mutators."""
        ts = self.mutator.time_scale
        self.tick(dt * abs(ts) if ts != 1.0 else dt)
        if not self.mutator.is_identity:
            self.mutator.apply(self.fx)

    # --- helpers for subclasses ------------------------------------------

    @property
    def bpm(self) -> float:
        return max(30.0, min(240.0, float(getattr(self.ctx, "bpm", 120.0))))

    def beat_secs(self, beats: float = 1.0) -> float:
        return (60.0 / self.bpm) * beats

    def all(self, fn) -> None:
        for f in self.fx:
            fn(f)
