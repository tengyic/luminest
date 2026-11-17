# 2026-11-15 交付判定（技术 / 产品就绪度）

**判定范围**：代码、架构、端到端可运行性、数据与多用户、测量数据采集、分发包。  
**明确排除**：法律合同、商业计划、定价、授权与许可条款。本文不对这些下任何结论；  
签名/公证与法律文本占位符仅作为"发布闸门未清"的事实列出，不展开法务判断。

---

## 0. 结论前置

| 对象               | 判定                                                                                         |
| ---------------- | ------------------------------------------------------------------------------------------ |
| **Closed Alpha** | **技术封版成立**。一门真实课程（AP Psychology）从注册到分析报表全程跑通，47/47 端到端 HTTP 检查通过，含六项"不许假通过"的强断言。           |
| **Closed Beta**  | **具备条件，未验收**。代码与配置层齐备，但对外服务链路（TLS + PostgreSQL + 邀请码 + 远程语音网关）没有做端到端实测；冻结二进制刻意只绑 loopback。 |
| **可交付物**         | 72 MB 一键启动包 + 安装说明 + 进度分析报告 + GitHub 推送，均已产出并实测。                                           |

不给"全绿"的说法：能力登记册仍有 16 项 `partial`、2 项 `external`，见 §5。  
公开站点已上线（sharecode 门禁，下载另需兑换 token），但**外部用户的实际交付链路仍未验收**，
见 §6。

---

## 1. 证据链（全部可复现）

| 证据                    | 结果                                               | 复现                                                                                                                                   |
| --------------------- | ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------ |
| Closed-Alpha E2E gate | **47/47**                                        | `python3 scripts/alpha_e2e_gate.py --base http://127.0.0.1:<port> --course ap_psychology`                                            |
| 后端全量测试                | **2451 passed / 0 failed / 2 skipped**（19m33s）   | `cd backend && env -u PYTHONPATH -u NODE_OPTIONS .venv/bin/python -m pytest -q --basetemp=.pytest-basetemp-XXXX -p no:cacheprovider` |
| 冻结后端 smoke            | **11/11**                                        | `python3 scripts/package.py --backend-only --allow-template-legal`                                                                   |
| 分发包一键启动               | `ready=true` / schema 11 / 53 tools / 静态页 200    | `cd Luminfest-Server && ./start.sh`                                                                                                  |
| 交叉账号隔离                | 跨账号 deck → 404                                   | gate 内 `cross-account deck is refused`                                                                                               |
| 实时 ASR                | stream WebSocket，~1.6–2.4 s（原批量约 20 s）           | gate 内 `LIVE ASR`                                                                                                                    |
| 实时 TTS                | 100–214 KB 可播放 MP3                               | gate 内 `TTS clip renders to a playable asset`                                                                                        |
| 教师工具编排                | `stage_surface` + `whiteboard_write` 均 `ok=True` | gate 内 `TEACHER ORCHESTRATES A TOOL`                                                                                                 |
| 教材带图                  | 随包 CC BY-SA 4.0 图带署名离线装配到 block 1                | gate 内 `shipped textbook photograph attaches offline`                                                                                |

机器可读证据：`outputs/alpha_e2e_evidence.json`、`outputs/test_suite_2026-11-15.json`。  
`outputs/` 按仓库规则不入库，因此上面的测试数字直接写在本文里，clone 后不依赖磁盘上的证据文件即可核对结论。

---

## 2. 今天修掉的四处真实缺陷（不是"接线声明"）

1. **Ollama 工具调用走错端点**：`chat_tools` 用裸 `/chat/completions` 打 Ollama，本地模型因此完全没有工具能力。改为 `…/v1/chat/completions`（已带 `/v1` 时不重复），并加回归测试。实测模型随后真的派发了 `whiteboard_write`。
2. **测量冷测预算 500**：`_cold_decision` 把 `episodes.label_attempts` 返回的 dict 当 ORM 行读 `row.question_id`，第一个有答题记录的用户就让 `/measurement/probe/next` 崩掉。改为 `.get()` 并加回归测试。
3. **工具标识符未被服务端绑定**：1.5B 模型会把 schema 示例（`board_id_example`）或自己编的短 id（`lesson_1`）填进 `board_id`，白板工具正确地拒绝，但表现为"白板坏了"。在 `toolbox.invoke` 这一唯一闸口，用白板层自己的 ID 校验器判定不可解析的地址，替换成 live lesson 的真实 ID；真实显式 ID 一律不动，替换会写进 tool result 的 notes 以便审计。9 项回归测试。
4. **课时图片不走随包图库**：`fetch_for_lesson` 直接联网搜索，对已有随包许可图的物理概念也报 `no_images`。改为先用 `photograph_for_concept` 装配一张随包图填概念槽，其余槽仍走正常许可搜索；2 项回归测试。

另外修了 gate 自身的三处假通过：源文本只有 1 段导致 422、TTS 把 MP3 字节响应当 JSON 状态读、以及"HTTP 200 就算教师编排成功"。现在 gate 会拒绝"答案是兜底文本""没派发工具""ASR 走了批量回退"。

