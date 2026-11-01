"""Whiteboard tools: the tutor's hands on the shared Stage surface.

These four tools now write the *node board* (``board.py``) — the same document the
learner's rich canvas edits — instead of the retired op-log store. The names and
argument names are unchanged because the tutor prompt references them; only the
destination changed. A ``wb-<concept>`` id and a ``board-<concept>`` id resolve to the
same board (``whiteboard.concept_node_id``), which is what closes the teaching loop:
what the tutor draws is what the canvas shows.

All four are teacher-gated (fail-close, role re-derived from the authenticated
principal — never from model arguments). Students never call these; their only write
path is the ink route, which is restricted server-side to path ops.

``whiteboard_place_image`` never invents an image: it goes through the same
licence-classified acquire pipeline as ``find_image``, and only a licence-cleared,
locally-cached asset is placed. The node carries the content hash the board resolves
bitmaps by, so the client renders the real file — ``ready`` renders, ``link_only`` a
source chip, ``withheld`` the reason. The client never upgrades.
"""

from __future__ import annotations

from . import board as node_boards
from . import whiteboard as legacy
from .toolbox import ToolResult

_TOOL = 'whiteboard'


def _gate(ctx, tool: str) -> ToolResult | None:
    from . import toolbox
    return toolbox._require_teacher(ctx, tool)


def _settings(ctx):
    return getattr(ctx, 'settings', None)


def _owner(ctx) -> str:
    return str(getattr(getattr(ctx, 'user', None), 'id', '') or '')


def _apply_nodes(ctx, board_id: str, nodes: list[dict], *, tag_new: str = '') -> dict | None:
    """Add translated nodes to the concept board, creating it on first use.

    The board id is the address, so the owner is read back from the document when it
    already exists (a second teacher must not be locked out of a shared concept board)
    and taken from the principal only when the board is first created. A lost version
    race is retried, not surfaced: a drawing write is cheap to re-derive.
    """
    settings = _settings(ctx)
    nid = legacy.concept_node_id(board_id)
    if settings is None or nid is None:
        return None
    mutations = [{'action': 'add', 'node': n} for n in nodes]
    for _ in range(3):
        doc = node_boards.load(settings, nid)
        if doc is None:
            doc = node_boards.create(settings, owner_id=_owner(ctx), board_id=nid,
                                     space=dict(legacy.DEFAULT_SPACE))
        # The document's own owner wins, and an empty string is a real owner (a legacy
        # concept board): `or` would silently substitute the caller and the ownership
        # check inside apply_mutations would then refuse a board that does exist.
        existing = doc.get('owner_id')
        owner = str(existing) if existing is not None else _owner(ctx)
        doc, reason = node_boards.apply_mutations(
            settings, nid, owner_id=owner,
            base_version=int(doc.get('version', 1)), mutations=mutations,
            actor='tutor', tag_new=tag_new)
        if doc is not None:
            return doc
        if reason != 'version':
            return None
    return None


def whiteboard_read(ctx, board_id: str) -> ToolResult:
    """Read the shared board: every node with its kind, geometry and text, plus a
    bounded digest the tutor can reason over, and how many hands are raised."""
    gate = _gate(ctx, 'whiteboard_read')
    if gate is not None:
        return gate
    settings = _settings(ctx)
    if settings is None:
        return ToolResult('whiteboard_read', False, error='No settings are bound to this call')
    nid = legacy.concept_node_id(board_id)
    doc = node_boards.load(settings, nid) if nid else None
    if doc is None:
        return ToolResult('whiteboard_read', False,
                          refused=f'No board named {board_id!r} exists. Boards are created '
                                  'on first write; use the id the client shows.')
    view = legacy.legacy_view(doc)
    nodes = sorted(doc.get('nodes', []), key=lambda n: n.get('z', ''))
    return ToolResult('whiteboard_read', True,
                      {'board_id': doc['id'], 'title': doc.get('title', ''),
                       'version': int(doc.get('version', 1)),
                       'space': doc.get('space'),
                       'nodes': nodes,
                       'digest': legacy.digest(nodes),
                       # Legacy-shape projection, kept for readers of the old view.
                       'board_ops': view['layers']['board']['ops'],
                       'student_ink_ops': view['layers']['student_ink']['ops'],
                       'open_interrupts': len(doc.get('interrupts') or [])},
                      notes=['Read the board before editing so your drawing composes '
                             'with what is already there. Node ids and z order are '
                             'server facts: never invent them.'])


