"""HTTP surface for the TA's interval check: ``/api/v1/ta/sweep``.

The division of labour the product is built on: the teacher talks, the TA makes sure there
is something to talk *about*. That means the TA is the one who asks, before the teacher
reaches for an asset, three questions the teacher should never have to ask mid-sentence:

1. **Does it exist?** A concept with no figure, or a figure the engine refused to build.
2. **Is it about this concept?** The generator can produce a perfectly formed figure for a
   neighbouring idea and cannot tell that it did — see :mod:`app.harness.teaching.assets`.
3. **Should we interrupt at all?** The learner may be working, drifting, away or resting,
   and only the last two justify speech — see :mod:`app.harness.teaching.supervision`.

Why this is a route and not a TA job
------------------------------------
``/api/v1/ta/dispatch`` runs an *agent turn*, which needs a language model and takes as long
as one. This check needs neither: it builds the figure with the deterministic symbolic
engine, reviews the text it produced, and reads the account's own state. It is fast and has
no outbound call, so it can run on every interval tick without a job pool, a queue, or a
model. The two coexist: this route decides *whether the class is ready*, and dispatch does
the slow work of making it ready when it is not.

Nothing here writes. The figure is rebuilt rather than cached because the engine is
deterministic: rebuilding is the cheapest way to guarantee that what was reviewed is what
the teacher will show.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping, Sequence

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from . import courses, figures
from .db import State
from .harness.teaching import assets, supervision
from .routes_supervision import AssessInput, _stored_mastery, authenticated

router = APIRouter()

log = logging.getLogger('luminfest.ta')

API = '/api/v1/ta'


def _teacher(user) -> None:
    """The TA is the teacher's assistant; a learner has nothing to dispatch it for."""
    if getattr(user, 'role', '') != 'teacher':
        raise HTTPException(403, 'Only a teacher account can run the TA sweep')


def _states_for(db, user, graph) -> dict[str, dict[str, Any]]:
    """The account's own mastery per concept, for the concept map's labels.

    Read-only and scoped to the caller. A missing row is simply absent, which the figure
    builder already renders as "no evidence yet" rather than as zero.
    """
    rows = db.scalars(select(State).where(State.user_id == user.id)).all()
    states: dict[str, dict[str, Any]] = {}
    for row in rows:
        data = dict(getattr(row, 'data', None) or {})
        if 'mastery' in data and getattr(row, 'concept_id', '') in graph.nodes:
            try:
                states[row.concept_id] = {'mastery': float(data['mastery'])}
            except (TypeError, ValueError):
                continue
    return states


class SweepInput(BaseModel):
    """A concept, plus whatever the client knows about the learner right now.

    The supervision signals are optional and reuse :class:`AssessInput` verbatim, so a
    client that already posts to ``/supervision/assess`` sends the same body here. Omitting
    them skips the supervision half and returns the asset review alone.
    """

    model_config = {'extra': 'forbid'}

    concept_id: str = Field(min_length=1, max_length=120)
    signals: AssessInput | None = None


