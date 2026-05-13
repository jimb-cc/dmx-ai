"""25-second build from black through deep red → orange → amber → warm white,
with a 1s white-out at the climax, then a sustained amber wash.
The single biggest cue you've got. Save it for the moment."""

from scene import Scene
from utils import in_cubic, lerp


# (r, g, b, lime, amber) keypoints across the build, 0..1
RAMP = [
    (0.00, (0.02, 0.00, 0.00, 0.00, 0.00)),   # near black
    (0.30, (0.45, 0.02, 0.00, 0.00, 0.10)),   # deep red
    (0.55, (0.85, 0.10, 0.00, 0.05, 0.45)),   # orange
    (0.80, (0.95, 0.30, 0.00, 0.30, 0.80)),   # amber
    (1.00, (1.00, 0.75, 0.40, 0.80, 0.95)),   # warm white
]
RAMP_PAIRS = list(zip(RAMP, RAMP[1:]))


def _ramp(p):
    for (a_t, a_c), (b_t, b_c) in RAMP_PAIRS:
        if p <= b_t:
            k = (p - a_t) / max(0.001, b_t - a_t)
            return tuple(lerp(a_c[i], b_c[i], k) for i in range(5))
    return RAMP[-1][1]


class SunRise(Scene):
    label = "🌅 Sun Rise"
    mood = "spectacle"
    weight = 0.5
    preferred_duration = (35.0, 60.0)

    BUILD = 22.0
    HOLD = 1.0
    DECAY = 4.0

    def tick(self, dt):
        super().tick(dt)
        if self.t < self.BUILD:
            p = in_cubic(self.t / self.BUILD)
            r, g, b, lime, amber = _ramp(p)
        elif self.t < self.BUILD + self.HOLD:
            r, g, b, lime, amber = (1.0, 1.0, 1.0, 1.0, 1.0)
        elif self.t < self.BUILD + self.HOLD + self.DECAY:
            k = (self.t - self.BUILD - self.HOLD) / self.DECAY
            white = (1.0, 1.0, 1.0, 1.0, 1.0)
            sustain = (0.65, 0.20, 0.0, 0.20, 0.70)
            r, g, b, lime, amber = (lerp(white[i], sustain[i], k) for i in range(5))
        else:
            r, g, b, lime, amber = (0.65, 0.20, 0.0, 0.20, 0.70)
        for f in self.fx:
            f.set(r=r, g=g, b=b, lime=lime, amber=amber)
