"""HTTP server: nothing sensitive before sign-in, OIDC flow against a fake provider, sessions, edits, uploads."""

import base64
import http.client
import io
import json
import threading
import unittest
import urllib.parse
from contextlib import contextmanager
from http.server import ThreadingHTTPServer

from helpers import empty_dir, synthetic_dir

from agame import auth
from agame.build import build
from agame.server import Config, State, make_handler
from helpers import BUILD_DATE

ISS = "https://idp.test"
OWNER = "owner@example.com"
SECRET = "s" * 40
TOKEN = "upload-token-for-tests"
AGENT = "agent-token-for-tests"


def _jwt(claims):
    enc = lambda o: base64.urlsafe_b64encode(json.dumps(o).encode()).rstrip(b"=").decode()
    return f"{enc({'alg': 'RS256'})}.{enc(claims)}.sig"


class FakeIdP:
    """Stands in for Google: discovery, token and userinfo endpoints."""

    def __init__(self):
        self.email, self.verified, self.nonce, self.aud = OWNER, True, None, "client-id"

    def __call__(self, req, timeout=None):
        url = req if isinstance(req, str) else req.full_url
        if url.endswith("/.well-known/openid-configuration"):
            body = {"issuer": ISS, "authorization_endpoint": ISS + "/auth", "token_endpoint": ISS + "/token", "userinfo_endpoint": ISS + "/userinfo"}
        elif url == ISS + "/token":
            body = {"access_token": "at", "id_token": _jwt({"iss": ISS, "aud": self.aud, "nonce": self.nonce, "email": self.email, "email_verified": self.verified, "exp": 4102444800})}
        elif url == ISS + "/userinfo":
            body = {"email": self.email, "email_verified": self.verified}
        else:
            raise AssertionError("unexpected URL " + url)

        @contextmanager
        def resp():
            yield io.BytesIO(json.dumps(body).encode())
        return resp()


class ServerCase(unittest.TestCase):
    data_source = staticmethod(empty_dir)

    @classmethod
    def setUpClass(cls):
        cls.data = cls.data_source()
        cls.dist = cls.data / "dist"
        build(cls.data, cls.dist, BUILD_DATE)
        env = {"AGAME_OIDC_ISSUER": ISS, "AGAME_OIDC_CLIENT_ID": "client-id", "AGAME_OIDC_CLIENT_SECRET": "x", "AGAME_OWNER_EMAIL": OWNER,
               "AGAME_SESSION_SECRET": SECRET, "AGAME_BASE_URL": "http://127.0.0.1", "AGAME_UPLOAD_TOKEN": TOKEN, "AGAME_AGENT_TOKEN": AGENT}
        cls.cfg = Config(cls.data, cls.dist, dev=False, host="127.0.0.1", port=0, env=env)
        cls.idp = FakeIdP()
        cls.cfg.oidc._open = cls.idp
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.cfg, State(cls.cfg)))
        cls.port = cls.httpd.server_address[1]
        cls.cfg.base_url = f"http://127.0.0.1:{cls.port}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def req(self, method, path, body=None, headers=None, cookie=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        h = dict(headers or {})
        if cookie:
            h["Cookie"] = cookie
        data = None
        if body is not None:
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            h.setdefault("Content-Type", "application/json")
        c.request(method, path, body=data, headers=h)
        r = c.getresponse()
        raw = r.read()
        c.close()
        try:
            parsed = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            parsed = raw.decode(errors="replace")
        return r.status, dict(r.getheaders()), parsed, r.headers.get_all("Set-Cookie") or []

    def session_cookie(self, email=OWNER):
        return f"{auth.SESSION_COOKIE}={auth.new_session(self.cfg.signer, email)}"


