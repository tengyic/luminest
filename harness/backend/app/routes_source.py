"""HTTP surface for *finding* a source and turning it into a course in one motion.

Mounted by convention: ``main.create_app`` imports this module through the
optional-feature-router loop (the module is named ``routes_source``) and includes
``router``, so nothing in the shared API file has to know this feature exists.

    POST /api/v1/create/search   candidates for a topic, each with its rights position
    POST /api/v1/create/auto     build, personalise, store and enrol in one request

The feature itself lives in ``app.source_extension``; this file is the boundary and
nothing else. Two things are deliberate here.

* **Auth is inherited, not re-invented.** The dependency is ``routes_create.account``,
  the same bearer-token check every other create route uses. A course belongs to an
  account, so there is no anonymous mode, and re-deriving the check from ``Token`` and
  ``User`` would be a second auth scheme answering the same question differently.

* **A refusal is a 422 with the reason.** ``SourceRefused`` carries a code, a reason in
  the learner's words, and - when a licence is what stopped them - the licence class.
  The response body is that refusal verbatim rather than a generic error, because
  "OpenStax is link-only, so paste your own material" is actionable and "bad request"
  is not.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import course_builder
from . import source_extension
from .db import now_ts
from .routes_create import account  # one auth scheme, borrowed rather than rebuilt

log = logging.getLogger('luminfest.source.routes')

router = APIRouter()

#: A pasted source is capped at the same ceiling the paste path in ``routes_create``
#: uses. Stated as data so the refusal that names it is generated from the number the
#: server actually enforced.
MAX_SOURCE_CHARS = 2_000_000

#: A URL is a URL; 2048 is the practical ceiling every client agrees on. A longer
#: string is not a link a browser could open, so it is refused as malformed rather
#: than handed to the fetcher to fail on.
MAX_URL_CHARS = 2048


class SearchInput(BaseModel):
    """What the learner typed, and how many answers they want to read."""

    query: str = Field(default='', max_length=300)
    limit: int = Field(default=source_extension.SEARCH_LIMIT, ge=1,
                       le=source_extension.SEARCH_LIMIT)


class AutoInput(BaseModel):
    """One of four ways to say where the material is, plus optional decoration.

    ``candidate_id`` is a handle for something the learner just saw in a search; the
    other three are the source itself, in the three shapes a client can send one.
    Exactly one is expected - ``source_extension.build_course`` resolves them in a
    fixed order and says which it used, so an ambiguous request is answered
    deterministically rather than by accident of dict ordering.
    """

    query: str = Field(default='', max_length=300)
    candidate_id: str = Field(default='', max_length=64)
    text: str = Field(default='', max_length=MAX_SOURCE_CHARS)
    url: str = Field(default='', max_length=MAX_URL_CHARS)
    title: str = Field(default='', max_length=200)
    subject: str = Field(default='', max_length=80)
    level: str = Field(default='', max_length=40)
    #: Save it to the account. False gives back the plan and stores nothing, so a
    #: learner can read what a source would turn into before committing to it.
    save: bool = True
    #: Make it the active course as well as storing it. Default on: the point of this
    #: endpoint is that finding a course and starting it are one motion, and a
    #: learner who wanted only to browse a plan can send ``save=false``.
    enrol: bool = True


def _refusal(exc: Exception) -> HTTPException:
    """A structured refusal as a 422, with the code and the bar that was not met."""
    detail = {
        'refused': True,
        'code': getattr(exc, 'code', ''),
        'reason': getattr(exc, 'reason', str(exc)),
    }
    for key in ('licence_class', 'detail'):
        value = getattr(exc, key, '')
        if value:
            detail[key] = value
    detail['however'] = ('Search again, paste your own material, or upload a file at '
                         '/api/v1/create/upload.')
    return HTTPException(422, detail=detail)


@router.post('/api/v1/create/search')
def create_search(payload: SearchInput, auth=Depends(account)):
    """Find candidate sources for a topic, each carrying what may be done with it.

    The list is a decision aid, not a menu: every candidate states its licence class
    and whether this harness may build a course from it, so "OpenStax College
    Physics, link-only" and "a Wikipedia article, CC BY-SA, buildable" do not look
    like the same option. Nothing is persisted and nothing is fetched beyond the
    candidate's own metadata - the article's text is read only when the learner asks
    for a course to be built from it.
    """
    _db, user = auth
    result = source_extension.search(payload.query, limit=payload.limit)
    payload = result.to_dict()
    payload['saved_for'] = str(getattr(user, 'goal', '') or '')
    return payload


@router.post('/api/v1/create/auto', status_code=201)
def create_auto(payload: AutoInput, auth=Depends(account)):
    """Build a course from a found or supplied source, personalised to this learner.

    The three things that happen here are the feature: the source is resolved (from a
    candidate the learner picked, or from text or a URL they supplied), the plan is
    personalised against the learner's own recorded goal and pace, and - unless they
    asked otherwise - the course is stored on their account and made the active one.
    A refusal at any stage leaves nothing behind.
    """
    db, user = auth
    try:
        built = source_extension.build_course(
            user,
            query=payload.query,
            candidate_id=payload.candidate_id,
            text=payload.text,
            url=payload.url,
            title=payload.title,
            subject=payload.subject,
            level=payload.level,
        )
    except source_extension.SourceRefused as exc:
        raise _refusal(exc) from exc

    plan = built.plan
    rights = plan.source
    summary = {
        'course_id': plan.course_id,
        'title': plan.title,
        'subject': plan.subject,
        'level': plan.level,
        'concepts': len(plan.concepts),
        'questions': len(plan.questions),
        'graph_stats': plan.stats(),
        # The rights position, read straight off the policy the plan was stamped
        # with. Built from the same fields ``CoursePlan.to_preview`` reports, so the
        # auto path and the preview path cannot disagree about what a source is.
        'source_rights': {
            'name': rights.name,
            'url': rights.url,
            'licence': rights.licence,
            'licence_class': rights.licence_class.value,
            'attribution': rights.attribution,
            'needs_attribution': rights.needs_attribution,
        },
        'personalisation': built.personalisation.to_dict(),
        'candidate': built.candidate.to_dict() if built.candidate else None,
        'rights_note': course_builder.RIGHTS_NOTE,
    }

    if not payload.save:
        # The plan, and nothing else. A learner who reads this and then commits
        # sends the same request with ``save=true`` and gets exactly this course,
        # because ``course_id`` is minted here and the plan is deterministic.
        return JSONResponse(status_code=200, content={**summary, 'created': False,
                                                       'enrolled': False,
                                                       'next': 'Send the same request with '
                                                               '"save": true to store it.'})

    row = course_builder.save_course(db, user, plan)
    enrolled = False
    if payload.enrol:
        user.course_id = row.id
        user.onboarding_completed_at = now_ts()
        enrolled = True
    db.commit()
    return {
        **summary,
        'course_id': row.id,
        'course': row.to_dict(),
        'created': True,
        'enrolled': enrolled,
        'active_course': getattr(user, 'course_id', '') or '',
        'next': ('This course is your active course now: Today, the map, the lessons and '
                 'the practice items all come from it.'
                 if enrolled else
                 'Enrol in it at /api/v1/my-courses/{id}/enrol to make it your active '
                 'course.'),
    }
