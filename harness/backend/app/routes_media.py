"""HTTP surface for image *acquisition*: fetch, library, lesson batch, attribution, delete.

Mounted by main.py through the optional-feature-router loop (the module is named
``routes_media``), so this file owns every ``/api/v1/images/*`` route and nothing else.
The pre-existing ``/api/v1/media/*`` routes live in main.py and are deliberately untouched:
those *read* the cache, and this module is the write path that fills it. The two prefixes
never collide, which is the whole reason for the second one.

Every route requires an authenticated account, resolved exactly as the rest of the API
resolves one: a bearer token whose SHA-256 digest is a live, unrevoked ``Token`` row
belonging to an active user. There is no anonymous mode here - a cached image belongs to
the account that fetched it, so a request with no token has no library to read. The library
is scoped to that account because "the images this instance happens to hold" and "the images
this learner asked for" are not the same list.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import logging
import re

from fastapi import Depends, APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from . import courses, curriculum
from .db import Token, User, now_ts
from .harness import media
from .security import digest, rate_limit, resolve_account, require_principal


log = logging.getLogger('luminfest.media.routes')

router = APIRouter(dependencies=[Depends(require_principal("images", 120))])

#: Ceiling on one library page. The library is a picker, not an export; a client that wants
#: everything asks again with a filter rather than paging through thousands of rows.
MAX_LIBRARY_PAGE = 200


def _account(request: Request) -> dict:
    """Resolve the authenticated account, or raise 401.

    Deliberately stricter than the web workbench's ``principal``: media has no development
    anonymous mode, because an unauthenticated fetch would write a cached, licence-cleared
    file that no account owns and no account could delete. The token and erasure checks are
    ``security.resolve_account``'s, so a deleted account's library is not served here.
    """
    factory = getattr(request.app.state, 'factory', None)
    if factory is None:
        raise HTTPException(503, 'Account storage is unavailable')
    with factory() as db:
        user = resolve_account(request, db, rate_key='images', limit=120)
        return {'user_id': user.id,
                'course_id': str(getattr(user, 'course_id', '') or ''),
                'account_role': str(getattr(user, 'role', '') or '')}


def _course_id(account: dict) -> str:
    try:
        return courses.course(account.get('course_id')).id
    except courses.UnknownCourse:
        return courses.DEFAULT_COURSE_ID


def _lesson(account: dict, concept_id: str) -> dict | None:
    """The lesson entry for a concept, in the caller's own course.

    Both id namespaces are accepted - an authored lesson id (``fractions``) and a graph node
    id (``fraction_equivalence``) name the same idea - because a client may hold either.
    """
    table = curriculum.course_concepts(_course_id(account))
    entry = table.get(concept_id)
    if entry is None:
        mapped = curriculum.GRAPH_TO_LESSON.get(concept_id)
        entry = table.get(mapped) if mapped else None
    return entry


class FetchInput(BaseModel):
    """Body for ``POST /api/v1/images/fetch``. This is the "create image fetch" action."""
    query: str = Field(min_length=1, max_length=200)
    concept_id: str = Field(default='', max_length=64)
    course_id: str = Field(default='', max_length=64)
    count: int = Field(default=1, ge=1, le=media.MAX_FETCH_PER_CALL)


class LessonInput(BaseModel):
    concept_id: str = Field(min_length=1, max_length=64)


class PasteImageInput(BaseModel):
    """The system clipboard delivers bytes, not a fetched/cleared web asset."""
    data_base64: str = Field(min_length=1, max_length=16_777_216)
    filename: str = Field(default='Pasted image', max_length=160)


@router.post('/api/v1/images/paste', status_code=201)
def paste_image(payload: PasteImageInput, request: Request):
    """Cache a locally pasted bitmap for the user's board, without claiming its licence."""
    account = _account(request)
    settings = request.app.state.settings
    try:
        raw = base64.b64decode(payload.data_base64, validate=True)
    except (ValueError, binascii.Error):
        raise HTTPException(422, 'data_base64 is not valid base64')
    if not raw or len(raw) > media.MAX_BYTES:
        raise HTTPException(422, 'The pasted image is empty or exceeds the 12 MB limit')
    mime, _ = media._sniff_mime(raw)
    if mime not in {'image/png', 'image/jpeg', 'image/webp', 'image/gif'}:
        raise HTTPException(422, 'Clipboard paste accepts PNG, JPEG, WebP or GIF images only')
    sha = hashlib.sha256(raw).hexdigest()
    title = ' '.join(payload.filename.split())[:120] or 'Pasted image'
    media.store_bytes(settings, raw, sha=sha, title=title, source='clipboard_paste')
    asset = next((row for row in media.cached_assets(settings)
                  if str(row.get('sha256') or '') == sha), None)
    if asset is None:
        raise HTTPException(422, 'The pasted bytes could not be cached as an image')
    media.record_ownership(settings, account['user_id'], [sha], query='clipboard paste')
    return {'asset': {'sha256': sha, 'src': f'/api/v1/media/images/{sha}/bytes',
                      'title': title,
                      'credit': 'Pasted from clipboard · source/licence not verified',
                      'licence': 'User-provided (unverified)', 'mime': mime,
                      'bytes': len(raw)}}


