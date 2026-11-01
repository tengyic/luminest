"""The bundled game catalogue: which games exist, and which had to be withheld.

Games are data. A game is an ``archetype`` id plus a ``spec``, and the whole
catalogue is one directory of JSON fragments (``media_packs/playground_games*.json``)
that the packaging script already bundles. Adding a game means adding a JSON object;
adding a *kind* of game means adding an archetype module. Neither requires touching
this file.

Everything is validated on load, and an invalid game is **withheld with its reason**
rather than dropped. That is the same discipline :mod:`app.simulation_map` applies to
a PhET slug that does not resolve, and it exists for the same reason: a catalogue that
silently omits a broken entry looks complete while a learner finds the hole. A
withheld game is reported through :func:`withheld` and surfaces in the API, so a
content bug is visible to the operator instead of only to the learner who hit it.

The pack is loaded once and cached. It is read on every playground request and never
changes at runtime, and re-reading a few hundred kilobytes of JSON per request would
be a real cost for no benefit.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping

from . import archetypes as archetype_registry

#: Where the game fragments live. ``media_packs`` is bundled as data by
#: ``scripts/package.py`` (``PACK_DATA_DIRS``), so this resolves inside the frozen
#: bundle exactly as it does from source.
PACK_DIR = Path(__file__).resolve().parents[2] / 'media_packs'
PACK_GLOB = 'playground_games*.json'

#: The declared difficulty bands. A closed vocabulary, so the gallery can filter on
#: it and an authoring model cannot invent "medium-hard".
DIFFICULTIES = ('intro', 'core', 'stretch')

#: Fields every game entry must carry, and the type each must be.
_REQUIRED = {'slug': str, 'archetype': str, 'title': str, 'course_id': str,
             'concept': str, 'prompt': str, 'learning_objective': str,
             'subjects': list, 'spec': dict}
_OPTIONAL = {'difficulty': str, 'minutes': (int, float), 'reference': str,
             'tags': list, 'note': str}


def _problem(game: Any, index: int, source: str) -> str | None:
    """The first structural problem with an entry, or ``None``."""
    if not isinstance(game, Mapping):
        return f'{source}[{index}] is not an object'
    for key, kind in _REQUIRED.items():
        if key not in game:
            return f'missing required field {key!r}'
        if not isinstance(game[key], kind):
            return f'field {key!r} must be {kind.__name__}'
    for key, kind in _OPTIONAL.items():
        if key in game and not isinstance(game[key], kind):
            return f'field {key!r} must be {kind.__name__}'
    if game.get('difficulty') and game['difficulty'] not in DIFFICULTIES:
        return (f'difficulty {game["difficulty"]!r} is not one of {list(DIFFICULTIES)}')
    return None


def _load_pack() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Read every fragment, returning ``(usable_games, withheld)``.

    A game is withheld - never silently dropped - when the fragment is malformed,
    its archetype is not registered, its slug duplicates another, or its spec fails
    its own archetype's schema.
    """
    usable: list[dict[str, Any]] = []
    withheld: list[dict[str, Any]] = []
    seen: dict[str, str] = {}
    for path in sorted(PACK_DIR.glob(PACK_GLOB)):
        try:
            rows = json.loads(path.read_text(encoding='utf-8'))
        except (ValueError, OSError) as exc:
            withheld.append({'slug': path.name, 'source': path.name,
                             'reason': f'could not be read: {type(exc).__name__}: {exc}'})
            continue
        if not isinstance(rows, list):
            withheld.append({'slug': path.name, 'source': path.name,
                             'reason': 'the fragment must be a JSON array of games'})
            continue
        for index, game in enumerate(rows):
            problem = _problem(game, index, path.name)
            if problem:
                withheld.append({'slug': f'{path.name}[{index}]', 'source': path.name,
                                 'reason': problem})
                continue
            slug = str(game['slug'])
            if slug in seen:
                withheld.append({'slug': slug, 'source': path.name,
                                 'reason': f'duplicate slug; already defined in {seen[slug]}'})
                continue
            archetype = archetype_registry.get(str(game['archetype']))
            if archetype is None:
                withheld.append({'slug': slug, 'source': path.name,
                                 'reason': f'unknown archetype {game["archetype"]!r}; '
                                           f'registered: {sorted(a.id for a in archetype_registry.all_archetypes())}'})
                continue
            problems = archetype_registry.validate_spec(game['spec'], archetype)
            if problems:
                withheld.append({'slug': slug, 'source': path.name,
                                 'reason': 'spec does not match the archetype schema: '
                                           + '; '.join(problems)})
                continue
            seen[slug] = path.name
            usable.append({**dict(game), 'slug': slug,
                           'difficulty': game.get('difficulty') or 'core'})
    usable.sort(key=lambda g: (str(g.get('course_id')), str(g['slug'])))
    return usable, withheld


