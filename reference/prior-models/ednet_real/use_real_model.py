# -*- coding: utf-8 -*-
"""
use_real_model.py — 用你自己训出来的真教师 / 真学生做"下一题答对概率"预测

怎么选:
  - 服务器/离线/精度优先  -> 用 teacher  (real_kt_teacher.pt, 844K, AUC 0.711)
  - 端侧/实时/成本优先    -> 用 student  (real_kt_student.pt, 395K, AUC 0.731, 更快)

注意本管线实测里学生 AUC 反而更高 (蒸馏正则化), 所以默认 serving 用 student 即可;
teacher 的价值是"当裁判/oracle/继续蒸馏的底座", 而不是直接被调用来服务。

用法:
  PY=.../envs/distill/bin/python
  $PY use_real_model.py --which teacher     # 用真教师
  $PY use_real_model.py --which student     # 用真学生
  $PY use_real_model.py --which both        # 两个都跑做对比
"""
import argparse, math, time
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

DEVICE = "cpu"

# ===================== 与训练脚本完全同构的模型 =====================
class TimeDecayAttention(nn.Module):
    def __init__(self, d, heads):
        super().__init__()
        self.h, self.dk = heads, d // heads
        self.qkv = nn.Linear(d, 3 * d)
        self.o = nn.Linear(d, d)
        self.gamma = nn.Parameter(torch.ones(heads) * 0.1)
    def forward(self, x, cum_t, mask):
        B, L, D = x.shape
        qkv = self.qkv(x).view(B, L, 3, self.h, self.dk).permute(2, 0, 3, 1, 4)
        q, k, v = qkv[0], qkv[1], qkv[2]
        att = (q @ k.transpose(-2, -1)) / math.sqrt(self.dk)
        dt = (cum_t.unsqueeze(-1) - cum_t.unsqueeze(-2)).clamp(min=0)
        att = att - F.softplus(self.gamma).view(1, -1, 1, 1) * dt.unsqueeze(1)
        att = att.masked_fill(mask, float("-inf")).softmax(-1)
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
    def __init__(self, n_items, d=64, heads=4, layers=2, ff=128, max_len=200):
        super().__init__()
        self.item_emb = nn.Embedding(n_items, d, padding_idx=0)
        self.resp_emb = nn.Embedding(3, d)
        self.dt_proj = nn.Linear(1, d)
        self.blocks = nn.ModuleList([Block(d, heads, ff) for _ in range(layers)])
        self.norm = nn.LayerNorm(d)
        self.head = nn.Sequential(nn.Linear(2 * d, d), nn.GELU(), nn.Linear(d, 1))
        self.max_len = max_len
    def forward(self, items, resps, dts):
        B, L = items.shape
        hist_items = torch.cat([torch.zeros_like(items[:, :1]), items[:, :-1]], 1)
        hist_resps = torch.cat([torch.full_like(resps[:, :1], 2), resps[:, :-1]], 1)
        x = self.item_emb(hist_items) + self.resp_emb(hist_resps) \
            + self.dt_proj(torch.log1p(dts).unsqueeze(-1))
        cum_t = dts.cumsum(-1)
        causal = torch.triu(torch.ones(L, L, dtype=torch.bool, device=items.device), 1)
        for b in self.blocks:
            x = b(x, cum_t, causal.unsqueeze(0).unsqueeze(0))
        x = self.norm(x)
        cur = self.item_emb(items)
        return self.head(torch.cat([x, cur], -1)).squeeze(-1)

# ===================== 加载 =====================
def load_model(which="teacher"):
    path = "real_kt_teacher.pt" if which == "teacher" else "real_kt_student.pt"
    ck = torch.load(path, map_location=DEVICE)
    m = RealKT(ck["n_items"], ck["d"], 4, ck["layers"], ck["d"] * 2, 200)
    m.load_state_dict(ck["state_dict"]); m.eval()
    return m, ck["n_items"]

# ===================== 推理 API =====================
def predict_next(model, n_items, hist_items, hist_resps, hist_dts, next_item, next_dt):
    """
    给定历史作答, 预测"下一题答对概率"。

    hist_items : list[int]  历史做过的题 id (1..n_items), 长度 n
    hist_resps : list[int]  对应 0/1 (答错/答对),      长度 n
    hist_dts   : list[float] 每步距上一步的间隔(天),    长度 n, 首步填 0
    next_item  : int         要预测能否答对的下一题 id
    next_dt    : float       距上次作答的天数(遗忘用)
    返回: float, P(答对 next_item)
    """
    assert len(hist_items) == len(hist_resps) == len(hist_dts), "三个历史列表等长"
    items = hist_items + [int(next_item)]
    resps = hist_resps + [0]            # 末位只是占位(预测目标), 不参与历史
    dts   = hist_dts   + [float(next_dt)]
    it = torch.tensor([items], dtype=torch.long)
    rs = torch.tensor([resps], dtype=torch.long)
    dt = torch.tensor([dts], dtype=torch.float)
    with torch.no_grad():
        logit = model(it, rs, dt)[0, -1]     # 取最后一步(预测 next_item)
    return float(torch.sigmoid(logit))

# ===================== 演示 =====================
def demo(which):
    model, n_items = load_model(which)
    nparam = sum(p.numel() for p in model.parameters())
    # 从真实数据随机抽一条真实序列做演示 (没有数据就用手造例子)
    try:
        d = np.load("ednet_seqs.npz")
        items, resps, dts, lens = d["items"], d["resps"], d["dts"], d["lens"]
        i = int(np.random.default_rng().integers(0, len(lens)))
        L = int(lens[i])
        hi, hr = items[i, :L-1].tolist(), resps[i, :L-1].tolist()
        hd = dts[i, :L-1].tolist()
        nxt, ndt = int(items[i, L-1]), float(dts[i, L-1])
        src = f"真实 EdNet 序列 #{i}"
    except Exception:
        hi, hr = [100, 205, 77, 531], [1, 0, 1, 1]
        hd, nxt, ndt = [0, 1.5, 0.3, 2.0], 412, 3.0
        src = "手造示例"

    t0 = time.time()
    p = predict_next(model, n_items, hi, hr, hd, nxt, ndt)
    ms = (time.time() - t0) * 1000
    print(f"[{which}] 参数 {nparam/1e3:.0f}K | {src}")
    print(f"        历史({len(hi)}题): 题={hi} 对错={hr} 间隔天={[round(x,1) for x in hd]}")
    print(f"        预测 题#{nxt} (间隔{ndt:.1f}天) 答对概率 = {p:.3f}  | 延迟 {ms:.2f} ms")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--which", choices=["teacher", "student", "both"], default="both")
    a = ap.parse_args()
    for w in (["teacher", "student"] if a.which == "both" else [a.which]):
        demo(w)
