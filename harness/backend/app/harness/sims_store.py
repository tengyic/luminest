"""Storage and validation for self-contained teaching artifacts (simulations, decks).

The creation tools write real files that the web layer serves back to the learner, so
this module owns three things that would otherwise drift apart.

1. **Versioning.** Every edit produces a new version file and never overwrites the old
   one. A scoped edit that goes wrong must be revertible, which it cannot be if the
   previous bytes are gone, so the previous version stays on disk and in the manifest.

2. **Validation before storage.** An artifact is stored only after
   :func:`validate_html` accepts it. The checks are structural, not aesthetic: the file
   must parse, must be self-contained (no external scripts, stylesheets, fetches or form
   posts to outside hosts), must tag interactive series with ``data-series`` (the
   hover-highlight convention the web UI uses), and must not contain ``eval`` or
   ``new Function`` — a teaching artifact has no legitimate use for either, and deciding
   per-call-site whether an ``eval`` argument is "trusted" is exactly the judgement this
   project refuses to make at runtime.

3. **One serving contract.** Artifacts live under ``<data_dir>/sims/`` and are served
   read-only as::

       GET /api/v1/sims/{artifact_id}/raw              -> latest version, text/html
       GET /api/v1/sims/{artifact_id}/raw?version=n    -> a specific version
       GET /api/v1/sims/{artifact_id}                  -> manifest (metadata only)

   The web layer implements these routes *against this module*: :func:`read_version`
   (and its :func:`latest_html` convenience) is the read path, :func:`load` is the
   manifest path, and :func:`validate_html` is the authority on what is servable. There
   is deliberately no second storage format -- a route that reads ``sims/`` files
   directly instead of through this module would drift from the versioning and
   validation rules recorded here.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Mapping

#: Kinds of artifact this store holds. A simulation is interactive HTML; a deck is a
#: printable HTML slide deck (optionally paired with a .pptx file recorded in the
#: version entry).
KINDS = ('simulation', 'deck')

#: The URL prefix the web layer serves artifacts under. See the module docstring for
#: the full contract and the recorded assumption.
RAW_URL_PREFIX = '/api/v1/sims'

_VOID_ELEMENTS = frozenset({
    'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta',
    'param', 'source', 'track', 'wbr',
})

#: Resource-loading attributes that may not point at an outside host. An artifact that
#: loads a script or a stylesheet from the network is not self-contained: it breaks
#: offline use, it phones home from a lesson, and it defeats the point of validating
#: what we serve. ``srcset`` is included because it loads images exactly as ``src`` does.
_RESOURCE_ATTR = re.compile(
    r'(?:src|href|action|data|poster|srcset)\s*=\s*["\']\s*(?:https?:)?//[^"\']+["\']', re.I)

#: Outbound calls from inside the artifact's own script. A bare ``Function(...)`` call
#: is dynamic evaluation exactly as ``eval`` is. JavaScript identifiers are
#: case-sensitive, so the constructor alternative is case-sensitive on purpose: the
#: lowercase ``function (`` keyword is how ordinary named and callback functions are
#: written, and a case-insensitive match here would refuse almost every authored
#: artifact. The word boundary keeps ``myFunction(`` untouched either way. ``eval``
#: itself is matched case-insensitively; the ``(?-i:...)`` inline group scopes the
#: case-sensitivity to the constructor alternative alone.
_FETCH_HTTP = re.compile(r'(?:fetch|import)\s*\(\s*["\'`]https?:', re.I)
_XHR = re.compile(r'XMLHttpRequest|WebSocket|EventSource', re.I)
_DYNAMIC_EVAL = re.compile(r'\beval\s*\(|(?-i:\bFunction\s*\()', re.I)

#: A bracketed string member call such as ``globalThis['Function']('alert(1)')`` or
#: ``window["eval"](code)`` is dynamic evaluation through the back door: the
#: case-sensitive constructor pattern above cannot see ``Function`` spelled out in a
#: string. The property string is matched case-insensitively (``window['function'](``
#: has no legitimate meaning either) and only the *call* is flagged -- plain property
#: access such as ``window.location`` never enters a bracket string of this shape.
_GLOBAL_BRACKET_EVAL = re.compile(
    r"\b(?:globalThis|self|window)\s*\[\s*['\"](?:eval|function)['\"]\s*\]\s*\(", re.I)

#: ``setTimeout('code', 100)`` compiles and runs the string, which is ``eval`` under
#: another name. The legitimate form -- a function reference -- carries no quote
#: directly after the opening paren, so it stays clean.
_TIMER_STRING_ARG = re.compile(r'''\b(?:setTimeout|setInterval)\s*\(\s*["'`]''', re.I)

#: CSS ``@import`` of a network URL fetches an external stylesheet at render time; the
#: same self-containment rule that bans ``<link href`` bans this. Whitespace after
#: ``@import`` is optional in CSS (``@import'https://...'`` is valid), so the gap is
#: ``\s*``, not ``\s+``. A relative ``@import`` is allowed (it can only ever 404
#: inside a single-file artifact, not phone home).
_CSS_IMPORT_HTTP = re.compile(r'@import\s*[^;"]*(?:["\']\s*|url\s*\(\s*["\']?)\s*(?:https?:)?//', re.I)
_META_REFRESH = re.compile(r'<meta[^>]+http-equiv\s*=\s*["\']refresh["\']', re.I)

# --------------------------------------------------------------------- layout


def store_root(settings) -> Path:
    """The artifact directory. Under the data dir so export/delete covers it."""
    override = getattr(settings, 'sims_dir', None)
    return Path(override) if override else Path(settings.data_dir) / 'sims'


def manifest_path(settings) -> Path:
    return store_root(settings) / 'index.json'


def _load_manifest(settings) -> dict[str, dict[str, Any]]:
    path = manifest_path(settings)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (ValueError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_manifest(settings, manifest: dict[str, dict[str, Any]]) -> None:
    path = manifest_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding='utf-8')


def raw_url(artifact_id: str, version: int | None = None) -> str:
    """The serving URL for an artifact. The web layer's contract; see module docstring."""
    if version is None:
        return f'{RAW_URL_PREFIX}/{artifact_id}/raw'
    return f'{RAW_URL_PREFIX}/{artifact_id}/raw?version={int(version)}'


