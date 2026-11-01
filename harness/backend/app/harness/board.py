"""Board: the interactive canvas the teacher, the learner and the tutor share.

Distinct from ``whiteboard.py`` (the op-append Stage surface the tutor draws on):
a board is a *node* document — every mark is an addressable node the client can
move, update and delete, and the client never fabricates server facts (ids, the
z-order index, media status). Storage is one JSON file per board under
``<data_dir>/boards/``.

Boundary invariants (fail-close, enforced here, never in the client):
- Ownership: every route re-derives the caller from the authenticated principal
  and compares against ``owner_id``. A board that is not yours is a 404, not a
  403 (existence is not disclosed).
- Optimistic concurrency: writes carry ``base_version``; a stale write is a 409,
  never a silent last-writer-wins stomp.
- The z-order index is a base-62 fractional string computed here. The client
  sends ordering *intent* (append, or between two ids), never an index.
- Media nodes: status arrives only from a licence-gated pipeline (media.acquire,
  video, simulation_map). ``update`` cannot touch media status — a client never
  upgrades a withheld card, and an embed URL must be https on the allowlist hosts.
- Every mutation appends one line to ``boards/manifest.jsonl`` (audit), and the
  audit line names the principal, never the model.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import secrets
import threading
import time
import zipfile
from pathlib import Path
from typing import Any

NODE_KINDS = ('path', 'shape', 'connector', 'text', 'image', 'video', 'simulation', 'answer')
SHAPES = ('rect', 'ellipse', 'arrow')
# Mirror of MediaEmbed.hosts on the Swift side: the only hosts a board node may
# embed. Gizmos is deep-link only and never appears here.
EMBED_HOSTS = ('youtube-nocookie.com', 'youtube.com', 'phet.colorado.edu')
VIDEO_STATUSES = ('verified_embed', 'link_only', 'withheld')
SIM_STATUSES = ('verified_embed', 'link_only', 'withheld')

MAX_NODES = 800
MAX_POINTS_PER_PATH = 800
MAX_TEXT_CHARS = 2000
MAX_ANSWER_CHARS = 6000
MAX_MUTATIONS = 128
MAX_SPACE = 200_000
DEFAULT_SPACE = {'w': 6000, 'h': 4000}

_ALPHABET = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock(board_id: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(board_id, threading.Lock())


def _root(settings) -> Path:
    return Path(settings.data_dir) / 'boards'


def _path(settings, board_id: str) -> Path:
    return _root(settings) / f'{board_id}.json'


def _valid_id(board_id: str) -> bool:
    return bool(board_id) and len(board_id) <= 80 and all(
        c.isalnum() or c in '-_' for c in board_id)


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and value == value and abs(value) <= MAX_SPACE


def _num(value: Any, default: float = 0.0) -> float | None:
    return round(float(value), 1) if _finite(value) else None


# --------------------------------------------------------------------- z-order
#
# Fractional indexing as plain base-62 fixed-point numbers: a z string is the
# digit expansion of a value in (0,1), '' is zero, trailing '0's are stripped
# (canonical form). Midpoint insertion is integer arithmetic at a wider
# precision, which is far harder to get wrong than digit-by-digit carry logic.

def _val(s: str, k: int) -> int:
    v = 0
    for ch in s.ljust(k, '0'):
        v = v * 62 + _ALPHABET.index(ch)
    return v


def _encode(v: int, k: int) -> str:
    out = []
    for _ in range(k):
        v, r = divmod(v, 62)
        out.append(_ALPHABET[r])
    return ''.join(reversed(out)).rstrip('0')


def between(prev: str, nxt: str) -> str | None:
    """A canonical z string strictly between ``prev`` and ``nxt`` (or None).

    ``''`` is the zero sentinel: ``between('', x)`` is a value below ``x``,
    ``between(x, '')`` a value above ``x``. Returns None when no room exists at
    any precision, so the caller can refuse or renumber instead of corrupting
    the order.
    """
    prev = prev if isinstance(prev, str) else ''
    nxt = nxt if isinstance(nxt, str) else ''
    if prev == '' and nxt == '':
        return _encode(_val('1', 2) // 2, 2) or '0v'
    if prev == '':
        if nxt == '' or set(nxt) == {'0'}:
            return None  # nxt is zero: nothing canonical lives below it
        k = len(nxt) + 8
        return _encode(_val(nxt, k) // 2, k) or None
    if nxt == '':
        # strictly above prev: increment at prev's own precision, else extend
        k = max(len(prev), 1)
        v = _val(prev, k) + 1
        if v < 62 ** k:
            s = _encode(v, k)
            if s and _val(s, len(s)) > _val(prev, len(prev)):
                return s
        return prev + '1'
    if _val(prev, len(prev)) >= _val(nxt, len(nxt)):
        return None
    k = max(len(prev), len(nxt)) + 8
    a, b = _val(prev, k), _val(nxt, k)
    v = (a + b) // 2
    if v <= a:
        v = a + 1
    if v >= b:
        return None
    return _encode(v, k) or None


def _renumber(nodes: list[dict]) -> None:
    """Re-space the stack with wide, even gaps (used when a gap is exhausted)."""
    for i, node in enumerate(sorted(nodes, key=lambda n: n.get('z', ''))):
        node['z'] = _encode((i + 1) * 62 ** 6, 8).rstrip('0')


def top_z(nodes: list[dict]) -> str:
    """The z string for a node appended frontmost (rendered last, on top).

    Renderers sort ascending by z, so the largest z paints on top; a new node
    goes above the current maximum. Exhausted gaps trigger a renumber.
    """
    highest = max((n.get('z', '') for n in nodes if isinstance(n.get('z'), str)), default='')
    z = between(highest, '')
    if z is None:
        _renumber(nodes)
        highest = max((n.get('z', '') for n in nodes), default='')
        z = between(highest, '')
    return z or '0v'


def _z_between_neighbors(nodes: list[dict], after_id: str = '', before_id: str = '') -> str | None:
    """z between two existing nodes identified by id. Empty id = that end of the stack."""
    ordered = sorted(nodes, key=lambda n: n.get('z', ''))
    prev_z, next_z = '', ''
    if after_id:
        after = next((n for n in ordered if n['id'] == after_id), None)
        if after is None:
            return None
        prev_z = after['z']
    if before_id:
        before = next((n for n in ordered if n['id'] == before_id), None)
        if before is None:
            return None
        next_z = before['z']
    z = between(prev_z, next_z)
    if z is None:
        _renumber(ordered)
        prev_z, next_z = '', ''
        if after_id:
            prev_z = next((n['z'] for n in ordered if n['id'] == after_id), '')
        if before_id:
            next_z = next((n['z'] for n in ordered if n['id'] == before_id), '')
        z = between(prev_z, next_z)
    return z


def _z_between_neighbors(nodes: list[dict], after_id: str = '', before_id: str = '') -> str | None:
    """z between two existing nodes identified by id. Empty id = that end of the stack."""
    ordered = sorted(nodes, key=lambda n: n.get('z', ''))
    prev_z, next_z = '', ''
    if after_id:
        after = next((n for n in ordered if n['id'] == after_id), None)
        if after is None:
            return None
        prev_z = after['z']
    if before_id:
        before = next((n for n in ordered if n['id'] == before_id), None)
        if before is None:
            return None
        next_z = before['z']
    return between(prev_z, next_z)


# --------------------------------------------------------------------- nodes

def _clean_payload(kind: str, payload: Any, *, geom: tuple = ()) -> dict | None:
    payload = payload if isinstance(payload, dict) else {}
    out: dict[str, Any] = {}

    def text(key: str, cap: int) -> str:
        return ' '.join(str(payload.get(key) or '').split())[:cap]

    if kind == 'path':
        points = payload.get('points')
        if not isinstance(points, list) or not (2 <= len(points) <= MAX_POINTS_PER_PATH):
            return None
        clean = []
        for pair in points:
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                return None
            x, y = _num(pair[0]), _num(pair[1])
            if x is None or y is None:
                return None
            clean.append([x, y])
        out['points'] = clean
        colour = str(payload.get('colour') or '')[:32]
        width = payload.get('width')
        if colour:
            out['colour'] = colour
        if _finite(width):
            out['width'] = min(48.0, max(0.3, float(width)))
        return out

    if kind == 'shape':
        # Geometry lives on the node (flat x/y/w/h per the merged schema); the
        # payload carries only the shape kind and its stroke colour.
        if payload.get('shape') not in SHAPES:
            return None
        if len(geom) != 4 or any(v is None for v in geom) or geom[2] <= 0 or geom[3] <= 0:
            return None
        out.update(shape=payload['shape'])
        if str(payload.get('colour') or '')[:32]:
            out['colour'] = str(payload['colour'])[:32]
        return out

    if kind == 'connector':
        a, b = _num(payload.get('x')), _num(payload.get('y'))
        x2, y2 = _num(payload.get('x2')), _num(payload.get('y2'))
        if None in (a, b, x2, y2):
            return None
        out.update(x=a, y=b, x2=x2, y2=y2)
        label = text('label', 120)
        if label:
            out['label'] = label
        return out

    if kind == 'text':
        value = text('text', MAX_TEXT_CHARS)
        if not value:
            return None
        out['text'] = value
        size = payload.get('size')
        out['size'] = min(96.0, max(9.0, float(size))) if _finite(size) else 16.0
        return out

    if kind == 'answer':
        value = text('text', MAX_ANSWER_CHARS)
        question = text('question', 2000)
        if not value:
            return None
        out['text'] = value
        if question:
            out['question'] = question
        sha = str(payload.get('image_sha256') or '')
        if sha and all(c in '0123456789abcdef' for c in sha) and len(sha) <= 64:
            out['image_sha256'] = sha
        return out

    if kind == 'image':
        src = str(payload.get('src') or '').strip()
        sha = str(payload.get('sha256') or '')
        # src is a server-relative asset URL the bytes route can actually serve.
        if not src.startswith('/api/v1/media/images/') or len(src) > 400:
            return None
        if len(sha) != 64 or not all(c in '0123456789abcdef' for c in sha):
            return None
        out.update(src=src, sha256=sha,
                   title=text('title', 160), credit=text('credit', 240),
                   licence=text('licence', 80), licence_class=text('licence_class', 40),
                   source_url=text('source_url', 400))
        return out

    if kind == 'video':
        embed = str(payload.get('embed_url') or '').strip()
        watch = str(payload.get('watch_url') or '').strip()
        status = payload.get('status')
        if status not in VIDEO_STATUSES:
            return None
        out.update(status=status, title=text('title', 200),
                   watch_url=watch[:400], licence_class=text('licence_class', 40))
        if embed:
            # The embed allowlist is the same one the Swift MediaEmbed enforces at
            # render time; enforcing it here too means a bad payload is refused,
            # not stored and discovered as a blank frame later.
            from urllib.parse import urlparse
            parsed = urlparse(embed)
            host = (parsed.hostname or '').removeprefix('www.')
            if parsed.scheme != 'https' or host not in EMBED_HOSTS:
                return None
            if status != 'verified_embed':
                return None
            out['embed_url'] = embed[:400]
        elif status == 'verified_embed':
            return None
        reason = text('withheld_reason', 300)
        if reason:
            out['withheld_reason'] = reason
        if status == 'withheld' and not reason:
            return None
        return out

    if kind == 'simulation':
        provider = payload.get('provider')
        status = payload.get('status')
        if provider not in ('phet', 'gizmos') or status not in SIM_STATUSES:
            return None
        url = str(payload.get('url') or '').strip()
        if not url or len(url) > 400:
            return None
        from urllib.parse import urlparse
        parsed = urlparse(url)
        host = (parsed.hostname or '').removeprefix('www.')
        if parsed.scheme != 'https':
            return None
        if provider == 'phet' and status == 'verified_embed' and host != 'phet.colorado.edu':
            return None
        out.update(provider=provider, status=status, url=url,
                   title=text('title', 200), licence_class=text('licence_class', 40),
                   integration='embed' if (provider == 'phet' and status == 'verified_embed')
                   else 'deep_link')
        reason = text('withheld_reason', 300)
        if reason:
            out['withheld_reason'] = reason
        return out

    return None


def _clean_node(raw: Any) -> dict | None:
    """A full node as it arrives in an ``add`` mutation. id/z are assigned here."""
    if not isinstance(raw, dict):
        return None
    kind = raw.get('kind')
    if kind not in NODE_KINDS:
        return None
    x, y = _num(raw.get('x')), _num(raw.get('y'))
    if x is None or y is None:
        return None
    w = _num(raw.get('w'), 0) or 0 if kind in ('path', 'shape', 'connector', 'image',
                                               'video', 'simulation', 'answer') else 0
    h = _num(raw.get('h'), 0) or 0 if kind in ('path', 'shape', 'connector', 'image',
                                               'video', 'simulation', 'answer') else 0
    if kind == 'shape':
        # The shape validator needs the node geometry that was just read.
        payload = _clean_payload('shape', raw.get('payload'), geom=(x, y, w, h))
        if payload is None:
            return None
    else:
        payload = _clean_payload(kind, raw.get('payload'))
        if payload is None:
            return None
    node: dict[str, Any] = {'kind': kind, 'x': x, 'y': y, 'payload': payload}
    if w or h:
        node['w'] = w
        node['h'] = h
    return node


def _touch(doc: dict) -> None:
    doc['version'] = int(doc.get('version', 1)) + 1
    doc['updated_at'] = round(time.time(), 3)


# --------------------------------------------------------------------- audit

def _audit(settings, board_id: str, *, user: str, action: str, version: int,
           detail: dict | None = None) -> None:
    manifest = _root(settings) / 'manifest.jsonl'
    manifest.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps({'at': round(time.time(), 3), 'board_id': board_id,
                       'user': str(user)[:80], 'action': action, 'version': version,
                       'detail': detail or {}}, ensure_ascii=False)
    with manifest.open('a', encoding='utf-8') as fh:
        fh.write(line + '\n')


# --------------------------------------------------------------------- crud

def create(settings, *, owner_id: str, board_id: str | None = None,
           title: str = '', space: dict | None = None) -> dict:
    """Create an empty board. ``space`` overrides the default world size.

    The concept boards the Stage whiteboard tools address are created in the legacy
    4000x2500 space so the native Stage's fixed pixel mapping stays faithful; every
    other caller keeps the 6000x4000 default. The override is a creation-time fact
    only — it never bumps a version, because there is no version yet.
    """
    board_id = board_id or f'board-{secrets.token_hex(6)}'
    if not _valid_id(board_id):
        raise ValueError('invalid board id')
    doc = {'id': board_id,
           'title': ' '.join(str(title or '').split())[:120] or 'Untitled board',
           'owner_id': str(owner_id)[:80],
           'version': 1, 'created_at': round(time.time(), 3),
           'updated_at': round(time.time(), 3),
           'space': dict(space or DEFAULT_SPACE),
           'nodes': []}
    root = _root(settings)
    root.mkdir(parents=True, exist_ok=True)
    tmp = _path(settings, board_id).with_suffix('.tmp')
    tmp.write_text(json.dumps(doc, ensure_ascii=False), encoding='utf-8')
    tmp.replace(_path(settings, board_id))
    _audit(settings, board_id, user=owner_id, action='create', version=1)
    return doc


def load(settings, board_id: str) -> dict | None:
    if not _valid_id(board_id):
        return None
    path = _path(settings, board_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None


def load_owned(settings, board_id: str, owner_id: str) -> dict | None:
    doc = load(settings, board_id)
    if doc is None or doc.get('owner_id') != owner_id:
        return None
    return doc


def latest_version(settings, board_id: str) -> int:
    """The board's current version, 0 when absent — a read-to-write shortcut the
    agent tools use so a mutation carries the version it actually saw."""
    doc = load(settings, board_id)
    return int(doc.get('version', 1)) if doc else 0


def delete(settings, board_id: str, *, owner_id: str) -> bool:
    with _lock(board_id):
        doc = load_owned(settings, board_id, owner_id)
        if doc is None:
            return False
        _path(settings, board_id).unlink(missing_ok=True)
    _audit(settings, board_id, user=owner_id, action='delete', version=doc['version'])
    return True


def list_for_owner(settings, owner_id: str) -> list[dict]:
    root = _root(settings)
    if not root.exists():
        return []
    out = []
    for path in sorted(root.glob('board-*.json')):
        try:
            doc = json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            continue
        if doc.get('owner_id') != owner_id:
            continue
        out.append({'id': doc['id'], 'title': doc.get('title', ''),
                    'version': doc.get('version', 1),
                    'node_count': len(doc.get('nodes', [])),
                    'updated_at': doc.get('updated_at', 0)})
    out.sort(key=lambda row: -row['updated_at'])
    return out


def apply_mutations(settings, board_id: str, *, owner_id: str, base_version: int,
                    mutations: list, actor: str = '',
                    tag_new: str = '') -> tuple[dict | None, str]:
    """Apply a validated mutation batch. Returns (doc, '') or (None, reason).

    Reasons: ``missing`` (no such board for this owner), ``version`` (stale
    base_version), ``invalid`` (every mutation failed validation). A batch is
    all-or-nothing: the file is written once, under the board lock.

    ``tag_new`` names a top-level list the ids of the nodes this batch *added* are
    appended to, in the same write. The legacy Stage shim uses it to remember which
    path nodes arrived through the student ink channel; it is a single-write seam so
    a batch still bumps the version exactly once.
    """
    with _lock(board_id):
        doc = load_owned(settings, board_id, owner_id)
        if doc is None:
            return None, 'missing'
        if int(doc.get('version', 1)) != int(base_version):
            return None, 'version'
        if not isinstance(mutations, list) or not mutations:
            return None, 'invalid'
        mutations = mutations[:MAX_MUTATIONS]
        nodes: list[dict] = list(doc.get('nodes', []))
        applied = 0
        added_ids: list[str] = []
        for mutation in mutations:
            if not isinstance(mutation, dict):
                continue
            action = mutation.get('action')
            if action == 'add':
                node = _clean_node(mutation.get('node'))
                if node is None or len(nodes) >= MAX_NODES:
                    continue
                node['id'] = f'n-{secrets.token_hex(5)}'
                node['z'] = top_z(nodes)
                node['author'] = str(actor or owner_id)[:80]
                node['at'] = round(time.time(), 3)
                nodes.append(node)
                added_ids.append(node['id'])
                applied += 1
            elif action == 'move':
                node = next((n for n in nodes if n['id'] == mutation.get('id')), None)
                if node is None:
                    continue
                moved = False
                for key in ('x', 'y', 'w', 'h'):
                    if key in mutation:
                        value = _num(mutation.get(key))
                        if value is None:
                            continue
                        node[key] = value
                        moved = True
                if mutation.get('before_id') or mutation.get('after_id'):
                    z = _z_between_neighbors(nodes, after_id=str(mutation.get('after_id') or ''),
                                             before_id=str(mutation.get('before_id') or ''))
                    if z is None:
                        continue
                    node['z'] = z
                    moved = True
                if moved:
                    node['at'] = round(time.time(), 3)
                    applied += 1
            elif action == 'update':
                node = next((n for n in nodes if n['id'] == mutation.get('id')), None)
                if node is None:
                    continue
                fields = mutation.get('fields')
                if not isinstance(fields, dict):
                    continue
                # Media status is server-derived truth: an update may never carry it.
                forbidden = {'status', 'sha256', 'embed_url', 'src', 'url', 'provider',
                             'integration', 'licence_class'}
                if forbidden & set(fields):
                    continue
                if node['kind'] in ('text', 'answer'):
                    payload = _clean_payload(node['kind'],
                                             {**node['payload'], **fields})
                    if payload is None:
                        continue
                    node['payload'] = payload
                    applied += 1
                elif node['kind'] == 'path' and 'colour' in fields:
                    node['payload']['colour'] = str(fields['colour'])[:32]
                    applied += 1
                else:
                    continue
                node['at'] = round(time.time(), 3)
            elif action == 'delete':
                before = len(nodes)
                nodes = [n for n in nodes if n['id'] != mutation.get('id')]
                applied += 1 if len(nodes) < before else 0
        if not applied:
            return None, 'invalid'
        doc['nodes'] = nodes
        if tag_new and added_ids:
            tagged = [str(i) for i in (doc.get(tag_new) or []) if isinstance(i, str)]
            doc[tag_new] = (tagged + added_ids)[-MAX_NODES:]
        _touch(doc)
        root = _root(settings)
        root.mkdir(parents=True, exist_ok=True)
        tmp = _path(settings, board_id).with_suffix('.tmp')
        tmp.write_text(json.dumps(doc, ensure_ascii=False), encoding='utf-8')
        tmp.replace(_path(settings, board_id))
    _audit(settings, board_id, user=actor or owner_id, action='mutate',
           version=doc['version'], detail={'applied': applied})
    return doc, ''


def update_meta(settings, board_id: str, mutator) -> dict | None:
    """Apply ``mutator(doc)`` to a board's top-level metadata, then bump and persist.

    Returns the doc, or None when the board is absent. Additive seam for the legacy
    Stage surface: raised hands and the ink-channel node index are board-level facts
    that are not nodes, so they ride as extra JSON keys — which ``apply_mutations``
    already preserves verbatim. The read-modify-write happens under the board lock so
    two raised hands cannot lose each other to a last-writer-wins race.
    """
    with _lock(board_id):
        doc = load(settings, board_id)
        if doc is None:
            return None
        mutator(doc)
        _touch(doc)
        root = _root(settings)
        root.mkdir(parents=True, exist_ok=True)
        tmp = _path(settings, board_id).with_suffix('.tmp')
        tmp.write_text(json.dumps(doc, ensure_ascii=False), encoding='utf-8')
        tmp.replace(_path(settings, board_id))
    return doc


# --------------------------------------------------------------------- licence rollup

def licence_rollup(settings, doc: dict) -> dict:
    """The composition posture of everything this instance actually stores.

    Only image nodes carry locally-stored assets, so only they feed the rollup;
    video/simulation nodes are EMBED_ONLY and are degraded to link chips by the
    exporters rather than redistributed. Strictest class wins, and any ShareAlike
    member flattens the whole export into ShareAlike — a mixed board rasterised
    into one artifact is one derivative work.
    """
    classes: set[str] = set()
    attributions: list[dict] = []
    from ..ingest import policy
    severity = {
        policy.LicenceClass.CC_BY_SA: 5, policy.LicenceClass.CC_BY: 4,
        policy.LicenceClass.CC0: 2, policy.LicenceClass.PUBLIC_DOMAIN: 1,
    }
    worst_name, worst_rank = '', 0
    for node in doc.get('nodes', []):
        if node.get('kind') != 'image':
            continue
        payload = node.get('payload', {})
        klass = str(payload.get('licence_class') or '')
        classes.add(klass)
        resolved = policy.classify_licence(str(payload.get('licence') or ''))
        rank = severity.get(resolved, 3)  # unrecognised but stored codes rank above CC BY
        if rank > worst_rank:
            worst_rank, worst_name = rank, (resolved.value if resolved else klass or 'unknown')
        attributions.append({'sha256': payload.get('sha256', ''),
                             'title': payload.get('title', ''),
                             'credit': payload.get('credit', ''),
                             'licence': payload.get('licence', ''),
                             'licence_class': klass,
                             'source_url': payload.get('source_url', '')})
    share_alike = any(c in ('cc_by_sa', 'CC BY-SA', 'by-sa') or 'sa' in c.lower()
                      for c in classes if c)
    display = {'cc_by_sa': 'CC BY-SA', 'cc_by': 'CC BY', 'cc0': 'CC0',
               'public_domain': 'Public Domain', 'embed_only': 'Embed-only',
               'link_only': 'Link-only'}
    strictest = worst_name or 'open'
    return {'classes': sorted(classes), 'strictest': display.get(strictest, strictest),
            'share_alike': share_alike, 'attributions': attributions}


# --------------------------------------------------------------------- export

def _svg_escape(value: str) -> str:
    return (value.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            .replace('"', '&quot;'))


def to_svg(settings, doc: dict) -> str:
    """A standalone SVG of the board. Images are embedded as data URIs; video and
    simulation nodes become link chips because a live embed is not redistributable."""
    nodes = sorted(doc.get('nodes', []), key=lambda n: n.get('z', ''))
    rollup = licence_rollup(settings, doc)
    space = doc.get('space') or DEFAULT_SPACE
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{int(space["w"])}" '
        f'height="{int(space["h"])}" viewBox="0 0 {int(space["w"])} {int(space["h"])}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
    ]
    for node in nodes:
        kind, p, x, y = node.get('kind'), node.get('payload', {}), node.get('x', 0), node.get('y', 0)
        if kind == 'path':
            pts = p.get('points', [])
            if len(pts) >= 2:
                d = 'M ' + ' L '.join(f'{px},{py}' for px, py in pts)
                parts.append(f'<path d="{d}" fill="none" stroke="{_svg_escape(p.get("colour") or "#111827")}" '
                             f'stroke-width="{p.get("width", 2.5)}" stroke-linecap="round" stroke-linejoin="round"/>')
        elif kind == 'shape':
            shape, w, h = p.get('shape'), node.get('w', 0) or p.get('w', 0), node.get('h', 0) or p.get('h', 0)
            stroke = _svg_escape(p.get('colour') or '#111827')
            if shape == 'rect':
                parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="none" stroke="{stroke}" stroke-width="2"/>')
            elif shape == 'ellipse':
                parts.append(f'<ellipse cx="{x + w / 2}" cy="{y + h / 2}" rx="{w / 2}" ry="{h / 2}" fill="none" stroke="{stroke}" stroke-width="2"/>')
            elif shape == 'arrow':
                parts.append(f'<line x1="{x}" y1="{y}" x2="{x + w}" y2="{y + h}" stroke="{stroke}" stroke-width="2" marker-end="url(#arrowhead)"/>')
        elif kind == 'connector':
            stroke = '#374151'
            parts.append(f'<line x1="{x}" y1="{y}" x2="{p.get("x2", x)}" y2="{p.get("y2", y)}" '
                         f'stroke="{stroke}" stroke-width="1.5" marker-end="url(#arrowhead)"/>')
            if p.get('label'):
                parts.append(f'<text x="{x + 8}" y="{y - 6}" font-size="12" fill="{stroke}">{_svg_escape(p["label"])}</text>')
        elif kind == 'text':
            size = p.get('size', 16)
            parts.append(f'<text x="{x}" y="{y + size}" font-size="{size}" fill="#111827">{_svg_escape(p.get("text", ""))}</text>')
        elif kind == 'answer':
            size = 15
            lines = (p.get('text', ''))[:2000].splitlines() or ['']
            parts.append(f'<rect x="{x}" y="{y}" width="480" height="{28 + 20 * len(lines)}" rx="8" fill="#eef2ff" stroke="#6366f1"/>')
            for i, line in enumerate(lines[:24]):
                parts.append(f'<text x="{x + 12}" y="{y + 24 + 20 * i}" font-size="{size}" fill="#312e81">{_svg_escape(line[:120])}</text>')
        elif kind == 'image':
            data = _image_data_uri(settings, p.get('sha256', ''))
            w = node.get('w') or 320
            h = node.get('h') or 240
            if data:
                parts.append(f'<image x="{x}" y="{y}" width="{w}" height="{h}" href="{data}"/>')
            else:
                parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#f3f4f6" stroke="#9ca3af"/>'
                             f'<text x="{x + 8}" y="{y + 20}" font-size="12" fill="#6b7280">image unavailable</text>')
        elif kind in ('video', 'simulation'):
            url = _svg_escape(p.get('url') or p.get('watch_url') or p.get('embed_url') or '')
            parts.append(f'<rect x="{x}" y="{y}" width="320" height="72" rx="8" fill="#fffbeb" stroke="#f59e0b"/>'
                         f'<text x="{x + 12}" y="{y + 28}" font-size="14" fill="#92400e">{_svg_escape("▶ " if kind == "video" else "⚙ ") + _svg_escape(p.get("title", kind))[:60]}</text>'
                         f'<text x="{x + 12}" y="{y + 52}" font-size="11" fill="#92400e">link chip — embed not redistributable: {url[:70]}</text>')
    parts.append('<defs><marker id="arrowhead" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">'
                 '<path d="M0,0 L6,3 L0,6 z" fill="#374151"/></marker></defs>')
    if rollup['share_alike']:
        parts.append(f'<text x="12" y="{int(space["h"]) - 12}" font-size="12" fill="#6b7280">'
                     f'{_svg_escape("Mixed board flattened: whole export shared under " + (rollup["strictest"] or "CC BY-SA"))}</text>')
    parts.append('</svg>')
    return '\n'.join(parts)


def _image_row(settings, sha: str) -> dict | None:
    from . import media
    for row in media.cached_assets(settings):
        if row.get('sha256') == sha:
            return row
    return None


def image_file(settings, sha: str) -> Path | None:
    """The cached file for a content hash, or None. The manifest is the index of
    what this instance may serve; a sha that is not in it was never cleared."""
    if not sha or len(sha) != 64 or not all(c in '0123456789abcdef' for c in sha):
        return None
    row = _image_row(settings, sha)
    if not row:
        return None
    path = Path(settings.data_dir) / str(row.get('cache_path') or '')
    return path if path.is_file() else None


def _image_data_uri(settings, sha: str) -> str:
    path = image_file(settings, sha)
    if path is None:
        return ''
    mime = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
            '.webp': 'image/webp', '.gif': 'image/gif'}.get(path.suffix.lower(), 'image/jpeg')
    return f'data:{mime};base64,' + base64.b64encode(path.read_bytes()).decode('ascii')


def to_lesson_bundle(settings, doc: dict) -> bytes:
    """A re-importable .lesson bundle: board JSON, media files by sha, manifest."""
    rollup = licence_rollup(settings, doc)
    manifest = {
        'format': 'luminfest-lesson-bundle', 'format_version': 1,
        'exported_at': round(time.time(), 3),
        'board': {'id': doc['id'], 'title': doc.get('title', ''), 'space': doc.get('space')},
        'licence_rollup': rollup,
        'note': 'video/simulation nodes are export-time link chips: their embeds are '
                'licence-bound to the live platform and are never redistributed.',
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('board.json', json.dumps(doc, ensure_ascii=False, indent=1))
        zf.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=1))
        for node in doc.get('nodes', []):
            if node.get('kind') != 'image':
                continue
            sha = node.get('payload', {}).get('sha256', '')
            path = image_file(settings, sha)
            if path is not None and sha not in zf.namelist():
                zf.writestr(f'media/{sha}{path.suffix.lower()}', path.read_bytes())
    return buf.getvalue()


def import_bundle(settings, *, owner_id: str, data: bytes) -> dict:
    """Re-import a .lesson bundle as a new board owned by the caller.

    Media files are restored into the image cache under their sha; the manifest
    attributions ride along so licence provenance survives the round trip.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            doc = json.loads(zf.read('board.json').decode('utf-8'))
            manifest = json.loads(zf.read('manifest.json').decode('utf-8'))
            media_entries = [(name, zf.read(name)) for name in zf.namelist()
                             if name.startswith('media/') and not name.endswith('/')]
    except (zipfile.BadZipFile, KeyError, ValueError, UnicodeDecodeError) as exc:
        raise ValueError(f'not a valid lesson bundle: {type(exc).__name__}') from exc
    if not isinstance(doc, dict) or not isinstance(doc.get('nodes'), list):
        raise ValueError('bundle board.json is malformed')
    if manifest.get('format') != 'luminfest-lesson-bundle':
        raise ValueError('bundle manifest is missing or from another format')
    if len(doc['nodes']) > MAX_NODES:
        raise ValueError('bundle exceeds the node cap')
    # Restore media first; a sha the bundle shipped is re-cached, one it did not
    # ship renders as an honest "unavailable" placeholder, never as a fabrication.
    from . import media
    restored = 0
    for name, body in media_entries:
        sha = Path(name).stem
        if body and len(sha) == 64 and all(c in '0123456789abcdef' for c in sha):
            restored += media.store_bytes(settings, body, sha=sha)
    for node in doc['nodes']:
        node['id'] = f'n-{secrets.token_hex(5)}'
    new_id = f'board-{secrets.token_hex(6)}'
    board = create(settings, owner_id=owner_id, board_id=new_id,
                   title=(str(doc.get('title') or 'Imported board')[:120] + ' (imported)'))
    board['nodes'] = doc['nodes']
    board['space'] = doc.get('space') or dict(DEFAULT_SPACE)
    _touch(board)
    root = _root(settings)
    root.mkdir(parents=True, exist_ok=True)
    tmp = _path(settings, new_id).with_suffix('.tmp')
    tmp.write_text(json.dumps(board, ensure_ascii=False), encoding='utf-8')
    tmp.replace(_path(settings, new_id))
    _audit(settings, new_id, user=owner_id, action='import',
           version=board['version'], detail={'media_restored': restored})
    return {'board': board, 'media_restored': restored}


