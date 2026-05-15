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


# ----------------------------------------------------------------- write-back
#
# `to_ofl()` is the inverse of `convert()` for upstreaming verified profiles.
# The output is a *starting point* for an OFL contribution, not a finished
# submission — OFL's schema is richer than ours (capability ranges, wheels,
# pixel matrices, RDM). The user pastes it into the OFL fixture editor at
# https://open-fixture-library.org/fixture-editor/import and fills in the
# rest. No GitHub auth in this app.

# Inverse of _CAP_MAP / _COLOUR_MAP — our function -> OFL capability dict.
_FUNC_TO_CAP = {
    "master_dimmer": {"type": "Intensity"},
    "dimmer": {"type": "Intensity"},
    "red": {"type": "ColorIntensity", "color": "Red"},
    "green": {"type": "ColorIntensity", "color": "Green"},
    "blue": {"type": "ColorIntensity", "color": "Blue"},
    "white": {"type": "ColorIntensity", "color": "White"},
    "warm_white": {"type": "ColorIntensity", "color": "Warm White"},
    "cool_white": {"type": "ColorIntensity", "color": "Cold White"},
    "lime": {"type": "ColorIntensity", "color": "Lime"},
    "amber": {"type": "ColorIntensity", "color": "Amber"},
    "uv": {"type": "ColorIntensity", "color": "UV"},
    "cyan": {"type": "ColorIntensity", "color": "Cyan"},
    "magenta": {"type": "ColorIntensity", "color": "Magenta"},
    "yellow": {"type": "ColorIntensity", "color": "Yellow"},
    "strobe": {"type": "ShutterStrobe", "shutterEffect": "Strobe",
               "speedStart": "slow", "speedEnd": "fast"},
    "shutter": {"type": "ShutterStrobe", "shutterEffect": "Open"},
    "pan": {"type": "Pan", "angleStart": "0deg", "angleEnd": "540deg"},
    "pan_fine": {"type": "Pan", "angleStart": "0deg", "angleEnd": "540deg"},
    "tilt": {"type": "Tilt", "angleStart": "0deg", "angleEnd": "270deg"},
    "tilt_fine": {"type": "Tilt", "angleStart": "0deg", "angleEnd": "270deg"},
    "pan_tilt_speed": {"type": "PanTiltSpeed", "speedStart": "fast", "speedEnd": "slow"},
    "color_wheel": {"type": "WheelSlot", "slotNumber": 1},
    "gobo": {"type": "WheelSlot", "slotNumber": 1},
    "gobo_rotation": {"type": "WheelSlotRotation", "speedStart": "slow CW", "speedEnd": "fast CW"},
    "zoom": {"type": "Zoom", "angleStart": "narrow", "angleEnd": "wide"},
    "focus": {"type": "Focus", "distanceStart": "near", "distanceEnd": "far"},
    "iris": {"type": "Iris", "openPercentStart": "closed", "openPercentEnd": "open"},
    "prism": {"type": "Prism"},
    "frost": {"type": "Frost", "frostIntensityStart": "0%", "frostIntensityEnd": "100%"},
    "macro": {"type": "Effect", "effectName": "Built-in programs"},
    "macro_speed": {"type": "EffectSpeed", "speedStart": "slow", "speedEnd": "fast"},
    "speed": {"type": "Speed", "speedStart": "slow", "speedEnd": "fast"},
    "ct_override": {"type": "ColorTemperature", "colorTemperatureStart": "warm", "colorTemperatureEnd": "cold"},
    "reset": {"type": "Maintenance", "comment": "Reset"},
    "lamp": {"type": "Maintenance", "comment": "Lamp control"},
    "none": {"type": "NoFunction"},
}

_TYPE_TO_CAT = {
    "par": "Color Changer", "wash": "Color Changer", "spot": "Color Changer",
    "mover": "Moving Head", "batten": "Pixel Bar", "strobe": "Strobe",
    "generic": "Other",
}

