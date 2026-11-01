import importlib
import math
import os

from . import memory

PRIOR = 0.15
GUESS = 0.25
SLIP = 0.10
LEARN = 0.12
#: Mastery at or above which a concept counts as known. Shared by prerequisite gating
#: and by the "skip what is already known" rule below, so the two cannot drift apart.
MASTERY_THRESHOLD = 0.6
_adapter = None
_adapter_error = None


def adapter():
    global _adapter, _adapter_error
    if os.getenv('HARNESS_ADAPTATION', '0') != '1':
        return None
    if _adapter is None and _adapter_error is None:
        try:
            candidate = importlib.import_module('app.adaptation')
            if not all(callable(getattr(candidate, x, None)) for x in ('predict', 'update', 'recommend')):
                raise ValueError('Missing adaptation interface')
            metadata = getattr(candidate, 'MODEL_METADATA', {})
            if metadata.get('domain') not in {'math', 'domain_generic'} or not metadata.get('validated_for_math', False):
                raise ValueError('Adaptation disabled: model has not passed the mathematics domain gate')
            _adapter = candidate
        except Exception as exc:
            _adapter_error = str(exc)
    return _adapter


def predict(state: dict, item: dict) -> dict:
    module = adapter()
    if module:
        return module.predict(state, item)
    now = item.get('now', state.get('last_at', 0))
    recall = memory.recall_probability(state, now) if memory.enabled() else _legacy_recall(state, now)
    if memory.enabled() and recall is None:
        # Legacy states without a review timestamp keep the old shape.
        recall = None if state.get('last_at') is None and state.get('last_review') is None else recall
    return {'mastery': state.get('mastery', PRIOR), 'recall': recall,
            'evidence': _memory_evidence()}


def _legacy_recall(state: dict, now: float):
    last = state.get('last_at')
    half_life = state.get('half_life_days', 1.0)
    return None if last is None else 2 ** (-max(0, now-last) / (86400*half_life))


def _memory_evidence() -> str:
    if memory.enabled():
        w = memory.WEIGHTS_PROVENANCE
        return (f'FSRS-6 DSR memory model (published default weights {w["tag"]}, '
                f'commit {w["commit"][:12]}); mastery is a heuristic BKT prior, not a trained math model')
    return 'Heuristic BKT priors; Leitner-style two-constant recall fallback, not a trained math model'


def _mastery_update(state: dict, correct: bool) -> dict:
    """Mastery is a Bayesian belief about current skill, separate from memory
    strength (the DSR stability). Kept identical across both memory paths so the
    mastery-driven recommenders do not change behaviour when the model switches."""
    prior = state.get('mastery', PRIOR)
    numerator = prior * ((1-SLIP) if correct else SLIP)
    denominator = numerator + (1-prior) * (GUESS if correct else 1-GUESS)
    posterior = numerator / denominator
    return min(0.995, posterior + (1-posterior)*LEARN)


def update(state: dict, correct: bool, elapsed: float, now: float) -> dict:
    module = adapter()
    if module:
        return module.update(state, correct, elapsed, now)
    mastery = _mastery_update(state, correct)
    correct_count = state.get('correct_count', 0) + int(correct)
    attempts = state.get('attempts', 0) + 1
    rating = memory.RATING_GOOD if correct else memory.RATING_AGAIN
    if memory.enabled():
        # DSR path: FSRS-6 stability/difficulty drive recall and scheduling. The
        # half_life_days field is kept (stability, in days) for legacy readers.
        memory_state = memory.review(state, rating, now)
        due_at, _interval = memory.due_time(memory_state)
        return {**state, **memory_state, 'mastery': mastery, 'attempts': attempts,
                'correct_count': correct_count, 'last_at': now,
                'half_life_days': memory_state['stability'], 'due_at': due_at,
                'last_correct': bool(correct), 'last_elapsed': elapsed,
                'prior_kind': 'FSRS-6 memory model with published default weights; heuristic BKT mastery prior'}
    # Legacy fallback: Leitner-style two-constant half-life progression. Kept
    # runnable via HARNESS_MEMORY_MODEL=leitner; it cannot express "how well it
    # was remembered", which is precisely what the DSR model adds.
    half_life = min(60.0, max(0.25, state.get('half_life_days', 1.0) * (1.6 if correct else 0.55)))
    interval = max(300, -math.log2(0.8) * half_life * 86400)
    return {**state, 'mastery': mastery, 'attempts': attempts, 'correct_count': correct_count,
            'last_at': now, 'half_life_days': half_life, 'due_at': now+interval,
            'last_correct': bool(correct), 'last_elapsed': elapsed,
            'prior_kind': 'heuristic BKT; Leitner-style uncalibrated prior'}


