"""Legacy Stage whiteboard — DEPRECATED. This module is now a *view* over board.py.

What this used to be
--------------------
An independent op-log board: one JSON file per board under
``<data_dir>/whiteboards/<id>.json``, holding ``{id, title, version, space,
layers: {board: {ops}, student_ink: {ops}}, interrupts}``. Ops were append-only and
had no node ids, so an op could never be moved, resized, reordered or deleted — and
the tutor (writing here, ``wb-<concept>``) and the learner's rich canvas (writing the
node board, ``board-<concept>``) were two documents that never met. That split is why
the teaching loop could not close: the teacher's drawing never reached the canvas.

What it is now
--------------
A thin, fail-closed compatibility shim over the node board (``board.py``), which is
the single survivor. Every function here reads or writes the *node* board
``board-<concept>`` and either (a) presents it in the legacy op-log shape so anything
still reading ``layers.board.ops`` / ``layers.student_ink.ops`` keeps working, or
(b) accepts the legacy op vocabulary and translates it into nodes. A ``wb-<concept>``
id and a ``board-<concept>`` id resolve to the same document on purpose: that is the
unification. Nothing here creates a second store.

New code must use ``board.py``. Do not extend this module; the legacy JSON files it
used to own are gone, and the shape it presents is a projection, not a store.

Boundary invariants (fail-close, enforced here, never in the client):
- The ``student_ink`` channel accepts ONLY path ops; a non-path op is refused in
  full, and the server overwrites ``layer``/``author`` regardless of what the request
  claims. A student can never write a text/shape/image node through the pen.
- Image nodes only carry a content hash the media pipeline actually cleared; an op
  without a valid sha256 is dropped rather than stored as an unresolvable reference.
"""

from __future__ import annotations

import re
import time
from typing import Any

from . import board as node_boards

BOARD_OPS = ('path', 'shape', 'connector', 'text', 'image')
INK_OPS = ('path',)
MAX_OPS_PER_LAYER = 800
MAX_POINTS_PER_PATH = 800
MAX_TEXT_CHARS = 200
DEFAULT_SPACE = {'w': 4000, 'h': 2500}

# The digest ``whiteboard_read`` hands the tutor. Bounded so a busy board cannot
# turn a read into a token flood: at most 40 lines, 200 chars each, 2400 chars total.
DIGEST_MAX_LINES = 40
DIGEST_MAX_CHARS = 2400
DIGEST_LINE_CHARS = 200

_ID_RE = re.compile(r'^(?:wb|board)-[A-Za-z0-9_.-]{1,72}$')


def _node_id_ok(board_id: str) -> bool:
    return bool(board_id) and len(board_id) <= 80 and all(
        c.isalnum() or c in '-_' for c in board_id)


# --------------------------------------------------------------- id normalisation

def concept_node_id(board_id: Any) -> str | None:
    """Normalise a ``wb-<concept>`` or ``board-<concept>`` id to the node board id.

    Both spellings name one concept surface: the Stage pane was built around
    ``wb-<concept>`` while the native canvas was built around ``board-<concept>``, and
    the whole point of this shim is that they are the same document. The concept part
    is sanitised exactly as the native ``BoardStore.id(forConcept:)`` sanitises it, so
    a dotted concept id lands on the id the canvas already uses. A malformed id returns
    None — a board is never silently created for garbage.
    """
    raw = str(board_id or '').strip()
    if not _ID_RE.match(raw):
        return None
    concept = raw.split('-', 1)[1]
    safe = ''.join(c for c in concept if c.isalnum() or c in '-_')[:60]
    candidate = f'board-{safe}' if safe else ''
    return candidate if _node_id_ok(candidate) else None


# ------------------------------------------------------------------- op cleaning

