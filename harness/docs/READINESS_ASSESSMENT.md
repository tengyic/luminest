# Luminfest Learning Harness — 可用性判定（实测版）

判定时间：2026-11-05 · 判定对象：本仓库源码 + 本机实跑的后端（`desktop_entry.py --port 8877`，`HARNESS_DATA_DIR=/tmp/lf-smoke`）

**2026-11-05 追加（第二轮实测）**：用户要求把三个外部依赖真正接通。本机 `/Applications/VoiceStudio.app` 已启动（自带 uvicorn 监听 127.0.0.1:3900），`/voice/speak` 现在返回真 MP3；`web_search` 与视频发现改用**已安装的 headless Chromium**（Bing SERP + YouTube results page），不再依赖 `ddgs` 或 YouTube API key；`/media/video` 加了按需策展，实测为 `fractions` 与 `ratios` 各策展出 1 个经 oEmbed 验证、可 iframe 嵌入的真实视频。详见 `docs/LOCAL_SERVICES.md`。

本文所有结论都有命令或返回值作证据。没有跑通的地方直接写"不工作"，不做"应该可以"的推断。

---

## 2026-11-11 更正（本文其余部分是 11-05 的历史快照，不要当现状读）

这份文档写于 2026-11-05，此后发布分支增加了 14 门课程、约 500 个测试、模型配置层与白板 `tex` 渲染器。下面三处数字已经过期，**读之前先看这里**：

| 本文说法 | 2026-11-11 实测 |
|---|---|
| 后端套件 1813 passed / 1 failed / 2 skipped | 该数字出自一个从未提交的工作树，任何提交都复现不出来。发布分支 `ab8bcda` 实测 **2291 collected → 2286 passed / 3 failed / 2 skipped**；那 3 个失败已于同日修复（陈旧的 concept id、14 条指向不存在课时的策展视频行、一个把哨兵当成兜底的错误谓词）。`main` (`bbbe2e4`) 为 **1835 / 1 / 2**，唯一的失败是本机 venv 版本漂移（`test_packaging_manifest`），与 `main` 的代码无关 |
| "唯一失败是已修成确定性断言的既有墙钟 flake" | 那个 flake 确实已修（`test_stream.py` 17 passed）。但 11-05 的"1 failed"不是它，而是现在仍存在于 `main` 的 pin 漂移；两个失败被混为一谈 |
| "LLM 导师默认 `offline`" | `offline` 已被 `config.py` 删除，传它会直接 `ValueError`。现在是"未配置"状态：`development`/`desktop` 照常启动并声明 `model-required`，`production` 拒绝启动 |

当前口径以仓库根 `README.md` 的 Testing evidence 表与 `docs/evidence/` 下的日期化证据为准；每行都标明覆盖范围、commit 与复现命令。本文件其余内容作为 11-05 的历史记录保留，不再更新。

---

## 0. 一句话结论

**一句话结论：核心学习闭环能用；"教师调用工具产课件 → PPT → quiz/单词卡 → 等级反馈"这条线是真的。第二轮实测已把之前缺的三个外部条件全部接通：本机 VoiceStudio 出真 MP3、Chromium 驱动 web_search 出真结果、Chromium 现场策展让 `/media/video` 出真视频——**全程没有申请任何 YouTube API key**。仍待外部输入的是双向语音的 OpenAI Realtime key 与在线 LLM 导师。发布层面仍不可公开分发——签名、公证、法律文本三条 release gate 未清，与代码质量无关。**

