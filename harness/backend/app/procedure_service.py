"""Resolve the real assets a lesson can use, compile the procedure, and persist the run.

The compiler in :mod:`app.harness.teaching.procedure` is deliberately pure: it decides
from an inventory it is handed. This module builds that inventory from the things that
actually exist on this instance - the learner's own course, its authored lesson blocks,
the bundled playground catalogue, the curated video allowlist and the symbolic maths
engine - and owns the database row that remembers how far the learner got.

Three boundaries are enforced here and nowhere else.

**The inventory is honest.** An asset is reported available only when it can actually be
delivered: a deck only when there is an authored lesson to build one from, a video only
when a concept-specific entry is curated for this course, a simulation only when a
first-party interactive is genuinely bound to the concept. A missing asset becomes a
*reason* the compiler publishes, not a silently empty field.

**Only mathematics gets a symbolic figure.** ``mathkit.template_for`` will happily return
a generic quadratic for a physics concept. Presenting that as "acceleration" is exactly
the class of confident fabrication the rest of this project exists to prevent, so the
resolver refuses it for every non-mathematics subject and says why.

**The run is a plan, not evidence.** Advancing a block records that the learner did the
activity. Mastery still moves only through the question route and the playground's own
outcome route. Nothing in this module writes to ``State`` or ``Attempt``.
"""

from __future__ import annotations

import re
import time
from dataclasses import replace
from typing import Any, Mapping, Sequence

from sqlalchemy import func, select

from . import courses
from .curriculum import course_concepts, course_questions
from .db import Message, ProcedureRun, Project, State, UserPreference, now_ts
from .harness.playground import catalogue
from .harness.teaching import (ConceptFacts, ProcedureAssets, build_evidence,
                               compile_procedure, concept_facts, default_profile,
                               procedure_hash)

__all__ = ['UnknownConcept', 'advance_run', 'assets_for', 'compile_for', 'concept_title_for',
           'current_run', 'deck_cursor', 'deck_section_count', 'materialize',
           'prompt_context', 'recent_kinds', 'run_to_dict', 'set_deck_cursor', 'start_run']


class UnknownConcept(Exception):
    """The concept is not in the learner's own course."""


#: Words too common to prove that a game and a concept are about the same thing. Kept
#: small on purpose: an aggressive stoplist is how a matcher starts agreeing with itself.
_STOPWORDS = frozenset({
    'the', 'and', 'for', 'with', 'from', 'into', 'that', 'this', 'are', 'was', 'has',
    'its', 'their', 'how', 'why', 'what', 'when', 'where', 'using', 'use', 'used',
    'between', 'versus', 'total', 'unit', 'units', 'basics', 'intro', 'introduction',
    'explore', 'exploring', 'model', 'models', 'topic', 'concept',
})

_WORD = re.compile(r"[a-z0-9']+")


def _stem(word: str) -> str:
    """A deliberately crude stemmer: enough to match "sorting" to "sort".

    A real stemmer is a dependency and a second vocabulary to audit. Both sides of every
    comparison go through this function, so consistency matters more than linguistic
    correctness - "analysis" and "analyses" both reduce to something stable, which is all
    the matcher needs.
    """
    if len(word) > 5 and word.endswith('ing'):
        return word[:-3]
    if len(word) > 4 and word.endswith('es'):
        return word[:-2]
    if len(word) > 3 and word.endswith('s'):
        return word[:-1]
    return word


def _tokens(text: str) -> set[str]:
    return {_stem(word) for word in _WORD.findall((text or '').lower())
            if len(word) > 2 and word not in _STOPWORDS}


def _match_game(lesson: Mapping[str, Any], course_id: str) -> dict[str, Any] | None:
    """The first-party game that covers this concept, or ``None``.

    The rule is containment, not overlap: every significant word of the *concept* must
    appear in the game's own concept line or tags. That direction matters. Scoring by
    overlap once bound "determinants of supply and demand" to "determinants of price
    elasticity of demand" - two different concepts that share two words - and a lesson
    that opens the wrong simulation is worse than one that opens none.

    A false negative costs an interactive; a false positive teaches the wrong idea.
    """
    concept_tokens = _tokens(str(lesson.get('title') or '') + ' '
                             + ' '.join(str(k) for k in (lesson.get('keywords') or [])))
    if not concept_tokens:
        return None
    best: tuple[tuple[int, int, str], dict[str, Any]] | None = None
    for game in catalogue.by_course(course_id):
        game_tokens = _tokens(str(game.get('concept') or '') + ' '
                              + ' '.join(str(t) for t in (game.get('tags') or [])))
        if not concept_tokens <= game_tokens:
            continue
        # Prefer the most specific game: fewer extra words, then the shorter title, then
        # the slug - a deterministic tie-break, never dict order.
        key = (len(game_tokens - concept_tokens), len(str(game.get('title') or '')),
               str(game.get('slug') or ''))
        if best is None or key < best[0]:
            best = (key, dict(game))
    return best[1] if best else None


