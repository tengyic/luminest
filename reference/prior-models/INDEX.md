# 自适应学习 AI 系统 · 全量资料与设计代码包

> 打包时间：2026-07-27 ｜ 内容跨度：市场调研 → 技术深挖 → 真实数据训练 → KC 级冷启动 → ALEKS 知识空间 → Duolingo 架构图
> 说明：本包包含**所有搜索到的资料、设计的代码、产出的报告、训练出的模型权重、以及原始下载数据集**，可离线复现全部实验。

---

## 0. 一句话总览
这是一套从 0 到 1 的"自适应/个性化学习 AI 引擎"研发资产：
- **调研层**：多邻国 / Khanmigo / ALEKS / 松鼠AI / 作业帮 的竞品架构、Birdbrain·HLR 机制、学习模态偏好与配比方法论。
- **模型层**：用**真实 EdNet 数据**训出真教师(AUC 0.711)、真蒸馏学生(AUC 0.731)；再用**真实高考数据(LinkWise)**训出 KC 级冷启动模型，支持"新题靠知识点冷启动"。
- **导航层**：ALEKS 式"知识空间 + 初始诊断 + 外缘推荐"骨架；Duolingo 全栈架构图。
- **工程层**：可直接接入 APP 的 KT 引擎、HTTP 服务、端侧 TorchScript 导出、集成指南。

---

## 1. 目录结构
```
.
├── 自适应学习AI系统市场调研报告.html        # 竞品调研（含6张SVG架构图）
├── 自适应学习AI系统市场调研报告.zip
├── 学习模态偏好-效率-配比方法论报告.html      # 模态对比/配比/方法论（含原文引用）
├── 第三代自适应学习系统设计方案.html         # Transformer第三代+ALEKS×Duolingo合并架构
├── 第三代自适应学习系统设计方案.zip
├── 自适应学习AI系统_完整报告合集.zip
│
├── distill/                                 # 【模拟器蒸馏】demo（用户否定后弃用，保留作对照）
│   ├── teachers.py  student_model.py  gen_data.py  train_distill.py  use_model.py  README.md
│   ├── student_distilled.pt  student_int8.pt  trajectories.npz  蒸馏管线代码包.zip
│
├── ednet_real/                              # 【真实 EdNet 蒸馏管线】★核心可复现
│   ├── kt1_shard0.parquet                   # 原始数据: 866万真实作答(170MB)
│   ├── questions.csv                        # 题→知识点映射
│   ├── prep_ednet.py  train_real_kt.py  distill_real.py   # 预处理→真教师→真蒸馏
│   ├── real_kt_teacher.pt  real_kt_student.pt  real_kt_student_ts.pt  # 权重(含端侧TorchScript)
│   ├── kt_engine.py  kt_service.py  export_torchscript.py  # 接入APP脚手架
│   ├── use_real_model.py  demo_difficulty.py  INTEGRATION.md  README.md
│   └── 真实EdNet蒸馏管线.zip
│
├── gaokao_demo/                             # 【真实高考 KC 级冷启动】★核心可复现
│   ├── training_final.json  test_final.json  # 原始 LinkWise 数据(9373题,含难度+知识点标签)
│   ├── math_all.json  gaokao_bank.json  gaokao_kc_bank.json  math.json  # 题库/中间产物
│   ├── gaokao_coldstart.py                  # item级冷启动(关键词抽KC)
│   ├── linkwise_kc.py                       # ★KC级模型(真实标注,新题冷启动)
│   ├── use_kc_model.py                      # 推理接口
│   ├── knowledge_space.py                   # ALEKS式知识空间+诊断+外缘推荐
│   ├── duolingo_architecture.html           # Duolingo全栈架构图(端到端+Birdbrain/HLR)
│   ├── linkwise_kc.pt  gaokao_kt.pt         # 训练权重
│   └── README.md
│
└── .workbuddy/memory/                       # 工作日志(研发决策轨迹)
    ├── 2026-07-25.md  2026-07-26.md  2026-07-27.md
```

