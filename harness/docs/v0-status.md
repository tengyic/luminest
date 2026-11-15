# v0 状态

一次会话内做完的事，按"能被证明"和"还没被证明"分开。所有命令都在
`harness/` 下执行，后端假定已在 `127.0.0.1:8877` 运行
（`bash scripts/start_local_services.sh --serve`）。

## 已经证明的

来自实际运行输出，不是推断：

| 事实 | 证据 |
|---|---|
| Voice Studio 端到端可用 | `audio: 8/8 clip(s) rendered`，单条 58–213 KB 真实 mp3 |
| 模型已配置 | `/health` → `provider=openai model=deepseek-flash api_key_set=true` |
| 随包图库完整 | `rows: 107 / pack: 107`，文件都在盘上 |
| 教材里真的有图 | `idea: ['text','text','image','text']`，`/deck/{id}/images` → `resolved=True` |
| 导出文件里有字节 | `pptx carries pictures: 1 media file(s), 6 slide(s), 154 KB` |
| 课里有图 | `lesson blocks carry a picture: 1 available picture(s) in 3 blocks` |
| 十二项自检全绿 | `verdict: all checks passed` |

## 这一轮改了什么

**一个 bug，重复了三处。** 随包图库的键是短 slug（`active_transport`），而三个调用点
都拿课程限定的长 id（`biology_active_transport_against_a_gradient`）去查，于是 107 张
图一张也用不上，每次回落到联网搜索再回 `network_disabled`：

- `routes_ta.prepare` —— 而且它**从来没有查过图**（docstring 原文 "Only video is repaired here"）
- `procedure_service._deck_image` —— deck 唯一的图源
- `presentation.compose` —— 旁白侧的 enrichment，图片挂在 slide 的 `visual` 上

修法是一处共用函数而不是三处补丁：

- `media._concept_keys()` 从 id 自身切 1–5 个 token 的连续窗口，最长优先。
  **候选不依赖读 pack** —— 第一版从 pack 推导候选，pack 一异常就复现同一个 bug。
- `media.photograph_for_concept()` 先查随包（离线、确定），再按 `media_enabled` 决定
  是否联网；无论有没有图都返回 `available` + 命名的 `reason`，让"没有"和"被拒绝"
  不再长得一样。
- `deck.from_presentation()` 本来就会在 `visual.sha256` 存在时生成 image 元素，
  只是从来没有人给它 sha。

**课内那张图**：首次接触时 deck 被视频替代，课就没有任何能放图的 block。
不改教学规则，而是给 video 挂 `poster`（`artifact.poster`），并且**刻意不在
`_artifact_identity` 白名单里**——重新挑一张照片不算"计划变卦"。

**PPT 难看**：`from_presentation` 里所有版式共用一组坐标（`48,36,864,78` +
`48,132,560,320`），所以每一页都是"标题 + 一个项目符号框"。

- `LAYOUT_GEOMETRY`：八种版式各自一套 `(x, y, w, h, pt)`。
- `deck.lint()` + `GET /api/v1/deck/{id}/lint`：规范变成代码，六条规则（画布、
  标题/正文/脚注下限、bullet 上限、图片必须带署名）。
- 投影层压平：超 6 条移进备注，单条超 220 字符截断——**修上游，不放宽检查**。

**题目质量**：诊断题的干扰项是别的概念的 summary，靠排除法就能答对。

- `_item_quality()` 标成 `error_process` / `topic_recognition` / `none`；
- 错误过程题排前面；
- 全是指辨识题时，block 的 `why` 自己说明"这是定向，不是关于你能做什么的证据"。

## 已运行验证（2026-11-15 下午，`mcp__bash`）

- `24 passed`（`test_deck_lint` / `test_item_quality` / `test_media_concept_keys`）；
  `197 passed` 覆盖 deck、课程引擎、媒体管线、图片包、题目质量。
- 第一次运行就抓到一个我写的崩溃级 bug：`deck.py` 里我新建的 `CANVAS = (960, 540)`
  覆盖了原有的 `CANVAS = {'w': 960.0, 'h': 540.0}`，`new_deck` 的 `dict(CANVAS)` 直接
  `TypeError`，整条 deck 路由会挂。改名 `SLIDE_SIZE` 后通过。
- 视觉复核（chromium 截图）另抓到两个：预览器里图片元素少了 `image` class，导致
  `object-fit: contain` 没生效、图片被裁；`idea` 版式的图槽只有 288pt，1600×650 的图
  塞进去只剩一条。都已修，图现在是完整的。
- 图片挂载点从第一个 `idea` 页改到 `figure` 页：`figure` 才有最宽的图槽（444pt），
  而且那一页的职责就是放图。