def _sweep_assets(figure: Mapping[str, Any],
                  curated: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The assets to review: always the figure, plus the curated video when there is one.

    The video is included so its own review appears in the report - an unverified card is
    usable and worth telling the TA about - and so ``plan_repair`` can see whether the
    substitute it is about to name actually exists.
    """
    assets = {'simulation': figure}
    if curated:
        assets['video'] = curated[0]
    return assets


def _curated_cards(settings, course_id: str, concept_id: str) -> list[dict[str, Any]]:
    """The curated, non-withheld video cards for this concept.

    A read of the allowlist, never a search: this runs on every sweep, including the ones
    an interval check triggers, and a sweep must not spend a network call to answer "is a
    video already in hand?".
    """
    from .harness import video as video_module
    try:
        cards = video_module.resolve(settings, course_id, concept_id, verify_remote=False)
    except Exception:            # an unreadable allowlist is "no video", not a 500
        return []
    return [card for card in cards if not card.get('withheld_reason')]


@router.post(API + '/sweep')
def sweep(payload: SweepInput, request: Request, principal=Depends(authenticated)):
    """Review this concept's assets and, when signals are supplied, whether to speak now."""
    db, user = principal
    _teacher(user)

    concept_id = payload.concept_id
    graph = courses.graph_for_node(concept_id)
    if graph is None or concept_id not in graph.nodes:
        raise HTTPException(404, f'No course contains the concept {concept_id!r}')
    node = graph.nodes[concept_id]
    concept = node.to_dict()

    settings = request.app.state.settings
    subject_kind = courses.subject_kind_for(concept_id)
    figure = figures.figure_for(concept, graph, _states_for(db, user, graph),
                                subject_kind=subject_kind)
    # What the teacher already has in hand, so a broken interactive can hand off to a real
    # explanation rather than to a concept map. Read from the allowlist; no search here.
    curated = _curated_cards(settings, courses.course_for_node(concept_id), concept_id)

    review = assets.sweep(concept, _sweep_assets(figure, curated))
    plan = assets.plan_repair(review['reviews'],
                              can_search_video=bool(getattr(settings, 'media_enabled', False)),
                              video_available=bool(curated))

    reading = None
    if payload.signals is not None:
        signals = payload.signals.model_dump()
        signals.pop('concept_id', None)
        last_notice_at = signals.pop('last_notice_at', None)
        # Overwrite, never merge: the client does not get to state its own mastery here
        # either, or the check would grade its own homework.
        signals['mastery'], signals['mastery_known'] = _stored_mastery(db, user, concept_id)
        reading = supervision.assess(signals, last_notice_at=last_notice_at)

    report = assets.describe(review['reviews'])
    if reading and reading.get('move', {}).get('kind') not in (None, '', 'continue'):
        spoken = f"{reading['state']}: {reading['move']['why']}"
        report = f'{report} {spoken}'.strip()

    return {
        'concept': {'id': concept_id, 'title': concept.get('title', ''),
                    'course_id': courses.course_for_node(concept_id),
                    'subject_kind': subject_kind},
        'figure': figure,
        'assets': review,
        'plan': plan,
        'supervision': reading,
        'report': report,
        'ready': review['clean'] and (reading is None or reading.get('state') != 'away'),
    }


class PrepareInput(BaseModel):
    """One concept to get ready before a lesson starts."""

    model_config = {'extra': 'forbid'}

    concept_id: str = Field(min_length=1, max_length=120)
    curate_video: bool = True


@router.post(API + '/prepare')
def prepare(payload: PrepareInput, request: Request, principal=Depends(authenticated)):
    """Get one concept's materials ready, doing the work rather than reporting a gap.

    ``/sweep`` answers "is this class ready?"; this answers "make it ready". The difference
    is one write: a concept with no curated video has none in its lesson, because the
    procedure refuses to promise a video it cannot verify. Curating is therefore the step
    that turns "no video" into "video", and it is the TA's job because the teacher is
    already talking.

    Only video is repaired here. A figure that is off-topic is regenerated by the
    deterministic engine on the next build, and a broken one needs a new template -- a
    code change, not a job. Saying so is better than pretending to fix it.
    """
    db, user = principal
    _teacher(user)
    concept_id = payload.concept_id
    graph = courses.graph_for_node(concept_id)
    if graph is None or concept_id not in graph.nodes:
        raise HTTPException(404, f'No course contains the concept {concept_id!r}')
    concept = graph.nodes[concept_id].to_dict()
    course_id = courses.course_for_node(concept_id)
    settings = request.app.state.settings

    figure = figures.figure_for(concept, graph, _states_for(db, user, graph),
                                subject_kind=courses.subject_kind_for(concept_id))
    curated = _curated_cards(settings, course_id, concept_id)
    review = assets.sweep(concept, _sweep_assets(figure, curated))

    from .harness import video_search
    video: dict[str, Any] = {'curated': bool(curated),
                             'title': curated[0].get('title', '') if curated else ''}
    if not curated and payload.curate_video:
        if not getattr(settings, 'media_enabled', False):
            video['reason'] = ('Video search needs network media, which is disabled for '
                               'this instance, so nothing was curated.')
        else:
            found = video_search.curate_for_concept(settings, concept, course_id)
            video = {'curated': bool(found.get('curated')),
                     'title': str((found.get('video') or {}).get('title') or ''),
                     'reason': str(found.get('reason') or ''),
                     'search_path': str(found.get('path') or '')}

    return {
        'concept': {'id': concept_id, 'title': concept.get('title', ''),
                    'course_id': course_id},
        'assets': review,
        'figure': figure,
        'video': video,
        'ready': review['clean'] and bool(video.get('curated')),
        'report': (assets.describe(review['reviews'])
                   + (' Video: ' + (video.get('title') or video.get('reason') or 'none') + '.')
                   ).strip(),
    }


__all__ = ['router']
