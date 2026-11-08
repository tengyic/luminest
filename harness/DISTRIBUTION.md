# Luminest — macOS 分发与签名指南

Release boundary reviewed on 2026-11-08. The observed `outputs/.packaging/package-result.json`
records version `1.2.0`, `legal_gate.ship_ready: true`, and zero legal placeholders, but
`sign_identity`, `app_notarization`, and `notarization` are null. That recorded build is
**not a public release**. These observations do not establish that its bytes match the
current source tree or that its legal text has independent legal approval.

Every public direct download requires genuine Developer ID Application signatures,
Apple notarization, validated stapled app and DMG tickets, passing build/smoke/provenance
checks, and legal approval. Metadata or successful local launch cannot replace these
checks. `scripts/release_kit.py` fails closed when release evidence is absent or rejected.

`--allow-template-legal` is for development-only template builds, never a public beta or
end-user download. Their filenames carry `-ALPHA-TEMPLATE-LEGAL`, and their bundle carries
`Contents/Resources/NOT_RELEASABLE.txt`; these markers must not be removed or relabeled.

## 打包产物里已就位的东西

| 项 | 位置 | 状态 |
|---|---|---|
| Privacy manifest | `Contents/Resources/PrivacyInfo.xcprivacy`(无条件复制) | ✅ 随每次打包进入 bundle |
| Entitlements | `LuminfestLearningHarness-Direct.entitlements`(直发,hardened runtime)或 `-Sandbox`(Mac App Store) | ✅ 签名时施加 |
| 签名顺序 | 内层 Mach-O 自底向上 → bundle(禁用 `--deep`) | ✅ `sign_bundle()` |
| DMG signing and notarization | Sign and verify the expected Developer ID before `notarytool submit --wait`; staple/validate app before archiving and DMG after submission | Implemented by `notarize_app()` / `notarize()`; public release still requires live verification |
| distribution.json | 记录 signing/sandboxed/notarized/notice | ✅ 每包自带 |
| 课程/媒体 pack | `--add-data` 进 bundle(`PACK_DATA_DIRS`) | ✅ 冻结冒烟断言图谱非空、媒体与仿真路由可用 |
| 法律文本草稿 | `backend/legal/` 以 `--add-data` 进 bundle(`LEGAL_DATA_DIR`) | ✅ 冻结冒烟断言 `/legal` 非空;发布门禁仍拦未填占位符 |
| 依赖一致性 | 冻结前比对构建环境与 `requirements.txt`(`dependency_gate()`) | ✅ 缺包直接失败,不产出功能缺失的包 |
| 功能路由 | `routes_*` 模块由 `app/feature_routers.py` **单点声明**,打包时转成 `--hidden-import`,并在冻结模块表中断言其落地 | ✅ 冻结冒烟断言 `/deck`、`/flashcards`、`/my-courses`、`/images/library`、`/playground` 均非 404 |
| 语言声明 | `Info.plist` 的 `CFBundleLocalizations`(`en`、`zh-Hans`)+ 资源包内 `en.lproj` / `zh-Hans.lproj` | ✅ 缺任一语言即**构建失败**,见下文「语言与本地化」 |

## 一条命令产出可分发版本

```bash
# 0) 前置(运营者一次性操作):
#    - Apple Developer Program 会员(US$99/年)
#    - 创建 "Developer ID Application" 证书并装入钥匙串
#    - 存一个 notarytool 凭据:
#      xcrun notarytool store-credentials LUMINFEST_NOTARY \
#        --apple-id <APPLE_ID> --team-id <TEAM_ID> --password <app-specific password>

# 1) 构建环境(一次性):打包脚本用 --python 指定的解释器冻结,
#    该解释器必须满足 backend/requirements.txt,并且装有 PyInstaller:
python3 -m pip install -r harness/backend/requirements-dev.txt

# 2) 签名 + 公证打包:
python3 harness/scripts/package.py --version 1.1.9 \
  --sign-identity "Developer ID Application: <YOUR NAME> (<TEAM_ID>)" \
  --notarize --notary-profile LUMINFEST_NOTARY

# 3) 验证:
codesign --verify --deep --strict --verbose=2 "outputs/Luminest.app"
spctl assess --type execute --verbose=2 "outputs/Luminest.app"   # 期望 accepted, source=Notarized Developer ID
```

