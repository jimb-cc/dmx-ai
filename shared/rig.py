"""Rig schema, validation, conflict detection, and auto-patching.

A rig describes which physical fixtures are where on stage, what addresses
they're patched at, and how they're grouped. Both apps use this — the Design
app for the Rigging tab, the Show app to build the Fixture list at startup.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from .profile import Profile, ProfileRegistry


@dataclass
class RigFixture:
    id: str
    profile: str
    mode: str
    address: int
    universe: int = 1
    label: str = ""
    x: float = 0.0
    y: float = 0.0
    z: float = 2.0
    facing_deg: float = 0.0
    tilt_deg: float = -10.0
    groups: list[str] = field(default_factory=list)
    # Skip the master-fader scaling on this fixture's intensity. A 100W spot
    # already looks weak next to four LED pars at point-blank range — turning
    # it down further with the master makes it disappear. Set per-rig because
    # it depends on the room and the brightness mix, not the fixture itself.
    ignore_master: bool = False

    @classmethod
    def from_dict(cls, d: dict) -> "RigFixture":
        return cls(
            id=str(d["id"]),
            profile=str(d["profile"]),
            mode=str(d["mode"]),
            address=int(d["address"]),
            universe=int(d.get("universe", 1)),
            label=str(d.get("label", d["id"])),
            x=float(d.get("x", 0.0)),
            y=float(d.get("y", 0.0)),
            z=float(d.get("z", 2.0)),
            facing_deg=float(d.get("facing_deg", 0.0)),
            tilt_deg=float(d.get("tilt_deg", -10.0)),
            groups=list(d.get("groups", [])),
            ignore_master=bool(d.get("ignore_master", False)),
        )

    def to_dict(self) -> dict:
        d = {
            "id": self.id, "label": self.label, "profile": self.profile,
            "mode": self.mode, "universe": self.universe, "address": self.address,
            "x": self.x, "y": self.y, "z": self.z,
            "facing_deg": self.facing_deg, "tilt_deg": self.tilt_deg,
            "groups": self.groups,
        }
        if self.ignore_master:
            d["ignore_master"] = True
        return d


@dataclass
class Rig:
    name: str = "Rig"
    stage: dict = field(default_factory=lambda: {"width_m": 5.0, "depth_m": 3.0})
    fixtures: list[RigFixture] = field(default_factory=list)
    _profiles: ProfileRegistry | None = field(default=None, repr=False)

    @classmethod
    def from_dict(cls, d: dict, profiles: ProfileRegistry | None = None) -> "Rig":
        return cls(
            name=str(d.get("name", "Rig")),
            stage=dict(d.get("stage", {})),
            fixtures=[RigFixture.from_dict(f) for f in d.get("fixtures", [])],
            _profiles=profiles,
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "stage": self.stage,
            "fixtures": [f.to_dict() for f in self.fixtures],
        }

    # -- helpers that need profile lookup -----------------------------------

    def profile_of(self, fx: RigFixture) -> Profile:
        if self._profiles is None:
            raise RuntimeError("Rig has no ProfileRegistry attached")
        return self._profiles.get(fx.profile)

    def footprint_of(self, fx: RigFixture) -> int:
        return self.profile_of(fx).mode(fx.mode).footprint

    def conflicts(self) -> list[tuple[str, str, tuple[int, int]]]:
        """Pairs of fixture ids with overlapping address ranges in the same
        universe. Returns [(id_a, id_b, (overlap_start, overlap_end)), ...]."""
        out = []
        spans = []
        for fx in self.fixtures:
            try:
                fp = self.footprint_of(fx)
            except Exception:
                fp = 1
            spans.append((fx.universe, fx.address, fx.address + fp - 1, fx.id))
        for i, (au, a1, a2, aid) in enumerate(spans):
            for bu, b1, b2, bid in spans[i + 1:]:
                if au != bu:
                    continue
                lo, hi = max(a1, b1), min(a2, b2)
                if lo <= hi:
                    out.append((aid, bid, (lo, hi)))
        return out

    def auto_patch(self, start: int = 1, universe: int = 1) -> None:
        """Assign sequential addresses with footprint spacing, in fixture order."""
        addr = start
        for fx in self.fixtures:
            if fx.universe != universe:
                continue
            fx.address = addr
            try:
                addr += self.footprint_of(fx)
            except Exception:
                addr += 16

    def cheat_sheet(self) -> list[dict]:
        """Per-fixture rigging notes for the printable plan."""
        out = []
        for fx in self.fixtures:
            try:
                p = self.profile_of(fx)
                mode_label = p.mode(fx.mode).label
                model = f"{p.manufacturer} {p.model}".strip() or p.id
            except Exception:
                mode_label = fx.mode
                model = fx.profile
            out.append({
                "id": fx.id,
                "label": fx.label,
                "model": model,
                "mode": mode_label,
                "universe": fx.universe,
                "address": fx.address,
                "groups": fx.groups,
            })
        return out

    def validate(self) -> list[str]:
        errs = []
        seen_ids = set()
        for fx in self.fixtures:
            if fx.id in seen_ids:
                errs.append(f"duplicate fixture id {fx.id!r}")
            seen_ids.add(fx.id)
            if not (1 <= fx.address <= 512):
                errs.append(f"{fx.id}: address {fx.address} out of range 1-512")
            if self._profiles is not None:
                if fx.profile not in self._profiles:
                    errs.append(f"{fx.id}: unknown profile {fx.profile!r}")
                else:
                    p = self._profiles.get(fx.profile)
                    if not any(m.id == fx.mode for m in p.modes):
                        errs.append(f"{fx.id}: profile {fx.profile!r} has no mode "
                                    f"{fx.mode!r}")
                    elif fx.address + p.mode(fx.mode).footprint - 1 > 512:
                        errs.append(f"{fx.id}: footprint overruns universe end")
        for a, b, (lo, hi) in self.conflicts():
            errs.append(f"address conflict: {a} and {b} overlap at DMX {lo}-{hi}")
        return errs


def load(path: str, profiles: ProfileRegistry | None = None) -> Rig:
    with open(path, encoding="utf-8") as f:
        return Rig.from_dict(json.load(f), profiles)


def save(rig: Rig, path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rig.to_dict(), f, indent=2, ensure_ascii=False)
        f.write("\n")
