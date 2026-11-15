"""HTTP surface for learning-efficiency measurement: ``/api/v1/measurement``.

Thin for the same reason :mod:`app.routes_supervision` is: the policy about *when* to probe and
*what* a reading means lives in :mod:`app.measurement`, and a rule that lives in a route is a
rule the next route will disagree with. This module scopes to the caller, fills in the belief
and the conditions the client must not be allowed to state for itself, and serialises.

Two boundaries enforced here
----------------------------
**The client does not report whether its own answer was correct.** A probe that accepted
``correct: true`` would be a self-marked test, and the entire point of the cold probe is that
it measures something the learner cannot talk up. ``complete`` therefore takes an ``attempt_id``
and reads correctness from the server-graded ``Attempt`` row - the same row ``/attempts``
produced, with the same receipt verification behind it.

**The conditions are recorded by the server, not claimed by the client.** When a probe is
issued, the support state is captured into ``conditions``. A client cannot assert after the
fact that the learner was unaided; it can only point at the attempt that answered the probe.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from .db import Attempt, now_ts
from .measurement import bench, episodes, probe, report
from .measurement.models import MeasurementProbe
from .security import resolve_account, require_principal


router = APIRouter(dependencies=[Depends(require_principal("api", 180))])

API = '/api/v1/measurement'


def authenticated(request: Request):
    """Resolve ``(db, user)`` from the bearer token, through ``security.resolve_account``."""
    from .main import start_write
    factory = request.app.state.factory
    with factory() as db:
        user = resolve_account(request, db, rate_key='api', limit=180)
        start_write(db)
        token = request.state.token
        token.last_used_at = now_ts()
        user.last_seen_at = now_ts()
        yield db, user
        db.commit()


class CompleteInput(BaseModel):
    """Which server-graded attempt answered the probe.

    Nothing else. ``correct`` is deliberately absent: it is read from the attempt, so a client
    that wanted to inflate or deflate a reading would have to forge a graded attempt, which the
    receipt and payload-hash checks in ``/attempts`` already make expensive.
    """

    model_config = {'extra': 'forbid'}

    attempt_id: str = Field(min_length=1, max_length=36)


class EffortInput(BaseModel):
    """The Paas 1992 rating. An integer on the published nine-point scale."""

    model_config = {'extra': 'forbid'}

    value: int = Field(ge=1, le=9)
    concept_id: str = Field(default='', max_length=120)


@router.get(API)
def describe_measurement(principal=Depends(authenticated)):
    """What the harness measures, on what conditions, and how often it may interrupt."""
    return {
        **probe.describe(),
        'report_url': f'{API}/report',
        'note': ('Measurement is opt-in through use: a learner who never accepts a probe still '
                 'gets a report, with the unsupported half of it declared as not measured.'),
    }


@router.get(API + '/report')
def measurement_report(principal=Depends(authenticated)):
    """One reading of learning efficiency, progress and retention for this account."""
    db, user = principal
    return report.read(db, user)


@router.get(API + '/probe/next')
def probe_next(principal=Depends(authenticated)):
    """Whether a cold probe is due now, and why not if not.

    Read-only: it decides without writing. ``POST /probe`` is what actually issues one, so a
    client polling this on every screen change cannot consume the budget.
    """
    db, user = principal
    return _cold_decision(db, user)


def _cold_decision(db, user) -> dict[str, Any]:
    from .main import graded_attempts

    attempts = graded_attempts(db, user)
    labelled = episodes.label_attempts(attempts)
    practice_by_concept: dict[str, int] = {}
    for row in labelled:
        concept = str(row.get('concept_id') or '')
        if concept:
            practice_by_concept[concept] = practice_by_concept.get(concept, 0) + 1
    rows = list(db.scalars(select(MeasurementProbe).where(
        MeasurementProbe.user_id == user.id, MeasurementProbe.kind == 'cold')))
    issued = sorted((row.issued_at for row in rows), reverse=True)
    last = issued[0] if issued else None
    minutes_since = (now_ts() - last) / 60.0 if last is not None else None
    # An episode is the last completed sitting's span; the probe budget is per sitting.
    segments = episodes.segment(labelled)
    current = segments[-1] if segments else None
    this_episode = 0
    if current is not None:
        this_episode = sum(1 for row in rows if row.issued_at >= current['started_at'])
    # ``episodes.label_attempts`` returns dicts, not ORM rows. Reading an
    # attribute here raised AttributeError on the first account with a graded
    # attempt, which turned ``GET /probe/next`` into a 500 on exactly the
    # learners the measurement surface exists for.
    seen_recently = {
        str(row.get('question_id')) for row in labelled
        if row.get('question_id') and current is not None
        and float(row.get('created_at') or 0) >= current['started_at']
    }
    # A probe must not cut across an assessment: the attempt it produced would be graded
    # differently and the conditions would not hold.
    blocked = _assessment_in_progress(db, user)
    return probe.cold_probe_decision(
        minutes_since_last=minutes_since,
        probes_this_episode=this_episode,
        practice_by_concept=practice_by_concept,
        seen_recently=seen_recently,
        blocked=blocked,
    )


def _assessment_in_progress(db, user) -> bool:
    from .db import Assessment
    row = db.scalar(select(Assessment.id).where(
        Assessment.user_id == user.id, Assessment.complete.is_(False),
        Assessment.expires_at > now_ts()))
    return row is not None


@router.post(API + '/probe')
def issue_probe(principal=Depends(authenticated)):
    """Issue a cold probe, capturing the support conditions at this moment.

    Returns ``issued: false`` with the reason when the budget or the cooldown says no. That is
    a normal outcome, not an error: a learner who asks for a probe when one is not due should be
    told why, not handed a 4xx that reads as a failure.
    """
    db, user = principal
    decision = _cold_decision(db, user)
    if not decision.get('due'):
        return {'issued': False, **decision}
    conditions = {
        'feedback_withheld': True,
        'lesson_open': False,
        'tutor_reachable': False,
        'item_novel': True,
        'recorded_at': now_ts(),
        'source': 'server',
        'detail': ('Captured at issue. The client is required to hold these for the duration; '
                   'the attempt that answers the probe is checked against the concept, and a '
                   'probe answered after a tutor turn is still recorded rather than discarded, '
                   'so the mixing is visible instead of hidden.'),
    }
    row = MeasurementProbe(user_id=user.id, kind='cold', concept_id=decision['concept_id'],
                           status='issued', conditions=conditions,
                           reason=str(decision.get('why') or ''))
    db.add(row)
    db.flush()
    return {'issued': True, 'probe_id': row.id, 'concept_id': row.concept_id,
            'conditions': conditions, 'spec': decision.get('spec'),
            'why': decision.get('why'),
            'next': ('Serve one question for this concept with feedback held back, then call '
                     f'{API}/probe/{row.id}/complete with the attempt id.')}


@router.post(API + '/probe/{probe_id}/complete')
def complete_probe(probe_id: str, payload: CompleteInput,
                   principal=Depends(authenticated)):
    """Close a cold probe against the server-graded attempt that answered it."""
    db, user = principal
    row = db.scalar(select(MeasurementProbe).where(
        MeasurementProbe.id == probe_id, MeasurementProbe.user_id == user.id))
    if row is None:
        raise HTTPException(404, 'No such probe on this account')
    if row.status not in {'issued', 'scheduled'}:
        raise HTTPException(409, f'Probe is already {row.status}')
    attempt = db.scalar(select(Attempt).where(Attempt.id == payload.attempt_id,
                                             Attempt.user_id == user.id))
    if attempt is None:
        raise HTTPException(404, 'No such graded attempt on this account')
    if attempt.concept_id != row.concept_id:
        raise HTTPException(422, 'That attempt is for a different concept than the probe; '
                                 'scoring it here would attribute it to the wrong item.')
    row.status = 'completed'
    row.question_id = attempt.question_id
    row.value = 1.0 if attempt.correct else 0.0
    row.completed_at = now_ts()
    row.response = {'attempt_id': attempt.id, 'correct': bool(attempt.correct),
                    'elapsed_seconds': attempt.elapsed_seconds,
                    'latency_note': ('Client-reported and server-bounded by the receipt '
                                     'interval, as every attempt is.')}
    # A probe is a real retrieval attempt, so it also updates the memory model through the
    # attempt that carried it. Nothing extra is written here: writing mastery twice for one
    # answer is how a harness ends up rewarding the measurement instead of the learning.
    return {'probe_id': row.id, 'status': row.status, 'value': row.value,
            'correct': bool(attempt.correct),
            'note': ('This answer now counts as an unaided observation. Some wrong answers '
                     'here are expected and are not a penalty: they are the measurement '
                     'working.')}


@router.post(API + '/probe/{probe_id}/abandon')
def abandon_probe(probe_id: str, principal=Depends(authenticated)):
    """Close a probe the learner walked away from, so the completion rate stays honest."""
    db, user = principal
    row = db.scalar(select(MeasurementProbe).where(
        MeasurementProbe.id == probe_id, MeasurementProbe.user_id == user.id))
    if row is None:
        raise HTTPException(404, 'No such probe on this account')
    if row.status == 'completed':
        raise HTTPException(409, 'Probe already completed')
    row.status = 'abandoned'
    row.completed_at = now_ts()
    return {'probe_id': row.id, 'status': row.status,
            'note': 'Recorded as abandoned rather than deleted: when probing fails, the timing '
                    'is the thing to fix.'}


@router.post(API + '/effort')
def submit_effort(payload: EffortInput, principal=Depends(authenticated)):
    """Record the one-tap mental-effort rating.

    Kept out of ``/attempts`` on purpose: an effort rating is not evidence about a concept, and
    routing it through the graded-attempt path would put a number in the mastery model that
    says nothing about mastery.
    """
    db, user = principal
    row = MeasurementProbe(user_id=user.id, kind='effort', concept_id=payload.concept_id,
                           status='completed', value=float(payload.value),
                           conditions={'feedback_withheld': False, 'source': 'client',
                                       'instrument': probe.EFFORT_SCALE['instrument']},
                           response={'value': payload.value},
                           reason='Paas single-item mental-effort rating',
                           completed_at=now_ts())
    db.add(row)
    db.flush()
    return {'probe_id': row.id, 'value': payload.value, 'status': 'completed',
            'scale': probe.EFFORT_SCALE}


@router.get(API + '/bench')
def run_benchmark(principal=Depends(authenticated)):
    """Run the estimator recovery benchmark. Teacher role only.

    Benchmarked against *synthetic learners with a known learning rate*, because no public
    corpus - ASSISTments, EdNet, Eedi - carries an answer key for "this learner's true rate".
    They score next-step prediction; they cannot tell you whether this instrument is biased.

    Restricted to teachers because the suite is a few seconds of CPU on every call and it is a
    property of the instrument, not of the account asking.
    """
    db, user = principal
    if getattr(user, 'role', 'learner') != 'teacher':
        raise HTTPException(403, 'The estimator benchmark is an operator surface; it does not '
                                 'read your data and is not part of your report.')
    return bench.run_suite()
