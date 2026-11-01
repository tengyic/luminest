# -*- coding: utf-8 -*-
"""
kt_service.py — 把 KTEngine 包成 HTTP 服务, 你的 APP 直接 POST 调用

启动:
  pip install fastapi uvicorn
  uvicorn kt_service:app --host 0.0.0.0 --port 8000

你的 APP 这样接:
  POST /predict      # 预测某题答对概率
  POST /recommend    # 从候选题里挑最合适的下一题
  GET  /health       # 健康检查
"""
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List
from kt_engine import KTEngine

app = FastAPI(title="Adaptive KT Engine")

# 生产可改 "teacher", 或做混合(默认 student 端侧友好)
engine = KTEngine("student")

class History(BaseModel):
    hist_items: List[int]          # 历史做过的题 id
    hist_resps: List[int]          # 对应 0/1 (答错/答对)
    hist_dts:   List[float]        # 每步距上一步天数, 首步填 0
    next_dt:    float = 0.0        # 距上次作答的天数(遗忘用)

class PredictReq(History):
    next_item: int                 # 要预测能否答对的题

class RecommendReq(History):
    candidate_ids: List[int]       # 候选题库
    target: float = 0.70           # 目标难度(答对概率)

@app.post("/predict")
def predict(r: PredictReq):
    p = engine.p_correct(r.hist_items, r.hist_resps, r.hist_dts,
                         r.next_item, r.next_dt)
    return {"question_id": r.next_item, "p_correct": round(p, 4)}

@app.post("/recommend")
def recommend(r: RecommendReq):
    picks = engine.recommend(r.hist_items, r.hist_resps, r.hist_dts,
                             r.candidate_ids, r.next_dt, r.target)
    return {"recommended": picks}

@app.get("/health")
def health():
    return {"status": "ok", "model": engine.which, "n_items": engine.n_items}