# OFL channel names should be human-readable — turn our function slugs into
# title-cased labels. Channels with the same function in different modes
# need distinct names in `availableChannels`.
_FUNC_LABEL = {
    "master_dimmer": "Master Dimmer", "dimmer": "Dimmer",
    "red": "Red", "green": "Green", "blue": "Blue", "white": "White",
    "warm_white": "Warm White", "cool_white": "Cold White",
    "lime": "Lime", "amber": "Amber", "uv": "UV", "cyan": "Cyan",
    "magenta": "Magenta", "yellow": "Yellow",
    "strobe": "Strobe", "shutter": "Shutter",
    "pan": "Pan", "pan_fine": "Pan Fine", "tilt": "Tilt", "tilt_fine": "Tilt Fine",
    "pan_tilt_speed": "Pan/Tilt Speed",
    "color_wheel": "Color Wheel", "gobo": "Gobo Wheel", "gobo_rotation": "Gobo Rotation",
    "zoom": "Zoom", "focus": "Focus", "iris": "Iris", "prism": "Prism", "frost": "Frost",
    "macro": "Program", "macro_speed": "Program Speed", "speed": "Speed",
    "ct_override": "Color Temperature", "reset": "Reset", "lamp": "Lamp",
    "none": "Unused",
}


def to_ofl(profile: Profile, author: str = "dmx-ai") -> dict:
    """Convert one of our profiles to an OFL fixture JSON. Best-effort —
    OFL's schema is richer than ours, so the output needs hand-finishing in
    the OFL fixture editor before submission. Movers especially: OFL wants
    explicit wheel slot definitions and pan/tilt angles which we don't store."""
    from datetime import date

    physical = {}
    p = profile.physical or {}
    if p.get("watts"):
        physical["power"] = p["watts"]
    if p.get("weight_kg"):
        physical["weight"] = p["weight_kg"]
    if p.get("beam_deg"):
        physical["lens"] = {"degreesMinMax": [p["beam_deg"], p["beam_deg"]]}
    if p.get("pan_range_deg") or p.get("tilt_range_deg"):
        physical["focus"] = {"type": "Head"}
        if p.get("pan_range_deg"):
            physical["focus"]["panMax"] = p["pan_range_deg"]
        if p.get("tilt_range_deg"):
            physical["focus"]["tiltMax"] = p["tilt_range_deg"]

    # Build availableChannels. OFL channels are a shared pool keyed by name;
    # modes reference them. The same function across modes (e.g. "Red" in
    # 6ch and 10ch) reuses one entry. Two channels with the same function
    # but different defaults/labels get a numeric suffix — rare, but our
    # validator already flags it on a single mode so this is belt-and-braces.
    avail: dict[str, dict] = {}
    mode_chans: list[tuple[str, list[str | None]]] = []
    for mode in profile.modes:
        n_slots = max((c.offset for c in mode.channels), default=-1) + 1
        slots: list[str | None] = [None] * n_slots
        for ch in mode.channels:
            cap = dict(_FUNC_TO_CAP.get(ch.function, {"type": "NoFunction"}))
            if ch.label:
                cap.setdefault("comment", ch.label)
            entry: dict = {"capability": cap}
            if ch.default:
                entry["defaultValue"] = ch.default
            base = _FUNC_LABEL.get(ch.function, ch.function.replace("_", " ").title())
            # Reuse an existing channel definition if the capability type
            # matches — the same emitter referenced from two modes should be
            # one OFL channel even if the label/comment differs. Disambiguate
            # only when the capability *type* genuinely diverges.
            name = base
            suffix = 1
            while name in avail and avail[name]["capability"]["type"] != cap["type"]:
                suffix += 1
                name = f"{base} {suffix}"
            if name not in avail:
                avail[name] = entry
            slots[ch.offset] = name
        mode_chans.append((mode.label or mode.id, slots))

    today = date.today().isoformat()
    out: dict = {
        "$schema": "https://raw.githubusercontent.com/OpenLightingProject/"
                   "open-fixture-library/master/schemas/fixture.json",
        "name": profile.model or profile.id,
        "categories": [_TYPE_TO_CAT.get(profile.type, "Other")],
        "meta": {
            "authors": [author],
            "createDate": today,
            "lastModifyDate": today,
        },
        "comment": (
            f"Exported from dmx-ai. "
            f"{'Hardware-verified.' if profile.verified else 'NOT hardware-verified — sweep before trusting.'} "
            f"Footprints in the source profile may be padded above the channel "
            f"count (a defensive habit after an undocumented CH11 bit us)."
        ),
    }
    if physical:
        out["physical"] = physical
    out["availableChannels"] = avail
    out["modes"] = [{"name": name, "channels": chans} for name, chans in mode_chans]
    return out


# OFL's editor doesn't accept a pre-filled fixture via URL — you download
# the JSON here and submit it through their editor or as a GitHub PR.
EDITOR_URL = "https://open-fixture-library.org/fixture-editor"
CONTRIB_URL = "https://github.com/OpenLightingProject/open-fixture-library/blob/master/CONTRIBUTING.md"


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
