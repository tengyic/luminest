"""HTTP surface for the slide editor: an editable deck document and a real .pptx bridge.

Mounted by ``main.py`` with one guarded include (``app.include_router(routes_deck.router)``),
which is why this module owns nothing but the routes and reaches for the document model in
:mod:`app.deck` for every rule. There is deliberately no deck logic here: a validation rule
that lived in two places would drift, and the deck is exactly the place where a drifted rule
silently corrupts a teacher's work.

The serving contract:

    GET    /api/v1/deck                          -> this account's decks (summaries)
    POST   /api/v1/deck                          -> a new, empty deck
    GET    /api/v1/deck/from-concept/{concept_id}-> an editable deck built from the curriculum
    GET    /api/v1/deck/{deck_id}                -> the document
    PUT    /api/v1/deck/{deck_id}                -> replace the document
    POST   /api/v1/deck/{deck_id}/slides         -> add a slide
    PATCH  /api/v1/deck/{deck_id}/slides/{slide_id}
    DELETE /api/v1/deck/{deck_id}/slides/{slide_id}
    POST   /api/v1/deck/{deck_id}/slides/{slide_id}/move
    POST   /api/v1/deck/{deck_id}/slides/{slide_id}/duplicate
    POST   /api/v1/deck/{deck_id}/elements       -> add an element
    PATCH  /api/v1/deck/{deck_id}/elements/{element_id}
    DELETE /api/v1/deck/{deck_id}/elements/{element_id}
    GET    /api/v1/deck/{deck_id}/export.pptx    -> the real .pptx (the route that was missing)
    POST   /api/v1/deck/import                   -> a .pptx in, a document out
    GET    /api/v1/deck/{deck_id}/slide/{slide_id}.svg
    GET    /api/v1/deck/{deck_id}/images         -> referenced images with attribution

Two boundaries are enforced here and nowhere else:

* **Ownership.** The caller is re-derived from the bearer token on every request and a deck
  that is not theirs is a 404, never a 403 — a 403 would confirm the deck exists.
* **Fail-closed validation.** A malformed document or element is refused with a 422 that
  names every problem; nothing is written. python-pptx being absent is a structured 503
  (``{"ok": false, "reason": ...}``), not a crash.
"""

from __future__ import annotations

import base64
import hashlib
import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from . import courses, deck
from .db import Token, User, now_ts
from .harness import media, presentation
from .security import digest, rate_limit

router = APIRouter()

PPTX_MEDIA_TYPE = ('application/vnd.openxmlformats-officedocument.presentationml.'
                   'presentation')


# --------------------------------------------------------------------- auth


def _authenticate(request: Request, db) -> User:
    """Resolve the account behind the bearer token, or raise 401.

    Deliberately the same digest lookup the rest of the API performs — no second auth scheme,
    and no anonymous path: a deck belongs to an account, so a request without one is refused
    even in development.
    """
    factory = getattr(request.app.state, 'factory', None)
    header = request.headers.get('authorization', '')
    if not header.startswith('Bearer ') or len(header) > 200:
        raise HTTPException(401, 'Valid bearer token required', headers={'WWW-Authenticate': 'Bearer'})
    raw = header[7:]
    rate_limit(factory, 'deck:' + digest(raw), 600)
    token = db.get(Token, digest(raw))
    if not token or token.expires_at <= now_ts() or token.revoked_at is not None:
        raise HTTPException(401, 'Invalid or expired token')
    user = db.get(User, token.user_id)
    if not user or getattr(user, 'status', 'active') != 'active':
        raise HTTPException(401, 'Account unavailable')
    return user


def _user_id(request: Request) -> str:
    with request.app.state.factory() as db:
        return _authenticate(request, db).id


def _settings(request: Request):
    return request.app.state.settings


def _owned(request: Request, deck_id: str) -> dict:
    """The caller's document, or 404. Someone else's deck is indistinguishable from a
    missing one."""
    doc = deck.load_deck(_settings(request), deck_id, owner_id=_user_id(request))
    if doc is None:
        raise HTTPException(404, 'Deck not found')
    return doc


def _commit(request: Request, doc: dict) -> dict:
    """Persist a document the caller already validated, bumping the version."""
    doc['version'] = int(doc.get('version') or 0) + 1
    deck.save_deck(_settings(request), doc)
    return doc


