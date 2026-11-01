# Tutoring Stage × TA 助教 — 设计与实施规格

状态：**P0 已实现，P1/P2 为 sequenced 路线**（本文档持续作为 SSOT）。
上游依赖：`whiteboard_playground_design.md`（白板文档模型沿用其 §3，不再重复）。

---

## 0. 结论前置

| 需求 | 方案 | 本轮状态 |
|---|---|---|
| 大屏 Stage（中央） | Studio 页中央 `StageView`，四态切换：Whiteboard / Deck / Web / Assets | ✅ 已实现 |
| 老师在白板上写/画/贴图 | tutor agent 通过 4 个 `whiteboard_*` 工具 mutate 共享板（矢量 ops） | ✅ 已实现（后端） |
| 用户也能写/画，老师看得到 | 学生 ink 走 `POST /whiteboards/{id}/ink`，服务端只接受 ink ops（fail-close），同一版本链 | ✅ 已实现 |
| 打断模式（pair-wise interrupt） | 学生「举手」事件进入 agent context（`interrupt`），tutor 下一 turn 必须先响应 | ✅ 已实现（信号灯级） |
| 基本 ASR | macOS 原生 `SFSpeechRecognizer`（on-device，免费，无 key）→ 文本进 chat | ✅ 已实现 |
| 基本 TTS | `AVSpeechSynthesizer`（tutor 回复的 🔊 按钮，设备端） | ✅ 已实现 |
| Live voice2voice / 低延迟 TTS | Gemini Live API 或 OpenAI Realtime API（WS 双向音频流） | 🔜 P2，**阻塞：需要 API key 决策**（DeepSeek 无语音） |
| Vision 模型（看屏幕/快照分析） | 独立 vision provider（qwen-vl / glm-4v / gpt-4o-mini），复用 provider.py 的 OpenAI 兼容层加 `image_url` part | 🔜 P1，**阻塞：需要 vision key** |
| PPT/视频 → browser preview | Stage 的 Web 态就是内嵌 WKWebView；`search_videos`/`find_game` 卡片「Open in Stage」直达 | ✅ 已实现（Web 态） |
| 仿真展示 | Assets 态列出 sims_store artifacts，simulation 用现有原生渲染 | ✅ 已实现（列表+链接） |
| TA 助教子代理 | 后台 agent turn（restricted toolset），异步跑，结果只进老师 feed，**永不上屏**；并发上限 5，常规 1 | ✅ 已实现（单 TA worker） |
| TA 编排（fan-out 等） | orchestrator 模式：TA dispatcher 可拆 sub-job 并行 | 🔜 P1（先跑通单 TA） |
| 不展示 chain-of-thought | TA/tutor 的 events trace 默认 `developer_mode=false` 不下发；Alpha/开发模式才开 | ✅ 已实现（沿用 AgentTurnInput.developer_mode） |

---

## 1. Stage：一个预览空间，四种形态

```
┌────────────────────────────────────────────────────────┐
│  [Whiteboard] [Deck] [Web] [Assets]        ← segmented  │
├────────────────────────────────────────────────────────┤
│                                                        │
│              STAGE  (大屏, min height 420)              │
│   Whiteboard: SVG 场景 + ink Canvas + 文本块             │
│   Deck:      NarratedDeckView 复用                      │
│   Web:       WKWebView（URL bar, teacher 可导航）        │
│   Assets:    sims_store 列表（sim/deck/白板快照）         │
│                                                        │
├────────────────────────────────────────────────────────┤
│  工具条: ✋打断 · 🎤ASR · 🔊TTS · TA dispatch            │
└────────────────────────────────────────────────────────┘
```

原则：
1. **Stage 是 preview，不是第二个 agent 输入面** —— 所有 mutate 仍走 chat → tools → 服务端 gate。
2. **切换零丢失** —— 每态持有自己的 state object，切走不销毁。
3. **老师讲课时永不"wait a minute"** —— 重活（research/asset 生成）派 TA，Stage 只显示老师点名要的东西。

## 2. Whiteboard：文档模型与边界

沿用 whiteboard 设计文档 §3：`{id, kind, version, space, layers, blocks}`。
本轮 P0 实现取舍：

- **存储**：`data_dir/whiteboards/{board_id}.json`（单文件整文档 + `version` 递增），不进 sims_store
  manifest —— 白板是工作面不是 artifact 交付物；P1 再决定是否升格为 artifact kind。
- **工具（teacher/agent-only, fail-close）**：
  - `whiteboard_read(board_id)` → 全文档（agent 可"看见"板面）
  - `whiteboard_apply(board_id, ops[])` → 矢量 ops：`path / shape / connector / text / image`
  - `whiteboard_write(board_id, text, x, y)` → text op 语法糖
  - `whiteboard_place_image(board_id, url|asset)` → 走 media gate，license 状态戳进 op
- **学生边界**：`POST /api/v1/whiteboards/{id}/ink` 只接受 `op.type == 'path'` 且 `layer='student_ink'`
  （服务端强制覆写这两个字段，客户端声明无效）；其他任何 op → 422 fail-close。
- **打断**：ink POST 带 `raise_hand: true` 时在 board doc 记 `interrupt` 事件，tutor 下一 turn 的
  system framing 里注入"学生举手了，先回应"。

## 3. TA 助教（subagent）

```
Teacher (讲课中) ──"帮我找三张细胞图 + 一段视频"──▶ POST /ta/dispatch
                                                      │
                                              ┌───────▼────────┐
                                              │ TAJob (后台线程) │
                                              │ agent turn      │
                                              │ restricted tools │
                                              └───────┬────────┘
                                       结果(资产卡片+摘要) │ 只进 teacher feed
                                              ┌───────▼────────┐
                                              │ GET /ta/results │──▶ Studio 侧栏角标
                                              └────────────────┘
```

- **restricted toolset**：research + 资产生成（search_concepts/web_search/wikipedia_summary/
  fetch_page_text/image_search/image_generate/find_game/search_videos/build_figure/
  generate_slides/write_simulation）。**没有** creation gate 之外的东西、没有 memory 写。
- **并发上限 5**（`HARNESS_TA_MAX_JOBS`），超限 429；老师 UI 常态只派 1 个。
- **永不上屏**：TA 结果只存在于 teacher feed；Stage 的任何形态都不自动切到 TA 产物。
- **CoT 不展示**：TA turn 以 `developer_mode=false` 跑，events 不下发，只有摘要 + 卡片。

## 4. 语音路线

| 阶段 | 技术 | 成本 | 状态 |
|---|---|---|---|
| 基本 ASR | SFSpeechRecognizer（on-device） | 0，无 key | ✅ |
| 基本 TTS | AVSpeechSynthesizer | 0 | ✅（现有 LessonSpeech 已有雏形，Stage 直接复用） |
| Live voice（低延迟 TTS/voice2voice） | Gemini Live API 或 OpenAI Realtime（WS） | key + 按 token 计费 | 🔜 P2，key 决策后接入：`HARNESS_LIVE_VOICE_PROVIDER` |
| Vision | OpenAI 兼容 vision provider（image_url part） | key | 🔜 P1，`HARNESS_VISION_MODEL` |

## 5. Sequenced（本轮明确不做，非遗失）

- P1-A：白板升格 sims_store artifact kind（版本回退 UI）
- P1-B：TA orchestrator（fan-out 多 TA 协作，合成 barrier）
- P1-C：vision 快照监控回环（等 key）
- P2：Live voice WS 管线（等 key）；PPT 上传→deck 转换管线
