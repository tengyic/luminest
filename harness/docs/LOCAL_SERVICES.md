# 本地服务接线说明（VoiceStudio / Chromium / 后端）

第二轮实测（2026-11-05）把三个"外部条件"变成可重复启动的本地服务。**全程没有申请 YouTube Data API key，也没有向任何搜索服务付费**：视频与网页发现都走本机已安装的 headless Chromium。

---

## 1. 一条命令

```bash
cd "/Users/tengyi/WorkBuddy AI/2026-10-10-18-14-50/harness"
scripts/start_local_services.sh --serve
```

`--serve` 会：检查/安装声明依赖 → 确认 Chromium 二进制 → 确认或启动 VoiceStudio → 用一组显式环境变量启动 FastAPI（默认 `:8877`）。
不带 `--serve` 只做检查，不启后端。要换解释器用 `PYTHON=/path/to/python scripts/start_local_services.sh`。
VoiceStudio 缺失是**软失败**（打 warning 但退出码仍为 0）：TTS 会诚实返回 503，而 Chromium 的网页/视频发现不受影响。

只保活 VoiceStudio：

```bash
python3 scripts/ensure_voicestudio.py --json
python3 scripts/ensure_voicestudio.py --no-launch   # 只探测，不开 app
```

---

## 2. 三个服务分别是什么

| 服务 | 位置 | 谁来启动 | 判据 |
| --- | --- | --- | --- |
| **VoiceStudio TTS** | `/Applications/VoiceStudio.app` 自带 Python backend，uvicorn 监听 `127.0.0.1:3900` | `ensure_voicestudio.py` 用 `open -a VoiceStudio` | `GET /v1/models` 返回模型列表 |
| **headless Chromium** | Playwright 1.62 + `~/Library/Caches/ms-playwright/chromium-*` | 后端按需 `launch()`，用完即关 | `chromium_search.available()` |
| **Luminfest backend** | `backend/desktop_entry.py` | `--serve` | `GET /health` → `ready: true` |

VoiceStudio 的 API 契约（OpenAI 兼容，无需 key）：

```
POST http://127.0.0.1:3900/v1/audio/speech
  {"model":"omnivoice","input":"...","voice":"default",
   "response_format":"mp3","speed":1.0}
  -> 200 audio/mpeg
GET  /v1/models        -> tts-1, tts-1-hd, gpt-4o-mini-tts, whisper-1, omnivoice, ...
GET  /v1/audio/voices  -> alloy, ash, ballad, ...
```

Luminfest 的 `app/harness/voice.py` 用 `httpx.Client(trust_env=False)` 直连 loopback，**不走代理**；`ensure_voicestudio.py` 的探测同样用无代理 opener。这是刻意的：本机 `HTTP_PROXY` 会把 3900 的失败伪装成 `502 Bad Gateway / upstream connect failed`。

---

## 3. 环境变量

| 变量 | 默认（`from_env()`） | 作用 |
| --- | --- | --- |
| `HARNESS_VOICE_ENABLED` | `1`（development/test/desktop），production `0` | 是否允许合成语音。与 `media_enabled` 是两件事：TTS 是 loopback，不外发文本 |
| `HARNESS_VOICE_BASE_URL` | `http://127.0.0.1:3900` | VoiceStudio 端口；不是 3900 时改这里，不用改代码 |
| `HARNESS_MEDIA_ENABLED` | `1`（development/test） | 是否允许联网取媒体/搜索 |
| `HARNESS_CHROMIUM_SEARCH` | `1` | 允许 Playwright/Chromium 作为搜索与视频发现 provider。设 `0` 则回落到 `ddgs` |
| `HARNESS_VIDEO_AUTO_CURATE` | `1` | allowlist 无该 concept 时，按需跑教师策展 |
| `HARNESS_YOUTUBE_API_KEY` | 空 | **可选**。填了会用 Data API v3 的 `status.embeddable` 做权威校验；不填用免 key oEmbed，功能不缺 |

三个新开关同时要求 `media_enabled=True` 才会真正联网，所以打包版（media 默认关）不会因为默认 `1` 就突然发起外部请求。

---

## 4. 验证命令与实测输出

```bash
B=http://127.0.0.1:8877/api/v1
TOK=$(curl -s -X POST $B/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"smoke@example.com","password":"..."}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
```

**TTS**

```bash
curl --noproxy '*' -X POST $B/voice/speak -H "Authorization: Bearer $TOK" \
  -H 'Content-Type: application/json' -d '{"text":"Fractions are parts of a whole."}' \
  -o /tmp/speak.mp3 -w '%{http_code} %{size_download} %{content_type}\n'
# 200 33068 audio/mpeg
# file: Audio file with ID3 version 2.4.0, MPEG ADTS layer III, 128 kbps, 24 kHz
```

**能力矩阵**

```bash
curl -s $B/capabilities | python3 -c '...'
# audio_tts   ready=True  VoiceStudio is answering at http://127.0.0.1:3900.
# web_search  ready=True  A headless Chromium search provider is ready (Bing / YouTube).
```

**视频（首次会现场策展，约 25–30 s；之后 0.05 s）**

```bash
curl -s "$B/media/video?concept_id=fractions" -H "Authorization: Bearer $TOK"
# data.videos[0] = Khan Academy "Intro to equivalent fractions"
#                  video_id N1X0vf5PUz4 · iframe_embed · oembed_iframe_present
curl -s "$B/media/video?concept_id=ratios" -H "Authorization: Bearer $TOK"
# Math with Mr. J "Introduction to Ratios" · xA435umOQuw
```