| 维度 | 状态 |
| --- | --- |
| 后端可启动、可注册登录、可写入 | ✅ 实测通过 |
| 51 个工具注册、107 条 API 路由 | ✅ 实测枚举 |
| 课件生成（从粘贴文本/文件/链接） | ✅ 实测产出 6 概念 / 24 题 |
| PPTX 导出 | ✅ 实测 48,780 字节真 OOXML，8 页 |
| 单词卡 / quiz | ✅ 实测生成 4 张带 provenance 的卡 |
| 互动仿真 | ✅ 内置 sim 可渲染 + 桥接注入；参数化仿真 API 可返回 |
| 点击遥测 | ✅ 原生 + Web 工作台双覆盖（都要用户显式同意） |
| 级别外显（CEFR/年级） | ✅ API 与 UI 都有；但**需要 ≥5 道校准题**才有数值 |
| 语音输出（TTS） | ✅ **第二轮接通**：本机 VoiceStudio 0.5.6 @ 3900，`/voice/speak` → 200 + 33,068 字节真 MP3 |
| 实时双向语音 | ⚠️ 代码与 UI 齐备，**仍需 OpenAI Realtime key**（Keychain 配置卡片已就位） |
| 网络视频 | ✅ **第二轮接通**：Chromium 现场策展 + oEmbed 验证，`/media/video` 出可嵌入真视频 |
| web_search | ✅ **第二轮接通**：headless Chromium 走 Bing，`provider_ready: true`，4 个真结果 |
| LLM 导师 | ⚠️ 默认 `offline`；`HARNESS_TUTOR_PROVIDER` 被故意留空 |
| 找图片 | ✅ 联网搜到 35 个候选，全被质量/许可闸拒并写明理由（换 query 即出图） |
| 后端测试套件 | **（2026-11-05 当时）** 1785 passed / 0 failed / 5 skipped（第一轮）；第二轮 v5 为 1813 passed / 1 failed / 2 skipped，唯一失败是已修成确定性断言的既有墙钟 flake，见 §4 —— **两个数字都已过期，见文首 2026-11-11 更正** |

---

## 1. 九个能力逐条核验

### 1.1 教师能否调用工具做课件 — ✅ 能

工具箱是显式注册表，不是散落的 if：`app/harness/toolbox.py` 里 `_register(ToolSpec(...))` 共 **51 个**，`/health` 也自报 `tools: 51, moves: 9`。与课件直接相关的工具：

`author_course` · `draft_course` · `extend_course` · `read_course_blueprint` · `illustrate_course` · `attach_lesson_image` · `course_images` · `compose_content` · `prepare_case_study` · `build_figure`

实测（`POST /api/v1/create/preview`，粘贴 1384 字符、5 段文本）：

```
concepts 6 · questions 24
  - Solving Linear Equations / A linear equation / The Distributive Property
  - Special Cases of Linear Equations / Linear Inequalities / The solution
```

`POST /api/v1/create/course` 返回 `201`，落库为 `mine_af6f8d4447`。

**但要注意它诚实的方式**：返回体里 `honesty` 明写

> "No language model was used. The same source always produces the same course."

也就是说离线路径是**确定性抽取**（概念 + 原文引用 + 规则前置序），不是 LLM 生成。它会拒绝而不是编：

| 你喂什么 | 它怎么答 |
| --- | --- |
| 419 字符 / 74 词 | 拒：需要 ≥400 字符且 ≥80 词，附实际计数 |
| 单段长文 | 拒：需要 ≥2 段落，"一段文字没有内部结构可建前置序" |
| 3 个概念 | 拒：需要 ≥4 概念，"少于 4 个无法做四选项带原文干扰项" |

---

### 1.2 制作 PPT — ✅ 能，且是可编辑 deck 不是截图

链路：`GET /api/v1/deck/from-concept/{concept_id}` → `GET /api/v1/deck/{deck_id}/export.pptx`

实测 `fractions`：

```
deck id = deck-e2111540f7bc · slides = 8
export: http 200 · 48780 bytes · application/vnd.openxmlformats-officedocument.presentationml.presentation
file:   Microsoft OOXML
zip:    71 entries · ppt/slides/slide1..slide8.xml
```

配套还有完整 deck 编辑 API（`routes_deck.py` 20 条路由）：加/删/改/移动/复制 slide、加/改/删 element、`import`（上传 .pptx 变可编辑文档）、逐页 SVG 预览、deck 图片增删。

---

### 1.3 语音沟通 — ✅ 服务端 TTS 已接通 / ⚠️ 双向语音待 key

