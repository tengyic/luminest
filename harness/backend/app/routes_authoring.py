"""HTTP surface for the content foundry.

Mounted by ``main.create_app`` through the same guarded include as every other feature
router, and listed in :mod:`app.feature_routers` so the packager declares it to
PyInstaller. This module owns routing and nothing else: the methodology is
:mod:`app.harness.authoring.methodology`, the document is
:mod:`app.harness.authoring.blueprint`, the build is
:mod:`app.harness.authoring.synthesize`, the gate is
:mod:`app.harness.authoring.audit` and the store is
:mod:`app.harness.authoring.registry`.

The contract::

    GET    /api/v1/author/methodology          -> the profile, its limits and its lineage
    GET    /api/v1/author/courses              -> authored courses, with audit status
    POST   /api/v1/author/preview              -> plan and audit a blueprint; store nothing
    POST   /api/v1/author/courses              -> build, audit, store and publish
    POST   /api/v1/author/draft                -> author from a topic with the model
    GET    /api/v1/author/courses/{id}         -> one course: card, blueprint, audit
    GET    /api/v1/author/courses/{id}/blueprint -> the design document itself
    POST   /api/v1/author/courses/{id}/units   -> append a unit and rebuild
    POST   /api/v1/author/courses/{id}/rebuild -> re-synthesize from the stored blueprint
    POST   /api/v1/author/courses/{id}/illustrate -> attach real photographs to the textbook
    GET    /api/v1/author/courses/{id}/images  -> the photographs it actually serves
    DELETE /api/v1/author/courses/{id}         -> withdraw it from every registry

Two boundaries enforced here, and nowhere else
---------------------------------------------
**Personal previews are authenticated; publishing remains teacher-only.** A preview or
``save=false`` build belongs to the requesting account and is never stored or registered.
Publishing, replacing and administering shared courses still requires a canonical
teacher, staff or admin role from the authenticated account, never from client fields.
Personal authoring does not promote the account or grant access to another author's
blueprint, and active exams block these learning activities before any model call.

**Preview is a real preview.** ``/preview`` runs the same synthesizer and the same audit
as ``/courses`` and persists nothing, so a teacher can see the lessons, the items and
every finding before anything exists. A preview that skipped the audit would be a demo
that lies about what will happen on save.
"""

from __future__ import annotations

from typing import Any, Iterator

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from .db import Token, User, now_ts
from .harness.authoring import (audit as audit_module, blueprint, draft as draft_module,
                                illustrate as illustrate_module, methodology, registry,
                                synthesize)
from .security import digest, rate_limit, resolve_account, require_principal


router = APIRouter(dependencies=[Depends(require_principal("author", 300))])

API = '/api/v1/author'

#: Roles that may author shared course content. Exact strings, no case folding: a role
#: is granted by the database, never inferred from what a client typed.
AUTHOR_ROLES = ('teacher', 'staff', 'admin')


class BlueprintBody(BaseModel):
    """A blueprint document, as sent by an authoring client."""

    blueprint: dict[str, Any] = Field(..., description='The course blueprint document')
    replace: bool = Field(False, description='Publish over an existing authored course')
    save: bool = Field(True, description='Persist and publish; false is a dry run')
    illustrate: bool = Field(
        True, description='Attach a real licence-cleared photograph to each concept. Needs '
                          'network media; when it is unavailable the course is still stored '
                          'and the response says the textbook is text-only.')


class DraftBody(BaseModel):
    topic: str = Field(..., min_length=3, max_length=300)
    units: int = Field(3, ge=1, le=12)
    level: str = Field('intro', max_length=24)
    profile: str = Field('default', max_length=24)
    overrides: dict[str, Any] | None = None
    save: bool = Field(True, description='Persist and publish; false returns the draft')
    illustrate: bool = Field(True, description='Attach a real photograph to each concept')


class UnitBody(BaseModel):
    """One unit appended to an existing course."""

    unit: dict[str, Any] = Field(..., description='A unit object in blueprint shape')


