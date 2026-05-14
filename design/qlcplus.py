"""QLC+ `.qxf` fixture definition → our profile JSON.

QLC+ fixture files are XML. The mapping that matters is QLC+'s `Preset`
attribute (the closest thing they have to a typed function vocabulary) onto
our `function` names. Channels with no recognised preset get `"none"` and
are zeroed at runtime; the Inventory tab editor is for fixing those up.

Imported profiles are flagged `"verified": false` until the user has run a
hardware sweep. Manuals lie. QLC+ profiles are mostly community-sourced and
sometimes lie too.
"""

from __future__ import annotations

import os
import re
import sys

# defusedxml protects against XXE / billion-laughs in uploaded .qxf files —
# .qxf files often come from forums and the QLC+ fixture site, not just your
# own machine, so this is a real input boundary. If defusedxml isn't
# available, fall back to stdlib but reject any input that contains a DTD
# so the unsafe parser can't be exploited.
try:
    from defusedxml import ElementTree as ET  # type: ignore
    _SAFE_XML = True
except ImportError:
    import xml.etree.ElementTree as ET
    _SAFE_XML = False


def _check_safe(xml_text: str) -> None:
    if not _SAFE_XML and ("<!DOCTYPE" in xml_text or "<!ENTITY" in xml_text):
        raise ValueError(
            "this .qxf contains a DTD, which can't be parsed safely without "
            "defusedxml — `pip install defusedxml` (it's in design/requirements.txt)"
        )

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from shared.profile import Channel, Mode, Profile  # noqa: E402

# QLC+ Preset attribute → our function name. Best-effort.
_PRESET_MAP = {
    "IntensityMasterDimmer": "master_dimmer",
    "IntensityDimmer": "dimmer",
    "IntensityRed": "red",
    "IntensityGreen": "green",
    "IntensityBlue": "blue",
    "IntensityWhite": "white",
    "IntensityAmber": "amber",
    "IntensityUV": "uv",
    "IntensityLime": "lime",
    "IntensityIndigo": "uv",
    "IntensityCyan": "cyan",
    "IntensityMagenta": "magenta",
    "IntensityYellow": "yellow",
    "IntensityWarmWhite": "warm_white",
    "IntensityColdWhite": "cool_white",
    "PositionPan": "pan",
    "PositionPanFine": "pan_fine",
    "PositionTilt": "tilt",
    "PositionTiltFine": "tilt_fine",
    "SpeedPanTiltSlowFast": "pan_tilt_speed",
    "SpeedPanTiltFastSlow": "pan_tilt_speed",
    "ShutterStrobeSlowFast": "strobe",
    "ShutterStrobeFastSlow": "strobe",
    "ColorWheel": "color_wheel",
    "ColorMacro": "macro",
    "ColorRGBMixer": "macro",
    "GoboWheel": "gobo",
    "GoboIndex": "gobo",
    "GoboWheelFine": "gobo",
    "BeamZoomSmallBig": "zoom",
    "BeamZoomBigSmall": "zoom",
    "BeamFocusNearFar": "focus",
    "BeamFocusFarNear": "focus",
    "BeamIris": "iris",
    "PrismRotationSlowFast": "prism",
    "PrismRotationFastSlow": "prism",
    "ResetAll": "reset",
    "Maintenance": "reset",
    "LampOn": "lamp",
    "LampOff": "lamp",
    "NoFunction": "none",
}

# Fall back to keyword matching on the channel name when there's no Preset.
_NAME_PATTERNS = [
    (r"\bmaster\b.*\bdim", "master_dimmer"),
    (r"\bdim", "dimmer"),
    (r"\bbright", "dimmer"),
    (r"\bpan\b.*\bfine", "pan_fine"),
    (r"\bpan\b", "pan"),
    (r"\btilt\b.*\bfine", "tilt_fine"),
    (r"\btilt\b", "tilt"),
    (r"\bspeed\b", "pan_tilt_speed"),
    (r"\bred\b", "red"),
    (r"\bgreen\b", "green"),
    (r"\bblue\b", "blue"),
    (r"\bwhite\b", "white"),
    (r"\bamber\b", "amber"),
    (r"\blime\b", "lime"),
    (r"\buv\b|\bultra", "uv"),
    (r"\bstrobe\b|\bshutter\b", "strobe"),
    (r"\bcolou?r\b", "color_wheel"),
    (r"\bgobo\b|\bpattern\b", "gobo"),
    (r"\bzoom\b", "zoom"),
    (r"\bfocus\b", "focus"),
    (r"\biris\b", "iris"),
    (r"\bprism\b", "prism"),
    (r"\bfrost\b", "frost"),
    (r"\bauto\b|\bmacro\b|\bprogram\b", "macro"),
    (r"\breset\b", "reset"),
]