| 路径 | 第一轮 | 第二轮实测 |
| --- | --- | --- |
| 服务端 TTS `POST /api/v1/voice/speak` | **503** | **200 · 43,820 / 33,068 字节 · `audio/mpeg` · MPEG Layer III 24 kHz** |
| 实时双向语音（原生 `VoiceRealtime`） | 未连 | 代码 / UI / 权限齐备，仍需 OpenAI Realtime key |

第一轮把"缺软件"判错了。本机实际有：

```
/Applications/VoiceStudio.app        # Electron 0.5.6, com.voicestudio.desktop
Contents/Resources/backend/          # 自带 Python backend + /v1/audio/speech
~/Library/Application Support/VoiceStudio/runtime/project/.venv/bin/python \
    -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 3900

GET  /v1/models        -> tts-1, tts-1-hd, gpt-4o-mini-tts, whisper-1, omnivoice, ...
POST /v1/audio/speech  -> 200, audio/mpeg
```

**根因是 app 没启动，不是没装。** 3900 上那个 502 来自本机 `HTTP_PROXY`（"upstream connect failed: Connection refused"）；Luminfest 的 `voice.py` 用 `trust_env=False` 直连，所以 app 一开就通。

第二轮新增 `scripts/ensure_voicestudio.py`：无代理探测 `/v1/models` → 未通则 `open -a VoiceStudio` → 轮询到 ready → 输出 JSON。实测 `{"ready": true, "action": "already running", "models": [...10]}`。`scripts/start_local_services.sh` 把依赖检查、Chromium、VoiceStudio 串成一条幂等命令。

原生端（第一轮已补齐并 `swift build` 通过）：

- `VoiceRealtime.swift` — 直连 `wss://api.openai.com/v1/realtime`，24 kHz PCM16 上下行，server-VAD 打断（`speech_started → response.cancel`）
- `RealtimeKey.swift` — key 存 Keychain（`kSecAttrAccessibleWhenUnlockedThisDeviceOnly`），不进 plist、不进 git
- Stage 页 "Voice chat" 按钮；Settings 页 "Duplex voice (OpenAI Realtime)" 卡片（SecureField + 保存/清除）
- `package_app.sh` 已写 `NSMicrophoneUsageDescription` / `NSSpeechRecognitionUsageDescription`；Direct 版 entitlements 已加 `com.apple.security.device.audio-input`
- 旧的 push-to-talk（`SFSpeechRecognizer` + TTS）保留，双向通话连上时自动禁用，两条路不抢麦

**结论**：服务端朗读现在真能用，且不需要联网、不消耗任何 key（文本只到本机 loopback）。双向语音仍缺一个 OpenAI Realtime key，两路不抢麦。

---

### 1.4 查网络视频 / 网络教材 — ✅ 第二轮接通（Chromium，无需 API key）

| 工具/路由 | 第一轮 | 第二轮实测 |
| --- | --- | --- |
| `web_search` | `provider_ready: false`（缺 ddgs） | **`provider_ready: true`** — "A headless Chromium search provider is ready (Bing / YouTube)"；实测 4 个真结果，Wikipedia 判 `ingestible`、其余 `link_only` |
| `GET /api/v1/media/video` | `videos: []` | **videos: 1** — `fractions` → Khan Academy "Intro to equivalent fractions"（`N1X0vf5PUz4`，`iframe_embed`，`oembed_iframe_present`）；`ratios` → Math with Mr. J（`xA435umOQuw`） |
| `HARNESS_YOUTUBE_API_KEY` | 以为是必需 | **不需要**：Chromium 渲染 YouTube results page，解析 `ytInitialData` 得 id/title/channel/duration，再用免 key oEmbed 验证可嵌入性 |

实现要点：

