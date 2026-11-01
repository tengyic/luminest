# -*- coding: utf-8 -*-
"""
train_real_kt.py — 在真实 EdNet KT1 数据上训练真正的知识追踪模型
模型: 时间衰减注意力 Transformer (AKT/SAINT+ 思想的简化实现)
数据: 真人真作答 (无任何模拟器成分)
目标: next-interaction 预测 —— 给定历史, 预测下一题是否答对
评估: 按学生划分 train/val, 报告真实 AUC / ACC
"""
import argparse, math, time
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.metrics import roc_auc_score

DEVICE = "cpu"

# ---------------- 模型: 与 distill/student_model.py 同构 ----------------
class TimeDecayAttention(nn.Module):
    def __init__(self, d, heads):
        super().__init__()
        self.h, self.dk = heads, d // heads
        self.qkv = nn.Linear(d, 3 * d)
        self.o = nn.Linear(d, d)
        self.gamma = nn.Parameter(torch.ones(heads) * 0.1)  # 每头可学习的时间衰减

    def forward(self, x, cum_t, mask):
        B, L, D = x.shape
        qkv = self.qkv(x).view(B, L, 3, self.h, self.dk).permute(2, 0, 3, 1, 4)
        q, k, v = qkv[0], qkv[1], qkv[2]                      # [B,h,L,dk]
        att = (q @ k.transpose(-2, -1)) / math.sqrt(self.dk)   # [B,h,L,L]
        # 时间衰减偏置: 越久远的交互, 注意力越低 (遗忘内建)
        dt = (cum_t.unsqueeze(-1) - cum_t.unsqueeze(-2)).clamp(min=0)  # [B,L,L]
        att = att - F.softplus(self.gamma).view(1, -1, 1, 1) * dt.unsqueeze(1)
        att = att.masked_fill(mask, float("-inf"))
        att = att.softmax(-1)
        out = (att @ v).transpose(1, 2).contiguous().view(B, L, D)
        return self.o(out)

class Block(nn.Module):
    def __init__(self, d, heads, ff):
        super().__init__()
        self.attn = TimeDecayAttention(d, heads)
        self.n1, self.n2 = nn.LayerNorm(d), nn.LayerNorm(d)
        self.ff = nn.Sequential(nn.Linear(d, ff), nn.GELU(), nn.Linear(ff, d))
    def forward(self, x, cum_t, mask):
        x = x + self.attn(self.n1(x), cum_t, mask)
        return x + self.ff(self.n2(x))

class RealKT(nn.Module):
    """输入: 历史(题,对错,间隔) + 当前题id -> 输出 P(当前题答对)"""
    def __init__(self, n_items, d=64, heads=4, layers=2, ff=128, max_len=200):
        super().__init__()
        self.item_emb = nn.Embedding(n_items, d, padding_idx=0)
        self.resp_emb = nn.Embedding(3, d)     # 0错/1对/2起始
        self.dt_proj = nn.Linear(1, d)
        self.blocks = nn.ModuleList([Block(d, heads, ff) for _ in range(layers)])
        self.norm = nn.LayerNorm(d)
        self.head = nn.Sequential(nn.Linear(2 * d, d), nn.GELU(), nn.Linear(d, 1))
        self.max_len = max_len

    def forward(self, items, resps, dts):
        B, L = items.shape
        # 历史流: 第 t 步的输入 = 第 t-1 步的 (题,对错) —— 严格避免标签泄漏
        hist_items = torch.cat([torch.zeros_like(items[:, :1]), items[:, :-1]], 1)
        hist_resps = torch.cat([torch.full_like(resps[:, :1], 2), resps[:, :-1]], 1)
        x = self.item_emb(hist_items) + self.resp_emb(hist_resps) \
            + self.dt_proj(torch.log1p(dts).unsqueeze(-1))
        cum_t = dts.cumsum(-1)
        causal = torch.triu(torch.ones(L, L, dtype=torch.bool, device=items.device), 1)
        for b in self.blocks:
            x = b(x, cum_t, causal.unsqueeze(0).unsqueeze(0))
        x = self.norm(x)
        # 拼上"当前要预测的题"的嵌入
        cur = self.item_emb(items)
        return self.head(torch.cat([x, cur], -1)).squeeze(-1)   # logits [B,L]

# ---------------- 训练 ----------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--bs", type=int, default=64)
    ap.add_argument("--d", type=int, default=64)
    ap.add_argument("--layers", type=int, default=2)
    args = ap.parse_args()

    data = np.load("ednet_seqs.npz")
    items, resps, dts, lens = data["items"], data["resps"], data["dts"], data["lens"]
    n_items = int(data["n_items"])
    N = len(lens)
    print(f"真实学生 {N} 名 | 题库 {n_items} | 总交互 {lens.sum():,}")

    rng = np.random.default_rng(42)
    perm = rng.permutation(N)
    n_val = max(200, N // 10)
    val_idx, tr_idx = perm[:n_val], perm[n_val:]

    model = RealKT(n_items, args.d, 4, args.layers, args.d * 2, items.shape[1]).to(DEVICE)
    n_params = sum(p.numel() for p in model.parameters())
    print(f"模型参数量: {n_params/1e3:.0f}K")
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-5)

    def batches(idx, bs, shuffle=True):
        idx = rng.permutation(idx) if shuffle else idx
        for i in range(0, len(idx), bs):
            j = idx[i:i + bs]
            yield (torch.from_numpy(items[j]), torch.from_numpy(resps[j]),
                   torch.from_numpy(dts[j]), torch.from_numpy(lens[j]))

    def valid_mask(lens_t, L):
        ar = torch.arange(L).unsqueeze(0)
        m = ar < lens_t.unsqueeze(1)
        m[:, 0] = False           # 第一步没有历史, 不计入
        return m

    for ep in range(1, args.epochs + 1):
        model.train(); t0 = time.time(); tot, nb = 0.0, 0
        for it, rs, dt, ln in batches(tr_idx, args.bs):
            logits = model(it, rs, dt)
            m = valid_mask(ln, it.shape[1])
            loss = F.binary_cross_entropy_with_logits(logits[m], rs[m].float())
            opt.zero_grad(); loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            tot += loss.item(); nb += 1
        # ---- 验证 ----
        model.eval(); ys, ps = [], []
        with torch.no_grad():
            for it, rs, dt, ln in batches(val_idx, 128, shuffle=False):
                logits = model(it, rs, dt)
                m = valid_mask(ln, it.shape[1])
                ys.append(rs[m].numpy()); ps.append(torch.sigmoid(logits[m]).numpy())
        y = np.concatenate(ys); p = np.concatenate(ps)
        auc = roc_auc_score(y, p); acc = ((p > 0.5) == y).mean()
        print(f"epoch {ep:2d} | loss {tot/nb:.4f} | val AUC {auc:.4f} | "
              f"val ACC {acc:.4f} | {time.time()-t0:.0f}s")

    torch.save({"state_dict": model.state_dict(),
                "n_items": n_items, "d": args.d, "layers": args.layers},
               "real_kt_teacher.pt")
    print("已保存真实教师模型: real_kt_teacher.pt")
    print(f"基线参考: 全预测多数类 ACC = {max(y.mean(), 1-y.mean()):.4f}")

if __name__ == "__main__":
    main()