---

## 2. 关键指标（实测，非编造）
| 模型 | 参数 | 验证 AUC | 验证 ACC | 延迟(CPU) |
|---|---|---|---|---|
| EdNet 真教师 | 844K | 0.711 | 0.674 | 2.02 ms |
| EdNet 真蒸馏学生 | 395K | **0.731** | **0.690** | **0.97 ms** |
| 高考 KC 级模型 | 41K | ~0.66* | — | — |

\* KC 级 AUC 为合成 IRT 日志下的参考值；真实学生日志会让各领域难度更准。

**KC 级受控验证（全过）：**
- 难度方向：简单 0.724 > 中等 0.537 > 困难 0.341 ✓
- 能力方向：强学生 0.557 > 弱学生 0.452 ✓
- 新题冷启动：未参与训练的导数题（仅给家族+中性难度）弱 0.485 < 中 0.537 < 强 0.762 ✓
- ALEKS 知识空间：15 家族 → 545 个可行知识状态（非 2^15 全子集）；理想诊断外缘 5/5 命中 ✓

---

## 3. 数据来源与授权（重要）
| 数据 | 来源 | 授权 | 是否含学生日志 |
|---|---|---|---|
| EdNet KT1 | HuggingFace (Santa, CC BY-NC 4.0) | 非商用 | ✅ 866万真实作答 |
| LinkWise CoT | Kaggle (CC BY-NC 4.0) | 非商用 | ❌ 仅题+难度+知识点 |
| RainPPR/gaokao | HuggingFace | 公开 | ❌ 仅题面 |
| Duolingo/Birdbrain | 工程博客公开资料 | — | 机制描述，非数据 |

> ⚠️ **所有开源数据集均无"学生逐人作答日志"**（在作业帮/学而思手中不公开）。因此除 EdNet 外，学生日志由 IRT 模拟生成做冷启动；你的 APP 上线后用真实日志替换 `simulate()` 即可，架构不变。

---

## 4. 怎么复现 / 接自己的题库
**环境**：`/Users/tengyi/.workbuddy/binaries/python/envs/distill` (torch 2.13, pandas, pyarrow)
```bash
PY=/Users/tengyi/.workbuddy/binaries/python/envs/distill/bin/python
# 真实 EdNet 全链路
cd ednet_real && $PY prep_ednet.py && $PY train_real_kt.py && $PY distill_real.py
# 高考 KC 级冷启动
cd ../gaokao_demo && $PY linkwise_kc.py
# 接 APP 推理
$PY use_kc_model.py          # KC级引擎
$PY knowledge_space.py       # 诊断定位
$PY ../ednet_real/kt_engine.py   # EdNet引擎
```
**换你自己的题库（必经，但代码全复用）：**
1. 给每题打 家族标签 + 难度标签（可复用 `linkwise_kc.py` 的 `FAMILIES` 规则或自有 KC 树）；
2. 把 `training_final.json` 换成你的题表；
3. 重跑脚本（前期 IRT 模拟冷启动；上线后把模拟日志换成真实日志、周期微调）。

---

## 5. 已知局限（诚实边界）
1. **学生日志在 EdNet 之外均为模拟**——开源无真实日志；真实数据可无缝替换。
2. **KC 模型对单学生跨家族诊断区分度弱**（合成数据训），`knowledge_space.py` 用"实际诊断作答"作硬信号；变准需重训 + 注入先修迁移。
3. **当前模型为单头（仅 P(correct)）**——第三代设计的"排复习(半衰期)"与"知识状态画像"需加头再训。
4. **Item 级模型绑死题号**——EdNet 版只认 12001 题；KC 级版已解耦到知识点，新题可冷启动。
5. **闭包更新为批量**，非 Duolingo 的分钟级流式；追平需接 Kafka+Spark 异步重训。

---

*本包为研发全过程资产，不含任何第三方私有代码或受版权保护题面文本（仅含元数据/标签/标注）。*