- `app/harness/chromium_search.py` — headless Chromium（Playwright 1.62；本机 Chromium 1234/1248 已装）抓 Bing SERP 与 YouTube 结果页。Bing 的 `/ck/a?u=a1<base64url>` 跳转在**授权闸之前**解码成真实 hostname，否则每条结果都会被误判为未审计的 `bing.com`。
- `app/harness/ddg_provider.py` — 新增 DDGS 形状的 `ChromiumDDGS.text()` 与 `resolve(settings)`。浏览器可用时优先；`ddgs` 作为不含 playwright 的打包版 fallback；两者皆无仍诚实拒绝，不伪造结果。
- `app/harness/video_search.py` — keyless 链首位 `_youtube_page_search` 内部优先用 Chromium，失败回落原 httpx；`site:youtube.com` 查询直达 YouTube 结果页（Bing 常忽略 `site:` 运算符）。
- `app/harness/toolbox.py` `find_video` — allowlist 无该 concept 时**按需**跑教师策展（标题相关性 / 邻课排除 / 可信频道 / oEmbed 四道闸），写入同一 allowlist；失败记 24h 负缓存，避免每次开浏览器。首次 ~25–30 s，之后命中 allowlist **0.05 s**。
- `fetch_page_text` `wikipedia_summary` / `search_material` `fetch_material_text` / `POST /api/v1/create/search` 保持原有实现与单一授权闸。

一份诚实的边界：`ingest/policy.py` 是唯一入口，`cc_by_nc_*` 默认拒——这不是 bug 是设计。Chromium 只负责**发现**，采不采用、能不能引用正文仍由原有闸门决定。

---

### 1.5 找图片 — ✅ 联网管线实测通了（闸门工作在真实数据上）

`GET /api/v1/media/images?concept_id=fractions` → `200`：

```
providers: openverse, wikimedia, met, nasa        enabled: true
licences_cached: cc0, cc_by, cc_by_sa, public_domain
licences_refused: cc_by_nc, cc_by_nc_...
assets: []      ← 缓存为空
```

`POST /api/v1/images/fetch {"query":"fraction pie chart","concept_id":"fractions"}` → `200`：

```json
{"outcome":"no_cleared_candidate","seen":35,"accepted":0,
 "rejections":[{"source":"openverse","title":"PieChartFraction …","why":"Too narrow for a lesson (500px < 800px)."}, …]}
```

**这不是失败，是闸门在真数据上工作**：真的去 Openverse 搜了 35 个候选，逐个按尺寸/宽高比/许可证判，不合格的写明理由。要拿到图，把 query 换成更适合教材的（或放宽 `min_width`/`min_height`）。

工具层：`find_image`（清权后才下载）、`image_search`、`image_generate`、`look_at_image`（视觉理解）、`/api/v1/images/paste`（剪贴板图，不冒称许可证）。

---

### 1.6 小游戏 / 互动 — ✅ 能

三层，从轻到重：

1. **参数化仿真**（符号引擎，非 LLM）：`GET /api/v1/simulations/fractions` → `200`
   `kind: fraction_bar`，`engine: symbolic`，带可调参数（`n: 1..4` 整数步进）。
   `honesty`：`no model inference is involved`。
2. **完整 HTML 仿真工件**：`/api/v1/sims` 全生命周期 —— 创建走 `sims_store.validate_html`（空文档、外链脚本直接拒 + 报问题清单），版本化（`v1, v2...`，改一次存一版），`frame-token` 后 `raw` 渲染。
   实测 11,451 字节的内置 "Supply & Demand" 仿真：SVG + `data-series="demand|supply|equilibrium"` 约定，父页面 hover-to-select，客户端脚本（`luminfest-agent.js`，4,265 字节）由服务端注入。
3. **白板 / 画板**：`whiteboard_*`（4 个工具）、`board_*`（3 个工具）+ `/api/v1/boards/*`，含 `diagram/trace`（lasso 抓取的 body 上限 17 MB）。

---

### 1.7 实时监测点击"整个 Harness app" — ✅ 原生 + Web 都覆盖，且要用户同意

**通了的部分**：事件通道 + 汇总都实测通过。

```
PATCH /api/v1/me  {"telemetry_consent": true}   → True
POST  /api/v1/events  interaction/click/stage.tab.deck  → {"accepted":1}
POST  /api/v1/events  click + "window":"Chrome - Bank"  → 422 "An interaction may not carry window."
GET   /api/v1/attention/window
      interaction_count: 1 · active 0.53s · idle 0.53s
      reading.state: "unclear"  evidence: "Too little interaction to read..."
```