def clean_op(op: Any, space: dict, *, layer: str) -> dict | None:
    """Normalise one incoming legacy op or return None when it is invalid.

    Kept as-is from the op-log era because the prompt, the Stage and the ink route all
    speak this vocabulary. The bounds are structural (no unbounded lists, no free
    strings beyond the text cap) so a malformed client payload cannot balloon the
    document.
    """
    if not isinstance(op, dict):
        return None
    kind = op.get('type')
    if layer == 'student_ink':
        if kind not in INK_OPS:
            return None
    elif kind not in BOARD_OPS:
        return None
    out: dict[str, Any] = {'type': kind, 'layer': layer, 'at': round(time.time(), 3)}
    if kind == 'path':
        points = _clean_points(op.get('points'))
        if points is None:
            return None
        out['points'] = points
        colour = str(op.get('colour') or '')[:32]
        width = op.get('width')
        if colour:
            out['colour'] = colour
        if _finite(width):
            out['width'] = min(24.0, max(0.5, float(width)))
        return out
    if kind == 'shape':
        shape = op.get('shape')
        if shape not in ('rect', 'ellipse', 'arrow'):
            return None
        x, y, w, h = op.get('x'), op.get('y'), op.get('w'), op.get('h')
        if not (_finite(x) and _finite(y) and _finite(w) and _finite(h)):
            return None
        out.update(shape=shape, x=round(float(x), 1), y=round(float(y), 1),
                   w=round(float(w), 1), h=round(float(h), 1))
        if str(op.get('colour') or '')[:32]:
            out['colour'] = str(op['colour'])[:32]
        return out
    if kind == 'connector':
        a, b = op.get('from'), op.get('to')
        if not (_finite(a) and _finite(b)):
            return None
        label = ' '.join(str(op.get('label') or '').split())[:120]
        out.update(**{'from': round(float(a), 1), 'to': round(float(b), 1)})
        if label:
            out['label'] = label
        return out
    if kind == 'text':
        text = ' '.join(str(op.get('text') or '').split())
        if not text or len(text) > MAX_TEXT_CHARS:
            return None
        x, y = op.get('x'), op.get('y')
        if not (_finite(x) and _finite(y)):
            return None
        out.update(text=text, x=round(float(x), 1), y=round(float(y), 1))
        size = op.get('size')
        if _finite(size):
            out['size'] = min(72.0, max(9.0, float(size)))
        return out
    if kind == 'image':
        src = str(op.get('src') or '').strip()
        if not src or len(src) > 400:
            return None
        status = op.get('status')
        if status not in ('ready', 'link_only', 'withheld'):
            return None
        out.update(src=src, status=status,
                   title=' '.join(str(op.get('title') or '').split())[:160],
                   licence=' '.join(str(op.get('licence') or '').split())[:80],
                   licence_class=' '.join(str(op.get('licence_class') or '').split())[:40])
        x, y, w = op.get('x'), op.get('y'), op.get('w')
        if _finite(x) and _finite(y) and _finite(w):
            out.update(x=round(float(x), 1), y=round(float(y), 1),
                       w=min(2000.0, max(40.0, float(w))))
        return out
    return None


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and value == value and abs(value) <= 100_000


def _clean_points(points: Any) -> list[list[float]] | None:
    if not isinstance(points, list) or not (1 <= len(points) <= MAX_POINTS_PER_PATH):
        return None
    out = []
    for pair in points:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            return None
        x, y = pair
        if not _finite(x) or not _finite(y):
            return None
        out.append([round(float(x), 1), round(float(y), 1)])
    return out


# -------------------------------------------------------------- op <-> node maps