@router.post('/api/v1/images/fetch')
def fetch_images(payload: FetchInput, request: Request):
    """Search the open image providers, clear the licence gate, download and cache.

    The response carries the cached assets *and* the rejections, so a search that returns
    nothing is an argued result rather than a black box: the caller sees how many candidates
    were seen and why each one was dropped.
    """
    account = _account(request)
    settings = request.app.state.settings
    result = media.fetch(settings, payload.query, concept_id=payload.concept_id,
                         course_id=payload.course_id or _course_id(account),
                         count=payload.count)
    shas = [asset.get('sha256') for asset in result.get('assets') or []]
    media.record_ownership(settings, account['user_id'], shas,
                           query=result.get('query') or payload.query,
                           concept_id=payload.concept_id)
    return result


@router.get('/api/v1/images/library')
def image_library(request: Request,
                  q: str = Query(default='', max_length=200),
                  limit: int = Query(default=60, ge=1, le=MAX_LIBRARY_PAGE)):
    """This account's cached images, newest first, filterable by a text query.

    Every row carries its source, author, licence, licence URL and attribution string,
    because a picker that shows a picture without its credit is how an unattributed CC image
    gets reused.
    """
    account = _account(request)
    settings = request.app.state.settings
    rows = media.library(settings, account['user_id'], query=q)
    return {'assets': rows[:limit], 'total': len(rows), 'query': q,
            'pipeline': media.describe(settings),
            'scope': 'Only images this account fetched. Each row carries its author, licence '
                     'and attribution, and the bytes live inside the data directory so account '
                     'export and deletion cover them.'}


@router.post('/api/v1/images/for-lesson')
def images_for_lesson(payload: LessonInput, request: Request):
    """Fetch the images a lesson needs and return them keyed to lesson block positions.

    A lesson gains at most ``media.MAX_LESSON_IMAGES`` photographs: the concept title and the
    blocks that are about something visible decide the queries, and a need that finds nothing
    is reported with its rejections rather than attached as a placeholder.
    """
    account = _account(request)
    settings = request.app.state.settings
    entry = _lesson(account, payload.concept_id)
    if entry is None:
        raise HTTPException(404, 'Unknown concept in this course')
    concept_key = str(entry.get('id') or payload.concept_id)
    result = media.fetch_for_lesson(
        settings, concept_id=concept_key, title=str(entry.get('title') or ''),
        summary=str(entry.get('summary') or ''), blocks=entry.get('blocks') or [],
        course_id=_course_id(account))
    shas = [image['asset']['sha256'] for image in result.get('images') or []
            if isinstance(image.get('asset'), dict) and image['asset'].get('sha256')]
    media.record_ownership(settings, account['user_id'], shas, concept_id=concept_key)
    # The blocks are resolved against the live manifest, so an image deleted since the fetch
    # is not promised back as a block that would render nothing.
    result['blocks'] = media.lesson_photograph_blocks(settings, concept_key)
    return result


@router.get('/api/v1/images/{sha}/attribution')
def image_attribution(sha: str, request: Request):
    """The credit line for one cached image, or 404 when it was never cleared."""
    _account(request)
    credit = media.attribution_for(request.app.state.settings, sha)
    if credit is None:
        raise HTTPException(404, 'No such cached image')
    return credit


@router.delete('/api/v1/images/{sha}')
def delete_image(sha: str, request: Request):
    """Remove one cached image from this account's library.

    The bytes are shared content-addressed storage, so they are deleted only when no other
    account still holds the image and no lesson still points at it. Otherwise the account
    loses it from its library and the shared copy stays, which is the honest outcome - a
    delete that silently broke another learner's lesson would not be a delete.
    """
    account = _account(request)
    settings = request.app.state.settings
    if sha not in media.owned_shas(settings, account['user_id']):
        raise HTTPException(404, "No such image in this account's library")
    media.release_ownership(settings, account['user_id'], sha)
    if not media.claims(settings, sha) and not media.lesson_references(settings, sha):
        media.remove_asset(settings, sha)
        return {'removed': True, 'deleted_bytes': True, 'sha256': sha}
    return {'removed': True, 'deleted_bytes': False, 'sha256': sha,
            'note': 'Removed from your library. The cached file is kept because another '
                    'account or a lesson still refers to it.'}
