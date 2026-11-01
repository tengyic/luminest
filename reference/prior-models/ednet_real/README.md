# 真实 EdNet 知识追踪 + 蒸馏管线（非模拟器）

这套代码用的是**真实公开的学生作答数据**（Riiid EdNet KT1，CC BY-NC 4.0，研究用途），
全程**没有任何模拟器成分**。教师是在真人真作答上训练出来的，学生是从这个真教师蒸馏出来的。

## 数据来源（真实）

- **EdNet KT1**：韩国 Santa TOEIC 备考 App 的真实学生作答日志，业界最大 KT 数据集（全量 78 万学生 / 1.3 亿交互）。
- 本管线用的是 HuggingFace 镜像 `mgor/EDNet` 的 1/11 分片（`train-00000-of-00011.parquet`，163MB，866 万条真实交互）。
- 题目元数据 `questions.csv` 来自 `Unggi/ednet5000_raw_data`。

数据字段：`timestamp, solving_id, question_id, user_answer, elapsed_time, subject_id(=用户), correct_answer, is_correct`。

## 管线三步

```
1. prep_ednet.py      真实 parquet -> 每个真实学生一条序列 (题/对错/间隔天) -> ednet_seqs.npz
2. train_real_kt.py   在真实序列上训练"真教师"(时间衰减注意力 Transformer) -> real_kt_teacher.pt
3. distill_real.py    用真教师软标签蒸馏出"端侧小学生" -> real_kt_student.pt
```

## 实测结果（本机 CPU，真实数据）

预处理后：**3,253 名真实学生 / 285,421 条真实交互 / 题库 12,001**，整体正确率 0.608。

| 模型 | 参数 | 验证集 AUC | 验证集 ACC | 单次推理延迟 |
|---|---|---|---|---|
| 多数类基线 | — | 0.500 | 0.619 | — |
| **真教师**（train_real_kt） | 844K | 0.711 | 0.674 | 2.02 ms |
| **蒸馏学生**（distill_real） | 395K | **0.731** | 0.690 | **0.97 ms** |

- AUC 0.71 是在 28 万交互的子集 + CPU 小模型上的合理成绩；全量 EdNet + GPU 上 SAINT+ 可达 ~0.78–0.80。
- 学生 AUC 反超教师：软标签的正则化效应 + 教师轻微过拟合，是蒸馏常见现象。
- **诚实边界**：本例压缩比只有 2.1x，因为参数被 12001×d 的**题目嵌入表主导**（d=32 时嵌入表 ≈384K，占学生 395K 的绝大部分）。真正的端侧压缩还需**嵌入表分解 / 词表裁剪 / INT8 量化**，那时压缩比可达 5–10x。

## 复跑命令

```bash
PY=/Users/tengyi/.workbuddy/binaries/python/envs/distill/bin/python
cd ednet_real
$PY prep_ednet.py                 # 需先有 kt1_shard0.parquet + questions.csv
$PY train_real_kt.py --epochs 15  # 训真教师
$PY distill_real.py --epochs 20   # 蒸馏真学生
```

数据下载（若缺 parquet）：
```bash
curl -sL -o kt1_shard0.parquet \
  "https://huggingface.co/datasets/mgor/EDNet/resolve/main/kt1/train-00000-of-00011.parquet"
```

## 与之前 `distill/`（模拟器版）的区别

- `distill/`：教师是**按公开论文复现的模拟器**（Birdbrain/ALEKS 行为等价简化版），验证的是**蒸馏方法论**。
- `ednet_real/`（本目录）：教师是**在真实 EdNet 上训练**出来的，数据/学生/作答**全部真实**。这才是"真蒸馏"。

## 扩到全量（GPU）

同一套脚本，把 `prep_ednet.py` 的 `MAX_USERS` 调大、下载全部 11 个分片、`train_real_kt.py` 的 `--d 256 --layers 6`，
在 1× A100/H100 上即可训练接近 SOTA 的教师，再用 `distill_real.py` 蒸成端侧模型。
