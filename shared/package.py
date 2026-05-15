"""Show-package export.

A show package is the contract between the Design app (laptop, pre-show) and
the Show app (Pi, gig-time, offline). It's a zip containing exactly what the
Pi needs to run a gig with no network:

    rig.json            ← the active rig
    profiles/<id>.json  ← only the profiles that rig uses
    setlist.yaml        ← copy of the setlist if one was supplied
    package.json        ← manifest: rig name, profile ids, generated_at

Extract it into ``show/data/`` on the Pi and restart — ``show/fixtures.py``
already prefers ``show/data/rig.json`` and ``show/data/profiles/`` over the
repo's ``data/`` if they exist.
"""

from __future__ import annotations

import io
import json
import os
import zipfile
from datetime import datetime, timezone

from .profile import ProfileRegistry
from .rig import Rig


def build_package(rig: Rig, profiles: ProfileRegistry,
                  setlist_path: str | None = None) -> bytes:
    """Bundle a rig + its profiles (+ optional setlist) into an in-memory zip.

    Only profiles the rig actually references are included; unknown profile
    ids are skipped (the rig validation step already flags them as warnings).
    """
    used_ids = sorted({fx.profile for fx in rig.fixtures})
    bundled: list[str] = []

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("rig.json", _dumps(rig.to_dict()))
        for pid in used_ids:
            try:
                p = profiles.get(pid)
            except KeyError:
                continue
            z.writestr(f"profiles/{pid}.json", _dumps(p.to_dict()))
            bundled.append(pid)
        if setlist_path and os.path.isfile(setlist_path):
            with open(setlist_path, "rb") as f:
                z.writestr("setlist.yaml", f.read())
        z.writestr("package.json", _dumps({
            "rig": rig.name,
            "fixtures": len(rig.fixtures),
            "profiles": bundled,
            "missing_profiles": sorted(set(used_ids) - set(bundled)),
            "setlist": bool(setlist_path and os.path.isfile(setlist_path)),
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }))
    return buf.getvalue()


def _dumps(d: dict) -> str:
    return json.dumps(d, indent=2, ensure_ascii=False) + "\n"
