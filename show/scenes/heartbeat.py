"""All four fixtures pulse together with a thump-thump-rest envelope.
Like a heartbeat at ~60 BPM, accelerating slightly over 30 seconds."""

from scene import Scene
from utils import lerp


class Heartbeat(Scene):
    label = "❤️ Heartbeat"
    mood = "spectacle"
    weight = 0.6
    preferred_duration = (25.0, 40.0)

    def tick(self, dt):
        super().tick(dt)
        # Cycle period shortens 1.0s → 0.7s over 30s
        period = lerp(1.0, 0.7, min(1.0, self.t / 30.0))
        p = (self.t % period) / period
        # thump-thump-rest envelope
        if p < 0.08:
            L = lerp(0.30, 0.85, p / 0.08)
        elif p < 0.16:
            L = lerp(0.85, 0.40, (p - 0.08) / 0.08)
        elif p < 0.24:
            L = lerp(0.40, 0.70, (p - 0.16) / 0.08)
        elif p < 0.32:
            L = lerp(0.70, 0.30, (p - 0.24) / 0.08)
        else:
            L = 0.30
        for f in self.fx:
            f.set(r=L, g=L * 0.05, b=L * 0.02)