# --------------------------------------------------------------------- share

def _shares_path(settings) -> Path:
    return _root(settings) / 'shares.jsonl'


def create_share(settings, board_id: str, *, owner_id: str,
                 ttl_days: int = 7) -> dict | None:
    if load_owned(settings, board_id, owner_id) is None:
        return None
    token = secrets.token_urlsafe(24)
    record = {'token_hash': hashlib.sha256(token.encode()).hexdigest(),
              'board_id': board_id, 'owner_id': str(owner_id)[:80],
              'created_at': round(time.time(), 3),
              'expires_at': round(time.time() + max(1, min(30, int(ttl_days))) * 86400, 3)}
    path = _shares_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as fh:
        fh.write(json.dumps(record) + '\n')
    _audit(settings, board_id, user=owner_id, action='share', version=0,
           detail={'expires_at': record['expires_at']})
    return {'token': token, 'board_id': board_id, 'expires_at': record['expires_at']}


def resolve_share(settings, token: str) -> dict | None:
    """The read-only snapshot behind a share token, recomputed at serve time.

    Only the sha256 of the token is stored, so a leaked file is not a leaked
    board. An expired or revoked token is indistinguishable: both are 410.
    """
    if not token or len(token) > 128:
        return None
    digest = hashlib.sha256(token.encode()).hexdigest()
    path = _shares_path(settings)
    if not path.exists():
        return None
    record = None
    try:
        for line in path.read_text(encoding='utf-8').splitlines():
            row = json.loads(line)
            if row.get('token_hash') == digest:
                record = row
    except Exception:
        return None
    if record is None or record.get('expires_at', 0) <= time.time():
        return None
    doc = load(settings, str(record.get('board_id') or ''))
    if doc is None:
        return None
    return {'title': doc.get('title', ''), 'space': doc.get('space'),
            'nodes': doc.get('nodes', []), 'version': doc.get('version', 1),
            'licence_rollup': licence_rollup(settings, doc),
            'expires_at': record['expires_at'], 'served_at': round(time.time(), 3)}


def revoke_shares(settings, board_id: str, *, owner_id: str) -> bool:
    if load_owned(settings, board_id, owner_id) is None:
        return False
    path = _shares_path(settings)
    if not path.exists():
        return True
    kept = []
    removed = 0
    for line in path.read_text(encoding='utf-8').splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get('board_id') == board_id:
            removed += 1
        else:
            kept.append(line)
    path.write_text('\n'.join(kept) + ('\n' if kept else ''), encoding='utf-8')
    _audit(settings, board_id, user=owner_id, action='revoke_share', version=0,
           detail={'removed': removed})
    return True
