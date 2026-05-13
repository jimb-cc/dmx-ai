"""Whole rig breathes in one colour, snapping to a new one each bar.
Sharp attack, long decay — feels like a kick drum."""

import math

from scene import Scene
from scenes._palettes import ROCK


class Pulse(Scene):
    label = "💗 Pulse"
    mood = "driving"
    weight = 1.2
    preferred_duration = (20.0, 40.0)
    palette = ROCK

    def on_enter(self):
        self.col = self.rng.choice(self.palette)
        self.bar_start = 0.0

    def tick(self, dt):
        super().tick(dt)
        bar = self.beat_secs(4)
        if self.t - self.bar_start >= bar:
            self.bar_start = self.t
            self.col = self.rng.choice(self.palette)
        beat = self.beat_secs(1)
        phase = ((self.t - self.bar_start) % beat) / max(0.01, beat)
        k = max(0.15, math.exp(-phase * 4.0))
        for f in self.fx:
            f.set_rgb(self.col[0] * k, self.col[1] * k, self.col[2] * k)