class Unauthenticated(ServerCase):
    def test_health_has_no_data(self):
        st, _, body, _ = self.req("GET", "/healthz")
        self.assertEqual((st, body), (200, {"ok": True}))

    def test_dashboard_redirects_to_signin(self):
        for path in ("/", "/fitness_dashboard.html", "/manifest.webmanifest", "/fitness_sw.js", "/icons/icon-192.png", "/records/x.pdf"):
            st, h, _, _ = self.req("GET", path)
            self.assertEqual((st, h.get("Location")), (302, "/auth/signin"), path)

    def test_api_is_401(self):
        for method, path in (("GET", "/api/ping"), ("GET", "/api/export"), ("GET", "/api/history"), ("POST", "/api/undo"),
                             ("POST", "/api/entries/journal.entries"), ("PATCH", "/api/profile"), ("POST", "/api/coach/ask")):
            st, _, _, _ = self.req(method, path, body={} if method != "GET" else None)
            self.assertEqual(st, 401, path)

    def test_signin_page_has_no_data_and_security_headers(self):
        st, h, body, _ = self.req("GET", "/auth/signin")
        self.assertEqual(st, 200)
        self.assertNotIn("agame-data", body)
        self.assertIn("frame-ancestors 'none'", h["Content-Security-Policy"])
        self.assertEqual(h["X-Content-Type-Options"], "nosniff")

    def test_tampered_and_foreign_sessions_rejected(self):
        good = auth.new_session(self.cfg.signer, OWNER)
        body, mac = good.split(".")
        forged = base64.urlsafe_b64encode(json.dumps({"email": OWNER, "iat": 1, "exp": 4102444800}).encode()).rstrip(b"=").decode()
        for cookie in (f"{auth.SESSION_COOKIE}={forged}.{mac}", f"{auth.SESSION_COOKIE}={body}.AAAA", self.session_cookie("someone@else.com"),
                       f"{auth.SESSION_COOKIE}={auth.Signer('z' * 40).sign({'email': OWNER, 'iat': 1, 'exp': 4102444800})}"):
            st, _, _, _ = self.req("GET", "/api/ping", cookie=cookie)
            self.assertEqual(st, 401, cookie)

    def test_expired_session_rejected(self):
        tok = self.cfg.signer.sign({"email": OWNER, "iat": 1, "exp": 2})
        st, _, _, _ = self.req("GET", "/api/ping", cookie=f"{auth.SESSION_COOKIE}={tok}")
        self.assertEqual(st, 401)

    def test_refuses_to_start_without_env(self):
        with self.assertRaises(SystemExit):
            Config(self.data, self.dist, dev=False, env={})


class SignIn(ServerCase):
    def login(self, email=OWNER, verified=True, tamper_state=False):
        st, h, _, cookies = self.req("GET", "/auth/login")
        self.assertEqual(st, 302)
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(h["Location"]).query))
        self.assertEqual((q["code_challenge_method"], q["client_id"]), ("S256", "client-id"))
        flow = cookies[0].split(";")[0]
        self.idp.email, self.idp.verified, self.idp.nonce = email, verified, q["nonce"]
        state = "wrong" if tamper_state else q["state"]
        return self.req("GET", f"/auth/callback?code=abc&state={state}", cookie=flow)

    def test_owner_gets_session(self):
        st, h, _, cookies = self.login()
        self.assertEqual((st, h["Location"]), (302, "/fitness_dashboard.html"))
        sess = next(c for c in cookies if c.startswith(auth.SESSION_COOKIE + "=") and "Max-Age=0" not in c)
        self.assertIn("HttpOnly", sess)
        self.assertIn("SameSite=Lax", sess)
        st, _, body, _ = self.req("GET", "/fitness_dashboard.html", cookie=sess.split(";")[0])
        self.assertEqual(st, 200)
        self.assertIn("agame-data", body)

    def test_wrong_email_denied(self):
        st, h, _, cookies = self.login(email="intruder@example.com")
        self.assertEqual(h["Location"], "/auth/signin?e=denied")
        self.assertFalse(any(c.startswith(auth.SESSION_COOKIE + "=") for c in cookies))

    def test_unverified_email_denied(self):
        _, h, _, _ = self.login(verified=False)
        self.assertEqual(h["Location"], "/auth/signin?e=denied")

    def test_state_mismatch_is_error(self):
        _, h, _, _ = self.login(tamper_state=True)
        self.assertEqual(h["Location"], "/auth/signin?e=error")

    def test_nonce_mismatch_is_error(self):
        st, h, _, cookies = self.req("GET", "/auth/login")
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(h["Location"]).query))
        self.idp.email, self.idp.verified, self.idp.nonce = OWNER, True, "replayed"
        _, h, _, _ = self.req("GET", f"/auth/callback?code=abc&state={q['state']}", cookie=cookies[0].split(";")[0])
        self.assertEqual(h["Location"], "/auth/signin?e=error")

    def test_wrong_audience_is_error(self):
        self.idp.aud = "another-app"
        try:
            _, h, _, _ = self.login()
        finally:
            self.idp.aud = "client-id"
        self.assertEqual(h["Location"], "/auth/signin?e=error")

    def test_logout_clears_cookie(self):
        _, h, _, cookies = self.req("GET", "/auth/logout", cookie=self.session_cookie())
        self.assertEqual(h["Location"], "/auth/signin")
        self.assertTrue(any("Max-Age=0" in c for c in cookies))


