"""Design app backend.

Flask API the React frontend talks to. Reads/writes the flat JSON files in
data/. Migrating to MongoDB later means swapping the load/save functions —
the document shapes are unchanged.

    python3 design/server.py            # serves on :5050
    cd design/frontend && npm run dev   # Vite on :5173, proxies /api here
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys

from flask import Flask, Response, abort, jsonify, request, send_from_directory

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

import ofl  # noqa: E402
import preview  # noqa: E402
import qlcplus  # noqa: E402
from shared.package import build_package  # noqa: E402
from shared.profile import FIXTURE_TYPES, FUNCTIONS, Profile, ProfileRegistry, validate  # noqa: E402
from shared.rig import Rig, save as save_rig  # noqa: E402

DATA = os.path.join(_root, "data")
PROFILES_DIR = os.path.join(DATA, "profiles")
RIGS_DIR = os.path.join(DATA, "rigs")
SETLIST_PATH = os.path.join(_root, "show", "setlist.yaml")
FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "frontend", "dist")

app = Flask(__name__)
log = logging.getLogger("design")

# IDs / file names must be plain slugs — closes path traversal on the
# data/ directory writes/deletes.
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


def _safe_slug(s: str) -> str:
    if not _SLUG_RE.match(s):
        abort(400, description=f"invalid identifier {s!r}")
    return s


@app.before_request
def _csrf_guard():
    """Reject cross-site writes. The Design app writes to the local
    filesystem, so a malicious page POSTing to localhost:5050 from the
    user's browser is a real attack. Browsers send Sec-Fetch-Site on
    fetch(); require same-origin (or absent — non-browser tools)."""
    if request.method in ("POST", "PUT", "DELETE"):
        site = request.headers.get("Sec-Fetch-Site")
        if site not in (None, "same-origin", "none"):
            abort(403, description="cross-site request blocked")


# --------------------------------------------------------------------- profiles

def _profile_path(pid: str) -> str:
    return os.path.join(PROFILES_DIR, f"{_safe_slug(pid)}.json")


def _load_profile(pid: str) -> dict | None:
    p = _profile_path(pid)
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _save_profile(d: dict) -> None:
    os.makedirs(PROFILES_DIR, exist_ok=True)
    with open(_profile_path(d["id"]), "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
        f.write("\n")


@app.get("/api/meta")
def api_meta():
    """Vocabulary the frontend's dropdowns need."""
    return jsonify(functions=list(FUNCTIONS), fixture_types=list(FIXTURE_TYPES))


@app.get("/api/profiles")
def api_profiles_list():
    out = []
    if os.path.isdir(PROFILES_DIR):
        for fn in sorted(os.listdir(PROFILES_DIR)):
            if not fn.endswith(".json"):
                continue
            try:
                with open(os.path.join(PROFILES_DIR, fn), encoding="utf-8") as f:
                    out.append(json.load(f))
            except Exception as e:
                log.warning("skipped %s: %s", fn, e)
    return jsonify(profiles=out)


@app.get("/api/profiles/<pid>")
def api_profile_get(pid):
    d = _load_profile(pid)
    if d is None:
        return jsonify(error="not found"), 404
    return jsonify(d)


@app.put("/api/profiles/<pid>")
def api_profile_put(pid):
    d = request.get_json(silent=True)
    if not d:
        return jsonify(error="bad JSON"), 400
    d["id"] = pid
    errs = validate(Profile.from_dict(d))
    if errs:
        return jsonify(error="validation failed", details=errs), 422
    _save_profile(d)
    return jsonify(d)


@app.delete("/api/profiles/<pid>")
def api_profile_delete(pid):
    p = _profile_path(pid)
    if os.path.isfile(p):
        os.remove(p)
    return jsonify(ok=True)


@app.post("/api/profiles/import/qxf")
def api_import_qxf():
    """Upload a QLC+ .qxf, convert, save, return."""
    f = request.files.get("file")
    if not f:
        return jsonify(error="no file"), 400
    try:
        prof = qlcplus.parse_qxf(f.read().decode("utf-8", errors="replace"))
    except Exception as e:
        return jsonify(error=f"parse failed: {e}"), 400
    d = prof.to_dict()
    if _load_profile(d["id"]):
        d["id"] = d["id"] + "-imported"
    _save_profile(d)
    return jsonify(d)


# -------------------------------------------------------------------------- OFL

@app.get("/api/ofl/search")
def api_ofl_search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify(results=[])
    try:
        return jsonify(results=ofl.search(q))
    except Exception as e:
        return jsonify(error=str(e)), 502