注意:`--notarize` 和 `--sandbox` 都**要求** `--sign-identity`(脚本强制;ad-hoc 公证/沙盒
会被 Apple 拒绝,所以脚本直接报错而不是产出废包)。

**Development-only template build example — not an end-user installation or public beta:**

```bash
python3 harness/scripts/package.py --version 1.1.9 --allow-template-legal
```

This explicitly records `legal_gate.ship_ready: false` and the placeholder count. It does
not waive public signing, notarization, or legal requirements. Do not pass such a build
to `release_kit.py`, rename it as a public release, or strip its non-release markers.

## 冷启动:首次启动比预热慢一个数量级

打包产物第一次被运行时,几百 MB 的 dylib 一个字节都不在 page cache 里。实测同一份
1.1.9 后端:

| 场景 | 到 `/health` 返回 `ready:true` |
|---|---|
| 全新写入后第一次启动(冷) | **~60 s** |
| 同一二进制第二次启动(热) | **~18 s** |

因此"等后端就绪"的两个超时都设为 **120 s**:`scripts/package.py` 的 smoke 门,和
`BackendLauncher.swift` 里 App 等待自带后端的那段。这两个值原先分别是 45 s 和 35 s,
而 35 s 恰好会在**最需要它成功的那一次**失败——把包交给别人,对方第一次打开必然冷启动,
于是 App 报"自带服务没能就绪",而后端其实马上就绪了。

超时是**上限**不是延迟:热启动照样在 `health()` 一应答就返回。所以调大它不会让正常启动
变慢,只是不再把冷启动判成失败。

## 硬依赖(无法替代)

1. **Developer ID Application 证书** — codesign 没有它只能 ad-hoc;ad-hoc 的 spctl 结果是
   rejected,这是 Apple 的密码学事实,不是配置问题。
2. **notarytool 凭据** — 公证必须提交给 Apple 的服务端,需要运营者的 Apple ID。

缺少这两者时的诚实产物是:当前 ad-hoc 包 + `distribution.json` 里的 notice
("Ad-hoc signed, not notarized...")。管线不会伪造一个"看起来能分发"的包。

## 公开分发门禁

没有 Developer ID Application 证书和 Apple 公证凭据，**不能生成公开发布目录**。Ad-hoc 签名的本地开发构建可以用于开发者自己的机器，但不能被 `scripts/release_kit.py` 当作可分发版本；不得清除隔离属性、建议安全设置例外，或用安装脚本绕过 Gatekeeper。法律文本、版本、后端冒烟及摘要检查同样是必要门禁，任何一个通过都不等于全部通过。

公开分发的顺序是：准备正式法律文本 → 使用明确的 Developer ID 身份签名 App → 提交 App 公证并 stapler 验证 → 签名 DMG、提交 DMG 与 ZIP 公证、验证 DMG ticket → 运行发布门禁。`scripts/release_kit.py` 会实际检查 App、DMG 和 ZIP 内 App 的签名身份、Gatekeeper 来源及公证凭据，而不是只相信 `distribution.json` 的布尔字段；缺少证书、凭据或 Apple 验证工具时拒绝发布，不会制造一个看似可安装的替代物。

```bash
python3 scripts/package.py --version <version> \
  --python "$PWD/ui-tests/.venv/bin/python" \
  --sign-identity "Developer ID Application: <name> (<team-id>)" \
  --notarize --notary-profile <keychain-profile>
python3 scripts/release_kit.py --version <version> --verify
# 只有已验证的公开下载地址才生成 Homebrew cask：
python3 scripts/release_kit.py --version <version> --verify --base-url https://example.test/releases/<version>
```

