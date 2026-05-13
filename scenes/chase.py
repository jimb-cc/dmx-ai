"""Single colour ping-pongs across the rig with a dim tail.
One step per half-beat."""

from scene import Scene
from scenes._palettes import ROCK


class Chase(Scene):
    label = "➡️ Chase"
    mood = "driving"
    weight = 1.2
    preferred_duration = (20.0, 40.0)
    palette = ROCK

    def on_enter(self):
        n = len(self.fx)
        self.order = list(range(n)) + list(range(n - 2, 0, -1))
        self.idx = 0
        self.next_at = 0.0
        self.col = self.rng.choice(self.palette)

    def tick(self, dt):
        super().tick(dt)
        if self.t >= self.next_at:
            self.idx = (self.idx + 1) % len(self.order)
            if self.idx == 0:
                self.col = self.rng.choice(self.palette)
            self.next_at = self.t + self.beat_secs(0.5)
        pos = self.order[self.idx]
        for i, f in enumerate(self.fx):
            if i == pos:
                f.set_rgb(*self.col)
            elif abs(i - pos) == 1:
                f.set_rgb(*(c / 5.0 for c in self.col))
            else:
                f.set_rgb(0, 0, 0)
