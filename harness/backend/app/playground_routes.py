"""HTTP surface for the simulator playground.

Mounted by ``main.create_app`` through the same guarded include as every other feature
router, and listed in :mod:`app.feature_routers` so the packager declares it to
PyInstaller. This module owns routing and nothing else: the archetypes own the
mechanics, :mod:`app.harness.playground.catalogue` owns which games exist,
:mod:`app.harness.playground.pipeline` owns turning a spec into a stored artifact, and
:mod:`app.harness.playground.evidence` owns what a finished game means.

The serving contract::

    GET  /api/v1/playground                          -> the gallery, with filters
    GET  /api/v1/playground/archetypes               -> the templates and their schemas
    GET  /api/v1/playground/posture                  -> how the pipeline works
    GET  /api/v1/playground/summary                  -> counts, and what was withheld
    GET  /api/v1/playground/runs                     -> this account's runs
    GET  /api/v1/playground/games/{slug}             -> one game: spec and metadata
    GET  /api/v1/playground/games/{slug}/html        -> the playable page, text/html
    POST /api/v1/playground/games/{slug}/instantiate -> store it; returns the /sims URL
    POST /api/v1/playground/games/{slug}/outcome     -> record a committed result
                                                        (a simulation must carry its
                                                         predict/explain cycle)
    POST /api/v1/playground/compose                  -> author a game from a spec
    POST /api/v1/playground/draft                    -> let the model fill a schema

Two boundaries enforced here, and nowhere else
----------------------------------------------
**A run is recorded; mastery moves only when the concept is attributable.** A learner
enrolled in algebra may legitimately play a physics game. That run is worth recording,
but crediting it to an algebra concept would be an invention, so attribution is
resolved explicitly and the response says which way it went.

**Scoring is the game's.** The game holds its own answer key, so it reports whether the
learner was right. This is a real trust boundary and it is stated rather than hidden: a
learner who tampers with their own browser can overstate their own mastery, which harms
only themselves, and the alternative - re-implementing twenty-four archetypes' checks on
the server - would defeat the architecture that makes twenty-four archetypes possible.
The run records the artifact id and content revision it was played from, so a result is
traceable to exact bytes. Nothing here feeds a credential.

Every play surface is behind :func:`app.exam_guard.block`. A game that teaches the
concept being examined is help, whatever it is called.
"""

from __future__ import annotations

from typing import Any, Iterator

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from . import courses, curriculum, exam_guard
from .db import Token, User, now_ts
from .harness import guided_sim
from .harness.playground import archetypes as archetype_registry
from .harness.playground import catalogue, evidence, pipeline
from .resources import resource_dir
from .security import digest, rate_limit

router = APIRouter()

#: Where the playground lives. One constant, so a route cannot be added under a
#: slightly different prefix and become unreachable from the client.
API = '/api/v1/playground'

#: The gallery page itself. Served from ``web/`` alongside the workbench, so the two share
#: one static directory and one asset route. Resolved through :mod:`app.resources` so the
#: frozen bundle finds ``_internal/web`` instead of looking one directory above it.
WEB_DIR = resource_dir('web')


@router.get('/playground', include_in_schema=False)
def playground_page():
    """The gallery page. Unauthenticated, like the workbench shell: it holds no data,
    and every request it makes carries the learner's own token."""
    page = WEB_DIR / 'playground.html'
    if not page.exists():
        raise HTTPException(404, 'Playground page not built; expected harness/web/playground.html')
    return FileResponse(page, media_type='text/html; charset=utf-8')


# --------------------------------------------------------------------- plumbing


def _session(request: Request) -> Iterator[Any]:
    """One database session per request, closed when the request ends."""
    with request.app.state.factory() as db:
        yield db


def _authenticate(request: Request, db) -> User:
    """Resolve the account behind the bearer token, or raise 401.

    The same digest lookup the rest of the API performs: no second auth scheme, and no
    anonymous path. A run belongs to an account, so a request without one is refused.
    """
    factory = getattr(request.app.state, 'factory', None)
    header = request.headers.get('authorization', '')
    if not header.startswith('Bearer ') or len(header) > 200:
        raise HTTPException(401, 'Valid bearer token required',
                            headers={'WWW-Authenticate': 'Bearer'})
    raw = header[7:]
    rate_limit(factory, 'playground:' + digest(raw), 900)
    token = db.get(Token, digest(raw))
    if not token or token.expires_at <= now_ts() or token.revoked_at is not None:
        raise HTTPException(401, 'Invalid or expired token')
    user = db.get(User, token.user_id)
    if not user or getattr(user, 'status', 'active') != 'active':
        raise HTTPException(401, 'Account unavailable')
    return user


