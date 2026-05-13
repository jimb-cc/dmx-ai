"""Hard random colour cuts on the beat. Mid/up-tempo rock."""

from scene import Scene
from scenes._palettes import ROCK


class ColorPop(Scene):
    label = "🥁 Pop"
    mood = "driving"
    weight = 1.5
    preferred_duration = (15.0, 35.0)
    palette = ROCK

    def on_enter(self):
        self.next_at = 0.0
        self._set_pattern()

    def _set_pattern(self):
        col = self.rng.choice(self.palette)
        roll = self.rng.random()
        if roll < 0.25:
            tgt = self.rng.randrange(len(self.fx))
            self.colours = [col if i == tgt else (0, 0, 0) for i in range(len(self.fx))]
        elif roll < 0.45:
            col2 = self.rng.choice(self.palette)
            self.colours = [col if i % 2 == 0 else col2 for i in range(len(self.fx))]
        else:
            self.colours = [col] * len(self.fx)

    def tick(self, dt):
        super().tick(dt)
        if self.t >= self.next_at:
            self._set_pattern()
            self.next_at = self.t + self.beat_secs(1)
        for i, f in enumerate(self.fx):
            f.set_rgb(*self.colours[i])
            f.lime = f.amber = f.uv = 0.0
            f.strobe = 0
