"""HTTP surface for flashcard decks: ``/api/v1/flashcards``.

Mounted by convention -- ``main.create_app`` imports this module and calls
``include_router`` -- so the capability can be removed by deleting the file. Every route
re-derives the caller from the authenticated principal and scopes every query to that
user; a card that is not yours is a 404, never a 403, because a 403 would confirm the card
exists. The router holds no scheduling logic: it validates input, calls
:mod:`app.flashcards`, and serialises the result.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from . import flashcards
from .db import Flashcard, Token, User, now_ts
from .security import digest, rate_limit

router = APIRouter()

API = '/api/v1/flashcards'

#: Upper bound on a single listing / session page, so one request cannot serialise a whole
#: deck of thousands.
MAX_PAGE = 200


def authenticated(request: Request):
    """Resolve ``(db, user)`` from the bearer token, exactly as ``main.authenticated`` does.

    ``main.create_app`` defines its auth dependency as a closure, so a router module cannot
    import it. Rather than weaken the rule, this mirrors it line for line: same header
    check, same rate limit, same token/user lookup, same commit on exit. A divergence here
    would be an authentication bug, so the two are kept deliberately identical.
    """
    from .main import start_write
    factory = request.app.state.factory
    header = request.headers.get('authorization', '')
    if not header.startswith('Bearer ') or len(header) > 200:
        raise HTTPException(401, 'Valid bearer token required', headers={'WWW-Authenticate': 'Bearer'})
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


class CardInput(BaseModel):
    concept_id: str
    front: str
    back: str
    kind: str = 'basic'
    hint: str | None = None
    tags: list[str] = Field(default_factory=list)
    source: dict = Field(default_factory=dict)


class CardPatch(BaseModel):
    front: str | None = None
    back: str | None = None
    hint: str | None = None
    kind: str | None = None
    tags: list[str] | None = None


class GenerateInput(BaseModel):
    concept_id: str | None = None
    lesson_id: str | None = None
    count: int | None = None
    #: When true, return the cards that would be created without persisting them, so the
    #: client can show a preview before the learner commits.
    dry_run: bool = False


class ReviewInput(BaseModel):
    grade: int


class ImportInput(BaseModel):
    #: A JSON deck: either the export's ``cards`` array or the whole export payload's list.
    cards: list[dict] | None = None
    #: A CSV deck, verbatim. Both transports are JSON because the API's boundary middleware
    #: requires ``application/json`` for every write with a body; the CSV text rides inside
    #: the JSON envelope rather than as a raw ``text/csv`` request.
    csv: str | None = None


def _page(limit: int, offset: int) -> tuple[int, int]:
    return max(1, min(int(limit), MAX_PAGE)), max(0, int(offset))


def _owned(db, user_id: str, card_id: str):
    """The caller's card, or None. Scoped by ``user_id`` so another learner's card is
    indistinguishable from one that does not exist."""
    return db.scalar(select(Flashcard).where(Flashcard.id == card_id,
                                            Flashcard.user_id == user_id))


def _concept(identifier: str) -> str:
    resolved = flashcards.resolve_concept(identifier)
    if resolved is None:
        raise HTTPException(404, f'Unknown concept {identifier!r}')
    return resolved


def _card_or_404(db, user_id: str, card_id: str) -> Flashcard:
    card = _owned(db, user_id, card_id)
    if card is None:
        raise HTTPException(404, 'No such card')
    return card


def _validate_kind(kind: str) -> str:
    if kind not in flashcards.KINDS:
        raise HTTPException(422, f'kind must be one of {", ".join(flashcards.KINDS)}')
    return kind


# ------------------------------------------------------------------ read

@router.get(API)
def list_cards(concept_id: str | None = None, kind: str | None = None, due: bool = False,
               limit: int = 100, offset: int = 0, auth=Depends(authenticated)):
    db, user = auth
    limit, offset = _page(limit, offset)
    stmt = select(Flashcard).where(Flashcard.user_id == user.id)
    if concept_id:
        stmt = stmt.where(Flashcard.concept_id == _concept(concept_id))
    if kind:
        stmt = stmt.where(Flashcard.kind == _validate_kind(kind))
    if due:
        stmt = stmt.where(Flashcard.due_at <= now_ts())
    stmt = (stmt.order_by(Flashcard.due_at, Flashcard.created_at, Flashcard.id)
            .limit(limit).offset(offset))
    cards = list(db.scalars(stmt))
    return {'cards': [flashcards.card_json(card) for card in cards], 'count': len(cards)}


@router.get(API + '/session')
def session(concept_id: str | None = None, limit: int = Query(default=20, ge=1),
            auth=Depends(authenticated)):
    db, user = auth
    limit, _ = _page(limit, 0)
    now = now_ts()
    stmt = select(Flashcard).where(Flashcard.user_id == user.id, Flashcard.due_at <= now)
    if concept_id:
        stmt = stmt.where(Flashcard.concept_id == _concept(concept_id))
    due = list(db.scalars(stmt))
    ordered = flashcards.build_session(due, limit)
    return {
        'cards': [{**flashcards.card_json(card, now),
                   'preview': flashcards.grade_preview(card, now)} for card in ordered],
        'count': len(ordered),
        'due_total': len(due),
        'concepts': sorted({card.concept_id for card in ordered}),
    }


@router.get(API + '/stats')
def stats(concept_id: str | None = None, auth=Depends(authenticated)):
    db, user = auth
    stmt = select(Flashcard).where(Flashcard.user_id == user.id)
    if concept_id:
        stmt = stmt.where(Flashcard.concept_id == _concept(concept_id))
    cards = list(db.scalars(stmt))
    return flashcards.deck_stats(cards)


# ------------------------------------------------------------------ write

@router.post(API, status_code=201)
def create_card(payload: CardInput, auth=Depends(authenticated)):
    db, user = auth
    concept_id = _concept(payload.concept_id)
    front = ' '.join(payload.front.split())
    back = ' '.join(payload.back.split())
    if not front or not back:
        raise HTTPException(422, 'A card needs a non-empty front and back')
    _validate_kind(payload.kind)
    # Provenance is mandatory: a card whose source cannot be named cannot be checked
    # against the material it claims to teach, so it is refused rather than stored.
    if not flashcards.source_exists(payload.source):
        raise HTTPException(422, 'A card needs provenance: source must name a real '
                                 'curriculum block, question or concept.')
    key = flashcards.front_key(front)
    clash = db.scalar(select(Flashcard).where(Flashcard.user_id == user.id,
                                              Flashcard.concept_id == concept_id,
                                              Flashcard.front_key == key))
    if clash is not None:
        raise HTTPException(409, 'That card already exists in this concept.')
    now = now_ts()
    card = Flashcard(user_id=user.id, concept_id=concept_id, front=front, back=back,
                     hint=(payload.hint or '').strip() or None, tags=list(payload.tags),
                     source=payload.source, kind=payload.kind, front_key=key,
                     due_at=now, state='new')
    db.add(card)
    db.flush()
    return flashcards.card_json(card, now)


@router.patch(API + '/{card_id}')
def update_card(card_id: str, payload: CardPatch, auth=Depends(authenticated)):
    db, user = auth
    card = _card_or_404(db, user.id, card_id)
    if payload.kind is not None:
        card.kind = _validate_kind(payload.kind)
    if payload.hint is not None:
        card.hint = payload.hint.strip() or None
    if payload.tags is not None:
        card.tags = list(payload.tags)
    if payload.back is not None:
        back = ' '.join(payload.back.split())
        if not back:
            raise HTTPException(422, 'back cannot be empty')
        card.back = back
    if payload.front is not None:
        front = ' '.join(payload.front.split())
        if not front:
            raise HTTPException(422, 'front cannot be empty')
        key = flashcards.front_key(front)
        if key != card.front_key:
            clash = db.scalar(select(Flashcard).where(Flashcard.user_id == user.id,
                                                      Flashcard.concept_id == card.concept_id,
                                                      Flashcard.front_key == key))
            if clash is not None:
                raise HTTPException(409, 'Another card in this concept already has that front.')
            card.front = front
            card.front_key = key
    card.updated_at = now_ts()
    return flashcards.card_json(card)


@router.delete(API + '/{card_id}', status_code=204)
def delete_card(card_id: str, auth=Depends(authenticated)):
    db, user = auth
    card = _card_or_404(db, user.id, card_id)
    db.delete(card)
    return Response(status_code=204)


@router.post(API + '/{card_id}/review')
def review_card(card_id: str, payload: ReviewInput, auth=Depends(authenticated)):
    db, user = auth
    card = _card_or_404(db, user.id, card_id)
    try:
        schedule = flashcards.apply_grade(card, payload.grade)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {'card': flashcards.card_json(card), 'schedule': schedule,
            'preview': flashcards.grade_preview(card)}


# ------------------------------------------------------------------ generation

@router.post(API + '/generate')
def generate(payload: GenerateInput, auth=Depends(authenticated)):
    db, user = auth
    identifier = payload.concept_id or payload.lesson_id
    if not identifier:
        raise HTTPException(422, 'Provide a concept_id or a lesson_id')
    concept_id = _concept(identifier)
    if payload.count is not None and payload.count < 1:
        raise HTTPException(422, 'count must be at least 1')
    if payload.dry_run:
        result = flashcards.preview_for_user(db, user.id, concept_id, payload.count)
    else:
        result = flashcards.generate_for_user(db, user.id, concept_id, payload.count)
    result['skipped'] = len(result['skipped_duplicate'])
    return result


# ------------------------------------------------------------------ interchange

@router.get(API + '/export')
def export(fmt: str = 'json', concept_id: str | None = None, auth=Depends(authenticated)):
    db, user = auth
    fmt = fmt.lower()
    if fmt not in ('json', 'csv'):
        raise HTTPException(422, "fmt must be 'json' or 'csv'")
    stmt = select(Flashcard).where(Flashcard.user_id == user.id)
    if concept_id:
        stmt = stmt.where(Flashcard.concept_id == _concept(concept_id))
    cards = list(db.scalars(stmt.order_by(Flashcard.concept_id, Flashcard.created_at)))
    body, media_type = flashcards.export_cards(cards, fmt)
    return Response(content=body, media_type=media_type,
                    headers={'Content-Disposition': f'attachment; filename="flashcards.{fmt}"'})


@router.post(API + '/import')
def import_cards(payload: ImportInput, auth=Depends(authenticated)):
    """Import a JSON or CSV deck. Provenance is preserved when present and, when a row
    omits it, recorded as the import itself -- an imported card still names where it came
    from rather than arriving with none."""
    db, user = auth
    if payload.csv is not None:
        try:
            rows = flashcards.parse_import(payload.csv.encode('utf-8'), 'text/csv')
        except ValueError as exc:
            raise HTTPException(422, f'Could not parse the deck: {exc}') from exc
    elif payload.cards is not None:
        rows = [row for row in payload.cards if isinstance(row, dict)]
    else:
        raise HTTPException(422, 'Provide "cards" (JSON) or "csv" (CSV text)')
    now = now_ts()
    imported: list[Flashcard] = []
    duplicate = 0
    invalid = 0
    for row in rows:
        concept_id = flashcards.resolve_concept(str(row.get('concept_id') or ''))
        front = ' '.join(str(row.get('front') or '').split())
        back = ' '.join(str(row.get('back') or '').split())
        kind = str(row.get('kind') or 'basic')
        if not concept_id or not front or not back or kind not in flashcards.KINDS:
            invalid += 1
            continue
        source = row.get('source')
        if not flashcards.source_exists(source):
            source = {'kind': 'concept', 'concept_id': concept_id}
        key = flashcards.front_key(front)
        exists = db.scalar(select(Flashcard).where(Flashcard.user_id == user.id,
                                                   Flashcard.concept_id == concept_id,
                                                   Flashcard.front_key == key))
        if exists is not None:
            duplicate += 1
            continue
        tags = row.get('tags') if isinstance(row.get('tags'), list) else []
        card = Flashcard(user_id=user.id, concept_id=concept_id, front=front, back=back,
                         hint=str(row.get('hint') or '').strip() or None,
                         tags=[str(t) for t in tags], source=source, kind=kind,
                         front_key=key, due_at=now, state='new')
        db.add(card)
        imported.append(card)
    db.flush()
    return {'imported': len(imported), 'skipped_duplicate': duplicate,
            'skipped_invalid': invalid,
            'cards': [flashcards.card_json(card, now) for card in imported]}