def _refuse(exc: deck.DeckError) -> HTTPException:
    return HTTPException(422, {'message': str(exc), 'problems': exc.reasons})


def _body(payload) -> dict:
    if not isinstance(payload, dict):
        raise HTTPException(422, 'The request body must be a JSON object.')
    return payload


# --------------------------------------------------------------------- collection


@router.get('/api/v1/deck')
def list_decks(request: Request):
    """This account's decks, newest first. The editor's open-deck picker reads this."""
    user_id = _user_id(request)
    return {'decks': deck.list_decks(_settings(request), user_id),
            'pptx_available': deck.pptx_available()}


@router.post('/api/v1/deck', status_code=201)
def create_deck(request: Request, payload: dict):
    """A new, empty deck. ``{title, theme?}``."""
    payload = _body(payload)
    user_id = _user_id(request)
    doc = deck.new_deck(str(payload.get('title') or 'Untitled deck'),
                        theme=payload.get('theme'), owner_id=user_id)
    doc['slides'].append(deck.new_slide('title'))
    deck.save_deck(_settings(request), doc)
    return doc


# --------------------------------------------------------------------- from curriculum


@router.get('/api/v1/deck/from-concept/{concept_id}')
def deck_from_concept(concept_id: str, request: Request, title: str = ''):
    """Build an editable deck from the existing curriculum/presentation data.

    The narrated deck is composed exactly as ``/api/v1/harness/generate`` composes it, then
    projected into the editable document model. Nothing about the source changes: this is the
    same grounded content, now something a teacher can move, restyle and export.
    """
    settings = _settings(request)
    with request.app.state.factory() as db:
        user = _authenticate(request, db)
        spec = _course_for(user)
        ctx = _context(settings, user, db, spec)
        try:
            payload = presentation.compose(ctx, concept_id, {'include_visuals': True})
        except ValueError as exc:
            raise HTTPException(404, str(exc))
    doc = deck.from_presentation(payload, owner_id=user.id)
    if title.strip():
        doc['title'] = title.strip()[:deck.MAX_TITLE]
    if not doc['slides']:
        raise HTTPException(422, 'That concept produced no slides.')
    deck.save_deck(settings, doc)
    return doc


def _course_for(user):
    try:
        return courses.course(getattr(user, 'course_id', None))
    except courses.UnknownCourse:
        return courses.course(courses.DEFAULT_COURSE_ID)


def _context(settings, user, db, spec):
    """A harness context scoped to the learner's own course, without importing main.py —
    which would be a circular import, since main.py mounts this module."""
    from .harness import context_for
    return context_for(settings, user, db, graph=courses.graph_for(spec.id),
                       subject_kind=spec.subject_kind, course_id=spec.id)


# --------------------------------------------------------------------- document


@router.get('/api/v1/deck/{deck_id}')
def get_deck(deck_id: str, request: Request):
    return _owned(request, deck_id)


@router.put('/api/v1/deck/{deck_id}')
def replace_deck(deck_id: str, request: Request, payload: dict):
    """Replace the whole document. The client owns the deck; the server owns validity,
    ownership and the version counter."""
    payload = _body(payload)
    user_id = _user_id(request)
    stored = _owned(request, deck_id)
    incoming = deck.normalise_document(payload, owner_id=user_id)
    incoming['id'] = deck_id
    incoming['created_at'] = stored.get('created_at')
    try:
        deck.require_valid(incoming)
    except deck.DeckError as exc:
        raise _refuse(exc)
    _commit(request, incoming)
    return incoming


@router.delete('/api/v1/deck/{deck_id}', status_code=204)
def delete_deck(deck_id: str, request: Request):
    if not deck.delete_deck(_settings(request), deck_id, owner_id=_user_id(request)):
        raise HTTPException(404, 'Deck not found')
    return Response(status_code=204)


# --------------------------------------------------------------------- slides


@router.post('/api/v1/deck/{deck_id}/slides', status_code=201)
def add_slide(deck_id: str, request: Request, payload: dict):
    payload = _body(payload)
    doc = _owned(request, deck_id)
    # A non-integer index would be an insertion position nobody asked for; treat it as "append".
    index = payload.get('index')
    index = index if isinstance(index, int) and not isinstance(index, bool) else None
    try:
        slide = deck.add_slide(doc, layout=str(payload.get('layout') or 'blank'),
                               notes=str(payload.get('notes') or ''), index=index)
    except deck.DeckError as exc:
        raise _refuse(exc)
    _commit(request, doc)
    return slide


