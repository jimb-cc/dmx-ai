"""Fixture profile schema, validation, and channel-map building.

A profile describes a fixture model's channel layout per mode. Both the Show
app (encode FixtureState → DMX) and the Design app (Inventory tab editor,
Rigging tab patcher) use this module.

We learned the hard way that fixture manuals lie about channel maps (the
LPC1818 reads CH11 as a colour-temp override the manual never mentions).
Profiles carry a `verified` flag — false until someone has run a hardware
sweep on the real fixture — and a `footprint` per mode that may exceed the
documented channel count to leave defensive zeroes.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

# Closed vocabulary the encoder understands. Anything else maps to "none"
# and is left at its default value (or 0).
FUNCTIONS = (
    # intensity
    "master_dimmer", "dimmer",
    # additive colour emitters
    "red", "green", "blue", "white", "lime", "amber", "uv",
    "cyan", "magenta", "yellow", "warm_white", "cool_white",
    # effects
    "strobe", "shutter",
    # position
    "pan", "pan_fine", "tilt", "tilt_fine", "pan_tilt_speed",
    # beam
    "gobo", "gobo_rotation", "color_wheel", "zoom", "focus", "iris",
    "prism", "frost",
    # control / housekeeping
    "macro", "macro_speed", "ct_override", "speed", "reset", "lamp",
    "none",
)

# Functions that the encoder scales by master/floor (i.e. colour channels).
COLOUR_FUNCTIONS = frozenset({
    "red", "green", "blue", "white", "lime", "amber", "uv",
    "cyan", "magenta", "yellow", "warm_white", "cool_white",
})

FIXTURE_TYPES = ("par", "mover", "batten", "strobe", "wash", "spot", "generic")


@dataclass
class Channel:
    offset: int
    function: str
    default: int = 0
    lock: bool = False
    label: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "Channel":
        return cls(
            offset=int(d["offset"]),
            function=str(d.get("function", "none")),
            default=int(d.get("default", 0)),
            lock=bool(d.get("lock", False)),
            label=str(d.get("label", "")),
        )

    def to_dict(self) -> dict:
        out = {"offset": self.offset, "function": self.function}
        if self.default:
            out["default"] = self.default
        if self.lock:
            out["lock"] = True
        if self.label:
            out["label"] = self.label
        return out


@dataclass
class Mode:
    id: str
    label: str
    footprint: int
    channels: list[Channel] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "Mode":
        chans = [Channel.from_dict(c) for c in d.get("channels", [])]
        # footprint defaults to 1 past the highest channel offset.
        max_off = max((c.offset for c in chans), default=-1)
        return cls(
            id=str(d["id"]),
            label=str(d.get("label", d["id"])),
            footprint=int(d.get("footprint", max_off + 1)),
            channels=chans,
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "footprint": self.footprint,
            "channels": [c.to_dict() for c in self.channels],
        }


@dataclass
class Profile:
    id: str
    manufacturer: str = ""
    model: str = ""
    type: str = "generic"
    physical: dict = field(default_factory=dict)
    verified: bool = False
    modes: list[Mode] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "Profile":
        return cls(
            id=str(d["id"]),
            manufacturer=str(d.get("manufacturer", "")),
            model=str(d.get("model", "")),
            type=str(d.get("type", "generic")),
            physical=dict(d.get("physical", {})),
            verified=bool(d.get("verified", False)),
            modes=[Mode.from_dict(m) for m in d.get("modes", [])],
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "type": self.type,
            "physical": self.physical,
            "verified": self.verified,
            "modes": [m.to_dict() for m in self.modes],
        }

    def mode(self, mode_id: str) -> Mode:
        for m in self.modes:
            if m.id == mode_id:
                return m
        raise KeyError(f"profile {self.id!r} has no mode {mode_id!r}")

    @property
    def beam_deg(self) -> float:
        return float(self.physical.get("beam_deg", 25.0))

    @property
    def pan_range_deg(self) -> float:
        return float(self.physical.get("pan_range_deg", 540.0))

    @property
    def tilt_range_deg(self) -> float:
        return float(self.physical.get("tilt_range_deg", 270.0))


def validate(profile: Profile) -> list[str]:
    """Return a list of human-readable validation errors. Empty = OK."""
    errs = []
    if not profile.id:
        errs.append("profile has no id")
    if profile.type not in FIXTURE_TYPES:
        errs.append(f"unknown fixture type {profile.type!r} (one of {FIXTURE_TYPES})")
    if not profile.modes:
        errs.append("profile has no modes")
    for m in profile.modes:
        offs = [c.offset for c in m.channels]
        if len(offs) != len(set(offs)):
            errs.append(f"mode {m.id!r} has duplicate channel offsets")
        if offs and max(offs) >= m.footprint:
            errs.append(f"mode {m.id!r} footprint {m.footprint} is smaller than "
                        f"the highest channel offset {max(offs)}")
        funcs = [c.function for c in m.channels if c.function != "none"]
        for fn in funcs:
            if fn not in FUNCTIONS:
                errs.append(f"mode {m.id!r} channel offset {m.channels[funcs.index(fn)].offset} "
                            f"has unknown function {fn!r}")
        # The same function appearing twice (except "none") is almost always a mistake.
        seen = set()
        for fn in funcs:
            if fn in seen:
                errs.append(f"mode {m.id!r} has function {fn!r} on more than one channel")
            seen.add(fn)
    return errs


def build_channel_map(profile: Profile, mode_id: str) -> dict[str, int]:
    """function name -> 0-indexed channel offset for a fixture in `mode_id`.
    The Show app's Fixture.encode() reads this; "none" channels are excluded."""
    m = profile.mode(mode_id)
    return {c.function: c.offset for c in m.channels if c.function != "none"}


def locked_channels(profile: Profile, mode_id: str) -> list[tuple[int, int]]:
    """[(offset, default), ...] for channels written once and never touched."""
    m = profile.mode(mode_id)
    return [(c.offset, c.default) for c in m.channels if c.lock]


# ---------------------------------------------------------------------------
# Profile registry
# ---------------------------------------------------------------------------

class ProfileRegistry:
    """Load and look up profiles from a directory of JSON files."""

    def __init__(self, path: str | None = None):
        self.path = path
        self._by_id: dict[str, Profile] = {}
        if path and os.path.isdir(path):
            self.load_dir(path)

    def load_dir(self, path: str) -> None:
        for fn in sorted(os.listdir(path)):
            if not fn.endswith(".json"):
                continue
            try:
                with open(os.path.join(path, fn), encoding="utf-8") as f:
                    p = Profile.from_dict(json.load(f))
                self._by_id[p.id] = p
            except Exception as e:
                # Don't crash the whole registry on one bad file.
                print(f"profile.py: skipped {fn}: {e}")

    def add(self, profile: Profile) -> None:
        self._by_id[profile.id] = profile

    def get(self, profile_id: str) -> Profile:
        if profile_id not in self._by_id:
            raise KeyError(f"unknown fixture profile {profile_id!r} "
                           f"(known: {sorted(self._by_id)})")
        return self._by_id[profile_id]

    def all(self) -> list[Profile]:
        return list(self._by_id.values())

    def __contains__(self, profile_id: str) -> bool:
        return profile_id in self._by_id

    def __len__(self) -> int:
        return len(self._by_id)
