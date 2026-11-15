"""A benchmark with a known answer, which is the only kind available to a one-learner product.

The problem with benchmarking this
----------------------------------
Every off-the-shelf benchmark in this space - ASSISTments, EdNet, the Eedi/NeurIPS tasks -
evaluates a *knowledge-tracing model* on *other people's* interaction logs, scored by next-step
prediction AUC. None of them can tell you whether the measurement in *this* harness reports
what it claims to report, because none of them has an answer key for "this learner's true
learning rate". AUC on a public corpus says a model predicts held-out responses well; it says
nothing about whether the efficiency figure shown to a learner is biased.

So the benchmark here is a **recovery** benchmark. Synthetic learners are generated with a
learning rate that is known because it was set, put through the same pipeline the product uses,
and then the estimates are compared against the truth. Three questions follow from that, and
only the first is the obvious one:

1. **Recovery** - does the estimator return the true rate? Measured as bias and as rank
   correlation across learners, because ranking learners correctly ("this one is improving
   faster") matters more than the absolute value of a log-odds slope nobody reads directly.
2. **Coverage** - does a nominal 90% interval contain the truth 90% of the time? An estimator
   can be unbiased and still useless if its interval is a lie, and a wrong interval is worse
   than none because it manufactures confidence.
3. **Discrimination** - does the instrument separate a learner who is learning from one who is
   not, and can it tell supported performance apart from unaided performance? This is the check
   that justifies the whole probe apparatus: if aided and unaided readings were
   indistinguishable on data where they provably differ, the probe would be decoration.

What this benchmark cannot do
-----------------------------
It validates the *estimator*, not the product. A synthetic learner is a known statistical
process; a real learner is not, and no simulation proves that learning rate measured here
predicts a real exam. That claim needs the field experiment described in
``docs/MEASUREMENT.md``, and the code is careful not to imply otherwise: every payload says
``validates: estimator`` and names what remains unvalidated.
"""

from __future__ import annotations

import math
import random
from typing import Any, Sequence

from . import contracts, estimators

#: Default synthetic cohort. Large enough that a 90% coverage interval has a standard error of
#: about 2 percentage points, small enough that the whole suite runs in a couple of seconds.
DEFAULT_LEARNERS = 200

#: Practice opportunities per simulated learner, and the true rates they are drawn from. The
#: spread is deliberately wide: a benchmark that only ever simulates mid-range learners cannot
#: show that the estimator fails gracefully at the extremes.
OPPORTUNITIES = 40
TRUE_RATE_RANGE = (0.02, 0.30)

SCOPE = (
    'Validates the estimator against a known generating process. It does not show that a '
    'measured learning rate predicts an external exam, that real learners follow this curve, '
    'or that the probe schedule is adhered to in use. Those are field questions; see '
    'docs/MEASUREMENT.md for the design that would answer them.'
)


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exponent = math.exp(value)
    return exponent / (1.0 + exponent)


def simulate_learner(*, rate: float, seed: int, opportunities: int = OPPORTUNITIES,
                     start_logit: float = -1.2, aided_boost: float = 0.0,
                     concept: str = 'sim') -> list[dict[str, Any]]:
    """One learner whose per-opportunity improvement is exactly ``rate`` in log-odds.

    ``aided_boost`` is the extra log-odds that support conditions confer. It is the parameter
    the aided-versus-unaided check is built on: setting it to zero says the support changes
    nothing, and a large value says a supported answer is much more likely than an unsupported
    one at identical knowledge.
    """
    generator = random.Random(seed)
    rows = []
    for position in range(1, opportunities + 1):
        probability = _sigmoid(start_logit + rate * position + aided_boost)
        rows.append({
            'created_at': float(position * 60),
            'elapsed_seconds': 20.0,
            'concept_id': concept,
            'correct': generator.random() < probability,
            'mode': 'practice',
            'question_id': f'{concept}-q{position}',
            'opportunity': position,
        })
    return rows


def simulate_probes(*, rate: float, seed: int, start_logit: float = -1.2,
                    count: int = 8, concept: str = 'sim') -> list[dict[str, Any]]:
    """The same learner's *unaided* readings, with no support boost.

    Deliberately drawn from the same underlying curve: the difference between this and
    :func:`simulate_learner` is only the boost, so any measured gap is attributable to support
    rather than to a different generating process.
    """
    generator = random.Random(seed + 10_000)
    rows = []
    for index in range(1, count + 1):
        position = index * (OPPORTUNITIES / count)
        probability = _sigmoid(start_logit + rate * position)
        rows.append({
            'created_at': float(position * 60),
            'question_id': f'{concept}-p{index}',
            'concept_id': concept,
            'correct': generator.random() < probability,
            'mode': 'cold',
            'elapsed_seconds': 30.0,
            'opportunity': index,
        })
    return rows