成功的 `outputs/release/<version>/` 包含版本化 DMG/ZIP、`INSTALL.txt`、`SHA256SUMS.txt`、`RELEASE.md`、`release.json`，以及提供 `--base-url` 时的 cask。没有 `install.sh`，也不使用 `--no-quarantine`。`--verify` 复验复制后的成品，**不能**跳过源文件的签名和公证检查。接收者走正常的已签名、公证的 DMG 拖放或 ZIP 解压流程；如果系统拒绝，停止分发并排查证书、公证与包完整性，而不是绕过警告。

本机源码构建是开发流程，**不是**公开发布或给测试者提供未经验证下载的替代办法。摘要可辅助核对下载完整性，但单独的 SHA-256 值不能证明发布者身份或公证状态。

## 构建记录检查（不能代替发布门禁）

以下记录能发现陈旧包、缺失知识图谱或功能路由，是公开发布检查的**必要但不充分**条件。曾有文件名看似正确、内容却是上一次构建的包。即使冒烟通过，只有上节的 Developer ID、公证与真实成品验证全部通过，才能分发。

```bash
python3 - <<'PY'
import json, pathlib
r = json.loads(pathlib.Path("outputs/.packaging/package-result.json").read_text())
print("version      :", r["version"])
print("backend smoke:", r["backend_smoke"]["passed"], r["backend_smoke"].get("checks"))
print("legal docs   :", r["backend_smoke"].get("legal_documents"))
print("graph        :", r["backend_smoke"].get("knowledge_graph"))
for name, info in r["artifacts"].items():
    print(f"{name}: {info['bytes']/1e6:.1f} MB  sha256 {info['sha256'][:16]}…")
PY
```

期望看到 `passed: True`，`checks` 含 `knowledge_graph_populated` / `media_sources_present` /
`simulations_present` / `legal_documents_present` / `feature_routers_mounted`，且
`legal_documents` 列出 `terms, privacy, ai, accessibility`。这只验证这些内容随包存在，**不**等于法律审查、签名、公证或原生交互验收。任何一项缺失都阻止分发。

同一份记录里的 `backend_smoke.feature_routes` 会逐条列出**十二个**功能路由的实际状态码:

```json
{"/deck": 200, "/flashcards": 200, "/my-courses": 200, "/images/library": 200,
 "/create/search": 405, "/playground": 200}
```

这里 **405 是正常的**——`/create/search` 只有 POST,用 GET 探它必然 405,而 405 已经证明
该模块被挂载了。**只有 404 是故障**:它意味着那个 `routes_*` 模块根本没进 bundle。

对测试者应如实说明：模型提供方缺席时使用声明的离线后备；交互活动信号需要单独同意，不能当作注意力测量；本机资料可能保存在 Application Support，**不能声称卸载 App 自动删除全部数据**。法律文本进入 bundle 只能证明文件存在，正式法律审查和占位符清理仍是独立门禁。给出反馈渠道和需要验证的原生路径；公开下载仍须先满足上节的签名和公证条件。

**给双击启动的 app 配模型(不需要终端)**:把 `HARNESS_TUTOR_*`(或 `DEEPSEEK_*` 别名)写进

```
~/Library/Application Support/Luminfest Learning Harness/tutor.env
```

权限 `600`。`BackendLauncher` 启动内置服务时读这个文件,真实环境变量优先(与
`config.load_dotenv` 对 `backend/.env` 的优先级一致)。放在 Application Support 而不是 bundle
里有两个原因:bundle 是签名的,签名后不能再往里加文件;bundle 会发给每个测试者,把计费 key
放进去等于把 key 发给所有人。只有 `HARNESS_TUTOR_*` 生效,`HARNESS_DATA_DIR`、
`HARNESS_ALLOWED_HOSTS` 这类一概忽略——一行导师配置不该能改写存储路径或网络策略。若写了
provider 却缺 URL/model/key,启动器**留在离线导师**并在 `backend.log` 写一行说明,而不是让
服务起不来:那样 app 只会显示"服务器未就绪",把读者指向错误的问题。