# --------------------------------------------------------------------------
# FIRe-style implicit repetition credit propagation (reimplementation of the
# published idea from Math Academy's public write-up of their FIRe system; no
# proprietary code is involved). A successful review of a concept awards a
# fractional, distance-decayed stability increment to its prerequisites, as a
# weak-evidence update on the SAME DSR memory state.
# --------------------------------------------------------------------------

def _prerequisites(concept_id: str) -> list[str]:
    """Direct prerequisites of a concept, from whichever registry holds them.

    The authored maths lessons carry their real prerequisite structure in
    ``curriculum.KNOWLEDGE_GRAPH`` (the 164-node DAG), keyed by graph node id;
    a lesson id maps to its graph node through ``GRAPH_TO_LESSON``. Other
    courses keep prerequisites on their concept records.
    """
    from .curriculum import CONCEPTS, GRAPH_TO_LESSON, KNOWLEDGE_GRAPH
    node = None
    if concept_id in KNOWLEDGE_GRAPH.nodes:
        node = concept_id
    else:
        candidates = [n for n, lesson in GRAPH_TO_LESSON.items() if lesson == concept_id]
        if candidates:
            node = candidates[0]
    if node is not None:
        return list(KNOWLEDGE_GRAPH.nodes[node].prerequisites)
    concept = CONCEPTS.get(concept_id) or {}
    return list(concept.get('prerequisites') or [])


def propagate_implicit_credit(db, user_id: str, concept_id: str, state: dict, now: float) -> int:
    """Credit the prerequisite chain of a successfully reviewed concept.

    Returns the number of prerequisite states touched. Credit amount decays as
    IMPLICIT_CREDIT_DECAY**(distance-1) of the reviewed item's stability gain,
    capped at IMPLICIT_CREDIT_FRACTION of the gain for direct prerequisites.
    """
    if not memory.enabled():
        return 0
    gain = state.get('last_stability_gain', 0.0)
    if not gain or gain <= 0 or state.get('last_correct') is False:
        return 0
    from sqlalchemy import select as _select
    from .db import State
    touched = 0
    frontier = [concept_id]
    seen = {concept_id}
    for distance in range(1, memory.IMPLICIT_CREDIT_MAX_DISTANCE + 1):
        nxt = sorted({p for cid in frontier for p in _prerequisites(cid) if p not in seen})
        if not nxt:
            break
        seen.update(nxt)
        credit = (gain * memory.IMPLICIT_CREDIT_FRACTION
                  * memory.IMPLICIT_CREDIT_DECAY ** (distance - 1))
        for prereq_id in nxt:
            row = db.scalar(_select(State).where(State.user_id == user_id,
                                                 State.concept_id == prereq_id).with_for_update())
            if not row:
                row = State(user_id=user_id, concept_id=prereq_id, data={})
                db.add(row)
            row.data = memory.apply_implicit_credit(row.data or {}, credit, now)
            touched += 1
        frontier = nxt
    return touched


def logit(p):
    p = min(1 - 1e-6, max(1e-6, p))
    return math.log(p / (1 - p))


