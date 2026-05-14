"""Open Fixture Library search and import.

OFL (https://open-fixture-library.org) is the largest open fixture database.
We search via their public API and convert their JSON schema (which is much
richer than ours) down to our simple `function`-based profile.

Imported profiles are flagged unverified — community channel maps for cheap
Chinese fixtures don't always match what your particular firmware does.
"""

from __future__ import annotations

import os
import re
import sys

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from shared.profile import Channel, Mode, Profile  # noqa: E402

try:
    import requests
except ImportError:
    requests = None

OFL_API = "https://open-fixture-library.org/api/v1"
OFL_RAW = "https://raw.githubusercontent.com/OpenLightingProject/open-fixture-library/master/fixtures"


def _ensure_requests():
    if requests is None:
        raise RuntimeError("OFL search needs the `requests` package — `pip install requests`")


def search(query: str, limit: int = 25) -> list[dict]:
    """Search OFL. Returns [{man, model, key, manKey}, ...]."""
    _ensure_requests()
    r = requests.post(f"{OFL_API}/get-search-results",
                      json={"searchQuery": query, "manufacturersQuery": [],
                            "categoriesQuery": []},
                      timeout=10)
    r.raise_for_status()
    out = []
    for key in r.json()[:limit]:
        man, fix = key.split("/", 1)
        out.append({"key": key, "manufacturer": man.replace("-", " ").title(),
                    "model": fix.replace("-", " ").title()})
    return out


def fetch(key: str) -> dict:
    """Fetch a fixture's raw OFL JSON. `key` is `manufacturer-slug/fixture-slug`."""
    _ensure_requests()
    r = requests.get(f"{OFL_RAW}/{key}.json", timeout=10)
    r.raise_for_status()
    return r.json()


# OFL capability `type` (and colour, for ColorIntensity) → our function.
_CAP_MAP = {
    "Intensity": "dimmer",
    "ShutterStrobe": "strobe",
    "StrobeSpeed": "strobe",
    "StrobeDuration": "strobe",
    "Pan": "pan",
    "Tilt": "tilt",
    "PanContinuous": "pan",
    "TiltContinuous": "tilt",
    "PanTiltSpeed": "pan_tilt_speed",
    "WheelSlot": "color_wheel",
    "WheelShake": "color_wheel",
    "WheelSlotRotation": "color_wheel",
    "WheelRotation": "color_wheel",
    "ColorPreset": "macro",
    "ColorTemperature": "ct_override",
    "Effect": "macro",
    "EffectSpeed": "macro_speed",
    "BeamAngle": "zoom",
    "Zoom": "zoom",
    "Focus": "focus",
    "Iris": "iris",
    "Prism": "prism",
    "PrismRotation": "prism",
    "Frost": "frost",
    "Gobo": "gobo",
    "GoboIndex": "gobo",
    "Maintenance": "reset",
    "NoFunction": "none",
}
_COLOUR_MAP = {
    "Red": "red", "Green": "green", "Blue": "blue", "White": "white",
    "Amber": "amber", "UV": "uv", "Lime": "lime", "Cyan": "cyan",
    "Magenta": "magenta", "Yellow": "yellow", "Indigo": "uv",
    "Warm White": "warm_white", "Cold White": "cool_white",
}
_TYPE_MAP = {
    "Color Changer": "par", "Moving Head": "mover", "Scanner": "mover",
    "Strobe": "strobe", "Pixel Bar": "batten", "Bar": "batten",
    "Dimmer": "generic", "Smoke": "generic", "Hazer": "generic",
    "Effect": "generic", "Other": "generic", "Matrix": "batten",
}


def _func_for_channel(name: str, ch: dict) -> str:
    """Map an OFL availableChannels entry to our function vocabulary."""
    cap = ch.get("capability") or (ch.get("capabilities") or [{}])[0]
    ctype = cap.get("type", "")
    if ctype == "ColorIntensity":
        return _COLOUR_MAP.get(cap.get("color", ""), "none")
    if ctype in _CAP_MAP:
        return _CAP_MAP[ctype]
    n = name.lower()
    if "fine" in n:
        if "pan" in n:
            return "pan_fine"
        if "tilt" in n:
            return "tilt_fine"
    return "none"


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def convert(ofl: dict, manufacturer: str = "") -> Profile:
    """Convert an OFL fixture JSON to a Profile (all modes)."""
    avail = ofl.get("availableChannels", {})
    name_to_func = {n: _func_for_channel(n, ch) for n, ch in avail.items()}

    physical = {}
    p = ofl.get("physical", {})
    if "lens" in p and p["lens"].get("degreesMinMax"):
        physical["beam_deg"] = p["lens"]["degreesMinMax"][1]
    if "focus" in p:
        if p["focus"].get("panMax"):
            physical["pan_range_deg"] = p["focus"]["panMax"]
        if p["focus"].get("tiltMax"):
            physical["tilt_range_deg"] = p["focus"]["tiltMax"]
    if p.get("power"):
        physical["watts"] = p["power"]
    if p.get("weight"):
        physical["weight_kg"] = p["weight"]

    cats = ofl.get("categories", ["Other"])
    fx_type = next((_TYPE_MAP[c] for c in cats if c in _TYPE_MAP), "generic")

    modes = []
    for m in ofl.get("modes", []):
        chans = []
        for i, cn in enumerate(m.get("channels", [])):
            if cn is None:
                continue  # OFL uses null for "no function" placeholder slots
            fn = name_to_func.get(cn, "none")
            ch = Channel(offset=i, function=fn, label=cn)
            if fn in ("macro", "macro_speed", "reset", "color_wheel", "gobo",
                      "pan_tilt_speed", "ct_override", "lamp", "zoom", "focus",
                      "iris", "prism", "frost"):
                ch.lock = True
            if fn == "master_dimmer":
                ch.lock = True
                ch.default = 255
            chans.append(ch)
        n_chans = len(m.get("channels", []))
        modes.append(Mode(
            id=_slug(m.get("shortName") or m.get("name", f"{n_chans}ch")),
            label=m.get("name", f"{n_chans}-channel"),
            footprint=max(n_chans, ((n_chans + 3) // 4) * 4),
            channels=chans,
        ))

    return Profile(
        id=_slug(f"{manufacturer}-{ofl.get('name', '')}"),
        manufacturer=manufacturer,
        model=ofl.get("name", ""),
        type=fx_type,
        physical=physical,
        verified=False,
        modes=modes,
    )
