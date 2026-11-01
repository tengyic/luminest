"""Board tools: the tutor's hands on the interactive canvas.

Authorization is *ownership*, re-derived server-side from the authenticated
principal on every call — never from model arguments, never from the client.
The board is the native app's single-user canvas, so its owner is the account
holder; a tool call that is not the owner's is a refusal, not a read.

``board_place_media`` never invents an asset. Each kind goes through the same
licence-classified pipeline the lesson surfaces use (media.acquire for images,
video.resolve for Khan/YouTube, simulation_map.for_concept for PhET/Gizmos).
Whatever posture that pipeline returns is what lands on the board: ``ready``
embeds, ``link_only`` chips, ``withheld`` reasons. The client never upgrades.
"""

from __future__ import annotations

from . import board as node_boards
from .toolbox import ToolResult


def _settings(ctx):
    settings = getattr(ctx, 'settings', None)
    return settings


def _apply(ctx, board_id: str, mutations: list, *, actor: str):
    settings = _settings(ctx)
    user = getattr(ctx, 'user', None)
    if settings is None or user is None:
        return None, ToolResult('board_apply', False,
                                error='No settings or principal are bound to this call')
    doc, reason = node_boards.apply_mutations(settings, str(board_id or ''), owner_id=user.id,
                                              base_version=node_boards.latest_version(
                                                  settings, str(board_id or '')),
                                              mutations=mutations, actor=actor)
    if doc is None:
        detail = {'missing': 'No board with that id belongs to this account.',
                  'version': 'The board moved underneath the tool (stale version); read '
                             'it again and re-apply.',
                  'invalid': 'No mutation survived validation; nothing was changed.'}
        return None, ToolResult('board_apply', False, refused=detail.get(reason, reason))
    return doc, None


def board_read(ctx, board_id: str) -> ToolResult:
    """Read a board the authenticated principal owns."""
    settings = _settings(ctx)
    user = getattr(ctx, 'user', None)
    if settings is None or user is None:
        return ToolResult('board_read', False, error='No settings or principal are bound to this call')
    doc = node_boards.load_owned(settings, str(board_id or ''), user.id)
    if doc is None:
        return ToolResult('board_read', False,
                          refused=f'No board named {board_id!r} belongs to this account. '
                                  'Boards are created by the client; use the id it shows.')
    return ToolResult('board_read', True,
                      {'board_id': doc['id'], 'title': doc.get('title', ''),
                       'version': doc.get('version', 1), 'space': doc.get('space'),
                       'nodes': doc.get('nodes', [])},
                      notes=['Read before editing so your nodes compose with what is '
                             'already placed. Node ids and z indices are server facts: '
                             'never invent them, add or reorder instead.'])


def board_apply(ctx, board_id: str, mutations: list, summary: str = '') -> ToolResult:
    """Add, move, update or delete nodes on a board this principal owns."""
    if not isinstance(mutations, list) or not mutations:
        return ToolResult('board_apply', False, refused='No mutations supplied.')
    doc, failure = _apply(ctx, board_id, mutations, actor='tutor')
    if failure is not None:
        return failure
    return ToolResult('board_apply', True,
                      {'board_id': doc['id'], 'version': doc['version'],
                       'applied': len(mutations)},
                      notes=[summary] if summary else [])


def board_write(ctx, board_id: str, text: str, x: float, y: float,
                size: float = 16) -> ToolResult:
    """Text sugar over board_apply: one text node at a position."""
    return board_apply(ctx, board_id,
                       [{'action': 'add',
                         'node': {'kind': 'text', 'x': x, 'y': y,
                                  'payload': {'text': str(text or ''), 'size': size}}}],
                       summary='tutor wrote a text block')


