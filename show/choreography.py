"""Mover choreography layer.

Scenes only think about colour. Pan/tilt for movers is driven by this layer,
which runs after `scheduler.tick()` and before overlays/encode in the render
loop. It owns:

  - which fixture indices are movers, and their physical limits (from the
    profile's `pan_range_deg` / `tilt_range_deg`),
  - the active choreography pattern + a crossfade to the next one,
  - per-mover pan/tilt/intensity, written into the `FixtureState` shadow
    buffer the scheduler returns.

The pattern outputs are in **degrees from home** so a 30° sweep looks the
same on a 540°-pan mover and a 270°-pan mover. We learned the hard way that
slamming a cheap mover against its end-stop mid-show is loud and looks bad —
clamp to ±0.45 of the range to stay clear of the limits.

Movers are dramatic accents, not constant light. Each pattern carries an
intensity envelope that scales `FixtureState.dimmer`. The floor lift never
touches `dimmer` (see scene.lift_floor), so a "home" pattern can hold movers
fully dark while the pars stay lit.

The Show UI exposes a row of pattern pills; the setlist can carry a
`"choreo"` field per song. Auto mode picks a pattern that matches the
running scene's mood and rotates every couple of minutes — same philosophy
as the scene scheduler's auto-rotation.
"""

from __future__ import annotations

import math
import random
import threading
import time
from dataclasses import dataclass, field

from utils import in_out_sine

# Switching choreo crossfades pan/tilt over this many seconds. Slower than
# scene crossfades — a snap-to-home on every scene change reads as a glitch.
XFADE_SECONDS = 1.8
AUTO_ROTATE_SECONDS = (90.0, 180.0)
END_MARGIN = 0.02  # stay this fraction of channel clear of the end-stops

# Default home aim — channel-fraction, i.e. 0.0 is DMX value 0. The GravelAxe
# movers sit on their base on the floor with pan/tilt 0,0 pointing straight
# at the audience, so 0,0 is the right default for this rig. A truss-hung
# mover would want 0.5/0.5. Tunable live from the Show UI without a restart;
# persisted per-rig is a TODO if it varies between rigs.
HOME_PAN = 0.0
HOME_TILT = 0.0
# How much of the available pan/tilt headroom the patterns use. 1.0 = bang
# up to the end-stop margins. Live-tunable too — dial it down if a pattern
# overshoots the stage.
SPREAD = 0.85


@dataclass
class Mover:
    """One physical mover, as the choreographer sees it."""
    index: int                 # position in the fixture/state list
    frac: float                # 0..1 spread across the mover group (0 = SL, 1 = SR)
    pan_range: float = 540.0   # physical degrees of travel
    tilt_range: float = 270.0
    label: str = ""
    # Per-mover live state (degrees-from-home + intensity), crossfaded.
    pan: float = 0.0
    tilt: float = 0.0
    inten: float = 0.0
    _from: tuple[float, float, float] = field(default=(0.0, 0.0, 0.0), repr=False)


# --------------------------------------------------------------------- patterns
#
# Each pattern is a function (t, m: Mover, ctx) -> (pan_deg, tilt_deg, intensity).
# `t` is choreo-local seconds; `ctx` exposes `.bpm`. Pan/tilt are degrees from
# the home aim; intensity is 0..1 (scales FixtureState.dimmer).


def _home(t, m, ctx):
    # Parked: aimed at the band, dark. The default when the setlist hasn't
    # said anything — movers off so they don't compete with the pars.
    return 0.0, 0.0, 0.0


# Amplitudes are physical degrees of head travel from home. First studio
# session showed the initial values were laughably conservative — a 540°-pan
# mover doing ±32° looked like it was barely awake. These are sized for a
# small-club rig where the heads should be obviously *doing something*; the
# LIMIT_MARGIN clamp (±45% of range = ±243° on a 540° head) keeps even the
# big swings clear of the end-stops.

def _wash(t, m, ctx):
    # Aimed at the band, gentle slow swell. The "movers as extra wash" cue.
    swell = 0.7 + 0.3 * (0.5 - 0.5 * math.cos(t * 0.35 + m.frac * math.pi))
    return 0.0, 0.0, swell


def _sweep(t, m, ctx):
    # Side-to-side, opposite phases so they cross. Pulses brighter when the
    # head is moving fast (mid-sweep) — same trick a real LD uses.
    period = 8.0
    ph = t * math.tau / period + m.frac * math.pi
    pan = math.sin(ph) * 180.0
    tilt = math.sin(ph * 0.5) * 35.0
    inten = 0.6 + 0.4 * abs(math.cos(ph))
    return pan, tilt, inten