def load(settings, artifact_id: str) -> dict[str, Any] | None:
    """The manifest entry for one artifact, or ``None`` if the id is unknown."""
    entry = _load_manifest(settings).get(artifact_id)
    return dict(entry) if entry else None


def list_artifacts(settings, kind: str = '') -> list[dict[str, Any]]:
    """All artifacts, newest first, optionally filtered by kind."""
    rows = [e for e in _load_manifest(settings).values()
            if not kind or e.get('kind') == kind]
    rows.sort(key=lambda e: float(e.get('updated_at') or 0), reverse=True)
    return rows


# ------------------------------------------------------------------ validation


class _Wellformedness(HTMLParser):
    """Track tag balance. Lenient by design: the check exists to catch truncated or
    badly interleaved output from a model, not to enforce a markup standard."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.problems: list[str] = []
        self.stack: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag not in _VOID_ELEMENTS:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in _VOID_ELEMENTS:
            return
        if tag in self.stack:
            while self.stack and self.stack[-1] != tag:
                self.problems.append(f'<{self.stack.pop()}> was never closed')
            if self.stack:
                self.stack.pop()
        else:
            self.problems.append(f'</{tag}> closes a tag that is not open')


def validate_html(html: str, *, kind: str = 'simulation') -> list[str]:
    """Every reason this HTML may not be stored, or an empty list when it may.

    The reasons are returned, not raised, so a caller can show the authoring model (or
    the teacher) exactly what to fix. Deliberately a allowlist-shaped check: anything
    that would load an outside resource or execute dynamic code is refused with its
    reason, whatever the intention behind it.
    """
    problems: list[str] = []
    text = html or ''
    if not text.strip():
        return ['The artifact is empty.']
    if len(text) > 400_000:
        return [f'The artifact is {len(text)} bytes; the cap for one simulation is 400,000.']

    parser = _Wellformedness()
    try:
        parser.feed(text)
        parser.close()
    except Exception as exc:  # html.parser raises ValueError on malformed constructs
        problems.append(f'The HTML does not parse: {type(exc).__name__}: {exc}')
    for leftover in parser.stack:
        if leftover in {'html', 'body'}:
            problems.append(f'<{leftover}> was never closed')
    problems.extend(parser.problems)

    if kind == 'simulation':
        if not re.search(r'data-series\s*=', text):
            problems.append(
                'No element carries a data-series attribute. Interactive series must be '
                'tagged data-series="..." so the web UI\'s hover-highlight convention can '
                'find them.')

    for pattern, reason in (
            (_RESOURCE_ATTR, 'loads a resource from an outside host'),
            (_FETCH_HTTP, 'fetches or imports from an outside URL'),
            (_XHR, 'opens a raw network connection'),
            (_DYNAMIC_EVAL, 'uses eval or the Function constructor; a teaching artifact '
                            'has no legitimate use for dynamic code evaluation'),
            (_GLOBAL_BRACKET_EVAL, 'calls eval or the Function constructor through a '
                                   'bracketed string on globalThis/self/window; a '
                                   'teaching artifact has no legitimate use for '
                                   'dynamic code evaluation'),
            (_TIMER_STRING_ARG, 'passes a string of code to setTimeout or setInterval; '
                                'pass a function reference instead of a string'),
            (_CSS_IMPORT_HTTP, 'imports a stylesheet from an outside host via CSS '
                               '@import'),
            (_META_REFRESH, 'redirects via meta refresh')):
        match = pattern.search(text)
        if match:
            problems.append(f'The artifact {reason} ({match.group(0)[:60]!r}).')

    for form_action in re.finditer(r'<form[^>]+action\s*=\s*["\']([^"\']+)["\']', text, re.I):
        action = form_action.group(1)
        if re.match(r'https?:', action, re.I):
            problems.append(f'A form posts to an outside host ({action[:60]!r}).')
    return problems


# ----------------------------------------------------------------- diff summary


def diff_summary(old: str, new: str) -> dict[str, Any]:
    """A small, honest summary of what changed between two versions.

    Not a semantic diff — a byte-level one. It exists so the tool result can say
    "small, scoped edit" with numbers instead of asking anybody to believe it.
    """
    import difflib
    old_lines = (old or '').splitlines()
    new_lines = (new or '').splitlines()
    added = removed = 0
    for line in difflib.unified_diff(old_lines, new_lines, lineterm='', n=0):
        if line.startswith('+') and not line.startswith('+++'):
            added += 1
        elif line.startswith('-') and not line.startswith('---'):
            removed += 1
    kept = max(1, len(old_lines))
    return {'added_lines': added, 'removed_lines': removed,
            'old_bytes': len(old or ''), 'new_bytes': len(new or ''),
            'changed_fraction': round((added + removed) / kept, 4)}


# --------------------------------------------------------------------- writing


def _new_id(kind: str) -> str:
    prefix = 'sim' if kind == 'simulation' else 'deck'
    return f'{prefix}-{hashlib.sha256(str(time.time_ns()).encode()).hexdigest()[:12]}'


def create_artifact(settings, *, kind: str, title: str, html: str,
                    meta: Mapping[str, Any] | None = None,
                    files: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Store a validated artifact as version 1. Callers validate first.

    Layout: ``<root>/<artifact_id>/v1.html`` plus any extra files the caller recorded
    (a deck's .pptx), with the metadata in ``<root>/index.json``.
    """
    if kind not in KINDS:
        raise ValueError(f'Unknown artifact kind {kind!r}')
    artifact_id = _new_id(kind)
    root = store_root(settings) / artifact_id
    root.mkdir(parents=True, exist_ok=True)
    (root / 'v1.html').write_text(html, encoding='utf-8')
    now = time.time()
    entry: dict[str, Any] = {
        'id': artifact_id, 'kind': kind, 'title': title,
        'versions': [{'version': 1, 'file': 'v1.html', 'bytes': len(html),
                      'written_at': now, 'note': 'created',
                      **({'files': dict(files)} if files else {})}],
        'latest_version': 1, 'created_at': now, 'updated_at': now,
        'meta': dict(meta or {}),
    }
    manifest = _load_manifest(settings)
    manifest[artifact_id] = entry
    _save_manifest(settings, manifest)
    return entry


