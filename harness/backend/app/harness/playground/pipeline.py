"""The generation pipeline: content spec -> validated, stored, playable game.

Three entry points, in increasing order of how much is invented:

:func:`instantiate`
    Take a **bundled** game from the catalogue and make it playable. Nothing is
    generated; the spec was authored by a human and is already validated at load.

:func:`compose`
    Take an **authored** spec - from a teacher, an operator, or :func:`draft` - and
    make it playable. Validated against the archetype's declared schema first.

:func:`draft`
    Ask a configured language model to fill an archetype's schema from a topic, then
    compose the result. This is the part that produces *more* games without a human
    writing each one.

The one rule that makes this safe
---------------------------------
A model is never allowed to write the interaction. It fills a **declared schema** -
the archetype already owns the mechanic, the rendering, the correctness check and
the telemetry - so the worst a bad completion can do is produce content that fails
validation and is refused with a reason. It cannot introduce code, because nothing
in a spec is ever evaluated: the spec is embedded as JSON and read as data. That is
why this pipeline can safely accept machine-authored content at all.

Drafting retries once, feeding the validator's own messages back to the model. The
validator is therefore load-bearing twice over: it is the quality gate and it is the
error channel. A model that cannot produce a valid spec after two attempts gets an
honest failure, not a broken game.

Storage
-------
Everything is stored through :mod:`app.harness.sims_store`, so a generated game is
versioned, validated and served by exactly the same path as a hand-authored one, and
the workbench opens it with no special case. Instantiation is **idempotent**: the
same game at the same spec revision reuses its existing artifact instead of adding a
version, so replaying a game does not fill the store with identical copies. Change
the spec and the hash changes, which is what produces a new version.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

from .. import provider, sims_store
from . import archetypes as archetype_registry
from . import catalogue

#: How many times :func:`draft` will ask the model, feeding validation errors back.
#: Two is deliberate: one attempt is a coin flip, and more than two burns tokens on a
#: model that has demonstrated it cannot follow the schema.
DRAFT_ATTEMPTS = 2

_SLUG_SAFE = re.compile(r'[^a-z0-9]+')


def slugify(text: str, *, prefix: str = 'game') -> str:
    """A stable, URL-safe slug from arbitrary text."""
    cleaned = _SLUG_SAFE.sub('-', (text or '').strip().casefold()).strip('-')
    return f'{prefix}-{cleaned}'[:80] if cleaned else prefix


#: Bumped whenever a change to the runtime or the archetypes changes what a spec
#: renders into. It is part of the revision fingerprint, so a design change retires
#: every stored page instead of leaving the catalogue serving the old one.
#:
#: This exists because of a real trap: the fingerprint used to cover only
#: ``(archetype, spec)``, so a page was reused whenever its *content* was unchanged -
#: even after the renderer had been rewritten underneath it. The result is a
#: catalogue that silently serves the previous design, which looks exactly like the
#: redesign not having happened. "design-2" is the Morandi design system.
RENDER_VERSION = 'design-2'


def spec_hash(archetype_id: str, spec: Mapping[str, Any]) -> str:
    """A content revision fingerprint.

    Canonical JSON - sorted keys, no whitespace - so that two specs which differ only
    in key order hash the same. Anything else would make instantiation non-idempotent
    for cosmetic reasons and mint a new artifact version on every request.

    ``RENDER_VERSION`` is folded in so that a renderer change is a new revision. It is
    constant across specs, so it does not affect idempotence for unchanged content.
    """
    canonical = json.dumps({'archetype': archetype_id, 'spec': spec,
                            'render': RENDER_VERSION},
                           sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def render_game(*, archetype_id: str, spec: Mapping[str, Any], title: str = '',
                instruction: str = '', subject: str = '') -> str:
    """Render one spec to a complete page, refusing an invalid spec."""
    archetype = archetype_registry.get(archetype_id)
    if archetype is None:
        raise ValueError(f'Unknown archetype {archetype_id!r}; registered: '
                         f'{sorted(a.id for a in archetype_registry.all_archetypes())}')
    return archetype_registry.render(archetype, spec, title=title, instruction=instruction,
                                     subject=subject)


def _find_artifact(settings, slug: str, revision: str) -> dict[str, Any] | None:
    """The stored artifact for this game at this content revision, if it exists."""
    for entry in sims_store.list_artifacts(settings, kind='simulation'):
        meta = entry.get('meta') or {}
        if meta.get('playground_slug') == slug and meta.get('spec_hash') == revision:
            return entry
    return None


def _store(settings, *, slug: str, archetype_id: str, spec: Mapping[str, Any],
           title: str, html: str, meta: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and store one rendered game, reusing an identical prior revision."""
    problems = sims_store.validate_html(html, kind='simulation')
    if problems:
        raise ValueError('The rendered game was refused by the artifact store: '
                         + '; '.join(problems))
    revision = spec_hash(archetype_id, spec)
    existing = _find_artifact(settings, slug, revision)
    if existing is not None:
        return {**existing, 'reused': True, 'raw_url': sims_store.raw_url(existing['id'])}
    entry = sims_store.create_artifact(
        settings, kind='simulation', title=title, html=html,
        meta={**dict(meta), 'playground_slug': slug, 'archetype': archetype_id,
              'spec_hash': revision})
    return {**entry, 'reused': False, 'raw_url': sims_store.raw_url(entry['id'])}