`app/harness/telemetry.py` 的语法是封闭的：`KINDS = click|tap|key|blur|focus`，`FIELDS = kind|target`，`key` **只记按了一次，不记按了哪个键**，`window` 字段被显式拒（"窗口标题就是文件名/URL/邮件主题"）。并且 `EVIDENCE = False`——点击永不计入学习证据。

**没通的部分**：

| 端 | 覆盖 |
| --- | --- |
| macOS 原生 SwiftUI（Stage / Studio / Settings / Deck…） | ✅ `ClickTelemetry.swift`：`NSEvent` 本地监听 `leftMouseDown/rightMouseDown/keyDown`，无需辅助功能权限；每 5 s 或 40 条批上报；按 consent 与 focus/blur 自动 arm/disarm |
| Web 工作台（`web/app.js`） | ✅ 本次补齐：`web/telemetry.js` + 侧栏同意开关 |

Web 侧的实现（本次新增）：

- `web/telemetry.js` —— 纯函数模块（`sanitizeTarget` / `targetFor` / `isSensitive` / `createQueue`），目标名走服务端同一套文法 `^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$`，超长截到 64、非法字符折叠成 `-`；`input[type=password|email]` 与 `data-private="1"` 一律不命名。
- `app.js` —— 捕获阶段监听 `pointerdown` / `keydown`，`window` 的 `blur` / `focus` 不带 target（文法本来就不允许）；每 5 s 或 40 条 flush 到 `POST /events`；`/events` 返回 403 时自动 disarm，不重试。
- 侧栏 "Share interaction telemetry" 复选框 —— `PATCH /api/v1/me {telemetry_consent}`，勾选状态以服务端返回为准。
- 实测：`POST /events` 收到 3 条（click + key + blur）→ `{"accepted":3}`，`/attention/window` 回 `interaction_count: 2, blur_events: 1`（blur 单独计数，符合语义）。
- 新增测试 `tests/test_web_telemetry_helper.py` 7 passed。

`app/harness/telemetry.py` 的语法是封闭的：`KINDS = click|tap|key|blur|focus`，`FIELDS = kind|target`，`key` **只记按了一次，不记按了哪个键**，`window` 字段被显式拒（"窗口标题就是文件名/URL/邮件主题"）。并且 `EVIDENCE = False`——点击永不计入学习证据。

**仍未覆盖**：iframe 里的仿真画布是 cross-origin sandbox（`sandbox="allow-scripts"` 无 `allow-same-origin`），父页面收不到那里的 pointer 事件。仿真自身的交互走 `luminfest:select` / `luminfest:hover` 桥接消息，若要入遥测需在桥接处再记一笔——目前没接。

**为什么这不是 bug**：`/events` 对未同意用户直接 `403 Telemetry requires explicit consent`，同意开关在 `/me`。默认关闭是对的。

---

### 1.8 生成 quiz / 单词卡 — ✅ 能

`POST /api/v1/flashcards/generate {"concept_id":"fractions","count":4}` 实测产出 4 张，`GET /api/v1/flashcards` 回读 `count: 4`：

| front | back |
| --- | --- |
| In "Compute 1/2 + 1/4…", the answer "1/3" is wrong. What error does it represent? | The choice adds denominators as though units could be combined… |
| What is Fractions and equivalent quantities? | A fraction describes equal parts of a whole… |
| Fill the blank: A fraction \_\_\_\_ equal parts of a whole. | describes |

关键细节：`source` 是**必填**。`create_card` 里

```python
if not flashcards.source_exists(payload.source):
    raise HTTPException(422, 'A card needs provenance: source must name a real '
                             'curriculum block, question or concept.')
```

卡片表 `flashcards` 有 `due_at` 索引 + FSRS 调度，`/session` 出今日到期，`/review` 记评分，`/export` 出 json/csv，`/import` 吃回。quiz 走 `check_understanding`（一次一道检索题）+ 课件生成时的 24 道四选项题。

---

### 1.9 知道学习者是什么级别 — ✅ 有，但只在测过之后

`GET /api/v1/ability` 实测（0 题账号）：