def _settings(request: Request):
    return request.app.state.settings


def _game_or_404(slug: str) -> dict[str, Any]:
    game = catalogue.get_game(slug)
    if game is None:
        raise HTTPException(404, f'No playground game named {slug!r}')
    return game


def _owned_concepts(user) -> dict[str, Any]:
    """The concept table for the learner's own course, which attribution resolves against."""
    return curriculum.course_concepts(courses.enrolled_for(user).id)


# ----------------------------------------------------------------------- models


class GuidedCycle(BaseModel):
    """The scaffolding a *simulation* run must carry to count as evidence.

    Optional on :class:`Outcome`, because a scored game already has a checkable answer and
    does not need it. A simulation does not: the research is unambiguous that unguided
    exploration can be worse than no simulation at all (Alfieri et al. 2011, d ~ -0.38), so
    a run that skipped the prediction or the explanation is refused rather than recorded as
    if it were understanding. See :mod:`app.harness.guided_sim`.
    """

    sim_id: str = Field(default='', max_length=64)
    prediction: str = Field(default='', max_length=600)
    actual: str = Field(default='', max_length=600)
    exploration_score: float = Field(default=0.0, ge=0.0, le=1.0)
    explanation: str = Field(default='', max_length=4000)
    steps_completed: list[str] = Field(default_factory=list)


class Outcome(BaseModel):
    """A committed result reported by a game.

    ``detail`` is the game's own telemetry and is deliberately free-form, but it must
    never carry learner-typed free text: it is structured state, not a message. The
    self-explanation gate that covers practice questions has no analogue here, because a
    game answer is not a graded item.

    ``guided`` is the one exception: a simulation's explanation *is* learner-typed text,
    and it is carried in its own field rather than smuggled through ``detail`` so that the
    contract, the refusal message and the stored record all point at the same place.
    """

    correct: bool
    artifact_id: str = Field(default='', max_length=64)
    task_id: str = Field(default='', max_length=64)
    tries: int = Field(default=1, ge=1, le=50)
    elapsed_ms: int | None = Field(default=None, ge=0, le=3_600_000)
    detail: dict[str, Any] = Field(default_factory=dict)
    guided: GuidedCycle | None = None


class ComposeRequest(BaseModel):
    archetype: str = Field(max_length=40)
    spec: dict[str, Any]
    title: str = Field(default='', max_length=200)
    instruction: str = Field(default='', max_length=600)
    slug: str = Field(default='', max_length=80)


class DraftRequest(BaseModel):
    archetype: str = Field(max_length=40)
    topic: str = Field(min_length=3, max_length=400)
    course_id: str = Field(default='', max_length=64)
    concept: str = Field(default='', max_length=200)
    difficulty: str = Field(default='core', max_length=16)


# ---------------------------------------------------------------------- reading


@router.get(API)
def gallery(subject: str = Query(default='', max_length=40),
            course_id: str = Query(default='', max_length=64),
            archetype: str = Query(default='', max_length=40),
            difficulty: str = Query(default='', max_length=16),
            db=Depends(_session), request: Request = None):
    """Every playable game, with the filters and the withholding record.

    Listing is not blocked during an exam: knowing which games exist is not help. Play
    is, and every route that serves or scores a game is guarded.
    """
    _authenticate(request, db)
    return catalogue.catalogue(subject=subject, course_id=course_id,
                               archetype_id=archetype, difficulty=difficulty)


@router.get(API + '/archetypes')
def archetypes(db=Depends(_session), request: Request = None):
    """The template catalogue: what an author can build, and the schema they must fill."""
    _authenticate(request, db)
    return {
        'archetypes': [a.describe() for a in archetype_registry.all_archetypes()],
        'total': len(archetype_registry.all_archetypes()),
        'note': 'An archetype is the interaction; a spec is the content. Authoring a new '
                'game means filling one of these schemas, not writing code.',
    }


