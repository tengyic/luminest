"""HTTP surface for a **live course**: ``/api/v1/live``.

A compiled lesson is a run of show (:mod:`app.harness.teaching.procedure`), and a
surface decision says what the learner is looking at while each block runs
(:mod:`app.harness.teaching.surface`). This router does neither of those things.
It composes the state a live client needs into one document and exposes the two
I/O halves a real-time lesson has always been missing: speech recognition for a
barge-in question, and a recorded surface switch.

The teaching turn itself is **not** reimplemented here. A live turn goes through
``POST /api/v1/agent/stream`` (or ``/agent/chat``) with ``speak=true``,
``interrupted=true`` and ``context.concept_id`` set. That path already owns the
model, the tool loop, the ledger, the grounded fallback and TTS. Duplicating it in a
second route would create two teachers that disagree about the same learner.
What this router adds is the *state* that path reads: the surface boundary on
``ToolContext.surface`` is derived here, on the server, from the running lesson.

Serving contract::

    GET  /api/v1/live/catalog                 -> surfaces, rules, endpoints
    GET  /api/v1/live/{concept_id}/state     -> one document describing the live turn
    POST /api/v1/live/{concept_id}/surface   -> record a decided surface switch
    POST /api/v1/live/{concept_id}/asr       -> microphone audio -> transcript
    POST /api/v1/live/{concept_id}/advance   -> finish a block, re-decide the surface

Everything is behind ``require_principal``; there are no public live routes. ASR
never raises and never fabricates a transcript: see :func:`app.harness.voice.transcribe`.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from . import exam_guard, procedure_service
from .db import ProcedureRun, now_ts
from .harness import provider, voice
from .harness.teaching import surface as surface_router
from .routes_procedure import _require_concept
from .security import resolve_account, require_principal

router = APIRouter(dependencies=[Depends(require_principal('api', 180))])

log = logging.getLogger('luminfest.live')

API = '/api/v1/live'


def authenticated(request: Request):
    """Resolve ``(db, user)`` through the one account resolver, then commit."""
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


def _artifact(run: ProcedureRun | None, kind: str) -> dict[str, Any]:
    """The bound artifact of one kind, from the run the learner is actually in."""
    if run is None:
        return {}
    for row in (run.blocks or []):
        if not isinstance(row, dict) or row.get('kind') != kind:
            continue
        artifact = row.get('artifact') or {}
        return dict(artifact) if isinstance(artifact, dict) else {}
    return {}


def live_state(db, user, concept_id: str, settings) -> dict[str, Any]:
    """One document: the block, the surface, the artifacts, and the voice path.

    A client should be able to render the whole live turn from this and nothing
    else. That is deliberate: four endpoints polled separately disagree about which
    block is current, and a learner sees a deck from the previous activity while
    the teacher narrates the next one.
    """
    _require_concept(user, concept_id)
    run = procedure_service.current_run(db, user, concept_id)
    surface = procedure_service.surface_state(db, user, concept_id)
    deck_artifact = _artifact(run, 'deck')
    video_artifact = _artifact(run, 'video')
    cursor = procedure_service.deck_cursor(db, user, concept_id)
    plan = procedure_service.run_to_dict(run) if run else None
    current = (plan or {}).get('current') or {}
    return {
        'concept_id': concept_id,
        'concept_title': procedure_service.concept_title_for(user, concept_id),
        'run_id': run.id if run else None,
        'status': run.status if run else 'no-run',
        'current_block': current,
        'surface': surface,
        'deck': {**cursor, 'artifact_id': deck_artifact.get('artifact_id', ''),
                 'pptx_url': deck_artifact.get('pptx_url', ''),
                 'slide_count': len(deck_artifact.get('sections') or [])},
        'video': {key: video_artifact.get(key, '')
                  for key in ('title', 'provider', 'channel', 'watch_url',
                              'embed_url', 'licence_class', 'attribution')}
                 | {'verify_on_open': bool(video_artifact.get('verify_on_open'))},
        'whiteboard': {'board_id': f'board-{concept_id}',
                       'available': bool(surface['available'].get('whiteboard'))},
        'voice': {'enabled': bool(getattr(settings, 'voice_enabled', False)),
                  'model_configured': bool(provider.available(settings)),
                  'tts': '/api/v1/voice/speak',
                  'speech_state': '/api/v1/media/audio/{digest}/state',
                  'asr': f'{API}/{concept_id}/asr'},
        'turn': {'teach': '/api/v1/agent/stream', 'chat': '/api/v1/agent/chat',
                 'advance': f'{API}/{concept_id}/advance',
                 'surface': f'{API}/{concept_id}/surface',
                 'deck_cursor': f'/api/v1/procedure/{concept_id}/deck-cursor',
                 'body': {'message': '<learner question or empty for narration>',
                          'speak': True, 'interrupted': False,
                          'context': {'concept_id': concept_id,
                                      'board_id': f'board-{concept_id}'}}},
    }


class SurfaceInput(BaseModel):
    """A decided switch. ``reason`` is mandatory when deviating from the plan."""

    surface: str = Field(min_length=1, max_length=24)
    reason: str = Field(default='', max_length=300)
    interrupted: bool = False
    intent: str = Field(default='', max_length=24)


class AdvanceInput(BaseModel):
    order: int = Field(ge=1, le=64)
    outcome: str = Field(default='done', pattern='^(done|skipped)$')
    note: str = Field(default='', max_length=200)


@router.get(API + '/catalog')
def catalog(auth=Depends(authenticated)):
    """The decision contract, for a client and for the transparency panel.

    No account data is returned, but the route still requires a signed-in
    principal: a live course is always somebody's lesson. The frozen-bundle smoke
    test probes this path with a learner token.
    """
    return {'version': '1', **surface_router.describe(),
            'endpoints': ['/catalog', '/{concept_id}/state', '/{concept_id}/surface',
                          '/{concept_id}/asr', '/{concept_id}/advance'],
            'teaching_turn': '/api/v1/agent/stream (speak=true, interrupted, '
                             'context.concept_id)',
            'note': 'Surfaces are compiled into the lesson procedure and persisted '
                    'with the run. A switch is a recorded decision, not a view flag.'}


@router.get(API + '/{concept_id}/state')
def state(concept_id: str, request: Request, auth=Depends(authenticated)):
    """Everything needed to render and drive the current live turn."""
    db, user = auth
    exam_guard.block(db, user)
    return live_state(db, user, concept_id, _settings(request))


@router.post(API + '/{concept_id}/surface')
def switch_surface(concept_id: str, payload: SurfaceInput,
                   auth=Depends(authenticated)):
    """Record a teacher decision about what the learner looks at.

    A refusal is a 200 with ``ok=False`` and a named reason, not a 4xx: a missing
    video or an unstated reason is a product state the client must show, not a
    broken connection.
    """
    db, user = auth
    exam_guard.block(db, user)
    _require_concept(user, concept_id)
    return procedure_service.set_surface(
        db, user, concept_id, payload.surface, reason=payload.reason,
        interrupted=payload.interrupted, intent=payload.intent)


@router.post(API + '/{concept_id}/asr')
async def asr(concept_id: str, request: Request, auth=Depends(authenticated)):
    """One recorded utterance -> text, for a real interruption.

    The client posts the raw ``MediaRecorder`` blob with its own ``Content-Type``.
    The returned ``turn`` hint tells it exactly how to send the transcript to the
    agent stream with ``interrupted=true``; the surface state is included so the
    client can hold the deck rather than advance it.
    """
    db, user = auth
    exam_guard.block(db, user)
    _require_concept(user, concept_id)
    audio = await request.body()
    result = voice.transcribe(
        _settings(request), audio,
        content_type=request.headers.get('content-type', 'audio/webm'))
    surface = procedure_service.surface_state(db, user, concept_id)
    return {**result,
            'surface': {'compiled': surface['compiled_surface'],
                        'live': surface['surface'],
                        'hold': True},
            'turn': {'path': '/api/v1/agent/stream',
                     'body': {'message': result['text'], 'speak': True,
                              'interrupted': True,
                              'context': {'concept_id': concept_id,
                                          'board_id': f'board-{concept_id}'}}}}


@router.post(API + '/{concept_id}/advance')
def advance(concept_id: str, payload: AdvanceInput, request: Request,
            auth=Depends(authenticated)):
    """Finish the current block and return the next block's compiled surface.

    ``advance_run`` clears any recorded switch, so the next block starts on the
    surface the plan compiled for it. The client must re-read ``state`` (or this
    response) rather than keep the old surface on screen.
    """
    db, user = auth
    exam_guard.block(db, user)
    _require_concept(user, concept_id)
    run = procedure_service.current_run(db, user, concept_id)
    if run is None:
        raise HTTPException(404, 'No lesson is running for this concept')
    try:
        procedure_service.advance_run(db, run, payload.order,
                                      outcome=payload.outcome, note=payload.note)
    except (ValueError, KeyError) as exc:
        raise HTTPException(409, str(exc)) from exc
    db.flush()
    return {'advanced': {'order': payload.order, 'outcome': payload.outcome},
            **live_state(db, user, concept_id, _settings(request))}