def page_args(game: Mapping[str, Any], archetype) -> dict[str, str]:
    """The three strings a page takes from the *game* rather than from the spec.

    They live in one function because two callers need them and they must not drift:
    :func:`instantiate` (the real page) and ``scripts/playground_render_pages.py`` (the
    page the audit and the screenshots see). They did drift - the script rendered with
    the bare spec, so every shared archetype was labelled MATHEMATICS in every artifact
    while the app was correct, and the audit was measuring a page nobody plays.

    ``instruction`` prefers the spec's own "how to play" sentence over the game's prompt.
    Those are two different sentences and the layout contract (L2) requires them to be:
    the header says how the interaction works, ``#prompt`` says what this task asks. The
    first version passed the prompt for both, so half the catalogue printed the same
    sentence twice on one screen.
    """
    spec = game.get('spec') or {}
    task = str(spec.get('prompt') or '').strip()
    for candidate in (str(spec.get('instruction') or '').strip(),
                      str(game.get('prompt') or '').strip()):
        if candidate and candidate != task:
            instruction = candidate
            break
    else:
        instruction = archetype.blurb
    return {
        'title': str(game.get('title') or archetype.title),
        'instruction': instruction,
        'subject': next(iter(game.get('subjects') or ()), ''),
    }


def instantiate(settings, slug: str, *, refresh: bool = False) -> dict[str, Any]:
    """Make a bundled catalogue game playable, returning its artifact and URL.

    ``refresh=True`` re-renders and stores a new version even when the content is
    unchanged - the operator's escape hatch after an archetype's rendering changes.
    """
    game = catalogue.get_game(slug)
    if game is None:
        raise KeyError(slug)
    archetype = archetype_registry.get(str(game['archetype']))
    if archetype is None:  # pragma: no cover - the catalogue withholds these already
        raise ValueError(f'Game {slug!r} names unregistered archetype {game["archetype"]!r}')
    spec = dict(game['spec'])
    html = render_game(archetype_id=archetype.id, spec=spec, **page_args(game, archetype))
    if refresh:
        entry = sims_store.create_artifact(
            settings, kind='simulation', title=game['title'], html=html,
            meta={'playground_slug': slug, 'archetype': archetype.id,
                  'spec_hash': spec_hash(archetype.id, spec), 'refreshed': True})
        return {**entry, 'reused': False, 'raw_url': sims_store.raw_url(entry['id'])}
    return _store(settings, slug=slug, archetype_id=archetype.id, spec=spec,
                  title=game['title'], html=html,
                  meta={'source': 'bundled', 'course_id': game.get('course_id'),
                        'concept': game.get('concept'),
                        'learning_objective': game.get('learning_objective')})


