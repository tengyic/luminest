"""HTTP surface for the compiled lesson procedure: ``/api/v1/procedure``.

The sequence itself is decided on the server, in
:mod:`app.harness.teaching.procedure`, from this learner's own evidence and the assets
that actually exist on this instance. This module is deliberately thin: it validates,
scopes to the caller, and serialises. It holds no rule about when to show a deck or run a
simulation, because a rule that lives in a route is a rule the next route will disagree
with.

The serving contract::

    GET  /api/v1/procedure                    -> the lessons this account has running
    GET  /api/v1/procedure/{concept_id}       -> the compiled plan, and any active run
    POST /api/v1/procedure/{concept_id}/start -> start it; materialises the bound deck
    GET  /api/v1/procedure/runs/{run_id}      -> one run: plan, progress, current block
    GET  /api/v1/procedure/runs/{run_id}/next-item -> the next promised question + receipt
    POST /api/v1/procedure/runs/{run_id}/advance -> mark a block done or skipped
    POST /api/v1/procedure/runs/{run_id}/abandon -> stop the run without completing it
    GET  /api/v1/procedure/{concept_id}/deck-cursor -> which slide is showing
    PUT  /api/v1/procedure/{concept_id}/deck-cursor -> record a slide the learner moved to

Three boundaries enforced here
------------------------------
**The plan is not the evidence.** Advancing a block records that the learner did the
activity and nothing else. Mastery still moves only through the question route and the
playground's own outcome route, so a learner cannot raise their own estimate by tapping
"next" through a lesson. That is why ``advance`` writes to ``procedure_runs`` and to no
other table - and why answering a lesson's question goes through ``POST /attempts``, the
one scoring path, rather than through a second grader that would eventually disagree with
it.

**A commitment block is answered, not acknowledged.** A practice or diagnostic block binds
the exact items it promises. ``advance`` refuses to mark one done while any of them has no
recorded attempt, because the block used to complete on a tap and the whole adaptive loop
downstream of it starved for input. Skipping stays honest and available.

**Someone else's run is a 404, never a 403.** A 403 would confirm that the run exists.
The lookup is scoped to the authenticated account before anything else happens.

**Everything here is behind the exam guard.** A lesson plan names a deck, a simulation
and a video for the concept under examination - it is help, whatever it is called. The
guard runs before any write, so a blocked request leaves no partial progress behind.

Clients are expected to treat the returned ``blocks`` as the run of show and drive the
session one block at a time; ``current`` is the block to run now, and is ``None`` when
the lesson is complete.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from . import courses, curriculum, exam_guard, procedure_service
from .db import ProcedureRun, Token, User, now_ts
from .security import digest, rate_limit, resolve_account, require_principal


router = APIRouter(dependencies=[Depends(require_principal("api", 180))])

log = logging.getLogger('luminfest.procedure')

API = '/api/v1/procedure'


def authenticated(request: Request):
    """Resolve ``(db, user)`` from the bearer token, through ``security.resolve_account``.

    The docstring here used to argue that mirroring ``main.authenticated`` line for line
    was what guaranteed "there is only one rule". The mirror is what broke it: neither
    copy consulted the erasure ledger, so a deleted account's token still returned its
    runs. One resolver, called from every module, is what actually guarantees it.
    """
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


def _settings(request: Request):
    return request.app.state.settings


def _owned_concepts(user) -> dict:
    """The concept table for the learner's own course - the only concepts they may plan."""
    return curriculum.course_concepts(courses.enrolled_for(user).id)


def _require_concept(user, concept_id: str) -> None:
    """Refuse a concept that is not in the caller's own course.

    Both namespaces are accepted (lesson id and graph node id) because the native app
    and the web workbench hold different ones; anything else is a 404, which is the same
    answer for "not yours" and "does not exist".
    """
    concepts = _owned_concepts(user)
    if concept_id in concepts:
        return
    if any(str((entry or {}).get('graph_id') or '') == concept_id
           for entry in concepts.values()):
        return
    raise HTTPException(404, 'Unknown concept for this course')


def _run_or_404(db, user, run_id: str) -> ProcedureRun:
    """The caller's own run, or a 404. Scoping happens in the query, not after it."""
    run = db.scalar(select(ProcedureRun).where(ProcedureRun.id == run_id,
                                               ProcedureRun.user_id == user.id))
    if run is None:
        raise HTTPException(404, 'Unknown lesson run')
    return run


def _payload(db, user, run: ProcedureRun) -> dict:
    """One serialiser for every response, so no route can forget the concept title.

    The row stores an id; the card needs a title. Six routes each calling ``run_to_dict``
    directly is six chances to omit it, and the omission is invisible until a learner sees
    "Fraction Equivalence" on a card for a lesson the course calls "Fractions and
    equivalent quantities".

    Answer progress rides on the same call for the same reason: whether a promised
    question has been answered is a property of the block the learner is looking at, and a
    client that had to ask a second endpoint would sometimes render a stale count.
    """
    payload = procedure_service.run_to_dict(
        run, concept_title=procedure_service.concept_title_for(user, run.concept_id))
    return procedure_service.with_item_progress(db, run, payload)