class Edits(ServerCase):
    def test_entry_lifecycle_and_undo(self):
        ck = self.session_cookie()
        st, _, body, _ = self.req("POST", "/api/entries/journal.entries", {"date": "2026-10-04", "type": "mood", "value": 3}, cookie=ck)
        self.assertEqual(st, 200, body)
        rid = body["record"]["id"]
        st, _, body, _ = self.req("PATCH", f"/api/entries/journal.entries/{rid}", {"value": 5}, cookie=ck)
        self.assertEqual((st, body["record"]["value"]), (200, 5))
        st, _, body, _ = self.req("GET", "/api/history", cookie=ck)
        self.assertEqual(body["items"][0]["before"]["value"], 3)
        st, _, body, _ = self.req("POST", "/api/undo", {}, cookie=ck)
        self.assertEqual(body["undone"]["after"]["value"], 3)
        st, h, body, _ = self.req("GET", "/api/export", cookie=ck)
        self.assertIn("attachment", h["Content-Disposition"])
        self.assertEqual(body["collections"]["journal.entries"][0]["value"], 3)
        st, _, _, _ = self.req("DELETE", f"/api/entries/journal.entries/{rid}", cookie=ck)
        self.assertEqual(st, 200)

    def test_json_and_same_origin_required(self):
        ck = self.session_cookie()
        st, _, _, _ = self.req("POST", "/api/entries/journal.entries", b"date=2026-10-04", headers={"Content-Type": "application/x-www-form-urlencoded"}, cookie=ck)
        self.assertEqual(st, 415)
        st, _, _, _ = self.req("POST", "/api/entries/journal.entries", {"date": "2026-10-04", "type": "mood"}, headers={"Origin": "https://evil.example"}, cookie=ck)
        self.assertEqual(st, 403)

    def test_validation_error_is_400(self):
        st, _, body, _ = self.req("POST", "/api/entries/journal.entries", {"date": "nope", "type": "mood"}, cookie=self.session_cookie())
        self.assertEqual(st, 400)
        self.assertTrue(body["details"])

    def test_coach_without_llm_is_503(self):
        st, _, _, _ = self.req("POST", "/api/coach/ask", {"q": "How am I doing?"}, cookie=self.session_cookie())
        self.assertEqual(st, 503)

    def test_api_responses_are_not_cached(self):
        _, h, _, _ = self.req("GET", "/api/ping", cookie=self.session_cookie())
        self.assertEqual(h["Cache-Control"], "no-store")


class Upload(ServerCase):
    def test_requires_token(self):
        for hdr in ({}, {"Authorization": "Bearer nope"}):
            st, _, _, _ = self.req("POST", "/api/snapshot", {"files": {}}, headers=hdr)
            self.assertEqual(st, 401)

    def test_invalid_upload_changes_nothing(self):
        before = (self.data / "sleep.json").read_bytes()
        bad = json.loads(before)
        bad["nights"] = [{"source_id": "x", "start": "2026-10-04T05:00:00+02:00", "end": "2026-10-03T22:00:00+02:00", "segments": []}]
        st, _, body, _ = self.req("POST", "/api/snapshot", {"files": {"sleep.json": json.dumps(bad)}}, headers={"Authorization": f"Bearer {TOKEN}"})
        self.assertEqual(st, 400, body)
        self.assertEqual((self.data / "sleep.json").read_bytes(), before)
        st, _, _, _ = self.req("POST", "/api/snapshot", {"files": {"../etc/passwd": "x"}}, headers={"Authorization": f"Bearer {TOKEN}"})
        self.assertEqual(st, 400)

    def test_valid_upload_rebuilds(self):
        files = {f: (synthetic_dir() / f).read_text() for f in ("profile.json", "body.json")}
        st, _, body, _ = self.req("POST", "/api/snapshot", {"files": files}, headers={"Authorization": f"Bearer {TOKEN}"})
        self.assertEqual(st, 200, body)
        self.assertIn(body["build"]["status"], ("ok", "degraded"))
        self.assertEqual(json.loads((self.data / "body.json").read_text())["fixture"], "synthetic")



