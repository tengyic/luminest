"""Flashcard decks: grounded auto-generation, FSRS-6 scheduling, interleaved study.

A flashcard here is not a floating question/answer pair. It is a card *about a real
curriculum object* -- a lesson block or a question -- and it carries the provenance that
says which one, so its content can always be traced back and checked. A card with no
provenance is refused: a card whose source cannot be named cannot be verified against the
material it claims to teach.

Two design commitments run through this module:

**Generation is grounded, not templated.** Every card is built from text that already
exists in ``app.curriculum`` -- a block body, a formula, a worked example, a distractor
diagnosis. Nothing is invented. The ``misconception`` cards are the ones worth generating
most: a distractor whose diagnosis names an error process ("adds denominators as though
units could be combined") becomes a card whose answer is *that error*, so a review targets
the actual mistake rather than the surface fact.

**Scheduling is FSRS-6, imported not re-implemented.** A review is graded on the standard
four-point scale (again / hard / good / easy) and handed to :func:`app.memory.review`,
which returns the updated DSR state; :func:`app.memory.due_time` turns that state into the
next ``due_at``. This module owns none of the maths. What it adds is the card-shaped
plumbing around it -- and a session builder that interleaves across concepts, because
serving thirty cards from one concept in a row is massed practice, which is precisely what
spaced repetition exists to avoid.

Public API:
    resolve_concept(id) -> lesson concept id or None
    source_exists(source) -> bool
    generate_candidates(concept_id) -> list[card dict]      # pure, no DB
    generate_for_user(db, user_id, concept_id, count) -> summary dict
    apply_grade(card, grade, now) -> dict                    # FSRS-6 update, in place
    grade_preview(card, now) -> dict                         # per-grade consequence
    build_session(cards, limit) -> list                      # interleaved, due order
    deck_stats(cards, now) -> dict
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections import defaultdict

from . import memory
from .curriculum import CONCEPTS, GRAPH_TO_LESSON, QUESTIONS
from .db import Flashcard, iso, now_ts

#: Card kinds. ``misconception`` is deliberately first in priority: see the module docstring.
KINDS = ('basic', 'cloze', 'definition', 'formula', 'misconception')

#: Cards kept per concept. A deck is for practice, not storage, and an unbounded generator
#: buries the learner. The cap is applied to the *selected* candidates (see :func:`_select`),
#: not to the number of rows inserted, so re-running generation with the same parameters is
#: idempotent: the same candidates are chosen and all are already present.
MAX_CARDS_PER_CONCEPT = 12
#: Ceiling for an explicit ``count`` request, so a caller cannot ask for the whole syllabus
#: in one deck.
HARD_MAX_CARDS = 40

#: Scheduler target: the interval is the time until recall probability decays to this value.
#: FSRS-6's own default, used unmodified.
DESIRED_RETENTION = 0.9

#: Round-robin order used to build a balanced deck: one card of each kind before a second of
#: any, so a concept's deck is not all misconceptions and not all definitions.
_KIND_ORDER = ('misconception', 'definition', 'cloze', 'formula', 'basic')

#: Function words a cloze blank must not land on: blanking "the" tests nothing. The list is
#: deliberately short -- the real filter is "is this the longest content word in the
#: sentence", and a long stopword list would silently exclude legitimate short terms.
_STOPWORDS = frozenset("""
a an the and or but if then than that this these those of to in on for with without by from
as is are was were be been being it its they them their there here what which who whom whose
when where why how not no nor so such do does did done doing have has had having will would
can could should may might must about into over under between among each any all both few
more most other some only own same very just also too much many one two three you your we our
""".split())

_SENTENCE = re.compile(r'(?<=[.!?])\s+')
_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]*")


# ------------------------------------------------------------------ resolution

def resolve_concept(identifier: str) -> str | None:
    """Map a lesson id or a knowledge-graph node id to the authored lesson concept id.

    Lessons and graph nodes are separate namespaces (``fractions`` is a lesson,
    ``fraction_equivalence`` is the node it teaches). A caller may hold either id, so both
    are accepted and normalised here rather than at every call site.
    """
    if not identifier:
        return None
    if identifier in CONCEPTS:
        return identifier
    lesson = GRAPH_TO_LESSON.get(identifier)
    if lesson and lesson in CONCEPTS:
        return lesson
    return None


def _blocks(concept_id: str) -> list[dict]:
    return list((CONCEPTS.get(concept_id) or {}).get('blocks') or [])


def _questions(concept_id: str) -> list[dict]:
    return [q for q in QUESTIONS.values() if q.get('concept_id') == concept_id]


# ------------------------------------------------------------------ provenance

def block_source(concept_id: str, index: int) -> dict:
    blocks = _blocks(concept_id)
    return {'kind': 'block', 'concept_id': concept_id, 'index': index,
            'block_kind': blocks[index].get('kind') if 0 <= index < len(blocks) else ''}


def question_source(concept_id: str, question_id: str) -> dict:
    return {'kind': 'question', 'concept_id': concept_id, 'question_id': question_id}


def source_exists(source) -> bool:
    """True when a card's provenance names a curriculum object that actually exists.

    The three shapes are a lesson block (by index), a question (by id) and the concept
    itself. Anything else -- or a referent that has been renamed away -- is not provenance.
    """
    if not isinstance(source, dict):
        return False
    concept_id = source.get('concept_id')
    if not isinstance(concept_id, str) or concept_id not in CONCEPTS:
        return False
    kind = source.get('kind')
    if kind == 'block':
        index = source.get('index')
        return isinstance(index, int) and 0 <= index < len(_blocks(concept_id))
    if kind == 'question':
        question_id = source.get('question_id')
        question = QUESTIONS.get(question_id)
        return bool(question) and question.get('concept_id') == concept_id
    if kind == 'concept':
        return True
    return False


# ------------------------------------------------------------------ text helpers

def normalise(text: str) -> str:
    """Collapse whitespace and case so two renderings of one prompt dedupe together."""
    return ' '.join(str(text or '').split()).strip().lower()


def front_key(front: str) -> str:
    return hashlib.sha256(normalise(front).encode('utf-8')).hexdigest()


def _trim(text: str, limit: int = 600) -> str:
    value = ' '.join(str(text or '').split())
    return value if len(value) <= limit else value[:limit - 1].rstrip() + '\u2026'


# ------------------------------------------------------------------ generation

def _definition_candidates(concept: dict) -> list[dict]:
    """Definitions come from the concept's ``concept`` blocks, one card each.

    The block titles are authored and stable (``Core idea``, ``Definitions and
    conditions``, ``Where this sits``), so the prompt can name what the block is for
    instead of asking a vague "what is this?".
    """
    out = []
    title = concept.get('title', concept['id'])
    for index, block in enumerate(concept.get('blocks') or []):
        if block.get('kind') != 'concept' or not block.get('body'):
            continue
        heading = block.get('title', '')
        if heading == 'Definitions and conditions':
            front = f'What conditions must hold for {title}?'
        elif heading == 'Where this sits':
            front = f'Where does {title} sit, and what does it lead to?'
        else:
            front = f'What is {title}?'
        out.append({'kind': 'definition', 'front': front, 'back': _trim(block['body']),
                    'hint': '', 'tags': ['definition', concept['id']],
                    'source': block_source(concept['id'], index)})
    return out


def _formula_candidates(concept: dict) -> list[dict]:
    out = []
    for index, block in enumerate(concept.get('blocks') or []):
        formula = block.get('formula')
        if not formula:
            continue
        out.append({'kind': 'formula',
                    'front': f'Write the relationship for {concept.get("title", concept["id"])}.',
                    'back': _trim(formula), 'hint': '', 'tags': ['formula', concept['id']],
                    'source': block_source(concept['id'], index)})
    return out


def _worked_example_candidates(concept: dict) -> list[dict]:
    out = []
    for index, block in enumerate(concept.get('blocks') or []):
        if block.get('kind') != 'worked_example' or not block.get('body'):
            continue
        out.append({'kind': 'basic',
                    'front': f'{block.get("title", "Worked example")}: what is the method?',
                    'back': _trim(block['body']), 'hint': '', 'tags': ['method', concept['id']],
                    'source': block_source(concept['id'], index)})
    return out


def _content_word(sentence: str) -> str | None:
    """The longest non-stopword token, i.e. the word worth blanking."""
    words = [w for w in _WORD.findall(sentence) if w.lower() not in _STOPWORDS and len(w) >= 5]
    return max(words, key=len) if words else None


def _cloze_candidates(concept: dict, limit: int = 2) -> list[dict]:
    """Cloze cards from key sentences, blanking a content word -- never a stopword.

    Only the ``Core idea`` block is mined: it holds the definitional sentences, and
    blanking a word in a worked-example step would produce a card that is really a
    procedure question in disguise.
    """
    out = []
    for index, block in enumerate(concept.get('blocks') or []):
        if block.get('kind') != 'concept' or block.get('title') != 'Core idea':
            continue
        for sentence in _SENTENCE.split(block.get('body', '')):
            if len(out) >= limit:
                return out
            target = _content_word(sentence)
            if target is None:
                continue
            blanked = re.sub(r'\b' + re.escape(target) + r'\b', '____', sentence, count=1)
            if blanked == sentence:
                continue
            out.append({'kind': 'cloze', 'front': f'Fill the blank: {_trim(blanked, 400)}',
                        'back': target, 'hint': '', 'tags': ['cloze', concept['id']],
                        'source': block_source(concept['id'], index)})
    return out


def _misconception_candidates(concept: dict) -> list[dict]:
    """A card per diagnosed distractor: the prompt names the wrong answer, the answer names
    the error process. This is the card that targets the mistake rather than the fact."""
    out = []
    for question in _questions(concept['id']):
        texts = {o.get('id'): o.get('text', '') for o in question.get('options') or []}
        for option_id, diagnosis in (question.get('distractor_diagnoses') or {}).items():
            reason = diagnosis.get('reason')
            if not reason:
                continue
            answer = _trim(reason, 300)
            next_action = diagnosis.get('next_action')
            if next_action:
                answer += f' Next: {_trim(next_action, 200)}'
            out.append({
                'kind': 'misconception',
                'front': f'In \u201c{_trim(question.get("prompt", ""), 220)}\u201d, the answer '
                         f'\u201c{texts.get(option_id, "")}\u201d is wrong. What error does it represent?',
                'back': answer,
                'hint': diagnosis.get('category', ''),
                'tags': ['misconception', diagnosis.get('category', ''), concept['id']],
                'source': question_source(concept['id'], question['id']),
            })
    return out


def generate_candidates(concept_id: str, cap: int = MAX_CARDS_PER_CONCEPT) -> list[dict]:
    """Every card that can be grounded in this concept, deduped and capped.

    Deterministic: the same concept always yields the same ordered list, which is what makes
    re-running generation a no-op rather than a slow duplication.
    """
    concept = CONCEPTS.get(concept_id)
    if not concept:
        return []
    raw = (_misconception_candidates(concept) + _definition_candidates(concept)
           + _cloze_candidates(concept) + _formula_candidates(concept)
           + _worked_example_candidates(concept))
    # Dedupe on the normalised front before the cap, so a duplicate cannot consume a slot.
    seen: set[str] = set()
    unique: list[dict] = []
    for card in raw:
        key = front_key(card['front'])
        if key in seen:
            continue
        seen.add(key)
        unique.append(card)
    return _select(unique, cap)


def _select(candidates: list[dict], cap: int) -> list[dict]:
    """Round-robin across kinds up to ``cap`` (see ``_KIND_ORDER``)."""
    by_kind: dict[str, list[dict]] = defaultdict(list)
    for card in candidates:
        by_kind[card['kind']].append(card)
    counters: dict[str, int] = defaultdict(int)
    out: list[dict] = []
    while len(out) < cap:
        progressed = False
        for kind in _KIND_ORDER:
            if len(out) >= cap:
                break
            index = counters[kind]
            if index < len(by_kind[kind]):
                out.append(by_kind[kind][index])
                counters[kind] += 1
                progressed = True
        if not progressed:
            break
    return out


def generate_for_user(db, user_id: str, concept_id: str, count: int | None = None) -> dict:
    """Generate and persist a concept's deck. Idempotent for a given ``count``.

    Returns the created cards, the fronts skipped as duplicates, and the concept. Existing
    fronts for this concept are skipped rather than re-inserted, so calling this twice with
    the same arguments inserts nothing the second time.
    """
    concept_id = resolve_concept(concept_id) or concept_id
    if concept_id not in CONCEPTS:
        raise KeyError(concept_id)
    cap = min(count or MAX_CARDS_PER_CONCEPT, HARD_MAX_CARDS)
    if cap < 1:
        cap = 1
    existing = {row.front_key for row in db.query(Flashcard)
                .filter(Flashcard.user_id == user_id, Flashcard.concept_id == concept_id).all()}
    created: list[Flashcard] = []
    skipped: list[str] = []
    now = now_ts()
    for candidate in generate_candidates(concept_id, cap):
        key = front_key(candidate['front'])
        if key in existing:
            skipped.append(candidate['front'])
            continue
        card = Flashcard(user_id=user_id, concept_id=concept_id,
                         front=candidate['front'], back=candidate['back'],
                         hint=candidate['hint'] or None, tags=candidate['tags'],
                         source=candidate['source'], kind=candidate['kind'],
                         front_key=key, due_at=now, state='new')
        db.add(card)
        created.append(card)
        existing.add(key)
    db.flush()
    return {'concept_id': concept_id, 'created': len(created), 'skipped_duplicate': skipped,
            'cards': [card_json(card, now) for card in created]}


def preview_for_user(db, user_id: str, concept_id: str, count: int | None = None) -> dict:
    """The cards generation *would* add, without adding them.

    Same candidate selection as :func:`generate_for_user`, minus the fronts already in the
    deck. This is what lets the UI show what a generate action will create before it is
    committed, so the learner is never surprised by the deck they get.
    """
    concept_id = resolve_concept(concept_id) or concept_id
    if concept_id not in CONCEPTS:
        raise KeyError(concept_id)
    cap = min(count or MAX_CARDS_PER_CONCEPT, HARD_MAX_CARDS)
    if cap < 1:
        cap = 1
    existing = {row.front_key for row in db.query(Flashcard)
                .filter(Flashcard.user_id == user_id, Flashcard.concept_id == concept_id).all()}
    cards: list[dict] = []
    skipped: list[str] = []
    for candidate in generate_candidates(concept_id, cap):
        if front_key(candidate['front']) in existing:
            skipped.append(candidate['front'])
            continue
        cards.append({'front': candidate['front'], 'back': candidate['back'],
                      'hint': candidate['hint'], 'kind': candidate['kind'],
                      'tags': candidate['tags'], 'source': candidate['source'],
                      'concept_id': concept_id})
    return {'concept_id': concept_id, 'created': len(cards), 'skipped_duplicate': skipped,
            'cards': cards}


# ------------------------------------------------------------------ FSRS-6 scheduling

def _fsrs_state(card: Flashcard) -> dict:
    """The card's DSR state in the plain dict shape ``app.memory`` operates on."""
    return {'stability': card.stability, 'difficulty': card.difficulty,
            'last_review': card.last_review_at, 'reps': card.reps or 0,
            'lapses': card.lapses or 0}


