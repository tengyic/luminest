# -*- coding: utf-8 -*-
"""
kt_engine.py — 把训练好的真教师/真学生封装成「自适应教学 APP 的 KT 大脑」

职责:
  输入 = 一个学生的作答历史 (题id, 对错, 间隔天)
  输出 = 1) 下一题答对概率 P(correct)
        2) 在候选题库里挑出「难度最合适」的下一题 (目标 P≈0.7)

你的 APP 不需要懂模型内部, 只调用:
  engine = KTEngine("student")                 # 或 "teacher"
  p = engine.p_correct(hist_items, hist_resps, hist_dts, next_item, next_dt)
  picks = engine.recommend(hist_items, hist_resps, hist_dts, candidate_ids, next_dt)

注: 当前真实模型是单头输出(只预测 P(correct))。第三代架构里的
「排复习(Head B 半衰期)」和「知识状态(Head C 技能画像)」需在模型上再加头,
见 INTEGRATION.md 的演进路线。
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from use_real_model import RealKT, DEVICE
import torch

class KTEngine:
    def __init__(self, which="student", model_dir=None):
        model_dir = model_dir or os.path.dirname(os.path.abspath(__file__))
        fname = "real_kt_teacher.pt" if which == "teacher" else "real_kt_student.pt"
        path = os.path.join(model_dir, fname)
        ck = torch.load(path, map_location=DEVICE)
        self.n_items = int(ck["n_items"])
        self.model = RealKT(self.n_items, ck["d"], 4, ck["layers"], ck["d"] * 2, 200)
        self.model.load_state_dict(ck["state_dict"])
        self.model.eval()
        self.which = which

    def p_correct(self, hist_items, hist_resps, hist_dts, next_item, next_dt):
        items = hist_items + [int(next_item)]
        resps = hist_resps + [0]            # 末位占位, 不参与历史
        dts   = hist_dts   + [float(next_dt)]
        it = torch.tensor([items], dtype=torch.long)
        rs = torch.tensor([resps], dtype=torch.long)
        dt = torch.tensor([dts], dtype=torch.float)
        with torch.no_grad():
            logit = self.model(it, rs, dt)[0, -1]
        return float(torch.sigmoid(logit))

    def recommend(self, hist_items, hist_resps, hist_dts, candidate_ids,
                  next_dt, target=0.70):
        """在候选题里挑 P(correct) 最接近 target 的题 (即最恰到好处的难度)。
        一次性批量打分, 高效。返回按「越接近目标难度越靠前」排序的列表。"""
        cand = [int(c) for c in candidate_ids]
        items = torch.tensor([hist_items + [c] for c in cand], dtype=torch.long)
        resps = torch.tensor([hist_resps + [0] for _ in cand], dtype=torch.long)
        dts   = torch.tensor([hist_dts + [float(next_dt)] for _ in cand], dtype=torch.float)
        with torch.no_grad():
            logits = self.model(items, resps, dts)[:, -1]
            ps = torch.sigmoid(logits)
        scored = sorted(zip(cand, ps.tolist()), key=lambda x: abs(x[1] - target))
        return [{"question_id": q, "p_correct": round(p, 4)} for q, p in scored]

if __name__ == "__main__":
    e = KTEngine("student")
    print(f"引擎加载: {e.which} | 题库 {e.n_items}")
    hi, hr, hd = [100, 205, 77, 531], [1, 0, 1, 1], [0.0, 1.5, 0.3, 2.0]
    p = e.p_correct(hi, hr, hd, 412, 3.0)
    print(f"下一题#412 答对概率 = {p:.3f}")
    picks = e.recommend(hi, hr, hd, [412, 77, 100, 205, 531], 3.0)
    print("候选难度排序(越靠前越接近目标难度0.7):")
    for x in picks:
        print(f"  题#{x['question_id']}  P={x['p_correct']}")
