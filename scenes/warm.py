"""Warm amber/lime glow with a slow drift. Between songs, banter."""

import math

from scene import Scene
from utils import noise1d


class WarmWash(Scene):
    label = "🟠 Warm"
    mood = "ambient"
    weight = 1.0
    preferred_duration = (35.0, 70.0)

    def on_enter(self):
        self.phases = self.random_phases()

    def tick(self, dt):
        super().tick(dt)
        for i, f in enumerate(self.fx):
            k = 0.5 + 0.5 * math.sin(self.t * 0.35 + self.phases[i])
            d = noise1d(self.t * 0.12, seed=i * 13) * 0.15
            f.set(r=0.78 + 0.20 * k, g=0.20 + 0.18 * k, b=0.0,
                  lime=0.10 + 0.10 * k + d, amber=0.55 + 0.35 * k)