def _next_state(card: Flashcard, grade: int, now: float) -> dict:
    """One graded review, routed to the right FSRS-6 entry point.

    A card that has never been reviewed goes through :func:`app.memory.new_state`, which
    applies the published rating-dependent initial stability (w0-w3). It deliberately does
    NOT go through :func:`app.memory.review` with an empty dict: ``review`` treats a state
    with no stability as *legacy* and seeds it from a Leitner half-life, which would give a
    brand-new card a fabricated history. A reviewed card is a real DSR state and goes
    through ``review`` as normal.
    """
    if (card.reps or 0) == 0 or card.stability is None or card.last_review_at is None:
        state = memory.new_state(grade, now)
        state['last_stability_gain'] = state['stability']
        return state
    return memory.review(_fsrs_state(card), grade, now)


def _display_state(reps: int, grade: int) -> str:
    """A human summary of the DSR state. Not a second scheduler -- the schedule is due_at."""
    if reps <= 0:
        return 'new'
    if grade == memory.RATING_AGAIN:
        return 'relearning' if reps > 1 else 'learning'
    return 'review' if reps > 1 else 'learning'


def apply_grade(card: Flashcard, grade: int, now: float | None = None) -> dict:
    """Apply one FSRS-6 review to ``card`` in place and return its new schedule.

    The maths is :func:`app.memory.review`; the interval is
    :func:`app.memory.due_time`. Nothing about stability, difficulty or the forgetting
    curve is computed here.
    """
    if grade not in (memory.RATING_AGAIN, memory.RATING_HARD, memory.RATING_GOOD,
                     memory.RATING_EASY):
        raise ValueError('grade must be 1 (again), 2 (hard), 3 (good) or 4 (easy)')
    now = now_ts() if now is None else now
    updated = _next_state(card, grade, now)
    due_at, interval = memory.due_time(updated, desired_retention=DESIRED_RETENTION)
    card.stability = updated['stability']
    card.difficulty = updated['difficulty']
    card.reps = updated['reps']
    card.lapses = updated['lapses']
    card.last_review_at = updated['last_review']
    card.last_grade = grade
    card.due_at = due_at
    card.state = _display_state(updated['reps'], grade)
    card.updated_at = now
    return {'due_at': due_at, 'interval_seconds': interval,
            'stability': card.stability, 'difficulty': card.difficulty,
            'reps': card.reps, 'lapses': card.lapses, 'state': card.state,
            'last_review_at': card.last_review_at, 'last_grade': grade}