- AP Psych 真跑：`/create/upload` 必须带 `?save=1`（默认只 preview，返回一个"看起来
  建好了"的课程然后什么都不存，所以紧接着的 enrol 会 404）。加上之后
  `60 concepts / 240 questions / with_lesson: 60`，已保存并选课。
- 但课是空的：正文只有一行学习目标。根因在 `extract_concepts` —— 标题分支把**标题行本身**
  当 span 传给 `consider`，后面那段只被拿去当 240 字摘要。于是每节课的"原文"就是标题，
  deck 只能显示 `0.1-3 How does critical thinking feed a scientific attitude…` 加 70% 空白。
- 修法两层：(a) 标题的 span 收集到下一个标题为止的整段正文，跳过 `Learning Targets`
  这类版式标题与 `0.1-3` 这类目标行；(b) `concept_entry` 的 core 用 passage 而不是 summary。
  另外抽取脚本必须**按节重组段落**，原来按行切，段落碎到无法收集。
- 过程中两次踩到 v0 的不变量，都被测试挡下：
  - `source_span` 必须是原文**逐字子串** —— 我剥了 `##`、又把段落用空格拼接，两个都破坏了。
    正解：span 存原文切片，markdown 在展示层剥。
  - 工作示例必须**逐字引用** span —— 我折叠了空白，引用里就不含 span 了。
- 最终：`65 passed`（course_builder / deck / deck_lint）。
- 展示层两处收尾：正文不再重复概念标题（span 从标题开始，剥掉后用真句子开头）；
  `deck.from_concept` 现在传 `include_image=True`，于是**上传课程也能配图**——随包图库
  没有心理学条目，不联网就永远是 0 张。许可证门与署名照旧，无网络的实例降级为具名理由。
- AP Psych deck 现在 8 页、1 张图（Overconfidence 那张中世纪挂毯，搜索用概念标题命中）。
- `figure` 页的文案跟着图走：`asset_payload` 新增 `caption`（策展人写的 `description`），
  有才改标题与正文；下载来的图只有 `alt`，兜底成 `Illustration for X`，比原来的
  "标题说 See it move、正文列先修概念"好，但仍然平淡——图里那句真正的说明在像素里，
  不在元数据里。
- 全量相关模块：`143 passed`（deck / lesson_procedure / course_builder）。

## 图片到底要多大的：按五份参考量出来的标准

用户给了五份参考（Cave Paintings / Human Advantage / Catching Fire / Ten Principles /
Songs pptx）。按"图片面积占页面 ≥12%"统计，真实的标准不是"每页都有图"，而是
**少数几页、每页一张主导图**：

| 参考 | 有大图的页 | 最大占比 |
|---|---|---|
| Cave Paintings（6 页） | 6 | 44–50% |
| Human Advantage（19 页） | 2 | 45% |
| Catching Fire（13 页） | 3 | 45% |
| Ten Principles（24 页） | 5–8 | 27% |
| Songs（11 页 pptx） | 1 | — |

我们的 deck 原本是 8 页 1 张、占 26%——**不是没有，是像缩略图**。改法：

- `PHOTO_GEOMETRY`：按图片自身宽高比选槽位。宽图（≥1.4）走整条横幅（864×254，
  43%），近方的图走右栏（496×420，40%）。宽高来自 manifest，不猜。
- 封面复用同一张图：右缘出血 412×540（43%），`fit=cover` 只用于封面，内页仍 `contain`。
  封面是读者一定会看到的那一页，而重新搜一张只会更差且多一次请求。
- 预览器跟随 `fit` 属性，否则本地看到的永远和导出不一致。

## 白板：从 0/2 到 5/5，以及三个没人看见的洞

按真实路径测（`/api/v1/whiteboard-agent/draw`，`mode=description` 让 agent 自己写 spec）：

- 第一次就失败：`RENDER_FAILED` / "spec refused by visual_specs.clean_visual_payload"，
  什么都没写入。**提示里只给了顶层键**（`viewport, curves, points...`），没给嵌套形状，
  模型于是写出 `{"points":[{"at":[1,1]}]}` 和 `"expr": "2x + 1"`——都是合理的猜法，
  都被静默拒绝。
- 补 `visual_specs.SPEC_SHAPES`（mafs/plotly 的嵌套契约 + 表达式必须显式 `*`）之后：
  **5/5 DRAWN**（mafs ×3、plotly、tex）。
- 拒绝现在把**被拒的 spec**和允许的形状一起返回；之前只有"什么都没写入"。

另外两个：