def _sentences(text: str, limit: int = 4, width: int = 220) -> list[str]:
    parts = [part.strip() for part in re.split(r'(?<=[.!?])\s+', text or '') if part.strip()]
    return [part[:width] for part in parts[:limit]]


def _steps(text: str, limit: int = 5) -> list[str]:
    lines = [line.strip(' -•\t') for line in (text or '').splitlines() if line.strip()]
    if len(lines) <= 1:
        return _sentences(text, limit=limit)
    return [line[:220] for line in lines[:limit]]


def _deck_sections(lesson: Mapping[str, Any], title: str) -> tuple[dict[str, Any], ...]:
    """The exact slides a deck for this concept will contain.

    Built from the lesson's own blocks, never from a model: the deck is a rendering of
    authored material, so the procedure can promise "these four slides" and be right.
    Reflections are left out on purpose - they are prompts for the learner, not content
    to present - and the deck is capped at six slides, because a lesson opener that takes
    longer than five minutes is no longer an opener.
    """
    sections: list[dict[str, Any]] = []
    concepts = 0
    for block in lesson.get('blocks') or []:
        if not isinstance(block, Mapping):
            continue
        kind = str(block.get('kind') or '')
        body = str(block.get('body') or '').strip()
        if not body:
            continue
        if kind == 'concept':
            concepts += 1
            heading = title if concepts == 1 else f'Key idea {concepts}'
            bullets = _sentences(body, limit=3)
        elif kind == 'worked_example':
            heading = 'Worked example'
            bullets = _steps(body, limit=4)
        elif kind == 'retrieval':
            heading = 'Check yourself'
            bullets = _sentences(body, limit=2)
        else:
            continue
        if bullets:
            sections.append({'heading': heading, 'bullets': bullets,
                             'notes': body[:600]})
        if len(sections) >= 6:
            break
    return tuple(sections)


def _deck_image(settings, title: str, lesson_id: str = '') -> tuple[dict[str, Any] | None, str]:
    """One licence-cleared picture for this deck, or the reason there is none.

    The deck used to be text only, which made every lesson look like a mock-up. This
    goes through the same ``media.acquire`` pipeline the textbook illustrator uses - one
    searcher, one licence gate, one content-addressed cache - so the picture is either
    cleared and attributed or absent. Nothing is invented: an offline instance, a
    disabled network or a query nothing clears all return a *reason*, which the client
    can show instead of an empty frame.

    The shipped pack is asked first. On the desktop build the network is off by policy, so
    ``acquire`` can only ever answer ``network_disabled``; the pack is what turns that from
    "no picture, ever" into "the picture this build was shipped with". The live search stays
    as the fallback for an instance that has media enabled and a concept the pack does not
    cover.
    """
    from .harness import media
    shipped = media.shipped_for(settings, lesson_id)
    if shipped is not None:
        return _deck_image_payload(shipped), ''
    query = ' '.join(str(title or '').split())[:200]
    if not query:
        return None, 'This concept has no title to search a picture for.'
    try:
        # ``find_image``, not ``acquire``: it is the concept-facing entry point, so it applies
        # the same title-widening the curator does and a deck for "Blood vessels and their
        # adaptation" is not stuck on a query the relevance gate can only reject.
        payload = media.find_image(settings, query, alt_text=f'Illustration for {title}')
    except Exception as exc:   # noqa: BLE001 - a failed search must not break the deck
        return None, f'The image search failed ({type(exc).__name__}); the deck is complete without it.'
    outcome = str(payload.get('outcome') or '')
    asset = payload.get('asset') or {}
    if outcome not in ('downloaded', 'hit_deduplicated') or not asset.get('sha256'):
        return None, (f'No licence-cleared picture for {title!r} '
                      f'(search outcome: {outcome or "unknown"}).')
    return _deck_image_payload(asset), ''


def _deck_image_payload(asset: Mapping[str, Any]) -> dict[str, Any]:
    """The slide-shaped view of one manifest row.

    Delegates to ``media.asset_payload`` rather than spelling the fields out again: the
    narrated presentation and the textbook build the same view, and two copies of "what the
    client is told about a picture" is how one of them ends up shipping without a credit.
    """
    from .harness import media
    return media.asset_payload(asset)


def _worked_example(lesson: Mapping[str, Any]) -> Mapping[str, Any] | None:
    for index, block in enumerate(lesson.get('blocks') or []):
        if isinstance(block, Mapping) and block.get('kind') == 'worked_example':
            body = str(block.get('body') or '').strip()
            if body:
                return {'body': body[:1600], 'block_index': index}
    return None


