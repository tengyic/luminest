# -*- coding: utf-8 -*-
"""
demo_difficulty.py — 演示两件事:
  1) 你到底"输入"什么 (不是正确率数字, 是逐次作答序列)
  2) 题目难度是模型"学出来"的, 不是你喂进去的
     - 空历史时各题基础 P(对) 不同 = 模型内化的难度
     - 同一题对不同学生 P 不同 = 难度是"相对的"
"""
from kt_engine import KTEngine

e = KTEngine("student")

print("=== 1) 你输入的是: 逐次作答(题id, 对错, 间隔天), 不是'正确率'数字 ===")
hist_items, hist_resps, hist_dts = [], [], []
for qid, corr, gap in [(100, 1, 0.0), (205, 0, 1.5), (77, 1, 0.3)]:
    hist_items.append(qid); hist_resps.append(corr); hist_dts.append(gap)
    p = e.p_correct(hist_items, hist_resps, hist_dts, next_item=412, next_dt=2.0)
    print(f"  加到(题{qid},{'对' if corr else '错'})后 -> 题#412 P(对)={p:.3f}")

print("\n=== 2a) 难度是学出来的: 空历史下不同题的基础 P(对) 不同 ===")
print("   模型没被你告诉'哪题难', 但空历史时各题 P 已不同 = 内化的难度:")
for q in [100, 205, 77, 412, 531, 1263, 3284, 2888, 4385]:
    p = e.p_correct([], [], [], q, 0.0)
    tag = "难" if p < 0.4 else ("中" if p < 0.7 else "易")
    print(f"   题#{q:5d}  基础 P(对)={p:.3f}   [{tag}]")

print("\n=== 2b) 难度是相对的: 同一题(题#412)对不同学生 P 不同 ===")
strong = ([100, 205, 77], [1, 1, 1], [0.0, 1.0, 0.5])   # 全对的好学生
weak   = ([100, 205, 77], [0, 0, 0], [0.0, 1.0, 0.5])   # 全错的弱学生
ps = e.p_correct(*strong, 412, 2.0)
pw = e.p_correct(*weak, 412, 2.0)
print(f"   好学生历史 -> 题#412 P={ps:.3f}  (对他'较易')")
print(f"   弱学生历史 -> 题#412 P={pw:.3f}  (对他'较难')")
