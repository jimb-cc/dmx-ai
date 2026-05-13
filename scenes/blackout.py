from scene import Scene


class Blackout(Scene):
    label = "⬛ Blackout"
    mood = "ambient"
    weight = 0.0  # never auto-rotates in

    def tick(self, dt):
        super().tick(dt)
        self.all(lambda f: f.off())