def _accuracy(rows: Sequence[dict[str, Any]]) -> float:
    return sum(1 for row in rows if row['correct']) / len(rows) if rows else 0.0


def _spearman(pairs: Sequence[tuple[float, float]]) -> float | None:
    """Rank correlation with average ranks for ties, implemented rather than imported.

    The application deliberately carries no statistics dependency, and a benchmark that needs
    one to run is a benchmark that runs less often.
    """
    usable = [(a, b) for a, b in pairs if a is not None and b is not None]
    if len(usable) < 3:
        return None
    ranks_a = _ranks([a for a, _ in usable])
    ranks_b = _ranks([b for _, b in usable])
    n = len(usable)
    mean_a = sum(ranks_a) / n
    mean_b = sum(ranks_b) / n
    covariance = sum((x - mean_a) * (y - mean_b) for x, y in zip(ranks_a, ranks_b))
    var_a = math.sqrt(sum((x - mean_a) ** 2 for x in ranks_a))
    var_b = math.sqrt(sum((y - mean_b) ** 2 for y in ranks_b))
    if var_a <= 1e-12 or var_b <= 1e-12:
        return None
    return covariance / (var_a * var_b)


def _ranks(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    position = 0
    while position < len(order):
        end = position
        while end + 1 < len(order) and values[order[end + 1]] == values[order[position]]:
            end += 1
        average = (position + end) / 2.0 + 1.0
        for index in range(position, end + 1):
            ranks[order[index]] = average
        position = end + 1
    return ranks


# --------------------------------------------------------------------------- the checks

def check_recovery(learners: int = DEFAULT_LEARNERS, seed: int = 0) -> dict[str, Any]:
    """Does the estimator return the rate that was set?

    Split by whether the curve is *identifiable*, which the first version of this check was not
    and which made it look like an estimator defect rather than a property of the data. A
    learner who reaches near-perfect accuracy at opportunity ten contributes almost no
    information about their slope after that: every rate above theirs fits the remaining
    all-correct observations equally well. Their estimate is unbiased but imprecise, and no
    amount of estimator improvement changes that - the information is not in the sequence.

    So the gate is applied to learners whose curve is still rising at the end of the window,
    and the saturated group is reported beside them rather than quietly dropped. Bias and rank
    correlation are computed over everyone, because both remain meaningful under saturation:
    the estimate is still centred on the truth and still orders learners correctly, it is
    simply wider.
    """
    generator = random.Random(seed)
    pairs: list[tuple[float, float]] = []
    errors: list[float] = []
    identifiable_errors: list[float] = []
    saturated_errors: list[float] = []
    saturated = 0
    for index in range(learners):
        true_rate = generator.uniform(*TRUE_RATE_RANGE)
        rows = simulate_learner(rate=true_rate, seed=seed * 1000 + index)
        estimate = estimators.fit_learning_rate({'sim': rows}, draws=0).get('learning_rate')
        if estimate is None:
            continue
        pairs.append((true_rate, estimate))
        errors.append(estimate - true_rate)
        # "Still rising" is judged from the observed sequence, not from the parameter, so the
        # split is available for real data too.
        if _accuracy(rows[-10:]) >= 0.95:
            saturated += 1
            saturated_errors.append(estimate - true_rate)
        else:
            identifiable_errors.append(estimate - true_rate)
    rho = _spearman(pairs)
    bias = sorted(errors)[len(errors) // 2] if errors else None
    mae = sum(abs(value) for value in identifiable_errors) / len(identifiable_errors) \
        if identifiable_errors else None
    saturated_mae = (sum(abs(value) for value in saturated_errors) / len(saturated_errors)
                     if saturated_errors else None)
    return {
        'check': 'recovery',
        'question': 'Does the estimator return the learning rate that was set?',
        'learners': learners,
        'estimated': len(pairs),
        'median_bias': round(bias, 5) if bias is not None else None,
        'mean_absolute_error_identifiable': round(mae, 5) if mae is not None else None,
        'mean_absolute_error_saturated': (round(saturated_mae, 5)
                                          if saturated_mae is not None else None),
        'saturated': saturated,
        'rank_correlation': round(rho, 4) if rho is not None else None,
        'passes': bool(rho is not None and rho >= 0.6
                       and bias is not None and abs(bias) <= 0.02
                       and mae is not None and mae <= 0.06),
        'criterion': ('rank correlation >= 0.60, |median bias| <= 0.02, and mean absolute '
                      'error <= 0.06 on identifiable curves'),
        'note': ('Rank correlation is the headline: it decides whether the instrument orders '
                 'learners correctly, which is what the product uses. The saturated group is '
                 'reported rather than dropped - their estimate is unbiased but imprecise, '
                 'because a curve that finishes at ceiling contains no further information '
                 'about its slope.'),
    }


def check_coverage(learners: int = 120, seed: int = 1, draws: int = 150) -> dict[str, Any]:
    """Does a nominal 90% interval contain the truth about 90% of the time?

    An interval that is too narrow is actively harmful here: it is shown next to a number a
    learner is asked to trust, and a fabricated precision is worse than an honest wide band.
    """
    generator = random.Random(seed)
    covered = 0
    tried = 0
    widths: list[float] = []
    for index in range(learners):
        true_rate = generator.uniform(*TRUE_RATE_RANGE)
        rows = simulate_learner(rate=true_rate, seed=seed * 5000 + index)
        fit = estimators.fit_learning_rate({'sim': rows}, draws=draws, seed=index)
        interval = fit.get('interval_90')
        if not interval:
            continue
        tried += 1
        if interval['low'] <= true_rate <= interval['high']:
            covered += 1
        widths.append(interval['high'] - interval['low'])
    rate = covered / tried if tried else None
    mean_width = sum(widths) / len(widths) if widths else None
    return {
        'check': 'coverage',
        'question': 'Does the 90% interval contain the true rate 90% of the time?',
        'intervals': tried,
        'covered': covered,
        'coverage': round(rate, 4) if rate is not None else None,
        'mean_width': round(mean_width, 5) if mean_width is not None else None,
        # Tolerance is wide on purpose: with ~120 intervals the standard error of the coverage
        # estimate is around 2.7 points, so a tight band would fail on sampling noise alone.
        'passes': bool(rate is not None and 0.80 <= rate <= 0.98),
        'criterion': 'empirical coverage between 0.80 and 0.98 for a nominal 0.90',
        'note': ('Coverage below the band means the interval is too narrow and overstates '
                 'precision; above it means the interval is too wide to be useful.'),
    }


def check_discrimination(learners: int = 120, seed: int = 2) -> dict[str, Any]:
    """Can the instrument tell a learner who is learning from one who is not?

    Two synthetic groups: flat (true rate 0) and improving (true rate 0.15). A usable instrument
    must separate them. This is the check that would catch the worst possible failure - a
    measurement that responds to noise and not to learning.
    """
    generator = random.Random(seed)
    flat: list[float] = []
    improving: list[float] = []
    for index in range(learners):
        rows = simulate_learner(rate=0.0, seed=seed * 7000 + index)
        estimate = estimators.fit_learning_rate({'sim': rows}, draws=0).get('learning_rate')
        if estimate is not None:
            flat.append(estimate)
        rows = simulate_learner(rate=0.15, seed=seed * 9000 + index)
        estimate = estimators.fit_learning_rate({'sim': rows}, draws=0).get('learning_rate')
        if estimate is not None:
            improving.append(estimate)
    effect = estimators.cohens_d(improving, flat)
    separated = None
    if flat and improving:
        separated = sum(1 for value in improving if value > max(flat)) / len(improving)
    return {
        'check': 'discrimination',
        'question': 'Does the instrument separate a flat learner from an improving one?',
        'flat_mean': round(sum(flat) / len(flat), 5) if flat else None,
        'improving_mean': round(sum(improving) / len(improving), 5) if improving else None,
        'effect_size': effect.get('g_hedges'),
        'share_above_flat_max': round(separated, 4) if separated is not None else None,
        'passes': bool(effect.get('d') is not None and effect['d'] >= 0.8),
        'criterion': "Cohen's d >= 0.8 between flat and improving groups",
        'note': 'A measurement that cannot separate these two has no diagnostic value at all.',
    }


def check_aided_inflation(learners: int = 200, seed: int = 3,
                          boost: float = 0.8) -> dict[str, Any]:
    """Does an aided reading overstate what an unaided reading shows, as it should?

    The synthetic learner has an identical underlying rate in both conditions and a support
    boost of ``boost`` log-odds in the aided one. The check confirms two things: that a naive
    practice-accuracy reading is genuinely inflated by the boost (so the problem the probe
    solves is real in this data), and that the aided-minus-unaided gap estimator recovers that
    inflation rather than reporting zero.

    If this check came back negative the probe apparatus would be unjustified - the harness
    would be spending learner attention on a distinction that does not exist in its own data.
    """
    generator = random.Random(seed)
    naive_gap: list[float] = []
    measured_gap: list[float] = []
    for index in range(learners):
        rate = generator.uniform(*TRUE_RATE_RANGE)
        practice = simulate_learner(rate=rate, seed=seed * 11_000 + index, aided_boost=boost)
        probes = simulate_probes(rate=rate, seed=seed * 13_000 + index)
        naive_gap.append(_accuracy(practice) - _accuracy(probes))
        reading = estimators.aided_unaided_gap(
            {'n': len(practice), 'accuracy': _accuracy(practice)},
            {'n': len(probes), 'accuracy': _accuracy(probes)},
        )
        if reading.get('gap') is not None:
            measured_gap.append(reading['gap'])
    mean_naive = sum(naive_gap) / len(naive_gap) if naive_gap else 0.0
    mean_measured = (sum(measured_gap) / len(measured_gap)) if measured_gap else None
    positive_share = (sum(1 for gap in measured_gap if gap > 0) / len(measured_gap)
                      if measured_gap else None)
    # The gate is on the estimator's *aggregate* agreement with the truth, not on the sign of
    # each learner's gap. With eight unaided observations the standard error of the difference
    # is about 0.19, so a true gap of 0.07 cannot be signed reliably for one learner - an
    # earlier version gated on per-learner sign and failed for that reason alone, which was a
    # statement about power rather than about validity.
    tracks_truth = (mean_measured is not None
                    and abs(mean_measured - mean_naive) <= 0.04)
    return {
        'check': 'aided_inflation',
        'question': 'Does support inflate measured accuracy, and does the gap estimator see it?',
        'boost_log_odds': boost,
        'mean_observed_inflation': round(mean_naive, 4),
        'mean_estimated_gap': round(mean_measured, 4) if mean_measured is not None else None,
        'share_with_positive_gap': round(positive_share, 4) if positive_share is not None else None,
        'passes': bool(mean_naive >= 0.05 and tracks_truth),
        'criterion': ('mean observed inflation >= 0.05 and the estimator\'s mean gap within '
                      '0.04 of it'),
        'note': ('Confirms the confound the cold probe exists to remove is present in the '
                 'data at the stated size, and that the estimator tracks it in the same '
                 'direction rather than cancelling it. The per-learner sign is reported but '
                 'not gated: at eight unaided observations it is dominated by sampling noise, '
                 'and gating on it would be gating on power, not on validity.'),
    }


def check_null_false_positive(learners: int = 200, seed: int = 4) -> dict[str, Any]:
    """How often does a learner who is not improving get a positive interval?

    The failure being measured: reporting "your error rate is falling" for someone whose error
    rate is flat. A statistical test that fires on 30% of flat learners is not a measurement.
    """
    generator = random.Random(seed)
    fired = 0
    tried = 0
    for index in range(learners):
        rows = simulate_learner(rate=0.0, seed=seed * 17_000 + index)
        fit = estimators.fit_learning_rate({'sim': rows}, draws=80, seed=index)
        interval = fit.get('interval_90')
        if not interval:
            continue
        tried += 1
        if interval['low'] > 0:
            fired += 1
    rate = fired / tried if tried else None
    return {
        'check': 'null_false_positive',
        'question': 'How often is a flat learner reported as improving?',
        'intervals': tried,
        'false_positives': fired,
        'false_positive_rate': round(rate, 4) if rate is not None else None,
        # A 90% interval should exclude zero for at most about 5% of truly flat learners,
        # since the interval is one-sided here only one tail can fire.
        'passes': bool(rate is not None and rate <= 0.12),
        'criterion': 'false positive rate <= 0.12 at a nominal 5% one-sided',
        'note': ('A rate above this means the harness would tell learners they are improving '
                 'when they are not, which is the most damaging error this instrument can make.'),
    }


def run_suite(learners: int = DEFAULT_LEARNERS, seed: int = 0) -> dict[str, Any]:
    """Every check, with a single pass/fail the packaging gate can assert on."""
    checks = [
        check_recovery(learners=learners, seed=seed),
        check_coverage(learners=max(60, learners // 2), seed=seed + 1),
        check_discrimination(learners=max(60, learners // 2), seed=seed + 2),
        check_aided_inflation(learners=learners, seed=seed + 3),
        check_null_false_positive(learners=max(60, learners // 2), seed=seed + 4),
    ]
    passed = sum(1 for check in checks if check['passes'])
    return {
        'suite': 'learning-efficiency estimator recovery',
        'validates': 'estimator',
        'learners': learners,
        'passed': passed,
        'total': len(checks),
        'ok': passed == len(checks),
        'checks': checks,
        'scope': SCOPE,
    }


__all__ = ['DEFAULT_LEARNERS', 'OPPORTUNITIES', 'SCOPE', 'TRUE_RATE_RANGE',
           'check_aided_inflation', 'check_coverage', 'check_discrimination',
           'check_null_false_positive', 'check_recovery', 'run_suite', 'simulate_learner',
           'simulate_probes']
