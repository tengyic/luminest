# -*- coding: utf-8 -*-
"""
prep_ednet.py — 把真实 EdNet KT1 日志整理成 KT 训练序列
数据: 真实 Riiid EdNet KT1 (CC BY-NC 4.0, 研究用途)
输入: kt1_shard0.parquet  (全量 KT1 的 1/11 分片, 真人真作答)
     questions.csv       (题目元数据: question_id -> correct_answer, tags)
输出: ednet_seqs.npz     (每个真实学生一条序列: 题目id / 对错 / 间隔时间)
"""
import sys
import numpy as np
import pandas as pd

PARQUET = "kt1_shard0.parquet"
QUESTIONS = "questions.csv"
OUT = "ednet_seqs.npz"

MAX_USERS = 8000        # 取前 N 个真实学生（CPU 训练可承受的规模）
MIN_LEN = 20            # 序列太短的学生丢弃（信息不足）
MAX_LEN = 200           # 序列截断长度（保留最近 MAX_LEN 次作答）

def main():
    print("== 读取真实 EdNet parquet ==")
    df = pd.read_parquet(PARQUET)
    print("原始行数:", len(df))
    print("列:", list(df.columns))
    print(df.head(3).to_string())

    # ---- 列名自适应 ----
    cols = {c.lower(): c for c in df.columns}
    def pick(*cands):
        for c in cands:
            if c in cols: return cols[c]
        return None
    c_user = pick("user_id", "user", "student_id", "subject_id")
    c_q    = pick("question_id", "content_id", "item_id")
    c_ans  = pick("user_answer", "answer")
    c_corr = pick("correct", "answered_correctly", "is_correct")
    c_ts   = pick("timestamp", "time", "ts")
    c_el   = pick("elapsed_time", "elapsed")
    print(f"识别列: user={c_user} q={c_q} ans={c_ans} corr={c_corr} ts={c_ts} elapsed={c_el}")

    # ---- 对错标签 ----
    if c_corr is not None:
        df["y"] = df[c_corr].astype(int)
    else:
        # KT1 原始格式没有 correct 列 -> 需要 questions.csv 的正确答案来判分
        q = pd.read_csv(QUESTIONS)
        qc = {c.lower(): c for c in q.columns}
        qid = qc.get("question_id"); qca = qc.get("correct_answer")
        print("questions.csv 列:", list(q.columns))
        ansmap = dict(zip(q[qid], q[qca]))
        df["y"] = (df[c_ans].map(lambda a: a) == df[c_q].map(ansmap)).astype(int)

    # ---- 题目 id 重编码（压缩到连续整数） ----
    q_str = df[c_q].astype(str)
    if q_str.str.startswith("q").any():
        # 形如 'q123' -> 123
        df["qidx_raw"] = q_str.str.replace(r"^q", "", regex=True).astype("int64")
    else:
        df["qidx_raw"] = df[c_q].astype("int64")

    # ---- 按用户取序列 ----
    users = df[c_user].unique()[:MAX_USERS]
    df = df[df[c_user].isin(set(users))]
    print("选取真实学生数:", len(users), "| 交互数:", len(df))

    # 只保留出现频次前 N 的题目, 其余映射到 UNK, 控制嵌入表大小
    vc = df["qidx_raw"].value_counts()
    keep = set(vc.index[:12000])
    q2i = {q: i + 1 for i, q in enumerate(sorted(keep))}   # 0 = UNK/PAD
    df["qidx"] = df["qidx_raw"].map(lambda x: q2i.get(x, 0))

    df = df.sort_values([c_user, c_ts])
    seq_items, seq_resps, seq_dts, seq_lens = [], [], [], []
    for uid, g in df.groupby(c_user, sort=False):
        if len(g) < MIN_LEN: continue
        g = g.tail(MAX_LEN)
        items = g["qidx"].to_numpy(np.int64)
        resps = g["y"].to_numpy(np.int64)
        ts = g[c_ts].to_numpy(np.float64)
        dt = np.diff(ts, prepend=ts[0]) / (1000 * 3600 * 24.0)  # ms -> 天
        dt = np.clip(dt, 0, 30.0)
        L = len(items)
        pad = MAX_LEN - L
        seq_items.append(np.pad(items, (0, pad)))
        seq_resps.append(np.pad(resps, (0, pad)))
        seq_dts.append(np.pad(dt, (0, pad)).astype(np.float32))
        seq_lens.append(L)

    items = np.stack(seq_items); resps = np.stack(seq_resps)
    dts = np.stack(seq_dts); lens = np.array(seq_lens)
    print(f"最终: {len(lens)} 名真实学生 | 总交互 {lens.sum():,} | 题库 {len(q2i)+1}")
    print(f"整体正确率: {resps[np.arange(len(lens))[:,None], :].sum() / lens.sum():.3f}")
    np.savez_compressed(OUT, items=items, resps=resps, dts=dts, lens=lens,
                        n_items=len(q2i) + 1)
    print("已保存:", OUT)

if __name__ == "__main__":
    main()
