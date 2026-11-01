# Luminfest — macOS 分发与签名指南

状态(2026-10-25):打包管线完整;当前产物为 **ad-hoc 签名**。要产出 Gatekeeper 直接放行的
公开分发包,缺的是**两件事,不是一件**:运营者的 **Apple Developer 账号凭据**(签名 + 公证),
以及**法律文本的 59 处占位符填完**(`backend/legal/FILL_IN_SHEET.md`)。前者无法用任何技术手段
绕过或替代,也不应伪造(见下文硬依赖);后者不是技术问题,是法务事实,`package.py` 的
`legal_gate` 会**拒绝**打包未填完的发布版,所以它同样是发布前的硬门槛。

两个门槛都只在**发布**时生效。给具名内测者用 `--allow-template-legal` 打包是被允许的,但那样
产出的包文件名会带 `-ALPHA-TEMPLATE-LEGAL`,且 bundle 内 `Contents/Resources/NOT_RELEASABLE.txt`
会写明它不可发布——因为"这是内测包"如果只记在 `.packaging/` 里,拿到文件的人看不到。

## 打包产物里已就位的东西

| 项 | 位置 | 状态 |
|---|---|---|
| Privacy manifest | `Contents/Resources/PrivacyInfo.xcprivacy`(无条件复制) | ✅ 随每次打包进入 bundle |
| Entitlements | `LuminfestLearningHarness-Direct.entitlements`(直发,hardened runtime)或 `-Sandbox`(Mac App Store) | ✅ 签名时施加 |
| 签名顺序 | 内层 Mach-O 自底向上 → bundle(禁用 `--deep`) | ✅ `sign_bundle()` |
| 公证 | `notarytool submit --wait` + `stapler staple/validate`,DMG 与 zip 双产物 | ✅ `notarize()` |
| distribution.json | 记录 signing/sandboxed/notarized/notice | ✅ 每包自带 |
| 课程/媒体 pack | `--add-data` 进 bundle(`PACK_DATA_DIRS`) | ✅ 冻结冒烟断言图谱非空、媒体与仿真路由可用 |
| 法律文本草稿 | `backend/legal/` 以 `--add-data` 进 bundle(`LEGAL_DATA_DIR`) | ✅ 冻结冒烟断言 `/legal` 非空;发布门禁仍拦未填占位符 |
| 依赖一致性 | 冻结前比对构建环境与 `requirements.txt`(`dependency_gate()`) | ✅ 缺包直接失败,不产出功能缺失的包 |
| 功能路由 | `routes_*` 模块由 `app/feature_routers.py` **单点声明**,打包时转成 `--hidden-import`,并在冻结模块表中断言其落地 | ✅ 冻结冒烟断言 `/deck`、`/flashcards`、`/my-courses`、`/images/library`、`/playground` 均非 404 |

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
codesign --verify --deep --strict --verbose=2 "outputs/Luminfest.app"
spctl assess --type execute --verbose=2 "outputs/Luminfest.app"   # 期望 accepted, source=Notarized Developer ID
```

注意:`--notarize` 和 `--sandbox` 都**要求** `--sign-identity`(脚本强制;ad-hoc 公证/沙盒
会被 Apple 拒绝,所以脚本直接报错而不是产出废包)。

**Alpha / 内测构建**用同一命令但不签名,并显式接受"法律文本仍是草稿"这件事:

```bash
python3 harness/scripts/package.py --version 1.1.9 --allow-template-legal
```

`--allow-template-legal` 会在记录里写下 `legal_gate.ship_ready: false` 和占位符数量,所以
"这是模板构建"是记录在案的,不是靠人记住。**不要**对公开发布使用这个开关。

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

## 没有 Apple Developer 账号怎么发布

先把边界说清楚,因为这里最容易被"找个开关关掉 Gatekeeper"这种答案带偏。

**做不到的事。** `spctl` 对一个 ad-hoc 签名、带 quarantine 标记的 app 一律 `rejected`。这是
Apple 的密码学判断,不是配置项:没有 Developer ID 证书就无法生成 Apple 认可的签名链,没有
Apple ID 就无法提交公证。任何声称"改个 plist / 加个 entitlements 就过"的说法都是错的,而且
在 macOS 15 之后连"右键→打开"这条老路都基本失效了。

**做得到的事。** Gatekeeper 拦的不是"这个 app",是"这个**下载来的**文件":它的判据是
`com.apple.quarantine` 这个扩展属性,而那是下载器写上去的元数据,**不是签名的一部分**。安装器
在把 bundle 拷进 `/Applications` 之后清掉这个属性,用户就再也看不到那个对话框——系统设置里
"仍要打开"按钮做的是同一件事,只是手动、且藏在两层菜单下面。

所以"没有开发者账号怎么发"的真实答案不是绕过 Gatekeeper,而是**让用户不必自己面对它**:
把清理动作放进一个可读、可验证的安装器里。

### 三条路径,按用户摩擦从低到高

| 路径 | 用户要做什么 | 前提 |
|---|---|---|
| Homebrew cask | `brew install --cask --no-quarantine luminfest` | 需要一个公开 URL 放 DMG |
| 安装脚本 | 双击/`sh install.sh`,或把 DMG 交给它 | 无,离线可用 |
| 手动 | 拖进应用程序 + 一条 `xattr` 命令 | 无,离线可用 |

三条路径都由 `scripts/release_kit.py` 一次产出,见下节。

### 一次产出一个可发布的目录

```bash
python3 scripts/package.py --version 1.1.16 \
  --python "$PWD/ui-tests/.venv/bin/python"

