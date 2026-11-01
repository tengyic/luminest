# -*- coding: utf-8 -*-
"""
distill_real.py — 把"在真实 EdNet 上训练好的真教师"蒸馏成端侧小学生

这是【真蒸馏】：
  教师 = real_kt_teacher.pt (844K 参数, 真人真作答训练, AUC~0.71)
  学生 = 更小的同构模型 (d=32, 1 层, ~1/4 参数)
蒸馏目标 = 让小学生在【尺寸/延迟大幅下降】的同时, 尽量保住教师的预测能力
  —— 这正是蒸馏的唯一真实意义: 压缩 (端侧/低延迟/数据不上云)

损失:
  L = alpha * T^2 * KL(teacher_soft || student_soft)   # 响应蒸馏(暗知识)
    + (1-alpha) * BCE(student, 真实对错)                # 硬标签兜底
"""
import argparse, math, time
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.metrics import roc_auc_score
from train_real_kt import RealKT   # 复用同构结构

DEVICE = "cpu"

def load_teacher(path="real_kt_teacher.pt"):
    ck = torch.load(path, map_location=DEVICE)
    m = RealKT(ck["n_items"], ck["d"], 4, ck["layers"], ck["d"] * 2, 200)
    m.load_state_dict(ck["state_dict"]); m.eval()
    return m, ck["n_items"]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--bs", type=int, default=64)
    ap.add_argument("--T", type=float, default=2.0)         # 蒸馏温度
    ap.add_argument("--alpha", type=float, default=0.7)     # 软标签权重
    ap.add_argument("--sd", type=int, default=32)           # 学生维度(小)
    ap.add_argument("--slayers", type=int, default=1)       # 学生层数(小)
    args = ap.parse_args()

    data = np.load("ednet_seqs.npz")
    items, resps, dts, lens = data["items"], data["resps"], data["dts"], data["lens"]
    n_items = int(data["n_items"])
    N = len(lens)
    rng = np.random.default_rng(42)
    perm = rng.permutation(N)
    n_val = max(200, N // 10)
    val_idx, tr_idx = perm[:n_val], perm[n_val:]

    teacher, _ = load_teacher()
    tparams = sum(p.numel() for p in teacher.parameters())

    student = RealKT(n_items, args.sd, 4, args.slayers, args.sd * 2, items.shape[1]).to(DEVICE)
    sparams = sum(p.numel() for p in student.parameters())
    print(f"教师参数 {tparams/1e3:.0f}K -> 学生参数 {sparams/1e3:.0f}K "
          f"(压缩 {tparams/sparams:.1f}x)")
    opt = torch.optim.AdamW(student.parameters(), lr=1.5e-3, weight_decay=1e-5)

    def batches(idx, bs, shuffle=True):
        idx = rng.permutation(idx) if shuffle else idx
        for i in range(0, len(idx), bs):
            j = idx[i:i + bs]
            yield (torch.from_numpy(items[j]), torch.from_numpy(resps[j]),
                   torch.from_numpy(dts[j]), torch.from_numpy(lens[j]))

    def valid_mask(lens_t, L):
        ar = torch.arange(L).unsqueeze(0)
        m = ar < lens_t.unsqueeze(1); m[:, 0] = False
        return m

    def evaluate(model):
        model.eval(); ys, ps = [], []
        with torch.no_grad():
            for it, rs, dt, ln in batches(val_idx, 128, shuffle=False):
                logits = model(it, rs, dt)
                m = valid_mask(ln, it.shape[1])
                ys.append(rs[m].numpy()); ps.append(torch.sigmoid(logits[m]).numpy())
        y = np.concatenate(ys); p = np.concatenate(ps)
        return roc_auc_score(y, p), ((p > 0.5) == y).mean()

    t_auc, t_acc = evaluate(teacher)
    print(f"教师(真实数据) val AUC {t_auc:.4f} | ACC {t_acc:.4f}")

    T, alpha = args.T, args.alpha
    for ep in range(1, args.epochs + 1):
        student.train(); t0 = time.time(); tot, nb = 0.0, 0
        for it, rs, dt, ln in batches(tr_idx, args.bs):
            with torch.no_grad():
                t_logits = teacher(it, rs, dt)          # 教师软标签
            s_logits = student(it, rs, dt)
            m = valid_mask(ln, it.shape[1])
            # 响应蒸馏(二分类的 KL, 温度 T)
            tp = torch.sigmoid(t_logits[m] / T)
            sp_log = F.logsigmoid(s_logits[m] / T)
            sp_log_neg = F.logsigmoid(-s_logits[m] / T)
            kl = (tp * (torch.log(tp + 1e-8) - sp_log) +
                  (1 - tp) * (torch.log(1 - tp + 1e-8) - sp_log_neg)).mean()
            hard = F.binary_cross_entropy_with_logits(s_logits[m], rs[m].float())
            loss = alpha * (T * T) * kl + (1 - alpha) * hard
            opt.zero_grad(); loss.backward()
            torch.nn.utils.clip_grad_norm_(student.parameters(), 1.0)
            opt.step()
            tot += loss.item(); nb += 1
        auc, acc = evaluate(student)
        print(f"epoch {ep:2d} | loss {tot/nb:.4f} | 学生 val AUC {auc:.4f} | "
              f"ACC {acc:.4f} | {time.time()-t0:.0f}s")

    torch.save({"state_dict": student.state_dict(), "n_items": n_items,
                "d": args.sd, "layers": args.slayers}, "real_kt_student.pt")
    s_auc, s_acc = evaluate(student)
    print("\n==== 蒸馏结果 ====")
    print(f"教师: {tparams/1e3:.0f}K 参数 | AUC {t_auc:.4f}")
    print(f"学生: {sparams/1e3:.0f}K 参数 | AUC {s_auc:.4f} "
          f"(保留 {s_auc/t_auc*100:.1f}% 教师能力, 压缩 {tparams/sparams:.1f}x)")

    # 延迟对比
    it = torch.from_numpy(items[val_idx[:1]]); rs = torch.from_numpy(resps[val_idx[:1]])
    dt = torch.from_numpy(dts[val_idx[:1]])
    def lat(m):
        m.eval()
        with torch.no_grad():
            for _ in range(5): m(it, rs, dt)
            t0 = time.perf_counter()
            for _ in range(50): m(it, rs, dt)
            return (time.perf_counter() - t0) / 50 * 1000
    print(f"教师延迟 {lat(teacher):.2f} ms | 学生延迟 {lat(student):.2f} ms")

if __name__ == "__main__":
    main()
