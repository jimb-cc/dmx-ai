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

from flask import Flask, abort, jsonify, request, send_from_directory

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

import ofl  # noqa: E402
import qlcplus  # noqa: E402
from shared.profile import FIXTURE_TYPES, FUNCTIONS, Profile, ProfileRegistry, validate  # noqa: E402
from shared.rig import Rig, save as save_rig  # noqa: E402

DATA = os.path.join(_root, "data")
PROFILES_DIR = os.path.join(DATA, "profiles")
RIGS_DIR = os.path.join(DATA, "rigs")
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