@lru_cache(maxsize=1)
def _cache() -> tuple[tuple[dict[str, Any], ...], tuple[dict[str, Any], ...]]:
    usable, withheld = _load_pack()
    return tuple(usable), tuple(withheld)


def refresh() -> None:
    """Drop the cache. For a long-running process after the pack changes on disk."""
    _cache.cache_clear()


def all_games() -> list[dict[str, Any]]:
    """Every usable game, ordered by course then slug so listings are stable."""
    return [dict(game) for game in _cache()[0]]


def withheld() -> list[dict[str, Any]]:
    """Games that could not be loaded, each with the reason. Published, not hidden."""
    return [dict(row) for row in _cache()[1]]


def get_game(slug: str) -> dict[str, Any] | None:
    for game in _cache()[0]:
        if game['slug'] == slug:
            return dict(game)
    return None


def by_subject(subject: str) -> list[dict[str, Any]]:
    wanted = subject.strip().casefold()
    return [g for g in all_games()
            if any(str(s).casefold() == wanted for s in g.get('subjects') or [])]


def by_course(course_id: str) -> list[dict[str, Any]]:
    return [g for g in all_games() if g.get('course_id') == course_id]


def by_archetype(archetype_id: str) -> list[dict[str, Any]]:
    return [g for g in all_games() if g.get('archetype') == archetype_id]


def subjects() -> list[str]:
    """Every subject any game declares, sorted. Derived, never hardcoded."""
    found = {str(s) for game in all_games() for s in game.get('subjects') or []}
    return sorted(found)


def courses() -> list[str]:
    return sorted({str(game.get('course_id')) for game in all_games() if game.get('course_id')})


def _card(game: Mapping[str, Any]) -> dict[str, Any]:
    """The gallery entry for one game. Carries everything needed to render a card."""
    archetype = archetype_registry.get(str(game['archetype']))
    return {
        'slug': game['slug'], 'title': game['title'], 'archetype': game['archetype'],
        'course_id': game.get('course_id'), 'concept': game.get('concept'),
        'subjects': list(game.get('subjects') or []),
        'difficulty': game.get('difficulty'), 'minutes': game.get('minutes'),
        'prompt': game.get('prompt'), 'learning_objective': game.get('learning_objective'),
        'reference': game.get('reference'), 'tags': list(game.get('tags') or []),
        'interaction': archetype.interaction if archetype else '',
        'scored': archetype.scored if archetype else False,
        'telemetry': archetype.telemetry if archetype else '',
        'play_url': f"/api/v1/playground/games/{game['slug']}/html",
    }


def catalogue(*, subject: str = '', course_id: str = '', archetype_id: str = '',
              difficulty: str = '') -> dict[str, Any]:
    """The playground gallery: every game, the filters, and the withholding record."""
    games = all_games()
    if subject:
        games = [g for g in games if subject.casefold() in
                 [str(s).casefold() for s in g.get('subjects') or []]]
    if course_id:
        games = [g for g in games if g.get('course_id') == course_id]
    if archetype_id:
        games = [g for g in games if g.get('archetype') == archetype_id]
    if difficulty:
        games = [g for g in games if g.get('difficulty') == difficulty]
    return {
        'games': [_card(g) for g in games],
        'total': len(games),
        'catalogue_total': len(all_games()),
        'archetypes': len(archetype_registry.all_archetypes()),
        'subjects': subjects(),
        'courses': courses(),
        'difficulties': list(DIFFICULTIES),
        'filters': {'subject': subject, 'course_id': course_id,
                    'archetype': archetype_id, 'difficulty': difficulty},
        'withheld': withheld(),
        'note': 'Every game here is first-party: it runs offline and reports its outcome '
                'back to the harness, so unlike a PhET or Gizmos simulation it can be '
                'evidence of learning.',
    }


def summary() -> dict[str, Any]:
    """Counts by subject and by archetype, for the operator's view."""
    by_subject_count: dict[str, int] = {}
    by_archetype_count: dict[str, int] = {}
    for game in all_games():
        for subject in game.get('subjects') or ['(none)']:
            by_subject_count[str(subject)] = by_subject_count.get(str(subject), 0) + 1
        by_archetype_count[str(game['archetype'])] = \
            by_archetype_count.get(str(game['archetype']), 0) + 1
    return {
        'games': len(all_games()),
        'archetypes_registered': len(archetype_registry.all_archetypes()),
        'archetypes_used': len(by_archetype_count),
        'archetypes_unused': sorted(a.id for a in archetype_registry.all_archetypes()
                                    if a.id not in by_archetype_count),
        'by_subject': dict(sorted(by_subject_count.items())),
        'by_archetype': dict(sorted(by_archetype_count.items())),
        'withheld': len(withheld()),
        'pack_files': sorted(p.name for p in PACK_DIR.glob(PACK_GLOB)),
    }
