# Whiteboard × Vibecode Playground — 交互与能力设计规格

状态：**设计规格（未实现）**。基于 2026-10-11 的真实代码事实写成，所有"已存在"的引用都可回查到文件与符号。

---

## 0. 结论前置

| 问题 | 答案 |
|---|---|
| playground 与 whiteboard 怎么交付交互？ | **两个 surface，一个 artifact store**。白板是第 3 种 artifact kind（`whiteboard`），与 simulation/deck 走同一存储、同一版本链、同一 SSE agent 流；客户端在 `turn_end` 后拉新版本刷新画布。 |
| agent 能在白板上画吗？ | **能，且必须是矢量 ops，不是像素笔刷**。agent 发结构化 scene-graph patch（path/shape/connector），客户端渲染 SVG。可版本化、可编辑、license 干净、token 便宜。 |
| agent 能搜索并贴相关图/diagram 吗？ | **能**。复用已有 `image_search` / `find_image` / `image_generate` / `build_figure`；"贴"= 服务端下载入 store 缓存 + license 状态标记，**绝不外链热链**（`validate_html` 本来就禁外部资源）。diagram 优先语义化（mermaid→SVG 或 nodes/edges 块），位图是 fallback。 |
| agent 能在白板上写字吗？ | **能**。text block，可 anchor 到任意图形/笔画；数据层永远是文本（可搜索可翻译），"手写感"只是渲染字体选择。 |
| vibe-coded software 的类型怎么用？ | 见 §5 分类表：`simulation` / `deck` / `whiteboard` / `figure` / `quiz`，各自生成工具、交互方式、validator 约束。 |

---

## 1. 现状（代码事实，2026-10-11）

- **Playground 已存在**：`harness/web/` workbench —— AI 生成的单文件 HTML artifact 跑在
  `<iframe sandbox="allow-scripts allow-same-origin">`，hover-to-select，
  selection payload `{kind, selector, text, rect}` 发给 `POST /api/v1/agent/stream`（SSE）。
- **Artifact store**：`backend/app/harness/sims_store.py`，`KINDS = ('simulation', 'deck')`，
  `v{n}.html` + `index.json` manifest，全版本可回退，`validate_html` 是可服务性的唯一权威
  （禁外部资源、禁 fetch、禁 eval / new Function）。
- **Agent 工具面**（`toolbox.py` 注册）：`write_simulation` / `edit_simulation` / `generate_slides`
  / `image_search` / `web_search` / `image_generate`(Pollinations) / `find_image` / `find_video`
  / `find_simulation` / `build_figure` / `build_presentation` / `text_to_speech`
  / `run_in_workspace` / `write_workspace_file` / `read_workspace_file`。
- **边界 gate**：`creation_gate.py` —— `STUDENT_CATEGORIES = ('bug','wrong_info','ugly','ux')`，
  `TEACHER_CATEGORIES = ('create','restructure')`；role 来自服务端 account，fail-close。
- **媒体语义**：卡片状态 `ready / withheld(withheld_reason) / link_only / verified_embed`；
  所有外部源走 `app/ingest/policy.py` 的 audited list，fail-close。
- **不存在的东西**：白板 surface、freeform 绘图/写字/贴图工具、白板 artifact kind。

---

## 2. 总体架构：两个 surface，一个 store

```
┌────────────────────────────┐      ┌────────────────────────────┐
│  Playground (sim canvas)   │      │  Whiteboard (freeform)     │
│  iframe sandbox            │      │  SVG scene, 无 sandbox     │
│  hover→select→explain/req  │      │  画/写/贴/连 sim 卡片       │
└─────────────┬──────────────┘      └─────────────┬──────────────┘
              │ selection payload                  │ board intent (block_id / region)
              ▼                                    ▼
        ┌──────────────────────────────────────────────┐
        │   POST /api/v1/agent/stream  (SSE, 不变)      │
        │   body.context: {sim_id | board_id, role,     │
        │                  selection | board_anchor}    │
        └──────────────────┬───────────────────────────┘
                           ▼ agent loop → tools
        ┌──────────────────────────────────────────────┐
        │  sims_store (kind: simulation|deck|whiteboard)│
        │  + media store (图片缓存, license 状态)        │
        └──────────────────────────────────────────────┘
```

设计原则（全部继承既有铁律）：

1. **白板是 artifact，不是临时涂鸦层** —— 存进 `sims_store`，`kind='whiteboard'`，走
   `create_artifact` / `save_version`，天然获得版本历史与可回退。
2. **客户端永不升级状态** —— 图片按 media policy 状态渲染：`ready` 才显示位图，
   `link_only` 只渲染来源 chip + 链接，`withheld` 只渲染 `withheld_reason` 且不带 actionable URL。
3. **服务端是边界执行点** —— 学生在白板上只能加"个人 ink layer"和 filing request，
   mutate 共享白板的工具只对 teacher account 开放。

