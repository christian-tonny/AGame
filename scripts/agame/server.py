"""AGame HTTP server (stdlib): owner sign-in, dashboard + PWA behind auth, entries API,
agent API (imports, check-ins), snapshot upload, rebuilds, and optional Coach chat.

Nothing sensitive is served before authentication: the sign-in page and /healthz carry no
data. Edit endpoints require JSON and a same-origin request; session cookies are HttpOnly,
SameSite=Lax and Secure on HTTPS.
"""

import gzip
import hashlib
import json
import mimetypes
import os
import re
import secrets
import threading
import time
import traceback
import urllib.parse
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from agame import auth
from agame import checkins
from agame import coach_llm
from agame import timeutil as tu
from agame.build import build
from agame.datastore import load_all
from agame.entries import EntryError, Store
from agame.jsonio import atomic_write_many, canonical_dumps
from agame.paths import DATA_FILES

STATIC = {"fitness_dashboard.html", "manifest.webmanifest", "fitness_sw.js"}
REQUIRED_ENV = ["AGAME_OIDC_ISSUER", "AGAME_OIDC_CLIENT_ID", "AGAME_OIDC_CLIENT_SECRET", "AGAME_OWNER_EMAIL", "AGAME_SESSION_SECRET", "AGAME_BASE_URL"]