def _video(course_id: str, concept_id: str, settings) -> tuple[dict[str, Any] | None, str]:
    """The curated video for this concept, or the reason there is not one.

    Read from the allowlist without verifying embeddability, because compiling a lesson
    must not make a network call. ``verify_on_open`` is carried into the block so the
    delivery path checks the provider before showing a player; an unverifiable video
    degrades to its watch link rather than an empty frame.
    """
    from .harness import video as video_module
    try:
        table = video_module.load_allowlist(settings)
    except Exception:   # noqa: BLE001 - a broken allowlist must not break the lesson
        return None, ('The video allowlist could not be read, so no video can be '
                      'promised for this concept.')
    rows = [row for row in (table.get(course_id) or [])
            if isinstance(row, Mapping) and str(row.get('concept_id')) == concept_id]
    if not rows:
        return None, ('No verified, concept-specific video is curated for this concept. '
                      'A generic provider link is a reference, not a lesson, so it is '
                      'not offered as one.')
    try:
        cards = video_module.resolve(settings, course_id, concept_id, verify_remote=False)
    except Exception:   # noqa: BLE001
        cards = []
    usable = [card for card in cards if not card.get('withheld_reason')]
    if not usable:
        reason = next((str(card.get('withheld_reason')) for card in cards
                       if card.get('withheld_reason')), '')
        return None, (reason or 'The curated video for this concept was withheld by the '
                                'licence gate.')
    card = usable[0]
    return ({'provider': str(card.get('provider') or ''),
             'title': str(card.get('title') or ''),
             'channel': str(card.get('channel') or ''),
             'watch_url': str(card.get('watch_url') or ''),
             'embed_url': str(card.get('embed_url') or ''),
             'licence_class': str(card.get('licence_class') or 'embed_only'),
             'attribution': str(card.get('attribution') or card.get('channel') or ''),
             'why': str(card.get('why_this_video') or '')[:300]}, '')


def _simulation(lesson: Mapping[str, Any], course_id: str,
                subject_kind: str) -> tuple[dict[str, Any] | None, str]:
    """A first-party interactive bound to this concept, or the reason there is none.

    A playground game comes first because it is observable: it reports the answer the
    learner committed to, so its outcome can move mastery. The symbolic engine's figure
    is the fallback for mathematics only - it is a real first-party interactive but it
    reports nothing, and it is not valid for a concept whose subject is not mathematics.
    """
    game = _match_game(lesson, course_id)
    if game is not None:
        slug = str(game.get('slug') or '')
        return ({'mode': 'playground', 'slug': slug,
                 'title': str(game.get('title') or 'Interactive'),
                 'observable': True,
                 'play_url': f'/api/v1/playground/games/{slug}/html',
                 'objective': str(game.get('learning_objective') or ''),
                 'prompt': str(game.get('prompt') or ''),
                 'minutes': int(game.get('minutes') or 5)}, '')
    if subject_kind != 'mathematics':
        return None, ('No first-party interactive is bound to this concept. The symbolic '
                      'engine is valid only for mathematics, and drawing a generic '
                      'function plot for this subject would present a model as the '
                      'phenomenon itself.')
    from .mathkit import build as build_simulation
    from .mathkit import template_for
    try:
        spec = template_for(lesson)
        payload = build_simulation(spec)
    except Exception as exc:   # noqa: BLE001 - an unbuildable figure is a reason, not a crash
        return None, (f'The symbolic engine could not build a figure for this concept '
                      f'({type(exc).__name__}); no interactive is offered rather than a '
                      'broken one.')
    expression = payload.get('expression') or {}
    return ({'mode': 'exploratory', 'kind': str(spec.kind), 'title': str(spec.title),
             'observable': False,
             'expression': str(expression.get('substituted') or ''),
             'parameters': list(payload.get('parameters') or [])[:6],
             'objective': str(spec.objective or ''),
             'prompt': 'Predict what happens to the figure when you change one control, '
                       'then change it and check your prediction.'}, '')


def _resolve_lesson_id(concepts: Mapping[str, Any], concept_id: str) -> str:
    """Accept either namespace and return the authored-lesson id.

    A lesson id (``fractions``) and a graph node id (``fraction_equivalence``) name the
    same concept, and a client may hold either. The asset resolver reads lesson blocks,
    which only exist under the lesson id, so the translation happens exactly once here
    rather than in every lookup.
    """
    if concept_id in concepts:
        return concept_id
    for key, entry in concepts.items():
        if str((entry or {}).get('graph_id') or '') == concept_id:
            return key
    raise UnknownConcept(concept_id)