def grade_preview(card: Flashcard, now: float | None = None) -> dict:
    """What each grade would produce, without touching the card.

    This is what lets the UI put the consequence on the button ("Good · 3d"): grading is
    only honest when the learner can see what the choice buys. Each grade is simulated with
    the same pure FSRS-6 update the real review uses, so the label cannot drift from the
    schedule.
    """
    now = now_ts() if now is None else now
    out: dict[str, dict] = {}
    for grade, name in ((1, 'again'), (2, 'hard'), (3, 'good'), (4, 'easy')):
        updated = _next_state(card, grade, now)
        due_at, interval = memory.due_time(updated, desired_retention=DESIRED_RETENTION)
        out[name] = {'grade': grade, 'due_at': due_at, 'interval_seconds': interval,
                     'label': interval_label(interval)}
    return out


def interval_label(seconds: float) -> str:
    """A compact human interval: ``10m``, ``5h``, ``3d``, ``2mo``."""
    seconds = max(0.0, float(seconds))
    minutes = seconds / 60.0
    if minutes < 60:
        return f'{max(1, round(minutes))}m'
    hours = minutes / 60.0
    if hours < 24:
        return f'{max(1, round(hours))}h'
    days = hours / 24.0
    if days < 30:
        return f'{max(1, round(days))}d'
    months = days / 30.0
    if months < 12:
        return f'{max(1, round(months))}mo'
    return f'{max(1, round(days / 365.0))}y'