def op_to_node(cleaned: dict, raw: Any = None) -> dict | None:
    """Translate one validated legacy op into a node (raw, pre node-validation).

    The legacy vocabulary is a subset of the node kinds, so path/shape/connector/text
    map totally. An ``image`` op is only translatable when it carries the content hash
    the node board resolves bitmaps by; without it the op is dropped rather than
    stored as an unresolvable reference. A legacy connector carries scalar ``from``/
    ``to`` rather than node geometry, so it is anchored at that pair; real connectors
    are made with ``board_apply``.
    """
    if not isinstance(cleaned, dict):
        return None
    raw = raw if isinstance(raw, dict) else {}
    kind = cleaned.get('type')
    if kind == 'path':
        points = cleaned.get('points') or []
        if len(points) < 2:
            return None
        payload: dict[str, Any] = {'points': points}
        if cleaned.get('colour'):
            payload['colour'] = cleaned['colour']
        if cleaned.get('width') is not None:
            payload['width'] = cleaned['width']
        return {'kind': 'path', 'x': points[0][0], 'y': points[0][1], 'payload': payload}
    if kind == 'shape':
        w, h = cleaned.get('w'), cleaned.get('h')
        if not (_finite(w) and _finite(h)) or w <= 0 or h <= 0:
            return None
        payload = {'shape': cleaned.get('shape')}
        if cleaned.get('colour'):
            payload['colour'] = cleaned['colour']
        return {'kind': 'shape', 'x': cleaned['x'], 'y': cleaned['y'],
                'w': w, 'h': h, 'payload': payload}
    if kind == 'connector':
        a, b = cleaned.get('from'), cleaned.get('to')
        payload = {'x': a, 'y': b, 'x2': a, 'y2': b}
        if cleaned.get('label'):
            payload['label'] = cleaned['label']
        return {'kind': 'connector', 'x': a, 'y': b, 'payload': payload}
    if kind == 'text':
        payload = {'text': cleaned.get('text', '')}
        if cleaned.get('size') is not None:
            payload['size'] = cleaned['size']
        return {'kind': 'text', 'x': cleaned['x'], 'y': cleaned['y'], 'payload': payload}
    if kind == 'image':
        sha = str(raw.get('sha256') or '')
        if len(sha) != 64 or any(c not in '0123456789abcdef' for c in sha):
            return None
        node: dict[str, Any] = {
            'kind': 'image', 'x': cleaned.get('x', 0), 'y': cleaned.get('y', 0),
            'payload': {'src': f'/api/v1/media/images/{sha}/bytes', 'sha256': sha,
                        'title': cleaned.get('title', ''),
                        'credit': ' '.join(str(raw.get('credit') or '').split())[:240],
                        'licence': cleaned.get('licence', ''),
                        'licence_class': cleaned.get('licence_class', ''),
                        'source_url': str(raw.get('source_url') or '')[:400]}}
        w = cleaned.get('w')
        if _finite(w) and w > 0:
            node['w'] = w
            node['h'] = w * 0.75
        return node
    return None


def node_to_op(node: dict, layer: str) -> dict | None:
    """Project one node back into the legacy op shape, or None for a node kind the
    legacy vocabulary never had (video/simulation/answer)."""
    kind, p = node.get('kind'), node.get('payload') or {}
    base = {'layer': layer, 'at': node.get('at', 0), 'author': node.get('author', '')}
    if kind == 'path':
        op: dict[str, Any] = {'type': 'path', **base, 'points': p.get('points', [])}
        if p.get('colour'):
            op['colour'] = p['colour']
        if p.get('width') is not None:
            op['width'] = p['width']
        return op
    if kind == 'shape':
        op = {'type': 'shape', **base, 'shape': p.get('shape'), 'x': node.get('x', 0),
              'y': node.get('y', 0), 'w': node.get('w', 0), 'h': node.get('h', 0)}
        if p.get('colour'):
            op['colour'] = p['colour']
        return op
    if kind == 'connector':
        op = {'type': 'connector', **base, 'from': p.get('x'), 'to': p.get('y')}
        if p.get('label'):
            op['label'] = p['label']
        return op
    if kind == 'text':
        op = {'type': 'text', **base, 'text': p.get('text', ''),
              'x': node.get('x', 0), 'y': node.get('y', 0)}
        if p.get('size') is not None:
            op['size'] = p['size']
        return op
    if kind == 'image':
        op = {'type': 'image', **base, 'src': p.get('src', ''), 'status': 'ready',
              'title': p.get('title', ''), 'licence': p.get('licence', ''),
              'licence_class': p.get('licence_class', ''),
              'x': node.get('x', 0), 'y': node.get('y', 0)}
        if node.get('w'):
            op['w'] = node['w']
        return op
    return None