（`ratios` 的首次结果是 `xA435umOQuw`；后续 `--force` 重策展可能换成同主题、同样通过全部闸门的另一支视频，属预期行为。）

策展结果写在 `data_dir/media/video_allowlist.json`（与人工编辑同一文件，幂等）；失败记在 `video_curation_attempts.json`，24 h 内不重试。`--force` 重策展若选出**不同的**视频会**替换**该 concept 的旧行，不会累积多行——`video.resolve()` 会把同一 concept 的所有行都返回给课程，重复行等于一次给学生推两支视频。替换只在新视频写入成功后执行，失败时旧卡片原样保留。

**web_search**（工具层，非公开 REST 路由）

```python
from app.config import Settings
from app.harness import tools_creation
r = tools_creation.web_search(
    types.SimpleNamespace(settings=Settings.from_env(), role='teacher'),
    'fractions explained for kids', 4).to_dict()
# ok=True, results=4, notes[-1]='Search provider: chromium.'
#   Fraction Calculator / Fractions - Math is Fun / Math Monks  -> link_only
#   Fraction - Wikipedia                                      -> ingestible
```

`link_only` 不是失败：单一下游授权闸 `app/ingest.policy` 决定哪些域名可引用正文。Chromium 只负责**发现**，不改变授权结论。

---

## 5. 实现位置

| 文件 | 作用 |
| --- | --- |
| `backend/app/harness/chromium_search.py` | Playwright 封装：Bing 结果解码 `/ck/a?u=a1<base64url>`、YouTube 结果页 HTML、代理/直连双路径、失败显式抛错 |
| `backend/app/harness/ddg_provider.py` | `ChromiumDDGS`（DDGS 形状的 `.text()`）+ `resolve(settings)` 优先级决策 |
| `backend/app/harness/video_search.py` | keyless 链优先 Chromium；`site:youtube.com` 直达 YouTube 页；原有 httpx 路径保留为 fallback |
| `backend/app/harness/toolbox.py` | `find_video` 按需策展 + 24 h 负缓存 |
| `backend/app/config.py` | 三个新字段与 `HARNESS_*` 读取 |
| `backend/app/capabilities.py` | `provider_ready` 认 Chromium |
| `scripts/ensure_voicestudio.py` | VoiceStudio 幂等保活 |
| `scripts/start_local_services.sh` | 一键检查 + 启动 |
| `scripts/populate_video_allowlist.py` | 批量预热整门课；`--force` 重策展采用替换语义 |

新增测试：`tests/test_chromium_provider.py`、`tests/test_voice_bridge.py`、`tests/test_video_auto_curate.py`、`tests/test_video_warmup_replace.py`，全部离线可跑（无网络、无真实浏览器）。

---

## 6. 排障

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `3900` 返回 `502 upstream connect failed` | 请求被本机 `HTTP_PROXY` 接管，不是 VoiceStudio 的状态 | 用 `curl --noproxy '*'`，或让脚本自己探测（它已无代理） |
| `/voice/speak` 仍 503 | VoiceStudio app 退出了（实测它会中途退出，3900 不再监听） | `python3 scripts/ensure_voicestudio.py --json` 会 `open -a` 拉起并轮询到 ready（实测 40.7 s 恢复）；必要时设 `HARNESS_VOICE_BASE_URL` 指到实际端口 |
| `web_search` 说 `not configured` | 既无 `ddgs` 也无可用 Chromium | `pip install playwright==1.62.0 && playwright install chromium`；或 `HARNESS_CHROMIUM_SEARCH=0` 后装 `ddgs==9.16.0` |
| `/media/video` 一直空 | 首次策展没找到满足四道闸的候选 | 看返回 `notes` 里的具体原因；24 h 后自动重试，或删 `data_dir/media/video_curation_attempts.json` 立即重试 |
| 第一次请求慢 25–30 s | 启动 Chromium + 多个查询 + 每个候选 oEmbed 校验 | 正常。命中 allowlist 后是 0.05 s；用 `scripts/populate_video_allowlist.py --all` 一次预热整门课，`<concept> --force` 重策展单个概念 |
| Chromium 抓不到结果 | 网络只允许走代理 | 模块自动先试 `HTTPS_PROXY`、失败再直连；两块都失败会把尝试日志原样抛给调用方 |

---

## 7. 开机自启（可选）

VoiceStudio 是普通 macOS app，把它加进「系统设置 → 通用 → 登录项与扩展」即可；或者在自己的 LaunchAgent 里先跑 `ensure_voicestudio.py`、再跑 `start_local_services.sh --serve`。脚本本身不写登录项、不改系统设置。

---

## 8. 明确没有做的事

- **没有申请或配置 YouTube Data API key。** 用户账号登录 Google Cloud 属于外部动作，而且 Chromium + oEmbed 已经把能力补齐，配 key 只会带来配额和账单。若将来需要权威 `status.embeddable`，填 `HARNESS_YOUTUBE_API_KEY` 即可，代码路径已存在。
- **没有用 GUI computer use。** 浏览器驱动走 headless Playwright，不占用用户屏幕、不需要辅助功能权限。
- **没有改动打包/签名状态。** `distribution.json`、法律文本、PhET 授权仍是独立的 release gate，见 `docs/READINESS_ASSESSMENT.md` 第 5 节。