python3 scripts/release_kit.py --version 1.1.16 --verify
# 有公开下载地址时,再生成 Homebrew cask:
python3 scripts/release_kit.py --version 1.1.16 --verify --base-url https://example.test/v1.1.16
```

产物在 `outputs/release/<version>/`:

| 文件 | 作用 |
|---|---|
| `Luminfest-<version>-arm64.dmg` | 版本化命名,与 zip 同源 |
| `Luminfest-<version>-arm64.zip` | 网盘/微信传输用,比 DMG 更耐中转 |
| `install.sh` | 挂载、拷贝、清 quarantine、校验签名 |
| `INSTALL.txt` | 三条路径的人话说明,含失败时怎么办 |
| `SHA256SUMS.txt` | DMG / zip / install.sh 三个摘要 |
| `RELEASE.md` | 这一版是什么、怎么装、签名状态 |
| `luminfest.rb` | Homebrew cask(仅 `--base-url` 时生成) |
| `release.json` | 机器可读的发布记录 |

`release_kit.py` **拒绝**从"构建记录说自己不可发布"的产物组装发布目录,四种情况会直接退出:
`legal_gate.ship_ready` 为假、版本号与包不符、后端冒烟没过、DMG/zip 的 sha256 与记录不一致。
这不是礼貌性检查——1.1.10 曾经把旧字节贴上过新版本号,而当时唯一的证据是一个没人读的字段。

`--verify` 做的事:把 DMG 复制到临时目录、**真的打上 quarantine 标记**、用 `install.sh` 装到
一个临时 `INSTALL_DIR`,然后断言 (1) 安装成功、(2) quarantine 属性已消失、(3) `codesign
--verify --strict` 通过。也就是说它验证的不是"脚本存在",而是"用户那条路真的通"。

### `$99` 到底买到什么

买了之后仍然要做的:建 Developer ID 证书、`notarytool store-credentials`、打包时加
`--sign-identity` 与 `--notarize`(管线里已有,见上文)。

买到的**只有一件事**:用户下载后双击即开,没有任何对话框。它买到的是"零摩擦",不是"能运行"。
如果分发范围是自己 + 几位同学,为这一件事付年费不划算;如果要挂到公开站点让陌生人下载,
它就是必须的——不是因为法律要求,而是因为绝大多数人在看到"无法验证开发者"时不会读完说明,
他们直接删掉。

还有一条与钱无关的路径:把源码交给对方,让他在本机 `swift build` + 打包。本机构建出来的 app
不带 quarantine 标记,所以 Gatekeeper 不拦。这条路径的代价是对方要有 Xcode 和 Python 环境,
只适合开发者本人。

### 一个必须随包说清楚的事实

ad-hoc 签名意味着**签名不绑定任何身份**。所以"这个包是不是我发的"无法用签名回答,只能用
`SHA256SUMS.txt` 回答。发布时请把摘要贴在你发布它的那个地方(README、群公告、网盘说明),
否则中间人替换一个包,接收方没有任何办法分辨。

## Alpha 测试分发(无 Developer ID 也能发)

适用:小范围熟人测试。产物是 ad-hoc 签名的 zip/DMG,测试者首次打开需手动过一次 Gatekeeper。

**发给测试者的东西**:`outputs/Luminfest-arm64.zip`(比 DMG 更适合网盘/微信传输;DMG 与 zip
由同一条命令同时写出,只有其中一个新鲜就说明构建中途失败,**不要发**)。要求:Apple
Silicon Mac、macOS 14+。**不需要发任何源码**——bundle 内不含可读项目源码(见下节),后端是
PyInstaller 字节码冻结、UI 是编译后的二进制。

> ⚠️ **发之前先核对本次构建记录,不要凭文件名和记忆。** 这里出过一次事故:本文档长期写着
> "约 44MB",而磁盘上那个 `Luminfest-arm64.zip` 是**上一次**构建——87.8MB、知识图谱为空、
> pack 数据全无,修复后的包就安静地放在它旁边。文件名不随版本变化,所以唯一可靠的判据是
> 构建记录本身:

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

期望看到 `passed: True`、`checks` 含 `knowledge_graph_populated` / `media_sources_present` /
`simulations_present` / `legal_documents_present` / `feature_routers_mounted`,且
`legal_documents` 列出 `terms, privacy, ai, accessibility`。任何一项缺失都说明这个包不该发出去。

同一份记录里的 `backend_smoke.feature_routes` 会逐条列出**十二个**功能路由的实际状态码:

```json
{"/deck": 200, "/flashcards": 200, "/my-courses": 200, "/images/library": 200,
 "/create/search": 405, "/playground": 200}
