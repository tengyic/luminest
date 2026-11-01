"""Real-data training CLI. EdNet parquet or verified, owner-controlled opt-in CSV."""
import argparse
import hashlib
import json
import platform
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow
import pyarrow.parquet as pq
import scipy
from scipy import sparse
import sklearn
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from threadpoolctl import threadpool_limits

try:
    from .features import FEATURE_NAMES, causal_features, parse_skills
    from .trained_pfa import TrainedPFA
except ImportError:
    from features import FEATURE_NAMES, causal_features, parse_skills
    from trained_pfa import TrainedPFA


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def json_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def validate_logs(frame):
    columns = {"student_id", "question_id", "is_correct", "timestamp"}
    if not columns.issubset(frame.columns) or frame.empty:
        raise ValueError("Missing required log columns or empty data")
    if frame[list(columns)].isna().any().any():
        raise ValueError("Log fields cannot be null")
    if not frame["is_correct"].isin([0, 1, False, True]).all():
        raise ValueError("is_correct must be 0 or 1")
    frame = frame.copy()
    frame["timestamp"] = pd.to_numeric(frame["timestamp"], errors="raise")
    if not np.isfinite(frame["timestamp"].to_numpy(dtype=float)).all():
        raise ValueError("Timestamps must be finite")
    for name in ("student_id", "question_id"):
        frame[name] = frame[name].astype(str)
        if frame[name].str.strip().eq("").any():
            raise ValueError("Identifiers cannot be empty")
    frame["is_correct"] = frame["is_correct"].astype(int)
    return frame


def load_ednet(data, questions, max_users, max_per_user):
    if not questions:
        raise ValueError("EdNet requires --questions with actual tags")
    metadata = pd.read_csv(questions, dtype={"question_id": str, "tags": str})
    if not {"question_id", "tags", "correct_answer"}.issubset(metadata.columns):
        raise ValueError("Invalid EdNet question metadata")
    if metadata["question_id"].duplicated().any():
        raise ValueError("Duplicate question metadata")
    tag_map = {str(row.question_id): parse_skills(row.tags) for row in metadata.itertuples()}
    answer_map = dict(zip(metadata["question_id"], metadata["correct_answer"]))
    parquet = pq.ParquetFile(data)
    required = ["subject_id", "question_id", "timestamp", "user_answer"]
    if not set(required).issubset(parquet.schema_arrow.names):
        raise ValueError("Unsupported EdNet parquet schema")
    users = set()
    selected = []
    scanned = 0
    unmatched = 0
    for batch in parquet.iter_batches(batch_size=65536, columns=required):
        frame = batch.to_pandas()
        scanned += len(frame)
        for uid in frame["subject_id"].unique():
            if len(users) < max_users:
                users.add(str(uid))
            else:
                break
        frame = frame[frame["subject_id"].isin(users)].copy()
        if frame.empty:
            continue
        answers = frame["question_id"].map(answer_map)
        valid = answers.notna() & frame["user_answer"].notna()
        unmatched += int((~valid).sum())
        frame = frame[valid].copy()
        frame["is_correct"] = (frame["user_answer"] == answers[valid]).astype(int)
        frame = frame.rename(columns={"subject_id": "student_id"})
        # Batch-local truncation is safe: discarded rows already have at least N earlier peers.
        frame = frame.sort_values(["student_id", "timestamp"], kind="stable")
        selected.append(frame.groupby("student_id", sort=False).head(max_per_user)[
            ["student_id", "question_id", "timestamp", "is_correct"]])
    if not selected:
        raise ValueError("No eligible EdNet rows")
    frame = validate_logs(pd.concat(selected, ignore_index=True))
    frame["timestamp"] = frame["timestamp"].astype(float) / 1000.0
    frame["skill_ids"] = frame["question_id"].map(tag_map)
    if frame["skill_ids"].isna().any():
        raise ValueError("Question tags unavailable")
    return frame, {"source_rows_scanned": scanned, "unmatched_answer_rows_dropped": unmatched,
                   "source_students_selected_before_min_length_filter": len(users),
                   "timestamp_input_unit": "milliseconds", "selected_users_policy": "first_encountered_then_seeded_disjoint_split"}


