"""Hold-to-fire overlays that compose on top of the running scene.

Overlays are leased: each `POST /api/overlay {"name":..., "active":true}`
sets a TTL of ~1.5s. The phone re-sends every ~1s while a button is held.
If the phone vanishes (wifi drop, crash, pocket-dial), the lease expires and
the overlay auto-releases — no stuck strobe at the end of the night.

Priority order, lowest → highest:
    uv_boost < flash < blinder < strobe < blackout
"""

from __future__ import annotations

import time

from scene import FixtureState

LEASE_TTL = 1.5  # seconds; phone re-sends ~every 1.0s while held

# Render order: lower index = applied first = overridden by later overlays.
PRIORITY = ("uv_boost", "flash", "blinder", "strobe", "blackout")


def apply_uv_boost(states, _args):
    """Add a UV layer to every fixture, leave visible colours alone."""
    for s in states:
        s.uv = max(s.uv, 0.85)


def apply_flash(states, args):
    """Override all fixtures with a single colour. `args` carries r/g/b 0..255."""
    r = (args.get("r", 255)) / 255.0
    g = (args.get("g", 255)) / 255.0
    b = (args.get("b", 255)) / 255.0
    for s in states:
        s.r, s.g, s.b = r, g, b
        s.lime = s.amber = 0.0
        # leave UV — flash + UV-boost composes nicely


def apply_blinder(states, args):
    """Front pair to full warm white (lime+amber+r). args may carry 'front'
    list of fixture indices; defaults to [0, 1]."""
    front = set(args.get("front", (0, 1)))
    for i, s in enumerate(states):
        if i in front:
            s.r, s.g, s.b = 1.0, 0.55, 0.10
            s.lime, s.amber = 0.9, 1.0
            s.strobe = 0


def apply_strobe(states, args):
    """Full white hardware strobe on top of whatever's running."""
    rate = int(args.get("rate", 230))
    for s in states:
        s.r = s.g = s.b = 1.0
        s.lime = s.amber = 0.6
        s.strobe = rate


def apply_blackout(states, _args):
    for s in states:
        s.off()


_APPLY = {
    "uv_boost": apply_uv_boost,
    "flash": apply_flash,
    "blinder": apply_blinder,
    "strobe": apply_strobe,
    "blackout": apply_blackout,
}


class OverlayStack:
    """Tracks active leased overlays and applies them in priority order."""

    def __init__(self):
        # name -> (expiry_monotonic, args_dict)
        self._active: dict[str, tuple[float, dict]] = {}

    def push(self, name: str, args: dict | None = None) -> bool:
        if name not in _APPLY:
            return False
        self._active[name] = (time.monotonic() + LEASE_TTL, args or {})
        return True

    def pop(self, name: str) -> None:
        self._active.pop(name, None)

    def active_names(self) -> list[str]:
        self._gc()
        return [n for n in PRIORITY if n in self._active]

    def apply(self, states: list[FixtureState]) -> None:
        self._gc()
        for name in PRIORITY:
            entry = self._active.get(name)
            if entry is not None:
                _APPLY[name](states, entry[1])

    def _gc(self) -> None:
        now = time.monotonic()
        stale = [n for n, (exp, _) in self._active.items() if exp < now]
        for n in stale:
            del self._active[n]