@app.get("/api/ofl/manufacturers")
def api_ofl_manufacturers():
    """All OFL manufacturers, cached server-side for ~24h. `?refresh=1` busts
    the cache."""
    try:
        return jsonify(manufacturers=ofl.manufacturers(force=request.args.get("refresh") == "1"))
    except Exception as e:
        return jsonify(error=str(e)), 502


@app.get("/api/ofl/manufacturers/<slug>")
def api_ofl_manufacturer_fixtures(slug):
    """All fixtures for one OFL manufacturer, cached. `?refresh=1` busts."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug):
        return jsonify(error="bad manufacturer slug"), 400
    try:
        return jsonify(fixtures=ofl.fixtures_for(slug, force=request.args.get("refresh") == "1"))
    except Exception as e:
        return jsonify(error=str(e)), 502


@app.get("/api/profiles/<pid>/ofl")
def api_profile_export_ofl(pid):
    """Download an OFL-format JSON for upstreaming a verified profile."""
    d = _load_profile(pid)
    if d is None:
        return jsonify(error="not found"), 404
    out = ofl.to_ofl(Profile.from_dict(d))
    body = json.dumps(out, indent=2, ensure_ascii=False) + "\n"
    return Response(body, mimetype="application/json", headers={
        "Content-Disposition": f"attachment; filename={_safe_slug(pid)}.ofl.json",
    })


@app.post("/api/ofl/import")
def api_ofl_import():
    body = request.get_json(silent=True) or {}
    key = body.get("key", "")
    # OFL keys are manufacturer-slug/fixture-slug. Validate the shape so
    # `key` can't steer the request elsewhere on the OFL host.
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*\/[a-z0-9][a-z0-9-]*", key):
        return jsonify(error="bad key"), 400
    try:
        raw = ofl.fetch(key)
        prof = ofl.convert(raw, manufacturer=body.get("manufacturer", key.split("/")[0]))
    except Exception as e:
        return jsonify(error=f"OFL import failed: {e}"), 502
    d = prof.to_dict()
    if _load_profile(d["id"]):
        d["id"] = d["id"] + "-ofl"
    _save_profile(d)
    return jsonify(d)


# ------------------------------------------------------------------------- rigs

def _rig_path(name: str) -> str:
    return os.path.join(RIGS_DIR, f"{_safe_slug(name)}.json")


@app.get("/api/rigs")
def api_rigs_list():
    out = []
    if os.path.isdir(RIGS_DIR):
        for fn in sorted(os.listdir(RIGS_DIR)):
            if fn.endswith(".json"):
                try:
                    with open(os.path.join(RIGS_DIR, fn), encoding="utf-8") as f:
                        d = json.load(f)
                    out.append({"file": fn[:-5], "name": d.get("name", fn),
                                "fixtures": len(d.get("fixtures", []))})
                except Exception:
                    pass
    return jsonify(rigs=out)


@app.get("/api/rigs/<name>")
def api_rig_get(name):
    p = _rig_path(name)
    if not os.path.isfile(p):
        return jsonify(error="not found"), 404
    with open(p, encoding="utf-8") as f:
        return jsonify(json.load(f))


@app.put("/api/rigs/<name>")
def api_rig_put(name):
    d = request.get_json(silent=True)
    if not d:
        return jsonify(error="bad JSON"), 400
    reg = ProfileRegistry(PROFILES_DIR)
    rig = Rig.from_dict(d, reg)
    errs = rig.validate()
    save_rig(rig, _rig_path(name))
    return jsonify(rig=rig.to_dict(), warnings=errs)


@app.delete("/api/rigs/<name>")
def api_rig_delete(name):
    p = _rig_path(name)
    if os.path.isfile(p):
        os.remove(p)
    return jsonify(ok=True)


@app.post("/api/rigs/<name>/auto_patch")
def api_rig_auto_patch(name):
    """Run the canonical Python auto-patcher on the posted rig body and
    return the result *without saving* — the frontend keeps the rig dirty
    until the user hits Save. `name` is unused but kept for URL symmetry."""
    _safe_slug(name)
    d = request.get_json(silent=True)
    if not d:
        return jsonify(error="bad JSON"), 400
    body = d.get("rig", d)
    reg = ProfileRegistry(PROFILES_DIR)
    rig = Rig.from_dict(body, reg)
    rig.auto_patch(start=int(d.get("start", 1)), universe=int(d.get("universe", 1)))
    return jsonify(rig=rig.to_dict(), warnings=rig.validate())


@app.get("/api/export/<name>")
def api_export(name):
    """Bundle a saved rig + the profiles it uses into a show-package zip.
    Extract into show/data/ on the Pi."""
    p = _rig_path(name)
    if not os.path.isfile(p):
        return jsonify(error="not found"), 404
    reg = ProfileRegistry(PROFILES_DIR)
    with open(p, encoding="utf-8") as f:
        rig = Rig.from_dict(json.load(f), reg)
    setlist = os.path.join(_root, "show", "setlist.yaml")
    data = build_package(rig, reg, setlist_path=setlist if os.path.isfile(setlist) else None)
    return Response(data, mimetype="application/zip", headers={
        "Content-Disposition": f"attachment; filename={_safe_slug(name)}-package.zip",
    })


# -------------------------------------------------------------- setlist + preview

@app.get("/api/setlist")
def api_setlist_get():
    """Read show/setlist.yaml. Same shape the Show app's Setlist class uses,
    minus the `current` runtime field."""
    import yaml
    if not os.path.isfile(SETLIST_PATH):
        return jsonify(name="Setlist", between={"scene": "warm"}, songs=[])
    try:
        with open(SETLIST_PATH, encoding="utf-8") as f:
            d = yaml.safe_load(f) or {}
    except Exception as e:
        return jsonify(error=f"setlist parse failed: {e}"), 500
    return jsonify(name=d.get("name", "Setlist"),
                   between=d.get("between", {"scene": "warm"}),
                   songs=list(d.get("songs", [])))


# Output key order — matches the existing show/setlist.yaml so the first
# Design-app save doesn't produce a noisy reorder-only diff.
_SONG_KEYS = ("title", "artist", "section", "scene", "bpm", "hue", "choreo", "notes")


def _clean_song(s: dict) -> dict:
    """Drop empty/unknown fields so the YAML stays terse and hand-editable."""
    out = {}
    for k in _SONG_KEYS:
        v = s.get(k)
        if v in (None, "", 0) and k not in ("hue", "bpm"):
            continue
        if k in ("hue", "bpm") and not v:
            continue
        out[k] = v
    return out


@app.put("/api/setlist")
def api_setlist_put():
    import yaml
    d = request.get_json(silent=True)
    if not d or not isinstance(d.get("songs"), list):
        return jsonify(error="bad JSON — need at least {songs: [...]}"), 400
    out = {
        "name": str(d.get("name", "Setlist")),
        "between": _clean_song(d.get("between", {})) or {"scene": "warm"},
        "songs": [_clean_song(s) for s in d["songs"]],
    }
    with open(SETLIST_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(out, f, sort_keys=False, allow_unicode=True,
                       default_flow_style=False, width=120)
    return jsonify(out)


@app.get("/api/scenes")
def api_scenes():
    """The Show app's scene catalogue — name, label, mood, weight."""
    return jsonify(scenes=preview.catalogue(), choreos=preview.choreo_catalogue())


