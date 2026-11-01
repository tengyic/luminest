"""Invariant fixtures are for tests only; they are never used for model training."""
import hashlib
import importlib.util
import json
import math
import tempfile
import time
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from features import FEATURE_NAMES, causal_features, features_from_history
from kt_engine import DEFAULT_ARTIFACT, KTEngine
from train import design_matrix, file_hash, fit_vocabulary, load_ednet, load_opt_in, retain_earliest, split_students
from trained_pfa import TrainedPFA, sigmoid

MODEL_DIR = Path(__file__).resolve().parent


def fixture_model():
    return TrainedPFA({
        "schema_version": 1, "model_type": "regularized_kc_pfa",
        "feature_names": list(FEATURE_NAMES), "coefficients": [0.4, -0.3, 1.0, -0.1, -0.1],
        "intercept": 0.0, "kc_difficulty_biases": {"A": 0.25},
        "item_difficulty_biases": {"easy": -1.0, "hard": 1.0},
        "item_skills": {"easy": ["A"], "hard": ["A"]},
        "domain": "ednet_english_toeic", "license": "CC BY-NC 4.0", "research_only": True,
    })


def adapter_module():
    """The real adapter, imported as part of its own package.

    Loading it by file path gave it no parent package, so its own
    ``from .resources import resource_dir`` raised ImportError - these three tests were
    failing on an import, not on anything they assert. ``pytest.ini`` already puts
    ``backend`` on sys.path, so the package import is the honest one.
    """
    return importlib.import_module('app.adaptation')


class CausalTests(unittest.TestCase):
    def test_current_and_future_labels_do_not_affect_features(self):
        rows = [{"timestamp": t, "skill_ids": ("A",), "is_correct": y}
                for t, y in zip([1, 2, 3, 4], [1, 0, 1, 0])]
        original = causal_features(rows)
        for target in range(len(rows)):
            changed = [dict(row) for row in rows]
            for row in changed[target:]:
                row["is_correct"] = 1 - row["is_correct"]
            self.assertEqual(original[:target + 1], causal_features(changed)[:target + 1])

    def test_tied_timestamp_peer_does_not_leak(self):
        rows = [{"timestamp": 1, "skill_ids": ("A",), "is_correct": 1},
                {"timestamp": 1, "skill_ids": ("A",), "is_correct": 0},
                {"timestamp": 2, "skill_ids": ("A",), "is_correct": 1}]
        result = causal_features(rows)
        self.assertEqual(result[0], result[1])
        self.assertAlmostEqual(result[2][0], math.log(2))
        self.assertAlmostEqual(result[2][1], math.log(2))
        self.assertEqual(result[2][2], 0.5)

    def test_initial_features_and_cross_item_same_kc_transfer(self):
        rows = [{"timestamp": 1, "question_id": "first", "skill_ids": ("A",), "is_correct": 1},
                {"timestamp": 2, "question_id": "different", "skill_ids": ("A",), "is_correct": 0},
                {"timestamp": 3, "question_id": "unrelated", "skill_ids": ("B",), "is_correct": 1}]
        features = causal_features(rows)
        self.assertEqual(features[0], [0.0, 0.0, 0.5, 0.0, 0.0])
        self.assertAlmostEqual(features[1][0], math.log(2))
        self.assertEqual(features[1][1], 0.0)
        self.assertEqual(features[2][0], 0.0)
        self.assertEqual(features[2][1], 0.0)

    def test_history_reconstruction_parity_and_future_exclusion(self):
        rows = [{"timestamp": t * 86400, "skill_ids": ("A", "B"), "is_correct": y}
                for t, y in zip([1, 2, 3], [1, 0, 1])]
        for index, expected in enumerate(causal_features(rows)):
            self.assertEqual(expected, features_from_history(rows, ("A", "B"), rows[index]["timestamp"]))

    def test_split_disjoint_and_repeatable(self):
        frame = pd.DataFrame({"student_id": [f"student-{i}" for i in range(100)]})
        first, second = split_students(frame), split_students(frame)
        self.assertEqual(first, second)
        self.assertEqual([len(first[name]) for name in ("train", "validation", "test")], [80, 10, 10])
        self.assertFalse(first["train"] & first["validation"])
        self.assertFalse(first["train"] & first["test"])
        self.assertFalse(first["validation"] & first["test"])

    def test_earliest_chronological_truncation(self):
        frame = pd.DataFrame({"student_id": ["one"] * 30, "question_id": [str(i) for i in range(30)],
                              "timestamp": list(reversed(range(30)))})
        kept = retain_earliest(frame, 20)
        self.assertEqual(kept["timestamp"].tolist(), list(range(20)))

    def test_vocab_and_matrix_exclude_held_out_identifiers(self):
        train_frame = pd.DataFrame({"question_id": ["known"], "skill_ids": [("A",)]})
        skills, items = fit_vocabulary(train_frame)
        held_out = pd.DataFrame({"question_id": ["held-out"], "skill_ids": [("held-out-KC",)]})
        matrix = design_matrix(held_out, np.zeros((1, 5)), skills, items)
        self.assertEqual(matrix.nnz, 0)
        self.assertEqual(set(skills), {"A"})
        self.assertEqual(set(items), {"known"})