**直接面向 macOS 用户分发**需要 Developer ID 签名与公证（见上节）。TestFlight / Mac App Store 是另一套 Apple 分发流程，不应与直接下载的 Developer ID 门禁混为一谈。

## 运行环境:`desktop`,不是 `development`

`BackendLauncher` 给内置服务设的是 `HARNESS_ENV=desktop`,这是 `config.py` 里的第四个取值,
存在的理由只有一个:桌面包需要**production 级别的门禁**,但 `production` 会要求 PostgreSQL 和
32 位 `HARNESS_SECRET` 并拒绝启动——一个刚双击打开的应用不能"起不来"。

与 `development` 相比,桌面包改两个默认值;`media_enabled` 保持开启,因为桌面端
明确需要联网图片/视频搜索,而 `privacy.md` 已列出 Openverse、Met、Wikimedia、NASA
与 YouTube 这几条出站路径:

| 默认值 | development | desktop | 对应承诺 |
|---|---|---|---|
| `require_launch_gate` | 关 | **开** | `privacy.md` 说产品面向 13+;注册要 `age_confirmed` + `accept_terms` |
| `attention_monitor` | 开 | **关** | `privacy.md` 与设置页都说"活动信号默认关" |
| `media_enabled` | 开 | **开** | 桌面端要现场搜图/搜视频；提供方已在隐私政策披露 |

联网搜索与策展视频并存:白名单/本地图示引擎仍然优先,搜索只是补上白名单没有的概念。

两个耦合点必须一起记住,否则新加一个环境值会静默毁掉 app:

1. `require_invite` 曾与门禁共用 `gate_default`。现在拆成 `invite_default`,只有 `production`
   为真;否则 desktop 包会要求 Beta 邀请码,注册全部失败。
2. `_ensure_operator` 与"首个账号即教师"两条规则曾写死 `== 'development'`。新环境值会让
   发出去的 app **完全没有教师**,所有白板/仿真/课件工具 fail-closed。现在两者都接受
   `{'development', 'desktop'}`。

`backend/tests/test_desktop_environment.py` 钉住以上全部,包括"生产环境仍然拒绝 SQLite"。
冻结包里的实测:`desktop` + 全新数据目录下,不带声明注册返回 **422**,带声明返回 **201**、
`role: teacher`、`telemetry_consent: false`。

## 依赖:声明与冻结必须一致

`backend/requirements.txt` 是**运行时**需求,打包前 `dependency_gate()` 会逐条比对构建环境,
缺包或版本不符直接失败。原因是 PyInstaller 只收集**已安装**的东西,对"声明了但没装"完全
沉默——这正是当初一个包带着"永远只会拒绝"的上传路径和 TTS 工具发出去的原因。

`backend/requirements-optional.txt` 里的包**不**进入桌面 bundle,这是刻意的:

| 包 | 用途 | 为什么不进 bundle |
|---|---|---|
| `playwright` | 教师端 `browser_snapshot` 工具 | ~40MB 包体 + 另需下载 chromium;排除它是 DMG 从 87.8MB 降到 45.6MB 的原因。工具目录在它缺席时不再向模型宣传该工具 |
| `psycopg[binary]` | PostgreSQL 部署(`deploy/compose.yaml`) | 桌面端用 SQLite,从不打开 Postgres 连接;Dockerfile 装的是两份 requirements |

`backend/requirements-dev.txt` 是超集(运行时 + pytest + pyinstaller)。PyInstaller 也在里面,
因为**它就是构建本身**:此前任何环境都没装它,于是没人能重跑打包脚本,也就没人发现发给
测试者的文件停在上一个版本。


## 一个会静默丢掉整块功能的坑:动态 import

