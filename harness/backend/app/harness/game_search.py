"""Curated math-game / interactive-activity search over an audited, operator-edited pack.

Mirrors :mod:`app.simulation_map`: the pack (``app/media_packs/games.json``) is frozen
data, every row carries its ``policy_name`` so a stored card is re-evaluated against the
live licence registry, and a topic with no coverage produces a *named gap* rather than a
fabricated hit. Every source in the pack is ``LINK_ONLY`` in
:mod:`app.ingest.policy` -- the harness names and links the activity; it never copies
it, embeds it outside the rights-holder's terms, or screenshots its problems.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_PACK_PATH = Path(__file__).resolve().parents[1] / 'media_packs' / 'games.json'


@lru_cache(maxsize=1)
def _pack() -> dict[str, Any]:
    if not _PACK_PATH.exists():
        return {'schema': 1, 'games': []}
    return json.loads(_PACK_PATH.read_text(encoding='utf-8'))


def pack_games() -> list[dict[str, Any]]:
    return list(_pack().get('games') or [])


def for_query(query: str, *, commercial: bool = False) -> dict[str, Any]:
    """Games whose title/topics/keywords match the query, as deep-link cards.

    Cards are stamped with ``policy_name`` and therefore survive the same
    ``reapply_media_policy`` re-evaluation every other stored card goes through: if a
    rights position changes, the stored card changes with it instead of silently
    outliving its licence.
    """
    needle = ' '.join((query or '').casefold().split())
    cards: list[dict[str, Any]] = []
    for game in pack_games():
        haystack = ' '.join([game.get('title', ''), ' '.join(game.get('topics', [])),
                             ' '.join(game.get('keywords', []))]).casefold()
        if not any(term in haystack for term in needle.split() if len(term) > 2):
            continue
        cards.append({
            'kind': 'game', 'slug': game.get('slug'),
            'title': game.get('title'), 'url': game.get('url'),
            'source': game.get('site_title'), 'policy_name': game.get('policy_name'),
            'integration_mode': 'deep_link', 'licence': game.get('licence'),
            'licence_class': 'link_only', 'topics': game.get('topics', []),
            'status': 'ready', 'observable': False,
            'note': game.get('note', 'Opens outside the harness; nothing is ingested.'),
        })
    if commercial:
        for card in cards:
            card['status'] = 'withheld'
            card['withheld_reason'] = ('Non-commercial source, and this instance is '
                                       'configured as a paid offering.')
    return {'query': query, 'games': cards,
            'sources': _pack().get('sources', []),
            'gap': ('No pack entry matches this topic. The pack is operator-curated: '
                    'coverage gaps are reported, not invented.') if not cards else ''}