class IllustrateBody(BaseModel):
    """Illustrate a whole textbook, or attach one chosen image to one lesson.

    ``concept_id`` selects the second mode. In it, name the image by ``query`` (acquire and
    attach) or by ``sha256`` (attach something already fetched and chosen) - the second is
    the move after a search, when the caller has looked at the candidates.
    """

    concept_id: str = Field('', max_length=64)
    query: str = Field('', max_length=200)
    sha256: str = Field('', max_length=64)
    block_index: int = Field(1, ge=0, le=64)
    caption: str = Field('', max_length=200)
    limit: int = Field(1, ge=1, le=3, description='Photographs per concept, whole-course mode')
    concept_ids: list[str] | None = Field(
        None, description='Restrict the whole-course pass to these concepts')


# --------------------------------------------------------------------- plumbing

def _session(request: Request) -> Iterator[Any]:
    with request.app.state.factory() as db:
        yield db


def _authenticate(request: Request, db) -> User:
    return resolve_account(request, db, rate_key='author', limit=300)


def _author(request: Request, db) -> User:
    user = _authenticate(request, db)
    role = str(getattr(user, 'role', '') or '')
    if role not in AUTHOR_ROLES:
        raise HTTPException(403, 'Authoring course content requires a teacher account '
                                 f'(this account is {role or "unknown"}); the check is '
                                 'fail-closed')
    return user


def _creator(request: Request, db, *, publish: bool) -> User:
    from . import exam_guard

    user = _author(request, db) if publish else _authenticate(request, db)
    exam_guard.block(db, user)
    return user


def _settings(request: Request):
    settings = request.app.state.settings
    registry.hydrate(settings)
    return settings


def _problems(problems: list[blueprint.Problem]) -> dict[str, Any]:
    return {'blocking': [problem.to_dict() for problem in blueprint.blocking(problems)],
            'advisory': [problem.to_dict() for problem in problems
                         if not blueprint.is_fatal(problem)]}


# ------------------------------------------------------------------------ routes

@router.get(API + '/methodology')
def methodology_route(request: Request, profile: str = 'default',
                      db=Depends(_session)):
    """What the foundry will enforce, before anyone writes a blueprint."""
    _author(request, db)
    try:
        return methodology.describe(profile)
    except KeyError as exc:
        raise HTTPException(404, str(exc))


@router.get(API + '/courses')
def list_courses(request: Request, db=Depends(_session)):
    """Every authored course in this deployment, newest first."""
    _author(request, db)
    _settings(request)
    return {'courses': registry.listing(), 'withheld': registry.withheld()}


@router.post(API + '/preview')
def preview(body: BlueprintBody, request: Request, db=Depends(_session)):
    """Synthesize and audit without storing. The honest dry run."""
    user = _creator(request, db, publish=False)
    plan, problems = blueprint.parse(body.blueprint, author=user.id)
    if plan is None:
        return {'ok': False, 'stored': False, 'problems': _problems(problems)}
    course = synthesize.build(plan)
    report = audit_module.audit(course)
    return {'ok': report.ok, 'stored': False, 'problems': _problems(problems),
            'course': course.summary(), 'audit': report.to_dict(),
            'lesson_sample': _lesson_sample(course),
            'items_sample': _items_sample(course)}


@router.post(API + '/courses')
def create_course(body: BlueprintBody, request: Request, db=Depends(_session)):
    """Build, audit, store and publish one authored course."""
    user = _creator(request, db, publish=body.save)
    settings = _settings(request) if body.save else request.app.state.settings
    plan, problems = blueprint.parse(body.blueprint, author=user.id)
    if plan is None:
        raise HTTPException(422, {'message': 'The blueprint could not be read',
                                  'problems': _problems(problems)})
    course = synthesize.build(plan)
    report = audit_module.audit(course)
    if not body.save:
        return {'ok': report.ok, 'stored': False, 'problems': _problems(problems),
                'course': course.summary(), 'audit': report.to_dict()}
    try:
        record = registry.store(settings, course, report, replace=body.replace)
    except audit_module.CourseRefused as refused:
        raise HTTPException(422, {'message': 'The course failed the audit',
                                  'audit': refused.audit.to_dict(),
                                  'problems': _problems(problems)})
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    illustrated = None
    if body.illustrate:
        # After the store, never before: the audit decides whether the content ships, and a
        # network call must not sit in that path. A failure here leaves a complete,
        # text-only textbook rather than an unpublished one.
        illustrated = illustrate_module.illustrate(settings, course).summary()
    return {'ok': True, 'stored': True, 'problems': _problems(problems),
            'course': record.card(), 'audit': record.audit,
            'illustration': illustrated}