`main.create_app()` 用 `importlib.import_module('.' + name)` 挂载 `routes_*` 模块。这对
PyInstaller 是**不可见**的——它只跟踪能静态看到的 import。后果是:发给测试者的 bundle 里
`app.main` 在、而它挂载的路由一个都不在,`/api/v1/deck`、`/api/v1/flashcards`、
`/api/v1/my-courses`、`/api/v1/images/library` 在源码树里全部可用、在装到的 app 里全部 404。
"模块缺失就跳过"这个设计让故障既不报错、也不影响其余测试,于是一路走到了发布评审。

现在有三道锁,任何一道都会让**构建失败**,而不是产出一个功能缺失的包:

1. `app/feature_routers.py` 里的 `FEATURE_ROUTERS` 是**唯一**的路由清单;
2. `scripts/package.py` 把它转成 `--hidden-import`——这才是真正把模块放进 bundle 的动作;
3. 冻结后读取 PYZ 模块表,断言六个模块都在;随后冒烟测试实打实地请求那六个端点。

新增一个功能路由 = 在 `FEATURE_ROUTERS` 加一行 + 在 `FEATURE_ROUTE_PROBES` 加一个探针。
`backend/tests/test_feature_routers.py` 会在两者不一致、或某个模块没定义 `router`、或某条
探针路径并不属于该模块时失败。

## 仿真操场(playground):随包分发的第一方互动游戏

playground 是一套模板系统:一个 **archetype**(可复用的交互)加一份 **spec**(内容)= 一个
游戏。它和 `app/simulation_map.py` 里的第三方仿真(PhET / Gizmos,永久 `observable: false`)
相对:游戏跑在 workbench 自己的 web view 里,能上报学习者提交的答案,所以它可以作为掌握度的
证据;第三方仿真不行。

| 项 | 位置 | 说明 |
|---|---|---|
| 代码 | `backend/app/harness/playground/` | `runtime`、契约、各科 archetype 模块、`catalogue`、`pipeline`、`evidence` |
| 内容 | `media_packs/playground_games_*.json` | 6 个 pack,共 45 个游戏;`media_packs` 已在 `PACK_DATA_DIRS` 里,随 `--add-data` 进 bundle,无需额外配置 |
| 路由 | `backend/app/playground_routes.py` | API 挂在 `/api/v1/playground`;画廊页挂在 `/playground` |
| 画廊页 | `web/playground.html` | `GET /playground` 原样返回(`FileResponse`);`web/` 与 workbench 共用同一个静态目录 |

**资源目录必须走 `app/resources.py`,不能再手算深度。** `web/`、`model/`、`legal/` 三个顶层目录
原先各自写着 `Path(__file__).resolve().parents[2]`:在源码树里正确,在冻结包里**深了一层**
(PyInstaller 把包树镜像到 `_internal/` 下,少了一个 `backend/` 去抵消那一步)。后果是
装出来的 app 里 **一个 `.html` 都没有**,`/` 和 `/playground` 一律 404,而 `/api/v1/health`
依旧 200 —— 冒烟测试如果只探健康检查,就会放行一个打不开任何页面的包。

现在三个模块统一用 `resource_dir(name)`:`sys.frozen` 且 `sys._MEIPASS` 存在时返回
`_MEIPASS/<name>`,否则回落到源码树根;两个标志都在**调用时**读取,所以测试可以伪造一个
bundle 布局。`backend/tests/test_resource_paths.py` 把两种布局都钉住,并断言三个模块的答案
一致(当年就是同一段算术被抄了三份,错一起错)。

同理,`model/` 里那 4 个运行时模块打包后只剩 `.pyc`(见下节),而 `adaptation._runtime_module()`
原先写死 `__init__.py` —— 冻结包里必然 `FileNotFoundError`。现在按
`("__init__.py", "__init__.pyc")` 依次取第一个存在的;`spec_from_file_location` 对 `.py`
选 `SourceFileLoader`、对 sourceless `.pyc` 选 `SourcelessFileLoader`,一次调用同时服务两种布局。
这条路径源码树永远走不到,后端冒烟又跑在 `HARNESS_ADAPTATION=0` 下从不 import `app.adaptation`,
所以它由 `test_resource_paths.py` 里那 4 个**真的编译出 `.pyc`、真的删掉 `.py`** 的用例来钉。

