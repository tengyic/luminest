"""Item Response Theory and computerised adaptive testing, kept deliberately small.

Why this exists
---------------
``app.learning`` already predicts a per-concept success probability from a BKT-style
mastery belief plus an empirical-Bayes item offset, and ``app.memory`` schedules reviews
with FSRS-6. Neither answers the question an adaptive *test* asks: **where is this learner
on one continuous scale, and which item would tell us the most right now?**

That is what a 2PL IRT model gives, and it gives it in a way that is comparable across
concepts - an ability estimate in logits is the same unit whether the item came from
linear equations or from supply and demand. The mastery belief cannot do that, because it
is defined per concept and never leaves it.

What is implemented, and what is not
------------------------------------
* **2PL response function** with an optional guessing floor. Exact, textbook.
* **EAP ability estimation** over a fixed grid with a normal prior. This is a real
  posterior mean and standard deviation, not a gradient step dressed up as one, and it is
  deterministic - which matters more here than speed, because a test asserts on it.
* **Maximum-information item selection** with exposure control, plus a *practice* mode
  that targets a success probability instead of maximum information. The distinction is
  the one the research draws: measurement wants items near 50% (maximum Fisher
  information); practice wants items near 85% (the "desirable difficulty" band where
  retrieval succeeds often enough to be productive and fails often enough to teach).
* **Rasch-style item calibration** from pooled counts: difficulty is the negated logit of
  the pooled success rate, discrimination is fixed at 1.0.

What is *not* implemented, and is not pretended otherwise:

* **Discrimination is not estimated.** Estimating ``a`` needs per-learner response
  vectors and a joint (marginal maximum-likelihood) fit; the calibration surface here
  only has pooled counts per item, so ``a`` is a stated assumption, not a measurement.
  Every payload carries ``discrimination_estimated: false`` so a reader cannot mistake it.
* **No equating, no DIF analysis, no item-fit statistics.** A bank calibrated this way is
  usable for ordering items; it is not a psychometrically certified instrument, and the
  payloads say so.

The cold-start rule is the practical consequence: an item with fewer than
:data:`MIN_RESPONSES_PER_ITEM` responses is returned with ``calibrated: false`` and a
difficulty taken from the prior, not from noise. LLM-generated items start there.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping, Sequence

#: Ability grid. +/-4 logits covers roughly the 0.02-0.98 success band on an average item,
#: which is wider than any course this harness serves.
THETA_MIN = -4.0
THETA_MAX = 4.0
THETA_STEP = 0.1

#: Prior on ability for a learner with no evidence: standard normal, the conventional
#: identification constraint for a 2PL model.
PRIOR_MEAN = 0.0
PRIOR_SD = 1.0

#: Below this many responses an item's difficulty is the prior, not an estimate. Twenty is
#: not a magic number; it is the point below which the standard error of a logit exceeds
#: about 0.5 logits, which is half the spread of a typical course.
MIN_RESPONSES_PER_ITEM = 20

#: Rasch assumption: every item discriminates equally. Stated, not estimated - see the
#: module docstring.
RASCH_DISCRIMINATION = 1.0

#: Maximum share of administrations any one item may take before it is skipped in favour of
#: a less-exposed item. Sympson-Hetter-style exposure control, simplified to a hard cap:
#: without it, maximum-information selection converges on the same handful of items and
#: both the bank's coverage and the test's security degrade.
EXPOSURE_CAP = 0.25

#: The success probability practice aims for. The "85% rule" (Wilson, Shenhav, Straccia &
#: Cohen 2019) is the training regime that maximised learning rate in their experiments; it
#: is a target, not a law, and it is exposed as a parameter for that reason.
PRACTICE_TARGET = 0.85

#: Measurement aims here instead: maximum Fisher information for a 2PL item sits at the
#: point where P(correct) is around 0.5, which is *not* where practice wants to be.
MEASUREMENT_TARGET = 0.5

IRT_RESEARCH_NOTE = (
    'A 2PL item response model estimates one ability value per learner on a scale that is '
    'comparable across items, and picks the next item by Fisher information. Adaptive tests '
    'built this way reach a given measurement precision in fewer items than fixed tests '
    '(Weiss 1982; van der Linden & Glas 2010). Two limits matter in practice: the estimate '
    'is only as good as the item calibration behind it, and maximum-information selection '
    'without exposure control collapses onto a few items.'
)

CAT_RESEARCH_NOTE = (
    'Item selection differs by purpose. Measurement maximises information, which for a 2PL '
    'item sits near a 50% success probability; practice targets a higher success rate, '
    'following the ~85% rule reported by Wilson et al. (2019, Nature Communications). '
    'Using one target for both is a common and quiet error: a test tuned to 85% is a weak '
    'test, and practice tuned to 50% is demoralising.'
)


# ------------------------------------------------------------------ response function

def probability(theta: float, a: float = RASCH_DISCRIMINATION, b: float = 0.0,
                c: float = 0.0) -> float:
    """P(correct) under a 2PL model with an optional guessing floor ``c``.

    ``c`` defaults to 0, which is the 2PL case. A multiple-choice item with four options
    has a guessing floor near 0.25 and passing it makes the model 3PL; the parameter is
    accepted rather than assumed so a caller who knows the floor can use it.
    """
    z = float(a) * (float(theta) - float(b))
    # Clamp the exponent before exponentiating: exp(800) is inf and inf/inf is nan, which
    # would silently poison an ability estimate rather than raise.
    z = max(-60.0, min(60.0, z))
    return float(c) + (1.0 - float(c)) / (1.0 + math.exp(-z))


def information(theta: float, a: float = RASCH_DISCRIMINATION, b: float = 0.0,
                c: float = 0.0) -> float:
    """Fisher information an item carries about ability at ``theta``.

    For the 2PL this is ``a^2 * P * (1 - P)``; with a guessing floor the numerator gains
    a ``(1 - c)^2`` factor and the denominator a ``P`` term, which is the standard 3PL
    form. Information is what "the item tells us the most" actually means, and it is
    maximised where the item is neither certainly right nor certainly wrong.
    """
    p = probability(theta, a, b, c)
    if c:
        q = 1.0 - p
        if p <= 0 or q <= 0:
            return 0.0
        return float(a) ** 2 * ((1.0 - float(c)) ** 2) * q / p
    return float(a) ** 2 * p * (1.0 - p)


def standard_error(theta: float, a: float = RASCH_DISCRIMINATION, b: float = 0.0,
                   c: float = 0.0) -> float:
    """Standard error of an ability estimate from a *single* item, from its information."""
    info = information(theta, a, b, c)
    return float('inf') if info <= 0 else 1.0 / math.sqrt(info)


# ------------------------------------------------------------------ ability estimation

def _grid() -> list[float]:
    steps = int(round((THETA_MAX - THETA_MIN) / THETA_STEP))
    return [round(THETA_MIN + index * THETA_STEP, 6) for index in range(steps + 1)]


def ability_posterior(responses: Sequence[tuple[float, float, bool]],
                      prior_mean: float = PRIOR_MEAN,
                      prior_sd: float = PRIOR_SD) -> dict[str, Any]:
    """Expected a posteriori ability given ``(a, b, correct)`` responses.

    The posterior is evaluated on a fixed grid and summarised by its mean and standard
    deviation. Grid EAP rather than Newton-Raphson because it cannot diverge, needs no
    starting value, and returns a *distribution* - so the standard error is a real
    posterior SD rather than the curvature of a likelihood at one point.

    With no responses the result is the prior, and the payload says ``n: 0`` so a caller
    cannot mistake a prior for a measurement.
    """
    grid = _grid()
    sd = max(1e-6, float(prior_sd))
    log_prior = [-0.5 * ((theta - float(prior_mean)) / sd) ** 2 for theta in grid]
    log_like = [0.0] * len(grid)
    for a, b, correct in responses:
        for index, theta in enumerate(grid):
            p = probability(theta, a, b)
            # Clamp before the log: a probability of exactly 0 or 1 from a saturated item
            # would otherwise make the whole posterior -inf.
            p = min(1.0 - 1e-9, max(1e-9, p))
            log_like[index] += math.log(p) if correct else math.log(1.0 - p)
    log_post = [lp + ll for lp, ll in zip(log_prior, log_like)]
    peak = max(log_post)
    weights = [math.exp(value - peak) for value in log_post]
    total = sum(weights)
    weights = [value / total for value in weights]
    mean = sum(weight * theta for weight, theta in zip(weights, grid))
    variance = sum(weight * (theta - mean) ** 2 for weight, theta in zip(weights, grid))
    return {
        'theta': round(mean, 4),
        'se': round(math.sqrt(max(0.0, variance)), 4),
        'n': len(responses),
        'prior_mean': float(prior_mean),
        'prior_sd': float(prior_sd),
        'at_boundary': bool(mean <= THETA_MIN + 0.2 or mean >= THETA_MAX - 0.2),
        'note': ('A posterior mean on a fixed grid with a normal prior; with n=0 this is '
                 'the prior and measures nothing.'),
    }


def estimate_ability(rows: Iterable[Mapping[str, Any]],
                     prior_mean: float = PRIOR_MEAN,
                     prior_sd: float = PRIOR_SD) -> dict[str, Any]:
    """Convenience wrapper: estimate ability from ``{a, b, correct}`` mappings.

    Rows without a usable ``b`` are skipped rather than defaulted to zero, because an
    uncalibrated item silently entered as "average difficulty" biases every estimate
    toward the middle and is impossible to see in the output.
    """
    responses: list[tuple[float, float, bool]] = []
    skipped = 0
    for row in rows:
        try:
            b = float(row.get('b'))
        except (TypeError, ValueError):
            skipped += 1
            continue
        try:
            a = float(row.get('a', RASCH_DISCRIMINATION))
        except (TypeError, ValueError):
            a = RASCH_DISCRIMINATION
        responses.append((max(0.1, a), b, bool(row.get('correct'))))
    payload = ability_posterior(responses, prior_mean, prior_sd)
    payload['skipped_uncalibrated'] = skipped
    return payload


def theta_to_success(theta: float, a: float = RASCH_DISCRIMINATION,
                     b: float = 0.0) -> float:
    """P(correct) on a reference item (``a=1, b=0``) - a readable 0-1 rendering of theta.

    This is *not* mastery: it is the probability of getting an average item right. It is
    offered because "ability 0.7 logits" means nothing to a learner and "about 67% on an
    average question" does.
    """
    return round(probability(theta, a, b), 4)


# ------------------------------------------------------------------- item selection

def select_item(candidates: Sequence[Mapping[str, Any]], theta: float, *,
                purpose: str = 'practice', target: float | None = None,
                exposure: Mapping[str, Mapping[str, Any]] | None = None,
                cap: float = EXPOSURE_CAP,
                exclude: Iterable[str] = ()) -> dict[str, Any]:
    """Pick the next item for an ability estimate, and say why.

    Two purposes, and they are not interchangeable:

    * ``measure`` - maximise Fisher information. This is what a test wants: the item that
      most reduces the standard error of ``theta``.
    * ``practice`` - minimise the distance to ``target`` success probability (default
      :data:`PRACTICE_TARGET`). This is what practice wants: an item the learner will
      probably get right, but not certainly, so retrieval is effortful and productive.

    Exposure control is applied *before* scoring: an item whose administration rate exceeds
    ``cap`` is skipped unless every candidate is over the cap, in which case the least
    exposed one is returned and the payload says the cap could not be honoured. Silently
    ignoring the cap would be worse than breaking it loudly.

    ``candidates`` are mappings carrying ``id``, ``a`` and ``b``. Items missing a usable
    ``b`` are reported in ``skipped_uncalibrated`` rather than being assigned difficulty 0.
    """
    if purpose not in ('measure', 'practice'):
        raise ValueError("purpose must be 'measure' or 'practice'")
    if target is None:
        target = MEASUREMENT_TARGET if purpose == 'measure' else PRACTICE_TARGET
    target = min(0.99, max(0.01, float(target)))

    excluded = {str(item) for item in exclude}
    exposure = exposure or {}
    usable: list[dict[str, Any]] = []
    skipped_uncalibrated: list[str] = []
    for candidate in candidates:
        item_id = str(candidate.get('id') or '')
        if not item_id or item_id in excluded:
            continue
        try:
            b = float(candidate.get('b'))
        except (TypeError, ValueError):
            skipped_uncalibrated.append(item_id or '<unnamed>')
            continue
        try:
            a = float(candidate.get('a', RASCH_DISCRIMINATION))
        except (TypeError, ValueError):
            a = RASCH_DISCRIMINATION
        a = max(0.1, a)
        p = probability(theta, a, b)
        info = information(theta, a, b)
        row = exposure.get(item_id) or {}
        opportunities = max(0, int(row.get('opportunities', 0) or 0))
        administered = max(0, int(row.get('administered', 0) or 0))
        rate = (administered / opportunities) if opportunities else 0.0
        usable.append({'id': item_id, 'a': a, 'b': b, 'p': p, 'info': info,
                       'exposure_rate': round(rate, 4), 'over_cap': rate > cap})

    if not usable:
        return {
            'item': None, 'theta': round(float(theta), 4), 'purpose': purpose,
            'target': target, 'skipped_uncalibrated': skipped_uncalibrated,
            'reason': 'No calibrated, non-excluded candidate was available, so no item was '
                      'selected. Returning a default item would hide a cold-start bank '
                      'behind a confident-looking choice.',
            'alternatives': [], 'notes': [],
        }

    in_cap = [row for row in usable if not row['over_cap']]
    pool = in_cap or usable
    notes: list[str] = []
    if not in_cap:
        notes.append('Every candidate was over the exposure cap, so the least-exposed item '
                     'was returned rather than a repeated one. The cap is reported as '
                     'breached, not silently dropped.')

    if purpose == 'measure':
        pool.sort(key=lambda row: (-row['info'], abs(row['p'] - target), row['id']))
    else:
        pool.sort(key=lambda row: (abs(row['p'] - target), -row['info'], row['id']))
    chosen = pool[0]

    # Expected information after one more response, treating Fisher information as
    # additive with the prior's. An approximation, and labelled as one: the true posterior
    # SD after an item depends on which response is observed.
    prior_info = 1.0 / (PRIOR_SD ** 2)
    expected_se = 1.0 / math.sqrt(prior_info + chosen['info'])
    if purpose == 'measure':
        why = (f"Maximum information ({chosen['info']:.3f}) at ability "
               f"{theta:.2f}; predicted P(correct)={chosen['p']:.2f}. Measurement targets "
               f"the item that most narrows the estimate, which is why it does not aim for "
               f"a high success rate.")
    else:
        why = (f"Predicted P(correct)={chosen['p']:.2f} against a practice target of "
               f"{target:.2f} (the ~85% band), information {chosen['info']:.3f}. Practice "
               f"aims for effortful success, not for a precise estimate.")
    return {
        'item': {key: chosen[key] for key in ('id', 'a', 'b', 'p', 'info', 'exposure_rate')},
        'theta': round(float(theta), 4),
        'purpose': purpose,
        'target': target,
        'expected_se_after': round(expected_se, 4),
        'skipped_uncalibrated': skipped_uncalibrated,
        'reason': why,
        'alternatives': [{key: row[key] for key in ('id', 'p', 'info')}
                         for row in pool[1:4]],
        'notes': notes,
        'research_note': CAT_RESEARCH_NOTE,
    }


# --------------------------------------------------------------------- calibration

def rasch_item(count: Any, successes: Any, *, pooled_rate: float | None = None) -> dict[str, Any]:
    """Difficulty for one item from pooled counts, with an honest cold-start state.

    ``b = -logit(p)`` with a small prior correction that pulls thin items toward the
    pooled rate, so a single lucky response does not mint an extreme difficulty. The
    correction is the same empirical-Bayes idea ``app.main.calibration_for`` already uses
    (add 4 successes and 4 failures), applied here at the item level.

    Below :data:`MIN_RESPONSES_PER_ITEM` the item is marked ``calibrated: false`` and its
    difficulty is the pooled prior: usable for ordering, not for measurement.
    """
    try:
        n = max(0, int(count))
        s = max(0, min(n, int(successes)))
    except (TypeError, ValueError):
        n, s = 0, 0
    prior = 0.5 if pooled_rate is None else min(0.99, max(0.01, float(pooled_rate)))
    smoothed = (s + 4.0 * prior) / (n + 4.0)
    smoothed = min(0.99, max(0.01, smoothed))
    b = -math.log(smoothed / (1.0 - smoothed))
    calibrated = n >= MIN_RESPONSES_PER_ITEM
    return {
        'a': RASCH_DISCRIMINATION,
        'b': round(b, 4),
        'count': n,
        'successes': s,
        'observed_rate': round(s / n, 4) if n else None,
        'smoothed_rate': round(smoothed, 4),
        'calibrated': calibrated,
        'discrimination_estimated': False,
        'reason': ('Enough responses to place this item on the scale.' if calibrated else
                   f'Only {n} responses; below the {MIN_RESPONSES_PER_ITEM}-response floor, '
                   f'so the difficulty is the pooled prior, not an estimate of this item.'),
    }


def calibrate_bank(rows: Iterable[Mapping[str, Any]], *,
                   pooled_rate: float | None = None) -> dict[str, Any]:
    """Calibrate a whole bank from ``{id, count, successes}`` rows.

    Returns the per-item table plus a summary that counts calibrated and cold-start items,
    because "the bank is calibrated" is a claim that should come with its denominator.
    """
    table: dict[str, Any] = {}
    for row in rows:
        item_id = str(row.get('id') or '')
        if not item_id:
            continue
        table[item_id] = rasch_item(row.get('count', 0), row.get('successes', 0),
                                    pooled_rate=pooled_rate)
    calibrated = sum(1 for entry in table.values() if entry['calibrated'])
    return {
        'items': table,
        'total': len(table),
        'calibrated': calibrated,
        'cold_start': len(table) - calibrated,
        'min_responses': MIN_RESPONSES_PER_ITEM,
        'note': ('Difficulty is a Rasch estimate from pooled counts; discrimination is '
                 'fixed at 1.0 rather than estimated, and no item-fit or DIF statistics '
                 'are computed. This is enough to order items, not a certified instrument.'),
    }


def describe() -> dict[str, Any]:
    """The model's posture, for the status endpoint and the transparency panel."""
    return {
        'model': '2PL item response theory',
        'ability_scale': f'logits, grid {THETA_MIN}..{THETA_MAX} step {THETA_STEP}',
        'estimation': 'grid EAP with a normal prior; theta and posterior SD are returned',
        'purposes': {'measure': 'maximum Fisher information',
                     'practice': f'target success probability {PRACTICE_TARGET}'},
        'exposure_cap': EXPOSURE_CAP,
        'min_responses_per_item': MIN_RESPONSES_PER_ITEM,
        'not_implemented': ['discrimination estimation (a is fixed at 1.0)',
                            'item-fit statistics', 'DIF analysis', 'test equating'],
        'research_note': IRT_RESEARCH_NOTE,
    }
