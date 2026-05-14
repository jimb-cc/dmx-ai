"""Slow cool blue/violet wash with hybrid lightning strikes.

A strike is two phases:
  1. **Hardware strobe burst** (CH8) — 60-180ms of razor-sharp full-white
     pulses. The par's strobe is essentially binary, so this is the violent
     "BANG" that no software approach can match.
  2. **Software after-flashes** — 0-3 progressively dimmer ~40ms pulses with
     dark gaps, à la ToyKeeper's Anduril decay. These read as the soft
     flickering re-strikes a real lightning event has.

Each fixture strikes independently with its own envelope and a small offset.
The bursty inter-strike gap (log-uniform 1ms..8s) is Anduril's, so strikes
cluster then go quiet for seconds.
"""

from scene import Scene
from utils import noise1d


def _make_gap(rng) -> float:
    """Off time between bursts: log-uniform 1ms..8s, biased short. Anduril's."""
    ms = 1 << rng.randrange(13)
    ms += rng.randrange(max(1, ms))
    return ms / 1000.0


def _make_burst(rng) -> list[tuple[float, int, float]]:
    """One strike as a list of (colour_level_0to1, strobe_byte, hold_secs)."""
    seq = []
    # Phase 1 — hardware strobe BANG, always full white.
    rate = 200 + rng.randrange(56)               # ~12-25 Hz on most pars
    strobe_s = 0.06 + rng.random() * 0.13        # 60-190ms = 1-4 pulses
    seq.append((1.0, rate, strobe_s))
    # Beat of darkness so the after-flashes read as separate.
    seq.append((0.0, 0, 0.05 + rng.random() * 0.07))
    # Phase 2 — soft after-flashes, ToyKeeper-style stepwise decay.
    n_trail = rng.choice((0, 1, 1, 2, 2, 2, 3))  # mostly 1-2
    b = rng.uniform(0.40, 0.65)
    for i in range(n_trail):
        seq.append((b, 0, 0.035 + rng.random() * 0.045))    # ~1-2 frames lit
        if i < n_trail - 1:
            seq.append((0.0, 0, 0.04 + rng.random() * 0.08))  # dark gap
        b *= rng.uniform(0.35, 0.65)
    seq.append((0.0, 0, 0.0))                    # end marker
    return seq


class _Bolt:
    """Per-fixture strike sequence player."""

    __slots__ = ("steps", "step_t")

    def __init__(self):
        self.steps: list[tuple[float, int, float]] = []
        self.step_t = 0.0

    def fire(self, rng, delay: float = 0.0) -> None:
        seq = _make_burst(rng)
        if delay > 0:
            seq.insert(0, (0.0, 0, delay))
        self.steps = seq
        self.step_t = 0.0

    @property
    def active(self) -> bool:
        return bool(self.steps)

    def level(self, dt: float) -> tuple[float, int]:
        """Advance by dt, return (colour_level, strobe_byte). Renders the
        brightest step seen this frame so a transient is never skipped."""
        if not self.steps:
            return (0.0, 0)
        self.step_t += dt
        peak_lvl, peak_strobe = 0.0, 0
        while self.steps and self.step_t >= self.steps[0][2]:
            lvl, st, dur = self.steps.pop(0)
            if lvl > peak_lvl or st > peak_strobe:
                peak_lvl, peak_strobe = max(peak_lvl, lvl), max(peak_strobe, st)
            self.step_t -= dur
        if self.steps:
            lvl, st, _ = self.steps[0]
            peak_lvl, peak_strobe = max(peak_lvl, lvl), max(peak_strobe, st)
        return (peak_lvl, peak_strobe)


class Thunderstorm(Scene):
    label = "⛈️ Storm"
    mood = "atmospheric"
    weight = 0.8
    preferred_duration = (40.0, 90.0)

    def on_enter(self):
        self.bolts = [_Bolt() for _ in self.fx]
        self.gap_until = self.t + 1.0   # first strike ~1s in

    def tick(self, dt):
        super().tick(dt)

        # Slow blue/violet breathing wash. Kept dim so the lightning pops.
        for i, f in enumerate(self.fx):
            n = noise1d(self.t * 0.15, seed=i * 17)
            m = noise1d(self.t * 0.10, seed=i * 31 + 5)
            f.set(r=0.02 + 0.10 * n,
                  g=0.01 + 0.03 * (1 - n),
                  b=0.10 + 0.28 * m,
                  uv=0.05 + 0.12 * n)

        # Storm clock: pick 1..N fixtures, give each a small offset so a
        # strike sweeps across the rig rather than landing as one big flash.
        if self.t >= self.gap_until and not any(b.active for b in self.bolts):
            n_hit = self.rng.choice((1, 1, 1, 2, 2, 3, len(self.fx)))
            for i in self.rng.sample(range(len(self.fx)), min(n_hit, len(self.fx))):
                self.bolts[i].fire(self.rng, delay=self.rng.random() * 0.18)
            self.gap_until = self.t + 9999.0  # re-armed when all bolts clear

        any_active = False
        for i, f in enumerate(self.fx):
            level, rate = self.bolts[i].level(dt)
            any_active |= self.bolts[i].active
            if level > 0.0 or rate > 0:
                f.set(r=level, g=level, b=level,
                      lime=level * 0.9, amber=level * 0.5, uv=level * 0.25)
                f.strobe = rate

        if not any_active and self.gap_until > self.t + 100:
            self.gap_until = self.t + _make_gap(self.rng)
