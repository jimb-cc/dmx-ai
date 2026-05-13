"""Slow cool blue/violet wash with random white lightning strikes.
Spoken intros, slow blues openers, anything earning drama."""

from scene import Scene
from utils import noise1d, poisson_event


class Thunderstorm(Scene):
    label = "⛈️ Storm"
    mood = "atmospheric"
    weight = 0.8
    preferred_duration = (40.0, 90.0)

    def on_enter(self):
        self.flash_until = [0.0] * len(self.fx)

    def tick(self, dt):
        super().tick(dt)
        # Slow blue/violet breathing wash
        for i, f in enumerate(self.fx):
            n = noise1d(self.t * 0.15, seed=i * 17)
            m = noise1d(self.t * 0.10, seed=i * 31 + 5)
            # n=0 → steel blue, n=1 → violet
            r = 0.05 + 0.30 * n
            g = 0.02 + 0.06 * (1 - n)
            b = 0.30 + 0.45 * m
            f.set(r=r, g=g, b=b, uv=0.10 + 0.15 * n)

        # Lightning: Poisson event ~10s mean, picks a random fixture
        if poisson_event(self.rng, dt, mean_interval=10.0):
            i = self.rng.randrange(len(self.fx))
            self.flash_until[i] = self.t + (0.32 if self.rng.random() < 0.30 else 0.12)

        for i, f in enumerate(self.fx):
            if self.t < self.flash_until[i]:
                f.set(r=1.0, g=1.0, b=1.0, lime=0.7, amber=0.3)