def item_probability(state, question, calibration=None):
    baseline = GUESS + (1 - SLIP - GUESS) * state.get('mastery', PRIOR)
    row = (calibration or {}).get(question['id'], {})
    count = row.get('count', 0)
    pooled = row.get('pooled_rate', 0.5)
    # Beta prior centered on pooled actual-response prevalence; no prescribed item difficulty.
    smoothed = (row.get('successes', 0) + 8 * pooled) / (count + 8)
    offset = logit(smoothed) - logit(pooled)
    probability = 1 / (1 + math.exp(-(logit(baseline) + offset)))
    return {'p_correct': probability, 'item_logit_offset': offset, 'sample_count': count,
            'calibration_status': 'low_data' if count < 20 else 'observational_not_validated'}


def _next_action(concept: dict, index: int = 5) -> str:
    """The next-action text from a concept's blocks, without assuming the block exists.

    An authored lesson has eight blocks and a generated lesson has four, so indexing a
    fixed position would raise on every generated concept. The fallback is the concept's
    hint, which every concept has.
    """
    blocks = concept.get('blocks') or []
    if 0 <= index < len(blocks) and blocks[index].get('body'):
        return blocks[index]['body']
    for block in blocks:
        if block.get('kind') in {'retrieval', 'reflection'} and block.get('body'):
            return block['body']
    return concept.get('hint') or 'Explain the method on a fresh variant.'


def diagnose(question, correct, option_id, response_confidence=None):
    from .curriculum import CONCEPTS
    evidence = question.get('distractor_diagnoses', {}).get(option_id)
    if correct:
        result = {'category': 'supported_correct', 'confidence': 0.6,
                  'reason': 'Tentative support from this response only; guessing remains possible.',
                  'next_action': _next_action(CONCEPTS.get(question['concept_id']) or {}),
                  'alternatives': ['A correct method', 'A lucky guess or remembered answer']}
    elif evidence:
        result = {**evidence, 'confidence': 0.35,
                  'reason': 'Tentative: ' + evidence['reason'] + ' This option is compatible with, but does not prove, that error process.',
                  'alternatives': ['An arithmetic slip', 'Misreading or accidental selection', 'A conceptual or procedural gap']}
    else:
        result = {'category': 'unanswered' if option_id is None else 'uncertain', 'confidence': 0.2,
                  'reason': 'Tentative: no option-specific process evidence; a blank or free-text mismatch cannot establish an error type.',
                  'next_action': (CONCEPTS.get(question['concept_id']) or {}).get('hint', 'Re-read the core idea.')
                                 + ' Explain the method on a fresh variant.',
                  'alternatives': ['A skipped response', 'Formatting mismatch', 'Uncertain knowledge']}
    return {**result, 'response_confidence': response_confidence,
            'scope': 'Task-level hypothesis; confidence is a heuristic, not calibrated diagnostic probability.'}