---

## 3. Whiteboard 文档模型

```json
{
  "id": "wb_xxx",
  "kind": "whiteboard",
  "title": "…",
  "version": 7,
  "space": { "w": 4000, "h": 2500, "origin": "top-left", "units": "px@1x" },
  "layers": [
    { "id": "shared", "role": "teacher" },
    { "id": "ink:<user_id>", "role": "student", "owner": "<user_id>" }
  ],
  "blocks": [
    {
      "id": "b_01",
      "layer": "shared",
      "type": "path | shape | connector | text | image | diagram | sim_embed",
      "rect": { "x": 0, "y": 0, "w": 0, "h": 0 },
      "data": { },
      "provenance": { "turn_id": "…", "tool_call": "…", "source": "agent|student" }
    }
  ]
}
```

block 类型与 `data` 约定：

| type | data | 说明 |
|---|---|---|
| `path` | `{points:[[x,y]…], stroke, width, closed}` | 自由笔画/函数曲线；客户端 Catmull-Rom 平滑 |
| `shape` | `{shape:'rect|ellipse|polygon|arrow', fill, stroke}` | 几何图元 |
| `connector` | `{from:block_id, to:block_id, label?}` | 语义连接线，端点移动自动跟随 |
| `text` | `{text, size, color, anchor?:block_id}` | 可锚定到任何 block，随其移动 |
| `image` | `{asset_id, license_state, caption, source_url?}` | 只指向 media store 缓存，永不外链 |
| `diagram` | `{format:'mermaid|graphviz', src}` 或 `{nodes:[], edges:[]}` | 语义图；服务端渲染成 SVG，agent 后续可编辑 src |
| `sim_embed` | `{artifact_id, version, rect}` | 白板上嵌一张 sim/deck 卡片（沿用 embed 白名单思路，但同源 store 内嵌不受 EMBED_ONLY host 限制） |

validator 规则（新增 `validate_board_doc`，与 `validate_html` 并列成为权威）：
- 坐标必须在 `space` 内；`image.asset_id` 必须存在于 media store 且记录 license_state；
- 禁止任何 `data` 字段携带可执行脚本；`text` 长度上限（防 token 灌水）；
- `provenance` 必填 —— 每一笔都可追回 turn。

---

## 4. Agent 的三项白板能力（工具规格）

### 4.1 画（draw）—— 矢量 ops，不是像素

```python
whiteboard_apply(board_id, ops=[...])
# op: {"op":"add"|"update"|"remove", "block":{...}}
# 一次 turn 内的所有 ops 原子提交：任一非法 → 全部拒绝，版本不 bump
```

- agent "画"的方式是**发几何**：`path` 给点列，`shape` 给图元，`connector` 给语义端点。
  不做鼠标模拟、不做位图笔刷 —— 因为位图不可版本 diff、不可编辑、agent 输出成本高 100 倍。
- 数学场景特化：`path` 支持函数表达式形式
  `{"points_expr": "y = 2x+1", "x_range":[0,10]}` 由服务端采样成点列，
  与 native 侧 `Studio.swift` 的 Canvas 坐标语义对齐。
- 读回能力：`whiteboard_read(board_id)` 返回 blocks 摘要（id/type/rect/text 前 80 字符），
  agent 必须能"看见"板面才能引用与增量编辑（如学生在曲线上圈了个圈 → selection payload
  带 `board_block_id`，agent `whiteboard_read` 后针对性讲解）。

### 4.2 搜图并贴（search & paste）—— 走已有 gate 管线

链路（复用现有工具，只新增"落板"一步）：

```
agent 决策 → image_search(query) / find_image(concept_id) / image_generate(prompt)
          → 候选带 license/来源
          → whiteboard_place_image(board_id, asset_id, rect, caption)
             · 服务端把图片写入 media store 缓存
             · license_state 原样带到 image block
             · ready → 渲染位图；link_only → 只渲染来源 chip；
               withheld → 只渲染 withheld_reason（无 actionable URL）
          → 版本 bump，SSE turn_end 后客户端刷新
```

- **diagram 优先语义化**：流程图/关系图默认用 `diagram` block（mermaid/Graphviz 源码），
  服务端渲染 SVG。语义源可被 agent 再编辑，位图贴图只用于照片/扫描件类素材。
- `image_generate`（Pollinations）产物 license 最干净（生成物），教学板面优先级最高；
  检索图必须过 `ingest/policy.py` 的 audited list，未注册源 = refuse，不降级。
- validator 既有约束自然生效：**贴图必须入缓存，artifact 内不存在外部 URL**。

### 4.3 写（write）—— 文本块

```python
whiteboard_write(board_id, text, x, y, *, size='m', anchor=None, layer='shared')
```

- 数据层永远是纯文本（可搜索、可翻译、可 TTS —— 与 `text_to_speech` 管线天然接通）；
  "手写感"是 presentation 层的字体选择，不进入数据。
