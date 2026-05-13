"""Deep red/amber drift with random brightness pops. Dying-fire ballad cue.
Uses the real amber emitter — looks two grades richer than RGB-only."""

from scene import Scene
from utils import noise1d, out_cubic, poisson_event


class Embers(Scene):
    label = "🔥 Embers"
    mood = "ambient"
    weight = 1.0
    preferred_duration = (40.0, 80.0)

    def on_enter(self):
        self.pop_until = [0.0] * len(self.fx)

    def tick(self, dt):
        super().tick(dt)
        if poisson_event(self.rng, dt, mean_interval=4.0):
            i = self.rng.randrange(len(self.fx))
            self.pop_until[i] = self.t + 0.6

        for i, f in enumerate(self.fx):
            base = 0.30 + 0.20 * noise1d(self.t * 0.15, seed=i * 7)
            warm = noise1d(self.t * 0.10, seed=i * 11 + 2)  # 0 = deep red, 1 = amber
            pop = 0.0
            remain = self.pop_until[i] - self.t
            if remain > 0:
                pop = out_cubic(remain / 0.6) * 0.30
            k = base + pop
            f.set(r=k * (0.95 - 0.25 * warm), g=k * 0.10 * warm, b=0,
                  amber=k * (0.30 + 0.65 * warm), lime=k * 0.05 * warm)
            f.strobe = 0