def _fan(t, m, ctx):
    # Movers spread outward symmetrically, slow breathe in/out. Looks like
    # the rig opening up — good "big chorus" cue.
    spread = (m.frac - 0.5) * 2.0   # -1..+1
    breathe = 0.55 + 0.45 * (0.5 - 0.5 * math.cos(t * 0.3))
    pan = spread * 200.0 * breathe
    tilt = -25.0 + breathe * 50.0
    return pan, tilt, 0.8 + 0.2 * breathe


def _scan(t, m, ctx):
    # Audience scan: tilt up, pan sweeps the room. The "you're at a show" cue.
    # Use sparingly — blinding the punters reads as aggressive.
    period = 10.0
    ph = t * math.tau / period + m.frac * 0.6
    pan = math.sin(ph) * 220.0
    tilt = 80.0 + math.sin(ph * 0.4) * 20.0
    return pan, tilt, 1.0


def _crossfire(t, m, ctx):
    # Movers point across the stage at each other — a tight X. Beat-locked
    # snap between the two diagonals.
    beat = 60.0 / max(60.0, ctx.bpm)
    bar = beat * 8
    flip = -1.0 if (t % (bar * 2)) >= bar else 1.0
    spread = (m.frac - 0.5) * 2.0
    pan = -spread * 200.0 * flip
    tilt = -15.0
    # Punch on the bar boundary.
    phase = (t % bar) / bar
    inten = 0.7 + 0.3 * math.exp(-phase * 3.0)
    return pan, tilt, inten


def _beatsnap(t, m, ctx):
    # Each mover snaps to a new pseudo-random position every bar, with a
    # bright punch on the snap. The "drum break" cue.
    beat = 60.0 / max(60.0, ctx.bpm)
    bar = beat * 4
    n = int(t / bar)
    rng = random.Random(n * 7919 + m.index * 104729)
    pan = (rng.random() * 2 - 1) * 240.0
    tilt = (rng.random() * 2 - 1) * 70.0
    phase = (t % bar) / bar
    inten = 0.4 + 0.6 * math.exp(-phase * 5.0)
    return pan, tilt, inten


def _circle(t, m, ctx):
    # Each head traces a slow circle, opposite directions. Atmospheric.
    period = 12.0
    direction = 1.0 if m.frac < 0.5 else -1.0
    ph = t * math.tau / period * direction + m.frac * math.pi
    pan = math.cos(ph) * 130.0
    tilt = math.sin(ph) * 55.0
    return pan, tilt, 0.85


# name -> (fn, label, moods it suits, auto weight)
PATTERNS: dict[str, tuple] = {
    "home":      (_home,      "🏠 Home",       (), 0.0),
    "wash":      (_wash,      "💡 Wash",       ("ambient", "atmospheric"), 1.0),
    "sweep":     (_sweep,     "↔️ Sweep",      ("driving", "spectacle"), 1.2),
    "fan":       (_fan,       "📡 Fan",        ("spectacle", "ambient"), 1.0),
    "scan":      (_scan,      "👀 Scan",       ("spectacle",), 0.5),
    "crossfire": (_crossfire, "❌ Crossfire",  ("driving",), 0.9),
    "beatsnap":  (_beatsnap,  "🥁 Beat Snap",  ("driving",), 0.7),
    "circle":    (_circle,    "🌀 Circle",     ("atmospheric", "ambient"), 0.8),
}


def catalogue() -> list[dict]:
    return [{"name": n, "label": v[1], "moods": list(v[2])} for n, v in PATTERNS.items()]


def _to_channel(deg: float, home: float, range_deg: float, spread: float) -> float:
    """Map a pattern's degrees-from-home to a 0..1 channel value.

    Home is where the head sits at rest (offset = 0). Patterns swing the
    head ±degrees around home, scaled by `spread`. The result clamps clear
    of the channel end-stops; when home is right at a limit the swing is
    one-sided. Move the home slider toward the middle of the range if you
    want the full arc.

    First version had a "smart" bias toward the centre of available headroom
    so a one-sided home still got a full arc — but the bias cancelled the
    home setting completely (every home value resolved to channel ~128,
    which on a floor-standing mover is straight up). Lesson learned: the
    home slider should do exactly what it says.
    """
    rng = max(1.0, range_deg)
    n = home + (deg * spread) / rng
    return max(END_MARGIN, min(1.0 - END_MARGIN, n))


# ------------------------------------------------------------------- choreographer

