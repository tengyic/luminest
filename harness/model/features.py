"""Causal, timestamp-tie-safe PFA features shared by training and inference."""
import math
from collections import defaultdict

FEATURE_NAMES = (
    "log1p_skill_prior_success", "log1p_skill_prior_failure",
    "global_prior_accuracy", "log1p_gap_days", "log1p_skill_recency_days",
)
SECONDS_PER_DAY = 86400.0


def parse_skills(value):
    if value is None:
        return ()
    if isinstance(value, (list, tuple, set)):
        values = value
    else:
        values = str(value).split(";")
    return tuple(sorted({str(v).strip() for v in values
                         if str(v).strip() not in {"", "nan", "None"}}))


def skills_for(row, item_skills=None):
    for key in ("skill_ids", "tags", "concept_id", "skill_id"):
        if row.get(key) is not None:
            return parse_skills(row[key])
    item = str(row.get("question_id", row.get("item_id", "")))
    return parse_skills((item_skills or {}).get(item, ()))


class CausalState:
    def __init__(self):
        self.success = defaultdict(float)
        self.failure = defaultdict(float)
        self.last_skill = {}
        self.correct = 0.0
        self.total = 0
        self.last_timestamp = None

    def features(self, skills, timestamp):
        skills = parse_skills(skills)
        n = len(skills) or 1
        success = sum(math.log1p(self.success[s]) for s in skills) / n
        failure = sum(math.log1p(self.failure[s]) for s in skills) / n
        accuracy = (self.correct + 1.0) / (self.total + 2.0)
        gap = 0.0 if self.last_timestamp is None else max(0.0, timestamp - self.last_timestamp)
        recency = sum(math.log1p(max(0.0, timestamp - self.last_skill[s]) / SECONDS_PER_DAY)
                      for s in skills if s in self.last_skill) / n
        return [success, failure, accuracy, math.log1p(gap / SECONDS_PER_DAY), recency]

    def observe(self, skills, is_correct, timestamp):
        if is_correct not in (0, 1, False, True):
            raise ValueError("is_correct must be binary")
        for skill in parse_skills(skills):
            self.success[skill] += int(is_correct)
            self.failure[skill] += 1 - int(is_correct)
            self.last_skill[skill] = timestamp
        self.correct += int(is_correct)
        self.total += 1
        self.last_timestamp = timestamp


def causal_features(rows):
    """Rows must be chronological, from one student, with timestamps in seconds.

    No response at the target timestamp (including tied peers) is used to predict it.
    Every timestamp group is featurized before any of its outcomes are observed.
    """
    state = CausalState()
    result = []
    start = 0
    while start < len(rows):
        timestamp = float(rows[start]["timestamp"])
        if state.last_timestamp is not None and timestamp < state.last_timestamp:
            raise ValueError("History must be chronological")
        end = start + 1
        while end < len(rows) and float(rows[end]["timestamp"]) == timestamp:
            end += 1
        for row in rows[start:end]:
            result.append(state.features(skills_for(row), timestamp))
        for row in rows[start:end]:
            state.observe(skills_for(row), row["is_correct"], timestamp)
        start = end
    return result


def features_from_history(history, skills, timestamp=None, item_skills=None, next_dt=0.0):
    """History uses absolute seconds; next_dt is in days for legacy engine calls."""
    history = sorted(history, key=lambda row: float(row["timestamp"]))
    if timestamp is None:
        timestamp = (float(history[-1]["timestamp"]) if history else 0.0) + float(next_dt) * SECONDS_PER_DAY
    timestamp = float(timestamp)
    if not math.isfinite(timestamp):
        raise ValueError("Prediction timestamp must be finite")
    state = CausalState()
    for row in history:
        when = float(row["timestamp"])
        if not math.isfinite(when):
            raise ValueError("History timestamps must be finite")
        if when >= timestamp:
            continue
        state.observe(skills_for(row, item_skills), row["is_correct"], when)
    return state.features(skills, timestamp)
