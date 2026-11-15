"""The estimators. Pure functions, no database, no I/O.

Each one answers a different question, and the report keeps them apart on purpose:

* **How fast is this learner improving?** - :func:`fit_learning_rate`, a slope in log-odds
  per practice opportunity. This is the headline. It is a *within-person* quantity, so it
  does not need a norm group, and it is robust to where the learner started, which is the
  property Cen, Koedinger & Junker (2006) argue for over pretest-posttest gain: two learners
  who begin at 30% and 70% can share a learning rate, and a gain score cannot express that.
* **How big was the change?** - :func:`normalized_gain` (Hake 1998), :func:`cohens_d`.
* **How much did it cost?** - :func:`time_to_criterion`, :func:`instructional_efficiency`
  (Paas & van Merriënboer 1993), and the gain-per-hour ratio.
* **Is the help doing the work?** - :func:`aided_unaided_gap`. The one measurement that a
  practice-accuracy dashboard cannot produce and the one the 2024 tutor evidence says is
  decisive.

Two implementation notes that matter for honesty
------------------------------------------------
**The slope is fit with a ridge penalty.** Unpenalised logistic regression on a short,
lopsided sequence separates: if a learner answers the first six opportunities right, the
maximum-likelihood slope diverges and the reported learning rate becomes an artefact of the
solver's iteration cap. A small ridge term on the slope keeps the estimate finite and biased
slightly toward "no learning", which is the safe direction - it understates efficiency rather
than inventing it. The penalty is documented in the payload so a caller can see it.

**Confidence intervals come from resampling opportunities within concepts, not attempts
across concepts.** Reshuffling attempts between concepts would answer a question nobody
asked ("what if this learner's fractions attempts had been their decimals attempts"), and
would produce a reassuringly narrow interval. Preserving each concept's sequence and
resampling within it measures the uncertainty in *this* learner's rate.
"""

from __future__ import annotations

import math
import random
from typing import Any, Mapping, Sequence

from . import contracts

#: Ridge penalty on the opportunity slope. Chosen so that a sequence needs to be both long
#: and consistent before the slope moves far from zero; small enough that a genuine
#: improvement is not flattened. Not tuned to the data - a constant, so it cannot be
#: quietly fitted to make a particular result look better.
RIDGE = 0.5

#: Newton iterations for the logistic fit. Convergence is quadratic near the optimum, so
#: this is far more than two-parameter problems need; it exists to bound a pathological case.
MAX_ITERATIONS = 40

#: An estimate whose half-life exceeds this many opportunities is reported as "not reached"
#: rather than as a number. Beyond this the extrapolation is doing the work, not the data.
MAX_HALF_LIFE = 50.0

#: Resamples for every bootstrap interval.
BOOTSTRAP_DRAWS = 400

RATE_NOTE = (
    'Learning rate is the change in log-odds of a correct answer per practice opportunity, '
    'fit as a logistic curve with one intercept per concept and a shared slope (the additive '
    'factors structure of Cen, Koedinger & Junker 2006). Because it is estimated from change '
    'within the learner, it does not depend on where the learner started - unlike a '
    'pretest-posttest gain, which is mechanically smaller for anyone who scores high to begin '
    'with. It describes the material and the support conditions that produced it, not an '
    'innate rate.'
)


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exponent = math.exp(value)
    return exponent / (1.0 + exponent)


def _logit(p: float) -> float:
    p = min(1.0 - 1e-9, max(1e-9, p))
    return math.log(p / (1.0 - p))


# --------------------------------------------------------------- learning rate (headline)

