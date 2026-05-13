"""Slow random colour cross-fades, each fixture independent. Ballads.
Fade length is 4 bars at the current tempo so it breathes with the song."""

from scene import Scene
from scenes._palettes import COOL
from utils import lerp


class SlowFade(Scene):
    label = "🌊 Chill"
    mood = "ambient"
    weight = 1.5
    preferred_duration = (40.0, 90.0)
    palette = COOL

    def on_enter(self):
        self.cur = [self.rng.choice(self.palette) for _ in self.fx]
        self.nxt = [self.rng.choice(self.palette) for _ in self.fx]
        self.k = 0.0

    def tick(self, dt):
        super().tick(dt)
        fade_secs = self.beat_secs(16)  # 4 bars of 4
        self.k += dt / max(1.0, fade_secs)
        if self.k >= 1.0:
            self.cur, self.nxt = self.nxt, [self.rng.choice(self.palette) for _ in self.fx]
            self.k = 0.0
        for i, f in enumerate(self.fx):
            a, b = self.cur[i], self.nxt[i]
            f.set_rgb(lerp(a[0], b[0], self.k), lerp(a[1], b[1], self.k), lerp(a[2], b[2], self.k))