**一处测试环境加固（不是产品缺陷，但必须讲清楚）**：修复后首次全量复跑在 99% 处出现 5 个失败，全部集中在 `tests/test_web_telemetry_helper.py`，错误都是 WorkBuddy sandbox broker 的 `Error: execution capability 已过期`。这些用例通过 `subprocess` 拉起 Node，继承了宿主的 `NODE_OPTIONS=--require …/node-language-shim.cjs`，而 broker 的执行凭据在 16 分钟长跑中过期。判定依据不是"看着像环境问题"：该模块单独跑 **7/7 通过**，`env -u NODE_OPTIONS` 下也是 **7/7 通过**，且断言内容完全没动。修法是让 `_probe()` 从子进程环境剥离 `NODE_OPTIONS`——一个纯 `node -e` 探针不该继承宿主的 JS 预加载。随后在两套 shim 都排除的条件下重跑全量套件，结果见 §1。这个改动只涉及测试文件，不影响已冻结的分发后端，zip 与 sha256 保持不变。

另外同步了 `capabilities.py` 的品牌常量（`Luminfest` → `Luminest`）与 beta cohort 字段，修掉第一遍全量套件里 3 个纯断言漂移；`test_capabilities.py` 单独复跑 23/23。两次全量复跑的失败数（3 → 5 → 0）因此都有明确归因，没有靠"重跑一次就绿了"糊过去。

---

## 3. 用户点名能力逐条判定

| 能力                                                                      | 判定            | 说明                                                                                                                     |
| ----------------------------------------------------------------------- | ------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Live voice ASR + TTS（VoiceStudio）                                       | ✅             | PCM 流式 WebSocket ASR + 异步渲染 TTS，真实 MP3                                                                                 |
| Teacher system rebuild                                                  | ✅             | 编译式 lesson plan / teaching procedure / Socratic gate；角色服务端每次重算                                                         |
| Whiteboard calling + teacher live use                                   | ✅             | 真派发两步工具并都成功；surface 决策边界生效                                                                                             |
| PPT real creation                                                       | ✅             | 真 OOXML `.pptx` 导出，deck lint 六条规则                                                                                      |
| Image finding + textbook with images                                    | ✅             | 随包许可图离线装配、带署名；无图时返回命名原因而非静默                                                                                            |
| Real-time teaching / AP Psychology end-to-end                           | ✅             | 21 门课、141 概念全带 lesson；诊断→计划→授课→评分→分析                                                                                   |
| Browser use                                                             | ⚠️            | `browser_snapshot` 已注册，但窗口流 `STREAM-01` 仍 partial，浏览器开关默认关                                                             |
| 教师 agent 决定 what / when                                                 | ✅             | 53 工具注册表、surface 决策边界、服务端绑定真实标识符                                                                                       |
| Course creation / skill creation / planning / diagnostic / quiz grading | ✅             | 源文本建课并落库、blueprint dry-run、签名 receipt 评分、gradebook                                                                     |
| Progress & analytics                                                    | ✅             | `PROGRESS_ANALYTICS.html`，数字从证据文件生成                                                                                    |
| Mindmap / flashcards 媒体                                                 | ✅（管线）/ ⚠️（呈现） | 课内图片链路已修；思维导图仍渲染 SVG 树、单词卡仍是文本卡，二者本身不内嵌照片                                                                              |
| 数据库处理 / 多用户验证                                                           | ✅             | schema 11、SQLite 默认、PostgreSQL 可切、双账号隔离实测                                                                              |
| 基于学习基准的数据采集                                                             | ✅             | `docs/MEASUREMENT.md`（Soderström & Bjork 2015 / Bastani 2024 / Kestin 2025）；report / cold probe / estimator bench 三个端点 |
| 模型配置 / live voice API                                                   | ✅             | `/settings/model-config` 热更新；Ollama 与 OpenAI 双线                                                                        |
| 允许 beta 客户连服务端                                                          | ⚠️            | `beta_control/` + `webapp/` 已落地，生产链路未端到端验收                                                                             |

---

## 4. 数据与多用户

- 默认 SQLite（`data/`），schema 11；`HARNESS_DATABASE_URL` 可切 PostgreSQL。
- 每个账号的课程、答题、记忆、板书、课件按 `user_id` 隔离；跨账号 deck 实测返回 404。
- `HARNESS_ENV=production` 强制 PostgreSQL、≥32 字符 secret、显式 allowed hosts、HTTPS 模型地址，并默认关闭外联媒体与语音（需显式开）。
- 测量数据采集是**条件化**的：记录答题时的援助条件，不把练习正确率当作"学习"。
- `beta_control` 的采集端点 fail-closed：live token + 显式 `consent: true` + 字段白名单，否则不落库。

---

## 5. 未验收能力（不因主链路跑通而改标）