**路由必须同时进两张表,缺一不可。** `playground_routes` 在 `app/feature_routers.py` 的
`FEATURE_ROUTERS` 里声明(那是唯一的路由清单:`main.create_app` 靠它挂载、`package.py` 靠它
生成 `--hidden-import`),**并且**在 `scripts/package.py` 的 `FEATURE_ROUTE_PROBES` 里有一条
探针 `("playground_routes", "/playground")`。只有前者、没有后者,就是"模块声明了却从未被冻结
冒烟验证"——正是上文那类"源码树里可用、装到的 app 里 404"的故障。冻结冒烟会实打实请求
`/playground`,404 直接让构建失败;`backend/tests/test_feature_routers.py` 保证两张表一致。

## 在浏览器里用这个 app:`/app`

`GET /app` 把**正在运行的 app 窗口**投到一个浏览器标签页里,1:1:同一个进程、同一个后端、同一个
数据库、同一节上到一半的课。浏览器是 app 的一扇窗,不是第二个前端。

**为什么是投屏而不是"web 版"。** 客户端是 SwiftUI(36 个文件、约 19,500 行),`harness/web/`
是另一套界面(仿真 workbench 在 `/`、画廊在 `/playground`),不是这个 app。所以"把 app 的前端
发给浏览器"没有文件可发;ChatGPT / WorkBuddy 那套"一份 React 前端、两个壳"的模式在这里是反过来
的。要在浏览器里看到原生窗口,只有三条路:把前端重写成 HTML(等于第二个前端,立刻会分叉)、
投屏并回传输入(**本方案**)、或者用 API 驱动 app 再重新渲染状态(那又是新界面)。

**链路。** app 自己上报窗口 frame(`WindowStream.swift`)→ 后端按该区域 `screencapture -R`
截图、`sips` 重编码成 JPEG → 浏览器每帧 `GET /api/v1/stream/frame` 画进 canvas,点击/按键
`POST /api/v1/stream/input` 经 System Events 回到 app。窗口几何由 app 自报,因为向窗口服务器
要它需要"辅助功能"权限 —— 那是输入路径才需要的权限,截图路径刻意不依赖它。

**两个一次性权限**,都由人在「系统设置 → 隐私与安全性」里按**可执行文件**授予,装不上也脚本不了:
屏幕录制(`screencapture` 出像素)、辅助功能(System Events 点击与键入)。缺哪个,`/status`
就用一句话说明,`/app` 把那句话显示在面板里,而不是给一块黑画布。

**开关 `HARNESS_STREAM_ENABLED` 默认关,任何环境(含 `desktop`)都不例外** —— 它是唯一会抓屏、
并且能往宿主里发输入的能力。关着的时候 `frame`/`window` 返回 503 并点名开关,`status` 返回
`enabled: false`,app 的上报器在第一次被拒后退避一分钟。**只有 teacher 能开**(learner 403):
在共享部署上,"宿主的屏幕"就是所有学习者的数据。后端绑 `127.0.0.1`,要给别的设备看就得改绑,
那是一次部署决定,这个功能不会自己偷偷做。

**实测**(1470×956 窗口,Retina):`screencapture` 单次 147 ms / 764 KiB;加 `sips` 1280 px @55%
= 202 ms / 142 KiB(出货档);因此上限约 **4–5 帧/秒**,真实浏览器里量到 4 fps。够读课、点击、
打字,不够放视频 —— 页面因此是限速而不是假装流畅。

