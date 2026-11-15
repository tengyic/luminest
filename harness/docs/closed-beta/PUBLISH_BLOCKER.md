# Public link — blocked by the publishing platform

**Run:** 03621090 · **Date:** 2026-11-15 · **Status:** NOT PUBLISHED. No public URL exists.

## What is actually available

| Kind | Link | Status |
| --- | --- | --- |
| Local preview (loopback) | `http://127.0.0.1:18799` | **live**, 200 on all smoke routes |
| Same-machine LAN | `http://192.168.110.119:18799` | reachable only while the preview process runs, on the same network |
| Public share link | — | **none** |

The preview is a real, running instance of `outputs/closed-beta-site/server.py`
(PID from background task `J6xDdw`, `PORT=18799`, binds `0.0.0.0`). It is a
working link for this machine / LAN, **not** a public release link.

## Three failed deploy attempts (all identical)

| # | Directory | Result |
| --- | --- | --- |
| 1 | `outputs/closed-beta-site/` (original) | `SITES_APP_NOT_FOUND`, `retryable:false`, `appId=wbapp_3EiXiwaWSovkxwc1HX78j5` |
| 2 | `/Users/tengyi/WorkBuddy AI/luminest-beta-publish` (fresh copy + fresh task) | same code, same deleted appId |
| 3 | `/Users/tengyi/luminest-beta-public` (clean copy **outside** the workspace tree, no `.genie`, no `.workbuddy/applications.yaml` anywhere up the chain) | same code, same deleted appId |

Attempt 3 proves the binding is **session-level**, not directory-level: the tool
resolves the deleted appId from the current WorkBuddy task, so copying the project
to a new directory cannot escape it. Local root bindings that remain untouched:
`/Users/tengyi/WorkBuddy AI/2026-10-10-18-14-50/.wbapp_3EiXiwaWSovkxwc1HX78j5.genie`
and `/Users/tengyi/WorkBuddy AI/2026-10-10-18-14-50/.workbuddy/applications.yaml`.
These were **not deleted** — they belong to other published apps and deleting them
is not authorised.

The tool's `agentGuidance` says: do not call it again for this directory; relay the
user message and STOP. No further retry was made.

## Platform message (verbatim, Chinese — keep every path)

> 这个目录之前发布到的应用（wbapp_3EiXiwaWSovkxwc1HX78j5）已不存在（可能已在「设置—数据管理—应用」中删除），本次没有发布任何内容。为避免悄悄更换分享链接，已删除的应用不会自动重建，原来的分享链接也无法恢复，这个目录也不能再发布。如果要重新上线（会得到一条新的分享链接）：1. 把项目文件复制到一个新的目录；2. 删除 新目录里的 `.wbapp_3EiXiwaWSovkxwc1HX78j5.genie` 和 `.workbuddy/applications.yaml` 这两个文件；3. 在新目录中新开一个任务，再发布。如果你确认没有删除过这个应用，可能是服务暂时异常，可以过一会儿再试一次。

Steps 1–3 have already been carried out once (attempt 2/3) at the user's explicit
request and still returned the same deleted appId. The remaining supported path is
a **genuinely new WorkBuddy task/session**, i.e. a new conversation whose workspace
is the new directory, then publish from there. That cannot be done from inside this
session. The other clause — "if you are sure you did not delete the app, it may be a
temporary service anomaly, try again later" — is a platform-side recovery, not
something this workspace can force.

## What was checked as an alternative

- No tunnel CLI is installed (`cloudflared`, `ngrok`, `localtunnel`, `lt`,
  `tailscale` all absent). No public link can be manufactured locally.
- No `workbuddy_sites_deploy` re-call is permitted for this directory.
- The self-contained site directory is fully portable: copy it to any host that has
  Python 3 (stdlib only, SQLite file), run `PORT=<port> python3 server.py`, and it
  serves the landing, share codes, downloads, update manifest and the web version.
  See `INSTALL.txt` in the site directory.

## Consequence for the release checklist

Everything else in the closed-beta request is delivered and verified; the single
outstanding item is the public URL. The beta must not be described as "published".
Any status page or README claiming a live link is stale and must be corrected.