def _lesson_key(user, concept_id: str) -> str:
    """The lesson id for a concept the caller may name either way, or the input unchanged.

    A run has to be looked up by the *same* key it was stored under, and a client may ask
    about ``fractions`` while the compiled plan was filed under ``fraction_equivalence``
    (or the reverse). Without this normalisation the lookup misses, the caller silently
    gets a freshly compiled plan, and the learner's progress never reaches the prompt -
    the lesson restarts on every turn while looking perfectly healthy in the response.
    """
    try:
        return _resolve_lesson_id(course_concepts(courses.enrolled_for(user).id), concept_id)
    except Exception:   # noqa: BLE001 - an unknown concept falls through to "no run"
        return concept_id


def assets_for(concept_id: str, *, course_id: str, graph, settings,
               subject_kind: str = 'mathematics') -> ProcedureAssets:
    """Everything this instance can deliver for this concept, with the reasons it cannot."""
    concepts = course_concepts(course_id)
    lesson_id = _resolve_lesson_id(concepts, concept_id)
    lesson = dict(concepts.get(lesson_id) or {})
    if not lesson:
        raise UnknownConcept(concept_id)
    node_id = str(lesson.get('graph_id') or lesson_id)
    node = graph.nodes.get(node_id) if graph is not None else None
    title = str(lesson.get('title') or getattr(node, 'title', '') or lesson_id)

    reasons: dict[str, str] = {}
    deck = _deck_sections(lesson, title)
    if not deck:
        reasons['deck'] = ('This concept has no authored lesson blocks, so there is '
                           'nothing to build a deck from.')
    else:
        # One real picture on the opening slide. The deck block's sections are what
        # the client renders, so the image rides on the section, not on the HTML
        # twin: every artifact route is bearer-protected and the native client is
        # the one that can fetch the bytes. Offline or nothing-cleared leaves the
        # deck exactly as it was, with a published reason.
        image, image_reason = _deck_image(settings, title, lesson_id)
        if image is None:
            reasons['deck_image'] = image_reason
            # The reason rides on the opening section, exactly where the picture
            # would have been. ``reasons`` is an asset-level dict the client never
            # sees; ``sections`` is what it renders, so a client can say "picture
            # unavailable: <why>" instead of showing an empty frame it cannot
            # explain. Co-locating them also means the one place that reads the
            # picture is the one place that reads why there is none.
            deck = tuple([{**deck[0], 'image_unavailable': image_reason}, *deck[1:]])
        else:
            deck = tuple([{**deck[0], 'image': image}, *deck[1:]])
    simulation, simulation_reason = _simulation(lesson, course_id, subject_kind)
    if simulation is None:
        reasons['simulation'] = simulation_reason
    video, video_reason = _video(course_id, lesson_id, settings)
    if video is None:
        reasons['video'] = video_reason
    example = _worked_example(lesson)
    if example is None:
        reasons['worked_example'] = ('This concept has no authored worked example, so a '
                                     'solved instance cannot be shown without inventing '
                                     'one.')

    prompts = tuple(str(block.get('body') or '')[:800]
                    for block in lesson.get('blocks') or []
                    if isinstance(block, Mapping) and block.get('kind') == 'retrieval')
    bank = course_questions(course_id)
    practice_count = sum(1 for question in bank.values()
                         if str(question.get('concept_id')) == lesson_id)

    prerequisites: tuple[str, ...] = ()
    dependants: tuple[str, ...] = ()
    if graph is not None and node_id in graph.nodes:
        prerequisites = tuple(str(graph.nodes[pid].title) for pid in graph.parents(node_id)
                              if pid in graph.nodes)[:3]
        dependants = tuple(str(graph.nodes[cid].title) for cid in graph.children(node_id)
                           if cid in graph.nodes)[:3]

    return ProcedureAssets(
        concept_id=lesson_id, concept_title=title, course_id=course_id,
        deck_sections=deck, simulation=simulation, video=video,
        worked_example=example, practice_prompts=prompts,
        practice_count=practice_count, prerequisites=prerequisites,
        dependants=dependants, reasons=reasons)


def _speak_lesson_id(procedure, lesson_id: str, lesson_title: str = ''):
    """Re-label a compiled plan onto the authored-lesson namespace.

    The compiler works in graph-node ids and graph-node titles, which is what the
    knowledge graph and the evidence record are keyed by. Everything that *persists* or is
    *addressed by a client* - the question bank, the chat history, the run row, the card
    the learner reads - is the authored lesson. Left unaligned, the same concept had two
    ids (a run filed under ``fraction_equivalence`` was invisible to a request for
    ``fractions``, so progress silently vanished between turns and the lesson restarted)
    and two titles ("Fraction equivalence" on a card for the lesson the course calls
    "Fractions and equivalent quantities").

    The graph id stays an accepted alias on the way in; the authored lesson is what comes
    out. ``lesson_title`` is the resolver's own title for the concept and wins, because it
    is the one the learner will see on the lesson they are actually reading.
    """
    if not lesson_title and procedure.concept_id == lesson_id:
        return procedure
    blocks = tuple(
        replace(block, artifact={**dict(block.artifact), 'concept_id': lesson_id})
        if block.artifact.get('concept_id') else block
        for block in procedure.blocks)
    return replace(procedure, concept_id=lesson_id,
                   concept_title=lesson_title or procedure.concept_title,
                   blocks=blocks)


