"""HTTP surface for the session supervisor: ``/api/v1/supervision``.

Thin on purpose, for the same reason :mod:`app.routes_procedure` is: the rule about when to
interrupt a learner lives in :mod:`app.harness.teaching.supervision`, and a rule that lives
in a route is a rule the next route will disagree with. This module validates, scopes to the
caller, fills in the belief the client must not be allowed to state for itself, and
serialises.

Two boundaries enforced here
----------------------------
**The client does not report its own mastery.** A learner who could post ``mastery: 1.0``
could talk the supervisor out of teaching them anything. When ``concept_id`` is given the
belief is read from that account's stored concept state; a client-supplied ``mastery`` is
overwritten rather than merged.

**A reading is not a record.** Nothing here writes. The supervisor's output is a decision
for this moment - state, reasons, one move - and the only thing a caller may keep is that
output. That is what makes ``POST /assess`` safe to call on every interval tick: it is a
pure function of the signals in the request plus one read of the account's own state.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from .db import State, Token, User, now_ts
from .harness.teaching import supervision
from .security import digest, rate_limit

router = APIRouter()

log = logging.getLogger('luminfest.supervision')

API = '/api/v1/supervision'

#: The BKT prior the teaching core uses for a concept with no attempts. Duplicated here as
#: a literal on purpose: importing ``evidence.PRIOR`` would couple a route to the teaching
#: core's internals, and the two must agree - which the test suite asserts.
PRIOR_MASTERY = 0.15


def authenticated(request: Request):
    """Resolve ``(db, user)`` from the bearer token, mirroring ``main.authenticated``."""
    from .main import start_write
    factory = request.app.state.factory
    header = request.headers.get('authorization', '')
    if not header.startswith('Bearer ') or len(header) > 200:
        raise HTTPException(401, 'Valid bearer token required',
                            headers={'WWW-Authenticate': 'Bearer'})
    raw = header[7:]
    rate_limit(factory, 'api:' + digest(raw), 180)
    with factory() as db:
        start_write(db)
        token = db.get(Token, digest(raw))
        if not token or token.expires_at <= now_ts() or token.revoked_at is not None:
            raise HTTPException(401, 'Invalid or expired token')
        user = db.scalar(select(User).where(User.id == token.user_id).with_for_update())
        if not user or getattr(user, 'status', 'active') != 'active':
            raise HTTPException(401, 'Account unavailable')
        token.last_used_at = now_ts()
        user.last_seen_at = now_ts()
        yield db, user
        db.commit()


class AssessInput(BaseModel):
    """The signals a client already has, plus the concept under study.

    Every field is optional: an interval tick that knows only ``idle_seconds`` is still a
    useful reading, and refusing it would push clients into inventing numbers.
    """

    model_config = {'extra': 'forbid'}

    concept_id: str = Field(default='', max_length=120)
    idle_seconds: float = Field(default=0.0, ge=0.0, le=86_400.0)
    window_seconds: float = Field(default=300.0, ge=30.0, le=3_600.0)
    active_seconds: float = Field(default=0.0, ge=0.0, le=86_400.0)
    hidden_seconds: float = Field(default=0.0, ge=0.0, le=86_400.0)
    scroll_events: int = Field(default=0, ge=0, le=100_000)
    click_events: int = Field(default=0, ge=0, le=100_000)
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    elapsed_seconds: float = Field(default=0.0, ge=0.0, le=86_400.0)
    planned_seconds: float = Field(default=1800.0, ge=60.0, le=86_400.0)
    rest_quota_total: int = Field(default=2, ge=0, le=20)
    rest_quota_used: int = Field(default=0, ge=0, le=20)
    resting: bool = False
    item_context: str = Field(default='', max_length=32)
    last_answer_correct: bool = False
    answer_latency_seconds: float = Field(default=0.0, ge=0.0, le=86_400.0)
    personal_average_latency: float = Field(default=0.0, ge=0.0, le=86_400.0)
    recent_accuracy: float = Field(default=-1.0, ge=-1.0, le=1.0)
    variant_result: str = Field(default='', max_length=16)
    explained: bool | None = None
    last_notice_at: float | None = None


def _stored_mastery(db, user, concept_id: str) -> tuple[float, bool]:
    """``(belief, known)`` for the account's concept state. Never the request's.

    ``known`` is separate from the number because ``PRIOR_MASTERY`` is a placeholder for
    "no attempts yet", not a claim that the learner is weak. Collapsing the two would open
    every new learner with a difficulty drop and an unsolicited explanation.
    """
    if not concept_id:
        return PRIOR_MASTERY, False
    row = db.scalar(select(State).where(State.user_id == user.id,
                                        State.concept_id == concept_id))
    data: dict[str, Any] = dict(getattr(row, 'data', None) or {}) if row else {}
    if 'mastery' not in data:
        return PRIOR_MASTERY, False
    try:
        value = float(data['mastery'])
    except (TypeError, ValueError):
        return PRIOR_MASTERY, False
    return min(1.0, max(0.0, value)), True


@router.get(API)
def describe_supervision(principal=Depends(authenticated)):
    """The thresholds and the posture, so a client can render the transparency panel."""
    _db, _user = principal
    return supervision.describe()


@router.post(API + '/assess')
def assess(payload: AssessInput, request: Request,
           principal=Depends(authenticated)):
    """One decision for this moment: the state, why, and the single move worth making."""
    db, user = principal
    signals = payload.model_dump()
    concept_id = signals.pop('concept_id', '')
    last_notice_at = signals.pop('last_notice_at', None)
    # Overwrite, not merge: a client-supplied mastery is ignored even when it is present.
    signals['mastery'], signals['mastery_known'] = _stored_mastery(db, user, concept_id)
    reading = supervision.assess(signals, last_notice_at=last_notice_at)
    reading['concept_id'] = concept_id
    reading['notice'] = _notice(reading)
    # Only a notice that will actually be spoken gets a voice rendered for it. This is the
    # silent half of the teacher, so the clip is what makes it *supervision* rather than a
    # line of text the learner has to be looking at the screen to notice.
    if reading['notice'].get('say'):
        reading['notice']['speech'] = _notice_speech(
            request.app.state.settings, str(reading['notice']['text']))
    return reading


def _notice_speech(settings, text: str) -> dict[str, Any]:
    """Render a notice through the same voice a tutor turn uses.

    Off the request path, like every other spoken line: synthesis costs 20-40 s on the local
    engine, and an interval check that waited for it would be a stall, not a check. The
    descriptor therefore usually says ``pending`` and the client polls the clip exactly as it
    does for an answer. A disabled or unreachable engine returns its own refusal rather than
    a silent no-op, so the client can say why nothing was heard.
    """
    from .harness import speech
    try:
        clip = speech.request_sequence(settings, text)
    except Exception as exc:  # a broken engine must not break the check itself
        return {'state': 'failed', 'reason': f'{type(exc).__name__}: {exc}'}
    return speech.classify(clip, 'notification')


def _notice(reading: dict[str, Any]) -> dict[str, Any]:
    """The interval check's one spoken line, or a refusal to speak.

    This is the *silent* half of the teacher: nobody asked a question, and the harness has
    decided there is something worth saying. It is a notification, not an explanation --
    it must never cut across a sentence the teacher is in the middle of, which is why the
    delivery is ``idle_only`` rather than ``replace``. When the supervisor has decided not
    to interrupt, this returns ``say: False`` with the reason instead of a sentence, so a
    client cannot accidentally speak a thought the harness chose to keep to itself.
    """
    from .harness import speech
    move = reading.get('move') or {}
    kind = str(move.get('kind') or 'continue')
    if reading.get('quiet'):
        return {'say': False, 'kind': 'notification', 'delivery': 'idle_only',
                'reason': 'A notice was given recently; the cooldown is still running.'}
    if kind == 'continue':
        return {'say': False, 'kind': 'notification', 'delivery': 'idle_only',
                'reason': 'Nothing to say: the learner is working.'}
    text = str(move.get('say') or move.get('why') or '').strip()
    if not text:
        return {'say': False, 'kind': 'notification', 'delivery': 'idle_only',
                'reason': 'The move has no sentence attached.'}
    return {'say': True, 'text': text, 'kind': 'notification',
            'delivery': speech.DELIVERY['notification'], 'move': kind}
