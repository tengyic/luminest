"""HTTP surface for building a course out of the learner's own material.

Mounted by convention: ``main.create_app`` imports this module and includes
``router``, so nothing in the shared API file has to know this feature exists.

    POST   /api/v1/create/preview        plan a course, persist nothing
    POST   /api/v1/create/course         build and store it on the account
    POST   /api/v1/create/upload         same, from an uploaded file
    GET    /api/v1/my-courses            the courses this account built
    GET    /api/v1/my-courses/{id}       one of them, with its graph and lessons
    DELETE /api/v1/my-courses/{id}       remove it
    POST   /api/v1/my-courses/{id}/enrol make it the learner's active course

Two deliberate implementation notes.

* **Auth is resolved here, from the app state**, exactly as
  ``app.web_routes.principal`` does. ``main``'s ``authenticated`` dependency is a
  closure inside ``create_app`` and cannot be imported; re-deriving the check from
  ``Token``/``User`` keeps one auth scheme rather than inventing a second. There is
  no anonymous fallback: a course belongs to an account, so a request without a
  valid bearer token is a 401.

* **The upload comes in three shapes.** The middleware in ``app.main`` elevates
  this route's body cap to 32 MiB and admits document content types (see
  ``DOCUMENT_BODY_CAPS`` and ``DOCUMENT_CONTENT_TYPES``), so a file can arrive as
  a ``multipart/form-data`` part named ``file``, or as the raw bytes with the
  filename in ``?filename=``. The base64-in-JSON envelope stays for a client that
  can build neither - a deck import still sends a ``.pptx`` that way. The
  middleware buffers the body before the route runs, so all three paths read the
  same bytes and none re-consumes the stream.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError
# The Starlette class, not ``fastapi.UploadFile``: ``request.form()`` is parsed by
# Starlette's form parsers and yields *starlette.datastructures.UploadFile``.
# FastAPI's own UploadFile subclasses that parent, so an isinstance against
# FastAPI's class rejects every real file part.
from starlette.datastructures import UploadFile

from . import course_builder, courses
from .course_builder import BuildRefused, IntakeRefused
from .db import Token, User, now_ts
from .security import digest, rate_limit

router = APIRouter()

#: Ceiling on a pasted body. Above this the learner is uploading a book, not
#: pasting notes, and the upload path is the right one. The boundary middleware's
#: 128 KiB request cap binds first in practice; this is the model-level backstop.
MAX_PASTE_CHARS = 2_000_000

#: Ceiling on one uploaded file. The middleware caps this route's *request body*
#: at 32 MiB (``DOCUMENT_BODY_CAPS``), and multipart framing plus base64 inflation
#: both eat into that, so the file itself is capped below the body cap to keep
#: headroom on every path. Stated as data so the refusal can name the number.
MAX_UPLOAD_BYTES = 24 * 1024 * 1024
MAX_UPLOAD_BASE64 = 4 * ((MAX_UPLOAD_BYTES + 2) // 3)


class SourceInput(BaseModel):
    """A source is pasted text or an https URL. Exactly one is expected."""

    text: str = Field(default='', max_length=MAX_PASTE_CHARS)
    url: str = Field(default='', max_length=2000)


class UploadInput(BaseModel):
    """A file to turn into a course, base64-encoded inside JSON.

    ``filename`` is only a label and a hint: the builder detects the real format
    from the bytes, so a mislabelled file is handled as what it actually is.
    """

    filename: str = Field(default='', max_length=300)
    data_base64: str = Field(default='', max_length=MAX_UPLOAD_BASE64)
    title: str = Field(default='', max_length=200)
    subject: str = Field(default='', max_length=80)
    level: str = Field(default='', max_length=40)


class CreateInput(SourceInput):
    title: str = Field(default='', max_length=200)
    subject: str = Field(default='', max_length=80)
    level: str = Field(default='', max_length=40)


@dataclass
class _Upload:
    """One uploaded file, from whichever of the three envelopes it arrived in."""

    data: bytes
    filename: str
    title: str = ''
    subject: str = ''
    level: str = ''


def account(request: Request):
    """The authenticated learner, and the session this request writes through.

    Mirrors the rest of the API's bearer-token check (Token digest lookup) rather
    than introducing a second scheme, and registers the session factory with the
    course builder so a persisted course can be re-hydrated on a later request.
    """
    factory = getattr(request.app.state, 'factory', None)
    header = request.headers.get('authorization', '')
    if factory is None or not header.startswith('Bearer ') or len(header) > 200:
        raise HTTPException(401, 'Valid bearer token required',
                            headers={'WWW-Authenticate': 'Bearer'})
    raw = header[7:]
    rate_limit(factory, 'create:' + digest(raw), 240)
    with factory() as db:
        token = db.get(Token, digest(raw))
        if not token or token.expires_at <= now_ts() or token.revoked_at is not None:
            raise HTTPException(401, 'Invalid or expired token')
        user = db.get(User, token.user_id)
        if not user or getattr(user, 'status', 'active') != 'active':
            raise HTTPException(401, 'Account unavailable')
        course_builder.attach_store(factory)
        request.state.course_factory = factory
        yield db, user
        db.commit()


def _refusal_response(refusal: course_builder.Refusal) -> HTTPException:
    """A refusal is a 422 with the reason and the bar that was not met."""
    return HTTPException(422, detail=refusal.to_dict())


def _plan_or_refuse(source: dict, *, title: str = '', subject: str = '', level: str = ''):
    try:
        intake = course_builder.intake_from(source)
    except IntakeRefused as exc:
        raise _refusal_response(exc.refusal) from exc
    try:
        return course_builder.plan_course(intake, title=title, subject=subject, level=level)
    except BuildRefused as exc:
        raise _refusal_response(exc.refusal) from exc


def _decode_upload(payload: UploadInput) -> bytes:
    """Decode the base64 field, or refuse with a reason that names the problem."""
    if not payload.data_base64:
        raise HTTPException(422, detail={
            'refused': True, 'code': 'missing_file',
            'reason': 'No file was sent. Put the file\'s bytes in a base64 "data_base64" field, '
                      'with its "filename".'})
    try:
        data = base64.b64decode(payload.data_base64, validate=True)
    except ValueError as exc:  # binascii.Error is a ValueError subclass
        raise HTTPException(422, detail={
            'refused': True, 'code': 'invalid_base64',
            'reason': 'data_base64 is not valid base64.'}) from exc
    if not data:
        raise HTTPException(422, detail={'refused': True, 'code': 'empty_file',
                                         'reason': 'The uploaded file was empty.'})
    # The size ceiling is checked once, on the decoded bytes, in the route: the
    # base64 envelope is one of three ways in, not a case with a cap of its own.
    return data


# ------------------------------------------------------------------ planning
@router.post('/api/v1/create/preview')
def create_preview(payload: SourceInput, auth=Depends(account)):
    """Extract, order and quiz the source, and persist nothing.

    A learner should be able to judge the course before it exists. Nothing here
    touches the database, so a preview cannot leave a half-built course behind.
    """
    plan = _plan_or_refuse(payload.model_dump())
    return plan.to_preview()


@router.post('/api/v1/create/course', status_code=201)
def create_course(payload: CreateInput, auth=Depends(account)):
    """Build the course and store it on this account."""
    db, user = auth
    plan = _plan_or_refuse(payload.model_dump(), title=payload.title,
                           subject=payload.subject, level=payload.level)
    row = course_builder.save_course(db, user, plan)
    return {
        'course': row.to_dict(),
        'graph_stats': plan.stats(),
        'concepts': len(plan.concepts),
        'questions': len(plan.questions),
        'enrolled': False,
        'next': 'Enrol in it to make it your active course, then it appears on Today and the map.',
        'rights_note': course_builder.RIGHTS_NOTE,
    }


async def _read_multipart(request: Request) -> _Upload:
    """A ``multipart/form-data`` body: one file part named ``file``.

    ``max_part_size`` matters: Starlette defaults a multipart part to 1 MiB, which
    would turn every real document - a textbook chapter, a scanned PDF - into a
    400 before the route sees a byte of it. The limit is the upload ceiling, and
    the request body was already capped at 32 MiB by the middleware.
    """
    form = await request.form(max_files=1, max_fields=8, max_part_size=MAX_UPLOAD_BYTES)
    part = form.get('file')
    # A *text* field named ``file`` is still no file: the bytes never arrived, and
    # handing the builder a label instead of a document would refuse on a
    # confusing error rather than on the missing part itself.
    if not isinstance(part, UploadFile):
        raise HTTPException(422, detail={
            'refused': True, 'code': 'missing_file',
            'reason': 'No file was sent. Send a multipart/form-data body with a file part '
                      'named "file".'})
    return _Upload(data=await part.read(), filename=part.filename or '',
                   title=str(form.get('title') or ''),
                   subject=str(form.get('subject') or ''),
                   level=str(form.get('level') or ''))


def _read_json(body: bytes) -> _Upload:
    """The base64-in-JSON envelope, for a client that cannot build a multipart body."""
    try:
        payload = UploadInput.model_validate_json(body)
    except ValidationError as exc:
        raise HTTPException(422, detail={
            'refused': True, 'code': 'invalid_upload',
            'reason': 'That is not a valid upload envelope. Send JSON with a "filename" and '
                      'the file\'s bytes base64-encoded in "data_base64".'}) from exc
    return _Upload(data=_decode_upload(payload), filename=payload.filename,
                   title=payload.title, subject=payload.subject, level=payload.level)


async def _read_upload(request: Request) -> _Upload:
    """Read the upload from whichever envelope the client used.

    Three ways in, in order of preference, because three kinds of client exist: a
    browser or the native app that can build a ``multipart/form-data`` body; a
    script that streams the file's bytes with a declared content type and names it
    with ``?filename=``; and a client that can only do JSON. The middleware has
    already buffered the body (``DOCUMENT_BODY_CAPS`` in ``app.main``), so all
    three read the same bytes and no path re-consumes the stream.
    """
    declared = (request.headers.get('content-type') or '').split(';')[0].strip().lower()
    if declared == 'multipart/form-data':
        return await _read_multipart(request)
    if declared == 'application/json':
        return _read_json(await request.body())
    # Anything else is the document itself - ``application/pdf``, ``text/plain``,
    # ``application/octet-stream``: the middleware admits exactly the types a
    # document can honestly declare, and a raw body carries no part headers, so the
    # filename rides in the query string.
    return _Upload(data=await request.body(),
                   filename=request.query_params.get('filename', ''))


@router.post('/api/v1/create/upload')
async def create_upload(request: Request, auth=Depends(account)):
    """Read an uploaded file, then behave exactly like the preview endpoint.

    ``?save=1`` stores the course on the account (and ``?enrol=1``, the
    default, makes it the active one), because a learner who has just handed
    over a textbook chapter wants the course, not a plan of it - and the file's
    bytes are not something a client can echo back as text to reach the
    text-only save path. A refusal at any stage leaves nothing behind.
    """
    db, user = auth
    save = (request.query_params.get('save') or '').lower() in ('1', 'true', 'yes')
    enrol = (request.query_params.get('enrol') or 'true').lower() not in ('0', 'false', 'no')
    upload = await _read_upload(request)
    # One ceiling for all three ways in, on the decoded bytes. A file past it is a
    # book rather than notes: the learner is told the number and pointed at the
    # paste and link paths, which have their own (larger) ceilings.
    if len(upload.data) > MAX_UPLOAD_BYTES:
        raise _refusal_response(course_builder.Refusal(
            code='source_too_large',
            reason=f'That file is larger than the {MAX_UPLOAD_BYTES} byte limit for an upload. '
                   f'Paste the text, or link to an https page, instead.',
            minimum={'bytes': MAX_UPLOAD_BYTES}))
    try:
        intake = course_builder.intake_bytes(upload.filename, upload.data)
    except IntakeRefused as exc:
        raise _refusal_response(exc.refusal) from exc
    try:
        plan = course_builder.plan_course(intake, title=upload.title,
                                          subject=upload.subject, level=upload.level)
    except BuildRefused as exc:
        raise _refusal_response(exc.refusal) from exc
    if not save:
        return plan.to_preview()

    row = course_builder.save_course(db, user, plan)
    enrolled = False
    if enrol:
        user.course_id = row.id
        user.onboarding_completed_at = now_ts()
        enrolled = True
    db.commit()
    return {
        **plan.to_preview(),
        'course_id': row.id,
        'course': row.to_dict(),
        'created': True,
        'enrolled': enrolled,
        'active_course': getattr(user, 'course_id', '') or '',
        'rights_note': course_builder.RIGHTS_NOTE,
        'next': ('This course is your active course now: Today, the map, the lessons and '
                 'the practice items all come from it.'
                 if enrolled else
                 'Enrol in it at /api/v1/my-courses/{id}/enrol to make it your active course.'),
    }


# --------------------------------------------------------------- my courses
@router.get('/api/v1/my-courses')
def my_courses(auth=Depends(account)):
    """Every course this account built. Scoped to the account, always."""
    db, user = auth
    rows = course_builder.courses_for(db, user)
    enrolled = getattr(user, 'course_id', '') or ''
    return {
        'courses': [row.to_dict() for row in rows],
        'enrolled': enrolled,
        'count': len(rows),
        'note': ('These are your own courses. They are stored on your account, are never added to '
                 'the shared catalogue, and another learner cannot see or delete them.'),
    }


@router.get('/api/v1/my-courses/{course_id}')
def my_course(course_id: str, auth=Depends(account)):
    """One of this account's courses, with its graph, concepts and lesson count."""
    db, user = auth
    row = course_builder.find_course(db, user, course_id)
    if row is None:
        raise HTTPException(404, 'No such course on this account')
    graph = row.graph()
    payload = row.to_dict(with_graph=True)
    payload['lesson_count'] = len(row.concepts)
    payload['concepts_list'] = [
        {'id': entry['id'], 'title': entry['title'], 'unit': entry.get('unit', ''),
         'tier': entry.get('tier', ''), 'difficulty': entry.get('difficulty', 3),
         'summary': entry.get('summary', ''), 'prerequisites': entry.get('prerequisites', []),
         'source_span': entry.get('source_span', '')}
        for entry in row.concepts.values()]
    payload['graph_stats'] = graph.stats()
    payload['enrolled'] = (getattr(user, 'course_id', '') or '') == row.id
    return payload


@router.delete('/api/v1/my-courses/{course_id}')
def delete_my_course(course_id: str, auth=Depends(account)):
    """Delete one of this account's courses, and everything derived from it."""
    db, user = auth
    if not course_builder.delete_course(db, user, course_id):
        raise HTTPException(404, 'No such course on this account')
    reset = False
    if (getattr(user, 'course_id', '') or '') == course_id:
        # The active course cannot be one that no longer exists, so the account
        # falls back to the shipped default rather than to a dangling id.
        user.course_id = courses.DEFAULT_COURSE_ID
        db.commit()
        reset = True
    return {'deleted': True, 'course_id': course_id, 'active_course_reset': reset}


@router.post('/api/v1/my-courses/{course_id}/enrol')
def enrol_my_course(course_id: str, auth=Depends(account)):
    """Make one of this account's own courses the active course."""
    db, user = auth
    row = course_builder.find_course(db, user, course_id)
    if row is None:
        raise HTTPException(404, 'No such course on this account')
    user.course_id = row.id
    user.onboarding_completed_at = now_ts()
    db.commit()
    return {
        'enrolled': True,
        'course_id': row.id,
        'course': row.to_dict(),
        'next': 'The map, the lessons and the practice items now come from this course.',
    }
