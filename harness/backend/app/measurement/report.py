"""Assembling one reading of the instrument: what the learner's data can and cannot support.

This module is the only place in the package that reads a database. Everything below it is
pure, which is what lets the benchmark validate the estimators against known ground truth with
no database at all - and what makes this file short enough to audit.

The payload has one structural rule: **every figure is accompanied by the evidence it rests
on, and anything not yet measurable appears in ``cannot_claim`` instead of being omitted.**
Omitting it is the failure mode that matters. A report that simply lacks an entry for retention
reads as "retention is fine", while a report that says "retention not measured: no delayed test
has been taken" cannot be misread. The learner is being asked to trust a number about their own
mind; the least this can do is be explicit about the edges of what it knows.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from . import contracts, episodes, estimators, probe

#: Transfer delays the harness schedules, mirrored from ``learning_science.TRANSFER_DELAYS``.
#: Duplicated as a literal rather than imported so this package does not depend on the teaching
#: core; the test suite asserts the two agree.
TRANSFER_DELAYS = (7, 28)


def _blocks(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The aided and unaided buckets, and the gap between them.

    ``unaided`` is not a synonym for "first attempt": an attempt made while the tutor was open
    or the lesson was displayed is supported even if it is the first time. The bucket comes
    from the aid label, which was derived from what was actually present.
    """
    aided = [row for row in rows if not contracts.unaided(str(row.get('aid')))]
    unaided = [row for row in rows if contracts.unaided(str(row.get('aid')))]
    def rate(subset: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        correct = sum(1 for row in subset if row.get('correct'))
        return {'n': len(subset), 'correct': correct,
                'accuracy': round(correct / len(subset), 4) if subset else None}
    return {
        'aided': rate(aided),
        'unaided': rate(unaided),
        'gap': estimators.aided_unaided_gap(rate(aided), rate(unaided)),
        'mix': contracts.summarise_aid(rows),
    }


def _effort_pairs(rows: Sequence[Mapping[str, Any]],
                  ratings: Sequence[Mapping[str, Any]]) -> list[tuple[float, float]]:
    """Pair each effort rating with the accuracy of the work that preceded it.

    The rating is retrospective: the learner reports the effort a just-finished stretch of work
    cost them. Pairing it with anything other than that stretch would make the
    instructional-efficiency ratio meaningless, so the window is the one the rating closed -
    the attempts in the gap-window immediately before the rating was issued.
    """
    pairs: list[tuple[float, float]] = []
    for rating in ratings:
        value = rating.get('value')
        if value is None:
            continue
        issued = float(rating.get('issued_at') or 0)
        window = [row for row in rows
                  if 0 <= issued - float(row.get('created_at') or 0) <= contracts.EPISODE_GAP_SECONDS]
        if not window:
            continue
        accuracy = sum(1 for row in window if row.get('correct')) / len(window)
        pairs.append((accuracy, float(value)))
    return pairs


def build(attempts: Sequence[Any],
          probes: Sequence[Mapping[str, Any]] = (),
          tutor_timestamps: Iterable[float] = (),
          lesson_timestamps: Iterable[float] = (),
          retention: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """One measurement reading from already-loaded rows. No I/O, so it is directly testable.

    ``attempts`` are graded attempt rows (ORM or mapping). ``probes`` are
    ``measurement_probes`` rows as mappings. ``retention`` is the delayed-test summary the
    caller computed, because eligibility depends on the assessment tables and belongs there.
    """
    labelled = episodes.label_attempts(attempts, tutor_timestamps=tutor_timestamps,
                                       lesson_timestamps=lesson_timestamps)
    # Segmentation preserves the aid labels, so the per-episode unaided counts are consistent
    # with the global buckets by construction rather than by re-matching timestamps after.
    segments = episodes.aid_by_episode(episodes.segment(labelled))
    engagement = {
        'episodes': len(segments),
        'solve_seconds': round(sum(s['solve_seconds'] for s in segments), 1),
        'engaged_seconds': round(sum(s['engaged_seconds'] for s in segments), 1),
        'idle_seconds': round(sum(s['idle_seconds'] for s in segments), 1),
        'engaged_minutes': round(sum(s['engaged_seconds'] for s in segments) / 60.0, 1),
        'note': ('Engaged time excludes gaps longer than '
                 f'{contracts.IDLE_CAP_SECONDS:.0f}s between answers. Wall-clock time would be '
                 'larger and would make every efficiency ratio better for exactly the learner '
                 'who walks away most often.'),
    }
    blocks = _blocks(labelled)
    # Sequences are built over *all* graded attempts, because the learning rate is about the
    # material, not about the support. The aided/unaided split is reported separately and
    # answers a different question; conflating them would confound a rate with a condition.
    sequences = episodes.learning_opportunities(labelled)
    # Bootstrap draws are bounded by the size of the history. Each draw refits over every
    # opportunity, so a fixed 400 is a couple of seconds on a long history - too slow for a
    # request that a screen makes on open. Small histories keep the full draw count, which is
    # where the interval matters most; long ones trade interval stability for a responsive
    # endpoint, and the interval width is already tight at that size.
    opportunities = sum(len(rows) for rows in sequences.values())
    draws = min(estimators.BOOTSTRAP_DRAWS,
                max(60, 40_000 // max(1, opportunities)))
    rate = estimators.fit_learning_rate(sequences, draws=draws)
    # Time-to-criterion uses only unsupported observations, since a criterion reached with help
    # says when the support became unnecessary, not when the idea was available. The longest
    # unsupported sequence is used because it is the one with a chance of reaching the window.
    unaided_rows = [row for row in labelled if contracts.unaided(str(row.get('aid')))]
    unaided_sequences = episodes.learning_opportunities(unaided_rows)
    criterion = (estimators.time_to_criterion(max(unaided_sequences.values(), key=len))
                 if unaided_sequences else
                 {**contracts.evidence_status(0, 4),
                  'note': 'No unsupported observations yet, so no criterion can be timed.'})
    ratings = [row for row in probes
               if str(row.get('kind')) == 'effort' and row.get('value') is not None]
    pairs = _effort_pairs(labelled, ratings)
    efficiency = estimators.instructional_efficiency(
        [accuracy for accuracy, _effort in pairs], [effort for _accuracy, effort in pairs])
    # Only the most-practised concepts get a curve in the payload. A learner can accumulate a
    # hundred short sequences, and shipping a hundred curve arrays to draw one small chart is
    # both a slow response and a misleading picture - the long curves are the informative ones.
    if rate.get('curves'):
        rate['curves'] = sorted(rate['curves'], key=lambda curve: -curve.get('opportunities', 0))[:8]
        rate['curves_shown'] = len(rate['curves'])
    return {
        'scope': contracts.SCOPE_NOTE,
        'evidence': {
            'attempts': len(labelled),
            'episodes': engagement['episodes'],
            'aid': blocks['mix'],
            'engagement': engagement,
            'probes': probe.coverage(probes),
            'note': ('Everything below is computed from these rows. An empty or thin report is '
                     'an honest statement about the evidence, not a failure to compute.'),
        },
        'efficiency': {
            'learning_rate': rate,
            'time_to_criterion': criterion,
            'instructional_efficiency': efficiency,
            'gain_per_hour': _gain_per_hour(unaided_rows, engagement['engaged_seconds']),
        },
        'support': blocks,
        'retention': dict(retention) if retention else _no_retention(),
        'cannot_claim': _cannot_claim(rate=rate, blocks=blocks, retention=retention,
                                      efficiency=efficiency),
    }


def _gain_per_hour(unaided_rows: Sequence[Mapping[str, Any]],
                   engaged_seconds: float) -> dict[str, Any]:
    """Improvement per engaged hour, from the unsupported observations alone.

    A true pre/post design would test the learner before and after a unit on the same scale.
    The harness does not have one, so the closest defensible substitute is the first half of a
    learner's unsupported observations against the second half: same learner, same measurement
    condition, so the difference is not a support artefact. It is still weaker than a real
    pretest, because the halves may cover different material - which is why both the
    normalised gain and the raw rate are returned, and why the item sets are named as the
    caveat rather than assumed equivalent.
    """
    if len(unaided_rows) < 2 * contracts.MIN_UNAIDED_OBSERVATIONS:
        return {**contracts.evidence_status(len(unaided_rows),
                                           2 * contracts.MIN_UNAIDED_OBSERVATIONS),
                'gain_per_hour': None,
                'note': ('A gain per hour needs unsupported observations in both halves of the '
                         'history so the change is not a change of measurement condition.')}
    ordered = sorted(unaided_rows, key=lambda row: float(row.get('created_at') or 0))
    middle = len(ordered) // 2
    pre = sum(1 for row in ordered[:middle] if row.get('correct')) / middle
    post = sum(1 for row in ordered[middle:] if row.get('correct')) / (len(ordered) - middle)
    return estimators.gain_per_hour(pre, post, engaged_seconds) | {
        'normalized_gain': estimators.normalized_gain(pre, post),
        'caveat': ('Compared across the halves of one learner\'s unsupported history rather '
                   'than against a fixed pretest, so the two halves may not cover the same '
                   'items. Weak evidence by design, and labelled as such.'),
    }


def _no_retention() -> dict[str, Any]:
    return {
        'status': 'not_measured',
        'delays_days': list(TRANSFER_DELAYS),
        'note': ('No delayed test has been completed. Retention is the outcome a within-session '
                 'score cannot see, and it is deliberately not estimated: a guess here would be '
                 'the single most misleading number in the report.'),
        'next_action': (f'Practise, then return {TRANSFER_DELAYS[0]} days later and take the '
                        'delayed check.'),
    }


def _cannot_claim(*, rate: Mapping[str, Any], blocks: Mapping[str, Any],
                  retention: Mapping[str, Any] | None,
                  efficiency: Mapping[str, Any]) -> list[dict[str, str]]:
    """What this reading does not yet establish, each with the evidence that would settle it.

    Every item is a claim a dashboard would ordinarily make by default. Listing them is the
    defence against a number being read as more than it is.
    """
    claims: list[dict[str, str]] = []
    if rate.get('status') != 'measured' or rate.get('learning_rate') is None:
        claims.append({
            'claim': 'that your error rate is falling',
            'why_not': (f'{rate.get("observations", 0)} of {contracts.MIN_OPPORTUNITIES} '
                        'opportunities needed on at least one concept.'),
            'to_settle': f'Keep practising one concept to {contracts.MIN_OPPORTUNITIES}+ '
                         'attempts.',
        })
    elif rate.get('interval_90', {}).get('includes_zero'):
        claims.append({
            'claim': 'that your error rate is falling',
            'why_not': ('The interval on the learning rate includes zero, so a flat curve has '
                        'not been ruled out.'),
            'to_settle': 'More practice opportunities spread across several concepts.',
        })
    if blocks['unaided']['n'] < contracts.MIN_UNAIDED_OBSERVATIONS:
        claims.append({
            'claim': 'that what you can do unprompted matches what you can do with help',
            'why_not': (f'Only {blocks["unaided"]["n"]} unsupported observations; '
                        f'{contracts.MIN_UNAIDED_OBSERVATIONS} are needed before the gap is '
                        'estimated.'),
            'to_settle': 'Accept a cold recall check when one is offered.',
        })
    if retention is None or retention.get('status') != 'measured':
        claims.append({
            'claim': 'that you will still know this in a week',
            'why_not': 'No delayed check has been taken; nothing here measures retention.',
            'to_settle': f'Take the delayed check {TRANSFER_DELAYS[0]} days after practice.',
        })
    if efficiency.get('status') != 'measured':
        claims.append({
            'claim': 'that the learning was cheap in mental effort',
            'why_not': (f'{efficiency.get("observations", 0)} usable effort rating(s) paired '
                        f'with performance; {efficiency.get("minimum", 3)} are needed before '
                        'the ratio is identified.'),
            'to_settle': 'Answer the one-tap effort question at the end of each sitting.',
        })
    claims.append({
        'claim': 'that this predicts your AP or external exam result',
        'why_not': ('Nothing in this harness is normed against an external exam, and no '
                    'external outcome has been observed.'),
        'to_settle': 'An external criterion study; this instrument is not one.',
    })
    return claims


def read(db, user) -> dict[str, Any]:
    """Load this account's rows and build the reading.

    Imports ``graded_attempts`` lazily: the withholding rule for exam items lives in
    ``main`` and must not be re-implemented here, or a withheld exam answer would leak into
    the efficiency figures. The lazy import also keeps this module importable without the
    application, which the tests and the benchmark rely on.
    """
    from sqlalchemy import select

    from ..db import Assessment, Message, TelemetryEvent
    from ..main import graded_attempts
    from .models import MeasurementProbe

    attempts = graded_attempts(db, user)
    # A tutor turn is the strongest aid confound, so its timestamps are read from the message
    # log rather than inferred. User turns are excluded: the learner talking does not supply
    # an answer, the tutor replying might.
    tutor_times = [float(row.created_at) for row in db.scalars(
        select(Message).where(Message.user_id == user.id, Message.role == 'tutor'))]
    lesson_times = [float(row.received_at) for row in db.scalars(
        select(TelemetryEvent).where(TelemetryEvent.user_id == user.id,
                                     TelemetryEvent.type == 'lesson_view'))]
    probes = [{'kind': row.kind, 'status': row.status, 'concept_id': row.concept_id,
               'value': row.value, 'issued_at': row.issued_at,
               'completed_at': row.completed_at, 'reason': row.reason,
               'conditions': row.conditions, 'response': row.response}
              for row in db.scalars(select(MeasurementProbe).where(
                  MeasurementProbe.user_id == user.id))]

    return build(attempts, probes=probes, tutor_timestamps=tutor_times,
                 lesson_timestamps=lesson_times,
                 retention=_retention(db, user, Assessment, select))


def _retention(db, user, Assessment, select) -> dict[str, Any] | None:
    """The best completed delayed test, if any.

    "Best" is the longest delay that has been completed, not the highest score: the question is
    what survived, so a 28-day result is a stronger answer than a 7-day one and choosing the
    higher score would be selecting the flattering measurement.
    """
    rows = [row for row in db.scalars(select(Assessment).where(
        Assessment.user_id == user.id, Assessment.mode == 'transfer',
        Assessment.complete.is_(True))) if row.total]
    if not rows:
        return None
    best = max(rows, key=lambda row: (row.delay_days or 0, row.created_at))
    return {
        'status': 'measured',
        'delay_days': best.delay_days,
        'correct': best.correct,
        'total': best.total,
        'accuracy': round(best.correct / best.total, 4) if best.total else None,
        'completed_at': best.created_at,
        'delays_available': sorted({row.delay_days for row in rows if row.delay_days}),
        'note': ('Taken without tutor access, so this is a retention reading rather than a '
                 'performance reading. A single test at one delay cannot separate forgetting '
                 'from a hard item set; the 7-vs-28 comparison is what does.'),
    }


__all__ = ['TRANSFER_DELAYS', 'build', 'read']