def legacy_view(doc: dict | None) -> dict | None:
    """Present a node board in the legacy op-log shape.

    The ``student_ink`` / ``board`` split is recovered from the ink-channel index the
    write path records (``ink_node_ids``); a node whose id is not in it was a board
    op. Non-path nodes are rendered on the board layer, path nodes wherever they came
    from. Never raises on an empty or absent board — an empty board is empty ops.
    """
    if not isinstance(doc, dict):
        return None
    ink_ids = {i for i in (doc.get('ink_node_ids') or []) if isinstance(i, str)}
    board_ops: list[dict] = []
    ink_ops: list[dict] = []
    for node in sorted(doc.get('nodes', []), key=lambda n: n.get('z', '')):
        layer = 'student_ink' if node.get('id') in ink_ids else 'board'
        op = node_to_op(node, layer)
        if op is None:
            continue
        (ink_ops if layer == 'student_ink' else board_ops).append(op)
    return {'id': doc.get('id', ''), 'title': doc.get('title', ''),
            'version': int(doc.get('version', 1)),
            'updated_at': doc.get('updated_at', 0),
            'space': dict(doc.get('space') or DEFAULT_SPACE),
            'layers': {'board': {'ops': board_ops}, 'student_ink': {'ops': ink_ops}},
            'interrupts': list(doc.get('interrupts') or [])}


# ---------------------------------------------------------------------- digest

def digest(nodes: list[dict]) -> str:
    """A compact, ordered, bounded textual description of the board for the tutor.

    The tutor must be able to reason about what the learner drew, so this names the
    node kinds, their geometry and their text — but a board is not a document, and an
    unbounded read is a token flood. Bounded to ``DIGEST_MAX_LINES`` lines,
    ``DIGEST_LINE_CHARS`` chars each, ``DIGEST_MAX_CHARS`` total.
    """
    lines: list[str] = []
    for node in sorted(nodes, key=lambda n: n.get('z', '')):
        if len(lines) >= DIGEST_MAX_LINES:
            lines.append(f'… {len(nodes) - DIGEST_MAX_LINES} more node(s) omitted')
            break
        lines.append(_describe(node)[:DIGEST_LINE_CHARS])
    return '\n'.join(lines)[:DIGEST_MAX_CHARS]


def _describe(node: dict) -> str:
    kind, p = node.get('kind'), node.get('payload') or {}
    x, y = node.get('x', 0), node.get('y', 0)
    if kind == 'text':
        return f'text at ({x},{y}): {p.get("text", "")}'
    if kind == 'answer':
        return f'answer at ({x},{y}): {p.get("text", "")[:80]}'
    if kind == 'path':
        return f'path of {len(p.get("points") or [])} points from ({x},{y})'
    if kind == 'shape':
        return (f'{p.get("shape", "shape")} {node.get("w", 0)}x{node.get("h", 0)} '
                f'at ({x},{y})')
    if kind == 'connector':
        return f'connector ({p.get("x")},{p.get("y")})->({p.get("x2")},{p.get("y2")})'
    if kind == 'image':
        return f'image: {p.get("title", "")} ({p.get("licence", "")}) at ({x},{y})'
    if kind in ('video', 'simulation'):
        return f'{kind}: {p.get("title", "")} [{p.get("status", "")}] at ({x},{y})'
    return f'{kind} at ({x},{y})'


# ------------------------------------------------------------------ read / write

def load(settings, board_id: str) -> dict | None:
    """The node board behind this legacy id, in the legacy shape (None if absent)."""
    nid = concept_node_id(board_id)
    if nid is None:
        return None
    return legacy_view(node_boards.load(settings, nid))


def load_or_create(settings, board_id: str, title: str = '') -> dict:
    """Create the node board on first use, in the legacy 4000x2500 space, and return
    the legacy view. An invalid id raises, exactly as the op-log store did."""
    nid = concept_node_id(board_id)
    if nid is None:
        raise ValueError('invalid board id')
    doc = node_boards.load(settings, nid)
    if doc is None:
        doc = node_boards.create(settings, owner_id='', board_id=nid,
                                 title=title, space=dict(DEFAULT_SPACE))
    return legacy_view(doc)


def _ensure(settings, nid: str) -> dict:
    doc = node_boards.load(settings, nid)
    if doc is None:
        doc = node_boards.create(settings, owner_id='', board_id=nid,
                                 space=dict(DEFAULT_SPACE))
    return doc


