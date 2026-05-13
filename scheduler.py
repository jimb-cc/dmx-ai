"""SceneScheduler — runs scenes, crossfades between them, auto-rotates.

The scheduler owns:
  - the current and outgoing Scene instances (each with its own FixtureState
    shadow buffer),
  - the crossfade state,
  - auto-rotation with mood filtering and a recency penalty,
  - a blended FixtureState buffer that the render loop reads each tick.

Threading: all mutation goes through a single lock. The render loop calls
`tick()`; the Flask handlers call `goto()` / `set_auto()` etc. The lock is
held briefly — no DMX I/O inside it.
"""

from __future__ import annotations

import random
import threading
import time
from collections import deque

from scene import FixtureState, Scene, lerp_states
from utils import in_out_sine


XFADE_SECONDS = 2.5
RECENCY_BUFFER = 4
RECENCY_PENALTY = 4.0  # weight ÷ (1 + penalty * appearances)

MOODS = ("mixed", "ambient", "driving", "spectacle", "atmospheric", "nature", "glitch")


class SceneScheduler:
    def __init__(self, n_fixtures: int, registry: dict, ctx, *,
                 default_scene: str = "blackout"):
        self._lock = threading.Lock()
        self.n = n_fixtures
        self.registry = registry           # name -> (cls, mutator|None)
        self.ctx = ctx                     # exposes .bpm

        self.mode = "auto"                 # "auto" | "manual"
        self.auto_mood = "mixed"
        self._recency: deque[str] = deque(maxlen=RECENCY_BUFFER)
        self._auto_until = 0.0

        self.current: Scene | None = None
        self.current_name = default_scene
        self.outgoing: Scene | None = None
        self.outgoing_name = ""
        self._xfade_t = 1.0                # 1.0 = no crossfade in progress
        self._xfade_dur = XFADE_SECONDS

        self.blended = [FixtureState() for _ in range(n_fixtures)]

        self._make_current(default_scene)

    # ------------------------------------------------------------------ API

    def goto(self, name: str, xfade: float = XFADE_SECONDS) -> bool:
        """Manually switch to a scene with crossfade. Exits auto mode."""
        if name not in self.registry:
            return False
        with self._lock:
            self.mode = "manual"
            self._start_crossfade(name, xfade)
        return True

    def set_auto(self, mood: str = "mixed") -> None:
        with self._lock:
            self.mode = "auto"
            self.auto_mood = mood if mood in MOODS else "mixed"
            self._auto_until = 0.0  # pick a new scene next tick

    def tick(self, dt: float) -> list[FixtureState]:
        """Advance one frame. Returns the blended fixture states (do not
        mutate the returned list outside the render loop)."""
        with self._lock:
            now = time.monotonic()
            if self.mode == "auto" and now >= self._auto_until and self._xfade_t >= 1.0:
                nxt = self._pick_auto()
                if nxt and nxt != self.current_name:
                    self._start_crossfade(nxt, XFADE_SECONDS)

            if self.current:
                self.current.step(dt)

            if self.outgoing is not None and self.current is not None:
                self.outgoing.step(dt)
                self._xfade_t = min(1.0, self._xfade_t + dt / max(0.05, self._xfade_dur))
                k = in_out_sine(self._xfade_t)
                for i in range(self.n):
                    lerp_states(self.outgoing.fx[i], self.current.fx[i], k, self.blended[i])
                if self._xfade_t >= 1.0:
                    self.outgoing.on_exit()
                    self.outgoing = None
                    self.outgoing_name = ""
            elif self.current is not None:
                for i in range(self.n):
                    self.blended[i].copy_from(self.current.fx[i])

            return self.blended

    def status(self) -> dict:
        with self._lock:
            return {
                "scene": self.current_name,
                "outgoing": self.outgoing_name or None,
                "xfading": self.outgoing is not None,
                "mode": self.mode,
                "mood": self.auto_mood,
            }

    # ---------------------------------------------------------------- internals

    def _instantiate(self, name: str) -> Scene:
        cls, mutator = self.registry[name]
        rng = random.Random(time.time_ns() ^ hash(name))
        sc = cls(self.n, rng, self.ctx, mutator=mutator)
        sc.name = name
        return sc

    def _make_current(self, name: str) -> None:
        self.current = self._instantiate(name)
        self.current_name = name
        self.outgoing = None
        self.outgoing_name = ""
        self._xfade_t = 1.0
        self._recency.append(name)
        if self.mode == "auto":
            self._schedule_next_auto()

    def _start_crossfade(self, name: str, dur: float) -> None:
        # Drop any in-progress outgoing scene; the new crossfade starts from
        # the *current blended* state rather than a half-faded outgoing.
        prev = self.current
        if prev is not None and self.outgoing is not None:
            # Snapshot the current blend into the outgoing buffer so the new
            # fade starts visually where we are, not from the half-finished
            # outgoing scene.
            for i in range(self.n):
                prev.fx[i].copy_from(self.blended[i])
        self.outgoing = prev
        self.outgoing_name = self.current_name
        self.current = self._instantiate(name)
        self.current_name = name
        self._xfade_dur = max(0.05, dur)
        self._xfade_t = 0.0
        self._recency.append(name)
        if self.mode == "auto":
            self._schedule_next_auto()

    def _schedule_next_auto(self) -> None:
        cls, _ = self.registry[self.current_name]
        lo, hi = getattr(cls, "preferred_duration", (25.0, 45.0))
        self._auto_until = time.monotonic() + random.uniform(lo, hi)

    def _pick_auto(self) -> str | None:
        candidates = []
        weights = []
        for name, (cls, _mut) in self.registry.items():
            if name == "blackout":
                continue
            if getattr(cls, "is_strobey", False) and self.auto_mood not in ("driving", "glitch"):
                continue
            mood = getattr(cls, "mood", "ambient")
            if self.auto_mood != "mixed" and mood != self.auto_mood:
                continue
            if name == self.current_name:
                continue  # never repeat back-to-back
            w = float(getattr(cls, "weight", 1.0))
            recency_hits = sum(1 for r in self._recency if r == name)
            w /= (1.0 + RECENCY_PENALTY * recency_hits)
            if w > 0:
                candidates.append(name)
                weights.append(w)
        if not candidates:
            return None
        return random.choices(candidates, weights=weights, k=1)[0]