@router.patch('/api/v1/deck/{deck_id}/slides/{slide_id}')
def patch_slide(deck_id: str, request: Request, slide_id: str, payload: dict):
    payload = _body(payload)
    doc = _owned(request, deck_id)
    slide = deck.patch_slide(doc, slide_id, payload)
    if slide is None:
        raise HTTPException(404, 'Slide not found')
    # Nothing has been written yet, so a validation failure simply abandons the in-memory
    # edit: the stored deck is still the last valid one.
    problems = deck.validate_document(doc)
    if problems:
        raise _refuse(deck.DeckError('The slide was not updated; it failed validation.', problems))
    _commit(request, doc)
    return slide


@router.delete('/api/v1/deck/{deck_id}/slides/{slide_id}', status_code=204)
def delete_slide(deck_id: str, request: Request, slide_id: str):
    doc = _owned(request, deck_id)
    if not deck.delete_slide(doc, slide_id):
        raise HTTPException(404, 'Slide not found')
    _commit(request, doc)
    return Response(status_code=204)


@router.post('/api/v1/deck/{deck_id}/slides/{slide_id}/move')
def move_slide(deck_id: str, request: Request, slide_id: str, payload: dict):
    payload = _body(payload)
    doc = _owned(request, deck_id)
    try:
        to_index = int(payload.get('to'))
    except (TypeError, ValueError):
        raise HTTPException(422, "A move needs an integer 'to' index.")
    if not deck.move_slide(doc, slide_id, to_index):
        raise HTTPException(404, 'Slide not found')
    _commit(request, doc)
    return doc


@router.post('/api/v1/deck/{deck_id}/slides/{slide_id}/duplicate', status_code=201)
def duplicate_slide(deck_id: str, request: Request, slide_id: str):
    doc = _owned(request, deck_id)
    clone = deck.duplicate_slide(doc, slide_id)
    if clone is None:
        raise HTTPException(404, 'Slide not found')
    _commit(request, doc)
    return clone


# --------------------------------------------------------------------- elements


@router.post('/api/v1/deck/{deck_id}/elements', status_code=201)
def add_element(deck_id: str, request: Request, payload: dict):
    """Add an element to a slide. ``{slide_id, element}``. This is what paste calls."""
    payload = _body(payload)
    doc = _owned(request, deck_id)
    slide_id = str(payload.get('slide_id') or '')
    element = payload.get('element')
    if not slide_id or not isinstance(element, dict):
        raise HTTPException(422, 'An element needs a slide_id and an element object.')
    try:
        created = deck.add_element(doc, slide_id, element)
    except deck.DeckError as exc:
        raise _refuse(exc)
    _commit(request, doc)
    return created


@router.patch('/api/v1/deck/{deck_id}/elements/{element_id}')
def patch_element(deck_id: str, request: Request, element_id: str, payload: dict):
    """Move, resize or restyle one element. This is what drag, resize and the inspector call."""
    payload = _body(payload)
    doc = _owned(request, deck_id)
    try:
        updated = deck.patch_element(doc, element_id, payload)
    except deck.DeckError as exc:
        raise _refuse(exc)
    if updated is None:
        raise HTTPException(404, 'Element not found')
    _commit(request, doc)
    return updated


@router.delete('/api/v1/deck/{deck_id}/elements/{element_id}', status_code=204)
def delete_element(deck_id: str, request: Request, element_id: str):
    doc = _owned(request, deck_id)
    if not deck.delete_element(doc, element_id):
        raise HTTPException(404, 'Element not found')
    _commit(request, doc)
    return Response(status_code=204)


# --------------------------------------------------------------------- export / import


@router.get('/api/v1/deck/{deck_id}/export.pptx')
def export_pptx(deck_id: str, request: Request):
    """The real .pptx. This is the route the product was missing: the file was written to
    disk and nothing served it."""
    doc = _owned(request, deck_id)
    try:
        data = deck.export_pptx(_settings(request), doc)
    except deck.DeckUnavailable as exc:
        return JSONResponse({'ok': False, 'reason': str(exc)}, status_code=503)
    filename = _filename(doc.get('title'), deck_id)
    return Response(content=data, media_type=PPTX_MEDIA_TYPE,
                    headers={'Content-Disposition': f'attachment; filename="{filename}"'})