def board_place_media(ctx, board_id: str, kind: str, query: str = '',
                      concept_id: str = '', x: float = 0, y: float = 0,
                      w: float = 320) -> ToolResult:
    """Acquire a licence-cleared asset and pin it on the board, posture intact.

    kind: ``image`` (search by query), ``video`` (curated, by concept),
    ``simulation`` (PhET/Gizmos, by concept). An uncleared result is the refusal,
    never a fabricated URL.
    """
    settings = _settings(ctx)
    user = getattr(ctx, 'user', None)
    if settings is None or user is None:
        return ToolResult('board_place_media', False,
                          error='No settings or principal are bound to this call')
    kind = str(kind or '').strip()
    if kind == 'image':
        from . import media
        payload = media.acquire(settings, ' '.join(str(query or '').split())[:200],
                                alt_text=f'Board image for {query}')
        asset = payload.get('asset') or {}
        outcome = payload.get('outcome', '')
        if outcome not in ('downloaded', 'hit_deduplicated') or not asset:
            return ToolResult('board_place_media', False, {'outcome': outcome},
                              refused=f'The acquire pipeline returned {outcome!r}: no '
                                      'licence-cleared image was found, so nothing was '
                                      'placed. The refusal is the result — do not retry '
                                      'with an invented URL.',
                              notes=payload.get('notes', []))
        node = {'kind': 'image', 'x': x, 'y': y, 'w': w,
                'h': w * (asset.get('height') or 3) / (asset.get('width') or 4),
                'payload': {'src': f'/api/v1/media/images/{asset.get("sha256")}/bytes',
                            'sha256': asset.get('sha256', ''),
                            'title': asset.get('title', ''),
                            'credit': asset.get('attribution_text', ''),
                            'licence': asset.get('licence_code', ''),
                            'licence_class': asset.get('licence_class', ''),
                            'source_url': asset.get('landing_page_url', '')}}
        doc, failure = _apply(ctx, board_id,
                              [{'action': 'add', 'node': node}], actor='tutor')
        if failure is not None:
            return failure
        return ToolResult('board_place_media', True,
                          {'board_id': doc['id'], 'version': doc['version'],
                           'placed': {'title': asset.get('title', ''),
                                      'licence': asset.get('licence_code', ''),
                                      'licence_class': asset.get('licence_class', ''),
                                      'source_url': asset.get('landing_page_url', ''),
                                      'abs_path': str((__import__('pathlib').Path(settings.data_dir) /
                                                       asset.get('cache_path', '')))}},
                          citations=[{'kind': 'image', 'title': asset.get('title', ''),
                                      'url': asset.get('landing_page_url', ''),
                                      'source': asset.get('source', 'media pipeline'),
                                      'licence': asset.get('licence_code', ''),
                                      'licence_class': asset.get('licence_class', '')}],
                          notes=['The image was downloaded into this instance\'s cleared '
                                 'cache; the board references it by content hash.'])

    if kind == 'video':
        from . import video
        if not getattr(ctx, 'course_id', ''):
            return ToolResult('board_place_media', False,
                              refused='Video curation is keyed by course; no course is bound.')
        cards = video.resolve(settings, ctx.course_id, str(concept_id or ''))
        if not cards:
            return ToolResult('board_place_media', False,
                              {'concept_id': concept_id},
                              refused='No curated video exists for this concept. A named gap '
                                      'is the result; do not substitute an unverified URL.')
        card = cards[0]
        status = card.get('status') or 'link_only'
        node_payload = {'title': card.get('title', ''),
                        'watch_url': card.get('watch_url', ''),
                        'licence_class': card.get('licence_class', 'embed_only')}
        if status == 'verified_embed' and card.get('embed_url'):
            node_payload.update(status='verified_embed', embed_url=card['embed_url'])
        elif status == 'withheld':
            node_payload.update(status='withheld',
                                withheld_reason=card.get('withheld_reason', 'unavailable'))
        else:
            node_payload.update(status='link_only')
        doc, failure = _apply(ctx, board_id,
                              [{'action': 'add', 'node': {'kind': 'video', 'x': x, 'y': y,
                                                         'w': w, 'h': w * 9 / 16,
                                                         'payload': node_payload}}],
                              actor='tutor')
        if failure is not None:
            return failure
        return ToolResult('board_place_media', True,
                          {'board_id': doc['id'], 'version': doc['version'],
                           'placed': {'kind': 'video', 'status': node_payload['status'],
                                      'title': node_payload['title']}},
                          citations=[{'kind': 'video', 'title': card.get('title', ''),
                                      'url': card.get('watch_url', ''),
                                      'source': card.get('provider', 'khan'),
                                      'licence': card.get('licence', ''),
                                      'licence_class': node_payload['licence_class']}],
                          notes=['Embedded through the provider\'s own player only when '
                                 'embeddability verified; otherwise a link chip.'])

    if kind == 'simulation':
        from .. import simulation_map
        if not getattr(ctx, 'course_id', ''):
            return ToolResult('board_place_media', False,
                              refused='The simulation map is keyed by course; no course is bound.')
        title = str(concept_id or '')
        node = next((n for n in (ctx.graph or {}).get('nodes', []) if n.get('id') == title), None)
        payload = simulation_map.for_concept(settings, ctx.course_id, (node or {}).get('title', title))
        sims = [s for s in payload.get('simulations', []) if s.get('status') == 'ready']
        if not sims:
            return ToolResult('board_place_media', False, {'gap': payload.get('gap', '')},
                              refused='No verified simulation covers this concept. The named '
                                      'gap is the result; do not invent a URL.')
        sim = sims[0]
        provider = sim.get('provider', '')
        url = sim.get('public_url') or sim.get('launch_url') or ''
        embeddable = provider == 'phet' and 'phet.colorado.edu' in url
        doc, failure = _apply(ctx, board_id,
                              [{'action': 'add',
                                'node': {'kind': 'simulation', 'x': x, 'y': y, 'w': w,
                                         'h': w * 3 / 4,
                                         'payload': {'provider': provider,
                                                     'status': 'verified_embed' if embeddable else 'link_only',
                                                     'url': url, 'title': sim.get('title', ''),
                                                     'licence_class': 'embed_only'}}}],
                              actor='tutor')
        if failure is not None:
            return failure
        return ToolResult('board_place_media', True,
                          {'board_id': doc['id'], 'version': doc['version'],
                           'placed': {'kind': 'simulation', 'provider': provider,
                                      'status': 'verified_embed' if embeddable else 'link_only',
                                      'title': sim.get('title', '')}},
                          citations=[{'kind': 'simulation', 'title': sim.get('title', ''),
                                      'url': url, 'source': provider,
                                      'licence': sim.get('licence', ''),
                                      'licence_class': 'embed_only'}],
                          notes=['Simulations are never observable evidence. Placement is '
                                 'recorded, and the app now records that the learner opened '
                                 'the node (an interaction tap); what happens *inside* the '
                                 'embedded simulation still reports nothing back, so no '
                                 'parameter or value is claimed.'])

    return ToolResult('board_place_media', False,
                      refused=f'Unknown kind {kind!r}; use image, video or simulation.')