def save_version(settings, artifact_id: str, html: str, *, note: str = '',
                 files: Mapping[str, str] | None = None) -> dict[str, Any] | None:
    """Add a new version of an artifact, keeping every previous version on disk.

    Returns the updated entry, or ``None`` for an unknown id. The previous version file
    is deliberately untouched: reversion is reading an old file, not restoring one.
    """
    manifest = _load_manifest(settings)
    entry = manifest.get(artifact_id)
    if entry is None:
        return None
    version = int(entry['latest_version']) + 1
    root = store_root(settings) / artifact_id
    root.mkdir(parents=True, exist_ok=True)
    filename = f'v{version}.html'
    (root / filename).write_text(html, encoding='utf-8')
    now = time.time()
    record: dict[str, Any] = {'version': version, 'file': filename, 'bytes': len(html),
                              'written_at': now, 'note': note}
    if files:
        record['files'] = dict(files)
    entry['versions'].append(record)
    entry['latest_version'] = version
    entry['updated_at'] = now
    _save_manifest(settings, manifest)
    return entry


def read_version(settings, artifact_id: str, version: int | None = None) -> str | None:
    """The HTML of one version (latest when unspecified), or ``None``.

    This is the read path the web layer's ``/raw`` route is built on.
    """
    entry = load(settings, artifact_id)
    if entry is None:
        return None
    target = int(version if version is not None else entry['latest_version'])
    record = next((v for v in entry['versions'] if int(v['version']) == target), None)
    if record is None:
        return None
    path = store_root(settings) / artifact_id / str(record['file'])
    try:
        return path.read_text(encoding='utf-8')
    except OSError:
        return None


def latest_html(settings, artifact_id: str) -> str | None:
    """The currently served HTML. The ``/raw`` route's common case, named for it."""
    return read_version(settings, artifact_id, None)


def pending_approvals_path(settings) -> Path:
    return store_root(settings) / 'approvals.json'
