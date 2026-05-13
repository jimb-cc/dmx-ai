"""Front pair / back pair alternate hard on/off on the beat.
Beat-locked rock, four-on-the-floor. Tap the tempo first."""

from scene import Scene


class HardCuts(Scene):
    label = "✂️ Hard Cuts"
    mood = "driving"
    weight = 0.8
    preferred_duration = (20.0, 40.0)

    FRONT = (0, 1)
    BACK = (2, 3)
    COL_FRONT = (1.0, 0.05, 0.0)   # red
    COL_BACK = (0.0, 0.10, 1.0)    # blue

    def tick(self, dt):
        super().tick(dt)
        beat = self.beat_secs(1)
        front_on = ((self.t / max(0.05, beat)) % 2.0) < 1.0
        for i, f in enumerate(self.fx):
            on_front = (i in self.FRONT) and front_on
            on_back = (i in self.BACK) and not front_on
            if on_front:
                f.set_rgb(*self.COL_FRONT)
            elif on_back:
                f.set_rgb(*self.COL_BACK)
            else:
                f.set_rgb(0, 0, 0)
            f.lime = f.amber = f.uv = 0.0
            f.strobe = 0