class AdvanceInput(BaseModel):
    """Which block finished, and how.

    ``outcome='skipped'`` is a real outcome, not a failure: a learner who declines the
    simulation has still completed that block of the lesson, and recording the refusal
    honestly is better than pretending they played it.
    """

    order: int = Field(ge=1, le=64)
    outcome: str = Field(default='done', pattern='^(done|skipped)$')
    seconds: int | None = Field(default=None, ge=0, le=4 * 3600)
    note: str = Field(default='', max_length=200)


@router.get(API)
def running(auth=Depends(authenticated)):
    """Every lesson this account currently has open, newest first.

    A learner can hold one active run per concept; this is how a client rebuilds the
    "continue where you left off" surface after a restart without guessing concept ids.
    """
    db, user = auth
    exam_guard.block(db, user)
    rows = list(db.scalars(select(ProcedureRun).where(
        ProcedureRun.user_id == user.id, ProcedureRun.status == 'active')
        .order_by(ProcedureRun.updated_at.desc()).limit(20)))
    return {'runs': [_payload(db, user, row) for row in rows]}


@router.get(API + '/runs/{run_id}')
def read_run(run_id: str, auth=Depends(authenticated)):
    db, user = auth
    exam_guard.block(db, user)
    return _payload(db, user, _run_or_404(db, user, run_id))


@router.get(API + '/runs/{run_id}/next-item')
def next_item(run_id: str, request: Request,
              order: int | None = Query(default=None, ge=1, le=64),
              auth=Depends(authenticated)):
    """The next question this lesson promised, with the receipt that lets it be answered.

    This is the address the answer channel was missing. The block names its items; this
    hands over one of them, signed, along with where the learner stands inside the block.
    The answer then goes to ``POST /attempts`` - the same route the practice card uses -
    so a lesson answer and a practice answer are graded by one implementation, produce one
    kind of ``attempt`` row, and move mastery through one path.

    ``question: null`` is not an error. It means the block owes nothing: every promised
    item is answered (the block can be completed) or the item vanished from the bank (the
    reason says so, and the plan is not silently repaired).
    """
    db, user = auth
    exam_guard.block(db, user)
    run = _run_or_404(db, user, run_id)
    if run.status != 'active':
        raise HTTPException(409, f'This lesson is {run.status}, not active')
    settings = _settings(request)
    try:
        return procedure_service.next_item(
            db, user, run, secret=request.app.state.signing_secret,
            ttl=float(settings.receipt_ttl), settings=settings, order=order)
    except (ValueError, KeyError) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post(API + '/runs/{run_id}/advance')
def advance(run_id: str, payload: AdvanceInput, request: Request,
            auth=Depends(authenticated)):
    """Mark one block finished. The plan does not change; only the progress record does.

    A double tap, a stale screen or an unknown order is refused with a 409 rather than
    accepted silently, because the progress record is what the next turn's prompt is
    built from: a record that says a block ran twice would make the tutor repeat it.

    A practice or diagnostic block also carries a 409 while any question it promised is
    unanswered - ``next-item`` serves those, ``POST /attempts`` scores them. The learner
    is never stuck: skipping is always available, and says so in the refusal.
    """
    db, user = auth
    exam_guard.block(db, user)
    run = _run_or_404(db, user, run_id)
    try:
        procedure_service.advance_run(db, run, payload.order, outcome=payload.outcome,
                                      seconds=payload.seconds, note=payload.note)
    except KeyError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    # Retry a deck build that failed at start. A no-op once the artifact id is stored, so
    # this costs one dict lookup on the common path and rescues the lesson on the rare
    # one - the deck is the next thing the learner sees.
    try:
        procedure_service.materialize(db, user, run, _settings(request))
    except Exception:   # noqa: BLE001 - a rendering failure must not fail the advance
        log.warning('deck materialisation failed for %s', run.concept_id, exc_info=True)
    db.flush()
    return _payload(db, user, run)


@router.post(API + '/runs/{run_id}/abandon')
def abandon(run_id: str, auth=Depends(authenticated)):
    """Stop a lesson without completing it, so a fresh one can be compiled.

    Abandoning is not a failure state to hide: the run keeps its completed blocks, which
    is how ``recent_kinds`` knows a deck already ran today and should not open the next
    lesson as well.
    """
    db, user = auth
    exam_guard.block(db, user)
    run = _run_or_404(db, user, run_id)
    if run.status != 'active':
        raise HTTPException(409, f'This lesson is {run.status}, not active')
    run.status = 'abandoned'
    run.updated_at = now_ts()
    db.flush()
    return _payload(db, user, run)