def whiteboard_apply(ctx, board_id: str, ops: list, summary: str = '') -> ToolResult:
    """Draw vector ops on the shared board: path/shape/connector/text/image.

    Each op is validated with the legacy bounds and translated into a node, then the
    whole batch is applied atomically — ids and z order are assigned server-side.
    """
    gate = _gate(ctx, 'whiteboard_apply')
    if gate is not None:
        return gate
    settings = _settings(ctx)
    if settings is None:
        return ToolResult('whiteboard_apply', False, error='No settings are bound to this call')
    if not isinstance(ops, list) or not ops:
        return ToolResult('whiteboard_apply', False, refused='No ops supplied.')
    nodes: list[dict] = []
    for op in ops[:64]:
        cleaned = legacy.clean_op(op, dict(legacy.DEFAULT_SPACE), layer='board')
        node = legacy.op_to_node(cleaned, op) if cleaned is not None else None
        if node is not None:
            nodes.append(node)
    if not nodes:
        return ToolResult('whiteboard_apply', False,
                          refused='No ops survived validation (unknown type, malformed '
                                  'geometry, or text over 200 chars). Nothing was changed.')
    doc = _apply_nodes(ctx, board_id, nodes)
    if doc is None:
        return ToolResult('whiteboard_apply', False,
                          refused='The board id is malformed or the board does not exist '
                                  'and could not be created. Nothing was changed.')
    return ToolResult('whiteboard_apply', True,
                      {'board_id': doc['id'], 'version': doc['version'],
                       'applied': len(nodes)},
                      notes=[summary] if summary else [])


def whiteboard_write(ctx, board_id: str, text: str, x: float, y: float,
                     size: float = 16) -> ToolResult:
    """Text sugar over whiteboard_apply: the data layer is always searchable text."""
    gate = _gate(ctx, 'whiteboard_write')
    if gate is not None:
        return gate
    settings = _settings(ctx)
    if settings is None:
        return ToolResult('whiteboard_write', False, error='No settings are bound to this call')
    cleaned = legacy.clean_op({'type': 'text', 'text': text, 'x': x, 'y': y, 'size': size},
                              dict(legacy.DEFAULT_SPACE), layer='board')
    node = legacy.op_to_node(cleaned) if cleaned is not None else None
    if node is None:
        return ToolResult('whiteboard_write', False,
                          refused='Text was empty, over 200 chars, or coordinates were '
                                  'invalid. Nothing was changed.')
    doc = _apply_nodes(ctx, board_id, [node])
    if doc is None:
        return ToolResult('whiteboard_write', False,
                          refused='The board id is malformed or the board does not exist '
                                  'and could not be created. Nothing was changed.')
    return ToolResult('whiteboard_write', True,
                      {'board_id': doc['id'], 'version': doc['version']})


def whiteboard_place_image(ctx, board_id: str, query: str, x: float = 0, y: float = 0,
                           w: float = 320) -> ToolResult:
    """Acquire a licence-cleared image and pin it on the board, licence posture intact.

    The node carries the content hash the board resolves by, so the canvas renders the
    real cached bitmap through the bytes route rather than a chip.
    """
    gate = _gate(ctx, 'whiteboard_place_image')
    if gate is not None:
        return gate
    settings = _settings(ctx)
    if settings is None:
        return ToolResult('whiteboard_place_image', False,
                          error='No settings are bound to this call')
    from . import media
    payload = media.acquire(settings, ' '.join(str(query or '').split())[:200],
                            alt_text=f'Whiteboard image for {query}')
    asset = payload.get('asset') or {}
    outcome = payload.get('outcome', '')
    if outcome not in ('downloaded', 'hit_deduplicated') or not asset:
        refused = (f'The acquire pipeline returned {outcome!r}: no licence-cleared image '
                   'was downloaded, so nothing was placed on the board. The refusal is '
                   'the result — do not retry with an invented URL.')
        return ToolResult('whiteboard_place_image', False,
                          {'outcome': outcome}, refused=refused,
                          notes=payload.get('notes', []))
    sha = str(asset.get('sha256') or '')
    width = asset.get('width') or 4
    height = asset.get('height') or 3
    node = {'kind': 'image', 'x': x, 'y': y, 'w': w,
            'h': w * height / width,
            'payload': {'src': f'/api/v1/media/images/{sha}/bytes', 'sha256': sha,
                        'title': asset.get('title', ''),
                        'credit': asset.get('attribution_text', ''),
                        'licence': asset.get('licence_code', ''),
                        'licence_class': asset.get('licence_class', ''),
                        'source_url': asset.get('landing_page_url', '')}}
    doc = _apply_nodes(ctx, board_id, [node])
    if doc is None:
        return ToolResult('whiteboard_place_image', False,
                          refused='The board id is malformed, or the acquired asset was '
                                  'not a resolvable cached image, so nothing was placed.')
    return ToolResult('whiteboard_place_image', True,
                      {'board_id': doc['id'], 'version': doc['version'],
                       'placed': {'title': asset.get('title', ''),
                                  'licence': asset.get('licence_code', ''),
                                  'licence_url': asset.get('licence_url', ''),
                                  'credit': asset.get('attribution_text', ''),
                                  'source_url': asset.get('landing_page_url', '')}},
                      citations=[{'kind': 'image', 'title': asset.get('title', ''),
                                  'url': asset.get('landing_page_url', ''),
                                  'source': asset.get('source', 'media pipeline'),
                                  'licence': asset.get('licence_code', ''),
                                  'licence_class': asset.get('licence_class', '')}],
                      notes=['The image was downloaded into this instance\'s cleared '
                             'cache; the board references it by content hash.'])