@router.post(API + '/draft')
def draft_course(body: DraftBody, request: Request, db=Depends(_session)):
    """Draft privately, or publish with the server-side author role."""
    _creator(request, db, publish=body.save)
    settings = _settings(request) if body.save else request.app.state.settings
    try:
        drafted = draft_module.draft(settings, body.topic, units=body.units,
                                     level=body.level, profile_name=body.profile,
                                     overrides=body.overrides)
    except draft_module.DraftUnavailable as exc:
        # 503 rather than 422: nothing the caller sent was wrong. The deployment cannot
        # draft, and saying so plainly is more useful than a validation error.
        raise HTTPException(503, {'message': str(exc), 'code': 'no_model'})
    except draft_module.DraftRefused as exc:
        raise HTTPException(422, {'message': str(exc), 'code': 'draft_refused',
                                  'findings': [finding.to_dict()
                                               for finding in exc.findings]})
    if not body.save:
        return {'ok': True, 'stored': False, 'draft': drafted.to_dict()}
    try:
        record = registry.store(settings, drafted.course, drafted.report)
    except (audit_module.CourseRefused, ValueError) as exc:
        raise HTTPException(409, str(exc))
    illustrated = None
    if body.illustrate:
        illustrated = illustrate_module.illustrate(settings, drafted.course).summary()
    return {'ok': True, 'stored': True, 'course': record.card(),
            'attempts': drafted.attempts, 'notes': drafted.notes,
            'illustration': illustrated, 'audit': record.audit}


@router.get(API + '/courses/{course_id}')
def get_course(course_id: str, request: Request, db=Depends(_session)):
    _author(request, db)
    _settings(request)
    record = registry.get(course_id)
    if record is None:
        raise HTTPException(404, 'No authored course with that id')
    return {'course': record.card(), 'audit': record.audit,
            'units': [{'title': unit.get('title'), 'objective': unit.get('objective'),
                       'concepts': [concept.get('title')
                                    for concept in unit.get('concepts') or []]}
                      for unit in record.blueprint.get('units') or []]}


@router.get(API + '/courses/{course_id}/blueprint')
def get_blueprint(course_id: str, request: Request, db=Depends(_session)):
    """The design document itself: what a reviewer reads to judge the course."""
    _author(request, db)
    _settings(request)
    record = registry.get(course_id)
    if record is None:
        raise HTTPException(404, 'No authored course with that id')
    return {'blueprint': record.blueprint, 'digest': record.card()['digest']}


@router.post(API + '/courses/{course_id}/units')
def add_unit(course_id: str, body: UnitBody, request: Request, db=Depends(_session)):
    """Append a unit to an existing course and rebuild it.

    This is the "new content" path that does not require a new course: a teacher extends
    a course the way a syllabus grows. The rebuild is a full synthesize-and-audit, so an
    added unit that breaks the sequence is refused rather than appended.
    """
    _author(request, db)
    settings = _settings(request)
    record = registry.get(course_id)
    if record is None:
        raise HTTPException(404, 'No authored course with that id')
    document = dict(record.blueprint)
    document['units'] = list(document.get('units') or []) + [body.unit]
    plan, problems = blueprint.parse(document, author='operator')
    if plan is None:
        raise HTTPException(422, {'message': 'The extended blueprint could not be read',
                                  'problems': _problems(problems)})
    course = synthesize.build(plan)
    report = audit_module.audit(course)
    if not report.ok:
        raise HTTPException(422, {'message': 'The extended course failed the audit',
                                  'audit': report.to_dict(),
                                  'problems': _problems(problems)})
    record = registry.store(settings, course, report, replace=True)
    return {'ok': True, 'course': record.card(), 'audit': record.audit}


@router.post(API + '/courses/{course_id}/rebuild')
def rebuild(course_id: str, request: Request, db=Depends(_session)):
    """Re-synthesize from the stored blueprint, with the current code.

    Separate from ``/units`` because the reason is different: a rebuild is how a course
    picks up a change to the synthesizer or the profile. It produces a new digest, so the
    version a learner was studying stays identifiable.
    """
    _author(request, db)
    settings = _settings(request)
    record = registry.get(course_id)
    if record is None:
        raise HTTPException(404, 'No authored course with that id')
    plan, problems = blueprint.parse(record.blueprint, author='operator')
    if plan is None:
        raise HTTPException(422, {'message': 'The stored blueprint no longer parses',
                                  'problems': _problems(problems)})
    course = synthesize.build(plan)
    report = audit_module.audit(course)
    if not report.ok:
        raise HTTPException(422, {'message': 'The rebuilt course failed the audit',
                                  'audit': report.to_dict()})
    rebuilt = registry.store(settings, course, report, replace=True)
    return {'ok': True, 'course': rebuilt.card(), 'audit': rebuilt.audit,
            'previous_digest': record.digest}