class DeckCursorInput(BaseModel):
    """Where the learner has moved the deck themselves.

    The client reports its own position so the tutor's "next" is relative to what is
    actually on screen. Without it, a learner who taps ahead three slides and then asks
    "next" would be moved from wherever the server last thought they were.
    """

    slide: int = Field(ge=0, le=64)


@router.get(API + '/{concept_id}/deck-cursor')
def read_deck_cursor(concept_id: str, auth=Depends(authenticated)):
    """Which slide of this concept's deck is showing.

    The deck is rendered natively from the run's blocks, so the server does not know
    where the learner is looking. This is the shared cursor that lets the tutor move the
    sheet the learner has open, and lets the learner's own navigation reach the tutor.
    """
    db, user = auth
    exam_guard.block(db, user)
    _require_concept(user, concept_id)
    return procedure_service.deck_cursor(db, user, concept_id)


@router.put(API + '/{concept_id}/deck-cursor')
def write_deck_cursor(concept_id: str, payload: DeckCursorInput,
                      auth=Depends(authenticated)):
    """Record where the learner moved the deck.

    A PUT, not a POST: the cursor is a position, not an event. Setting it twice to the
    same slide is the same state, which is what makes a client's retry harmless.
    """
    db, user = auth
    exam_guard.block(db, user)
    _require_concept(user, concept_id)
    return procedure_service.set_deck_cursor(db, user, concept_id, payload.slide)


@router.get(API + '/{concept_id}')
def plan(concept_id: str, request: Request,
         minutes: int | None = Query(default=None, ge=1, le=240),
         auth=Depends(authenticated)):
    """Compile what this learner's lesson would be right now, without starting it.

    Read-only: nothing is persisted and no deck is generated. A client uses this to show
    the run of show - "4 blocks, about 20 minutes, starting with a check" - before the
    learner commits, and to render the reasons activities were refused.

    Two plans can come back and the distinction is deliberate. ``plan`` is what a *new*
    lesson would be from the evidence as it stands; ``active`` is the lesson already in
    progress, whose shape was frozen when it began. They can differ - a practice item
    answered since then moves the estimate - and when they do, ``active`` is the lesson
    the learner is in. Silently swapping one for the other would hide the only fact a
    client needs in order to decide between "resume" and "start over".
    """
    db, user = auth
    exam_guard.block(db, user)
    _require_concept(user, concept_id)
    try:
        procedure, evidence = procedure_service.compile_for(
            db, user, concept_id, settings=_settings(request), minutes_budget=minutes)
    except procedure_service.UnknownConcept as exc:
        raise HTTPException(404, 'Unknown concept for this course') from exc
    active = procedure_service.current_run(db, user, concept_id)
    # The evidence the plan was derived from is returned beside it, because "why this
    # lesson" is a question a learner and a support engineer both ask, and neither should
    # have to read the database to answer it. ``recent_accuracy`` is None until the first
    # attempt, which is a different statement from 0.0.
    return {'plan': procedure.to_dict(),
            'evidence': {'mastery': round(evidence.mastery, 4),
                         'recent_accuracy': (round(evidence.recent_accuracy, 4)
                                             if evidence.recent_accuracy is not None else None),
                         'attempts': evidence.attempts,
                         'top_error': evidence.top_error,
                         'frustrated': evidence.frustrated,
                         'session_minutes': round(evidence.session_minutes, 1)},
            'active': _payload(db, user, active) if active else None}


@router.post(API + '/{concept_id}/start')
def start(concept_id: str, request: Request,
          minutes: int | None = Query(default=None, ge=1, le=240),
          auth=Depends(authenticated)):
    """Compile the lesson, persist it, and build the deck its first block promises.

    Starting the same plan twice returns the same run: the learner cannot end up with two
    half-finished lessons, and a client that retries a dropped request gets the row it
    already had rather than a second one.

    The deck is materialised here rather than at compile time because generating one is a
    real write with real bytes. A learner who previews a lesson and walks away causes
    none.
    """
    db, user = auth
    exam_guard.block(db, user)
    _require_concept(user, concept_id)
    try:
        procedure, _ = procedure_service.compile_for(
            db, user, concept_id, settings=_settings(request), minutes_budget=minutes)
    except procedure_service.UnknownConcept as exc:
        raise HTTPException(404, 'Unknown concept for this course') from exc
    run = procedure_service.start_run(db, user, procedure)
    db.flush()
    # Lazy deck build. A failure here is not a failed lesson: the block still names the
    # slides it will contain, and the delivery path retries the build on the next open.
    # Deliberately not rolled back - the run itself is valid, and discarding it would
    # lose the learner's lesson because a rendering step failed.
    try:
        procedure_service.materialize(db, user, run, _settings(request))
    except Exception:   # noqa: BLE001 - an unbuilt deck degrades the block, not the run
        log.warning('deck materialisation failed for %s', run.concept_id, exc_info=True)
    db.flush()
    payload = _payload(db, user, run)
    payload['started'] = True
    return payload