来自 `docs/feature_verification_register.json`：65 项中 **47 implemented / 16 partial / 2 external**。
（2026-11-17 补了 4 项 v12/v13 能力：项目评分、模型生成的声明式交互、四维概念图、BKT 模型注册表；
四项都按"后端已实现、原生面无读者"如实标为 `partial`，没有为了好看标 implemented。）

**关键 partial**：`TUTOR-04` 双工语音（OpenAI Realtime，本轮实现的是 VoiceStudio ASR+TTS 轮次，不是全双工）、`TUTOR-05` 教师档案/克隆、`STREAM-01` 浏览器窗口流、`AUTH-05` 邮箱验证与密码重置、`ASSESS-04` 对齐标准的单元成绩簿、`PROJECT-02/03/04` 项目式学习、`DATA-04` 缓存媒体删除。  
**external**：`PRIV-05` 数据最小化与租户隔离、`A11Y-01` 本地化/主题/无障碍。

发布闸门（与代码质量无关，仍未清）：Developer ID 签名、Apple 公证、法律文本占位符。 

---

## 6. Closed Beta 的确切门槛

已具备：模型配置层、beta 邀请码控制服务、浏览器 Web 客户端、反向代理 `/api/v1`、多用户隔离、测量采集、一键启动包。

**尚未验证**（因此不能宣布 Beta 就绪）：

1. 冻结二进制的 `desktop_entry.py` 只绑 `127.0.0.1`。对外服务必须使用源码部署路径  
   （`deploy/compose.yaml` + `uvicorn app.main:create_app --factory`），该路径本轮**没有**用  
   TLS + PostgreSQL + 邀请码跑过完整链路。
2. VoiceStudio 是本机回环服务。服务端部署需要独立的实时语音方案，或把语音能力留在客户端本地；  
   这个拓扑尚未定义并验证。
3. 全双工语音（OpenAI Realtime）仍需外部 key 与端到端实测。
4. **公开站点已上线，但下载仍需兑换 token**（本条 2026-11-17 更正）。此前的判定说"没有公开
   链接"，依据是 2026-11-15 三次 `SITES_APP_NOT_FOUND` 失败。该阻塞已于 2026-11-16 由新会话
   发布解决，本次实测（2026-11-17，独立 `curl`）：

   | 探测 | 结果 |
   | --- | --- |
   | `GET /`（无 sharecode） | **403**，3174 B |
   | `GET /?sharecode=<code>` | **200**，77 282 B，`<title>Luminest — closed beta</title>` |
   | `GET /api/health` | **200**，`{"status":"ok","version":"1.4.0-beta.1"}` |
   | `GET /app/`、`/agreement.html`、`/download-manifest.json`、`/api/updates/manifest.json` | **200 / 200 / 200 / 200** |
   | `GET /downloads/Luminest-arm64.dmg?sharecode=…` | **403**，`A valid beta share code is required to download the build` |
   | `GET https://luminest.app.workbuddy.host/`（vanity 域名） | **404**，旧应用已删除 |

   站点：`https://wbapp-i2nxsckskaquxjurlmkfnp.app.workbuddy.host/`（sharecode 由运营线下分发，
   **本文不打印该码**：这是 closed-beta 的门禁，写进公开仓库等于拆掉门禁；上面探测用的码由
   操作者在本地注入）。
   所以准确的表述是：**落地页与 beta 控制面（config / updates manifest / collect schema）已对外
   可用，下载受 token 门禁**——`downloads/*` 读的是兑换后的 `token` 参数（
   `beta_control/server.py:592-599`），不是页面 sharecode；邀请码需线下分发。vanity 域名未恢复。
   仍不可说的是"Beta 已交付给外部用户"：没有对外账号激活、没有远端学习后端，冻结二进制仍只绑
   loopback。

---

## 7. 分发包

`outputs/closed-beta-2026-11-15/Luminfest-Server-2026-11-15.zip`（72 MB，sha256 见同目录  
`sha256.txt`）。内含冻结后端、`start.sh`、`INSTALL.md`、`VERSION.txt`。  
一键启动已实测：`ready=true`、schema 11、53 工具、静态工作台 200。

---

## 8. 复现命令（最短路径）

```sh
cd harness/backend
env -u PYTHONPATH HARNESS_ENV=development HARNESS_DATA_DIR=/tmp/lf-verify \
  HARNESS_TUTOR_PROVIDER=ollama HARNESS_TUTOR_URL=http://127.0.0.1:11434 \
  HARNESS_TUTOR_MODEL=qwen2.5:1.5b HARNESS_VOICE_BASE_URL=http://127.0.0.1:3900 \
  python3 -m uvicorn app.main:create_app --factory --port 8796

cd ..
python3 scripts/alpha_e2e_gate.py --base http://127.0.0.1:8796 --course ap_psychology
python3 scripts/build_progress_report.py --tests-json outputs/test_suite_2026-11-15.json
```

前提：VoiceStudio 0.5.6 在 `:3900`，Ollama 在 `:11434`。缺模型时生成类功能会明确拒绝，不会伪造内容。