def apply_ops(settings, board_id: str, ops: list, *, layer: str,
              author: str = '') -> dict | None:
    """Translate legacy ops into nodes and add them atomically. Returns the legacy
    view of the new document, or None when nothing survived validation.

    ``student_ink`` accepts only path ops (``clean_op`` enforces it) and records the
    new node ids in the ink-channel index so the projection can put them back on the
    student layer. Everything a student writes is still a stroke on one shared board.
    """
    nid = concept_node_id(board_id)
    if nid is None or layer not in ('board', 'student_ink'):
        return None
    nodes: list[dict] = []
    for op in (ops or [])[:64]:
        cleaned = clean_op(op, dict(DEFAULT_SPACE), layer=layer)
        node = op_to_node(cleaned, op) if cleaned is not None else None
        if node is not None:
            nodes.append(node)
    if not nodes:
        return None
    doc = _ensure(settings, nid)
    tag = 'ink_node_ids' if layer == 'student_ink' else ''
    new_doc = _apply_retrying(settings, nid, doc, [{'action': 'add', 'node': n} for n in nodes],
                              actor=author or 'student', tag_new=tag)
    return legacy_view(new_doc)


def _apply_retrying(settings, nid: str, doc: dict, mutations: list, *, actor: str,
                    tag_new: str = '', attempts: int = 3) -> dict | None:
    """Apply a batch at the board's current version, retrying a lost version race.

    The board lock makes one write atomic, but the version read that precedes it can
    still lose to a concurrent writer; a whiteboard write is cheap to re-derive, so a
    stale version is retried rather than surfaced as a refusal.
    """
    for _ in range(attempts):
        current = node_boards.load(settings, nid) or doc
        new_doc, reason = node_boards.apply_mutations(
            settings, nid, owner_id=str(current.get('owner_id') or ''),
            base_version=int(current.get('version', 1)), mutations=mutations,
            actor=actor, tag_new=tag_new)
        if new_doc is not None:
            return new_doc
        if reason != 'version':
            return None
    return None


def raise_interrupt(settings, board_id: str, *, user: str, message: str = '') -> dict | None:
    """A student's raised hand: recorded on the board so the tutor's next turn sees it."""
    nid = concept_node_id(board_id)
    if nid is None:
        return None

    def mutator(doc: dict) -> None:
        doc.setdefault('interrupts', []).append(
            {'at': round(time.time(), 3), 'user': str(user)[:80],
             'message': ' '.join(str(message).split())[:300]})
        doc['interrupts'] = doc['interrupts'][-20:]

    return legacy_view(node_boards.update_meta(settings, nid, mutator))


def clear_interrupts(settings, board_id: str) -> dict | None:
    nid = concept_node_id(board_id)
    if nid is None:
        return None
    return legacy_view(node_boards.update_meta(
        settings, nid, lambda doc: doc.__setitem__('interrupts', [])))


def latest_version(settings, board_id: str) -> int:
    nid = concept_node_id(board_id)
    return node_boards.latest_version(settings, nid) if nid else 0


# ------------------------------------------------------------------- deprecated

def new_board(settings, *, board_id: str, title: str = '') -> dict:
    """Deprecated op-log constructor. Kept so an old caller keeps its behaviour: it
    now creates the node board behind the id and returns the legacy view."""
    nid = concept_node_id(board_id)
    if nid is None:
        raise ValueError('invalid board id')
    doc = node_boards.create(settings, owner_id='', board_id=nid, title=title,
                             space=dict(DEFAULT_SPACE))
    return legacy_view(doc)


def save(settings, doc: dict) -> None:
    """Deprecated op-log writer, now a one-way migration.

    The op-log file store is gone, so a legacy document cannot be written back as one.
    What this does instead is translate the ops of a legacy document onto the node
    board behind its id, which is the only meaning "save" can still honestly have.
    New code must use ``board.py``.
    """
    if not isinstance(doc, dict):
        raise ValueError('not a whiteboard document')
    nid = concept_node_id(doc.get('id'))
    if nid is None:
        raise ValueError('invalid board id')
    _ensure(settings, nid)
    for layer in ('board', 'student_ink'):
        ops = ((doc.get('layers') or {}).get(layer) or {}).get('ops') or []
        if ops:
            apply_ops(settings, doc['id'], ops, layer=layer)