- **SVG 导出丢掉全部 visual 节点**：11 个节点导出成 302 字节白纸。`to_svg` 有
  path/shape/text/answer/image/video 分支，唯独没有 `visual`。现在画带标题的虚线框
  （3885 字节、11 个框），框内自述"交互式，静态 SVG 不可呈现"。
- **Mafs 用深色主题**：白板是纸，图渲成一块黑板。宿主样式加
  `--mafs-bg/--mafs-fg/--mafs-line-color` 后白底黑字，实测
  `getComputedStyle(.MafsView).backgroundColor = rgb(255,255,255)`。

改产物踩到的坑：`web-visuals/out/` 与 `native/.../Visuals/` 都带 `MANIFEST.sha256`，
手改 CSS 直接让 `test_the_real_published_bundle_passes_the_gate` 失败。正确路径是改
`src/styles.css` 再 `npm run build`；而 build.mjs 里写死的 `python3` 没有 httpx，已改成
认 `PYTHON`。重建后 `153 passed`。

## 版式语言：从十张课堂实拍里读出来的

用户给了十张教室白板实拍（`DEVON SCHOOL DAILY NEWS` 系列）。它们不是"有图的幻灯片"，
而是一套**结构语言**：

| 元素 | 做法 |
|---|---|
| 页眉 | 左上角小字机构名 + 细线 |
| 标题 | 大号左对齐，下方一条横线 |
| 论点句 | 一行强调色句子 |
| 行结构 | 左侧彩色胶囊（`WHO/WHAT/WHEN`）+ 右侧内容 |
| 语义色 | 蓝=中性/事实，琥珀=谨慎/重构，红=禁止/无依据 |
| 分组 | 淡色卡片（`YOU MAY` / `YOU MAY NOT` 双栏） |
| 收束句 | 底部一行强调色 |
| 图片 | 只有一页有照片，而那一页讲的就是"图片与说明" |

已实现的是**骨架**：每页 kicker（小字页眉）+ 标题 + 细线（`shape: line`），正文紧贴
线下（`anchor: top`，不再在 320 高的框里垂直居中）。`shape` 是 deck 模型的一等元素
（`text/image/shape/formula/table`），所以分隔线和未来的胶囊都不需要新类型。

未实现的是**语义结构**：胶囊标签、淡色分组、底部收束句。它们要的不是画法，而是内容
schema——每个 segment 得能携带 `rows: [{label, text, tone}]`。那是下一步。

预览器补了两处否则永远看不清的东西：`shape` 之前不画（分隔线不可见），`anchor: top`
被当成居中（正文被推下去）。

## 还没被证明的
- **测试没跑过。** `backend/tests/test_deck_lint.py`、`test_item_quality.py`、
  `test_media_concept_keys.py` 一共 24 条断言，全部未经执行。第一次失败不代表功能错，
  可能只是我的断言写错了。
- **版式只验证了"不同"，没验证"好看"。** `title placement varies by layout` 能证明
  坐标分开了，证明不了投影可读。需要人看一眼 `outputs/deck-preview.html`。
- **AP Psych 仍然没有内容。** `curriculum_packs/ap_psychology.json` 是结构-only
  （版权决定）。路径是 `scripts/make_course.py` 走 learner-uploaded，
  不是补那个 pack。
- **诊断的另一半没做**：现场生成带错误过程的题。这是内容生成管线，不是改这几行代码。

## 验证顺序

```bash
# 1. 单元测试（最快，先排除我把代码写坏）
cd backend && PYTHONPATH=. TMPDIR="$PWD/.tmp/t1" .venv/bin/python -m pytest -q \
  tests/test_deck_lint.py tests/test_item_quality.py tests/test_media_concept_keys.py

# 2. 端到端十二项
cd .. && backend/.venv/bin/python -u scripts/selfcheck.py --base http://127.0.0.1:8877

# 3. 看设计（这一步只能靠眼睛）
backend/.venv/bin/python -u scripts/preview_deck.py

# 4. 看能力
backend/.venv/bin/python -u scripts/diagnose.py
```

## 工具

| 脚本 | 回答 |
|---|---|
| `selfcheck.py` | 十二项红线，能不能用 |
| `probe_images.py` | 图链路哪一环断了、为什么 |
| `preview_deck.py` | 这页长什么样（本地 HTML，图片内嵌） |
| `diagnose.py` | 我的能力在哪，题目够不够格当证据 |
| `make_course.py` | 把文档变成可学的课 |

## 下一步顺序

1. 跑上面四条，把失败项贴回来。
2. 按 `deck-preview.html` 的实际观感调 `LAYOUT_GEOMETRY`（改的是数字，不是结构）。
3. 生成带错误过程的题（内容管线，需要模型 + 校验）。
4. Voice Studio → Live API 切换（本地链路已证可用，换的是传输层）。