def _state_for(db, user, concept_id: str, node_id: str, parents: Sequence[str]) -> tuple[dict, dict]:
    wanted = {concept_id, node_id, *parents}
    rows = {row.concept_id: (row.data or {})
            for row in db.scalars(select(State).where(State.user_id == user.id,
                                                      State.concept_id.in_(wanted)))}
    return (rows.get(node_id) or rows.get(concept_id) or {},
            {parent: rows.get(parent, {}) for parent in parents})


def _session_minutes(db, user, concept_id: str, now: float) -> float:
    since = now - 3 * 3600
    first = db.scalar(select(func.min(Message.created_at)).where(
        Message.user_id == user.id, Message.concept_id == concept_id,
        Message.created_at >= since))
    return max(0.0, (now - first) / 60) if first else 0.0


def recent_kinds(db, user, concept_id: str, *, within_hours: float = 24.0) -> tuple[str, ...]:
    """Input activities the learner actually *finished* on this concept recently.

    Bounded to the last day on purpose. "Do not repeat the deck" is a same-day rule -
    two sessions on Tuesday should not both open with the same four slides. Across days
    the deck may be the right opener again, and suppressing it for a week would send a
    struggling learner to a video that does not exist for their concept.

    Two details decide whether this rule helps or sabotages the lesson. It reads
    ``completed``, not ``blocks``: a plan that *proposed* a deck and was abandoned after
    the diagnostic never showed one, so the deck has not been seen. And a block counts
    only when its outcome was ``done``; a learner who declined the deck has not had it.
    Reading the proposal instead made starting a lesson change the next lesson's shape,
    so the same learner got a different plan on every retry.
    """
    cutoff = now_ts() - within_hours * 3600
    rows = list(db.scalars(select(ProcedureRun).where(
        ProcedureRun.user_id == user.id, ProcedureRun.concept_id == concept_id,
        ProcedureRun.updated_at >= cutoff).order_by(ProcedureRun.updated_at.desc()).limit(4)))
    kinds: list[str] = []
    for row in rows:
        for entry in row.completed or []:
            if not isinstance(entry, Mapping) or entry.get('outcome') != 'done':
                continue
            kind = str(entry.get('kind') or '')
            if kind and kind not in kinds:
                kinds.append(kind)
    return tuple(kinds)


def compile_for(db, user, concept_id: str, *, settings,
                minutes_budget: int | None = None):
    """Compile this learner's lesson on this concept. Returns ``(procedure, evidence)``."""
    spec = courses.enrolled_for(user)
    graph = courses.graph_for(spec.id)
    concepts = course_concepts(spec.id)
    lesson_id = _resolve_lesson_id(concepts, concept_id)
    subject_kind = str(getattr(spec, 'subject_kind', '') or 'mathematics')
    facts = concept_facts(lesson_id, graph=graph, subject_kind=subject_kind)
    assets = assets_for(lesson_id, course_id=spec.id, graph=graph, settings=settings,
                        subject_kind=subject_kind)
    node_id = str(facts.id)
    parents = tuple(graph.parents(node_id)) if node_id in graph.nodes else ()
    state, parent_states = _state_for(db, user, lesson_id, node_id, parents)
    now = time.time()
    project = db.scalar(select(Project).where(Project.user_id == user.id,
                                              Project.concept_id == lesson_id))
    next_check = state.get('next_check')
    evidence = build_evidence(
        facts, state, parent_states=parent_states, now=now,
        session_minutes=_session_minutes(db, user, lesson_id, now),
        project_status=project.status if project else 'unknown',
        top_error=str((next_check or {}).get('category') or '')
        if isinstance(next_check, Mapping) else '',
        recent_moves=(), unit_coverage=0.0,
        mastery_threshold=default_profile().difficulty.mastery_threshold)
    budget = minutes_budget if minutes_budget is not None else int(
        getattr(user, 'daily_minutes', 20) or 20)
    procedure = compile_procedure(
        facts, evidence, assets, default_profile(), minutes_budget=budget,
        recent_kinds=recent_kinds(db, user, lesson_id))
    return _speak_lesson_id(procedure, lesson_id,
                            assets.concept_title or procedure.concept_title), evidence