class RuntimeTests(unittest.TestCase):
    def test_monotonic_learned_item_bias(self):
        model = fixture_model()
        values = [0.5, 0.1, 0.6, 0.0, 0.0]
        easy = model.p_correct(features=values, skill_id="A", item_id="easy")
        hard = model.p_correct(features=values, skill_id="A", item_id="hard")
        self.assertGreater(easy, hard)
        biases = [-100, -3, 0, 3, 100]
        probabilities = [sigmoid(0.3, bias) for bias in biases]
        self.assertEqual(probabilities, sorted(probabilities, reverse=True))

    def test_unknown_item_and_kc_use_generic_coefficients(self):
        model = fixture_model()
        values = [0.5, 0.2, 0.6, 0.4, 0.3]
        expected = sigmoid(sum(w*x for w, x in zip(model.coefficients, values)))
        self.assertAlmostEqual(model.p_correct(features=values, skill_id="newKC", item_id="newItem"), expected)
        response = model.predict({"domain": model.domain, "features": values},
                                 {"question_id": "newItem", "concept_id": "newKC"})
        self.assertTrue(response["cold_start"])
        self.assertEqual(response["known_kc_count"], 0)

    def test_research_predictor_rejects_math(self):
        with self.assertRaisesRegex(ValueError, "outside"):
            fixture_model().predict({"domain": "math"}, {"question_id": "easy"})

    def test_invalid_feature_boundary(self):
        with self.assertRaises(ValueError):
            fixture_model().p_correct(features=[float("nan")] * 5)
        with self.assertRaises(ValueError):
            fixture_model().p_correct(features=[1, 2])

    def test_math_default_and_opt_in_domain_gate(self):
        adapter = adapter_module()
        result = adapter.predict({"allow_research_model": True}, {"domain": "math", "id": "easy"})
        self.assertEqual(result["model"], "unvalidated_bkt_irt_prior")
        self.assertIsNone(result["validated_domain"])
        self.assertFalse(result["trained"])
        self.assertFalse(adapter.MODEL_METADATA["validated_for_math"])
        self.assertAlmostEqual(result["p_correct"], 0.25 + 0.65 * 0.15)
        result = adapter.predict({}, {"domain": "ednet_english_toeic", "id": "easy"})
        self.assertEqual(result["model"], "unvalidated_bkt_irt_prior")

    def test_math_irt_prior_monotonic_bias(self):
        adapter = adapter_module()
        low = adapter.predict({"theta": 0.4}, {"difficulty_bias": -1})["p_correct"]
        high = adapter.predict({"theta": 0.4}, {"difficulty_bias": 1})["p_correct"]
        self.assertGreater(low, high)

    def test_real_artifact_load_and_evidence(self):
        model = TrainedPFA.load(DEFAULT_ARTIFACT)
        provenance = json.loads((MODEL_DIR / "provenance.json").read_text())
        metrics = json.loads((MODEL_DIR / "metrics.json").read_text())
        self.assertTrue(provenance["actual_training"])
        self.assertEqual(hashlib.sha256(DEFAULT_ARTIFACT.read_bytes()).hexdigest(), provenance["artifact_sha256"])
        for name, expected_hash in provenance["training_source_sha256"].items():
            self.assertEqual(hashlib.sha256((MODEL_DIR / name).read_bytes()).hexdigest(), expected_hash)
        self.assertEqual(provenance["synthetic_training_rows"], 0)
        self.assertTrue(provenance["disjoint_students"])
        self.assertGreater(provenance["selected_rows"], 20000)
        self.assertGreater(metrics["evaluation"]["test"]["trained_pfa"]["auc"], 0.5)
        self.assertEqual(model.domain, "ednet_english_toeic")
        self.assertTrue(model.research_only)
        self.assertEqual(model.license, "CC BY-NC 4.0")
        self.assertLess(metrics["evaluation"]["test"]["json_inference_max_abs_error"], 1e-10)
        item = next(iter(model.item_biases))
        p = model.p_correct([], item_id=item)
        self.assertTrue(0 < p < 1)
        ordered = sorted(model.item_biases, key=model.item_biases.get)
        common_features = [0, 0, 0.5, 0, 0]
        self.assertGreaterEqual(model.p_correct(features=common_features, skill_id="unknown", item_id=ordered[0]),
                                model.p_correct(features=common_features, skill_id="unknown", item_id=ordered[-1]))

    def test_real_data_reconstructs_splits_vocab_features_and_hashes(self):
        provenance = json.loads((MODEL_DIR / "provenance.json").read_text())
        self.assertEqual(file_hash(provenance["data_path"]), provenance["data_sha256"])
        self.assertEqual(file_hash(provenance["questions_path"]), provenance["questions_sha256"])
        frame, _ = load_ednet(provenance["data_path"], provenance["questions_path"],
                              provenance["max_users"], provenance["max_rows_per_student"])
        frame = retain_earliest(frame, provenance["max_rows_per_student"])
        splits = split_students(frame, provenance["seed"])
        model = TrainedPFA.load(DEFAULT_ARTIFACT)
        train_frame = frame[frame["student_id"].isin(splits["train"])]
        skills, items = fit_vocabulary(train_frame)
        self.assertEqual(set(skills), set(model.kc_biases))
        self.assertEqual(set(items), set(model.item_biases))
        self.assertEqual(len(frame), provenance["selected_rows"])
        for name, students in splits.items():
            digest = hashlib.sha256(json.dumps(sorted(students), sort_keys=True,
                                               separators=(",", ":")).encode()).hexdigest()
            self.assertEqual(digest, provenance["split"][name]["student_ids_sha256"])
        for uid in list(sorted(splits["test"]))[:5]:
            rows = frame[frame["student_id"] == uid].to_dict("records")
            for row, expected in zip(rows, causal_features(rows)):
                actual = features_from_history(rows, row["skill_ids"], row["timestamp"], model.item_skills)
                self.assertEqual(actual, expected)
                for_features = model.p_correct(features=expected, skill_id=row["skill_ids"], item_id=row["question_id"])
                for_history = model.p_correct(rows, row["skill_ids"], row["question_id"], timestamp=row["timestamp"])
                self.assertAlmostEqual(for_history, for_features, places=13)

    def test_real_engine_compatibility_and_recommend(self):
        engine = KTEngine.load(DEFAULT_ARTIFACT)
        ids = list(engine.model.item_biases)[:4]
        p = engine.p_correct(ids[:2], [1, 0], [0, 1], ids[2], 1)
        self.assertTrue(0 < p < 1)
        recommendations = engine.recommend(ids[:2], [1, 0], [0, 1], ids, 1)
        distances = [abs(result["p_correct"] - 0.7) for result in recommendations]
        self.assertEqual(distances, sorted(distances))
        self.assertTrue(all(result["research_only"] for result in recommendations))

    def test_real_adapter_requires_explicit_research_domain(self):
        adapter = adapter_module()
        result = adapter.predict({"allow_research_model": True, "history": []},
                                 {"domain": "ednet_english_toeic", "question_id": "new-question", "concept_id": "new-skill"})
        self.assertEqual(result["model"], "trained_kc_pfa")
        self.assertEqual(result["validated_domain"], "ednet_english_toeic")
        self.assertTrue(result["research_only"])
        self.assertTrue(result["cold_start"])

    def test_no_consent_no_csv_training(self):
        with self.assertRaisesRegex(ValueError, "consent"):
            load_opt_in("not-read.csv", None, 1500)
        # Negative attestation fixture only: no generated log is trained here.
        with tempfile.TemporaryDirectory(dir=MODEL_DIR) as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps({"consent_verified": False, "ownership_verified": True}))
            with self.assertRaisesRegex(ValueError, "verification"):
                load_opt_in("not-read.csv", path, 1500)


if __name__ == "__main__":
    started = time.perf_counter()
    suite = unittest.defaultTestLoader.loadTestsFromModule(__import__(__name__))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    evidence = {
        "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
        "skipped": len(result.skipped), "passed": result.wasSuccessful(),
        "wall_seconds": time.perf_counter() - started,
        "test_source_sha256": file_hash(__file__), "artifact_sha256": file_hash(DEFAULT_ARTIFACT),
        "command": [__import__("sys").executable, str(Path(__file__).resolve())],
        "scope": "Causality, timestamp ties, train-only vocab, disjoint students, real-data reconstruction, JSON parity, domain gates, monotonic bias, cold starts, consent rejection",
        "fixtures": "Invariant fixtures only; zero synthetic training rows",
    }
    (MODEL_DIR / "test_results.json").write_text(json.dumps(evidence, indent=2) + "\n")
    raise SystemExit(0 if result.wasSuccessful() else 1)