@router.get(API + '/posture')
def posture(db=Depends(_session), request: Request = None):
    """How the pipeline works, and what it guarantees. For the transparency panel."""
    _authenticate(request, db)
    return {'pipeline': pipeline.describe(_settings(request)),
            'evidence': evidence.describe(),
            'catalogue': catalogue.summary()}


@router.get(API + '/summary')
def summary(db=Depends(_session), request: Request = None):
    """Catalogue counts and this account's play history."""
    user = _authenticate(request, db)
    return {'catalogue': catalogue.summary(), 'learner': evidence.summary(db, user)}


@router.get(API + '/runs')
def runs(limit: int = Query(default=20, ge=1, le=200), db=Depends(_session),
         request: Request = None):
    """This account's playground runs, newest first."""
    user = _authenticate(request, db)
    return {'runs': evidence.recent(db, user, limit=limit),
            'note': 'A run is not a graded attempt. The answer key belongs to the game.'}


@router.get(API + '/games/{slug}')
def one_game(slug: str, db=Depends(_session), request: Request = None):
    """One game's full spec and metadata, so an author can copy and adapt it."""
    _authenticate(request, db)
    game = _game_or_404(slug)
    archetype = archetype_registry.get(str(game['archetype']))
    return {**game, 'archetype_meta': archetype.describe() if archetype else None,
            'play_url': f'{API}/games/{slug}/html'}


@router.get(API + '/games/{slug}/html')
def game_html(slug: str, db=Depends(_session), request: Request = None):
    """The playable page itself, served as ``text/html``.

    Generated on demand rather than read from the store, so a game is always served from
    its current spec. ``POST .../instantiate`` is the path that stores a versioned
    artifact for the desktop workbench to open.
    """
    user = _authenticate(request, db)
    exam_guard.block(db, user)
    game = _game_or_404(slug)
    try:
        page = pipeline.render_game(archetype_id=str(game['archetype']), spec=game['spec'],
                                    title=game['title'],
                                    instruction=game.get('prompt') or '')
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return Response(content=page, media_type='text/html; charset=utf-8',
                    headers={'Cache-Control': 'no-store',
                             'Content-Security-Policy': "default-src 'none'; "
                                                        "style-src 'unsafe-inline'; "
                                                        "script-src 'unsafe-inline'"})


# ---------------------------------------------------------------------- playing


@router.post(API + '/games/{slug}/instantiate')
def instantiate(slug: str, refresh: bool = Query(default=False),
                db=Depends(_session), request: Request = None):
    """Store a bundled game as a versioned artifact and return its serving URL.

    This is how the native workbench plays a game: it opens the ``raw_url`` in its own
    sandboxed web view, exactly as it opens a hand-authored simulation. Idempotent per
    content revision, so opening the same game twice does not mint a second artifact.
    """
    user = _authenticate(request, db)
    exam_guard.block(db, user)
    _game_or_404(slug)
    try:
        stored = pipeline.instantiate(_settings(request), slug, refresh=refresh)
    except KeyError as exc:
        raise HTTPException(404, f'No playground game named {slug!r}') from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {'slug': slug, 'artifact_id': stored['id'], 'raw_url': stored['raw_url'],
            'reused': stored.get('reused', False),
            'versions': len(stored.get('versions') or []),
            'note': 'Open raw_url in the workbench web view. The same URL serves the same '
                    'content revision; changing the spec produces a new version.'}


