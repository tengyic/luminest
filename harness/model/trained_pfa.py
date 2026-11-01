"""Dependency-free inference for JSON logistic/PFA artifacts; no pickle or torch."""
import json
import math
from pathlib import Path

try:
    from .features import FEATURE_NAMES, features_from_history, parse_skills
except ImportError:
    from features import FEATURE_NAMES, features_from_history, parse_skills


def sigmoid(theta, bias=0.0):
    value = float(theta) - float(bias)
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exp_value = math.exp(value)
    return exp_value / (1.0 + exp_value)


class TrainedPFA:
    def __init__(self, artifact):
        if artifact.get("schema_version") != 1 or artifact.get("model_type") != "regularized_kc_pfa":
            raise ValueError("Unsupported model artifact")
        if artifact.get("feature_names") != list(FEATURE_NAMES):
            raise ValueError("Feature schema mismatch")
        self.artifact = artifact
        self.coefficients = [float(x) for x in artifact["coefficients"]]
        self.intercept = float(artifact["intercept"])
        self.kc_biases = {str(k): float(v) for k, v in artifact["kc_difficulty_biases"].items()}
        self.item_biases = {str(k): float(v) for k, v in artifact["item_difficulty_biases"].items()}
        self.item_skills = artifact["item_skills"]
        self.domain = artifact["domain"]
        self.license = artifact["license"]
        self.research_only = bool(artifact["research_only"])
        values = self.coefficients + [self.intercept] + list(self.kc_biases.values()) + list(self.item_biases.values())
        if len(self.coefficients) != len(FEATURE_NAMES) or not all(math.isfinite(v) for v in values):
            raise ValueError("Invalid model coefficients")

    @classmethod
    def load(cls, path):
        with Path(path).open(encoding="utf-8") as stream:
            return cls(json.load(stream))

    def p_correct(self, hist=None, skill_id=None, item_id=None, *, features=None,
                  timestamp=None, next_dt=0.0):
        item_id = str(item_id) if item_id is not None else ""
        skills = parse_skills(skill_id) if skill_id is not None else parse_skills(self.item_skills.get(item_id))
        if features is None:
            if isinstance(hist, dict):
                if "features" in hist:
                    features = hist["features"]
                elif any(key in hist for key in FEATURE_NAMES):
                    features = hist
                else:
                    timestamp = hist.get("timestamp", timestamp)
                    hist = hist.get("history", [])
            elif hist is not None and len(hist) == len(FEATURE_NAMES) and all(isinstance(v, (int, float)) for v in hist):
                features = hist
            if features is None:
                features = features_from_history(hist or [], skills, timestamp, self.item_skills, next_dt)
        if isinstance(features, dict):
            features = [features[name] for name in FEATURE_NAMES]
        features = [float(v) for v in features]
        if len(features) != len(FEATURE_NAMES) or not all(math.isfinite(v) for v in features):
            raise ValueError("Invalid causal features")
        theta = self.intercept + sum(w * x for w, x in zip(self.coefficients, features))
        kc_bias = sum(self.kc_biases.get(s, 0.0) for s in skills) / (len(skills) or 1)
        item_bias = self.item_biases.get(item_id, 0.0)
        return sigmoid(theta, kc_bias + item_bias)

    def predict(self, state, item):
        requested_domain = item.get("domain", state.get("domain"))
        if requested_domain != self.domain:
            raise ValueError("This trained artifact must not be applied outside its trained domain")
        item_id = str(item.get("question_id", item.get("id", item.get("item_id", ""))))
        skills = parse_skills(item.get("tags", item.get("concept_id", item.get("skill_id"))))
        if not skills:
            skills = parse_skills(self.item_skills.get(item_id))
        probability = self.p_correct(state, skills, item_id, timestamp=item.get("timestamp"))
        known_skills = [s for s in skills if s in self.kc_biases]
        cold_start = item_id not in self.item_biases or len(known_skills) != len(skills) or not skills
        return {
            "p_correct": probability, "model": "trained_kc_pfa",
            "validated_domain": self.domain, "validation_scope": "held_out_students_same_source",
            "research_only": self.research_only, "license": self.license,
            "cold_start": cold_start, "known_kc_count": len(known_skills),
            "item_bias_known": item_id in self.item_biases,
            "cold_start_policy": "shared_learned_coefficients_zero_unknown_bias",
            "limitations": ["Not mathematics-validated" if self.domain == "ednet_english_toeic" else "No external-domain validation",
                            "Cold-start probabilities have no separate validation guarantee"],
        }
