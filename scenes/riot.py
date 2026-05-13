"""Police-lights pattern: front pair red, back pair blue, alternating at
~4 Hz, with a periodic all-red drop. Punk covers, big aggressive choruses."""

from scene import Scene


class Riot(Scene):
    label = "🚨 Riot"
    mood = "driving"
    weight = 0.7
    preferred_duration = (15.0, 30.0)
    is_strobey = True   # flagged so auto-mixed mood avoids it

    FRONT = (0, 1)
    BACK = (2, 3)
    RED = (1.0, 0.0, 0.0)
    BLUE = (0.0, 0.10, 1.0)

    def tick(self, dt):
        super().tick(dt)
        # ~4 Hz alternation (250ms half-cycle)
        flip = (self.t % 0.25) < 0.125
        all_red = (self.t % 6.0) > 5.5  # 0.5s all-red drop every 6s
        for i, f in enumerate(self.fx):
            if all_red:
                f.set_rgb(*self.RED)
            elif (i in self.FRONT) == flip:
                f.set_rgb(*(self.RED if i in self.FRONT else self.BLUE))
            else:
                f.set_rgb(0, 0, 0)
            f.lime = f.amber = f.uv = 0.0
            f.strobe = 0