def current_run(db, user, concept_id: str) -> ProcedureRun | None:
    """The learner's open lesson on this concept, under either namespace."""
    return db.scalar(select(ProcedureRun).where(
        ProcedureRun.user_id == user.id,
        ProcedureRun.concept_id == _lesson_key(user, concept_id),
        ProcedureRun.status == 'active').order_by(ProcedureRun.updated_at.desc()))


def deck_section_count(db, user, concept_id: str) -> int:
    """How many slides the running lesson's deck has, or 0 when there is no deck.

    Read from the run rather than from the authored lesson: the run is what the learner
    is actually looking at, and a recompile could change the slide count while the open
    sheet still shows the old deck.
    """
    run = current_run(db, user, concept_id)
    if run is None:
        return 0
    for block in run.blocks or []:
        if not isinstance(block, Mapping) or block.get('kind') != 'deck':
            continue
        artifact = block.get('artifact') or {}
        sections = artifact.get('sections') if isinstance(artifact, Mapping) else None
        return len(sections or [])
    return 0


def deck_cursor(db, user, concept_id: str) -> dict[str, Any]:
    """Which slide of this concept's deck the learner is on.

    The cursor is UI state, not progress, so it lives in ``user_preferences.ui`` rather
    than on the run: no migration, and it survives a restart, which is what lets a deck
    reopen where the learner left it. It is stored under the authored-lesson key and
    reported under the caller's namespace, so a client addressing ``fraction_equivalence``
    and one addressing ``fractions`` see the same cursor.
    """
    key = _lesson_key(user, concept_id)
    preference = db.get(UserPreference, user.id)
    stored = dict(((preference.ui if preference else {}) or {}).get('deck_cursor') or {})
    count = deck_section_count(db, user, key)
    slide = int(stored.get('slide') or 0) if str(stored.get('concept_id') or '') == key else 0
    if count:
        slide = max(0, min(count - 1, slide))
    else:
        slide = max(0, slide)
    return {'concept_id': concept_id, 'slide': slide, 'count': count,
            'at': float(stored.get('at') or 0.0)}


def set_deck_cursor(db, user, concept_id: str, slide: int) -> dict[str, Any]:
    """Move the learner's deck to a slide, clamped to the deck that exists.

    Clamping is not a courtesy: an unclamped ``goto 9`` on a four-slide deck would store a
    position the client cannot render, and the next ``next`` would compute from a slide
    that is not on screen. Out of range lands on the nearest real slide.
    """
    key = _lesson_key(user, concept_id)
    count = deck_section_count(db, user, key)
    target = int(slide)
    if count:
        target = max(0, min(count - 1, target))
    else:
        target = max(0, target)
    preference = db.get(UserPreference, user.id)
    if preference is None:
        preference = UserPreference(user_id=user.id)
        db.add(preference)
    ui = dict(preference.ui or {})
    ui['deck_cursor'] = {'concept_id': key, 'slide': target, 'at': now_ts()}
    preference.ui = ui
    preference.updated_at = now_ts()
    db.flush()
    return {'concept_id': concept_id, 'slide': target, 'count': count,
            'at': ui['deck_cursor']['at']}


def start_run(db, user, procedure) -> ProcedureRun:
    """Persist the plan, or return the identical one already running.

    Starting the same plan twice must not create two rows: the learner would then have
    two half-finished lessons. A *different* plan (new evidence, new budget) is a new
    row and abandons the old one, because resuming a lesson whose shape changed is worse
    than starting the changed one.
    """
    digest = procedure_hash(procedure)
    existing = db.scalar(select(ProcedureRun).where(
        ProcedureRun.user_id == user.id,
        ProcedureRun.concept_id == procedure.concept_id,
        ProcedureRun.procedure_hash == digest))
    if existing is not None and existing.status == 'active':
        return existing
    if existing is not None:
        # The same plan was run before and finished (or was abandoned). Restarting it
        # resets the progress on the same row rather than creating a second one: the
        # unique key is what makes "start" idempotent, and progress is not evidence, so
        # there is no history worth preserving here.
        existing.status = 'active'
        existing.completed = []
        existing.blocks = [block.to_dict() for block in procedure.blocks]
        existing.skipped = [dict(row) for row in procedure.skipped]
        existing.rationale = procedure.rationale[:1000]
        existing.budget_minutes = procedure.budget_minutes
        existing.total_minutes = procedure.total_minutes
        existing.updated_at = now_ts()
        return existing
    for row in db.scalars(select(ProcedureRun).where(
            ProcedureRun.user_id == user.id,
            ProcedureRun.concept_id == procedure.concept_id,
            ProcedureRun.status == 'active')):
        row.status = 'abandoned'
        row.updated_at = now_ts()
    run = ProcedureRun(
        user_id=user.id, concept_id=procedure.concept_id,
        course_id=procedure.course_id, procedure_hash=digest,
        profile_name=procedure.profile_name,
        budget_minutes=procedure.budget_minutes,
        total_minutes=procedure.total_minutes,
        blocks=[block.to_dict() for block in procedure.blocks],
        skipped=[dict(row) for row in procedure.skipped],
        rationale=procedure.rationale[:1000],
        completed=[], status='active')
    db.add(run)
    db.flush()
    return run