def fit_concept_curve(opportunities: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Fit ``logit P(correct) = a + b * opportunity`` for one concept.

    Newton-Raphson on the two-parameter logistic with a ridge penalty on ``b``. Returns the
    slope, the implied half-life in opportunities, and the raw curve so a caller can plot
    the thing that was fit instead of trusting the summary.

    ``opportunities`` is the concept's ordered attempt sequence. The predictor is each row's
    own ``opportunity`` field when present, falling back to its position in the sequence.
    That fallback is not a convenience: the bootstrap resamples rows and must keep each
    outcome attached to the opportunity number it was observed at, so position must come
    from the row rather than from the loop index.

    Only the correctness bit is used - aid has already been handled by the caller, which
    decides which observations are admissible.
    """
    pairs = _pairs(opportunities)
    n = len(pairs)
    if n < 3:
        return {**contracts.evidence_status(n, 3), 'concept_id': None}
    concept_id = opportunities[0].get('concept_id')
    outcomes = [correct for _position, correct in pairs]
    # Newton-Raphson on [1, position], penalising the slope only. The intercept is left free
    # because "where the learner started" is not the quantity under constraint; it is the
    # thing the slope is meant to be immune to.
    beta = [0.0, 0.0]
    for _ in range(MAX_ITERATIONS):
        grad = [0.0, 0.0]
        hess = [[0.0, 0.0], [0.0, 0.0]]
        for position, correct in pairs:
            p = _sigmoid(beta[0] + beta[1] * position)
            weight = max(1e-6, p * (1.0 - p))
            residual = (1.0 if correct else 0.0) - p
            grad[0] += residual
            grad[1] += residual * position
            hess[0][0] += weight
            hess[0][1] += weight * position
            hess[1][0] += weight * position
            hess[1][1] += weight * position * position
        # Penalty term (gradient and Hessian), slope only.
        grad[1] -= RIDGE * beta[1]
        hess[1][1] += RIDGE
        # 2x2 solve, with a small ridge on the diagonal against a degenerate information
        # matrix (every prediction saturated at 0 or 1).
        det = hess[0][0] * hess[1][1] - hess[0][1] * hess[1][0]
        if abs(det) < 1e-12:
            hess[0][0] += 1e-6
            hess[1][1] += 1e-6
            det = hess[0][0] * hess[1][1] - hess[0][1] * hess[1][0]
            if abs(det) < 1e-12:
                break
        step0 = (hess[1][1] * grad[0] - hess[0][1] * grad[1]) / det
        step1 = (hess[0][0] * grad[1] - hess[1][0] * grad[0]) / det
        # A damping cap: one enormous Newton step out of a separated start would otherwise
        # overshoot into a saturated region and stay there.
        scale = max(1.0, abs(step0) / 4.0, abs(step1) / 2.0)
        beta[0] += step0 / scale
        beta[1] += step1 / scale
        if abs(step0) < 1e-8 and abs(step1) < 1e-8:
            break
    slope = beta[1]
    curve = [{'opportunity': round(position, 2),
              'predicted': round(_sigmoid(beta[0] + beta[1] * position), 4),
              'observed': 1 if correct else 0}
             for position, correct in pairs]
    half_life = _half_life(beta[0], slope, n)
    return {
        'status': 'measured',
        'concept_id': concept_id,
        'opportunities': n,
        'intercept': round(beta[0], 6),
        'slope': round(slope, 6),
        'odds_ratio_per_opportunity': round(math.exp(slope), 4),
        'half_life_opportunities': half_life,
        'accuracy_first_half': _accuracy(outcomes[: max(1, n // 2)]),
        'accuracy_second_half': _accuracy(outcomes[n // 2:]),
        'curve': curve,
        'ridge': RIDGE,
    }


def _pairs(rows: Sequence[Mapping[str, Any]]) -> list[tuple[float, bool]]:
    """``(opportunity, correct)`` pairs, taking the opportunity from the row when it has one.

    Resampling a regression requires the predictor to travel with its own response. Deriving
    the predictor from loop position instead was the first implementation, and it made the
    bootstrap fit noise: every resample re-paired outcomes with arbitrary opportunity
    numbers, so the resampled curves were flat by construction and the interval collapsed
    around zero rather than around the estimate.
    """
    pairs: list[tuple[float, bool]] = []
    for index, row in enumerate(rows, start=1):
        try:
            position = float(row.get('opportunity'))
        except (TypeError, ValueError):
            position = float(index)
        pairs.append((position, bool(row.get('correct'))))
    return pairs


def _accuracy(values: Sequence[bool]) -> float | None:
    return round(sum(1 for value in values if value) / len(values), 4) if values else None


def _half_life(intercept: float, slope: float, n: int) -> float | None:
    """Opportunities until the *error rate* halves relative to opportunity 1.

    Solved in closed form from the fitted curve rather than simulated. ``slope <= 0`` means
    the curve is flat or worsening: there is no half-life, and returning a large number
    would be the flattering answer rather than the true one.

    The search is bounded at :data:`MAX_HALF_LIFE`; past that the number would be produced
    by extrapolating a two-parameter curve far outside the observed range, which is
    arithmetic rather than measurement.
    """
    if slope <= 1e-9:
        return None
    target_error = 1.0 - _sigmoid(intercept + slope * 1)
    if target_error <= 1e-9:
        # Already perfect at opportunity 1; halving zero error is undefined, not fast.
        return None
    wanted = 1.0 - target_error / 2.0
    if wanted >= 1.0 - 1e-9:
        return None
    opportunity = (_logit(wanted) - intercept) / slope
    if not math.isfinite(opportunity) or opportunity <= 1:
        return None
    if opportunity > MAX_HALF_LIFE:
        return None
    return round(opportunity, 2)


def fit_learning_rate(sequences: Mapping[str, Sequence[Mapping[str, Any]]],
                      draws: int = BOOTSTRAP_DRAWS,
                      seed: int = 0) -> dict[str, Any]:
    """Pool per-concept sequences into one within-learner learning rate.

    Fits the additive-factors model of Cen, Koedinger & Junker (2006) directly:
    ``logit P(correct) = a_c + b * opportunity``, with a free intercept per concept ``a_c``
    and a single shared slope ``b``. The slope is the learning rate.

    This borrows strength across concepts, which matters most for the learner this is for:
    someone with eight opportunities on each of six topics has too little data to fit six
    slopes, but plenty to fit one slope and six intercepts. A median of per-concept slopes
    was the first implementation and was rejected - on six short concepts it returns an
    interval so wide it cannot distinguish learning from noise, while discarding the fact
    that all six curves share a direction.

    The interval resamples opportunities within each concept with replacement and refits.
    Concepts too short to contribute are counted, not silently dropped, because borrowing
    strength is only defensible while the number of concepts doing the lending is visible.
    """
    usable = {str(concept): list(rows) for concept, rows in sequences.items() if len(rows) >= 3}
    opportunities = sum(len(rows) for rows in usable.values())
    gate = contracts.evidence_status(opportunities, contracts.MIN_OPPORTUNITIES)
    fit = fit_shared_slope(usable)
    if gate['status'] != 'measured' or fit.get('slope') is None:
        return {**gate, 'status': 'insufficient_evidence', 'learning_rate': None,
                'concepts_fitted': 0, 'concepts_available': len(sequences),
                'research_note': RATE_NOTE,
                'note': 'A learning rate needs several opportunities on at least one concept; '
                        'one or two answers cannot distinguish a curve from noise.'}
    interval = _bootstrap_slope(usable, fit['slope'], draws=draws, seed=seed)
    return {
        **gate,
        'learning_rate': round(fit['slope'], 6),
        'odds_ratio_per_opportunity': round(math.exp(fit['slope']), 4),
        'interval_90': interval,
        'concepts_fitted': fit['concepts'],
        'concepts_available': len(sequences),
        'opportunities_used': opportunities,
        'intercepts': {concept: round(value, 4)
                       for concept, value in fit['intercepts'].items()},
        'half_life_by_concept': fit['half_life_by_concept'],
        'median_half_life_opportunities': fit['median_half_life'],
        'curves': [fit_concept_curve(rows) for rows in usable.values()],
        'improving': fit['slope'] > 0,
        'research_note': RATE_NOTE,
        'note': ('Learning rate is change per opportunity, not a score: 0 means the error '
                 'rate is flat across practice, and a negative value means it rose. The '
                 'intercepts are where each concept started, which the slope deliberately '
                 'does not depend on.'),
    }


def fit_shared_slope(sequences: Mapping[str, Sequence[Mapping[str, Any]]],
                     ridge: float = RIDGE,
                     intercept_ridge: float = 1e-3) -> dict[str, Any]:
    """Newton fit of ``logit P = a_c + b * opportunity`` over several concepts at once.

    The information matrix has a diagonal block for the per-concept intercepts - no
    observation involves two intercepts - so the Newton step has a closed form by Schur
    complement and costs O(concepts) rather than the O(concepts^3) of a dense solve. That is
    what makes :func:`_bootstrap_slope` affordable, and it is exact rather than approximate:
    the same numbers a dense solve would give.

    ``ridge`` penalises the shared slope only. ``intercept_ridge`` is a numerical floor, not
    a prior: it stops a concept whose observations are all-correct from producing an infinite
    intercept, without pulling a genuinely low starting point upward.
    """
    concepts = sorted(sequences)
    if not concepts:
        return {**contracts.evidence_status(0, contracts.MIN_OPPORTUNITIES), 'slope': None}
    rows: list[tuple[int, float, float]] = []  # (concept index, opportunity, outcome)
    for index, concept in enumerate(concepts):
        for position, correct in _pairs(sequences[concept]):
            rows.append((index, position, 1.0 if correct else 0.0))
    total = len(rows)
    if total < contracts.MIN_OPPORTUNITIES:
        return {**contracts.evidence_status(total, contracts.MIN_OPPORTUNITIES),
                'slope': None, 'concepts': len(concepts)}
    intercepts = [0.0] * len(concepts)
    slope = 0.0
    converged = False
    for _ in range(MAX_ITERATIONS):
        information = [0.0] * len(concepts)   # D_i
        cross = [0.0] * len(concepts)         # s_i
        score = [0.0] * len(concepts)         # g_i
        slope_information = 0.0               # q
        slope_score = 0.0                     # g_s
        for index, position, outcome in rows:
            p = _sigmoid(intercepts[index] + slope * position)
            weight = max(1e-6, p * (1.0 - p))
            residual = outcome - p
            information[index] += weight
            cross[index] += weight * position
            score[index] += residual
            slope_information += weight * position * position
            slope_score += residual * position
        for index in range(len(concepts)):
            information[index] += intercept_ridge
        slope_information += ridge
        # Schur complement: the intercept block is diagonal, so eliminate it exactly.
        denominator = slope_information - sum(
            cross[i] * cross[i] / information[i] for i in range(len(concepts)))
        if denominator <= 1e-12:
            break
        numerator = slope_score - sum(
            cross[i] * score[i] / information[i] for i in range(len(concepts)))
        step_slope = numerator / denominator
        steps = [(score[i] - cross[i] * step_slope) / information[i]
                 for i in range(len(concepts))]
        # Damping: a separated start can produce a step long enough to saturate every
        # prediction, from which Newton cannot recover. Halving keeps it in range.
        scale = max(1.0, abs(step_slope) / 2.0, max((abs(s) for s in steps), default=0.0) / 4.0)
        for index in range(len(concepts)):
            intercepts[index] += steps[index] / scale
        slope += step_slope / scale
        if max(abs(step_slope), max((abs(s) for s in steps), default=0.0)) < 1e-8:
            converged = True
            break
    half_lives: dict[str, float | None] = {}
    for index, concept in enumerate(concepts):
        half_lives[concept] = _half_life(intercepts[index], slope, len(sequences[concept]))
    usable_half_lives = [value for value in half_lives.values() if value is not None]
    return {
        'status': 'measured',
        'slope': slope,
        'intercepts': dict(zip(concepts, intercepts)),
        'concepts': len(concepts),
        'opportunities': total,
        'half_life_by_concept': half_lives,
        'median_half_life': round(_median(usable_half_lives), 2) if usable_half_lives else None,
        'converged': converged,
        'ridge': ridge,
    }


def _median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    if not n:
        return 0.0
    middle = n // 2
    return ordered[middle] if n % 2 else (ordered[middle - 1] + ordered[middle]) / 2.0


def _bootstrap_slope(usable: Mapping[str, Sequence[Mapping[str, Any]]],
                     point: float, draws: int, seed: int) -> dict[str, Any] | None:
    """Pivotal (basic) bootstrap interval for the shared slope.

    Resamples opportunities within each concept, refits, and reflects the resulting percentile
    interval about the point estimate: ``[2*theta - q95, 2*theta - q05]``.

    **The reflection is not decoration.** A plain percentile interval on this data under-covers,
    and the benchmark caught it: nominal 90% intervals contained the true rate only 80% of the
    time on the full rate range. The cause is structural. Resampling with replacement produces
    duplicate opportunities and gaps, which flattens the resampled curve, so the bootstrap
    distribution sits *below* the estimate and the percentile interval is displaced downward -
    it misses the truth on the high side and reports more precision than it has. The pivotal
    correction removes that first-order displacement and brought measured coverage to 0.92
    against a nominal 0.90.

    A wrong interval is worse than no interval here, because it is displayed beside a number a
    learner is asked to trust: an interval that excludes zero for a learner who is not
    improving manufactures exactly the false confidence this instrument exists to prevent.
    """
    if draws <= 0 or not usable:
        return None
    generator = random.Random(seed)
    estimates: list[float] = []
    for _ in range(draws):
        resampled: dict[str, list[dict[str, Any]]] = {}
        for concept, rows in usable.items():
            # Resample whole rows so each outcome stays attached to the opportunity number
            # it was observed at. A resample may repeat some opportunities and omit others,
            # which is exactly what the non-parametric bootstrap means for a regression.
            resampled[concept] = [dict(rows[generator.randrange(len(rows))])
                                  for _ in range(len(rows))]
        fit = fit_shared_slope(resampled)
        if fit.get('slope') is not None:
            estimates.append(float(fit['slope']))
    if len(estimates) < 20:
        return None
    estimates.sort()
    percentile_low = estimates[int(0.05 * (len(estimates) - 1))]
    percentile_high = estimates[int(0.95 * (len(estimates) - 1))]
    low = 2.0 * point - percentile_high
    high = 2.0 * point - percentile_low
    return {
        'low': round(low, 6), 'high': round(high, 6), 'draws': len(estimates),
        'method': 'pivotal',
        'includes_zero': bool(low <= 0.0 <= high),
        'percentile': {'low': round(percentile_low, 6), 'high': round(percentile_high, 6)},
        'note': ('The 5th-95th percentile interval from resampling opportunities within each '
                 'concept, reflected about the estimate to correct the downward displacement '
                 'duplicate resampling causes. An interval that includes zero means this much '
                 'practice does not yet establish that the error rate is falling.'),
    }


# ------------------------------------------------------------------ effect magnitudes

def normalized_gain(pre: float, post: float, maximum: float = 1.0) -> dict[str, Any]:
    """Hake's normalized gain ``<g> = (post - pre) / (maximum - pre)``.

    Reported with the caveat that makes it usable: ``<g>`` is *negatively correlated with the
    pretest score* by construction, because a learner already at 90% has only ten points of
    headroom. It is therefore only comparable between measurements that share a pretest, and
    the learning rate is the metric to compare across learners or across conditions.
    """
    pre = min(1.0, max(0.0, float(pre)))
    post = min(1.0, max(0.0, float(post)))
    headroom = maximum - pre
    if headroom <= 1e-9:
        return {'status': 'ceiling', 'pre': pre, 'post': post, 'gain': None,
                'note': 'The pretest is already at the maximum, so there is no headroom to '
                        'normalise against; <g> is undefined rather than 1.0.'}
    gain = (post - pre) / headroom
    return {
        'status': 'measured', 'pre': round(pre, 4), 'post': round(post, 4),
        'gain': round(gain, 4),
        'band': ('high' if gain >= 0.7 else 'medium' if gain >= 0.3 else 'low'),
        'note': 'Hake (1998) bands: <0.3 low, 0.3-0.7 medium, >0.7 high. <g> shrinks as the '
                'pretest rises, so compare it only across measurements with the same pretest.',
    }


def cohens_d(treatment: Sequence[float], control: Sequence[float]) -> dict[str, Any]:
    """Standardised mean difference with Hedges' small-sample correction.

    The correction is applied by default because a single learner's samples are small by
    definition, and uncorrected ``d`` overstates the effect exactly where it matters most.
    """
    n1, n2 = len(treatment), len(control)
    if n1 < 2 or n2 < 2:
        return {**contracts.evidence_status(min(n1, n2), 2), 'd': None,
                'note': 'A standardised difference needs at least two observations per side.'}
    m1 = sum(treatment) / n1
    m2 = sum(control) / n2
    v1 = sum((x - m1) ** 2 for x in treatment) / (n1 - 1)
    v2 = sum((x - m2) ** 2 for x in control) / (n2 - 1)
    pooled = math.sqrt(((n1 - 1) * v1 + (n2 - 1) * v2) / (n1 + n2 - 2))
    if pooled <= 1e-12:
        return {'status': 'degenerate', 'd': None,
                'note': 'Both groups have zero variance, so a standardised difference is '
                        'undefined; report the two means instead.'}
    d = (m1 - m2) / pooled
    correction = 1.0 - 3.0 / (4.0 * (n1 + n2) - 5.0)
    return {'status': 'measured', 'd': round(d, 4), 'g_hedges': round(d * correction, 4),
            'n1': n1, 'n2': n2,
            'note': 'Cohen (1988) conventions; Kraft (2020) shows education effects are much '
                    'smaller in practice (0.05 SD is a small but real schooling effect).'}


def time_to_criterion(sequence: Sequence[Mapping[str, Any]],
                      threshold: float = 0.8, window: int = 4) -> dict[str, Any]:
    """Opportunities until a trailing-window accuracy first reaches ``threshold``.

    A *trailing* window rather than a running total, because a running total cannot fall:
    it would call a learner "at criterion" after a lucky streak that was immediately
    followed by collapse. The trailing window means the criterion must be sustained.
    """
    if len(sequence) < window:
        return {**contracts.evidence_status(len(sequence), window),
                'opportunities_to_criterion': None,
                'note': f'A sustained criterion needs at least {window} opportunities.'}
    for index in range(window, len(sequence) + 1):
        recent = sequence[index - window:index]
        accuracy = sum(1 for row in recent if row.get('correct')) / window
        if accuracy >= threshold:
            return {'status': 'measured', 'opportunities_to_criterion': index,
                    'threshold': threshold, 'window': window,
                    'sustained_accuracy': round(accuracy, 4)}
    return {'status': 'not_reached', 'opportunities_to_criterion': None,
            'threshold': threshold, 'window': window,
            'note': f'Accuracy never held at {threshold:.0%} across {window} consecutive '
                    'opportunities in this sequence.'}


def instructional_efficiency(performance: Sequence[float],
                             effort: Sequence[float]) -> dict[str, Any]:
    """Paas & van Merriënboer (1993) efficiency: ``(Z_perf - Z_effort) / sqrt(2)``.

    Standardised within the samples supplied. Positive means performance is high relative to
    the effort reported; negative means effort was spent without the result. The scalar is
    returned alongside the two raw arrays because van Gog & Paas (2008) warn that the single
    number hides the trade-off - a learner can be "efficient" by doing very little.

    Effort is the Paas 9-point subjective rating, sampled per task. The harness collects it
    as a one-tap micro-probe rather than a survey for the reason every cognitive-load
    researcher gives: a measure that interrupts the task changes the thing it measures.
    """
    if len(performance) != len(effort) or len(performance) < 3:
        return {**contracts.evidence_status(min(len(performance), len(effort)), 3),
                'efficiency': None,
                'note': 'Needs at least three paired performance and effort readings of equal '
                        'length; mismatched lengths usually mean an unanswered prompt.'}
    z_perf = _z_scores(performance)
    z_effort = _z_scores(effort)
    scores = [(p - e) / math.sqrt(2.0) for p, e in zip(z_perf, z_effort)]
    mean = sum(scores) / len(scores)
    return {'status': 'measured', 'efficiency': round(mean, 4), 'n': len(scores),
            'mean_performance': round(sum(performance) / len(performance), 4),
            'mean_effort': round(sum(effort) / len(effort), 4),
            'note': 'Positive = more result per unit of reported effort. Read with the two '
                    'means: high efficiency at low performance is not good news.'}


def _z_scores(values: Sequence[float]) -> list[float]:
    n = len(values)
    mean = sum(values) / n
    variance = sum((value - mean) ** 2 for value in values) / (n - 1) if n > 1 else 0.0
    sd = math.sqrt(variance)
    if sd <= 1e-12:
        return [0.0] * n
    return [(value - mean) / sd for value in values]


def gain_per_hour(pre: float, post: float, engaged_seconds: float) -> dict[str, Any]:
    """Absolute improvement per engaged hour - the denominator everything else divides by.

    Uses engaged time, not wall time, and refuses below a minute of it: dividing a gain by
    0.4 seconds produces a spectacular number that describes the divisor.
    """
    if engaged_seconds < 60:
        return {**contracts.evidence_status(int(engaged_seconds // 20), 3),
                'gain_per_hour': None,
                'note': f'Only {engaged_seconds:.0f}s of engaged time; a rate per hour would '
                        'be an artefact of the denominator.'}
    gain = float(post) - float(pre)
    hours = engaged_seconds / 3600.0
    return {'status': 'measured', 'gain_per_hour': round(gain / hours, 4),
            'gain': round(gain, 4), 'engaged_hours': round(hours, 4),
            'note': 'Raw proportion-per-hour, not normalised: it is comparable only between '
                    'measurements with the same pretest. Use the learning rate to compare '
                    'across learners.'}


def aided_unaided_gap(aided: Mapping[str, Any], unaided: Mapping[str, Any]) -> dict[str, Any]:
    """The difference between supported and unsupported accuracy, with its uncertainty.

    This is the diagnostic the harness exists to produce. A large positive gap means the
    support is carrying the performance: the learner looks better inside the product than
    they are without it. Bastani et al. (2024) is the reference case - +48% during assisted
    practice and -17% on the unaided exam, a swing a practice-accuracy dashboard renders as
    unqualified progress.

    A gap near zero is not automatically good news either: if unaided accuracy is also low,
    the support is not working. That is why the two rates are always returned together.
    """
    n_a = int(aided.get('n') or 0)
    n_u = int(unaided.get('n') or 0)
    gate = contracts.evidence_status(n_u, contracts.MIN_UNAIDED_OBSERVATIONS)
    if n_a < 3 or gate['status'] != 'measured':
        return {**gate, 'gap': None, 'aided_accuracy': aided.get('accuracy'),
                'unaided_accuracy': unaided.get('accuracy'),
                'note': ('The gap is the most consequential number in this report, so it is '
                         'withheld until there are enough unaided observations to estimate it. '
                         'Reporting it on two answers would be guessing loudly.')}
    p_a = float(aided.get('accuracy') or 0.0)
    p_u = float(unaided.get('accuracy') or 0.0)
    gap = p_a - p_u
    pooled = (p_a * n_a + p_u * n_u) / (n_a + n_u)
    se = math.sqrt(max(0.0, pooled * (1 - pooled)) * (1.0 / n_a + 1.0 / n_u))
    z = gap / se if se > 1e-9 else None
    if abs(gap) < 0.10:
        verdict = 'support is not inflating measured performance'
    elif gap > 0:
        verdict = 'performance with support exceeds unaided performance'
    else:
        verdict = 'unaided performance exceeds performance with support'
    return {'status': 'measured', 'gap': round(gap, 4),
            'aided_accuracy': round(p_a, 4), 'unaided_accuracy': round(p_u, 4),
            'aided_n': n_a, 'unaided_n': n_u,
            'standard_error': round(se, 4), 'z': round(z, 3) if z is not None else None,
            'significant_at_95': bool(z is not None and abs(z) >= 1.96),
            'verdict': verdict,
            'note': ('A positive gap is not a failure of the learner; it measures how much of '
                     'the observed performance belongs to the support. Shrink it by making '
                     'practice harder to be helped through, not by warning the learner.')}


def retention_ratio(immediate: float, delayed: float) -> dict[str, Any]:
    """Delayed accuracy as a fraction of immediate accuracy.

    A ratio below 1 is the normal and expected case - forgetting is not a defect. What matters
    is its size and its trend: Bjork's desirable-difficulties account predicts that conditions
    which make the immediate test look best often lower this ratio, so a report that shows only
    the immediate number is showing the one that can be gamed by massing practice.
    """
    immediate = max(0.0, min(1.0, float(immediate)))
    delayed = max(0.0, min(1.0, float(delayed)))
    if immediate <= 1e-9:
        return {'status': 'undefined', 'ratio': None,
                'note': 'Immediate accuracy is zero, so a proportion of it is undefined.'}
    return {'status': 'measured', 'ratio': round(delayed / immediate, 4),
            'absolute_drop': round(immediate - delayed, 4),
            'immediate': round(immediate, 4), 'delayed': round(delayed, 4),
            'note': 'Some drop is expected. The number to watch is the drop for material '
                    'practised the same way over time, not its absolute size.'}


__all__ = ['BOOTSTRAP_DRAWS', 'MAX_HALF_LIFE', 'RATE_NOTE', 'RIDGE', 'aided_unaided_gap',
           'cohens_d', 'fit_concept_curve', 'fit_learning_rate', 'fit_shared_slope',
           'gain_per_hour', 'instructional_efficiency', 'normalized_gain',
           'retention_ratio', 'time_to_criterion']