@router.post(API + '/courses/{course_id}/illustrate')
def illustrate_course(course_id: str, body: IllustrateBody, request: Request,
                      db=Depends(_session)):
    """Put real photographs into an authored textbook.

    Two modes, because there are two real situations. With no ``concept_id`` the whole book
    is illustrated: each concept gets ``limit`` photographs chosen by the media pipeline
    from the concept's own title and lesson text. With ``concept_id`` one chosen image goes
    into one lesson - by ``query``, or by ``sha256`` when the caller has already searched
    and picked.

    An offline instance, a concept whose candidates all failed the licence gate, and a
    lesson already at its photograph cap are all reported as outcomes with reasons and a
    200. None of them is an error: the textbook is still a textbook, and the caller needs
    to know *which* concept has no picture and why, not that a request failed.
    """
    _author(request, db)
    settings = _settings(request)
    record = registry.get(course_id)
    if record is None:
        raise HTTPException(404, 'No authored course with that id')
    plan, problems = blueprint.parse(record.blueprint, author='operator')
    if plan is None:
        raise HTTPException(422, {'message': 'The stored blueprint no longer parses',
                                  'problems': _problems(problems)})
    course = synthesize.build(plan)
    if body.concept_id:
        if body.concept_id not in course.concepts:
            raise HTTPException(404, 'No such concept in this course')
        result = illustrate_module.attach(
            settings, course, body.concept_id, query=body.query, sha256=body.sha256,
            block_index=body.block_index, caption=body.caption)
        result['coverage'] = illustrate_module.coverage(settings, course)
        return result
    illustrated = illustrate_module.illustrate(
        settings, course, limit=body.limit, only=body.concept_ids or None)
    payload = illustrated.to_dict()
    payload['coverage'] = illustrate_module.coverage(settings, course)
    return payload


@router.get(API + '/courses/{course_id}/images')
def course_images(course_id: str, request: Request, db=Depends(_session)):
    """What a learner would actually see: every photograph this textbook serves, with credits."""
    _author(request, db)
    settings = _settings(request)
    record = registry.get(course_id)
    if record is None:
        raise HTTPException(404, 'No authored course with that id')
    plan, problems = blueprint.parse(record.blueprint, author='operator')
    if plan is None:
        raise HTTPException(422, {'message': 'The stored blueprint no longer parses',
                                  'problems': _problems(problems)})
    return illustrate_module.coverage(settings, synthesize.build(plan))


@router.delete(API + '/courses/{course_id}')
def delete_course(course_id: str, request: Request, db=Depends(_session)):
    _author(request, db)
    settings = _settings(request)
    if not registry.delete(settings, course_id):
        raise HTTPException(404, 'No authored course with that id')
    return {'deleted': course_id}


# ------------------------------------------------------------------------ samples

def _lesson_sample(course: synthesize.AuthoredCourse) -> dict[str, Any]:
    """One concept's lesson, so a preview shows the prose rather than a count of it."""
    for concept_id, entry in course.concepts.items():
        return {'concept_id': concept_id, 'title': entry.get('title'),
                'blocks': [{'kind': block.get('kind'), 'title': block.get('title'),
                            'body': block.get('body')}
                           for block in entry.get('blocks') or []]}
    return {}


def _items_sample(course: synthesize.AuthoredCourse) -> list[dict[str, Any]]:
    """One item per category, so a preview shows what the course will ask."""
    seen: dict[str, dict[str, Any]] = {}
    for item in course.questions.values():
        category = str(item.get('category') or '')
        if category in seen:
            continue
        seen[category] = {'id': item.get('id'), 'category': category,
                          'prompt': item.get('prompt'),
                          'options': item.get('options'),
                          'answer_id': item.get('answer_id')}
    return list(seen.values())


__all__ = ['API', 'AUTHOR_ROLES', 'BlueprintBody', 'DraftBody', 'UnitBody', 'router']