```

这里 **405 是正常的**——`/create/search` 只有 POST,用 GET 探它必然 405,而 405 已经证明
该模块被挂载了。**只有 404 是故障**:它意味着那个 `routes_*` 模块根本没进 bundle。

**测试者首次打开步骤**(随包附一段话即可):

```bash
# 解压后,把 Luminfest.app 拖进「应用程序」,然后:
xattr -cr /Applications/Luminfest.app
open /Applications/Luminfest.app
```

说明:未公证的 app 首次启动会被 Gatekeeper 拦("无法验证开发者"),上面第一条命令移除
隔离属性即可(只需一次)。macOS 15+ 的"右键打开"对未签名包已基本失效,直接给 xattr 命令。
图形界面方式:系统设置 → 隐私与安全性 → 底部"仍要打开"。

**Alpha 阶段建议随包附带的说明**:
- 这是 pre-alpha 内测版,法律文本仍是草稿(见 `backend/legal/FILL_IN_SHEET.md`)。草稿现在
  **已随包进入 bundle**,App 内可读、`GET /api/v1/legal` 可列出,不再是空白——但正式发布前
  仍必须把占位符填完并让打包门禁放行;
- 数据全部本地存储,卸载即删。注意"默认关"这句话在 1.1.9 及更早的包里**是假的**:
  那时 `HARNESS_ENV=development`,而 `config.py` 在 development 下 `media_default='1'`,
  于是 `HARNESS_ATTENTION_MONITOR` 与 `HARNESS_MEDIA_ENABLED` **都默认开**,与
  `legal/privacy.md` 的"off by default"直接冲突。1.1.10 起 bundle 用 `HARNESS_ENV=desktop`,
  两者默认关、启动门禁(13+ 与条款)默认开,这句话才成立。改动前先看 `config.py`
  里 `media_default`/`gate_default`/`invite_default` 三个默认值,不要凭这段说明推断;
- 无模型 API key 时,导师由**确定性离线导师**作答(读课程、你自己的作答记录与课程图,带引用),
  不是空回复;配上 `HARNESS_TUTOR_*` 后自动改用模型;
- 反馈渠道 + 你希望测试者重点看的路径(今天页 / 知识图谱 / 设置页)。

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

**升级到"双击即开"的唯一路径**:Developer ID 签名 + 公证(见上节)。TestFlight /
App Store Connect 上传同样要求先过这一步,alpha 阶段没有绕开它的意义。

## 运行环境:`desktop`,不是 `development`

`BackendLauncher` 给内置服务设的是 `HARNESS_ENV=desktop`,这是 `config.py` 里的第四个取值,
存在的理由只有一个:桌面包需要**production 级别的门禁**,但 `production` 会要求 PostgreSQL 和
32 位 `HARNESS_SECRET` 并拒绝启动——一个刚双击打开的应用不能"起不来"。

与 `development` 相比只有三个默认值不同,每一个都对应一条对外承诺:

| 默认值 | development | desktop | 对应承诺 |
|---|---|---|---|
| `require_launch_gate` | 关 | **开** | `privacy.md` 说产品面向 13+;注册要 `age_confirmed` + `accept_terms` |
| `attention_monitor` | 开 | **关** | `privacy.md` 与设置页都说"活动信号默认关" |
| `media_enabled` | 开 | **关** | 外发请求(Openverse/Met/Wikimedia/NASA)不在隐私政策的子处理者表里 |

策展视频与图示不受影响——它们来自白名单与本地图示引擎,不是搜索。

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

## 已刻意保留的内部标识(改名 Luminfest 时审过)

- `LuminfestBackend` — 打包内层目录/可执行名(bundle 内部路径,改名需同步 PyInstaller spec,无用户可见影响)
- `LuminfestLearningHarness*.entitlements` — 构建输入文件名
- `com.luminfest.learning-harness.session` — Keychain service(改了会孤儿化已存 session)
- Application Support 数据目录 `Luminfest Learning Harness` — 改名会孤儿化既有 learner 数据
- Python 包名/模块名 — 代码内部
- 用户可见面(窗口标题、邮件文案、UA、bundle id `com.luminfest.learningharness`、App 名/DMG 名)已全部改为 Luminfest。
