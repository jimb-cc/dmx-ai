"""Bright cool white front pair, warm amber back, with a slow swell.
The "you're in the audience and we're in the lights" cue. Use once a night."""

import math

from scene import Scene


class Headlights(Scene):
    label = "💡 Headlights"
    mood = "spectacle"
    weight = 0.5
    preferred_duration = (25.0, 50.0)

    FRONT = (0, 1)

    def tick(self, dt):
        super().tick(dt)
        swell = 0.65 + 0.35 * (0.5 - 0.5 * math.cos(self.t * 0.4))
        for i, f in enumerate(self.fx):
            if i in self.FRONT:
                f.set(r=swell, g=swell * 0.85, b=swell * 0.95, lime=swell * 0.6)
            else:
                f.set(r=swell * 0.55, g=swell * 0.18, b=0.0, amber=swell * 0.7)
            f.strobe = 0
