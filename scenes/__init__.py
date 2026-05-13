"""Scene registry. Maps scene names to (class, mutator) pairs.

Mutator-derived registrations are first-class catalogue entries — they get
their own button, weight, and recency tracking.
"""

from __future__ import annotations

from scene import Mutator
from scenes import _palettes
from scenes.blackout import Blackout
from scenes.chase import Chase
from scenes.chill import SlowFade
from scenes.embers import Embers
from scenes.hardcuts import HardCuts
from scenes.headlights import Headlights
from scenes.heartbeat import Heartbeat
from scenes.marquee import Marquee
from scenes.pop import ColorPop
from scenes.pulse import Pulse
from scenes.riot import Riot
from scenes.sunrise import SunRise
from scenes.thunderstorm import Thunderstorm
from scenes.uvhaze import UVHaze
from scenes.warm import WarmWash

# name -> (cls, Mutator | None)
REGISTRY: dict[str, tuple[type, Mutator | None]] = {}


def _register(name: str, cls, mutator: Mutator | None = None,
              label: str | None = None, **overrides) -> None:
    if mutator is not None or label is not None or overrides:
        # Subclass with overridden metadata so the scheduler can read class attrs.
        attrs = {"label": label or cls.label}
        attrs.update(overrides)
        cls = type(cls.__name__ + "_" + name, (cls,), attrs)
    REGISTRY[name] = (cls, mutator)


# --- Base scenes ---------------------------------------------------------

_register("blackout", Blackout)
_register("warm", WarmWash)
_register("chill", SlowFade)
_register("pulse", Pulse)
_register("pop", ColorPop)
_register("chase", Chase)
_register("uv", UVHaze)
_register("storm", Thunderstorm)
_register("embers", Embers)
_register("hardcuts", HardCuts)
_register("sunrise", SunRise)
_register("heartbeat", Heartbeat)
_register("riot", Riot)
_register("marquee", Marquee)
_register("headlights", Headlights)

# --- Mutator variants ----------------------------------------------------

_register("manic_pop", ColorPop, Mutator(time_scale=1.7),
          label="⚡ Manic Pop", preferred_duration=(10.0, 25.0))
_register("lazy_pop", ColorPop, Mutator(time_scale=0.55),
          label="🐌 Lazy Pop", weight=0.7)
_register("indie_pop", ColorPop, Mutator(palette=_palettes.INDIE),
          label="🍭 Indie Pop")
_register("reverse_chase", Chase, Mutator(time_scale=1.0, hue_shift_deg=180),
          label="⬅️ Cool Chase")
_register("jewel_chase", Chase, Mutator(palette=_palettes.JEWEL),
          label="💎 Jewel Chase", weight=0.8)
_register("marquee_fast", Marquee, Mutator(time_scale=2.0),
          label="🎰 Marquee Fast", preferred_duration=(15.0, 30.0))
_register("cool_sunrise", SunRise, Mutator(hue_shift_deg=190),
          label="🌌 Moonrise", weight=0.4)
_register("inferno_embers", Embers, Mutator(hue_shift_deg=-20, time_scale=1.4),
          label="🌋 Inferno", weight=0.7)
_register("violet_storm", Thunderstorm, Mutator(hue_shift_deg=40),
          label="🟣 Violet Storm", weight=0.6)
_register("ember_pulse", Pulse, Mutator(palette=_palettes.EMBER),
          label="🟠 Ember Pulse", weight=0.8)
_register("indie_chill", SlowFade, Mutator(palette=_palettes.INDIE),
          label="🌸 Indie Chill")
_register("storm_chill", SlowFade, Mutator(palette=_palettes.STORM),
          label="🌫️ Storm Chill", mood="atmospheric")
_register("heart_stop", Heartbeat, Mutator(brightness_invert=True),
          label="🖤 Heart Stop", weight=0.3, mood="atmospheric")


def catalogue() -> list[dict]:
    """Metadata for the phone UI."""
    out = []
    for name, (cls, mut) in REGISTRY.items():
        out.append({
            "name": name,
            "label": getattr(cls, "label", name),
            "mood": getattr(cls, "mood", "ambient"),
            "weight": getattr(cls, "weight", 1.0),
            "is_strobey": getattr(cls, "is_strobey", False),
            "mutated": mut is not None and not mut.is_identity,
        })
    return out
