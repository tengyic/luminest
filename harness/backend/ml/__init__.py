"""Math model training path: dataset handling, baselines, honest evaluation.

This is the skeleton for training a mathematics knowledge-tracing model, with a
correct held-out-by-student protocol (never split by row -- that leaks a
student's history across the split and inflates AUC).

Status: SKELETON. No production math model is trained or shipped this round;
see outputs/impl/u1_model_memory.md for the dataset/license analysis that
gates any commercial use.
"""