`web/app.html` 与 workbench、画廊共用 `web/` 目录,`PACK_DATA_DIRS` 之外的 `WEB_DATA_DIR` 已经
把整目录 `--add-data` 进 bundle;`routes_stream` 同时进了 `FEATURE_ROUTERS` 和
`FEATURE_ROUTE_PROBES`(探针 `/stream/status`,关着时是 503,仍然算通过 —— 只有 404 才是"模块
没进包")。细节与验证方法见 `docs/web-presentation.md` 与 `scripts/probe_stream.py`。

## 源码保护(bundle 内不含可读源码)

| 内容 | 形态 |
|---|---|
| 后端(app/、harness/loop 等) | PyInstaller 冻结为字节码(PYZ 归档),无 .py |
| `model/` 运行时 4 个模块 | 打包时编译为同解释器 `.pyc`(sourceless),**源文件已删除** — `strip_runtime_sources()` |
| 第三方库(psycopg 等) | 开源库,按许可随包分发 |
| Swift UI | 编译后的 Mach-O 二进制 |

诚实边界:Python 字节码不是加密——刻意逆向(uncompyle6 等工具)理论上可以还原近似源码。
对学校/熟人 alpha 这足够;若未来要商业分发且在意这点,需要额外混淆层或换语言重写核心。

## SwiftPM 资源包(Lumi 精灵图)——一个只在构建机上能跑的坑

`Package.swift` 把 `Sources/LearningHarness/Resources` 声明成 `.process("Resources")`,SwiftPM
因此生成一个 `<包名>_LearningHarness.bundle`。这里有三条互相咬合的规则:

1. **bundle 必须被复制进 `Contents/Resources/`。** `package.py` 从 `Package.swift` 推导出
   bundle 名(`resource_bundle()`),打包后校验归档里确实有它,没有就直接失败。
2. **任何代码都不许用 `Bundle.module` 加载它。** `swift build` 生成的那个 accessor 先查
   `Bundle.main.bundleURL`(即 `.app` 目录本身,而文件在 `Contents/Resources/` 下),再查一个
   **构建机上的绝对路径**——于是它在作者的 Mac 上一切正常,在任何别人的机器上 `fatalError`。
   唯一允许的加载器是 `AppResources.url(for:withExtension:)`:依次找 `Contents/Resources`、
   bundle 根、测试 bundle,**找不到返回 nil 而不是崩**。
3. **签名之后不许再往 `.app` 里加文件。** 资源在签名前就位,顺序反了签名失效。

**验证时先把构建产物挪开。** 在本机跑"装好的 app 能不能加载精灵图"时,`.build/.../<…>.bundle`
还在,规则 2 的绝对路径回退会让测试通过、把真实故障藏起来。先 `mv` 走再验。

其他两条打包实操(与本主题无关但同样会卡住构建):

- PyInstaller 的 `--clean` 会清 `outputs/.packaging/pyinstaller-cache`(约 102 个文件),本环境的
  批量删除守卫会直接中断它 —— 先把 `pyinstaller-cache`/`dist`/`build` `mv` 到旁边再打包。
- 只改了 Swift 时用 `--skip-backend-build`(若 `source_digest` 匹配则复用上次冻结),
  与 `--skip-native-build` 是两个独立开关;两个都加 ≈ 90 秒重打包。冻结期间**不要**再改后端源码,
  否则 `source_digest` 校验失败。

### 冻结与打包之间改了后端 = 打包中止

`source_digest` 只覆盖真正被冻结的文件(`backend/desktop_entry.py`、`backend/app/**/*.py`、
`model/` 里的运行时源码)。打包在 native 构建前后各校验一次,**不一致就抛错,不产出任何产物**。
错误信息里带两个摘要的前 12 位和补救办法。

这条以前只是"记录"而不是"门":1.1.10 的 `distribution.json` 里
`source_digest=1a60e8c9…` 与 `source_digest_at_package=4967f041…` 并排存在,
打包成功、11 项 smoke 全过,而后端是 14:57:50 冻结的、树在 15:04:18 已经变了
(`harness/__init__.py`、`harness/telemetry.py`、`harness/tools_board.py` 在 15:02–15:03 被改)。
也就是说:产物里的字节没有任何源文件能产生,而唯一的证据是一个没人读的字段。
现在由 `assert_backend_matches_tree()` 拦下,`test_packaging_manifest.py` 两条用例钉住。

推论:native 构建要几分钟,足够并发编辑落地。**打包期间不要在同一个树里改后端**;
真要改,等这一轮结束再改,然后重新打包 —— 不要用 `--skip-backend-build` 绕过,
那等于把旧字节贴上新的版本号。

## 语言与本地化(English / 简体中文)

App 自带中英切换,语言在设置页里选,不跟随系统——因为同一个人的系统语言和学习语言经常不是
一个。这一节记的是**打包层**必须配合的三件事,任何一件缺失都不报错,只是静默少一半功能。

**1. `Info.plist` 必须声明语言。** `app_info_plist()` 写入三个键:

| 键 | 值 | 作用 |
|---|---|---|
| `CFBundleDevelopmentRegion` | `en` | 开发语言(SwiftPM 的 `defaultLocalization` 也是 `en`) |
| `CFBundleLocalizations` | `["en", "zh-Hans"]` | **系统设置 → 语言与地区**据此把 app 列进两种语言;缺了它,app 在代码里双语、在系统眼里单语,按 App 覆盖语言只给一种选项 |
| `CFBundleAllowMixedLocalizations` | `true` | 允许逐语言混排,而不是整包回落到开发语言 |

**2. 翻译跟着 SwiftPM 资源包走,所以必须断言它真的进去了。** `en.lproj` 与 `zh-Hans.lproj`
在 `Sources/LearningHarness/Resources/` 下,由 `.process("Resources")` 收进
`<包名>_LearningHarness.bundle`,再随资源包进入 `Contents/Resources/`。文件夹在源码树里
**不等于**它在 bundle 里——构建产物若是加翻译之前生成的,拷进去的 bundle 一个 `.lproj` 都没有。
因此 `assemble_app()` 在拷贝资源包之后立即断言两个文件夹都存在,缺哪个就用
`RuntimeError` 点名哪个,构建当场失败。理由和资源包本身一样:这个仓库已经发出过一个
签名完好、资源包却缺失、直到首次使用才崩的 app,少一门语言也该在构建时失败,而不是在用户
第一次打开时才发现。

**3. `Info.plist` 本身也在检查范围内。** `verify_portability()` 读到 `Contents/Info.plist`
时会断言 `CFBundleLocalizations` 里两种语言都在。`.lproj` 进了 bundle、plist 却在写的时候
漏掉这个键,是同一类故障的上移一层:文件都在,系统就是不知道。

**测试者数据目录不跟着改名。** 用户数据(课程、设置、TCC 授权、`tutor.env`)在
`~/Library/Application Support/Luminfest Learning Harness`,名字里仍是旧拼写 `Luminfest`。
这是刻意的:改目录名等于让每一个既有用户的学习记录、偏好和已授予的权限全部凭空消失,而且
重新签名救不回来。**显示层改名,身份层不改**——`CFBundleIdentifier`
(`com.luminfest.learningharness`)同理,理由相同。

## 已刻意保留的内部标识(改名 Luminest 时审过)

- `LuminfestBackend` — 打包内层目录/可执行名(bundle 内部路径,改名需同步 PyInstaller spec,无用户可见影响)
- `LuminfestLearningHarness*.entitlements` — 构建输入文件名
- `Luminfest.icns` — bundle 内的图标文件名(与 `CFBundleIconFile` 成对改名才会有收益,但改它要动 `make_icon()`,换不来任何用户可见差异)
- `com.luminfest.learning-harness.session` — Keychain service(改了会孤儿化已存 session)
- Application Support 数据目录 `Luminfest Learning Harness` — 改名会孤儿化既有 learner 数据
- Python 包名/模块名 — 代码内部
- 用户可见面(`CFBundleName`/`CFBundleDisplayName`、`.app` 名、DMG 卷名、归档文件名)已全部改为 Luminest;bundle id 仍是 `com.luminfest.learningharness`,理由见上节。