SIGNIN_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-status-bar-style" content="black">
<meta name="theme-color" content="#1d1e22"><title>AGame · Sign in</title>
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#1d1e22;color:#f4f4f6;font:16px -apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif}
main{text-align:center;padding:24px}.mark{display:block;margin:0 auto 16px}
a{display:inline-block;margin-top:20px;padding:12px 20px;border-radius:12px;background:#f2561a;color:#140700;text-decoration:none;font-weight:700}
p{color:#a3a3ab;max-width:320px}</style></head><body><main>{logo}<h1>AGame</h1>
{msg}<a href="/auth/login">Sign in</a></main></body></html>"""


LOGO_SVG = ('<svg class="mark" width="64" height="64" viewBox="0 0 100 100" aria-hidden="true"><defs><linearGradient id="t" x1="0" y1="0" x2="1" y2="1">'
            '<stop offset="0" stop-color="#ff6b1a"/><stop offset="1" stop-color="#e8430a"/></linearGradient></defs><rect width="100" height="100" rx="23" fill="url(#t)"/>'
            '<path d="M28 78L50 22L72 78" fill="none" stroke="#fff" stroke-width="10" stroke-linecap="round" stroke-linejoin="round"/>'
            '<path d="M17 62H35L41 51L49 72L55 62H83" fill="none" stroke="#fff" stroke-width="6.5" stroke-linecap="round" stroke-linejoin="round"/></svg>')
SIGNIN_HTML = SIGNIN_HTML.replace("{logo}", LOGO_SVG)
AGENT_BLOCKED_ACTIONS = {"privacy.zone_remove"}
INTERNAL_ERROR = {"error": "internal error",
                  "next": "Retry once after a minute; repeating the same request is safe. If it fails again, tell the owner."}
JOBS = {}
GZIP_TYPES = ("text/html", "application/javascript", "text/javascript", "application/json", "application/manifest+json")


class Config:
    def __init__(self, data_dir, dist_dir, dev=False, host="0.0.0.0", port=8080, env=None):
        env = env if env is not None else os.environ
        self.data_dir = Path(data_dir)
        self.dist_dir = Path(dist_dir)
        self.dev = dev
        self.host = "127.0.0.1" if dev else host
        self.port = port
        self.base_url = (env.get("AGAME_BASE_URL") or f"http://127.0.0.1:{port}").rstrip("/")
        self.owner = (env.get("AGAME_OWNER_EMAIL") or "").strip().lower()
        self.upload_token = env.get("AGAME_UPLOAD_TOKEN") or ""
        self.agent_token = env.get("AGAME_AGENT_TOKEN") or ""
        self.secure = self.base_url.startswith("https://")
        missing = [k for k in REQUIRED_ENV if not env.get(k)]
        if not dev and missing:
            raise SystemExit("refusing to start: missing environment variables " + ", ".join(missing) + " (use --dev for local, unauthenticated use on 127.0.0.1)")
        secret = env.get("AGAME_SESSION_SECRET") or ("dev-" + "x" * 40 if dev else "")
        self.signer = auth.Signer(secret)
        self.oidc = None
        if env.get("AGAME_OIDC_ISSUER"):
            self.oidc = auth.OIDC(env["AGAME_OIDC_ISSUER"], env.get("AGAME_OIDC_CLIENT_ID", ""), env.get("AGAME_OIDC_CLIENT_SECRET", ""),
                                  self.base_url + "/auth/callback")
        self.tiles_origin = None


class State:
    def __init__(self, cfg):
        self.cfg = cfg
        self.lock = threading.RLock()
        self._snap = None
        self._snap_key = None

    def today(self):
        fixed = os.environ.get("AGAME_DEV_TODAY") if self.cfg.dev else None  # tests pin the clock; ignored outside --dev
        if fixed:
            return tu.parse_date(fixed)
        data, _, _ = load_all(self.cfg.data_dir)
        tz = tu.tzinfo(((data.get("profile") or {}).get("locale") or {}).get("timezone") or tu.DEFAULT_TZ)
        return datetime.now(tz).date()

    def rebuild(self):
        with self.lock:
            return build(self.cfg.data_dir, self.cfg.dist_dir, self.today())

    def snapshot(self):
        from agame.snapshot import build_snapshot
        key = tuple((f, (self.cfg.data_dir / f).stat().st_mtime if (self.cfg.data_dir / f).exists() else 0) for f in DATA_FILES)
        if self._snap is None or key != self._snap_key:
            data, _, _ = load_all(self.cfg.data_dir)
            self._snap, _ = build_snapshot(data, self.today())
            self._snap_key = key
        return self._snap


_GZ_CACHE = {}


def _gzipped(path, raw):
    """The dashboard is several MB of embedded JSON; gzip cuts it ~4x. Cached per file version."""
    st = path.stat()
    key = (str(path), st.st_mtime_ns, st.st_size)
    hit = _GZ_CACHE.get(str(path))
    if hit and hit[0] == key:
        return hit[1]
    data = gzip.compress(raw, compresslevel=6, mtime=0)
    _GZ_CACHE[str(path)] = (key, data)
    return data


def pinned_snapshot(cfg):
    """Rollback pin: AGAME_PIN_SNAPSHOT=YYYY-MM-DD or a dist/pin.txt file serves that kept snapshot instead of the latest build."""
    pin = (os.environ.get("AGAME_PIN_SNAPSHOT") or "").strip()
    if not pin and (cfg.dist_dir / "pin.txt").exists():
        pin = (cfg.dist_dir / "pin.txt").read_text().strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", pin or "") and (cfg.dist_dir / "snapshots" / f"{pin}.html").is_file():
        return pin
    return None


def make_handler(cfg, state=None):
    state = state or State(cfg)

    class Handler(BaseHTTPRequestHandler):
        server_version = "AGame"
        sys_version = ""

        def log_message(self, fmt, *args):  # no request bodies, no health data in logs
            if os.environ.get("AGAME_QUIET"):
                return
            super().log_message("%s %s", self.command, self.path.split("?")[0])

        # -------------------------------------------------------------- helpers
        def _security_headers(self, api=False):
            img = "'self' data:" + (f" {cfg.tiles_origin}" if cfg.tiles_origin else "")
            self.send_header("Content-Security-Policy", f"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src {img}; connect-src 'self'; manifest-src 'self'; worker-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Permissions-Policy", "geolocation=(), camera=(), microphone=()")
            if cfg.secure:
                self.send_header("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
            if api:
                self.send_header("Cache-Control", "no-store")

        def _send(self, code, body, ctype="application/json", headers=None, api=True):
            b = body if isinstance(body, bytes) else (json.dumps(body).encode() if ctype == "application/json" else body.encode())
            headers = list(headers or [])
            if getattr(self, "_refresh", None) and not any(k == "Set-Cookie" for k, _ in headers):
                headers.append(("Set-Cookie", self._refresh))
            self.send_response(code)
            self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith(("text/", "application/json")) else ""))
            self.send_header("Content-Length", str(len(b)))
            for k, v in (headers or []):
                self.send_header(k, v)
            self._security_headers(api)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(b)

        def _redirect(self, loc, cookies=()):
            self.send_response(302)
            self.send_header("Location", loc)
            for c in cookies:
                self.send_header("Set-Cookie", c)
            self.send_header("Content-Length", "0")
            self._security_headers(True)
            self.end_headers()

        def _user(self):
            if cfg.dev:
                return {"email": cfg.owner or "dev@localhost", "dev": True}
            c = auth.parse_cookies(self.headers.get("Cookie"))
            sess = cfg.signer.verify(c.get(auth.SESSION_COOKIE, ""))
            if not sess or sess.get("email") != cfg.owner:
                return None
            return sess

        def _body(self, limit=25 * 1024 * 1024):
            n = int(self.headers.get("Content-Length") or 0)
            if n > limit:
                raise EntryError(413, "request too large")
            raw = self.rfile.read(n) if n else b""
            if not raw:
                return {}
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                raise EntryError(400, "invalid JSON body")

        def _agent(self):
            """True for a valid AGAME_AGENT_TOKEN, False when no bearer token was sent. A wrong token is refused outright."""
            auth_h = self.headers.get("Authorization") or ""
            if not auth_h.startswith("Bearer "):
                return False
            import hmac as _h
            # compare bytes: compare_digest raises on non-ASCII str, and a pasted mask or placeholder must be a plain 401
            given = auth_h[7:].strip().encode("utf-8", "replace")
            if cfg.agent_token and _h.compare_digest(given, cfg.agent_token.encode("utf-8")):
                return True
            raw = auth_h[7:].strip()
            print(f"agent token refused: length {len(raw)} (expected {len(cfg.agent_token)}), plain ascii {raw.isascii()}, "
                  f"starts with another 'Bearer' {raw.lower().startswith('bearer')}, "
                  f"is the token's start {bool(raw) and cfg.agent_token.startswith(raw)}, is its end {bool(raw) and cfg.agent_token.endswith(raw)}, "
                  f"platform surrogate {raw.startswith('hsurr:')}, fingerprint {hashlib.sha256(raw.encode('utf-8', 'replace')).hexdigest()[:8]}",
                  flush=True)  # shape only, never the value
            raise EntryError(401, "invalid agent token: send the AGAME_AGENT_TOKEN value itself as Authorization: Bearer <token>")

        def _same_origin_json(self):
            if (self.headers.get("Content-Type") or "").split(";")[0].strip() != "application/json":
                raise EntryError(415, "JSON body required")
            origin = self.headers.get("Origin")
            if origin and not cfg.dev and origin.rstrip("/") != cfg.base_url:
                raise EntryError(403, "cross-origin request refused")

        def _deny(self, api):
            if api:
                return self._send(401, {"error": "sign-in required"})
            return self._redirect("/auth/signin")

        # -------------------------------------------------------------- routing
        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            self._guarded(self._get)

        def _guarded(self, fn, *args):
            """Last line of defence: an agent can only act on a status code, so no request may end without one."""
            try:
                fn(*args)
            except Exception:
                traceback.print_exc()
                try:
                    self._send(500, INTERNAL_ERROR)
                except Exception:
                    pass

        def _get(self):
            self._refresh = None
            path = urllib.parse.urlparse(self.path).path
            q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(self.path).query))
            if path == "/healthz":
                return self._send(200, {"ok": True})
            if path == "/auth/signin":
                msg = '<p style="color:#ff453a">' + {"denied": "That account is not allowed.", "error": "Sign-in failed. Try again."}.get(q.get("e"), "") + "</p>" if q.get("e") else ""
                return self._send(200, SIGNIN_HTML.replace("{msg}", msg), "text/html", api=True)
            if path == "/auth/login":
                if not cfg.oidc:
                    return self._send(503, "Sign-in is not configured", "text/plain")
                url, flow = cfg.oidc.start(cfg.signer)
                return self._redirect(url, [auth.cookie_header(auth.FLOW_COOKIE, flow, auth.FLOW_TTL, cfg.secure, "/auth")])
            if path == "/auth/callback":
                return self._callback(q)
            if path == "/auth/logout":
                return self._logout()
            api = path.startswith("/api/")
            if path.startswith("/api/agent/"):
                try:
                    if not self._agent() and not self._user():
                        return self._send(401, {"error": "agent token required (Authorization: Bearer <AGAME_AGENT_TOKEN>)"})
                    return self._agent_get(path, q)
                except EntryError as e:
                    return self._send(e.status, {"error": e.message, "details": e.details})
                except Exception:  # never drop the connection on an agent read
                    traceback.print_exc()
                    return self._send(500, INTERNAL_ERROR)
            user = self._user()
            if not user:
                return self._deny(api)
            refresh = self._refresh = self._maybe_rotate(user)
            if path in ("/", "/index.html"):
                return self._redirect("/fitness_dashboard.html")
            if path.lstrip("/") in STATIC or re.fullmatch(r"/icons/[a-z0-9\-]+\.png", path):
                return self._static(path.lstrip("/"), refresh)
            if path.startswith("/records/"):
                return self._record_file(path[len("/records/"):])
            try:
                if path == "/api/ping":
                    return self._send(200, {"ok": True, "llm": coach_llm.enabled(), "dev": bool(cfg.dev)})
                if path == "/api/history":
                    return self._send(200, {"items": Store(cfg.data_dir).history(int(q.get("limit", 50)))})
                if path == "/api/export":
                    data = Store(cfg.data_dir).export()
                    return self._send(200, json.dumps(data, indent=1).encode(), "application/json",
                                      headers=[("Content-Disposition", "attachment; filename=agame-export.json")])
                if path == "/api/build-report":
                    p = cfg.dist_dir / "build_report.json"
                    rep = json.loads(p.read_text()) if p.exists() else {"status": "missing"}
                    rep["pinned_snapshot"] = pinned_snapshot(cfg)
                    return self._send(200, rep)
            except EntryError as e:
                return self._send(e.status, {"error": e.message, "details": e.details})
            except Exception:
                traceback.print_exc()
                return self._send(500, INTERNAL_ERROR)
            return self._send(404, {"error": "not found"}) if api else self._send(404, "Not found", "text/plain")

        def do_POST(self):
            self._guarded(self._mutate, "POST")

        def do_PATCH(self):
            self._guarded(self._mutate, "PATCH")

        def do_DELETE(self):
            self._guarded(self._mutate, "DELETE")

        def _mutate(self, method):
            self._refresh = None
            path = urllib.parse.urlparse(self.path).path
            if path == "/api/snapshot" and method == "POST":
                return self._upload()
            if path == "/auth/logout":
                return self._logout()
            if not path.startswith("/api/"):
                return self._send(405, {"error": "method not allowed"})
            try:
                agent = self._agent()
            except EntryError as e:
                return self._send(e.status, {"error": e.message})
            user = None if agent else self._user()
            if not agent and not user:
                return self._send(401, {"error": "sign-in required"})
            if user:
                self._refresh = self._maybe_rotate(user)
            try:
                if agent:
                    self._agent_allowed(path, method)
                if path == "/api/import/apple-health-export" and method == "POST":
                    return self._export_upload()
                if method != "DELETE":
                    self._same_origin_json()
                if path == "/api/import" and method == "POST":
                    return self._import(self._body(limit=50 * 1024 * 1024))
                body = self._body() if method != "DELETE" else {}
                key = (self.headers.get("Idempotency-Key") or "").strip()[:200] or None
                store = Store(cfg.data_dir, actor="agent" if agent else "owner", idempotency_key=key if agent else None)
                if agent and key:
                    prev = store.replay(key)
                    if prev:
                        return self._send(200, {"ok": True, "duplicate": True, "record": prev.get("after"), "build": "unchanged"})
                m = re.fullmatch(r"/api/entries/([a-z_]+\.[a-z_]+)(?:/([^/]+))?", path)
                if m:
                    col, rid = m.group(1), urllib.parse.unquote(m.group(2)) if m.group(2) else None
                    if method == "POST" and not rid:
                        rec = store.create(col, body)
                    elif method == "PATCH" and rid:
                        rec = store.update(col, rid, body)
                    elif method == "DELETE" and rid:
                        rec = store.delete(col, rid)
                    else:
                        raise EntryError(405, "method not allowed for this path")
                    rep = state.rebuild()
                    return self._send(200, {"ok": True, "record": rec, "build": rep["status"]})
                m = re.fullmatch(r"/api/actions/([a-z_]+\.[a-z_]+)", path)
                if m and method == "POST":
                    from agame import actions
                    rec = actions.run(m.group(1), store, state.snapshot(), cfg.data_dir, body)
                    rep = state.rebuild()
                    return self._send(200, {"ok": True, "result": rec, "build": rep["status"]})
                if path == "/api/profile" and method == "PATCH":
                    prof = store.patch_profile(body)
                    rep = state.rebuild()
                    return self._send(200, {"ok": True, "profile": prof, "build": rep["status"]})
                if path == "/api/undo" and method == "POST":
                    h = store.undo()
                    rep = state.rebuild()
                    return self._send(200, {"ok": True, "undone": h, "build": rep["status"]})
                if path == "/api/rebuild" and method == "POST":
                    rep = state.rebuild()
                    return self._send(200 if rep["status"] != "failed" else 500, rep)
                if path == "/api/delete-all" and method == "POST":
                    n = store.delete_all_user_entered(body.get("confirm"))
                    rep = state.rebuild()
                    return self._send(200, {"ok": True, "deleted": n, "build": rep["status"]})
                if path == "/api/coach/ask" and method == "POST":
                    return self._coach(body, store)
            except EntryError as e:
                return self._send(e.status, {"error": e.message, "details": e.details})
            except Exception:  # an agent can only act on a status code, so never drop the connection
                traceback.print_exc()
                return self._send(500, INTERNAL_ERROR)
            return self._send(404, {"error": "not found"})

        # -------------------------------------------------------------- agent
        def _agent_allowed(self, path, method):
            """The agent logs and plans; it never deletes, undoes or changes settings. docs/agents.md lists the same rules."""
            if method == "DELETE":
                raise EntryError(403, "agents never delete; ask the owner to delete it in the app")
            if path in ("/api/import", "/api/import/apple-health-export"):
                return
            if path.startswith("/api/entries/") and method in ("POST", "PATCH"):
                return
            m = re.fullmatch(r"/api/actions/([a-z_]+\.[a-z_]+)", path)
            if m and method == "POST" and m.group(1) not in AGENT_BLOCKED_ACTIONS:
                return
            raise EntryError(403, "the agent token cannot use this endpoint")

        def _read_dist(self, name):
            p = cfg.dist_dir / name
            return json.loads(p.read_text()) if p.exists() else None

        def _checkins(self, q):
            data, _, _ = load_all(cfg.data_dir)
            tz = tu.tzinfo(((data.get("profile") or {}).get("locale") or {}).get("timezone") or tu.DEFAULT_TZ)
            try:
                now = tu.parse_ts(q["now"]).astimezone(tz) if q.get("now") else datetime.now(tz).replace(microsecond=0)
            except ValueError:
                raise EntryError(400, "now must be an ISO time with an offset, for example 2026-10-05T06:15:00+02:00")
            try:
                window = max(1, min(1440, int(q.get("window_min", 15))))
            except ValueError:
                raise EntryError(400, "window_min must be a number of minutes")
            out = checkins.report(data["coach"].get("checkins", []), now, window, cfg.dist_dir)
            out["timezone"] = str(tz)
            return out

        def _agent_get(self, path, q):
            names = {"/api/agent/morning-summary": "morning_summary.json", "/api/agent/build-report": "build_report.json",
                     "/api/agent/weekly-review": "weekly_review.json"}
            if path in names:
                body = self._read_dist(names[path])
                if body is None:
                    return self._send(404, {"error": "not built yet; POST /api/import first"})
                if path == "/api/agent/build-report":
                    body["pinned_snapshot"] = pinned_snapshot(cfg)
                return self._send(200, body)
            if path == "/api/agent/checkins":
                return self._send(200, self._checkins(q))
            if path == "/api/agent/job":
                job = JOBS.get(q.get("id", ""))
                return self._send(200, job) if job else self._send(404, {"error": "unknown job"})
            return self._send(404, {"error": "not found"})

        def _import(self, body):
            """One HealthKit batch (or Muse's muse.v1 results) -> importer -> rebuild, answered in one response."""
            from agame.importer import BatchError, apply_batch
            if any(j["status"] == "running" for j in JOBS.values()):
                return self._send(409, {"status": "busy", "error": "an Apple Health export import is running; try again in 10 minutes"})
            with state.lock:
                try:
                    summary, code = apply_batch(cfg.data_dir, body, lenient=True)
                except BatchError as e:
                    return self._send(400, {"status": "rejected", "exit_code": 1, "error": str(e),
                                            "next": "Fix the batch envelope and re-import. Nothing was written."})
                if code == 1:
                    return self._send(422, {"status": "rejected", "exit_code": 1, "import": summary, "rejected": summary.get("rejected", []),
                                            "errors": summary.get("errors", []), "next": "Nothing was written. Fix the batch and re-import."})
                rep = state.rebuild()
            q = {}
            out = {
                "status": summary["status"], "exit_code": 2 if (code == 2 or rep["status"] == "degraded") else 0,
                "import": {k: summary[k] for k in ("idempotency_key", "date", "status", "added", "updated", "skipped_duplicate", "duplicates", "conflicts", "stale", "domains_touched") if k in summary},
                "rejected": summary.get("rejected", []), "ignored_fields": (summary.get("adapter") or {}).get("ignored_fields", []),
                "build_report": {k: rep.get(k) for k in ("status", "exit_code", "build_date", "degraded_reasons", "errors", "next", "freshness")},
                "morning_summary": self._read_dist("morning_summary.json") if rep["status"] != "failed" else None,
                "checkins": self._checkins(q),
            }
            if rep["status"] == "failed":
                out["exit_code"] = 1
                return self._send(500, out)
            return self._send(200, out)

        def _export_upload(self):
            """Apple Health export.zip as the raw request body. Saved to the volume, imported in the background."""
            origin = self.headers.get("Origin")
            if origin and not cfg.dev and origin.rstrip("/") != cfg.base_url:
                raise EntryError(403, "cross-origin request refused")
            n = int(self.headers.get("Content-Length") or 0)
            if n <= 0:
                raise EntryError(400, "send the export.zip file as the request body")
            if n > EXPORT_MAX_BYTES:
                raise EntryError(413, f"export larger than {EXPORT_MAX_BYTES // (1024 * 1024)} MB")
            if any(j["status"] == "running" for j in JOBS.values()):
                raise EntryError(409, "an export import is already running")
            up = cfg.data_dir / ".uploads"
            up.mkdir(exist_ok=True)
            job_id = secrets.token_hex(6)
            path = up / f"export-{job_id}.zip"
            left = n
            with open(path, "wb") as fh:
                while left > 0:
                    chunk = self.rfile.read(min(1 << 20, left))
                    if not chunk:
                        break
                    fh.write(chunk)
                    left -= len(chunk)
            if left:
                path.unlink(missing_ok=True)
                raise EntryError(400, "upload ended early")
            JOBS[job_id] = {"id": job_id, "status": "running", "step": "reading export.xml", "started_at": datetime.now().astimezone().isoformat()}
            threading.Thread(target=_run_export_job, args=(job_id, path, cfg, state), daemon=True).start()
            return self._send(202, {"job": job_id, "status": "running", "status_url": f"/api/agent/job?id={job_id}"})

        # -------------------------------------------------------------- endpoints
        def _static(self, rel, refresh):
            pin = pinned_snapshot(cfg)
            if rel == "fitness_dashboard.html" and pin:
                rel = f"snapshots/{pin}.html"
            p = (cfg.dist_dir / rel).resolve()
            if cfg.dist_dir.resolve() not in p.parents or not p.is_file():
                return self._send(404, "Dashboard not built yet. Run build_dashboard.py.", "text/plain", api=True)
            ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
            if p.name.endswith(".webmanifest"):
                ctype = "application/manifest+json"
            hdrs = [("Cache-Control", "no-cache"), ("Vary", "Accept-Encoding")]
            if p.name == "fitness_sw.js":
                hdrs.append(("Service-Worker-Allowed", "/"))
            if refresh:
                hdrs.append(("Set-Cookie", refresh))
            body = p.read_bytes()
            if ctype in GZIP_TYPES and "gzip" in (self.headers.get("Accept-Encoding") or ""):
                body = _gzipped(p, body)
                hdrs.append(("Content-Encoding", "gzip"))
            return self._send(200, body, ctype, headers=hdrs, api=False)

        def _record_file(self, name):
            if not re.fullmatch(r"[A-Za-z0-9._\-]+", name):
                return self._send(404, {"error": "not found"})
            data, _, _ = load_all(cfg.data_dir)
            allowed = {r.get("file") for r in (data.get("health_records") or {}).get("records", []) if r.get("file")}
            p = cfg.data_dir / "records" / name
            if name not in allowed or not p.is_file():
                return self._send(404, {"error": "not found"})
            return self._send(200, p.read_bytes(), mimetypes.guess_type(name)[0] or "application/octet-stream",
                              headers=[("Content-Disposition", f"attachment; filename={name}")])

        def _callback(self, q):
            if not cfg.oidc:
                return self._send(503, "Sign-in is not configured", "text/plain")
            c = auth.parse_cookies(self.headers.get("Cookie"))
            clear = auth.cookie_header(auth.FLOW_COOKIE, "", 0, cfg.secure, "/auth")
            try:
                email, verified = cfg.oidc.finish(cfg.signer, c.get(auth.FLOW_COOKIE), q.get("code"), q.get("state"))
            except Exception:
                return self._redirect("/auth/signin?e=error", [clear])
            if not verified or email != cfg.owner:
                return self._redirect("/auth/signin?e=denied", [clear])
            sess = auth.new_session(cfg.signer, email)
            return self._redirect("/fitness_dashboard.html", [clear, auth.cookie_header(auth.SESSION_COOKIE, sess, auth.SESSION_TTL, cfg.secure)])

        def _logout(self):
            return self._redirect("/auth/signin", [auth.cookie_header(auth.SESSION_COOKIE, "", 0, cfg.secure)])

        def _maybe_rotate(self, user):
            if user.get("dev") or not user.get("iat"):
                return None
            if time.time() - user["iat"] >= auth.ROTATE_AFTER:
                return auth.cookie_header(auth.SESSION_COOKIE, auth.new_session(cfg.signer, user["email"]), auth.SESSION_TTL, cfg.secure)
            return None

        def _upload(self):
            tok = (self.headers.get("Authorization") or "").removeprefix("Bearer ").strip()
            import hmac as _h
            if not cfg.upload_token or not _h.compare_digest(tok, cfg.upload_token):
                return self._send(401, {"error": "invalid upload token"})
            try:
                body = self._body(limit=200 * 1024 * 1024)
                files = body.get("files") or {}
                bad = [f for f in files if f not in DATA_FILES]
                if bad or not files:
                    raise EntryError(400, "files must be a non-empty map of known data files", bad)
                from agame.validate import validate_data
                import tempfile
                import shutil
                with tempfile.TemporaryDirectory() as tmp:
                    for f in DATA_FILES:
                        src = cfg.data_dir / f
                        if src.exists():
                            shutil.copy(src, Path(tmp) / f)
                    for f, content in files.items():
                        (Path(tmp) / f).write_text(content if isinstance(content, str) else canonical_dumps(content, ndigits=6), encoding="utf-8")
                    rep, _ = validate_data(tmp, state.today())
                    if not rep.ok:
                        raise EntryError(400, "uploaded data invalid", rep.errors[:30])
                pairs = [(cfg.data_dir / f, content if isinstance(content, str) else canonical_dumps(content, ndigits=6)) for f, content in files.items()]
                atomic_write_many(pairs)
                report = state.rebuild()
                return self._send(200 if report["status"] != "failed" else 500, {"ok": report["status"] != "failed", "build": report})
            except EntryError as e:
                return self._send(e.status, {"error": e.message, "details": e.details})

        def _coach(self, body, store):
            q = (body.get("q") or "").strip()
            if not q:
                raise EntryError(400, "question required")
            if not coach_llm.enabled():
                raise EntryError(503, "Coach chat not connected (set AGAME_LLM_PROVIDER=anthropic and install the anthropic package)")
            snap = state.snapshot()
            include = bool(((snap.get("profile") or {}).get("coach") or {}).get("include_health_records"))
            try:
                res = coach_llm.ask(q, snap, body.get("mode", "adaptive"), body.get("personality", "data_nerd"), body.get("activity_id"), include)
            except Exception as exc:
                raise EntryError(502, f"coach provider error: {type(exc).__name__}")
            if not body.get("ghost"):
                now = datetime.now().astimezone().replace(microsecond=0).isoformat()
                if res.get("chart"):
                    store.create("coach.memory", {"type": "artifact", "text": f"Chart: {q[:300]}", "spec": res["chart"]})
                self._append_thread(q, res, now, body.get("activity_id"))
            return self._send(200, res)

        def _append_thread(self, q, res, now, activity_id):
            data, _, _ = load_all(cfg.data_dir)
            threads = data["coach"].setdefault("threads", [])
            tid = f"thread-{now[:10]}" + (f"-{activity_id}" if activity_id else "")
            t = next((x for x in threads if x["id"] == tid), None)
            if not t:
                t = {"id": tid, "title": None, "created_at": now, "activity_id": activity_id, "messages": []}
                threads.append(t)
            t["messages"] += [{"role": "user", "text": q, "t": now}, {"role": "coach", "text": res["text"], "t": now, "citations": res.get("citations") or [], "chart": res.get("chart")}]
            data["coach"]["threads"] = threads[-50:]
            from agame.jsonio import atomic_write_text
            atomic_write_text(cfg.data_dir / "coach.json", canonical_dumps(data["coach"], ndigits=6, indent=1) + "\n")

    return Handler


EXPORT_MAX_BYTES = 4 * 1024 * 1024 * 1024


def _run_export_job(job_id, path, cfg, state):
    from agame.apple_export import ExportError, run
    from agame.importer import BatchError
    job = JOBS[job_id]
    try:
        with state.lock:
            summary, code = run(path, cfg.data_dir, progress=lambda m: job.update(step=m))
            job["step"] = "rebuilding"
            rep = state.rebuild() if code != 1 else None
        job.update(status="done" if code != 1 else "rejected", exit_code=code, import_status=summary["status"],
                   added=summary.get("added"), updated=summary.get("updated"), rejected=summary.get("rejected", [])[:200],
                   export=summary.get("export"), build=rep and {k: rep.get(k) for k in ("status", "degraded_reasons", "errors", "next")})
    except (ExportError, BatchError, OSError, ValueError) as exc:
        job.update(status="failed", error=str(exc))
    finally:
        job["finished_at"] = datetime.now().astimezone().isoformat()
        try:
            Path(path).unlink()
        except OSError:
            pass


def serve(cfg):
    if cfg.dev:
        print("=" * 64 + "\n  AGame DEV MODE: no sign-in, bound to 127.0.0.1 only.\n  Never expose this mode to a network.\n" + "=" * 64, flush=True)
    state = State(cfg)
    if not (cfg.dist_dir / "fitness_dashboard.html").exists():
        rep = state.rebuild()
        print(f"initial build: {rep['status']}", flush=True)
    httpd = ThreadingHTTPServer((cfg.host, cfg.port), make_handler(cfg, state))
    print(f"AGame serving on http://{cfg.host}:{cfg.port}  data={cfg.data_dir}  dist={cfg.dist_dir}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
