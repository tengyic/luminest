# -*- coding: utf-8 -*-
"""
export_torchscript.py — 把真学生导出为 TorchScript, 用于 iOS / Android 端侧部署

TorchScript 是 PyTorch 官方的端侧格式, 不需要 Python 运行时:
  - iOS: 用 PyTorch iOS 库直接 load
  - Android: 用 PyTorch Android 库直接 load
  - 服务端: 也能 torch.jit.load 跑, 比原始 nn.Module 更快更稳定

若要更小/更快, 还需 INT8 量化 + 嵌入表分解(见 INTEGRATION.md)。
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from use_real_model import RealKT, DEVICE
import torch

ck = torch.load("real_kt_student.pt", map_location=DEVICE)
m = RealKT(ck["n_items"], ck["d"], 4, ck["layers"], ck["d"] * 2, 200)
m.load_state_dict(ck["state_dict"]); m.eval()

L = 50   # 导出的固定序列长度上限(推理时不足会 pad, 过长需截断)
ex_it = torch.randint(0, ck["n_items"], (1, L), dtype=torch.long)
ex_rs = torch.randint(0, 3, (1, L), dtype=torch.long)
ex_dt = torch.rand(1, L)

with torch.no_grad():
    traced = torch.jit.trace(m, (ex_it, ex_rs, ex_dt))
traced.save("real_kt_student_ts.pt")
print("已导出 TorchScript: real_kt_student_ts.pt (可上 iOS/Android 端侧)")
