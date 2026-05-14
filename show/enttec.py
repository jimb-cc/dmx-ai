"""Minimal driver for the Enttec DMX USB Pro / Pro Mk2 (port 1 only).

The Mk2 behaves exactly like the original USB Pro on port 1 — no API key
needed unless you want the second universe, which we don't.

Frame format (label 6, "Output Only Send DMX Packet Request"):
    0x7E | label(1) | length LSB | length MSB | start code(0x00) + data | 0xE7
"""

from __future__ import annotations

import glob
import struct
import sys
import time

try:
    import serial  # pyserial
except ImportError:  # allow --sim to run without pyserial installed
    serial = None


START = 0x7E
END = 0xE7
LABEL_SEND_DMX = 6


def find_port() -> str:
    """Auto-detect the Enttec serial port on macOS or Linux/Pi."""
    candidates = (
        glob.glob("/dev/cu.usbserial*")     # macOS (preferred for outgoing)
        + glob.glob("/dev/tty.usbserial*")  # macOS
        + glob.glob("/dev/ttyUSB*")         # Linux / Raspberry Pi
        + glob.glob("/dev/serial/by-id/*Enttec*")
    )
    if not candidates:
        raise RuntimeError(
            "No Enttec serial port found. Plug it in, or pass --port /dev/... "
            "(or use --sim to run without hardware)."
        )
    return candidates[0]


class EnttecUSBPro:
    """Sends raw DMX frames over the Enttec serial widget."""

    def __init__(self, port: str | None = None, baud: int = 57600):
        if serial is None:
            raise RuntimeError("pyserial not installed — `pip install pyserial`")
        self.port_name = port or find_port()
        self.ser = serial.Serial(self.port_name, baudrate=baud, timeout=1)
        # Pre-built 518-byte wire frame: header(4) + start_code(1) + 512 + end(1).
        # Only the 512 data bytes change per frame — saves a handful of
        # allocations and ~1 KB of copying every tick on the Pi.
        self._msg = bytearray(518)
        self._msg[0] = START
        self._msg[1] = LABEL_SEND_DMX
        self._msg[2:4] = struct.pack("<H", 513)  # length = start code + 512
        self._msg[4] = 0x00                      # DMX start code
        self._msg[517] = END

    def send(self, universe) -> None:
        self._msg[5:517] = universe[:512]
        self.ser.write(self._msg)

    def blackout(self) -> None:
        self.send(bytes(512))

    def close(self) -> None:
        try:
            self.blackout()
            time.sleep(0.05)
        finally:
            self.ser.close()


class SimOutput:
    """Drop-in replacement for EnttecUSBPro that draws the rig in the terminal
    as four coloured blocks. Lets you tune scenes with no hardware attached.
    """

    def __init__(self, fixture_addrs, channels_per_fixture: int = 10):
        self.addrs = list(fixture_addrs)
        self.cpf = channels_per_fixture

    def send(self, universe) -> None:
        blocks = []
        for addr in self.addrs:
            base = addr - 1
            master = universe[base] / 255.0
            # Approximate the visible colour: RGB plus lime/amber/UV folded in.
            r = universe[base + 1]
            g = universe[base + 2]
            b = universe[base + 3]
            lime = universe[base + 4]
            amber = universe[base + 5]
            uv = universe[base + 6]
            r = min(255, r + lime * 0.55 + amber * 1.00 + uv * 0.30)
            g = min(255, g + lime * 0.95 + amber * 0.55)
            b = min(255, b + lime * 0.10 + uv * 0.95)
            r, g, b = (int(c * master) for c in (r, g, b))
            blocks.append(f"\033[48;2;{r};{g};{b}m        \033[0m")
        sys.stdout.write("\r " + "  ".join(blocks) + "  ")
        sys.stdout.flush()

    def blackout(self) -> None:
        pass

    def close(self) -> None:
        sys.stdout.write("\n")
