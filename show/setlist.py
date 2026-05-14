"""Setlist loader / saver.

The setlist is a YAML file mapping songs to lighting presets so the FOH
operator doesn't have to remember which scene fits which song. Tap a song,
the scene loads, swap back to the mixer.

Each song carries:
    title, artist (display only)
    section          — "Set 1" / "Set 2" / "Encore" (rendered as headers)
    scene            — registry key (e.g. "pop", "embers")
    hue              — 0..359, optional, defaults to 0
    bpm              — optional, locks the beat clock
    notes            — optional free text shown in the editor

The file is gig-specific — `.gitignore`d by default. Keep multiple files
and pass `--setlist <path>` to swap between gigs.
"""

from __future__ import annotations

import os
import threading

import yaml

DEFAULT_PATH = "setlist.yaml"


class Setlist:
    """Thread-safe wrapper around a setlist YAML file."""

    def __init__(self, path: str = DEFAULT_PATH):
        self.path = path
        self._lock = threading.Lock()
        self._data = {"name": "Setlist", "between": {"scene": "warm"}, "songs": []}
        self.current = -1  # index of the last-played song; -1 = none
        self.load()

    def load(self) -> None:
        with self._lock:
            if not os.path.exists(self.path):
                return
            try:
                with open(self.path, encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                if isinstance(data, dict) and isinstance(data.get("songs"), list):
                    self._data = data
            except Exception:
                pass  # malformed file — keep the previous data

    def save(self) -> None:
        with self._lock:
            with open(self.path, "w", encoding="utf-8") as f:
                yaml.safe_dump(self._data, f, sort_keys=False, allow_unicode=True,
                               default_flow_style=False, width=120)

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "name": self._data.get("name", "Setlist"),
                "between": self._data.get("between", {"scene": "warm"}),
                "songs": list(self._data.get("songs", [])),
                "current": self.current,
            }

    def song(self, index: int) -> dict | None:
        with self._lock:
            songs = self._data.get("songs", [])
            if 0 <= index < len(songs):
                return dict(songs[index])
        return None

    def update_song(self, index: int, fields: dict) -> bool:
        with self._lock:
            songs = self._data.get("songs", [])
            if not (0 <= index < len(songs)):
                return False
            allowed = {"title", "artist", "section", "scene", "hue", "bpm", "notes"}
            for k, v in fields.items():
                if k in allowed:
                    if v in (None, ""):
                        songs[index].pop(k, None)
                    else:
                        songs[index][k] = v
        self.save()
        return True

    def set_current(self, index: int) -> None:
        with self._lock:
            self.current = index
