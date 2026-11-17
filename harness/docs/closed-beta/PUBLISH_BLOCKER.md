# Public link — RESOLVED (new share link issued)

**Run:** 03621090 → continued 2026-11-16 · **Status:** PUBLISHED.
**App:** `wbapp_i2NXsCksKaquxJUrLmkFNP` · `deployedAs: http-service` · `verified: true`
**Sandbox:** `c81b57ed3081400691027ec538449063`

The file name `PUBLISH_BLOCKER.md` is kept for audit continuity. It now records
both the original platform block and the resolution; it is no longer a blocker.

## The share link

```text
https://wbapp-i2nxsckskaquxjurlmkfnp.app.workbuddy.host/?sharecode=<code>
```

The `?sharecode=` query parameter is **required by the platform gateway**: without
it the same URL returns HTTP 403. It is not a second Luminest login; it is the
share gate for this published app. The app is managed in
**「设置—数据管理—应用」**.

**The code itself is deliberately not printed here.** It gates access to the closed beta, and
this repository is public; writing it down would remove the gate it exists to be. The
running document that recorded it before this redaction is operator-held. Everything else on
this page — route, app id, status codes, the download `token` rule — is verbatim.

`luminest.app.workbuddy.host/` — the exact host Tengyi asked for — still returns
HTTP 404 `链接已失效`. That application was deleted previously, and the platform
does not re-create deleted apps or restore their links. `domainPrefix: "luminest"`
was supplied on every deploy call, but the successful `http-service` publish was
assigned a new appId-based host. The vanity hostname cannot be claimed from this
workspace; it must be changed in the app's management UI or by the platform.

## Verified on the live link (2026-11-16 00:36 GMT+8)

All routes below were checked with `?sharecode=<code>`.

| Route | Result |
| --- | --- |
| `/` (Design A, default) | 200, 41 830 bytes, `<title>Luminest — closed beta</title>` |
| `/?variant=conversation` (Design B) | 200 |
| `/api/health`, `/api/beta/config`, `/api/beta/collect/schema`, `/api/updates/manifest.json` | 200 / 200 / 200 / 200 |
| `/agreement.html`, `/INSTALL.txt`, `/download-manifest.json`, `/updates/manifest.json` | 200 / 200 / 200 / 200 |
| `/assets/art.json`, `/assets/art/reader.jpg`, `/assets/captures/01-today.jpg` | 200 / 200 / 200 |
| `/app/`, `/app/manifest.webmanifest` | 200 / 200 (real PWA shell, not a placeholder) |
| `POST /api/beta/redeem` with `LUMINEST-DEMO-2026` | 200, `scope=demo`, `downloads_unlocked=false`, `billing_required=false`, `email_verification_required=false` |
| `POST /api/beta/redeem` with an unknown code | 200 with `{"error": "Unknown share code. Ask the operator for a code."}` |
| `/downloads/Luminest-arm64.dmg` without a token | 403 — server-side download gating holds |

## Defect found and fixed while publishing

The first successful deploy served `{"error": "Not found: /index.html"}` on `/`
while the API routes already returned 200. Cause: `beta_control/server.py`
defaulted `SITE` to `<ROOT>/site`, but the packaged bundle keeps `index.html`
beside `server.py`. Only the local preview passed `LUMINEST_SITE_DIR`; the
publish sandbox cannot set environment variables.

Fix in `harness/beta_control/server.py` (source of truth for `package_beta.py`):

```python
_DEFAULT_SITE = ROOT if os.path.isfile(os.path.join(ROOT, "index.html")) else os.path.join(ROOT, "site")
SITE = os.path.abspath(os.environ.get("LUMINEST_SITE_DIR", _DEFAULT_SITE))
```

`package_beta.py` was re-run (exit 0, brand guard green, 2 release artifacts
verified) and `server.py` was synced into all four site copies. A sandbox
simulation with only `PORT` set returned 200 on `/`, `/api/health`,
`/agreement.html`, `/assets/art.json`, `/assets/art/reader.jpg`,
`/assets/captures/01-today.jpg`, `/download-manifest.json` and `/app/` — 8/8
PASS. The fixed app was then re-published as `http-service`.

## Original block and how it was cleared

The three attempts on 2026-11-15, plus a fourth attempt in this session, all
returned `SITES_APP_NOT_FOUND` / `retryable:false` for the deleted app
`wbapp_3EiXiwaWSovkxwc1HX78j5`. Attempt 3 used `/Users/tengyi/luminest-beta-public`,
a clean copy outside the workspace tree with no `.genie` and no
`.workbuddy/applications.yaml` anywhere up the chain, proving the binding was
session-level rather than directory-level.

Following the platform's own recovery steps, a genuinely new WorkBuddy task was
started with workspace `/Users/tengyi/luminest-live`. Publishing from that new
session created the new app `wbapp_i2NXsCksKaquxJUrLmkFNP` and issued the share
link above. No stale binding was deleted and no unpublished content was claimed
as live.

Historical platform message from the blocked attempts (kept verbatim):

> 这个目录之前发布到的应用（wbapp_3EiXiwaWSovkxwc1HX78j5）已不存在（可能已在「设置—数据管理—应用」中删除），本次没有发布任何内容。为避免悄悄更换分享链接，已删除的应用不会自动重建，原来的分享链接也无法恢复，这个目录也不能再发布。如果要重新上线（会得到一条新的分享链接）：1. 把项目文件复制到一个新的目录；2. 删除 新目录里的 `.wbapp_3EiXiwaWSovkxwc1HX78j5.genie` 和 `.workbuddy/applications.yaml` 这两个文件；3. 在新目录中新开一个任务，再发布。如果你确认没有删除过这个应用，可能是服务暂时异常，可以过一会儿再试一次。

## Local preview

A local instance remains available at `http://127.0.0.1:18799`
(LAN `http://192.168.110.119:18799`) while the preview process runs. It is a
real instance of `outputs/closed-beta-site/server.py` bound to `0.0.0.0`, but it
is not the public link and should not be shared as one.

## Release checklist consequence

The public URL item is now closed. The exact vanity domain is not available; the
appId-based share link above is the canonical closed-beta link. This document is
the single source of truth for that distinction.