def compose(settings, *, archetype_id: str, spec: Mapping[str, Any], title: str = '',
            instruction: str = '', slug: str = '', source: str = 'authored',
            meta: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Make an authored spec playable. Raises ``ValueError`` with the reasons."""
    archetype = archetype_registry.get(archetype_id)
    if archetype is None:
        raise ValueError(f'Unknown archetype {archetype_id!r}')
    problems = archetype_registry.validate_spec(spec, archetype)
    if problems:
        raise ValueError('The spec does not match the archetype schema: ' + '; '.join(problems))
    resolved_title = title or str(spec.get('title') or archetype.title)
    html = archetype_registry.render(
        archetype, spec, title=resolved_title,
        instruction=instruction or str(spec.get('instruction') or archetype.blurb))
    resolved_slug = slug or slugify(resolved_title, prefix=archetype.id)
    return _store(settings, slug=resolved_slug, archetype_id=archetype.id, spec=spec,
                  title=resolved_title, html=html,
                  meta={'source': source, **dict(meta or {})})


# ------------------------------------------------------------------ the model path


def _draft_system_prompt(archetype, course_ids: list[str]) -> str:
    """The authoring instruction. Strict, because the schema is the contract."""
    schema = json.dumps(archetype.describe()['schema'], indent=2, ensure_ascii=False)
    return (
        'You author content for a teaching game. You do not write any code, markup or '
        'JavaScript: the game engine already exists and you only fill in its content.\n\n'
        f'The interaction is: {archetype.interaction}\n'
        f'What it is for: {archetype.blurb}\n\n'
        'Return ONE JSON object matching this schema exactly. Field names are literal. '
        'Every field marked required must be present. Where a field lists "choices", '
        'the value must be one of them.\n\n'
        f'{schema}\n\n'
        'Rules:\n'
        '- The content must be factually correct for the subject. Check your own '
        'arithmetic and your own science before answering; a game whose right answer is '
        'wrong teaches the wrong thing.\n'
        '- Every task must have exactly one defensible correct answer.\n'
        f'- Use a real course id from: {", ".join(course_ids) or "(none available)"}.\n'
        '- Do not include an "explanation" field that is not in the schema.\n'
        '- Return only the JSON object, with no commentary and no code fences.')


def draft(settings, *, archetype_id: str, topic: str, course_id: str = '',
          difficulty: str = 'core', concept: str = '',
          usage_out: dict | None = None) -> dict[str, Any]:
    """Ask a configured model to fill an archetype's schema, then compose it.

    Returns a structured result rather than raising, because "no model is configured"
    and "the model could not follow the schema" are both ordinary outcomes that the
    caller should be able to report honestly. Nothing is stored unless a spec
    validated.
    """
    archetype = archetype_registry.get(archetype_id)
    if archetype is None:
        return {'ok': False, 'stage': 'lookup', 'problems':
                [f'Unknown archetype {archetype_id!r}'],
                'registered': sorted(a.id for a in archetype_registry.all_archetypes())}
    if not provider.available(settings):
        return {'ok': False, 'stage': 'provider', 'problems': [
            'No language model is configured, so a new spec cannot be drafted. The '
            'bundled games are all playable without one; set an endpoint to author '
            'more.']}
    course_ids = catalogue.courses()
    if course_id and course_id not in course_ids:
        return {'ok': False, 'stage': 'course', 'problems': [
            f'{course_id!r} is not a course any game or pack declares; '
            f'known: {course_ids}']}
    messages = [
        {'role': 'system', 'content': _draft_system_prompt(archetype, course_ids)},
        {'role': 'user', 'content':
            f'Write a {difficulty} game about: {topic}\n'
            + (f'It is for the course {course_id}.\n' if course_id else '')
            + (f'The concept it must teach is: {concept}\n' if concept else '')
            + 'Remember: the schema, the field names, and the allowed choices are literal.'},
    ]
    attempts: list[dict[str, Any]] = []
    for attempt in range(1, DRAFT_ATTEMPTS + 1):
        candidate = provider.chat_json(settings, messages, max_tokens=3000, usage_out=usage_out)
        if not isinstance(candidate, Mapping):
            attempts.append({'attempt': attempt, 'problems': [
                'The model did not return a JSON object.']})
            messages.append({'role': 'user', 'content':
                             'That was not a JSON object. Return only the JSON object.'})
            continue
        problems = archetype_registry.validate_spec(candidate, archetype)
        if not problems:
            try:
                stored = compose(
                    settings, archetype_id=archetype.id, spec=dict(candidate),
                    title=str(candidate.get('title') or topic),
                    instruction=str(candidate.get('instruction') or ''),
                    source='model-drafted',
                    meta={'course_id': course_id or None, 'concept': concept or topic,
                          'difficulty': difficulty, 'drafted_from': topic})
            except ValueError as exc:
                attempts.append({'attempt': attempt, 'problems': [str(exc)]})
                messages.append({'role': 'user', 'content': str(exc)})
                continue
            return {'ok': True, 'stage': 'stored', 'provider': provider.label(settings),
                    'archetype': archetype.id, 'attempts': attempts + [
                        {'attempt': attempt, 'problems': []}],
                    'spec': dict(candidate), 'artifact': stored}
        attempts.append({'attempt': attempt, 'problems': problems})
        messages.append({'role': 'user', 'content':
                         'That spec was rejected. Fix exactly these problems and return '
                         'the whole object again:\n- ' + '\n- '.join(problems)})
    return {'ok': False, 'stage': 'validation', 'provider': provider.label(settings),
            'archetype': archetype.id, 'attempts': attempts,
            'problems': [f'The model could not produce a valid spec in {DRAFT_ATTEMPTS} '
                         'attempts; nothing was stored.']}


def describe(settings=None) -> dict[str, Any]:
    """The pipeline's posture, for the transparency panel."""
    return {
        'stages': [
            'A game is an archetype (the mechanic, written by us) plus a spec (the '
            'content). The archetype is never generated.',
            'A spec is validated against the archetype\'s declared schema before '
            'anything is rendered. Invalid content is refused with its reasons.',
            'A validated spec is rendered to one self-contained, offline page, then '
            'stored through the same artifact store and validator the hand-authored '
            'simulations use.',
            'Instantiation is idempotent per content revision, so replaying a game '
            'reuses its artifact instead of filling the store with copies.',
        ],
        'model_path': {
            'available': provider.available(settings),
            'provider': provider.label(settings) if provider.available(settings) else None,
            'attempts': DRAFT_ATTEMPTS,
            'what_the_model_may_write': 'Content fields only. Never markup, never code, '
                                        'never the interaction or the correctness check.',
            'on_failure': 'Nothing is stored and the reasons are returned. The bundled '
                          'games remain playable without a model.',
        },
        'guarantees': [
            'Nothing in a spec is evaluated; it is embedded as JSON and read as data.',
            'Every stored game passes sims_store.validate_html, so it is self-contained '
            'and free of dynamic code evaluation.',
            'A withheld catalogue game is reported with its reason rather than dropped.',
        ],
    }
