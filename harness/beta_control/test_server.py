"""End-to-end tests for the beta control server.

Runs the real server in a thread against a temporary database and site root, then
exercises the HTTP surface with urllib (proxy disabled for loopback).

    env -u PYTHONPATH python3 -m unittest discover -s harness/beta_control -v
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def load_server():
    spec = importlib.util.spec_from_file_location("beta_server", os.path.join(HERE, "server.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class BetaServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="luminest-beta-test-")
        cls.site = os.path.join(cls.tmp, "site")
        os.makedirs(cls.site, exist_ok=True)
        with open(os.path.join(cls.site, "index.html"), "w", encoding="utf-8") as fh:
            fh.write("<!doctype html><title>Luminest beta</title><h1>Luminest</h1>")
        os.makedirs(os.path.join(cls.site, "updates"), exist_ok=True)
        os.makedirs(os.path.join(cls.site, "downloads"), exist_ok=True)
        with open(os.path.join(cls.site, "downloads", "Luminest.zip"), "wb") as fh:
            fh.write(b"fake bundle for gating test")
        with open(os.path.join(cls.site, "seed_codes.json"), "w", encoding="utf-8") as fh:
            json.dump({"codes": [{"code": "LUMINEST-DEMO-2026", "scope": "demo",
                                  "max_uses": 10}]}, fh)
        with open(os.path.join(cls.site, "updates", "manifest.json"), "w", encoding="utf-8") as fh:
            json.dump({"product": "Luminest", "version": "1.4.0-beta.1",
                       "channel": "closed-beta", "artifacts": []}, fh)
        os.environ["LUMINEST_SITE_DIR"] = cls.site
        os.environ["LUMINEST_BETA_DB"] = os.path.join(cls.tmp, "beta.db")
        os.environ["LUMINEST_BETA_ADMIN_TOKEN"] = "test-admin-token"
        os.environ["LUMINEST_BACKEND_DB"] = ""
        os.environ["LUMINEST_BACKEND_URL"] = "http://127.0.0.1:1"
        cls.mod = load_server()
        from http.server import ThreadingHTTPServer
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), cls.mod.Handler)
        cls.port = cls.httpd.server_address[1]
        cls.mod.db()
        cls.mod.seed_codes()
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = "http://127.0.0.1:%d" % cls.port

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def call(self, method, path, body=None, token=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        if data:
            req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("Authorization", "Bearer " + token)
        try:
            with OPENER.open(req, timeout=10) as resp:
                raw = resp.read().decode()
                return resp.status, (json.loads(raw) if raw else {})
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode()
            try:
                return exc.code, json.loads(raw)
            except ValueError:
                return exc.code, raw

    def test_01_health_and_config(self):
        s, body = self.call("GET", "/api/health")
        self.assertEqual(s, 200)
        self.assertEqual(body["product"], "Luminest")
        self.assertTrue(body["admin_enabled"])
        s, cfg = self.call("GET", "/api/beta/config")
        self.assertTrue(cfg["share_code_required"])
        self.assertFalse(cfg["email_verification_required"])
        self.assertFalse(cfg["billing_required"])

    def test_02_admin_gate_fails_closed(self):
        s, _ = self.call("GET", "/api/beta/codes")
        self.assertEqual(s, 403)
        s, _ = self.call("POST", "/api/beta/codes", {"count": 1})
        self.assertEqual(s, 403)

    def test_03_issue_and_redeem(self):
        s, issued = self.call("POST", "/api/beta/codes",
                              {"count": 2, "max_uses": 1, "scope": "beta"},
                              token="test-admin-token")
        self.assertEqual(s, 201)
        self.assertEqual(len(issued["codes"]), 2)
        code = issued["codes"][0]
        s, session = self.call("POST", "/api/beta/redeem",
                               {"code": code.lower(), "email": "tester@example.test",
                                "device_id": "test-mac"})
        self.assertEqual(s, 200)
        self.assertTrue(session["downloads_unlocked"])
        self.assertFalse(session["email_verification_required"])
        self.assertFalse(session["billing_required"])
        s, verified = self.call("GET", "/api/beta/verify?token=" + session["token"])
        self.assertTrue(verified["valid"])
        # single-use: second redeem must fail
        s, _ = self.call("POST", "/api/beta/redeem", {"code": code})
        self.assertEqual(s, 403)
        self.__class__.token = session["token"]
        self.__class__.spare_code = issued["codes"][1]

    def test_04_unknown_code_rejected(self):
        s, body = self.call("POST", "/api/beta/redeem", {"code": "NOT-A-CODE"})
        self.assertEqual(s, 403)
        self.assertIn("Unknown", body["error"])

    def test_05_collect_is_consent_gated(self):
        token = getattr(self.__class__, "token", None)
        self.assertTrue(token)
        s, _ = self.call("POST", "/api/beta/collect",
                         {"token": token, "payload": {"event": "lesson_opened"}})
        self.assertEqual(s, 403, "missing consent must not store anything")
        s, _ = self.call("POST", "/api/beta/collect",
                         {"token": "bogus", "consent": True,
                          "payload": {"event": "lesson_opened"}})
        self.assertEqual(s, 403, "bad token must not store anything")
        s, ok = self.call("POST", "/api/beta/collect",
                          {"token": token, "consent": True,
                           "payload": {"event": "lesson_opened", "platform": "iPadOS",
                                       "note": "ignore me", "password": "must be dropped"}})
        self.assertEqual(s, 201)
        self.assertNotIn("password", ok["fields"])
        con = self.mod.db()
        count = con.execute("SELECT COUNT(*) FROM collected").fetchone()[0]
        self.assertEqual(count, 1)
        stored = con.execute("SELECT payload FROM collected").fetchone()[0]
        self.assertNotIn("password", stored)

    def test_06_revoke(self):
        code = getattr(self.__class__, "spare_code", None)
        self.assertTrue(code)
        s, body = self.call("DELETE", "/api/beta/codes/" + code, token="test-admin-token")
        self.assertTrue(body["revoked"])
        s, _ = self.call("POST", "/api/beta/redeem", {"code": code})
        self.assertEqual(s, 403)

    def test_07_update_manifest(self):
        s, body = self.call("GET", "/api/updates/manifest.json")
        self.assertEqual(s, 200)
        self.assertEqual(body["product"], "Luminest")
        s, published = self.call("POST", "/api/updates/manifest",
                                 {"version": "1.4.1-beta.1",
                                  "artifacts": [{"url": "downloads/Luminest.zip",
                                                 "sha256": "a" * 64}]},
                                 token="test-admin-token")
        self.assertEqual(s, 200)
        self.assertEqual(published["version"], "1.4.1-beta.1")
        s, reread = self.call("GET", "/api/updates/manifest.json")
        self.assertEqual(reread["version"], "1.4.1-beta.1")
        s, _ = self.call("POST", "/api/updates/manifest",
                         {"version": "bad", "artifacts": [{"url": "x"}]},
                         token="test-admin-token")
        self.assertEqual(s, 422, "artifacts without sha256 must be rejected")

    def test_08_static_site_and_spa_fallback(self):
        req = urllib.request.Request(self.base + "/index.html")
        with OPENER.open(req, timeout=10) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn(b"Luminest", resp.read())
        s, _ = self.call("GET", "/app/some/route")
        # SPA fallback only kicks in when app/index.html exists; here it 404s honestly.
        self.assertEqual(s, 404)

    def test_09_collect_schema_is_published(self):
        s, schema = self.call("GET", "/api/beta/collect/schema")
        self.assertEqual(s, 200)
        self.assertTrue(schema["consent_required"])
        self.assertIn("payment data (there is no billing)", schema["never_collected"])

    def test_10_downloads_gated_server_side(self):
        # No token at all -> 403 even though the file physically exists.
        req = urllib.request.Request(self.base + "/downloads/Luminest.zip")
        try:
            OPENER.open(req, timeout=10)
            self.fail("ungated download must be rejected")
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 403)
        # Demo-scope token -> still 403 (browser demo is not a beta entitlement).
        s, demo = self.call("POST", "/api/beta/redeem", {"code": "LUMINEST-DEMO-2026"})
        self.assertEqual(s, 200)
        self.assertFalse(demo["downloads_unlocked"])
        req = urllib.request.Request(
            self.base + "/downloads/Luminest.zip?token=" + demo["token"])
        try:
            OPENER.open(req, timeout=10)
            self.fail("demo token must not unlock the bundle")
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 403)
        # Beta token from test_03 -> 200 and the real bytes.
        token = getattr(self.__class__, "token", None)
        self.assertTrue(token)
        req = urllib.request.Request(
            self.base + "/downloads/Luminest.zip?token=" + token)
        with OPENER.open(req, timeout=10) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn(b"fake bundle", resp.read())

    def test_11_internal_files_never_served(self):
        for rel in ("seed_codes.json", "server.py", "beta.db"):
            req = urllib.request.Request(self.base + "/" + rel)
            try:
                OPENER.open(req, timeout=10)
            except urllib.error.HTTPError as exc:
                self.assertIn(exc.code, (403, 404))

    def test_12_verify_log_redacts_token(self):
        # The request line carries ?token=...; the log must not. We assert the
        # redaction function directly because capturing stderr is racy.
        import io
        from contextlib import redirect_stderr
        h = self.mod.Handler.__new__(self.mod.Handler)
        buf = io.StringIO()
        with redirect_stderr(buf):
            h.log_message('"GET /api/beta/verify?token=%s HTTP/1.1" 200 -', "SUPERSECRET")
        self.assertNotIn("SUPERSECRET", buf.getvalue())
        self.assertIn("<redacted>", buf.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