_QLC_TYPE_TO_OURS = {
    "Color Changer": "par",
    "Moving Head": "mover",
    "LED Bar (Pixels)": "batten",
    "LED Bar (Beams)": "batten",
    "Strobe": "strobe",
    "Dimmer": "generic",
    "Scanner": "mover",
    "Smoke": "generic",
    "Hazer": "generic",
    "Effect": "generic",
}


def _func_for(name: str, preset: str | None) -> str:
    if preset and preset in _PRESET_MAP:
        return _PRESET_MAP[preset]
    n = name.lower()
    for pat, fn in _NAME_PATTERNS:
        if re.search(pat, n):
            return fn
    return "none"


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def parse_qxf(xml_text: str) -> Profile:
    """Parse a QLC+ .qxf XML document into a Profile."""
    _check_safe(xml_text)
    root = ET.fromstring(xml_text)
    ns = "" if "}" not in root.tag else root.tag.split("}")[0] + "}"

    def find(parent, tag):
        return parent.find(f"{ns}{tag}")

    def findall(parent, tag):
        return parent.findall(f"{ns}{tag}")

    def text(parent, tag, default=""):
        el = find(parent, tag)
        return el.text.strip() if el is not None and el.text else default

    manufacturer = text(root, "Manufacturer")
    model = text(root, "Model")
    qlc_type = text(root, "Type", "Color Changer")

    # Channel definitions are global; modes reference them by name.
    chan_defs: dict[str, str] = {}  # name -> function
    for ch in findall(root, "Channel"):
        name = ch.get("Name", "")
        preset = ch.get("Preset")
        chan_defs[name] = _func_for(name, preset)

    # Physical block
    physical = {}
    phys = find(root, "Physical")
    if phys is not None:
        def _attr(parent_tag, attr, key, scale=1.0, nonzero=False):
            el = find(phys, parent_tag)
            v = el.get(attr) if el is not None else None
            if v:
                fv = float(v) * scale
                if not nonzero or fv:
                    physical[key] = fv
        _attr("Lens", "DegreesMax", "beam_deg", nonzero=True)
        _attr("Focus", "PanMax", "pan_range_deg")
        _attr("Focus", "TiltMax", "tilt_range_deg")
        _attr("Dimensions", "Weight", "weight_kg")
        _attr("Technical", "PowerConsumption", "watts")
        _attr("Bulb", "Lumens", "luminous_flux_lm")

    modes = []
    for mode_el in findall(root, "Mode"):
        mode_name = mode_el.get("Name", "default")
        channels = []
        for mch in findall(mode_el, "Channel"):
            num = int(mch.get("Number", 0))
            chan_name = (mch.text or "").strip()
            fn = chan_defs.get(chan_name, _func_for(chan_name, None))
            ch = Channel(offset=num, function=fn, label=chan_name)
            # Lock anything that's clearly a control channel — the safest
            # default for an unverified profile.
            if fn in ("macro", "macro_speed", "reset", "color_wheel", "gobo",
                      "pan_tilt_speed", "ct_override", "lamp"):
                ch.lock = True
            if fn == "master_dimmer":
                ch.lock = True
                ch.default = 255
            channels.append(ch)
        n_chans = len(channels)
        # Pad footprint a couple of slots for unverified fixtures —
        # we got bitten by an undocumented CH11 once.
        footprint = max(n_chans, ((n_chans + 3) // 4) * 4)
        modes.append(Mode(
            id=_slug(mode_name) or f"{n_chans}ch",
            label=mode_name,
            footprint=footprint,
            channels=channels,
        ))

    return Profile(
        id=_slug(f"{manufacturer}-{model}"),
        manufacturer=manufacturer,
        model=model,
        type=_QLC_TYPE_TO_OURS.get(qlc_type, "generic"),
        physical=physical,
        verified=False,
        modes=modes,
    )
