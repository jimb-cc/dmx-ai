"""Single warm-white spot rotates around the corners with a dim amber tail.
Vegas/marquee glamour. Anything with a sequinned-dancers riff."""

from scene import Scene


class Marquee(Scene):
    label = "🎰 Marquee"
    mood = "driving"
    weight = 1.0
    preferred_duration = (25.0, 45.0)

    # FL → FR → BR → BL perimeter loop (assuming addresses are FL/FR/BL/BR)
    ORDER = (0, 1, 3, 2)

    def on_enter(self):
        self.pos = 0
        self.next_at = 0.0

    def tick(self, dt):
        super().tick(dt)
        if self.t >= self.next_at:
            self.pos = (self.pos + 1) % len(self.ORDER)
            self.next_at = self.t + self.beat_secs(0.5)
        active = self.ORDER[self.pos]
        prev = self.ORDER[(self.pos - 1) % len(self.ORDER)]
        for i, f in enumerate(self.fx):
            if i == active:
                f.set(r=1.0, g=0.55, b=0.10, lime=0.85, amber=1.0)
            elif i == prev:
                f.set(r=0.25, g=0.08, b=0.0, amber=0.30)
            else:
                f.set(r=0.06, g=0.02, b=0.0, amber=0.08)