def advance_run(db, run: ProcedureRun, order: int, *, outcome: str = 'done',
                seconds: int | None = None, note: str = '') -> ProcedureRun:
    """Mark one block done (or skipped) and return the run.

    Refuses an unknown block, a block that is already complete, and a run that is no
    longer active. Each refusal is a real client bug - a double tap, a stale screen - and
    silently accepting it would make the progress record lie about how far the learner
    got.
    """
    if run.status != 'active':
        raise ValueError(f'This lesson is {run.status}, not active')
    blocks = list(run.blocks or [])
    block = next((row for row in blocks
                  if isinstance(row, Mapping) and int(row.get('order') or 0) == int(order)),
                 None)
    if block is None:
        raise KeyError(f'No block {order} in this lesson')
    completed = list(run.completed or [])
    if any(int(row.get('order') or 0) == int(order) for row in completed):
        raise ValueError(f'Block {order} is already complete')
    if outcome not in {'done', 'skipped'}:
        raise ValueError('outcome must be done or skipped')
    completed.append({'order': int(order), 'kind': str(block.get('kind') or ''),
                      'outcome': outcome, 'at': now_ts(),
                      'seconds': int(seconds) if seconds is not None else None,
                      'note': str(note or '')[:200]})
    run.completed = completed
    run.status = 'completed' if len(completed) >= len(blocks) else 'active'
    run.updated_at = now_ts()
    return run


def materialize(db, user, run: ProcedureRun, settings) -> ProcedureRun:
    """Build the deck this lesson promises, once, and remember its artifact id.

    Lazy in the only sense that matters: a learner who previews a lesson and walks away
    causes no write. Once they start, the deck is built immediately rather than when its
    block comes up, because the deck is the artifact a client wants to preload - the
    learner reads the diagnostic, then the slides. Waiting for the block to become
    current meant the build happened inside an ``advance`` call, which is a slow write
    in the one place a client is trying to move quickly.

    A lesson has at most one deck block by construction (the compiler allows exactly one
    input), so "the deck block that is not yet complete" is unambiguous. The artifact id
    is stored on the block, so a resumed run reopens the same deck instead of a second
    copy, and a second call is a no-op.
    """
    blocks = list(run.blocks or [])
    done = {int(row.get('order') or 0) for row in (run.completed or [])}
    target = next((row for row in blocks if isinstance(row, Mapping)
                   and row.get('kind') == 'deck'
                   and int(row.get('order') or 0) not in done), None)
    if target is None:
        return run
    artifact = dict(target.get('artifact') or {})
    if artifact.get('artifact_id'):
        return run
    sections = [dict(section) for section in (artifact.get('sections') or [])
                if isinstance(section, Mapping)]
    if not sections:
        return run
    from .harness.toolbox import ToolContext, invoke
    spec = courses.enrolled_for(user)
    graph = courses.graph_for(spec.id)
    title = str(artifact.get('concept_title') or run.concept_id).replace('_', ' ')
    ctx = ToolContext(db=db, user=user, settings=settings, graph=graph,
                      course_id=spec.id,
                      subject_kind=str(getattr(spec, 'subject_kind', '') or 'mathematics'))
    result = invoke(ctx, 'generate_slides', {
        'title': f'{title.title()} — lesson deck',
        'sections': sections, 'concept_id': run.concept_id, 'include_pptx': True})
    if not getattr(result, 'ok', False):
        return run
    data = getattr(result, 'data', None) or {}
    artifact_id = str(data.get('artifact_id') or '')
    pptx_file = data.get('pptx_file')
    artifact.update({'artifact_id': artifact_id,
                     'raw_url': str(data.get('raw_url') or ''),
                     # The tool records the twin's file name; a client needs a URL. Without
                     # one the block would carry a reference nothing can resolve.
                     'pptx_file': pptx_file,
                     'pptx_url': (f'/api/v1/sims/{artifact_id}/download/{pptx_file}'
                                  if artifact_id and pptx_file else ''),
                     'slide_count': int(data.get('slides') or len(sections)),
                     'materialized': True})
    updated = {**target, 'artifact': artifact}
    for index, row in enumerate(blocks):
        if isinstance(row, Mapping) and int(row.get('order') or 0) == int(updated['order']):
            blocks[index] = updated
            break
    run.blocks = blocks
    run.updated_at = now_ts()
    return run


