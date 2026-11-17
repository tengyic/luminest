#!/usr/bin/env python3
"""Luminest closed-beta control server.

One small Python process, standard library only. It is the *single* place that
owns share codes, beta session tokens, consent-gated data collection and the
remote update manifest, and it also serves the landing page, the downloadable
bundle and the browser version of Luminest.

Why stdlib only: this is meant to run on a spare Mac mini, a Raspberry Pi, a
$5 VPS or the single-port publishing sandbox. No pip install, no database
server, no Redis. SQLite is a local file.

    PORT=8788 python3 server.py                     # local / device
    LUMINEST_BETA_ADMIN_TOKEN=... python3 server.py  # with admin endpoints
    LUMINEST_BACKEND_URL=http://127.0.0.1:8766 ...  # proxy /api/v1 to FastAPI
    LUMINEST_BACKEND_DB=/path/to/harness.sqlite3 ... # mirror codes into backend

Endpoints
    GET  /api/health
    GET  /api/beta/config
    POST /api/beta/codes                (admin)  issue share codes
    GET  /api/beta/codes                (admin)  list
    DELETE /api/beta/codes/<code>       (admin)  revoke
    POST /api/beta/redeem                        code -> session token
    GET  /api/beta/verify?token=...
    GET  /api/beta/collect/schema
    POST /api/beta/collect                       consent-gated user data
    GET  /api/updates/manifest.json
    POST /api/updates/manifest          (admin)  publish a new manifest
    ANY  /api/v1/*                               reverse proxy to FastAPI
    ANY  /*                                      static site (SPA aware)

Fail-closed rules
    * admin endpoints are disabled entirely when no admin token is configured;
    * redeem rejects unknown / revoked / exhausted / expired codes;
    * collect requires a live token AND an explicit `consent: true`, otherwise
      nothing is written (this is deliberate: no silent telemetry);
    * collection bodies are bounded and never logged verbatim;
    * the update manifest is read-only unless an admin publishes a new one.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import mimetypes
import os
import secrets
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
# A packaged site keeps index.html next to server.py, while a dev checkout may
# keep it under <ROOT>/site. Prefer an explicit override, then detect which
# layout is actually on disk. The publish sandbox cannot set env vars, so the
# detection fallback is what makes the deployed bundle serve its own pages.
_DEFAULT_SITE = ROOT if os.path.isfile(os.path.join(ROOT, "index.html")) else os.path.join(ROOT, "site")
SITE = os.path.abspath(os.environ.get("LUMINEST_SITE_DIR", _DEFAULT_SITE))
DB_PATH = os.path.abspath(os.environ.get("LUMINEST_BETA_DB", os.path.join(ROOT, "beta.db")))
ADMIN_TOKEN = os.environ.get("LUMINEST_BETA_ADMIN_TOKEN", "")
BACKEND_URL = os.environ.get("LUMINEST_BACKEND_URL", "http://127.0.0.1:8766").rstrip("/")
BACKEND_DB = os.environ.get("LUMINEST_BACKEND_DB", "")
VERSION = os.environ.get("LUMINEST_BETA_VERSION", "1.4.0-beta.1")
TOKEN_TTL = int(os.environ.get("LUMINEST_TOKEN_TTL", str(30 * 86400)))
MAX_BODY = 1024 * 1024

# No outbound proxy for loopback / the publish sandbox. urllib otherwise picks up
# HTTP_PROXY and reports a fake 502 for 127.0.0.1 (a known environment quirk).
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

_LOCK = threading.RLock()
_DB = None


def db() -> sqlite3.Connection:
    global _DB
    with _LOCK:
        if _DB is None:
            _DB = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=15)
            _DB.row_factory = sqlite3.Row
            _DB.execute("PRAGMA journal_mode=WAL")
            _DB.executescript(
                """
                CREATE TABLE IF NOT EXISTS share_codes (
                    code TEXT PRIMARY KEY,
                    scope TEXT NOT NULL DEFAULT 'beta',
                    email TEXT,
                    max_uses INTEGER NOT NULL DEFAULT 1,
                    uses INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'active',
                    expires_at REAL,
                    created_at REAL NOT NULL,
                    note TEXT
                );
                CREATE TABLE IF NOT EXISTS redemptions (
                    id TEXT PRIMARY KEY,
                    code TEXT NOT NULL,
                    email TEXT,
                    device_id TEXT,
                    redeemed_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    code TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    email TEXT,
                    device_id TEXT,
                    issued_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    revoked INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS collected (
                    id TEXT PRIMARY KEY,
                    token_hash TEXT NOT NULL,
                    consent INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    received_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS update_manifest (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    body TEXT NOT NULL,
                    published_at REAL NOT NULL
                );
                """
            )
            _DB.commit()
        return _DB


def now() -> float:
    return time.time()


def new_code() -> str:
    # Upper-case and dash separated: accounts.find_invite() does .strip().upper(),
    # so these are directly usable as backend beta_invites too.
    return "LUMINEST-" + secrets.token_hex(2).upper() + "-" + secrets.token_hex(2).upper()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def is_admin(headers) -> bool:
    supplied = headers.get("Authorization", "")
    if supplied.startswith("Bearer "):
        supplied = supplied[7:]
    return bool(ADMIN_TOKEN) and hmac.compare_digest(supplied, ADMIN_TOKEN)


def json_body(handler) -> dict:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    if length <= 0 or length > MAX_BODY:
        raise ValueError("empty or oversized body")
    raw = handler.rfile.read(length)
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("body must be a JSON object")
    return value


# --------------------------------------------------------------------- backend mirror

def mirror_code(code: str, *, max_uses: int, expires_at, email) -> bool:
    """Write the code into the FastAPI backend's beta_invites table too.

    Both processes then read the *same* source of truth. This is optional: when
    LUMINEST_BACKEND_DB is unset the control server is a standalone gate. Returns
    False (never raises) when the DB is absent or has a different schema, so a
    small-device deployment keeps working without the full backend.
    """
    if not BACKEND_DB or not os.path.isfile(BACKEND_DB):
        return False
    try:
        con = sqlite3.connect(BACKEND_DB, timeout=10)
        try:
            cols = {r[1] for r in con.execute("PRAGMA table_info(beta_invites)")}
            required = {"id", "code", "max_uses", "uses", "status", "created_at"}
            if not required.issubset(cols):
                return False
            con.execute(
                "INSERT OR IGNORE INTO beta_invites "
                "(id, code, max_uses, uses, status, expires_at, created_at, email, normalized_email) "
                "VALUES (?, ?, ?, 0, 'active', ?, ?, ?, ?)",
                (secrets.token_hex(16), code, max_uses, expires_at, now(), email,
                 email.strip().lower() if email else None),
            )
            con.commit()
            return True
        finally:
            con.close()
    except (sqlite3.Error, OSError):
        return False


def mirror_revoke(code: str) -> None:
    if not BACKEND_DB or not os.path.isfile(BACKEND_DB):
        return
    try:
        con = sqlite3.connect(BACKEND_DB, timeout=10)
        con.execute("UPDATE beta_invites SET status='revoked' WHERE code=?", (code,))
        con.commit()
        con.close()
    except (sqlite3.Error, OSError):
        pass


def seed_codes() -> None:
    for path in (os.path.join(SITE, "seed_codes.json"), os.path.join(ROOT, "seed_codes.json")):
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, ValueError):
            continue
        con = db()
        for row in payload.get("codes", []):
            code = str(row.get("code", "")).strip().upper()
            if not code:
                continue
            con.execute(
                "INSERT OR IGNORE INTO share_codes "
                "(code, scope, email, max_uses, uses, status, expires_at, created_at, note) "
                "VALUES (?, ?, ?, ?, 0, 'active', ?, ?, ?)",
                (code, row.get("scope", "beta"), row.get("email"),
                 int(row.get("max_uses", 1)), row.get("expires_at"), now(),
                 row.get("note", "seeded")),
            )
            mirror_code(code, max_uses=int(row.get("max_uses", 1)),
                        expires_at=row.get("expires_at"), email=row.get("email"))
        con.commit()
        return


# --------------------------------------------------------------------- business logic

def issue_codes(payload: dict) -> dict:
    count = max(1, min(int(payload.get("count", 1)), 200))
    max_uses = max(1, min(int(payload.get("max_uses", 1)), 1000))
    days = payload.get("expires_in_days")
    expires_at = None if days is None else now() + max(1, min(int(days), 365)) * 86400
    scope = payload.get("scope", "beta")
    if scope not in ("beta", "demo"):
        raise ValueError("scope must be 'beta' or 'demo'")
    email = (payload.get("email") or "").strip() or None
    con = db()
    made = []
    with _LOCK:
        for _ in range(count):
            code = new_code()
            con.execute(
                "INSERT INTO share_codes (code, scope, email, max_uses, uses, status, "
                "expires_at, created_at, note) VALUES (?, ?, ?, ?, 0, 'active', ?, ?, ?)",
                (code, scope, email, max_uses, expires_at, now(), payload.get("note", "")),
            )
            made.append(code)
            mirror_code(code, max_uses=max_uses, expires_at=expires_at, email=email)
        con.commit()
    return {"codes": made, "scope": scope, "max_uses": max_uses,
            "expires_at": expires_at, "backend_mirrored": bool(BACKEND_DB)}


def list_codes() -> dict:
    con = db()
    rows = con.execute(
        "SELECT code, scope, email, max_uses, uses, status, expires_at, created_at "
        "FROM share_codes ORDER BY created_at DESC LIMIT 500"
    ).fetchall()
    return {"codes": [dict(r) for r in rows]}


def revoke_code(code: str) -> bool:
    con = db()
    with _LOCK:
        cur = con.execute("UPDATE share_codes SET status='revoked' WHERE code=?", (code,))
        con.commit()
    if cur.rowcount:
        mirror_revoke(code)
    return bool(cur.rowcount)


def redeem(payload: dict) -> dict:
    code = str(payload.get("code", "")).strip().upper()
    email = (payload.get("email") or "").strip() or None
    device_id = (payload.get("device_id") or "").strip() or None
    con = db()
    with _LOCK:
        row = con.execute("SELECT * FROM share_codes WHERE code=?", (code,)).fetchone()
        if not row:
            raise PermissionError("Unknown share code. Ask the operator for a code.")
        if row["status"] != "active":
            raise PermissionError("This share code has been revoked.")
        if row["expires_at"] and row["expires_at"] < now():
            con.execute("UPDATE share_codes SET status='expired' WHERE code=?", (code,))
            con.commit()
            raise PermissionError("This share code has expired.")
        if row["uses"] >= row["max_uses"]:
            con.execute("UPDATE share_codes SET status='exhausted' WHERE code=?", (code,))
            con.commit()
            raise PermissionError("This share code has already been used.")
        if row["email"] and (not email or row["email"].strip().lower() != email.strip().lower()):
            raise PermissionError("This share code is addressed to a different email.")
        token = secrets.token_urlsafe(32)
        issued = now()
        expires = issued + TOKEN_TTL
        con.execute("UPDATE share_codes SET uses=uses+1 WHERE code=?", (code,))
        con.execute(
            "INSERT INTO redemptions (id, code, email, device_id, redeemed_at) VALUES (?,?,?,?,?)",
            (secrets.token_hex(16), code, email, device_id, issued),
        )
        con.execute(
            "INSERT INTO sessions (token, code, scope, email, device_id, issued_at, expires_at, revoked) "
            "VALUES (?,?,?,?,?,?,?,0)",
            (token, code, row["scope"], email, device_id, issued, expires),
        )
        con.commit()
    return {"token": token, "scope": row["scope"],
            "downloads_unlocked": row["scope"] == "beta",
            "expires_at": expires,
            "email_verification_required": False,
            "billing_required": False}


def verify(token: str) -> dict:
    con = db()
    row = con.execute("SELECT * FROM sessions WHERE token=?", (token,)).fetchone()
    if not row or row["revoked"] or row["expires_at"] < now():
        return {"valid": False}
    return {"valid": True, "scope": row["scope"],
            "downloads_unlocked": row["scope"] == "beta",
            "expires_at": row["expires_at"]}


COLLECT_SCHEMA = {
    "purpose": "Closed-beta product improvement only. Nothing is sold or shared.",
    "consent_required": True,
    "fields": {
        "platform": "macOS / iPadOS / Windows / Linux / web",
        "app_version": "the version string shown in Settings",
        "event": "a short event name, e.g. lesson_opened",
        "note": "optional free text (do not enter personal or sensitive data)",
    },
    "never_collected": ["window titles", "keystrokes", "passwords", "share codes",
                        "lesson content", "payment data (there is no billing)"],
    "retention_days": 90,
    "withdraw": "Stop sending /api/beta/collect, or ask the operator to delete your rows.",
}


def collect(payload: dict) -> dict:
    token = str(payload.get("token", ""))
    if not verify(token)["valid"]:
        raise PermissionError("A live beta token is required.")
    if payload.get("consent") is not True:
        raise PermissionError("Explicit consent:true is required; nothing was stored.")
    body = payload.get("payload")
    if not isinstance(body, dict):
        raise ValueError("payload must be an object")
    allowed = {"platform", "app_version", "event", "note"}
    clean = {k: str(v)[:500] for k, v in body.items() if k in allowed}
    if not clean:
        raise ValueError("no recognised fields in payload")
    con = db()
    with _LOCK:
        con.execute(
            "INSERT INTO collected (id, token_hash, consent, kind, payload, received_at) "
            "VALUES (?,?,1,?,?,?)",
            (secrets.token_hex(16), token_hash(token), str(clean.get("event", "note")),
             json.dumps(clean, ensure_ascii=False), now()),
        )
        con.commit()
    return {"stored": True, "fields": sorted(clean)}


def manifest() -> dict:
    con = db()
    row = con.execute("SELECT body FROM update_manifest WHERE id=1").fetchone()
    if row:
        return json.loads(row["body"])
    path = os.path.join(SITE, "updates", "manifest.json")
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return {"product": "Luminest", "version": VERSION, "channel": "closed-beta",
            "artifacts": [], "note": "No published build yet."}


def publish_manifest(payload: dict) -> dict:
    for key in ("version", "artifacts"):
        if key not in payload:
            raise ValueError("manifest needs version and artifacts")
    for artifact in payload["artifacts"]:
        if not isinstance(artifact, dict) or not artifact.get("sha256") or not artifact.get("url"):
            raise ValueError("every artifact needs url and sha256")
    body = {
        "product": "Luminest",
        "channel": "closed-beta",
        "version": str(payload["version"]),
        "published_at": now(),
        "min_macos": payload.get("min_macos", "14.0"),
        "artifacts": payload["artifacts"],
        "notes": payload.get("notes", ""),
    }
    con = db()
    with _LOCK:
        con.execute(
            "INSERT INTO update_manifest (id, body, published_at) VALUES (1, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET body=excluded.body, published_at=excluded.published_at",
            (json.dumps(body), now()),
        )
        con.commit()
    os.makedirs(os.path.join(SITE, "updates"), exist_ok=True)
    with open(os.path.join(SITE, "updates", "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(body, fh, indent=2)
        fh.write("\n")
    return body


# --------------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    server_version = "LuminestBeta/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        # Never log tokens or collected payloads. `/api/beta/verify` carries the
        # session token in the query string, so redact every query before it
        # reaches stderr -- the promise above is worthless otherwise.
        line = fmt % args
        if "?" in line:
            head, _, _ = line.partition("?")
            tail = line[len(head) + 1:]
            line = head + "?<redacted>" + (tail[tail.find(" "):] if " " in tail else "")
        sys.stderr.write("[beta] %s\n" % line)

    def _send(self, status: int, body: bytes, ctype: str, extra=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, obj):
        self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _err(self, status: int, message: str):
        self._json(status, {"error": message})

    def do_OPTIONS(self):
        self._send(204, b"", "text/plain")

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        try:
            if path == "/api/health":
                return self._json(200, {"status": "ok", "product": "Luminest",
                                        "version": VERSION, "time": now(),
                                        "admin_enabled": bool(ADMIN_TOKEN),
                                        "backend_proxy": BACKEND_URL})
            if path == "/api/beta/config":
                return self._json(200, {
                    "product": "Luminest", "channel": "closed-beta",
                    "share_code_required": True,
                    "email_auth": "identifier-only",
                    "email_verification_required": False,
                    "reason": "Codes are issued out-of-band; no SMTP dependency on a small device.",
                    "billing_required": False,
                    "data_collection": COLLECT_SCHEMA,
                    "update_manifest_url": "/api/updates/manifest.json",
                })
            if path == "/api/beta/collect/schema":
                return self._json(200, COLLECT_SCHEMA)
            if path == "/api/beta/verify":
                return self._json(200, verify(query.get("token", [""])[0]))
            if path == "/api/beta/codes":
                if not is_admin(self.headers):
                    return self._err(403, "Admin token required (or not configured).")
                return self._json(200, list_codes())
            if path == "/api/updates/manifest.json":
                return self._json(200, manifest())
            if path.startswith("/api/v1/"):
                return self._proxy("GET", path, None)
            return self._static(path)
        except Exception as exc:  # noqa: BLE001 - fail closed, never leak a traceback
            return self._err(500, "internal error: %s" % type(exc).__name__)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        try:
            if path.startswith("/api/v1/"):
                return self._proxy("POST", path, self._read_raw())
            payload = json_body(self)
            if path == "/api/beta/codes":
                if not is_admin(self.headers):
                    return self._err(403, "Admin token required (or not configured).")
                return self._json(201, issue_codes(payload))
            if path == "/api/beta/redeem":
                return self._json(200, redeem(payload))
            if path == "/api/beta/collect":
                return self._json(201, collect(payload))
            if path == "/api/updates/manifest":
                if not is_admin(self.headers):
                    return self._err(403, "Admin token required (or not configured).")
                return self._json(200, publish_manifest(payload))
            return self._err(404, "No such endpoint")
        except PermissionError as exc:
            return self._err(403, str(exc))
        except (ValueError, KeyError, TypeError) as exc:
            return self._err(422, str(exc))
        except Exception as exc:  # noqa: BLE001
            return self._err(500, "internal error: %s" % type(exc).__name__)

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if not path.startswith("/api/beta/codes/"):
            return self._err(404, "No such endpoint")
        if not is_admin(self.headers):
            return self._err(403, "Admin token required (or not configured).")
        code = urllib.parse.unquote(path.rsplit("/", 1)[-1]).upper()
        return self._json(200, {"revoked": revoke_code(code)})

    def _read_raw(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return b""
        if length > 16 * 1024 * 1024:
            raise ValueError("request too large")
        return self.rfile.read(length)

    def _proxy(self, method: str, path: str, body: bytes | None):
        """Forward /api/v1/* to the FastAPI backend so the browser build works
        from the same origin (no CORS middleware exists in the backend)."""
        url = BACKEND_URL + path
        req = urllib.request.Request(url, data=body, method=method)
        for key in ("Content-Type", "Authorization", "Accept"):
            if self.headers.get(key):
                req.add_header(key, self.headers.get(key))
        try:
            with _OPENER.open(req, timeout=25) as resp:
                data = resp.read()
                status = resp.status
                ctype = resp.headers.get("Content-Type", "application/json")
        except urllib.error.HTTPError as exc:
            data = exc.read()
            status = exc.code
            ctype = exc.headers.get("Content-Type", "application/json")
        except Exception as exc:  # noqa: BLE001
            return self._json(502, {"error": "backend unreachable",
                                    "backend": BACKEND_URL,
                                    "detail": type(exc).__name__})
        self._send(status, data, ctype)

    def _static(self, path: str):
        if path.startswith("/api/"):
            return self._err(404, "No such endpoint")
        rel = urllib.parse.unquote(path).lstrip("/") or "index.html"
        # Never serve server internals. seed_codes.json holds the operator's
        # private codes, beta.db holds session tokens, and server.py is source.
        lowered = rel.lower()
        if (lowered.endswith("seed_codes.json") or lowered.endswith(".db")
                or lowered.endswith(".db-wal") or lowered.endswith(".db-shm")
                or lowered.endswith("server.py") or lowered.startswith(".env")
                or "/.git/" in lowered):
            return self._err(403, "Not served")
        # Downloads are genuinely gated server-side, not just hidden in the DOM.
        # A demo-scope token may use the browser build but cannot fetch the bundle.
        if rel.startswith("downloads/"):
            parsed = urllib.parse.urlparse(self.path)
            supplied = urllib.parse.parse_qs(parsed.query).get("token", [""])[0]
            if not supplied:
                supplied = self.headers.get("Authorization", "").removeprefix("Bearer ")
            info = verify(supplied)
            if not info["valid"] or not info["downloads_unlocked"]:
                return self._err(403, "A valid beta share code is required to download the build.")
        target = os.path.abspath(os.path.join(SITE, rel))
        if not target.startswith(SITE + os.sep) and target != SITE:
            return self._err(403, "Path outside site root")
        if os.path.isdir(target):
            target = os.path.join(target, "index.html")
        # SPA fallback for the browser client: /app/<route> -> /app/index.html
        if not os.path.isfile(target) and rel.startswith("app/"):
            target = os.path.join(SITE, "app", "index.html")
        if not os.path.isfile(target):
            return self._err(404, "Not found: /" + rel)
        ctype = mimetypes.guess_type(target)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        with open(target, "rb") as fh:
            data = fh.read()
        cache = "no-cache" if rel.startswith(("app/", "updates/")) else "public, max-age=300"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", cache)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)


def main() -> None:
    global DB_PATH, _DB
    os.makedirs(SITE, exist_ok=True)
    try:
        db()
    except sqlite3.OperationalError:
        # Some single-port publishing sandboxes mount the code directory
        # read-only. State still has to work, so fall back to a writable temp
        # file rather than failing to boot (and say so on stdout).
        import tempfile
        DB_PATH = os.path.join(tempfile.gettempdir(), "luminest-beta.db")
        _DB = None
        db()
        print("  note    : code dir read-only, DB relocated to %s" % DB_PATH, flush=True)
    seed_codes()
    port = int(os.environ.get("PORT", "8788"))
    httpd = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    httpd.daemon_threads = True
    print("Luminest beta control server on 0.0.0.0:%d" % port, flush=True)
    print("  site   : %s" % SITE, flush=True)
    print("  db     : %s" % DB_PATH, flush=True)
    print("  backend: %s" % BACKEND_URL, flush=True)
    print("  admin  : %s" % ("enabled" if ADMIN_TOKEN else "disabled (fail-closed)"), flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