def load_opt_in(data, consent_manifest, max_users):
    if not consent_manifest:
        raise ValueError("Owner opt-in CSV requires --consent-manifest")
    manifest = json.loads(Path(consent_manifest).read_text(encoding="utf-8"))
    if manifest.get("consent_verified") is not True or manifest.get("ownership_verified") is not True:
        raise ValueError("Consent and ownership verification are required")
    if manifest.get("data_sha256") != file_hash(data):
        raise ValueError("Consent manifest is not bound to this CSV")
    domain = manifest.get("domain")
    if not isinstance(domain, str) or not domain.strip() or domain == "ednet_english_toeic":
        raise ValueError("An explicit non-EdNet domain is required")
    if manifest.get("timestamp_unit") != "seconds" or not manifest.get("source_license"):
        raise ValueError("Manifest requires timestamp_unit=seconds and source_license")
    frame = pd.read_csv(data, dtype={"student_id": str, "question_id": str, "concept_id": str})
    if "concept_id" not in frame or frame["concept_id"].isna().any():
        raise ValueError("Opt-in CSV requires concept_id")
    frame = validate_logs(frame)
    allowed = {str(uid) for uid in manifest.get("opt_in_student_ids", [])}
    if not set(frame["student_id"]).issubset(allowed):
        raise ValueError("Every CSV student must have verified opt-in")
    frame["skill_ids"] = frame["concept_id"].map(parse_skills)
    if any(not skills for skills in frame["skill_ids"]):
        raise ValueError("Concept IDs cannot be empty")
    consistency = frame.groupby("question_id")["skill_ids"].nunique()
    if (consistency > 1).any():
        raise ValueError("Each question must have a consistent concept mapping")
    users = sorted(frame["student_id"].unique())[:max_users]
    frame = frame[frame["student_id"].isin(users)].copy()
    return frame, manifest


def retain_earliest(frame, max_per_user, min_per_user=20):
    frame = frame.sort_values(["student_id", "timestamp"], kind="stable")
    counts = frame.groupby("student_id")["question_id"].transform("size")
    frame = frame[counts >= min_per_user]
    return frame.groupby("student_id", sort=False).head(max_per_user).reset_index(drop=True)