- `anchor` 把标注钉到某个 block（如给一条曲线写 "斜率 = Δy/Δx"），端点移动文字跟随。
- 长讲解不要写上白板 —— 白板文字是**标注**（≤ 200 字/块），长内容用 `deck` 或 chat 转写，
  白板上放 `sim_embed`/链接卡。

---

## 5. 交互交付全链路（end-to-end）

一次典型 teacher turn：

1. **意图进入**：teacher 在白板圈选一个 block（或直接打字）→
   `POST /api/v1/agent/stream`，`context = {board_id, role:'teacher', selection:{board_block_id,…}}`。
2. **agent loop**（`agent_loop.py` 不变）：按需 `whiteboard_read` → `search_concepts` /
   `image_search` → `whiteboard_apply` / `whiteboard_write` / `whiteboard_place_image` →
   `whiteboard_save_version`（或 apply 内自动 bump）。
3. **流式反馈**：SSE 事件契约不变（`tool_call`/`tool_result` 卡片照常渲染）；
   新增一个**可选**事件 `artifact_updated {kind:'whiteboard', id, version}`，
   没有它客户端也兜底：`turn_end` 后 poll 一次 metadata（沿用现 sim 版本刷新模式）。
4. **画布刷新**：客户端拉 `GET /api/v1/sims/{board_id}/raw?version=n`（白板是 JSON，非 HTML，
   走同一路由按 kind 分流）→ 重建 SVG 场景 → 全部 block 带 provenance tooltip。
5. **学生侧**：学生的笔画/文字只落 `ink:<uid>` 层，UI 上是"我的批注"；
   想改共享板 → 四类 change request（bug/wrong_info/ugly/ux），服务端 gate 拒绝一切越权。

---

## 6. Vibe-coded software 分类表：每种怎么生成、怎么用

| kind | 生成工具 | 本质 | 交互方式 | 用途场景 | 约束 |
|---|---|---|---|---|---|
| `simulation` | `write_simulation` / `edit_simulation` | 单文件 HTML + JS 的可操作模型 | iframe sandbox + hover-select + 参数拖拽；学生只能 filing request | 需要学生**动手改参数看结果**的概念（供需曲线、分布） | `validate_html`：无外部资源/无 eval；`data-series` 约定；版本链 |
| `deck` | `generate_slides` | 分页讲解序列 | 翻页导航 | 线性讲解、概念引入 | 同 validator |
| `whiteboard` | `whiteboard_apply/write/place_image`（新增） | 结构化 SVG 场景文档 | 画/写/贴/连接/圈选讲解 | **即时性讲解**：agent 边说边画、标注、拼图 | `validate_board_doc`；矢量优先；图片必入缓存 |
| `figure` | `build_figure` | matplotlib 确定性图表 | 静态查看 | 数据/函数的精确静态图 | 模板化，非 vibe-coded（确定性管线） |
| `quiz` | `check_understanding` | 题目 + 判分 | 表单作答 | 检查理解、evidence 采集 | 结果进 learner evidence |

**使用判据（agent 侧决策规则）**：
- 学生要"玩参数" → `simulation`；要"顺序听讲" → `deck`；要"现在就在板上看这个关系" → `whiteboard`；
- 要精确数据图 → `figure`（不要让 agent 手画坐标轴，采样交给 matplotlib）；
- 白板上要交互模型 → `sim_embed` 卡片指向 `simulation`，**不在白板里重造 sim**。

---

## 7. 已存在 vs 需新建（delta）

| 项 | 状态 |
|---|---|
| SSE agent 流、selection payload、role gate、sims_store 版本链、image_search/generate/find_image、validate_html | ✅ 直接复用 |
| `KINDS += 'whiteboard'`、`validate_board_doc`、board JSON 路由分流 | 🆕 小改（sims_store + web_routes） |
| 工具：`whiteboard_read/apply/write/place_image/save_version` | 🆕 新增（toolbox 注册，5 个） |
| 白板前端（SVG 场景渲染、圈选、ink layer、学生边界 UI） | 🆕 主体工作量（`harness/web/` 新 panel 或独立 tab） |
| `artifact_updated` SSE 事件（可选优化） | 🆕 可后置 |

## 8. 实施阶段（每阶段可独立验证）

- **P1 后端最小闭环**：KINDS 扩展 + board 文档校验 + 5 个工具 + 路由；
  pytest 覆盖 gate 拒绝路径（学生 mutate → 403 / refuse）与 validator 拒绝路径（外链图、超界坐标、无 provenance）。
- **P2 前端白板**：SVG 渲染 + block 选择 + teacher/学生 ink layer + turn_end 刷新；
  复用现有 selection payload 结构（`kind` 增加 `board_block`）。
- **P3 diagram/数学特化**：mermaid 服务端渲染、`points_expr` 采样、sim_embed 卡片。