def _filename(title, deck_id: str) -> str:
    slug = re.sub(r'[^A-Za-z0-9._-]+', '-', str(title or '')).strip('-')[:60]
    return f'{slug or deck_id}.pptx'


@router.post('/api/v1/deck/import', status_code=201)
def import_pptx(request: Request, payload: dict):
    """Upload a .pptx and get back an editable document.

    The bytes arrive base64-encoded inside JSON: the API's one content-type is
    ``application/json`` (enforced by the request middleware), so a raw binary body would be
    refused before it reached this handler. The imported deck is stored and returned.
    """
    payload = _body(payload)
    settings = _settings(request)
    user_id = _user_id(request)
    encoded = payload.get('data_base64') or payload.get('data') or ''
    if not isinstance(encoded, str) or not encoded.strip():
        raise HTTPException(422, 'Provide the .pptx as a base64 data_base64 string.')
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError):
        raise HTTPException(422, 'data_base64 is not valid base64.')
    if not data.startswith(b'PK'):
        raise HTTPException(422, 'That is not a .pptx file (it does not begin with PK).')
    try:
        doc = deck.import_pptx(settings, data, title=str(payload.get('title') or ''),
                               owner_id=user_id)
    except deck.DeckUnavailable as exc:
        return JSONResponse({'ok': False, 'reason': str(exc)}, status_code=503)
    except deck.DeckError as exc:
        raise _refuse(exc)
    if not doc['slides']:
        raise HTTPException(422, 'That presentation has no slides to import.')
    deck.save_deck(settings, doc)
    return doc


# --------------------------------------------------------------------- thumbnails / images


@router.get('/api/v1/deck/{deck_id}/slide/{slide_id}.svg')
def slide_svg(deck_id: str, request: Request, slide_id: str):
    """The per-slide thumbnail, as SVG built from the document model. No browser is involved:
    the text is real <text> with the real family, size and colour, and the images are data
    URIs of the same bytes the .pptx embeds."""
    doc = _owned(request, deck_id)
    svg = deck.slide_svg(_settings(request), doc, slide_id)
    if svg is None:
        raise HTTPException(404, 'Slide not found')
    return Response(content=svg, media_type='image/svg+xml; charset=utf-8')


@router.get('/api/v1/deck/{deck_id}/images')
def deck_images(deck_id: str, request: Request):
    """The images the deck references, each resolved through the media store with the
    attribution its licence requires. An unresolved sha is reported, not hidden."""
    doc = _owned(request, deck_id)
    return {'images': deck.deck_images(_settings(request), doc),
            'note': 'Every image is a licence-cleared, content-addressed asset. An image the '
                    'media index no longer holds is reported with resolved=false rather than '
                    'silently dropped.'}


@router.post('/api/v1/deck/{deck_id}/images', status_code=201)
def upload_deck_image(deck_id: str, request: Request, payload: dict):
    """Insert a local image: the bytes go into the same content-addressed media store every
    other image is served from, so an inserted picture is embedded in the .pptx and drawn in
    the SVG by exactly the path a licence-cleared download is. The bytes are base64 in JSON
    because the API's one content-type is application/json. Only image bytes are accepted —
    the store sniffs the magic and refuses anything else."""
    payload = _body(payload)
    _owned(request, deck_id)                       # upload requires owning a deck
    settings = _settings(request)
    encoded = payload.get('data_base64') or payload.get('data') or ''
    if not isinstance(encoded, str) or not encoded.strip():
        raise HTTPException(422, 'Provide the image as a base64 data_base64 string.')
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError):
        raise HTTPException(422, 'data_base64 is not valid base64.')
    if len(data) > 12_000_000:
        raise HTTPException(413, 'That image is larger than 12 MB.')
    sha = hashlib.sha256(data).hexdigest()
    media.store_bytes(settings, data, sha=sha, title=str(payload.get('title') or '')[ :120])
    if deck.image_path(settings, sha) is None:
        raise HTTPException(422, 'Those bytes are not a PNG, JPEG, GIF or WebP image.')
    return {'sha256': sha, 'bytes': len(data),
            'bytes_url': f'/api/v1/media/images/{sha}/bytes'}


__all__ = ['router']