def concept_title_for(user, concept_id: str) -> str:
    """The authored title of a concept, or a readable form of its id.

    The run row stores an id, because a title is curriculum content and a stored copy would
    go stale the moment an author renames a lesson. A client, though, needs something to
    put on a card, and ``fraction_equivalence`` rendered through ``capitalized`` is not it.
    """
    try:
        spec = courses.enrolled_for(user)
        title = str((course_concepts(spec.id).get(concept_id) or {}).get('title') or '')
    except Exception:   # noqa: BLE001 - a missing title must not break a response
        title = ''
    return title or concept_id.replace('_', ' ').strip().capitalize()


def run_to_dict(run: ProcedureRun, *, concept_title: str = '') -> dict[str, Any]:
    """The run as the client reads it: the plan, the progress, and the current block.

    ``concept_title`` is passed in rather than looked up: this function takes a row and
    nothing else, which is what makes it safe to call from anywhere. Callers that have a
    user should use :func:`concept_title_for`; a caller that does not gets the id, which is
    still a correct answer to "which concept".
    """
    blocks = [dict(row) for row in (run.blocks or []) if isinstance(row, Mapping)]
    completed = [dict(row) for row in (run.completed or []) if isinstance(row, Mapping)]
    done = {int(row.get('order') or 0) for row in completed}
    current = next((row for row in blocks if int(row.get('order') or 0) not in done), None)
    return {
        'run_id': run.id,
        'concept_id': run.concept_id,
        'concept_title': concept_title or run.concept_id.replace('_', ' ').capitalize(),
        'course_id': run.course_id,
        'hash': run.procedure_hash,
        'status': run.status,
        'budget_minutes': run.budget_minutes,
        'total_minutes': run.total_minutes,
        'blocks': blocks,
        'completed': completed,
        'skipped': [dict(row) for row in (run.skipped or []) if isinstance(row, Mapping)],
        'rationale': run.rationale,
        'current': current,
        'progress': (len(completed) / len(blocks)) if blocks else 0.0,
    }


def _plan_dict(db, user, run: ProcedureRun) -> dict[str, Any]:
    """The run rendered in the shape the prompt renderer expects.

    ``procedure.to_dict()`` and ``run_to_dict()`` are different documents - one is a
    proposal, the other a proposal plus progress. The renderer needs the second but reads
    it with the first's keys, so the translation happens here once rather than as a set of
    ``.get`` fallbacks in the renderer.
    """
    blocks = [dict(row) for row in (run.blocks or []) if isinstance(row, Mapping)]
    return {'enabled': True, 'concept_id': run.concept_id,
            'concept_title': concept_title_for(user, run.concept_id),
            'course_id': run.course_id, 'budget_minutes': run.budget_minutes,
            'total_minutes': run.total_minutes, 'profile': run.profile_name,
            'hash': run.procedure_hash, 'blocks': blocks,
            'skipped': [dict(row) for row in (run.skipped or [])
                        if isinstance(row, Mapping)]}


def prompt_context(db, user, concept_id: str, *, settings) -> tuple[dict[str, Any] | None, tuple[int, ...]]:
    """What the tutor prompt needs: the running plan (or a fresh one) and its progress.

    An active run wins over a recompile. A lesson that changes under the learner because
    a practice item moved the mastery estimate is not a lesson; the new estimate shapes
    the *next* session, not this one.

    When there is no run, the plan is compiled **and started**. That is a write on a read
    path, which needs justifying: without it the sequence re-shuffles between turns. The
    tutor is told it may not add, remove or reorder an activity, and a list that is
    recompiled from fresh evidence on every turn would do exactly that behind its back -
    turn 1 says "block 2 of 4: the deck", the learner reads the deck, and turn 2 says
    "block 2 of 3: the simulation" because the deck no longer qualifies. Starting on
    first contact freezes the sequence at the moment the lesson begins, which is the only
    moment its shape was a decision.

    A failed start degrades to the compiled-but-unpersisted plan rather than failing the
    turn: an unstable plan is a worse lesson, but no lesson at all is a worse answer.
    """
    run = current_run(db, user, concept_id)
    if run is not None:
        return (_plan_dict(db, user, run),
                tuple(int(row.get('order') or 0) for row in (run.completed or [])
                      if isinstance(row, Mapping)))
    try:
        procedure, _ = compile_for(db, user, concept_id, settings=settings)
    except UnknownConcept:
        return None, ()
    try:
        run = start_run(db, user, procedure)
        db.flush()
        return (_plan_dict(db, user, run),
                tuple(int(row.get('order') or 0) for row in (run.completed or [])
                      if isinstance(row, Mapping)))
    except Exception:   # noqa: BLE001 - see the docstring: degrade, do not fail
        return procedure.to_dict(), ()
