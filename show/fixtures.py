"""Betopper LPC1818 — "10-channel" mode (display: A001).

The manual says 10 channels and an RGBW emitter set. **Both are wrong.**
Empirically verified against real hardware (May 2026, sweep test):

    CH1  Master dimmer  (gate; we pin it at 255 and dim in software)
    CH2  Red
    CH3  Green
    CH4  Blue
    CH5  Lime    (manual calls this "White" — it isn't)
    CH6  Amber
    CH7  UV
    CH8  Strobe (0 = off, ~30-255 slow → fast)
    CH9  Function choice — must stay 0 for direct DMX control
    CH10 Function speed  — keep 0
    CH11 Colour-temp override — **MUST be 0** or it overrides CH2-7 entirely
    CH12-16 Unused (zeroed for safety margin)

CH11 is the one that bites: it isn't documented, but if it's non-zero the
fixture ignores the colour channels and forces a CCT preset. We patch
fixtures 16 apart so adjacent fixtures can't tread on each other's CH11.

Set fixtures to: A001 / A017 / A033 / A049 on the rear display.
"""

from __future__ import annotations

from scene import FixtureState

CHANNELS = 16
DEFAULT_ADDRESSES = (1, 17, 33, 49)

# 0-indexed offsets from the fixture's DMX base address.
OFF_MASTER = 0
OFF_R = 1
OFF_G = 2
OFF_B = 3
OFF_LIME = 4
OFF_AMBER = 5
OFF_UV = 6
OFF_STROBE = 7
OFF_FUNC = 8
OFF_SPEED = 9
OFF_CT = 10  # colour-temp override — must stay 0


def _byte(v: float) -> int:
    """Convert a 0..1 float to a clamped DMX byte."""
    return max(0, min(255, int(v * 255.0 + 0.5)))


class Fixture:
    """One LPC1818 — encodes a FixtureState into the wire bytearray.
    Knows nothing about scenes; just where its channels live."""

    def __init__(self, address: int, label: str = ""):
        self.base = address - 1  # DMX address 1 → array index 0
        self.label = label or f"@{address}"

    def init_frame(self, frame: bytearray) -> None:
        """Zero the whole footprint and pin CH1=255. Called once at startup;
        encode() never writes CH1/9-16, so they stay at these values forever."""
        for i in range(CHANNELS):
            frame[self.base + i] = 0
        frame[self.base + OFF_MASTER] = 255

    def encode(self, st: FixtureState, master_k: float, frame: bytearray) -> None:
        """Write this fixture's colour channels into `frame`, scaled by the
        software master. CH1/9/10/11 are left at their init_frame values."""
        b = self.base
        frame[b + OFF_R] = _byte(st.r * master_k)
        frame[b + OFF_G] = _byte(st.g * master_k)
        frame[b + OFF_B] = _byte(st.b * master_k)
        frame[b + OFF_LIME] = _byte(st.lime * master_k)
        frame[b + OFF_AMBER] = _byte(st.amber * master_k)
        frame[b + OFF_UV] = _byte(st.uv * master_k)
        frame[b + OFF_STROBE] = max(0, min(255, int(st.strobe)))


def build_rig(addresses=DEFAULT_ADDRESSES) -> list[Fixture]:
    labels = ("FL", "FR", "BL", "BR")
    return [Fixture(a, labels[i] if i < len(labels) else f"FX{i+1}")
            for i, a in enumerate(addresses)]
