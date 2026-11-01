"""JSON-backed KTEngine compatibility; direct use is an explicit research API."""
from pathlib import Path

try:
    from .features import SECONDS_PER_DAY
    from .trained_pfa import TrainedPFA
except ImportError:
    from features import SECONDS_PER_DAY
    from trained_pfa import TrainedPFA

DEFAULT_ARTIFACT = Path(__file__).resolve().parent / "research" / "ednet_pfa.json"


class KTEngine:
    def __init__(self, which="research", model_dir=None, path=None):
        # Old student/teacher names select the new JSON model, never old item embeddings.
        if which not in {"research", "student", "teacher"}:
            path = path or which
        if path is None:
            path = Path(model_dir) / "research" / "ednet_pfa.json" if model_dir else DEFAULT_ARTIFACT
        self.model = TrainedPFA.load(path)
        self.which = "trained_kc_pfa_research"
        self.n_items = len(self.model.item_biases)
        self.validated_domain = self.model.domain
        self.research_only = self.model.research_only

    @classmethod
    def load(cls, path):
        return cls(path=path)

    def p_correct(self, hist_items, hist_resps=None, hist_dts=None, next_item=None,
                  next_dt=0.0, *, skill_id=None, features=None, timestamp=None):
        if hist_resps is None:
            return self.model.p_correct(hist_items, skill_id, next_item, features=features,
                                        timestamp=timestamp, next_dt=next_dt)
        if len(hist_items) != len(hist_resps) or len(hist_items) != len(hist_dts):
            raise ValueError("History arrays must have equal lengths")
        history = []
        when = 0.0
        for item, response, gap in zip(hist_items, hist_resps, hist_dts):
            if float(gap) < 0:
                raise ValueError("History gaps cannot be negative")
            when += float(gap) * SECONDS_PER_DAY
            # Preserve actual question IDs; NPZ compressed IDs must not be guessed.
            history.append({"question_id": str(item), "is_correct": response, "timestamp": when})
        return self.model.p_correct(history, skill_id, str(next_item), features=features,
                                    timestamp=timestamp, next_dt=next_dt)

    def recommend(self, hist_items, hist_resps, hist_dts, candidate_ids, next_dt=0.0,
                  target=0.70):
        if not 0 < target < 1:
            raise ValueError("target must be between zero and one")
        scored = [{"question_id": str(item),
                   "p_correct": self.p_correct(hist_items, hist_resps, hist_dts, item, next_dt),
                   "model": self.which, "validated_domain": self.validated_domain,
                   "research_only": self.research_only} for item in candidate_ids]
        return sorted(scored, key=lambda result: abs(result["p_correct"] - target))
