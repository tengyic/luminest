"""Learning-science scheduling and measurement.

Four independent, individually research-anchored pieces live here:

* ``build_practice_group`` - interleaved practice scheduling (P-1).
* ``brier_decomposition`` - confidence calibration measurement (P-2).
* ``next_transfer`` - delayed transfer test eligibility (P-4).
* shared KC-family resolution used by both.

Each is a legible rule, not a model, and each says in its own output what the
underlying research does and does not claim.
"""

from __future__ import annotations

#: Delayed transfer tests, in days after the learner's last practice activity.
TRANSFER_DELAYS: tuple[int, ...] = (7, 28)

#: A graded attempt needs at least this many characters of self-explanation when the
#: gate is on. Short enough to be one honest sentence; long enough that "idk" does
#: not count as explaining anything.
SELF_EXPLANATION_MIN_CHARS = 20

INTERLEAVE_RESEARCH_NOTE = (
    'Interleaved scheduling mixes related problem types in one set instead of blocking '
    'them by topic. Rohrer (2015) and Rohrer & Taylor (2007) found mixed practice of '
    'this kind produced substantially better delayed test performance than blocked '
    'practice (Rohrer 2015 reports d=0.79 on a delayed test). The benefit is measured '
    'for *discriminating between confusable problem types*; it does not claim to '
    'improve every kind of learning.'
)

TRANSFER_RESEARCH_NOTE = (
    'This item comes from a family that never appeared in your practice history, so '
    'correctness here is evidence of transfer, not of recall. Delayed testing after '
    'retrieval practice shows large retention gains (Karpicke & Roediger 2008, Science: '
    'repeated retrieval with feedback produced substantially better long-term retention '
    'than repeated study). That paper measures retention of tested material; whether a '
    'score here generalises beyond it is exactly what the 7d/28d comparison is for.'
)

CALIBRATION_RESEARCH_NOTE = (
    'Brier score decomposed per Murphy (1973): reliability (how far confidence '
    'frequency tracks actual accuracy), resolution (how well confidence levels '
    'separate correct from incorrect), and uncertainty (base-rate variance). '
    'brier = reliability - resolution + uncertainty. Lower is better; only the '
    'reliability component is directly actionable by the learner.'
)


# --------------------------------------------------------------------------- families

def concept_family(concept: dict) -> str:
    """The knowledge-component (KC) family a concept belongs to.

    A family is the finest classification the course graph carries: its *topic*,
    falling back to *unit*, then *strand*. Interleaving and transfer are both defined
    over families, and both must use the same definition or a transfer test could
    hand back a family the learner just practised.
    """
    for key in ('topic', 'unit', 'strand'):
        value = str(concept.get(key) or '').strip()
        if value:
            return value.casefold()
    return 'unclassified'


def _round_robin(pool: list[dict], keys: list[str], count: int) -> list[dict]:
    """Take ``count`` items from ``pool``, cycling across ``keys`` (family labels).

    Cycling - one item from family A, then B, then A again - is what makes the
    *presentation* interleaved rather than merely mixed, and it is also what
    guarantees family diversity whenever more than one family is available: the
    first ``len(keys)`` picks all come from different families.
    """
    by_key: dict[str, list[dict]] = {}
    for item in pool:
        by_key.setdefault(item['family'], []).append(item)
    # The incoming key order may repeat a family (it is often built per item); the
    # cycle must visit each family once per round, so dedupe while keeping order.
    ordered_keys = list(dict.fromkeys(key for key in keys if key in by_key))
    ordered_keys += sorted(set(by_key) - set(ordered_keys))
    picked: list[dict] = []
    progress = True
    while len(picked) < count and progress:
        progress = False
        for key in ordered_keys:
            if len(picked) >= count:
                break
            queue = by_key[key]
            if queue:
                picked.append(queue.pop(0))
                progress = True
    return picked


