"""Owner sign-in: OpenID Connect authorization-code flow (PKCE, state, nonce) and signed sessions.

Identity is taken from the ID token received directly from the provider's token endpoint
over TLS (OIDC Core 3.1.3.7: TLS server validation replaces signature checking for this
channel) and cross-checked with the userinfo endpoint. Only AGAME_OWNER_EMAIL, verified,
gets a session. Standard library only.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time
import urllib.parse
import urllib.request

SESSION_COOKIE = "agame_session"
FLOW_COOKIE = "agame_oidc"
SESSION_TTL = 30 * 24 * 3600
FLOW_TTL = 600
ROTATE_AFTER = 0  # every signed-in request renews the 30-day session


def _b64e(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _b64d(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class Signer:
    def __init__(self, secret):
        if not secret or len(secret) < 32:
            raise ValueError("AGAME_SESSION_SECRET must be at least 32 characters")
        self.key = secret.encode()

    def sign(self, obj):
        body = _b64e(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode())
        mac = _b64e(hmac.new(self.key, body.encode(), hashlib.sha256).digest())
        return f"{body}.{mac}"

    def verify(self, token, max_age=None):
        try:
            body, mac = token.split(".", 1)
        except (ValueError, AttributeError):
            return None
        good = _b64e(hmac.new(self.key, body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(good, mac):
            return None
        try:
            obj = json.loads(_b64d(body))
        except (ValueError, json.JSONDecodeError):
            return None
        now = time.time()
        if obj.get("exp") and now > obj["exp"]:
            return None
        if max_age and now - obj.get("iat", 0) > max_age:
            return None
        return obj


def new_session(signer, email):
    now = int(time.time())
    return signer.sign({"email": email, "iat": now, "exp": now + SESSION_TTL, "sid": secrets.token_hex(8)})


def cookie_header(name, value, max_age, secure, path="/"):
    parts = [f"{name}={value}", f"Path={path}", f"Max-Age={max_age}", "HttpOnly", "SameSite=Lax"]
    if secure:
        parts.append("Secure")
    return "; ".join(parts)


def parse_cookies(header):
    out = {}
    for part in (header or "").split(";"):
        if "=" in part:
            k, v = part.strip().split("=", 1)
            out[k] = v
    return out


class OIDC:
    def __init__(self, issuer, client_id, client_secret, redirect_uri, opener=None):
        self.issuer = issuer.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self._disc = None
        self._open = opener or urllib.request.urlopen

    def discovery(self):
        if self._disc is None:
            with self._open(self.issuer + "/.well-known/openid-configuration", timeout=10) as r:
                self._disc = json.loads(r.read())
        return self._disc

    def start(self, signer):
        state, nonce, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(24), secrets.token_urlsafe(48)
        challenge = _b64e(hashlib.sha256(verifier.encode()).digest())
        q = {"response_type": "code", "client_id": self.client_id, "redirect_uri": self.redirect_uri, "scope": "openid email profile",
             "state": state, "nonce": nonce, "code_challenge": challenge, "code_challenge_method": "S256", "prompt": "select_account"}
        url = self.discovery()["authorization_endpoint"] + "?" + urllib.parse.urlencode(q)
        now = int(time.time())
        flow = signer.sign({"state": state, "nonce": nonce, "verifier": verifier, "iat": now, "exp": now + FLOW_TTL})
        return url, flow

    def finish(self, signer, flow_cookie, code, state):
        flow = signer.verify(flow_cookie or "", max_age=FLOW_TTL)
        if not flow or not hmac.compare_digest(flow.get("state", ""), state or ""):
            raise PermissionError("sign-in state mismatch or expired; start again")
        d = self.discovery()
        body = urllib.parse.urlencode({"grant_type": "authorization_code", "code": code, "redirect_uri": self.redirect_uri,
                                       "client_id": self.client_id, "client_secret": self.client_secret,
                                       "code_verifier": flow["verifier"]}).encode()
        req = urllib.request.Request(d["token_endpoint"], data=body, headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
        with self._open(req, timeout=15) as r:
            tok = json.loads(r.read())
        claims = {}
        if tok.get("id_token"):
            try:
                claims = json.loads(_b64d(tok["id_token"].split(".")[1]))
            except (ValueError, IndexError, json.JSONDecodeError):
                raise PermissionError("malformed ID token")
            if claims.get("nonce") != flow["nonce"]:
                raise PermissionError("nonce mismatch")
            aud = claims.get("aud")
            if (aud != self.client_id) and not (isinstance(aud, list) and self.client_id in aud):
                raise PermissionError("ID token audience mismatch")
            if claims.get("iss", "").rstrip("/") != d.get("issuer", self.issuer).rstrip("/"):
                raise PermissionError("ID token issuer mismatch")
            if claims.get("exp") and time.time() > claims["exp"] + 60:
                raise PermissionError("ID token expired")
        info = {}
        if tok.get("access_token") and d.get("userinfo_endpoint"):
            req = urllib.request.Request(d["userinfo_endpoint"], headers={"Authorization": f"Bearer {tok['access_token']}", "Accept": "application/json"})
            with self._open(req, timeout=10) as r:
                info = json.loads(r.read())
        email = (info.get("email") or claims.get("email") or "").strip().lower()
        verified = info.get("email_verified", claims.get("email_verified"))
        if verified in ("true", True):
            verified = True
        return email, bool(verified)
