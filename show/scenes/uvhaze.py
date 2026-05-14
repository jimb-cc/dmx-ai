"""Deep blue + real UV wash with a slow shimmer. Spooky intros."""

import math

from scene import Scene


class UVHaze(Scene):
    label = "🔮 UV"
    mood = "atmospheric"
    weight = 0.7
    preferred_duration = (25.0, 50.0)

    def on_enter(self):
        self.phases = self.random_phases()

    def tick(self, dt):
        super().tick(dt)
        for i, f in enumerate(self.fx):
            k = 0.5 + 0.5 * math.sin(self.t * 0.5 + self.phases[i])
            f.set(b=0.20 + 0.18 * k, uv=0.65 + 0.30 * k)