# ------------------------------------------------------------------ session + stats

def build_session(cards: list[Flashcard], limit: int | None = None) -> list[Flashcard]:
    """Due cards, interleaved across concepts.

    Rule: group the due cards by concept (each group in ``due_at`` order), order the groups
    by their earliest due card, then take one card from each group in turn. With two
    concepts due, the first cards alternate instead of running a whole concept before the
    next -- massed practice is the thing spaced repetition exists to avoid. The trade-off is
    explicit: a later-due card from one concept can precede an earlier-due card from another,
    because alternation is worth more than a strict global due order within a session.
    """
    groups: dict[str, list[Flashcard]] = defaultdict(list)
    for card in sorted(cards, key=lambda c: (c.due_at, c.created_at, c.id)):
        groups[card.concept_id].append(card)
    order = sorted(groups, key=lambda cid: groups[cid][0].due_at)
    out: list[Flashcard] = []
    while True:
        progressed = False
        for concept_id in order:
            group = groups[concept_id]
            if group:
                out.append(group.pop(0))
                progressed = True
                if limit is not None and len(out) >= limit:
                    return out
        if not progressed:
            return out


def deck_stats(cards: list[Flashcard], now: float | None = None) -> dict:
    """Deck-level statistics, computed from the cards themselves (decks are small).

    ``retention_rate`` is ``1 - lapses/reviews`` across the deck: the share of graded
    reviews that were recalled. It is an aggregate proxy from stored counters, not a
    per-interval retention measurement -- and it is labelled as such wherever it surfaces.
    """
    now = now_ts() if now is None else now
    end_of_day = (int(now // 86400) + 1) * 86400
    reviews = sum(card.reps or 0 for card in cards)
    lapses = sum(card.lapses or 0 for card in cards)
    due_now = [c for c in cards if c.due_at <= now]
    future = sorted(c.due_at for c in cards if c.due_at > now)
    return {
        'total': len(cards),
        'learned': sum(1 for c in cards if (c.reps or 0) > 0),
        'due_now': len(due_now),
        'due_today': sum(1 for c in cards if c.due_at <= end_of_day),
        'reviews': reviews,
        'lapses': lapses,
        'retention_rate': (round(1 - lapses / reviews, 4) if reviews else None),
        'next_due_at': (future[0] if future else None),
        'next_due_in_seconds': (max(0, round(future[0] - now)) if future else None),
        'next_due_label': (interval_label(future[0] - now) if future else None),
    }


# ------------------------------------------------------------------ serialisation

def card_json(card: Flashcard, now: float | None = None) -> dict:
    now = now_ts() if now is None else now
    return {
        'id': card.id, 'concept_id': card.concept_id, 'kind': card.kind,
        'front': card.front, 'back': card.back, 'hint': card.hint or '',
        'tags': list(card.tags or []), 'source': dict(card.source or {}),
        'state': card.state,
        'due_at': card.due_at, 'due_iso': iso(card.due_at), 'due_now': card.due_at <= now,
        'stability': card.stability, 'difficulty': card.difficulty,
        'reps': card.reps or 0, 'lapses': card.lapses or 0,
        'last_review_at': card.last_review_at, 'last_review_iso': iso(card.last_review_at),
        'last_grade': card.last_grade,
        'created_at': card.created_at, 'updated_at': card.updated_at,
    }


# ------------------------------------------------------------------ interchange

_EXPORT_COLUMNS = ('front', 'back', 'hint', 'kind', 'concept_id', 'tags', 'source')


def export_cards(cards: list[Flashcard], fmt: str = 'json') -> tuple[str, str]:
    """(body, media_type) for a JSON or CSV export, so a deck is never locked in."""
    rows = [card_json(card) for card in cards]
    if fmt == 'csv':
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(_EXPORT_COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow({key: (','.join(row[key]) if key == 'tags'
                                   else (json.dumps(row[key]) if key == 'source' else row[key]))
                             for key in _EXPORT_COLUMNS})
        return buffer.getvalue(), 'text/csv'
    payload = {'format': 'luminfest-flashcards', 'version': 1, 'exported_at': now_ts(),
               'count': len(rows), 'cards': rows}
    return json.dumps(payload, ensure_ascii=False), 'application/json'


def parse_import(body: bytes, content_type: str) -> list[dict]:
    """Parse an interchange payload into raw card dicts, raising ValueError if malformed.

    Both export formats round-trip: a JSON export's ``cards`` array and the CSV export's
    rows are each accepted here.
    """
    text = body.decode('utf-8-sig', errors='replace').strip()
    if not text:
        return []
    if 'csv' in (content_type or '') or (not text.startswith('{') and not text.startswith('[')):
        rows = list(csv.DictReader(io.StringIO(text)))
        out = []
        for row in rows:
            out.append({'front': row.get('front', ''), 'back': row.get('back', ''),
                        'hint': row.get('hint') or None, 'kind': (row.get('kind') or 'basic'),
                        'concept_id': row.get('concept_id', ''),
                        'tags': [t for t in (row.get('tags') or '').split(',') if t],
                        'source': _parse_source(row.get('source'))})
        return out
    payload = json.loads(text)
    if isinstance(payload, dict):
        payload = payload.get('cards', [])
    if not isinstance(payload, list):
        raise ValueError('import payload must be a list of cards or {"cards": [...]}')
    return [row for row in payload if isinstance(row, dict)]


def _parse_source(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip().startswith('{'):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except ValueError:
            return {}
    return {}