```json
{"theta":0.0,"se":0.9996,"n_calibrated":0,"n_uncalibrated":0,
 "level":{"known":false,"label":"Not yet measured","n_items":0,"needed":5,
          "cefr":null,"grade":null,
          "note":"A level appears after 5 calibrated questions; you have answered 0. Showing one now would describe the starting assumption, not you.",
          "not_certified":true}}
```

这是我最认可的一处设计：**没数据就不编等级**。后端 `app/harness/leveling.py` 提供 `cefr_from_theta` / `grade_from_theta` / `level_summary` / `describe`，原生 `LevelCard` 在 Studio 页拉这个接口，随 `store.analytics` 刷新。

同时 `/health` 自报：`model_status.trained: false`，`commercial_ready: false`，`"mastery prior is not calibrated"`。**别对外宣称"已验证的自适应数学模型"。**

---

## 2. 上一轮审计的 5 个 P0/P1：现状

| 审计项 | 现状 | 证据 |
| --- | --- | --- |
| **P0** iframe 不携带 bearer → 生产 401 | ✅ 已修：`POST /api/v1/sims/{id}/frame-token` 换 120 s、单仿真作用域、只读的 HMAC 令牌，`frame.src` 带 `?frame_token=`；**不把长生命周期 bearer 放进 URL** | 无凭证读 `raw` 在生产态 401；跨仿真复用 401；改一个签名字符 401；过期 401（新增 7 个测试全绿） |
| **P1** TA 图片卡 `const` 重赋值崩溃 | ✅ 已修：合并逻辑抽成 `web/cards.js` 纯函数 `mergeCachedSha`，`app.js` 改调用；原循环已删 | `for (const item of payload.cards` 在 `app.js` 中已不存在；7 个 node 侧回归测试覆盖"有缓存 sha / 无 sha / 空 payload / 不改原数组" |
| **P1** Course Studio 宣称支持 https 链接但没实现 | ✅ 已修：`index.html` 加 `#studio-url`，`app.js` 走 URL 分支；后端 `SourceInput{text|url}` 本就支持 | 实测 `create/preview` 两条入参都能走；`_default_url_fetch` 加了 DNS/私网地址校验与逐跳重定向校验 |
| **P1** 教师/学生模式只是本地 UI 开关 | ✅ 已修：`GET /api/v1/role` + `principal()` 从 `users.role` 判角色，`app.js` 拉 `/me` 后按服务端角色启用/禁用；`server_role()` fail-closed（只有 `teacher` 走教师路径） | 学生声明 `role: teacher` 仍按学生处理（已有测试覆盖） |
| **P1** 未验证真实 LLM 导师 | ⚠️ 未变（这是产品决策） | `/health` `tutor.provider: offline`，`generation_mode: grounded-offline` |
| **P2** 离线仿真不完整 | ⚠️ 未变 | — |
| **P2** 仅 Apple Silicon / macOS 14+ | ⚠️ 未变（打包元数据） | — |

---

## 3. 我这次额外发现的两个问题（审计没提）

### 3.1 Plus 付费墙没有接线

`app/capabilities.py:755` 定义了 `require_capability(id)`，docstring 写"一行接一个路由"。全仓库检索：

```
Depends(require_capability    → 只命中 capabilities.py 自己的 docstring 示例
```

**零条路由接线。** 后果是这样自相矛盾的一组实测：

| `/api/v1/capabilities` 说 | 实际路由表现 |
| --- | --- |
| `course_creation: withheld · "part of Luminfest Plus"` | `POST /create/course` → **201**，成功建课 |
| `images: withheld · "part of Luminfest Plus"` | `GET /media/images` → **200**，管线正常 |

方向上是"对你有利"的（免费全能用），但意味着：① 对外文档/定价与代码行为不一致；② 想做订阅收款时，闸门得先接上。这属于产品决策，我没有擅自把闸门接上——接上等于砍掉你现在能用的功能。

### 3.2 Web 工作台的客户端遥测（本次已补）

原状：`web/app.js` 里 `grep "interaction|heartbeat|/events"` 只命中一行注释，Web 端一条遥测都不发，`/attention/window` 只能看见 macOS 客户端。