class Choreographer:
    """Drives mover pan/tilt/intensity each frame. Threadsafe API like the
    scheduler — `apply()` from the render loop, `set_pattern()` / `set_auto()`
    from Flask handlers."""

    def __init__(self, fixtures, ctx, *, default: str = "home"):
        self._lock = threading.Lock()
        self.ctx = ctx
        self.movers: list[Mover] = []
        n_movers = sum(1 for f in fixtures if f.is_mover and f.has_pan_tilt)
        k = 0
        for i, f in enumerate(fixtures):
            if not (f.is_mover and f.has_pan_tilt):
                continue
            self.movers.append(Mover(
                index=i,
                frac=k / max(1, n_movers - 1) if n_movers > 1 else 0.5,
                pan_range=f.profile.pan_range_deg,
                tilt_range=f.profile.tilt_range_deg,
                label=f.label,
            ))
            k += 1

        self.pattern = default if default in PATTERNS else "home"
        self.mode = "auto"            # "auto" | "manual"
        self.t = 0.0
        self._xfade_t = 1.0
        self._auto_until = 0.0
        self.home_pan = HOME_PAN
        self.home_tilt = HOME_TILT
        self.spread = SPREAD

    @property
    def has_movers(self) -> bool:
        return bool(self.movers)

    # ------------------------------------------------------------------ API

    def set_pattern(self, name: str) -> bool:
        if name not in PATTERNS:
            return False
        with self._lock:
            self.mode = "manual"
            self._switch(name)
        return True

    def set_auto(self) -> None:
        with self._lock:
            self.mode = "auto"
            self._auto_until = 0.0

    def set_home(self, pan: float | None = None, tilt: float | None = None,
                 spread: float | None = None) -> None:
        with self._lock:
            if pan is not None:
                self.home_pan = max(0.0, min(1.0, float(pan)))
            if tilt is not None:
                self.home_tilt = max(0.0, min(1.0, float(tilt)))
            if spread is not None:
                self.spread = max(0.05, min(2.0, float(spread)))

    def status(self) -> dict:
        with self._lock:
            return {
                "pattern": self.pattern,
                "mode": self.mode,
                "movers": len(self.movers),
                "home_pan": self.home_pan,
                "home_tilt": self.home_tilt,
                "spread": self.spread,
            }

    # ------------------------------------------------------------- render loop

    def apply(self, states, dt: float, scene_mood: str = "mixed") -> None:
        """Mutate the mover entries of `states` in place. Cheap when there
        are no movers."""
        if not self.movers:
            return
        with self._lock:
            self.t += dt
            now = time.monotonic()
            if self.mode == "auto" and now >= self._auto_until and self._xfade_t >= 1.0:
                nxt = self._pick_auto(scene_mood)
                if nxt and nxt != self.pattern:
                    self._switch(nxt)
                else:
                    # Nothing better — keep this pattern, retry sooner.
                    self._auto_until = now + 30.0

            fn = PATTERNS[self.pattern][0]
            self._xfade_t = min(1.0, self._xfade_t + dt / XFADE_SECONDS)
            k = in_out_sine(self._xfade_t)
            inv = 1.0 - k
            hp, ht, spread = self.home_pan, self.home_tilt, self.spread

            for m in self.movers:
                pd, td, inten = fn(self.t, m, self.ctx)
                if k < 1.0:
                    fp, ft, fi = m._from
                    pd = fp * inv + pd * k
                    td = ft * inv + td * k
                    inten = fi * inv + inten * k
                m.pan, m.tilt, m.inten = pd, td, inten
                st = states[m.index]
                st.pan = _to_channel(pd, hp, m.pan_range, spread)
                st.tilt = _to_channel(td, ht, m.tilt_range, spread)
                st.dimmer = max(0.0, min(1.0, st.dimmer * inten))

    # ---------------------------------------------------------------- internals

    def _switch(self, name: str) -> None:
        # Snapshot the current per-mover output so the new pattern fades in
        # from where the heads physically are, not from home.
        for m in self.movers:
            m._from = (m.pan, m.tilt, m.inten)
        self.pattern = name
        self.t = 0.0
        self._xfade_t = 0.0
        self._auto_until = time.monotonic() + random.uniform(*AUTO_ROTATE_SECONDS)

    def _pick_auto(self, scene_mood: str) -> str | None:
        candidates, weights = [], []
        for name, (_fn, _lbl, moods, w) in PATTERNS.items():
            if w <= 0 or name == self.pattern:
                continue
            # Boost patterns tagged for the current mood; still allow others
            # at lower weight so it doesn't get stale.
            ww = w * (3.0 if scene_mood in moods else 1.0)
            candidates.append(name)
            weights.append(ww)
        if not candidates:
            return None
        return random.choices(candidates, weights=weights, k=1)[0]