def build_practice_group(states: dict, candidates: list[dict], group_size: int,
                         now: float) -> tuple[list[dict], dict]:
    """Build one interleaved practice set.

    ``candidates`` are question dicts; each carries ``family`` (KC family label),
    ``concept_id`` and ``due_at`` (its concept's due timestamp or ``None`` when never
    attempted). ``states`` maps concept id to the learner's state dict.

    The rule, in order:

    1. Up to half the group comes from *due* concepts (``attempts > 0`` and
       ``due_at <= now``), most overdue first - retrieval of due material is the
       highest-value use of practice time.
    2. The rest comes from *new* concepts (never attempted).
    3. Both halves are filled family-round-robin, so the set spans as many KC
       families as the bank allows and consecutive items differ in type.
    4. The returned order is the interleaved order.

    Returns ``(ordered_items, mix)``. ``mix`` exposes the decision - which families,
    how many from each, how many due reviews vs new concepts - and states honestly
    when the bank could not support two families or had no due reviews.
    """
    size = max(1, int(group_size))
    def sort_key(item):
        return (item['concept_id'], item['id'])

    due_pool = sorted(
        [item for item in candidates
         if states.get(item['concept_id'], {}).get('attempts', 0) > 0
         and (states.get(item['concept_id'], {}).get('due_at') or float('inf')) <= now],
        key=lambda item: (states[item['concept_id']].get('due_at') or 0, *sort_key(item)))
    new_pool = sorted(
        [item for item in candidates
         if states.get(item['concept_id'], {}).get('attempts', 0) == 0],
        key=sort_key)
    filler_pool = sorted(
        [item for item in candidates
         if item not in due_pool and item not in new_pool],
        key=sort_key)

    due_count = min(len(due_pool), size // 2)
    remaining = size - due_count
    new_count = min(len(new_pool), remaining)
    filler_count = min(len(filler_pool), remaining - new_count)

    due_keys = [item['family'] for item in due_pool]
    new_keys = [item['family'] for item in new_pool]
    filler_keys = [item['family'] for item in filler_pool]

    selected = ([{**item, 'source': 'due_review'} for item in _round_robin(due_pool, due_keys, due_count)]
                + [{**item, 'source': 'new_concept'} for item in _round_robin(new_pool, new_keys, new_count)]
                + [{**item, 'source': 'further_practice'} for item in _round_robin(filler_pool, filler_keys, filler_count)])

    # Presentation order: cycle families again across the *final* selection, keeping
    # due reviews first in each cycle (retrieval first within each round).
    keys = []
    for item in selected:
        if item['family'] not in keys:
            keys.append(item['family'])
    ordered = _round_robin(selected, keys, len(selected))

    families: dict[str, dict] = {}
    for item in ordered:
        row = families.setdefault(item['family'], {'family': item['family'], 'count': 0,
                                                   'due_review': 0, 'new_concept': 0,
                                                   'further_practice': 0})
        row['count'] += 1
        row[item['source']] += 1

    notes = []
    if due_count == 0:
        notes.append('No reviews were due yet, so the group interleaves new concepts across families.')
    if len(keys) < 2:
        notes.append('The available bank could not supply two different KC families; the set is reported as returned rather than padded with faked variety.')

    mix = {
        'strategy': 'interleaved',
        'requested': size,
        'returned': len(ordered),
        'distinct_families': len(keys),
        'due_review_items': sum(1 for item in ordered if item['source'] == 'due_review'),
        'new_concept_items': sum(1 for item in ordered if item['source'] == 'new_concept'),
        'families': [{'family': row['family'], 'count': row['count'],
                      'due_review': row['due_review'], 'new_concept': row['new_concept'],
                      'further_practice': row['further_practice']}
                     for row in sorted(families.values(), key=lambda row: -row['count'])],
        'research_note': INTERLEAVE_RESEARCH_NOTE,
        'notes': notes,
    }
    return ordered, mix


# ------------------------------------------------------------------------ calibration

def brier_decomposition(outcomes: list[bool], confidences: list[float],
                        bins: int = 10) -> dict:
    """Murphy (1973) decomposition of the Brier score into its components.

    Uses only completed, graded attempts - the caller filters. With N attempts,
    confidences grouped into bins of width ``1/bins``:

    reliability = sum_k n_k (f_k - o_k)^2 / N
    resolution  = sum_k n_k (o_k - o)^2   / N
    uncertainty = o (1 - o)

    and Brier = reliability - resolution + uncertainty (verified as an identity in
    the tests). An *uncalibrated* but *resolving* forecaster can beat 0.25 on the
    full score, which is why the decomposition is reported rather than the scalar.
    """
    outcomes_b = [bool(outcome) for outcome in outcomes]
    confidences_f = [min(1.0, max(0.0, float(confidence))) for confidence in confidences]
    n = len(outcomes_b)
    if n == 0:
        return {'n': 0, 'status': 'insufficient_data'}
    mean_outcome = sum(outcomes_b) / n
    rows: dict[int, dict] = {}
    for outcome, confidence in zip(outcomes_b, confidences_f):
        index = min(bins - 1, int(confidence * bins))
        row = rows.setdefault(index, {'count': 0, 'confidence_sum': 0.0, 'correct': 0})
        row['count'] += 1
        row['confidence_sum'] += confidence
        row['correct'] += int(outcome)
    reliability = sum(row['count'] * (row['confidence_sum'] / row['count']
                                      - (row['correct'] / row['count'])) ** 2
                      for row in rows.values()) / n
    resolution = sum(row['count'] * (row['correct'] / row['count'] - mean_outcome) ** 2
                     for row in rows.values()) / n
    uncertainty = mean_outcome * (1 - mean_outcome)
    # The scalar is the decomposition-implied Brier score: reliability - resolution
    # + uncertainty, which is exact for binned confidences. The plain mean of
    # (confidence - outcome)^2 is smaller by the within-bin dispersion of the raw
    # confidences, so the two coincide only when every bin is internally uniform.
    brier = reliability - resolution + uncertainty
    bin_rows = []
    for index in sorted(rows):
        row = rows[index]
        bin_rows.append({
            'bin': f'{index / bins:.1f}-{(index + 1) / bins:.1f}',
            'count': row['count'],
            'mean_confidence': round(row['confidence_sum'] / row['count'], 4),
            'accuracy': round(row['correct'] / row['count'], 4),
        })
    stated = sum(confidences_f) / n
    accuracy = mean_outcome
    payload = {
        'n': n,
        'brier': round(brier, 6),
        'reliability': round(reliability, 6),
        'resolution': round(resolution, 6),
        'uncertainty': round(uncertainty, 6),
        'bins': bin_rows,
        'summary': {
            'stated_confidence': round(stated, 4),
            'actual_accuracy': round(accuracy, 4),
            'statement': f'You said {stated:.0%} confident on average; you were actually {accuracy:.0%} correct.',
            'verdict': ('well calibrated' if abs(stated - accuracy) <= 0.05
                        else 'overconfident' if stated > accuracy else 'underconfident'),
        },
        'research_note': CALIBRATION_RESEARCH_NOTE,
    }
    high = [(outcome, confidence) for outcome, confidence in zip(outcomes_b, confidences_f)
            if confidence >= 0.8]
    if high:
        stated_high = sum(confidence for _, confidence in high) / len(high)
        actual_high = sum(outcome for outcome, _ in high) / len(high)
        payload['high_confidence'] = {
            'n': len(high),
            'stated_confidence': round(stated_high, 4),
            'actual_accuracy': round(actual_high, 4),
            'statement': (f'On the answers you marked at least 80% confident, you said '
                          f'{stated_high:.0%} confident and were actually {actual_high:.0%} correct.'),
        }
    return payload


# --------------------------------------------------------------------------- transfer

def next_transfer(last_activity: float | None, now: float,
                  completed_delays: set[int]) -> tuple[int | None, float | None]:
    """Which delayed transfer test is due, and when the next one opens.

    Returns ``(delay_days | None, available_at | None)``. ``delay_days`` is the
    smallest configured delay that has elapsed and has not already been completed;
    when none is eligible, ``available_at`` is the earliest timestamp at which one
    will be. ``last_activity`` is the timestamp of the learner's last practice
    attempt; ``None`` (no history at all) means no transfer is ever due.
    """
    if last_activity is None:
        return None, None
    for delay in TRANSFER_DELAYS:
        if delay not in completed_delays:
            available_at = last_activity + delay * 86400
            if available_at <= now:
                return delay, None
            return None, available_at
    return None, None