class Agent(ServerCase):
    def bearer(self, token=AGENT, **extra):
        return dict({"Authorization": f"Bearer {token}"}, **extra)

    def muse(self):
        from test_muse import envelope
        return envelope()

    def test_agent_runs_a_morning_over_http(self):
        st, _, body, _ = self.req("POST", "/api/import", self.muse(), headers=self.bearer())
        self.assertEqual(st, 200, body)
        self.assertEqual(body["import"]["added"]["sleep"], 1)
        self.assertEqual(body["rejected"], [])
        self.assertIn(body["build_report"]["status"], ("ok", "degraded"))
        self.assertEqual(body["morning_summary"]["contract"], "agame.morning_summary.v2")
        self.assertTrue(body["morning_summary"]["message"])
        self.assertIn("schedule", body["checkins"])
        for path in ("/api/agent/morning-summary", "/api/agent/build-report", "/api/agent/weekly-review", "/api/agent/checkins"):
            st, _, b, _ = self.req("GET", path, headers=self.bearer())
            self.assertEqual(st, 200, (path, b))
        st, _, body, _ = self.req("POST", "/api/import", self.muse(), headers=self.bearer())
        self.assertEqual(body["import"]["status"], "already_imported")

    def test_agent_logs_are_marked_and_retries_are_not_doubled(self):
        coffee = {"t": "2026-10-04T08:00:00+02:00", "mg": 95}
        st, _, body, _ = self.req("POST", "/api/entries/nutrition.caffeine", coffee, headers=self.bearer(**{"Idempotency-Key": "coffee-1"}))
        self.assertEqual(st, 200, body)
        st, _, again, _ = self.req("POST", "/api/entries/nutrition.caffeine", coffee, headers=self.bearer(**{"Idempotency-Key": "coffee-1"}))
        self.assertTrue(again["duplicate"])
        caffeine = json.loads((self.data / "nutrition.json").read_text())["caffeine"]
        self.assertEqual(len([c for c in caffeine if c.get("kind") == "user_entered"]), 1)
        hist = [json.loads(x) for x in (self.data / "edit_history.jsonl").read_text().splitlines()]
        mine = [h for h in hist if h.get("idempotency_key") == "coffee-1"]
        self.assertEqual([(h["actor"], h["source"]) for h in mine], [("agent", "agent")])

    def test_agent_never_deletes_or_changes_settings(self):
        st, _, _, _ = self.req("DELETE", "/api/entries/journal.entries/x", headers=self.bearer())
        self.assertEqual(st, 403)
        for path in ("/api/undo", "/api/delete-all", "/api/actions/privacy.zone_remove"):
            st, _, _, _ = self.req("POST", path, {}, headers=self.bearer())
            self.assertEqual(st, 403, path)
        st, _, _, _ = self.req("PATCH", "/api/profile", {"display_name": "x"}, headers=self.bearer())
        self.assertEqual(st, 403)

    def test_wrong_or_missing_token(self):
        st, _, _, _ = self.req("GET", "/api/agent/morning-summary")
        self.assertEqual(st, 401)
        st, _, _, _ = self.req("POST", "/api/import", self.muse(), headers=self.bearer("nope"))
        self.assertEqual(st, 401)
        st, _, _, _ = self.req("POST", "/api/import", {"format": "muse.v1"}, headers=self.bearer())
        self.assertEqual(st, 400)

    def test_an_unexpected_error_is_a_json_500_not_a_dropped_connection(self):
        from unittest import mock
        with mock.patch("agame.importer.apply_batch", side_effect=RuntimeError("boom")):
            st, h, body, _ = self.req("POST", "/api/import", self.muse(), headers=self.bearer())
        self.assertEqual(st, 500)
        self.assertTrue(h["Content-Type"].startswith("application/json"))
        self.assertEqual(body["error"], "internal error")
        self.assertIn("Retry once", body["next"])
        with mock.patch("agame.checkins.report", side_effect=RuntimeError("boom")):
            st, _, body, _ = self.req("GET", "/api/agent/checkins", headers=self.bearer())
        self.assertEqual((st, body["error"]), (500, "internal error"))
        st, _, body, _ = self.req("GET", "/api/agent/checkins?now=garbage", headers=self.bearer())
        self.assertEqual(st, 400, body)

    def test_a_non_ascii_or_masked_token_is_a_clean_401(self):
        for token in ("••••••••", "<AGAME_AGENT_TOKEN>", "tökén"):
            hdr = {"Authorization": "Bearer " + token}
            raw = hdr["Authorization"].encode("utf-8").decode("latin-1")  # http.client sends header bytes as latin-1
            st, _, body, _ = self.req("GET", "/api/agent/checkins", headers={"Authorization": raw})
            self.assertEqual(st, 401, (token, body))
            st, _, body, _ = self.req("POST", "/api/import", self.muse(), headers={"Authorization": raw})
            self.assertEqual(st, 401, (token, body))
            self.assertIn("invalid agent token", body["error"])

    def test_signed_in_requests_renew_the_session(self):
        _, _, _, cookies = self.req("GET", "/api/ping", cookie=self.session_cookie())
        self.assertTrue(any(c.startswith(auth.SESSION_COOKIE + "=") and "Max-Age=2592000" in c for c in cookies))

if __name__ == "__main__":
    unittest.main()
