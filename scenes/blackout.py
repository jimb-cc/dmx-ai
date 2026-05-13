from scene import Scene


class Blackout(Scene):
    label = "⬛ Blackout"
    mood = "ambient"
    weight = 0.0          # never auto-rotates in
    respects_floor = False  # the one scene that's allowed to be fully dark

    def tick(self, dt):
        super().tick(dt)
        self.all(lambda f: f.off())