@app.get("/api/preview")
def api_preview():
    """Render N seconds of a scene against the rig and return per-fixture
    screen-RGB frames. Cheap enough to call live as the user scrubs sliders."""
    scene = request.args.get("scene", "")
    try:
        out = preview.render(
            scene,
            hue=float(request.args.get("hue", 0)),
            bpm=float(request.args.get("bpm", 120)),
            floor=float(request.args.get("floor", 0.12)),
            secs=min(20.0, max(1.0, float(request.args.get("secs", 6)))),
            fps=min(30, max(2, int(request.args.get("fps", 12)))),
            choreo=request.args.get("choreo") or None,
            rig_path=None,
        )
    except KeyError:
        return jsonify(error=f"unknown scene {scene!r}"), 404
    except Exception as e:
        log.exception("preview failed")
        return jsonify(error=f"preview failed: {e}"), 500
    return jsonify(out)


# --------------------------------------------------------------------- frontend

@app.get("/")
@app.get("/<path:path>")
def serve_frontend(path="index.html"):
    if os.path.isdir(FRONTEND_DIST):
        full = os.path.join(FRONTEND_DIST, path)
        if not os.path.isfile(full):
            path = "index.html"
        return send_from_directory(FRONTEND_DIST, path)
    return ("Design app frontend not built. Run `cd design/frontend && npm run dev` "
            "for the dev server, or `npm run build` to build static assets.", 200,
            {"Content-Type": "text/plain"})


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log.info("Design app backend on http://localhost:5050  data: %s", DATA)
    log.info("For the UI: cd design/frontend && npm run dev  ->  http://localhost:5173")
    # Werkzeug's debugger is RCE if reachable — never enable it by default,
    # even on localhost (DNS rebinding can reach 127.0.0.1 from a browser).
    debug = os.environ.get("DESIGN_DEBUG") == "1"
    app.run(host="127.0.0.1", port=5050, debug=debug, use_reloader=debug)


if __name__ == "__main__":
    main()