现在：`web/telemetry.js`（纯函数，可 node 直测）+ `app.js` 接线 + 侧栏同意开关，实测 3 条事件落库、blur 单独计数。剩余未覆盖点是 iframe 内的 canvas 交互（cross-origin sandbox，父页面收不到 pointer 事件），要补就接到 `luminfest:select` 桥接消息上。

---

## 4. 测试与构建（这次真跑了）

| 项目 | 结果 |
| --- | --- |
| 第一轮全套 pytest（系统 python3.14，缺两个已声明依赖） | 1753 passed / 11 failed / 5 skipped |
| 那 11 个失败 | 全部同一个根因：环境缺 `python-multipart==0.0.22`、`ddgs==9.16.0`（两者都在 `requirements.txt` 里声明），装进隔离 venv 后全绿 |
| 装齐依赖后整套重跑（含第一轮新增 21 个测试） | **1785 passed / 0 failed / 5 skipped** |
| 第二轮全套 pytest（v5：+26 个 Chromium/语音/策展测试） | 1813 passed / **1 failed** / 2 skipped（51m45s） |
| 那 1 个失败 | `tests/test_stream.py::test_the_event_budget_bounds_a_held_key`：限流用 `time.monotonic()` 的滑动 1 s 窗口，30 次调用在整机被 Chromium 拖慢时跨过秒边界，旧时间戳过期 → 30 个全放行（期望 25）。**既有墙钟 flake，与本轮改动无关**；单独重跑 `1 passed`。已改为 monkeypatch `screen.time` 冻结时钟 + 显式推进验证预算恢复，只改测试不动生产限流逻辑；`test_stream.py` **17 passed** |
| 第二轮新增测试 | `test_chromium_provider.py` / `test_voice_bridge.py` / `test_video_auto_curate.py` / `test_video_warmup_replace.py` —— **29 passed**，全部离线（无网络、无真实浏览器） |
| 原生 Swift | `SWIFT_DISABLE_SANDBOX=1 swift build --disable-sandbox` → **Build complete, exit 0**（本机环境嵌套 sandbox 会拒 SwiftPM 自带的 sandbox，必须显式关） |
| 后端启动 | `scripts/start_local_services.sh --serve` → `/health` `ready: true` |

一个环境坑记一下：`pytest` 默认 tmpdir 在本机会被 `mkdir` broker 拦成 `FileExistsError`，必须 `--basetemp=<已存在目录>`。另外 `test_playground.py::test_every_game_survives_a_headless_click_and_drag` 会为每个小游戏起一次无头浏览器，是整套里最慢的一段；并发跑 Chromium 时全套会拖到 50 分钟。

---

## 5. 要用起来，还差什么（按你问的顺序）

| 你想要的 | 现在 | 补齐动作 |
| --- | --- | --- |
| 做课件 | ✅ 可用（离线确定性） | 想让它"懂教材"而非"抽句子"，才需要开 LLM 导师 |
| 做 PPT | ✅ 可用 | 无 |
| 语音沟通 | ✅ 服务端朗读可用 / ⚠️ 双向语音待 key | 跑 `scripts/start_local_services.sh --serve`；双向语音在 Settings 填 Realtime key |
| 查网络视频/教材 | ✅ 可用（Chromium） | 无；`ddgs` 与 YouTube API key 都不再是前置条件 |
| 找图片 | ✅ | 联网搜到 35 个候选但全被质量/许可闸拒；换个 query 或放宽尺寸阈值即可出图 |
| 小游戏/互动 | ✅ 可用 | 无 |
| 监测点击 | ✅ 可用（原生 + Web），需在侧栏勾选同意 | 仅剩 iframe 内 canvas 的 pointer 事件未入账 |
| quiz/单词卡 | ✅ 可用 | 无 |
| 知道级别 | ✅ 架构对 | 答够 5 道校准题才有数；先别声称"已验证自适应模型" |

**能公开分发吗？** 不能，和这份代码无关：`distribution.json` 自报 ad-hoc 签名、未公证；`legal/FILL_IN_SHEET.md` 仍是 "ALL UNFILLED — DO NOT SHIP"；PhET 素材 CC BY-NC 商用需单独授权。这三条是 release gate，不是 bug。
