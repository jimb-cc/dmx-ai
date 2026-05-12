"""Betopper LPC1818 — "10-channel" mode (display: A001).

The manual says 10 channels. It lies. Empirically the fixture in A001 mode
also reads CH11 as a colour-temperature override which, when non-zero,
forces the output to a CCT preset and ignores CH2-7 entirely. We treat the
footprint as 16 channels for safety margin and patch fixtures 16 apart.

Verified channel map (sweep test against real hardware):
    CH1  Master dimmer  (gate; we pin it at 255 and dim in software)
    CH2  Red
    CH3  Green
    CH4  Blue
    CH5  White (lime-ish)
    CH6  Amber
    CH7  UV
    CH8  Strobe (0 = off, ~30-255 slow → fast)
    CH9  Function choice — must stay 0 for direct DMX control
    CH10 Function speed  — keep 0
    CH11 Colour-temp override — MUST be 0 or it overrides CH2-7
    CH12-16 Unused (zeroed for safety)

Set fixtures to: A001 / A017 / A033 / A049 on the rear display.
"""

from __future__ import annotations

CHANNELS = 16
DEFAULT_ADDRESSES = (1, 17, 33, 49)

# Channel offsets from the fixture's DMX base address (0-indexed).
CH = {
    "master": 0,
    "r": 1,
    "g": 2,
    "b": 3,
    "w": 4,
    "a": 5,
    "uv": 6,
    "strobe": 7,
    "func": 8,
    "speed": 9,
    "ct": 10,   # colour temp override — keep at 0
}

_COLOR_OFFSETS = tuple(CH[c] for c in ("r", "g", "b", "w", "a", "uv"))


def _clamp(v) -> int:
    return max(0, min(255, int(v)))


class Fixture:
    """One LPC1818, writing into a shared 512-byte universe buffer."""

    def __init__(self, universe: bytearray, address: int):
        self.u = universe
        self.base = address - 1  # DMX address 1 → array index 0

    def _set(self, ch: str, val) -> None:
        self.u[self.base + CH[ch]] = _clamp(val)

    def set_master(self, val) -> None:
        self._set("master", val)

    def set_color(self, r=0, g=0, b=0, w=0, a=0, uv=0) -> None:
        self._set("r", r)
        self._set("g", g)
        self._set("b", b)
        self._set("w", w)
        self._set("a", a)
        self._set("uv", uv)

    def set_strobe(self, val) -> None:
        """0 = off; ~30–255 slow → fast (exact thresholds vary by firmware)."""
        self._set("strobe", val)

    def off(self) -> None:
        self.set_color(0, 0, 0, 0, 0, 0)
        self.set_strobe(0)

    def scale_color_into(self, dest: bytearray, k: float) -> None:
        """Write a brightness-scaled copy of this fixture's colour channels
        into `dest`. The source universe is left untouched — important for
        scenes that hold a colour across several frames."""
        for off in _COLOR_OFFSETS:
            i = self.base + off
            dest[i] = _clamp(self.u[i] * k)


def build_rig(universe: bytearray, addresses=DEFAULT_ADDRESSES) -> list[Fixture]:
    rig = [Fixture(universe, a) for a in addresses]
    for f in rig:
        # Zero the whole footprint first so CH9-16 (function, speed, colour
        # temp override, and unknown spares) are guaranteed off.
        for i in range(CHANNELS):
            f.u[f.base + i] = 0
        # Pin CH1 (hardware master) wide open. Brightness is controlled in
        # software by scaling CH2-7 — the LPC1818's hardware dimmer is
        # choppy and cuts off hard around DMX ~17.
        f._set("master", 255)
    return rig