def recommend(states: dict, questions: list, mode: str, calibration=None, target=0.7):
    """Pick the next item, and say why.

    The ordering below is the whole adaptive policy for practice and review. Its first
    job is to *stop* teaching what the learner already knows: the point of a knowledge
    map is that it saves time by skipping known content, not that it re-drills it. An
    earlier version ranked candidates by ``missing`` prerequisites and then by how close
    the predicted success probability sat to the target, which had no term for "already
    mastered". A learner at mastery 0.995 kept out-ranking every unseen concept on both
    counts and was served the same concept indefinitely, so the graph was measured and
    then ignored.

    Mastered concepts are demoted rather than dropped. They stay in the candidate pool
    because ``min`` must still return something once everything is known, and because a
    mastered concept whose recall has decayed is exactly what should come back - that is
    the memory curve's job, and ``/reviews`` already restricts to concepts whose
    ``due_at`` has passed.
    """
    from .curriculum import CONCEPTS

    def priority(q):
        state = states.get(q['concept_id'], {})
        mastery = state.get('mastery', PRIOR)
        mastered = mastery >= MASTERY_THRESHOLD
        prerequisites = CONCEPTS[q['concept_id']]['prerequisites']
        missing = sum(states.get(p, {}).get('mastery', PRIOR) < MASTERY_THRESHOLD
                      for p in prerequisites)
        evidence_count = state.get('attempts', 0)
        uncertainty = 4 * mastery * (1 - mastery) / math.sqrt(1 + evidence_count)
        downstream = sum(q['concept_id'] in c['prerequisites'] for c in CONCEPTS.values())
        if mode == 'diagnostic':
            # Coverage is constrained by the caller; this heuristic prioritizes uncertain prerequisite evidence.
            gain = uncertainty * (1 + 0.25 * downstream) / (1 + missing)
            return (-gain, evidence_count, q['id'])
        pending = state.get('next_check')
        targeted = bool(pending and pending.get('question_id') != q['id'])
        p = item_probability(state, q, calibration)['p_correct']
        return (not targeted, mastered, missing, abs(p - target), evidence_count, q['id'])
    selected = min(questions, key=priority)
    state = states.get(selected['concept_id'], {})
    if mode == 'diagnostic':
        return selected, 'Coverage-constrained diagnostic: one check per concept, ordered by heuristic uncertainty, prerequisite dependencies and downstream information value; not a certainty or a validated information-gain estimate. Report response confidence.'
    prediction = item_probability(state, selected, calibration)
    reason = (f"Predicted P(correct)={prediction['p_correct']:.2f}; target={target:.2f} is a configurable practice hypothesis, not a scientific optimum. "
              f"BKT response prior plus monotonic empirical-Bayes item logit offset from {prediction['sample_count']} actual responses ({prediction['calibration_status']}); prerequisite evidence constrains selection.")
    # Say which rule decided, so "why this question" is answerable from the payload alone.
    selected_mastery = state.get('mastery', PRIOR)
    if selected_mastery >= MASTERY_THRESHOLD:
        known = {q['concept_id'] for q in questions
                 if states.get(q['concept_id'], {}).get('mastery', PRIOR) >= MASTERY_THRESHOLD}
        if len(known) >= len({q['concept_id'] for q in questions}):
            reason += (f' Every available concept is at or above mastery {MASTERY_THRESHOLD:.2f}, '
                       'so this is the one whose recall is weakest rather than new material.')
        else:
            reason += (' Revisited despite mastery ' f'{selected_mastery:.2f} because its recall '
                       'has decayed furthest; new concepts are preferred while any remain.')
    else:
        skipped = sum(1 for q in questions
                      if states.get(q['concept_id'], {}).get('mastery', PRIOR) >= MASTERY_THRESHOLD)
        if skipped:
            reason += (f' Advanced past {skipped} candidate item(s) at or above mastery '
                       f'{MASTERY_THRESHOLD:.2f}: known content is skipped, not re-drilled.')
    if state.get('next_check'):
        reason += ' Fresh variant cross-check for tentative ' + state['next_check']['category'] + ': ' + state['next_check']['next_action']
    if mode == 'review':
        reason += ' Selected only from due concepts.'
    return selected, reason


def model_status():
    module = adapter()
    if module:
        meta = module.MODEL_METADATA
        return {'name': meta.get('name', 'Domain-gated adaptation'), 'trained': bool(meta.get('trained', False)),
                'domain': meta['domain'], 'commercial_ready': False}
    if memory.enabled():
        w = memory.WEIGHTS_PROVENANCE
        return {'name': f'FSRS-6 DSR memory model (upstream defaults {w["tag"]}) + heuristic BKT mastery',
                'trained': False, 'domain': 'mathematics; memory model is principled, mastery prior is not calibrated',
                'commercial_ready': False}
    return {'name': 'Heuristic BKT + Leitner-style recall fallback' + (' (optional model rejected)' if _adapter_error else ''),
            'trained': False, 'domain': 'mathematics; heuristic, not calibrated', 'commercial_ready': False}