def split_students(frame, seed=42):
    users = sorted(frame["student_id"].unique())
    if len(users) < 30:
        raise ValueError("At least 30 eligible students are required for held-out evaluation")
    users = np.random.default_rng(seed).permutation(users).tolist()
    n_test = max(1, len(users) // 10)
    n_val = max(1, len(users) // 10)
    return {"train": set(users[n_test + n_val:]), "validation": set(users[n_test:n_test + n_val]),
            "test": set(users[:n_test])}


def build_features(frame):
    output = np.empty((len(frame), len(FEATURE_NAMES)), dtype=float)
    for _, group in frame.groupby("student_id", sort=False):
        output[group.index.to_numpy()] = causal_features(group.to_dict("records"))
    return output


def fit_vocabulary(frame):
    skills = sorted({s for tags in frame["skill_ids"] for s in tags})
    items = sorted(frame["question_id"].unique())
    return {skill: index for index, skill in enumerate(skills)}, {item: index for index, item in enumerate(items)}


def design_matrix(frame, features, skill_vocab, item_vocab):
    rows, columns, values = [], [], []
    offset = len(FEATURE_NAMES)
    item_offset = offset + len(skill_vocab)
    for row_index, (tags, item) in enumerate(zip(frame["skill_ids"], frame["question_id"])):
        for tag in tags:
            if tag in skill_vocab:
                rows.append(row_index)
                columns.append(offset + skill_vocab[tag])
                values.append(1.0 / len(tags))
        if item in item_vocab:
            rows.append(row_index)
            columns.append(item_offset + item_vocab[item])
            values.append(1.0)
    biases = sparse.coo_matrix((values, (rows, columns)),
                              shape=(len(frame), item_offset + len(item_vocab))).tocsr()
    numeric = sparse.hstack([sparse.csr_matrix(features),
                             sparse.csr_matrix((len(frame), len(skill_vocab) + len(item_vocab)))], format="csr")
    return numeric + biases


def scores(y, p):
    return {"auc": float(roc_auc_score(y, p)) if len(np.unique(y)) == 2 else None,
            "brier": float(brier_score_loss(y, p)),
            "logloss": float(log_loss(y, p, labels=[0, 1]))}


def calibration(y, p):
    result = []
    indices = np.minimum((p * 10).astype(int), 9)
    for index in range(10):
        mask = indices == index
        count = int(mask.sum())
        result.append({"lower": index / 10, "upper": (index + 1) / 10, "count": count,
                       "mean_prediction": float(p[mask].mean()) if count else None,
                       "observed_accuracy": float(y[mask].mean()) if count else None})
    return result


def benchmark(path, features, frame):
    before = time.perf_counter()
    model = TrainedPFA.load(path)
    load_ms = (time.perf_counter() - before) * 1000
    examples = [(x.tolist(), tags, item) for x, tags, item in
                zip(features[:1000], frame["skill_ids"].iloc[:1000], frame["question_id"].iloc[:1000])]
    for x, tags, item in examples[:50]:
        model.p_correct(features=x, skill_id=tags, item_id=item)
    times = []
    before = time.perf_counter()
    for _ in range(5):
        for x, tags, item in examples:
            start = time.perf_counter_ns()
            model.p_correct(features=x, skill_id=tags, item_id=item)
            times.append((time.perf_counter_ns() - start) / 1000)
    seconds = time.perf_counter() - before
    # Benchmark a separate 80-response-history reconstruction path, not just the dot product.
    group = frame[frame["student_id"] == frame.iloc[0]["student_id"]]
    history = group.to_dict("records")
    target = history[-1]
    history_times = []
    for _ in range(200):
        start = time.perf_counter_ns()
        model.p_correct(history, target["skill_ids"], target["question_id"],
                        timestamp=float(target["timestamp"]) + 86400)
        history_times.append((time.perf_counter_ns() - start) / 1000)
    return {"measured": True, "platform": platform.platform(), "python": platform.python_version(),
            "model_load_ms": load_ms, "feature_predict_calls": len(times),
            "feature_predict_p50_us": float(np.percentile(times, 50)),
            "feature_predict_p95_us": float(np.percentile(times, 95)),
            "feature_predict_calls_per_second": len(times) / seconds,
            "history_length": len(history), "history_predict_calls": 200,
            "history_predict_p50_us": float(np.percentile(history_times, 50)),
            "history_predict_p95_us": float(np.percentile(history_times, 95))}


def train(args):
    started = time.perf_counter()
    data = Path(args.data).resolve()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    is_ednet = data.suffix.lower() == ".parquet"
    if is_ednet:
        frame, source_info = load_ednet(data, args.questions, args.max_users, args.max_per_user)
        domain, license_name, research_only = "ednet_english_toeic", "CC BY-NC 4.0", True
    elif data.suffix.lower() == ".csv":
        frame, source_info = load_opt_in(data, args.consent_manifest, args.max_users)
        domain = source_info["domain"]
        license_name = source_info["source_license"]
        # Consent does not establish commercial rights or deployment certification.
        research_only = True
    else:
        raise ValueError("Use original EdNet parquet or verified opt-in CSV; NPZ is not auditable")
    frame = retain_earliest(frame, args.max_per_user)
    splits = split_students(frame, args.seed)
    masks = {name: frame["student_id"].isin(users).to_numpy() for name, users in splits.items()}
    features = build_features(frame)
    train_frame = frame[masks["train"]]
    skill_vocab, item_vocab = fit_vocabulary(train_frame)
    mean = features[masks["train"]].mean(axis=0)
    scale = features[masks["train"]].std(axis=0)
    scale[scale < 1e-8] = 1.0
    matrix = design_matrix(frame, (features - mean) / scale, skill_vocab, item_vocab)
    labels = frame["is_correct"].to_numpy()
    if len(np.unique(labels[masks["train"]])) != 2:
        raise ValueError("Training requires both response classes")
    trials = []
    best = None
    with threadpool_limits(limits=1):
        for regularization in (0.1, 1.0, 10.0):
            estimator = LogisticRegression(C=regularization, solver="lbfgs", max_iter=300, tol=1e-5)
            with warnings.catch_warnings(record=True) as captured:
                warnings.simplefilter("always", ConvergenceWarning)
                estimator.fit(matrix[masks["train"]], labels[masks["train"]])
            converged = not any(issubclass(w.category, ConvergenceWarning) for w in captured)
            p = estimator.predict_proba(matrix[masks["validation"]])[:, 1]
            result = scores(labels[masks["validation"]], p)
            trials.append({"C": regularization, "validation": result,
                           "converged": converged, "iterations": int(estimator.n_iter_[0])})
            print(json.dumps(trials[-1]), flush=True)
            if converged and (best is None or result["logloss"] < best[0]):
                best = (result["logloss"], estimator, regularization)
        if best is None:
            raise RuntimeError("No candidate converged; refusing to export an unfinished fit")
        estimator = best[1]
        numeric_baseline = LogisticRegression(C=1.0, solver="lbfgs", max_iter=300)
        numeric_baseline.fit(features[masks["train"]], labels[masks["train"]])
        item_baseline = LogisticRegression(C=best[2], solver="lbfgs", max_iter=300)
        item_baseline.fit(matrix[masks["train"], len(FEATURE_NAMES) + len(skill_vocab):], labels[masks["train"]])
    weights = estimator.coef_[0]
    coefficients = weights[:len(FEATURE_NAMES)] / scale
    intercept = float(estimator.intercept_[0] - np.dot(coefficients, mean))
    selected_rows_hash = hashlib.sha256(frame.assign(skill_ids=frame["skill_ids"].map(lambda x: ";".join(x)))
                                        .to_csv(index=False, lineterminator="\n").encode()).hexdigest()
    data_sha = file_hash(data)
    questions_sha = file_hash(args.questions) if is_ednet else None
    training_sources = {name: file_hash(Path(__file__).resolve().parent / name)
                        for name in ("train.py", "features.py", "trained_pfa.py")}
    reproducible_command = [sys.executable, str(Path(__file__).resolve()), "--data", str(data),
                            "--out", str(out), "--max-users", str(args.max_users),
                            "--max-per-user", str(args.max_per_user), "--seed", str(args.seed)]
    if is_ednet:
        reproducible_command += ["--questions", str(Path(args.questions).resolve())]
    else:
        reproducible_command += ["--consent-manifest", str(Path(args.consent_manifest).resolve())]
    artifact = {
        "schema_version": 1, "model_type": "regularized_kc_pfa", "domain": domain,
        "license": license_name, "research_only": research_only,
        "feature_names": list(FEATURE_NAMES), "coefficients": coefficients.tolist(), "intercept": intercept,
        "kc_difficulty_biases": {skill: float(-weights[len(FEATURE_NAMES) + index]) for skill, index in skill_vocab.items()},
        "item_difficulty_biases": {item: float(-weights[len(FEATURE_NAMES) + len(skill_vocab) + index]) for item, index in item_vocab.items()},
        "item_skills": {str(row.question_id): list(row.skill_ids)
                        for row in train_frame.drop_duplicates("question_id").itertuples()},
        "prediction_equation": "sigmoid(intercept + dot(coefficients, causal_features) - mean(kc_biases) - item_bias)",
        "unknown_bias": 0.0, "timestamp_unit": "seconds", "gap_unit": "days",
        "source_data_sha256": data_sha, "questions_sha256": questions_sha,
        "selected_rows_sha256": selected_rows_hash, "regularization_C": best[2],
        "training_source_sha256": training_sources,
        "attribution": "EdNet: A Large-Scale Hierarchical Dataset in Education; Choi et al.; Santa/TOEIC interactions" if is_ednet else "Owner-controlled, consent-verified domain logs",
        "validation_scope": "held_out_students_same_source_not_external_domain",
    }
    artifact_path = out / "research" / "ednet_pfa.json" if is_ednet else out / "domain_pfa.json"
    write_json(artifact_path, artifact)
    baseline_probability = float(labels[masks["train"]].mean())
    evaluation = {}
    runtime = TrainedPFA.load(artifact_path)
    for name, mask in masks.items():
        y = labels[mask]
        p = estimator.predict_proba(matrix[mask])[:, 1]
        numeric_p = numeric_baseline.predict_proba(features[mask])[:, 1]
        item_p = item_baseline.predict_proba(matrix[mask, len(FEATURE_NAMES) + len(skill_vocab):])[:, 1]
        indices = np.flatnonzero(mask)[:200]
        runtime_p = np.array([runtime.p_correct(features=features[i], skill_id=frame.iloc[i]["skill_ids"],
                                               item_id=frame.iloc[i]["question_id"]) for i in indices])
        parity_error = float(np.max(np.abs(runtime_p - p[:len(indices)])))
        if parity_error > 1e-10:
            raise RuntimeError("Exported JSON inference differs from fitted estimator")
        unknown_item = ~frame.loc[mask, "question_id"].isin(item_vocab).to_numpy()
        evaluation[name] = {
            "students": len(splits[name]), "rows": int(mask.sum()), "accuracy_rate": float(y.mean()),
            "trained_pfa": scores(y, p),
            "baseline_train_prevalence": scores(y, np.full(len(y), baseline_probability)),
            "baseline_causal_history_only": scores(y, numeric_p), "baseline_item_only": scores(y, item_p),
            "calibration_bins": calibration(y, p), "json_inference_max_abs_error": parity_error,
            "unknown_item_rows": int(unknown_item.sum()),
            "unknown_item_scores": scores(y[unknown_item], p[unknown_item]) if unknown_item.any() else None,
            "unknown_kc_rows": sum(any(s not in skill_vocab for s in tags) for tags in frame.loc[mask, "skill_ids"]),
        }
    metrics = {"schema_version": 1, "domain": domain, "evaluation": evaluation,
               "hyperparameter_selection": "validation_logloss_only; test_never_used_for_selection",
               "candidates": trials, "selected_C": best[2], "baseline_probability": baseline_probability,
               "benchmark": benchmark(artifact_path, features[masks["test"]], frame[masks["test"]].reset_index(drop=True)),
               "training_wall_seconds": time.perf_counter() - started,
               "artifact_path": str(artifact_path.relative_to(out)), "artifact_sha256": file_hash(artifact_path)}
    provenance = {
        "schema_version": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "actual_training": True, "synthetic_training_rows": 0, "domain": domain,
        "research_only": research_only, "license": license_name,
        "attribution": artifact["attribution"], "data_path": str(data), "data_sha256": data_sha,
        "questions_path": str(Path(args.questions).resolve()) if is_ednet else None,
        "questions_sha256": questions_sha, "selected_rows_sha256": selected_rows_hash,
        "artifact_sha256": metrics["artifact_sha256"],
        "seed": args.seed, "max_users": args.max_users, "max_rows_per_student": args.max_per_user,
        "min_rows_per_student": 20, "selected_rows": len(frame),
        "split": {name: {"students": len(users), "rows": int(masks[name].sum()),
                         "student_ids_sha256": json_hash(sorted(users))} for name, users in splits.items()},
        "disjoint_students": not (splits["train"] & splits["validation"] or splits["train"] & splits["test"] or splits["validation"] & splits["test"]),
        "feature_policy": "strictly_prior_timestamps; tied timestamps featurized as a group before updates; earliest N retained",
        "evaluation_protocol": "online one-step predictions; earlier held-out student outcomes may update history; no held-out fit",
        "vocabulary_policy": "KC and item biases fit training students only; shared coefficients and zero unknown biases",
        "kc_count": len(skill_vocab), "item_count": len(item_vocab),
        "learned_difficulty": "regularized KC and item intercepts; no manual difficulty feature",
        "source_info": source_info if is_ednet else {"manifest_sha256": file_hash(args.consent_manifest), "consent_verified": True,
                                                      "ownership_verified": True, "timestamp_input_unit": "seconds"},
        "raw_data_included": False,
        "dependencies": {"numpy": np.__version__, "pandas": pd.__version__, "scikit_learn": sklearn.__version__,
                         "pyarrow": pyarrow.__version__, "scipy": scipy.__version__},
        "training_command": reproducible_command,
        "training_source_sha256": training_sources,
        "consent_verification_boundary": "Trusted worker caller attests ledger verification; unsigned manifests alone are not independent proof" if not is_ednet else None,
        "limitations": ["EdNet English/TOEIC is not evidence for mathematics" if is_ednet else "Only same-source held-out students evaluated",
                        "No commercial rights or readiness certification", "NC source and derivative research artifact must remain separate",
                        "First-encounter student subsample is not population representative", "No external or prospective validation",
                        "Observed histories and item effects are predictive associations, not causal treatment effects",
                        "Cold-start unknown KC and item effects are zero, not learned domain-specific difficulty"],
    }
    write_json(out / "metrics.json", metrics)
    write_json(out / "provenance.json", provenance)
    print(json.dumps({"artifact": str(artifact_path), "test": evaluation["test"]["trained_pfa"],
                      "wall_seconds": metrics["training_wall_seconds"]}), flush=True)
    return metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True)
    parser.add_argument("--questions")
    parser.add_argument("--out", required=True)
    parser.add_argument("--max-users", type=int, default=1500)
    parser.add_argument("--max-per-user", type=int, default=80)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--consent-manifest")
    args = parser.parse_args()
    if args.max_users < 30 or args.max_per_user < 20:
        parser.error("Require max-users >= 30 and max-per-user >= 20")
    train(args)


if __name__ == "__main__":
    main()