@router.post(API + '/games/{slug}/outcome')
def record_outcome(slug: str, payload: Outcome, db=Depends(_session),
                   request: Request = None):
    """Record one committed, scored task.

    Always records the run. Moves the learner's mastery only when the game's concept
    resolves inside the learner's *own* course, because crediting a physics game to an
    algebra concept would be an invention dressed as measurement. The response says
    which happened and why.

    A run that carries a ``guided`` block is a *simulation* run, and is held to the
    predict-manipulate-explain contract before anything is written: the scaffolding is
    validated, the prediction is scored against what actually happened, and the credit
    the run has earned is computed from both. A run that skipped a phase is refused with
    the missing phase named, because recording unguided exploration as evidence is the
    exact failure the research on discovery learning documents.
    """
    user = _authenticate(request, db)
    exam_guard.block(db, user)
    game = _game_or_404(slug)
    archetype_id = str(game['archetype'])
    archetype = archetype_registry.get(archetype_id)
    if archetype is not None and not archetype.scored:
        raise HTTPException(422, f'{slug!r} is a sandbox archetype: it has no checkable '
                                 f'answer, so it cannot report an outcome.')
    concept_id, why = evidence.resolve_concept(game, _owned_concepts(user))

    correct = bool(payload.correct)
    detail = dict(payload.detail or {})
    earned: dict[str, Any] | None = None
    if payload.guided is not None:
        if concept_id is None:
            # A guided outcome is the strongest evidence the playground can produce, and
            # unattributable evidence is still noise. Refusing is the honest option; the
            # reason names the attribution failure rather than blaming the learner.
            raise HTTPException(422, detail={
                'error': 'guided simulation outcome rejected',
                'problems': ['the run cannot be attributed to a concept in your course, so '
                             'it cannot count as evidence'],
                'attribution': why,
            })
        outcome = guided_sim.outcome_payload(
            sim_id=payload.guided.sim_id or slug, concept_id=concept_id,
            prediction=payload.guided.prediction, actual=payload.guided.actual,
            exploration_score=payload.guided.exploration_score,
            explanation=payload.guided.explanation,
            steps_completed=payload.guided.steps_completed)
        problems = guided_sim.validate_outcome(outcome)
        if problems:
            raise HTTPException(422, detail={
                'error': 'guided simulation outcome rejected',
                'problems': problems,
                'contract': guided_sim.describe(),
            })
        earned = guided_sim.credit(outcome)
        # The game's own ``correct`` flag is not used here: for a simulation the claim
        # being measured is "can you predict this system and explain it", and that is
        # what the cycle scored. The reported flag is kept in the record for audit.
        correct = earned['counts_as_correct']
        detail = {**detail, 'guided_sim': outcome, 'guided_credit': earned,
                  'reported_correct': bool(payload.correct)}

    result = evidence.record(
        db, user, slug=slug, artifact_id=payload.artifact_id, archetype=archetype_id,
        concept_id=concept_id or '', correct=correct, tries=payload.tries,
        elapsed_ms=payload.elapsed_ms, task_id=payload.task_id, detail=detail,
        feed_mastery=concept_id is not None)
    response = {**result, 'attributed': concept_id is not None, 'attribution': why,
                'course_id': courses.enrolled_for(user).id,
                'scaffolding': 'guided' if earned else 'none'}
    if earned is not None:
        response['guided_credit'] = earned
        response['scaffolding_note'] = (
            'The mastery update used the guided-cycle credit (prediction + explanation), '
            'not the game\'s self-reported flag. Both are stored so the difference is '
            'auditable.')
    return response


# -------------------------------------------------------------------- authoring


@router.post(API + '/compose')
def compose(payload: ComposeRequest, db=Depends(_session), request: Request = None):
    """Turn an authored spec into a stored, playable game.

    The schema is validated before anything is rendered, so a malformed spec is refused
    with the field names and bounds it violated rather than a blank stage.
    """
    user = _authenticate(request, db)
    exam_guard.block(db, user)
    try:
        stored = pipeline.compose(
            _settings(request), archetype_id=payload.archetype, spec=payload.spec,
            title=payload.title, instruction=payload.instruction, slug=payload.slug,
            source='authored')
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {'artifact_id': stored['id'], 'raw_url': stored['raw_url'],
            'reused': stored.get('reused', False),
            'note': 'The archetype owns the mechanic; the spec only supplied content.'}


@router.post(API + '/draft')
def draft(payload: DraftRequest, db=Depends(_session), request: Request = None):
    """Ask a configured model to fill an archetype's schema, then store the result.

    Returns a structured result rather than raising, because "no model is configured"
    and "the model could not follow the schema" are ordinary outcomes a caller should be
    able to report honestly. Nothing is stored unless a spec validated.
    """
    user = _authenticate(request, db)
    exam_guard.block(db, user)
    rate_limit(request.app.state.factory, 'playground-draft:' + digest(user.id), 20)
    result = pipeline.draft(_settings(request), archetype_id=payload.archetype,
                            topic=payload.topic, course_id=payload.course_id,
                            concept=payload.concept, difficulty=payload.difficulty)
    if not result.get('ok'):
        # 503, not 500: "no model is configured" is a deployment state, not a fault, and
        # the body says which stage failed so the caller can act on it.
        return JSONResponse(status_code=503, content=result)
    return result
