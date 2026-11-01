"""Honest evaluation protocol: student-level splits and AUC.

The one rule that matters: SPLIT BY STUDENT, NEVER BY ROW. Splitting
interactions by row puts the same student's history in both train and test;
the model then memorizes the student instead of learning learning, and the
AUC is inflated garbage. This is the same disjoint-student protocol the
existing EdNet research artifact was evaluated under
(``model/test_results.json`` / the adaptation gate).
"""

from __future__ import annotations

import random
from collections import defaultdict

from .datasets import Record


def split_by_students(records, test_fraction=0.2, seed=42):
    """Partition records by disjoint student sets. Returns (train, test).

    Properties (tested): train and test share NO student id, and every record
    lands in exactly one side.
    """
    students = sorted({r.student_id for r in records})
    shuffled = list(students)
    random.Random(seed).shuffle(shuffled)
    n_test = int(round(len(shuffled) * test_fraction))
    test_ids = set(shuffled[:n_test])
    return ([r for r in records if r.student_id not in test_ids],
            [r for r in records if r.student_id in test_ids])


def group_by_student_skill(records):
    """{student_id: {skill: [Record]}} with records in sequence order."""
    grouped = defaultdict(lambda: defaultdict(list))
    for r in records:
        grouped[r.student_id][r.skill].append(r)
    for student in grouped:
        for skill in grouped[student]:
            grouped[student][skill].sort(key=lambda r: r.order)
    return grouped


def auc(labels, scores):
    """Rank-based AUC (Mann-Whitney U / (pos*neg)). No sklearn dependency.
    Ties count half. Returns None when only one class is present."""
    pairs = sorted(zip(scores, labels))
    n_pos = sum(1 for _, y in pairs if y)
    n_neg = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0:
        return None
    ranks = [0.0] * len(pairs)
    i = 0
    while i < len(pairs):
        j = i
        while j + 1 < len(pairs) and pairs[j + 1][0] == pairs[i][0]:
            j += 1
        avg_rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[k] = avg_rank
        i = j + 1
    rank_sum_pos = sum(rank for rank, (_, y) in zip(ranks, pairs) if y)
    return (rank_sum_pos - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def evaluate_model(records, model_factory, test_fraction=0.2, seed=42, min_history=1):
    """The protocol, end to end:

    1. split by student (never by row);
    2. ``model = model_factory(); model.fit(train_records)``;
    3. for each held-out student, predict each response from that student's
       EARLIER responses only (their t-th response is scored from 1..t-1), so
       there is no same-row leak either;
    4. report overall and per-skill AUC.

    ``model_factory`` returns an object with ``fit(records)`` and
    ``predict(history: list[bool], skill: str) -> float``.
    """
    train, test = split_by_students(records, test_fraction, seed)
    model = model_factory()
    model.fit(train)
    test_grouped = group_by_student_skill(test)
    labels, scores = [], []
    per_skill = defaultdict(lambda: ([], []))
    for _student, by_skill in sorted(test_grouped.items()):
        for skill, seq in sorted(by_skill.items()):
            history = []
            for r in seq:
                if r.order > min_history:
                    p = model.predict(history, skill)
                    labels.append(r.correct)
                    scores.append(p)
                    per_skill[skill][0].append(r.correct)
                    per_skill[skill][1].append(p)
                history.append(r.correct)
    per_skill = {skill: {'auc': auc(ys, ss), 'n': len(ys)}
                 for skill, (ys, ss) in sorted(per_skill.items())}
    macro = [v['auc'] for v in per_skill.values() if v['auc'] is not None]
    return {'auc_overall': (sum(macro) / len(macro)) if macro else None,
            'auc_overall_note': ('macro-average of per-skill AUCs; the pooled AUC '
                                 'over all skills is reported separately because '
                                 'pooling scores across skills with different base '
                                 'rates can invert the ranking'),
            'auc_pooled_all_skills': auc(labels, scores),
            'n_test_predictions': len(labels),
            'n_train_students': len({r.student_id for r in train}),
            'n_test_students': len({r.student_id for r in test}),
            'per_skill': per_skill,
            'protocol': ('disjoint-student split; model fit on training students '
                         'only; each prediction uses only that student\'s earlier '
                         'responses; AUC = Mann-Whitney U over next-step '
                         'correctness')}
