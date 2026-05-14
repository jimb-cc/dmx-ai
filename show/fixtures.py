"""Profile-driven DMX fixture encoder.

A `Fixture` is built from a `shared.profile.Profile` + mode + address.
At construction it precomputes an encode plan (which `FixtureState` field
maps to which channel offset), so the hot path is a flat list iteration —
no dict lookups, no branching on profile type.

`init_frame()` zeroes the fixture's footprint and writes locked channel
defaults once. `encode()` writes the live state every frame and never
touches locked channels.
"""

from __future__ import annotations

import os
import sys

# Make shared/ importable when running from show/ or anywhere else.
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from shared.profile import (  # noqa: E402
    Profile, ProfileRegistry, build_channel_map, locked_channels,
)
from shared.rig import Rig, load as load_rig  # noqa: E402

# Default location for the show package's data on the Pi. Falls back to the
# repo-root data/ when running from a dev checkout.
DEFAULT_PROFILES_DIR = next(
    (p for p in (
        os.path.join(os.path.dirname(__file__), "data", "profiles"),
        os.path.join(_root, "data", "profiles"),
    ) if os.path.isdir(p)),
    os.path.join(_root, "data", "profiles"),
)
DEFAULT_RIG = next(
    (p for p in (
        os.path.join(os.path.dirname(__file__), "data", "rig.json"),
        os.path.join(_root, "data", "rigs", "gravelaxe.json"),
    ) if os.path.isfile(p)),
    os.path.join(_root, "data", "rigs", "gravelaxe.json"),
)


# Maps profile `function` names to (FixtureState attr, scale_by_master).
# Colour channels are scaled by the software master; `dimmer` is too because
# on colour-wheel fixtures it's the only intensity channel.
_FUNC_TO_ATTR: dict[str, tuple[str, bool]] = {
    "red": ("r", True),
    "green": ("g", True),
    "blue": ("b", True),
    "white": ("white", True),
    "warm_white": ("white", True),
    "cool_white": ("white", True),
    "lime": ("lime", True),
    "amber": ("amber", True),
    "uv": ("uv", True),
    "strobe": ("strobe", False),
    "dimmer": ("dimmer", True),
}


def _byte(v: float) -> int:
    return max(0, min(255, int(v * 255.0 + 0.5)))


class Fixture:
    """One physical fixture — encodes a FixtureState into the wire frame."""

    def __init__(self, fx_id: str, profile: Profile, mode_id: str, address: int,
                 *, label: str = "", groups: list[str] | None = None):
        self.id = fx_id
        self.label = label or fx_id
        self.profile = profile
        self.mode_id = mode_id
        self.base = address - 1
        self.address = address
        self.groups = list(groups or [])
        self.is_mover = profile.type == "mover"

        chan = build_channel_map(profile, mode_id)
        self.footprint = profile.mode(mode_id).footprint
        self.locked: list[tuple[int, int]] = locked_channels(profile, mode_id)
        locked_offsets = {off for off, _ in self.locked}

        # Encode plan: (offset, FixtureState attr, scale_by_master)
        self._plan: list[tuple[int, str, bool]] = []
        for fn, off in chan.items():
            if off in locked_offsets:
                continue
            spec = _FUNC_TO_ATTR.get(fn)
            if spec:
                self._plan.append((off, spec[0], spec[1]))

        # Pan/tilt are 16-bit when a fine channel exists.
        def _free(name):
            off = chan.get(name)
            return off if off is not None and off not in locked_offsets else None
        self._pan = _free("pan")
        self._pan_fine = _free("pan_fine")
        self._tilt = _free("tilt")
        self._tilt_fine = _free("tilt_fine")
        self.has_pan_tilt = self._pan is not None or self._tilt is not None

        # Capability summary for scenes.
        self.colour_channels = frozenset(a for _, a, c in self._plan if c)

    def init_frame(self, frame: bytearray) -> None:
        """Zero the fixture's footprint and write locked defaults once."""
        for i in range(self.footprint):
            frame[self.base + i] = 0
        for off, default in self.locked:
            frame[self.base + off] = default

    def encode(self, st, master_k: float, frame: bytearray) -> None:
        b = self.base
        for off, attr, scale in self._plan:
            v = getattr(st, attr)
            if attr == "strobe":
                frame[b + off] = max(0, min(255, int(v)))
            elif scale:
                frame[b + off] = _byte(v * master_k)
            else:
                frame[b + off] = _byte(v)
        if self._pan is not None:
            p16 = max(0, min(65535, int(st.pan * 65535.0 + 0.5)))
            frame[b + self._pan] = p16 >> 8
            if self._pan_fine is not None:
                frame[b + self._pan_fine] = p16 & 0xFF
        if self._tilt is not None:
            t16 = max(0, min(65535, int(st.tilt * 65535.0 + 0.5)))
            frame[b + self._tilt] = t16 >> 8
            if self._tilt_fine is not None:
                frame[b + self._tilt_fine] = t16 & 0xFF


# ---------------------------------------------------------------------------
# Rig builder
# ---------------------------------------------------------------------------

def build_rig_from_file(rig_path: str | None = None,
                        profiles_dir: str | None = None) -> tuple[list[Fixture], Rig]:
    """Load a rig JSON and build the Fixture list. Raises on validation errors."""
    profiles = ProfileRegistry(profiles_dir or DEFAULT_PROFILES_DIR)
    rig = load_rig(rig_path or DEFAULT_RIG, profiles)
    errs = rig.validate()
    if errs:
        raise ValueError(f"rig {rig.name!r} invalid:\n  " + "\n  ".join(errs))
    fixtures = [Fixture(f.id, profiles.get(f.profile), f.mode, f.address,
                        label=f.label, groups=f.groups) for f in rig.fixtures]
    return fixtures, rig


def build_rig_from_addresses(addresses: tuple[int, ...],
                             profile_id: str = "betopper-lpc1818",
                             mode_id: str = "10ch",
                             profiles_dir: str | None = None) -> list[Fixture]:
    """Quick override: N copies of one profile at the given addresses.
    Used by the legacy `--addresses` CLI flag and the test harness."""
    profiles = ProfileRegistry(profiles_dir or DEFAULT_PROFILES_DIR)
    p = profiles.get(profile_id)
    labels = ("FL", "FR", "BL", "BR")
    return [Fixture(labels[i] if i < len(labels) else f"FX{i+1}", p, mode_id, a)
            for i, a in enumerate(addresses)]
