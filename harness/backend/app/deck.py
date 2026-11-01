"""The deck document and the real .pptx engine behind the slide editor.

The user's complaint was that the slide deck was "terrible" and that they wanted a
**1:1 PPTX tool inside the slide deck so the slide is actually a PPT**. That is what this
module is: a *document model* a client can edit, plus a bidirectional bridge to real
PowerPoint files.

What a deck is
--------------
A deck is a document: ``{id, title, theme, canvas, slides: [...]}``. Each slide is
``{id, layout, notes, background, elements: [...]}``. Each element is a positioned,
sized, styled box: ``{id, kind, x, y, w, h, rotation, z, style, ...}``.

Units
-----
Every coordinate in the document is in **points (pt), 1pt = 1/72 inch**, on a
**960pt x 540pt** canvas — that is 13.333in x 7.5in, the 16:9 widescreen slide. Points are
the natural unit for a slide editor: font sizes are already in points, so a 24pt headline
and a 24pt-tall margin are the same number, and the client never has to know about EMU.
The conversion to PowerPoint's EMU happens once, at the export boundary
(``1pt = 12700 EMU``), and back once at the import boundary. ``CANVAS`` records the size.

Why a document and not just an exporter
---------------------------------------
An exporter can only ever be a one-way trip: the deck is generated, rendered, and then
frozen. The complaint is precisely that a frozen deck cannot be corrected. So the deck is
the primary artifact and the .pptx is a projection of it — and, because a real product
must open a real .pptx a teacher already has, the projection runs both ways:
:func:`export_pptx` and :func:`import_pptx`.

What is deliberately honest here
--------------------------------
* **No headless browser.** A per-slide thumbnail is produced as **SVG built from the same
  document model** (:func:`slide_svg`) — real ``<text>`` with the real font family, size and
  colour, real shapes, and real images as data URIs. It needs no renderer and it is testable.
* **No invented pictures.** An image element references a content-addressed sha256 that the
  existing media store already serves; the same licence-cleared bytes are embedded in the
  .pptx and drawn in the SVG. There is no image model anywhere in this path.
* **python-pptx is optional at runtime.** :func:`export_pptx` and :func:`import_pptx` raise
  :class:`DeckUnavailable` when it is missing; the routes turn that into a structured
  refusal ``{"ok": False, "reason": ...}`` rather than a 500.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import math
import time
from io import BytesIO
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------- constants

#: The 16:9 slide canvas, in points. 960 x 540 pt == 13.333in x 7.5in.
CANVAS = {'w': 960.0, 'h': 540.0}

#: PowerPoint's English Metric Units per point. The one conversion this module owns.
EMU_PER_PT = 12700

#: The layout vocabulary. ``blank`` is the floor; the rest carry intent and a template
#: mapping. See :data:`TEMPLATE_LAYOUT` for how each is realised in a real .pptx.
LAYOUTS = ('title', 'section', 'idea', 'two_column', 'figure', 'caption', 'check', 'summary', 'blank')

#: Our layout name -> the name of a layout in the default python-pptx template. python-pptx
#: cannot author new slide masters without hand-editing package XML, which we deliberately do
#: not do; so each of our names binds to a real named template layout, and our own name is
#: recorded on the slide (``slide.name``) so it survives an export -> import round trip exactly.
TEMPLATE_LAYOUT = {
    'title': 'Title Slide',
    'section': 'Section Header',
    'idea': 'Title and Content',
    'two_column': 'Two Content',
    'figure': 'Picture with Caption',
    'caption': 'Content with Caption',
    'check': 'Title and Content',
    'summary': 'Title and Content',
    'blank': 'Blank',
}

#: Element kinds. Each has its own payload key below.
KINDS = ('text', 'image', 'shape', 'formula', 'table')

#: Shape primitives. ``polyline`` carries ``points`` (a freeform path).
SHAPES = ('rect', 'roundRect', 'ellipse', 'line', 'arrow', 'triangle', 'polyline')

#: Image fit modes. ``contain`` letterboxes, ``cover`` fills and crops, ``stretch`` distorts.
FITS = ('contain', 'cover', 'stretch')

ALIGNMENTS = ('left', 'center', 'right', 'justify')
ANCHORS = ('top', 'middle', 'bottom')

MAX_LEVEL = 4                 # bullet indent depth
MAX_SLIDES = 300
MAX_ELEMENTS = 400            # per slide
MAX_TEXT_CHARS = 8000         # per element
MAX_TITLE = 240
MAX_NOTES = 20000

#: The default theme. The fonts are the two every macOS install ships, so a deck authored
#: here opens looking the same on the machine it was authored on.
DEFAULT_THEME = {
    'name': 'Luminfest',
    'fonts': {'major': 'Helvetica Neue', 'minor': 'Helvetica Neue'},
    'colors': {
        'background': '#FFFFFF', 'text': '#24312A',
        'accent1': '#3E7A55', 'accent2': '#47519C', 'accent3': '#C46A3E',
        'accent4': '#7A3E8C', 'accent5': '#2F6E68', 'accent6': '#8F6A1F',
    },
}

DEFAULT_TEXT_STYLE = {
    'font': 'Helvetica Neue', 'size': 18, 'bold': False, 'italic': False,
    'underline': False, 'color': '#24312A', 'align': 'left', 'anchor': 'top',
    'line_spacing': 1.0, 'level': 0,
}

#: Presentation-layout names (from ``harness/presentation.py``) mapped onto ours, so a deck
#: built from the curriculum lands on the right layout without the curriculum knowing our
#: vocabulary.
PRESENTATION_LAYOUT = {
    'title': 'title', 'idea': 'idea', 'figure': 'figure',
    'check': 'check', 'summary': 'summary', 'section': 'section',
}


class DeckError(ValueError):
    """A deck operation was refused. ``reasons`` carries every reason, not just the first."""

    def __init__(self, message: str, reasons: list[str] | None = None):
        super().__init__(message)
        self.reasons = list(reasons or [])


class DeckUnavailable(RuntimeError):
    """A capability this deployment does not have (python-pptx is not importable)."""


# --------------------------------------------------------------------- small helpers


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _num(value: Any, default: float | None = None) -> float | None:
    if _finite(value):
        return round(float(value), 2)
    return default


def _new_id(prefix: str) -> str:
    return f'{prefix}-{hashlib.sha256(f"{time.time_ns()}-{id(object())}".encode()).hexdigest()[:12]}'


def _valid_deck_id(deck_id: str) -> bool:
    return bool(deck_id) and len(deck_id) <= 80 and all(c.isalnum() or c in '-_' for c in deck_id)


def _valid_sha(sha: Any) -> bool:
    return isinstance(sha, str) and len(sha) == 64 and all(c in '0123456789abcdef' for c in sha)


def normalise_color(value: Any) -> str | None:
    """``'#RRGGBB'`` (upper) from a hex string, or ``None`` when it is not a colour.

    Returns ``None`` rather than a default so a caller can *reject* a malformed colour
    instead of silently painting it something the author never chose.
    """
    if not isinstance(value, str):
        return None
    text = value.strip().lstrip('#')
    if len(text) not in (6, 8):
        return None
    if not all(c in '0123456789abcdefABCDEF' for c in text):
        return None
    return '#' + text[:6].upper()


def _pt(emu: Any) -> float:
    return round(float(emu) / EMU_PER_PT, 2)


# --------------------------------------------------------------------- construction


def new_deck(title: str = 'Untitled deck', *, theme: dict | None = None,
             owner_id: str = '') -> dict[str, Any]:
    """A fresh, valid, empty deck document."""
    now = time.time()
    return {
        'id': _new_id('deck'),
        'title': (str(title or 'Untitled deck'))[:MAX_TITLE] or 'Untitled deck',
        'theme': _normalise_theme(theme),
        'canvas': dict(CANVAS),
        'version': 1,
        'owner_id': owner_id,
        'created_at': now,
        'updated_at': now,
        'slides': [],
    }


def new_slide(layout: str = 'blank', *, notes: str = '',
              background: str | None = None) -> dict[str, Any]:
    return {
        'id': _new_id('slide'),
        'layout': layout if layout in LAYOUTS else 'blank',
        'notes': str(notes or '')[:MAX_NOTES],
        'background': normalise_color(background) if background else None,
        'elements': [],
    }


def new_text_element(x: float, y: float, w: float, h: float, text: str = '',
                     style: dict | None = None) -> dict[str, Any]:
    """A text box holding one paragraph, for the common "type a heading" gesture."""
    merged = {**DEFAULT_TEXT_STYLE, **(style or {})}
    return {
        'id': _new_id('el'), 'kind': 'text', 'x': x, 'y': y, 'w': w, 'h': h,
        'rotation': 0.0, 'z': 0, 'style': merged,
        'text': {'paragraphs': [{'runs': [{'text': str(text), 'style': {}}],
                                 'level': merged.get('level', 0),
                                 'align': merged.get('align', 'left'),
                                 'line_spacing': merged.get('line_spacing', 1.0)}]},
    }


# --------------------------------------------------------------------- normalisation


def _normalise_theme(theme: dict | None) -> dict[str, Any]:
    base = copy.deepcopy(DEFAULT_THEME)
    if not isinstance(theme, dict):
        return base
    if str(theme.get('name') or '').strip():
        base['name'] = str(theme['name'])[:80]
    fonts = theme.get('fonts')
    if isinstance(fonts, dict):
        for key in ('major', 'minor'):
            if str(fonts.get(key) or '').strip():
                base['fonts'][key] = str(fonts[key])[:120]
    colors = theme.get('colors')
    if isinstance(colors, dict):
        for key in base['colors']:
            normalised = normalise_color(colors.get(key))
            if normalised:
                base['colors'][key] = normalised
    return base


def _normalise_run(raw: Any, default_style: dict) -> dict[str, Any]:
    run = raw if isinstance(raw, dict) else {'text': raw}
    style = dict(default_style)
    incoming = run.get('style')
    if isinstance(incoming, dict):
        style.update(incoming)
    return {'text': str(run.get('text') or '')[:MAX_TEXT_CHARS], 'style': style}


def _normalise_paragraph(raw: Any, default_style: dict) -> dict[str, Any]:
    para = raw if isinstance(raw, dict) else {'runs': [{'text': raw}]}
    runs = para.get('runs')
    if not isinstance(runs, list) or not runs:
        runs = [{'text': para.get('text') or ''}]
    return {
        'runs': [_normalise_run(r, default_style) for r in runs],
        'level': para.get('level', default_style.get('level', 0)),
        'align': para.get('align', default_style.get('align', 'left')),
        'line_spacing': para.get('line_spacing', default_style.get('line_spacing', 1.0)),
        'space_after': para.get('space_after', 0),
    }


def _normalise_text(raw: Any, default_style: dict) -> dict[str, Any]:
    body = raw if isinstance(raw, dict) else {'paragraphs': [{'runs': [{'text': raw}]}]}
    paras = body.get('paragraphs')
    if not isinstance(paras, list) or not paras:
        paras = [{'runs': [{'text': ''}]}]
    return {'paragraphs': [_normalise_paragraph(p, default_style) for p in paras]}


def _normalise_element(raw: Any) -> dict[str, Any]:
    """Fill an element's optional structure in. Does not clamp geometry: a negative size
    is a refusal (see :func:`validate_element`), never silently corrected."""
    elem = dict(raw) if isinstance(raw, dict) else {}
    kind = str(elem.get('kind') or 'text')
    style = dict(DEFAULT_TEXT_STYLE)
    if isinstance(elem.get('style'), dict):
        style.update(elem['style'])
    out: dict[str, Any] = {
        'id': str(elem.get('id') or _new_id('el')),
        'kind': kind,
        'x': _num(elem.get('x'), 0.0),
        'y': _num(elem.get('y'), 0.0),
        'w': _num(elem.get('w'), 0.0),
        'h': _num(elem.get('h'), 0.0),
        'rotation': _num(elem.get('rotation'), 0.0),
        'z': int(elem['z']) if isinstance(elem.get('z'), int) else 0,
        'style': style,
    }
    if kind in ('text', 'formula'):
        out['text'] = _normalise_text(elem.get('text'), style)
    if kind == 'shape':
        out['shape'] = str(elem.get('shape') or 'rect')
        points = elem.get('points')
        if isinstance(points, list):
            out['points'] = [[_num(p[0], 0.0), _num(p[1], 0.0)]
                             for p in points if isinstance(p, (list, tuple)) and len(p) >= 2]
    if kind == 'image':
        image = elem.get('image') if isinstance(elem.get('image'), dict) else {}
        out['image'] = {
            'sha256': str(image.get('sha256') or ''),
            'fit': str(image.get('fit') or 'contain'),
            'crop': image.get('crop') if isinstance(image.get('crop'), dict) else None,
            'alt': str(image.get('alt') or '')[:300],
            'attribution': str(image.get('attribution') or '')[:300],
        }
    if kind == 'table':
        table = elem.get('table') if isinstance(elem.get('table'), dict) else {}
        rows = table.get('rows') if isinstance(table.get('rows'), list) else []
        out['table'] = {
            'rows': [[str(cell)[:500] for cell in row] if isinstance(row, list) else [str(row)[:500]]
                     for row in rows],
            'col_widths': table.get('col_widths') if isinstance(table.get('col_widths'), list) else [],
        }
    return out


def _normalise_slide(raw: Any) -> dict[str, Any]:
    slide = dict(raw) if isinstance(raw, dict) else {}
    elements = slide.get('elements')
    elements = elements if isinstance(elements, list) else []
    return {
        'id': str(slide.get('id') or _new_id('slide')),
        'layout': str(slide.get('layout') or 'blank'),
        'notes': str(slide.get('notes') or '')[:MAX_NOTES],
        'background': normalise_color(slide.get('background')) if slide.get('background') else None,
        'elements': [_normalise_element(e) for e in elements],
    }


def normalise_document(doc: Any, *, owner_id: str | None = None) -> dict[str, Any]:
    """A complete document with ids assigned and defaults filled.

    Idempotent: normalising an already-normal document returns an equal document. It never
    repairs a malformed value — that is :func:`validate_document`'s job, and the caller
    decides whether to refuse.
    """
    source = dict(doc) if isinstance(doc, dict) else {}
    slides = source.get('slides')
    slides = slides if isinstance(slides, list) else []
    now = time.time()
    out: dict[str, Any] = {
        'id': str(source.get('id') or _new_id('deck')),
        'title': str(source.get('title') or 'Untitled deck')[:MAX_TITLE] or 'Untitled deck',
        'theme': _normalise_theme(source.get('theme')),
        'canvas': dict(CANVAS),
        'version': int(source['version']) if isinstance(source.get('version'), int) else 1,
        'owner_id': owner_id if owner_id is not None else str(source.get('owner_id') or ''),
        'created_at': _num(source.get('created_at'), now) or now,
        'updated_at': _num(source.get('updated_at'), now) or now,
        'slides': [_normalise_slide(s) for s in slides],
    }
    return out


# --------------------------------------------------------------------- validation


def validate_element(elem: dict, *, where: str = 'element') -> list[str]:
    """Every reason this element is not storable. Empty list means it is."""
    problems: list[str] = []
    kind = elem.get('kind')
    if kind not in KINDS:
        problems.append(f'{where}: unknown kind {kind!r}; expected one of {", ".join(KINDS)}.')
    for key in ('x', 'y', 'w', 'h'):
        if not _finite(elem.get(key)):
            problems.append(f'{where}: {key} must be a finite number.')
    if _finite(elem.get('w')) and elem['w'] <= 0:
        problems.append(f'{where}: w must be positive, got {elem["w"]}.')
    if _finite(elem.get('h')) and elem['h'] <= 0:
        problems.append(f'{where}: h must be positive, got {elem["h"]}.')
    rotation = elem.get('rotation')
    if rotation is not None and not _finite(rotation):
        problems.append(f'{where}: rotation must be a finite number.')

    style = elem.get('style') if isinstance(elem.get('style'), dict) else {}
    if 'color' in style and normalise_color(style.get('color')) is None:
        problems.append(f'{where}: style.color must be a hex colour such as #24312A.')
    if 'fill' in style and style.get('fill') is not None and normalise_color(style.get('fill')) is None:
        problems.append(f'{where}: style.fill must be a hex colour or null.')
    if 'stroke' in style and style.get('stroke') is not None and normalise_color(style.get('stroke')) is None:
        problems.append(f'{where}: style.stroke must be a hex colour or null.')
    if 'size' in style and not (_finite(style.get('size')) and 1 <= style['size'] <= 400):
        problems.append(f'{where}: style.size must be between 1 and 400 points.')
    if style.get('align') not in (None, *ALIGNMENTS):
        problems.append(f'{where}: style.align must be one of {", ".join(ALIGNMENTS)}.')
    if style.get('anchor') not in (None, *ANCHORS):
        problems.append(f'{where}: style.anchor must be one of {", ".join(ANCHORS)}.')

    if kind in ('text', 'formula'):
        text = elem.get('text')
        if not isinstance(text, dict) or not isinstance(text.get('paragraphs'), list):
            problems.append(f'{where}: a {kind} element needs text.paragraphs.')
        else:
            total = 0
            for pi, para in enumerate(text['paragraphs']):
                if not isinstance(para, dict):
                    problems.append(f'{where}: paragraph {pi} must be an object.')
                    continue
                level = para.get('level', 0)
                if not isinstance(level, int) or not 0 <= level <= MAX_LEVEL:
                    problems.append(f'{where}: paragraph {pi} level must be an integer 0-{MAX_LEVEL}.')
                if para.get('align') not in (None, *ALIGNMENTS):
                    problems.append(f'{where}: paragraph {pi} align must be one of {", ".join(ALIGNMENTS)}.')
                runs = para.get('runs')
                if not isinstance(runs, list):
                    problems.append(f'{where}: paragraph {pi} runs must be a list.')
                    continue
                for run in runs:
                    total += len(str((run or {}).get('text') or ''))
            if total > MAX_TEXT_CHARS:
                problems.append(f'{where}: text is {total} characters; the cap is {MAX_TEXT_CHARS}.')

    if kind == 'shape':
        if elem.get('shape') not in SHAPES:
            problems.append(f'{where}: shape must be one of {", ".join(SHAPES)}.')
        if elem.get('shape') == 'polyline':
            points = elem.get('points')
            if not isinstance(points, list) or len(points) < 2:
                problems.append(f'{where}: a polyline needs at least two points.')

    if kind == 'image':
        image = elem.get('image') if isinstance(elem.get('image'), dict) else {}
        if not _valid_sha(image.get('sha256')):
            problems.append(f'{where}: image.sha256 must be a 64-character hex content hash.')
        if image.get('fit') not in FITS:
            problems.append(f'{where}: image.fit must be one of {", ".join(FITS)}.')
        crop = image.get('crop')
        if crop is not None:
            for key in ('l', 't', 'r', 'b'):
                value = crop.get(key, 0)
                if not _finite(value) or not 0 <= value < 1:
                    problems.append(f'{where}: image.crop.{key} must be a fraction in [0, 1).')

    if kind == 'table':
        table = elem.get('table') if isinstance(elem.get('table'), dict) else {}
        rows = table.get('rows')
        if not isinstance(rows, list) or not rows or not any(rows):
            problems.append(f'{where}: a table needs at least one non-empty row.')
        elif any(len(row) != len(rows[0]) for row in rows):
            problems.append(f'{where}: every table row must have the same number of cells.')

    return problems


def validate_document(doc: dict) -> list[str]:
    """Every reason this deck may not be stored, or an empty list when it may."""
    problems: list[str] = []
    if not isinstance(doc, dict):
        return ['The deck must be an object.']
    if not str(doc.get('title') or '').strip():
        problems.append('The deck needs a title.')
    slides = doc.get('slides')
    if not isinstance(slides, list):
        return ['The deck needs a slides list.']
    if len(slides) > MAX_SLIDES:
        problems.append(f'The deck has {len(slides)} slides; the cap is {MAX_SLIDES}.')
    seen_slides: set[str] = set()
    for si, slide in enumerate(slides):
        if not isinstance(slide, dict):
            problems.append(f'slide {si}: must be an object.')
            continue
        sid = str(slide.get('id') or '')
        if not sid:
            problems.append(f'slide {si}: needs an id.')
        elif sid in seen_slides:
            problems.append(f'slide {si}: duplicate id {sid!r}.')
        seen_slides.add(sid)
        if slide.get('layout') not in LAYOUTS:
            problems.append(f'slide {si}: layout must be one of {", ".join(LAYOUTS)}.')
        if slide.get('background') is not None and normalise_color(slide['background']) is None:
            problems.append(f'slide {si}: background must be a hex colour or null.')
        elements = slide.get('elements')
        if not isinstance(elements, list):
            problems.append(f'slide {si}: needs an elements list.')
            continue
        if len(elements) > MAX_ELEMENTS:
            problems.append(f'slide {si}: {len(elements)} elements; the cap is {MAX_ELEMENTS}.')
        seen_elems: set[str] = set()
        for ei, elem in enumerate(elements):
            if not isinstance(elem, dict):
                problems.append(f'slide {si} element {ei}: must be an object.')
                continue
            eid = str(elem.get('id') or '')
            if not eid:
                problems.append(f'slide {si} element {ei}: needs an id.')
            elif eid in seen_elems:
                problems.append(f'slide {si} element {ei}: duplicate id {eid!r}.')
            seen_elems.add(eid)
            problems.extend(validate_element(elem, where=f'slide {si} element {ei}'))
    return problems


def require_valid(doc: dict) -> dict:
    """Return the document when it is valid, else raise :class:`DeckError` with reasons."""
    problems = validate_document(doc)
    if problems:
        raise DeckError('The deck was not stored; it failed validation.', problems)
    return doc


# --------------------------------------------------------------------- element ops


def _ordered(elements: list[dict]) -> list[dict]:
    """Elements in paint order: ``z`` ascending, then document order. A stable sort keeps a
    tie reading as the author's own order rather than an arbitrary one."""
    return sorted(elements, key=lambda e: e.get('z', 0))


def next_z(elements: list[dict]) -> int:
    return (max((int(e.get('z') or 0) for e in elements), default=-1) + 1)


def find_slide(doc: dict, slide_id: str) -> dict | None:
    return next((s for s in doc['slides'] if s['id'] == slide_id), None)


def find_element(doc: dict, element_id: str) -> tuple[dict, dict] | None:
    for slide in doc['slides']:
        for elem in slide['elements']:
            if elem['id'] == element_id:
                return slide, elem
    return None


def add_slide(doc: dict, *, layout: str = 'blank', notes: str = '',
              index: int | None = None) -> dict:
    if layout not in LAYOUTS:
        raise DeckError(f'Unknown layout {layout!r}.', [f'layout must be one of {", ".join(LAYOUTS)}.'])
    slide = new_slide(layout, notes=notes)
    if index is None or index >= len(doc['slides']):
        doc['slides'].append(slide)
    else:
        doc['slides'].insert(max(0, int(index)), slide)
    doc['updated_at'] = time.time()
    return slide


def delete_slide(doc: dict, slide_id: str) -> bool:
    before = len(doc['slides'])
    doc['slides'] = [s for s in doc['slides'] if s['id'] != slide_id]
    doc['updated_at'] = time.time()
    return len(doc['slides']) != before


def move_slide(doc: dict, slide_id: str, to_index: int) -> bool:
    index = next((i for i, s in enumerate(doc['slides']) if s['id'] == slide_id), None)
    if index is None:
        return False
    slide = doc['slides'].pop(index)
    doc['slides'].insert(max(0, min(int(to_index), len(doc['slides']))), slide)
    doc['updated_at'] = time.time()
    return True


def duplicate_slide(doc: dict, slide_id: str) -> dict | None:
    index = next((i for i, s in enumerate(doc['slides']) if s['id'] == slide_id), None)
    if index is None:
        return None
    clone = copy.deepcopy(doc['slides'][index])
    clone['id'] = _new_id('slide')
    for elem in clone['elements']:      # ids must be unique across the deck
        elem['id'] = _new_id('el')
    doc['slides'].insert(index + 1, clone)
    doc['updated_at'] = time.time()
    return clone


def patch_slide(doc: dict, slide_id: str, patch: dict) -> dict | None:
    slide = find_slide(doc, slide_id)
    if slide is None:
        return None
    for key in ('layout', 'notes', 'background'):
        if key in patch:
            slide[key] = patch[key]
    doc['updated_at'] = time.time()
    return slide


def add_element(doc: dict, slide_id: str, raw: dict) -> dict:
    slide = find_slide(doc, slide_id)
    if slide is None:
        raise DeckError('No such slide.')
    elem = _normalise_element(raw)
    if elem.get('z', 0) == 0:
        elem['z'] = next_z(slide['elements'])
    problems = validate_element(elem, where='element')
    if problems:
        raise DeckError('The element was not added; it failed validation.', problems)
    slide['elements'].append(elem)
    doc['updated_at'] = time.time()
    return elem


def patch_element(doc: dict, element_id: str, patch: dict) -> dict | None:
    found = find_element(doc, element_id)
    if found is None:
        return None
    _, elem = found
    merged = copy.deepcopy(elem)
    for key, value in patch.items():
        if key == 'id':
            continue                      # identity is the server's, never the payload's
        if key == 'style' and isinstance(value, dict):
            merged['style'] = {**merged.get('style', {}), **value}
        elif key == 'image' and isinstance(value, dict):
            merged['image'] = {**merged.get('image', {}), **value}
        else:
            merged[key] = value
    merged = _normalise_element(merged)
    merged['id'] = elem['id']
    problems = validate_element(merged, where='element')
    if problems:
        raise DeckError('The element was not updated; it failed validation.', problems)
    elem.clear()
    elem.update(merged)
    doc['updated_at'] = time.time()
    return elem


def delete_element(doc: dict, element_id: str) -> bool:
    for slide in doc['slides']:
        before = len(slide['elements'])
        slide['elements'] = [e for e in slide['elements'] if e['id'] != element_id]
        if len(slide['elements']) != before:
            doc['updated_at'] = time.time()
            return True
    return False


def referenced_images(doc: dict) -> list[str]:
    """Every image sha the deck references, in first-use order, de-duplicated."""
    seen: list[str] = []
    for slide in doc.get('slides', []):
        for elem in slide.get('elements', []):
            if elem.get('kind') == 'image':
                sha = (elem.get('image') or {}).get('sha256')
                if _valid_sha(sha) and sha not in seen:
                    seen.append(sha)
    return seen


# --------------------------------------------------------------------- persistence
#
# One JSON file per deck under ``<data_dir>/decks/``, exactly like ``harness/board.py``.
# A deck is a document a client rewrites wholesale, so the file *is* the record; a
# relational row would only add a serialisation layer between the document and its bytes.
# Ownership is a field on the document and is re-checked on every read, so a deck that is
# not yours is a 404 (existence is never disclosed).


def deck_root(settings) -> Path:
    return Path(settings.data_dir) / 'decks'


def _deck_path(settings, deck_id: str) -> Path:
    return deck_root(settings) / f'{deck_id}.json'


def save_deck(settings, doc: dict) -> dict:
    """Persist a document. Writes atomically (tmp + replace) so a crash mid-write cannot
    leave a half-written deck behind."""
    deck_id = str(doc.get('id') or '')
    if not _valid_deck_id(deck_id):
        raise DeckError('Invalid deck id.')
    root = deck_root(settings)
    root.mkdir(parents=True, exist_ok=True)
    doc['updated_at'] = time.time()
    payload = json.dumps(doc, ensure_ascii=False)
    tmp = root / f'.{deck_id}.tmp'
    tmp.write_text(payload, encoding='utf-8')
    tmp.replace(_deck_path(settings, deck_id))
    return doc


def load_deck(settings, deck_id: str, *, owner_id: str | None = None) -> dict | None:
    """The document, or ``None``. When ``owner_id`` is given, a deck owned by anyone else
    is ``None`` — the same answer as a deck that does not exist."""
    if not _valid_deck_id(deck_id):
        return None
    path = _deck_path(settings, deck_id)
    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text(encoding='utf-8'))
    except (ValueError, OSError):
        return None
    if not isinstance(doc, dict):
        return None
    if owner_id is not None and str(doc.get('owner_id') or '') != owner_id:
        return None
    return doc


def list_decks(settings, owner_id: str) -> list[dict]:
    """This account's decks, newest first, as light summaries."""
    root = deck_root(settings)
    if not root.is_dir():
        return []
    rows: list[dict] = []
    for path in root.glob('*.json'):
        try:
            doc = json.loads(path.read_text(encoding='utf-8'))
        except (ValueError, OSError):
            continue
        if not isinstance(doc, dict) or str(doc.get('owner_id') or '') != owner_id:
            continue
        rows.append({'id': doc.get('id'), 'title': doc.get('title', ''),
                     'slides': len(doc.get('slides') or []),
                     'updated_at': doc.get('updated_at'), 'created_at': doc.get('created_at')})
    rows.sort(key=lambda r: float(r.get('updated_at') or 0), reverse=True)
    return rows


def create_deck(settings, doc: dict, *, owner_id: str) -> dict:
    doc = normalise_document(doc, owner_id=owner_id)
    require_valid(doc)
    return save_deck(settings, doc)


def delete_deck(settings, deck_id: str, *, owner_id: str) -> bool:
    doc = load_deck(settings, deck_id, owner_id=owner_id)
    if doc is None:
        return False
    path = _deck_path(settings, deck_id)
    if path.is_file():
        path.unlink()
    return True


# --------------------------------------------------------------------- images


def image_path(settings, sha: str) -> Path | None:
    """The cached file for a content hash, through the media store's own index."""
    from .harness import board as node_boards
    return node_boards.image_file(settings, sha)


def image_bytes(settings, sha: str) -> bytes | None:
    path = image_path(settings, sha)
    if path is None:
        return None
    try:
        return path.read_bytes()
    except OSError:
        return None


def _image_mime(path: Path) -> str:
    return {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
            '.webp': 'image/webp', '.gif': 'image/gif'}.get(path.suffix.lower(), 'image/jpeg')


def deck_images(settings, doc: dict) -> list[dict]:
    """The images the deck references, each with the attribution the media store holds.

    An image whose sha is no longer in the media index is reported with ``resolved: False``
    rather than dropped, so the client can show the hole instead of silently rendering nothing.
    """
    from .harness import media
    index = {row.get('sha256'): row for row in media.cached_assets(settings)}
    out: list[dict] = []
    for sha in referenced_images(doc):
        row = index.get(sha) or {}
        path = image_path(settings, sha)
        out.append({
            'sha256': sha,
            'resolved': path is not None,
            'bytes_url': f'/api/v1/media/images/{sha}/bytes',
            'mime': _image_mime(path) if path else '',
            'bytes': path.stat().st_size if path else 0,
            'title': row.get('title', ''), 'source': row.get('source', ''),
            'creator': row.get('creator', ''), 'licence': row.get('licence_code', ''),
            'licence_class': row.get('licence_class', ''),
            'licence_url': row.get('licence_url', ''),
            'attribution': row.get('attribution_text', ''),
            'source_page': row.get('landing_page_url', ''),
        })
    return out


# --------------------------------------------------------------------- SVG thumbnail
#
# Built from the document model, not from the .pptx, so it needs no renderer and it can be
# tested. Text is real <text> with the real family/size/colour; images are data URIs of the
# same bytes the .pptx embeds. The SVG is a *view of the model*, never a second source of
# truth.

_SVG_ESCAPE = {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}


def _esc(value: Any) -> str:
    return ''.join(_SVG_ESCAPE.get(c, c) for c in str(value or ''))


def _svg_align(align: str) -> str:
    return {'left': 'start', 'center': 'middle', 'right': 'end', 'justify': 'start'}.get(align, 'start')


def slide_svg(settings, doc: dict, slide_id: str) -> str | None:
    """A deterministic SVG of one slide, or ``None`` when the slide is unknown."""
    slide = find_slide(doc, slide_id)
    if slide is None:
        return None
    theme = doc.get('theme') or DEFAULT_THEME
    background = normalise_color(slide.get('background')) or normalise_color(
        (theme.get('colors') or {}).get('background')) or '#FFFFFF'
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 {int(CANVAS["w"])} {int(CANVAS["h"])}" '
        f'width="{int(CANVAS["w"])}" height="{int(CANVAS["h"])}" role="img">',
        f'<rect x="0" y="0" width="{int(CANVAS["w"])}" height="{int(CANVAS["h"])}" fill="{background}"/>',
    ]
    for elem in _ordered(slide['elements']):
        parts.append(_svg_element(settings, elem))
    parts.append('</svg>')
    return '\n'.join(p for p in parts if p)


def _svg_element(settings, elem: dict) -> str:
    kind = elem.get('kind')
    x, y, w, h = elem['x'], elem['y'], elem['w'], elem['h']
    style = elem.get('style') or {}
    fill = normalise_color(style.get('fill')) if style.get('fill') else None
    stroke = normalise_color(style.get('stroke')) if style.get('stroke') else None
    stroke_width = _num(style.get('stroke_width'), 1.0) or 1.0
    transform = f' transform="rotate({elem.get("rotation", 0)} {x + w / 2} {y + h / 2})"' \
        if elem.get('rotation') else ''

    if kind in ('text', 'formula'):
        return _svg_text(elem, transform, fill)
    if kind == 'image':
        return _svg_image(settings, elem, transform)
    if kind == 'table':
        return _svg_table(elem, transform, stroke)
    if kind == 'shape':
        shape = elem.get('shape')
        paint = f'fill="{fill or "none"}" stroke="{stroke or "none"}" stroke-width="{stroke_width}"'
        if shape in ('rect', 'roundRect'):
            radius = _num(style.get('radius'), 12.0) or 0.0
            rx = f' rx="{radius}"' if shape == 'roundRect' else ''
            return f'<rect x="{x}" y="{y}" width="{w}" height="{h}"{rx} {paint}{transform}/>'
        if shape == 'ellipse':
            return (f'<ellipse cx="{x + w / 2}" cy="{y + h / 2}" rx="{w / 2}" ry="{h / 2}" '
                    f'{paint}{transform}/>')
        if shape == 'triangle':
            points = f'{x + w / 2},{y} {x + w},{y + h} {x},{y + h}'
            return f'<polygon points="{points}" {paint}{transform}/>'
        if shape in ('line', 'arrow'):
            marker = ' marker-end="url(#arrowhead)"' if shape == 'arrow' else ''
            return (f'<line x1="{x}" y1="{y}" x2="{x + w}" y2="{y + h}" '
                    f'stroke="{stroke or "#24312A"}" stroke-width="{stroke_width}"{marker}{transform}/>')
        if shape == 'polyline':
            points = ' '.join(f'{p[0]},{p[1]}' for p in elem.get('points', []))
            return (f'<polyline points="{points}" fill="none" stroke="{stroke or "#24312A"}" '
                    f'stroke-width="{stroke_width}"{transform}/>')
    return ''


def _svg_text(elem: dict, transform: str, fill: str | None) -> str:
    style = elem.get('style') or {}
    size = _num(style.get('size'), 18.0) or 18.0
    color = normalise_color(style.get('color')) or '#24312A'
    anchor = _svg_align(str(style.get('align') or 'left'))
    anchor_x = {'start': elem['x'], 'middle': elem['x'] + elem['w'] / 2,
                'end': elem['x'] + elem['w']}[anchor]
    weight = '700' if style.get('bold') else '400'
    italic = ' font-style="italic"' if style.get('italic') else ''
    decoration = ' text-decoration="underline"' if style.get('underline') else ''
    lines = []
    cursor = elem['y'] + size            # first baseline sits one em below the box top
    for para in (elem.get('text') or {}).get('paragraphs', []):
        text = ''.join(str((r or {}).get('text') or '') for r in para.get('runs', []))
        indent = 14 * int(para.get('level') or 0)
        line_spacing = _num(para.get('line_spacing'), 1.0) or 1.0
        lines.append(
            f'<text x="{anchor_x + indent}" y="{cursor}" font-family="{_esc(style.get("font") or "Helvetica Neue")}" '
            f'font-size="{size}" font-weight="{weight}"{italic}{decoration} fill="{color}" '
            f'text-anchor="{anchor}"{transform}>{_esc(text)}</text>')
        cursor += size * line_spacing * 1.25
    return '\n'.join(lines)


def _svg_image(settings, elem: dict, transform: str) -> str:
    image = elem.get('image') or {}
    sha = image.get('sha256')
    path = image_path(settings, sha) if _valid_sha(sha) else None
    if path is None:
        return (f'<rect x="{elem["x"]}" y="{elem["y"]}" width="{elem["w"]}" height="{elem["h"]}" '
                f'fill="#ECEDDF" stroke="#DFE2D6"{transform}/>'
                f'<text x="{elem["x"] + 8}" y="{elem["y"] + 20}" font-size="12" fill="#5C6A60">'
                f'{_esc(image.get("alt") or "image unavailable")}</text>')
    data = base64.b64encode(path.read_bytes()).decode('ascii')
    return (f'<image href="data:{_image_mime(path)};base64,{data}" x="{elem["x"]}" y="{elem["y"]}" '
            f'width="{elem["w"]}" height="{elem["h"]}" preserveAspectRatio="xMidYMid slice"{transform}/>')


def _svg_table(elem: dict, transform: str, stroke: str | None) -> str:
    rows = (elem.get('table') or {}).get('rows') or []
    if not rows:
        return ''
    cols = len(rows[0])
    row_h = elem['h'] / len(rows)
    col_w = elem['w'] / cols
    style = elem.get('style') or {}
    size = _num(style.get('size'), 14.0) or 14.0
    out = [f'<rect x="{elem["x"]}" y="{elem["y"]}" width="{elem["w"]}" height="{elem["h"]}" '
           f'fill="none" stroke="{stroke or "#DFE2D6"}" stroke-width="1"{transform}/>']
    for ri, row in enumerate(rows):
        for ci, cell in enumerate(row):
            cx, cy = elem['x'] + ci * col_w, elem['y'] + ri * row_h
            out.append(f'<rect x="{cx}" y="{cy}" width="{col_w}" height="{row_h}" fill="none" '
                       f'stroke="{stroke or "#DFE2D6"}" stroke-width="0.5"/>')
            out.append(f'<text x="{cx + 6}" y="{cy + row_h / 2 + size / 3}" font-size="{size}" '
                       f'fill="#24312A">{_esc(cell)}</text>')
    return '\n'.join(out)


# --------------------------------------------------------------------- .pptx export


def _pptx_module():
    """The python-pptx entry points, or raise :class:`DeckUnavailable`."""
    try:
        from pptx import Presentation  # noqa: F401
        from pptx.dml.color import RGBColor  # noqa: F401
        from pptx.enum.shapes import MSO_SHAPE  # noqa: F401
        from pptx.enum.text import MSO_ANCHOR, PP_ALIGN  # noqa: F401
        from pptx.util import Pt  # noqa: F401
    except Exception as exc:  # ImportError, and any broken install behind it
        raise DeckUnavailable(
            'python-pptx is not available in this deployment, so a real .pptx cannot be '
            f'written or read ({type(exc).__name__}). The SVG slide view and the JSON '
            'document are unaffected.') from exc
    import pptx
    return pptx


def pptx_available() -> bool:
    try:
        _pptx_module()
        return True
    except DeckUnavailable:
        return False


def export_pptx(settings, doc: dict) -> bytes:
    """Render the document as a real .pptx: real size, runs, pictures, shapes and notes.

    Raises :class:`DeckUnavailable` when python-pptx is absent.
    """
    _pptx_module()
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
    from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
    from pptx.util import Pt

    presentation = Presentation()
    presentation.slide_width = Pt(CANVAS['w'])
    presentation.slide_height = Pt(CANVAS['h'])
    _apply_theme(presentation, doc.get('theme') or DEFAULT_THEME)

    layout_index = {name: i for i, name in enumerate(
        l.name for l in presentation.slide_layouts)}

    for slide in doc['slides']:
        template_name = TEMPLATE_LAYOUT.get(slide.get('layout'), 'Blank')
        layout = presentation.slide_layouts[layout_index.get(template_name, 6)]
        target = presentation.slides.add_slide(layout)
        target.name = slide.get('layout', 'blank')
        # The template layout's placeholders are unused: every element is placed explicitly.
        # Leaving them would put two empty boxes on every slide.
        for placeholder in list(target.placeholders):
            placeholder._element.getparent().remove(placeholder._element)

        background = normalise_color(slide.get('background'))
        if background:
            target.background.fill.solid()
            target.background.fill.fore_color.rgb = RGBColor.from_string(background.lstrip('#'))

        for elem in _ordered(slide['elements']):
            _export_element(settings, target, elem, Pt, RGBColor, MSO_SHAPE, MSO_CONNECTOR,
                            MSO_ANCHOR, PP_ALIGN)

        notes = str(slide.get('notes') or '')
        if notes:
            target.notes_slide.notes_text_frame.text = notes

    buffer = BytesIO()
    presentation.save(buffer)
    return buffer.getvalue()


_ALIGN_TO_PPTX = {'left': 'LEFT', 'center': 'CENTER', 'right': 'RIGHT', 'justify': 'JUSTIFY'}
_ANCHOR_TO_PPTX = {'top': 'TOP', 'middle': 'MIDDLE', 'bottom': 'BOTTOM'}


def _export_element(settings, slide, elem, Pt, RGBColor, MSO_SHAPE, MSO_CONNECTOR,
                    MSO_ANCHOR, PP_ALIGN) -> None:
    kind = elem['kind']
    if kind in ('text', 'formula'):
        box = slide.shapes.add_textbox(Pt(elem['x']), Pt(elem['y']), Pt(elem['w']), Pt(elem['h']))
        _style_box(box, elem, RGBColor)
        if elem.get('rotation'):
            box.rotation = float(elem['rotation'])
        frame = box.text_frame
        frame.word_wrap = True
        style = elem.get('style') or {}
        frame.vertical_anchor = getattr(MSO_ANCHOR, _ANCHOR_TO_PPTX.get(style.get('anchor'), 'TOP'))
        for pi, para in enumerate((elem.get('text') or {}).get('paragraphs', [])):
            target = frame.paragraphs[0] if pi == 0 else frame.add_paragraph()
            target.level = int(para.get('level') or 0)
            align = para.get('align') or style.get('align') or 'left'
            target.alignment = getattr(PP_ALIGN, _ALIGN_TO_PPTX.get(align, 'LEFT'))
            spacing = _num(para.get('line_spacing'), style.get('line_spacing', 1.0)) or 1.0
            target.line_spacing = float(spacing)
            for run in para.get('runs', []):
                r = target.add_run()
                r.text = str(run.get('text') or '')
                _style_run(r, run.get('style') or style, RGBColor, Pt)
        return

    if kind == 'image':
        data = image_bytes(settings, (elem.get('image') or {}).get('sha256', ''))
        if not data:
            _export_missing_image(slide, elem, Pt, RGBColor)
            return
        picture = _export_picture(slide, elem, data, Pt)
        if elem.get('rotation'):
            picture.rotation = float(elem['rotation'])
        alt = (elem.get('image') or {}).get('alt') or (elem.get('image') or {}).get('attribution')
        if alt:
            picture._element._nvXxPr.cNvPr.set('descr', str(alt)[:300])
        return

    if kind == 'shape':
        _export_shape(slide, elem, Pt, RGBColor, MSO_SHAPE, MSO_CONNECTOR)
        return

    if kind == 'table':
        rows = (elem.get('table') or {}).get('rows') or []
        if not rows:
            return
        cols = len(rows[0])
        shape = slide.shapes.add_table(len(rows), cols, Pt(elem['x']), Pt(elem['y']),
                                       Pt(elem['w']), Pt(elem['h']))
        table = shape.table
        for ri, row in enumerate(rows):
            for ci, cell in enumerate(row):
                frame = table.cell(ri, ci).text_frame
                frame.text = str(cell)
                for p in frame.paragraphs:
                    for run in p.runs:
                        _style_run(run, elem.get('style') or {}, RGBColor, Pt)
        return


def _export_picture(slide, elem, data: bytes, Pt):
    """Place an image honouring its fit mode. ``cover`` crops the source; ``contain``
    letterboxes by scaling to fit and centring; ``stretch`` fills the box exactly."""
    image = elem.get('image') or {}
    fit = image.get('fit') or 'contain'
    x, y, w, h = elem['x'], elem['y'], elem['w'], elem['h']
    stream = BytesIO(data)
    if fit == 'stretch':
        return slide.shapes.add_picture(stream, Pt(x), Pt(y), Pt(w), Pt(h))

    width, height = _image_size(data)
    if width <= 0 or height <= 0:
        return slide.shapes.add_picture(stream, Pt(x), Pt(y), Pt(w), Pt(h))
    scale = (max(w / width, h / height) if fit == 'cover' else min(w / width, h / height))
    drawn_w, drawn_h = width * scale, height * scale
    picture = slide.shapes.add_picture(stream, Pt(x), Pt(y), Pt(drawn_w), Pt(drawn_h))
    if fit == 'contain':
        picture.left = Pt(x + (w - drawn_w) / 2)
        picture.top = Pt(y + (h - drawn_h) / 2)
        return picture
    # cover: crop the overflow back to the box, then pin the frame to the box.
    crop = image.get('crop') or {}
    overflow_x = max(0.0, (drawn_w - w) / 2)
    overflow_y = max(0.0, (drawn_h - h) / 2)
    picture.crop_left = crop.get('l', overflow_x / drawn_w if drawn_w else 0)
    picture.crop_right = crop.get('r', overflow_x / drawn_w if drawn_w else 0)
    picture.crop_top = crop.get('t', overflow_y / drawn_h if drawn_h else 0)
    picture.crop_bottom = crop.get('b', overflow_y / drawn_h if drawn_h else 0)
    picture.left, picture.top, picture.width, picture.height = Pt(x), Pt(y), Pt(w), Pt(h)
    return picture


def _image_size(data: bytes) -> tuple[int, int]:
    try:
        from PIL import Image
        with Image.open(BytesIO(data)) as im:
            return im.size
    except Exception:
        return (0, 0)


def _export_missing_image(slide, elem, Pt, RGBColor) -> None:
    """An unresolved sha is drawn as a labelled placeholder rather than omitted: a hole the
    author can see is better than a picture that silently vanished."""
    box = slide.shapes.add_textbox(Pt(elem['x']), Pt(elem['y']), Pt(elem['w']), Pt(elem['h']))
    box.fill.solid()
    box.fill.fore_color.rgb = RGBColor.from_string('ECEDDF')
    frame = box.text_frame
    frame.text = (elem.get('image') or {}).get('alt') or 'Image unavailable'
    for p in frame.paragraphs:
        for run in p.runs:
            run.font.size = Pt(12)
            run.font.color.rgb = RGBColor.from_string('5C6A60')


def _export_shape(slide, elem, Pt, RGBColor, MSO_SHAPE, MSO_CONNECTOR) -> None:
    style = elem.get('style') or {}
    shape_name = elem.get('shape')
    fill = normalise_color(style.get('fill')) if style.get('fill') else None
    stroke = normalise_color(style.get('stroke')) if style.get('stroke') else None
    stroke_width = _num(style.get('stroke_width'), 1.0) or 1.0

    if shape_name in ('line', 'arrow'):
        connector = slide.shapes.add_connector(
            MSO_CONNECTOR.STRAIGHT, Pt(elem['x']), Pt(elem['y']),
            Pt(elem['x'] + elem['w']), Pt(elem['y'] + elem['h']))
        connector.line.color.rgb = RGBColor.from_string((stroke or '#24312A').lstrip('#'))
        connector.line.width = Pt(stroke_width)
        if shape_name == 'arrow':
            _add_arrowhead(connector)
        return

    if shape_name == 'polyline':
        points = elem.get('points') or []
        if len(points) < 2:
            return
        builder = slide.shapes.build_freeform(Pt(points[0][0]), Pt(points[0][1]))
        builder.add_line_segments([(Pt(p[0]), Pt(p[1])) for p in points[1:]], close=False)
        free = builder.convert_to_shape()
        free.fill.background()
        free.line.color.rgb = RGBColor.from_string((stroke or '#24312A').lstrip('#'))
        free.line.width = Pt(stroke_width)
        return

    autoshape = {
        'rect': MSO_SHAPE.RECTANGLE, 'roundRect': MSO_SHAPE.ROUNDED_RECTANGLE,
        'ellipse': MSO_SHAPE.OVAL, 'triangle': MSO_SHAPE.ISOSCELES_TRIANGLE,
    }.get(shape_name, MSO_SHAPE.RECTANGLE)
    shape = slide.shapes.add_shape(autoshape, Pt(elem['x']), Pt(elem['y']), Pt(elem['w']), Pt(elem['h']))
    if elem.get('rotation'):
        shape.rotation = float(elem['rotation'])
    if fill:
        shape.fill.solid()
        shape.fill.fore_color.rgb = RGBColor.from_string(fill.lstrip('#'))
    else:
        shape.fill.background()
    if stroke:
        shape.line.color.rgb = RGBColor.from_string(stroke.lstrip('#'))
        shape.line.width = Pt(stroke_width)
    else:
        shape.line.fill.background()
    if shape_name == 'roundRect':
        radius = _num(style.get('radius'), 12.0) or 0.0
        # adjustment 0..0.5 of the shorter side; python-pptx exposes it as a fraction.
        try:
            shape.adjustments[0] = max(0.0, min(0.5, radius / max(1.0, min(elem['w'], elem['h']))))
        except (IndexError, TypeError):
            pass  # a square corner is cosmetic; it must never fail the export
    if shape.has_text_frame:
        shape.text_frame.text = ''


def _add_arrowhead(connector) -> None:
    """python-pptx exposes no arrowhead API, so the one line that needs it edits the
    connector's own XML. A straight ``<a:tailEnd>`` is the smallest correct change."""
    try:
        from pptx.oxml.ns import qn
        line = connector.line._get_or_add_ln()
        tail = line.makeelement(qn('a:tailEnd'), {'type': 'triangle', 'w': 'med', 'len': 'med'})
        line.append(tail)
    except Exception:
        pass  # a missing arrowhead is cosmetic; it must never fail the export


def _style_box(box, elem: dict, RGBColor) -> None:
    style = elem.get('style') or {}
    fill = normalise_color(style.get('fill')) if style.get('fill') else None
    if fill:
        box.fill.solid()
        box.fill.fore_color.rgb = RGBColor.from_string(fill.lstrip('#'))
    else:
        box.fill.background()
    stroke = normalise_color(style.get('stroke')) if style.get('stroke') else None
    if stroke:
        box.line.color.rgb = RGBColor.from_string(stroke.lstrip('#'))
        box.line.width = Pt(_num(style.get('stroke_width'), 1.0) or 1.0)


def _style_run(run, style: dict, RGBColor, Pt) -> None:
    style = style or {}
    run.font.size = Pt(_num(style.get('size'), 18.0) or 18.0)
    if style.get('font'):
        run.font.name = str(style['font'])
    run.font.bold = bool(style.get('bold'))
    run.font.italic = bool(style.get('italic'))
    run.font.underline = bool(style.get('underline'))
    color = normalise_color(style.get('color')) or '#24312A'
    run.font.color.rgb = RGBColor.from_string(color.lstrip('#'))


_A_NS = 'http://schemas.openxmlformats.org/drawingml/2006/main'
_THEME_COLOR_SLOT = {'text': 'dk1', 'background': 'lt1', 'accent1': 'accent1',
                     'accent2': 'accent2', 'accent3': 'accent3', 'accent4': 'accent4',
                     'accent5': 'accent5', 'accent6': 'accent6'}


def _apply_theme(presentation, theme: dict) -> None:
    """Write the theme into the package's real theme part.

    python-pptx exposes no theme API, so this edits the theme part's XML directly: the theme
    name, the major/minor Latin typefaces and the colour scheme. It is best-effort — a theme
    that could not be written must never cost the export — so a failure is swallowed and the
    deck still opens with PowerPoint's default theme.
    """
    try:
        from lxml import etree
        from pptx.opc.constants import RELATIONSHIP_TYPE as RT
        part = presentation.slide_master.part.part_related_by(RT.THEME)
        root = etree.fromstring(part.blob)
        ns = {'a': _A_NS}
        root.set('name', str(theme.get('name') or 'Luminfest'))
        fonts = theme.get('fonts') or {}
        font_scheme = root.find('.//a:fontScheme', ns)
        if font_scheme is not None:
            for tag, key in (('majorFont', 'major'), ('minorFont', 'minor')):
                latin = font_scheme.find(f'a:{tag}/a:latin', ns)
                if latin is not None and fonts.get(key):
                    latin.set('typeface', str(fonts[key]))
        clr = root.find('.//a:clrScheme', ns)
        colors = theme.get('colors') or {}
        if clr is not None:
            for key, slot in _THEME_COLOR_SLOT.items():
                value = normalise_color(colors.get(key))
                if not value:
                    continue
                existing = clr.find(f'a:{slot}', ns)
                node = etree.SubElement(clr, f'{{{_A_NS}}}srgbClr')
                node.set('val', value.lstrip('#'))
                if existing is not None:
                    existing.getparent().replace(existing, node)
        part.blob = etree.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True)
    except Exception:
        return


# --------------------------------------------------------------------- .pptx import


def import_pptx(settings, data: bytes, *, title: str = '', owner_id: str = '') -> dict:
    """Parse a real .pptx back into an editable document.

    This is the direction that makes the tool a *tool*: a teacher's existing deck opens here
    and every shape, run, picture and note becomes an element the client can move and restyle.
    Pictures are written into the media store under their content hash, so an imported deck
    uses the same serving path as an authored one.
    """
    _pptx_module()
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    from pptx.util import Emu

    try:
        presentation = Presentation(BytesIO(data))
    except Exception as exc:
        raise DeckError('The file is not a readable .pptx presentation.',
                        [f'{type(exc).__name__}: {exc}'])

    canvas_w = _pt(presentation.slide_width) if presentation.slide_width else CANVAS['w']
    canvas_h = _pt(presentation.slide_height) if presentation.slide_height else CANVAS['h']
    doc = new_deck(title or _pptx_title(presentation) or 'Imported deck', owner_id=owner_id)
    # The document canvas is fixed at 16:9; an imported 4:3 deck is scaled into it so nothing
    # falls off the slide. Scaling is recorded in the geometry, not the model's units.
    scale = min(CANVAS['w'] / canvas_w, CANVAS['h'] / canvas_h) if canvas_w and canvas_h else 1.0

    for source in presentation.slides:
        layout = source.name if source.name in LAYOUTS else \
            next((k for k, v in TEMPLATE_LAYOUT.items() if v == source.slide_layout.name), 'blank')
        slide = new_slide(layout)
        if source.has_notes_slide:
            slide['notes'] = str(source.notes_slide.notes_text_frame.text or '')[:MAX_NOTES]
        for shape in source.shapes:
            elem = _import_shape(settings, shape, scale, Emu, MSO_SHAPE_TYPE)
            if elem is not None:
                elem['z'] = len(slide['elements'])
                slide['elements'].append(elem)
        doc['slides'].append(slide)

    doc = normalise_document(doc, owner_id=owner_id)
    # An imported deck must be storable; if a shape produced something the validator refuses,
    # drop that element rather than refusing the whole import, and say so.
    clean: list[dict] = []
    dropped = 0
    for slide in doc['slides']:
        keep = []
        for elem in slide['elements']:
            if validate_element(elem):
                dropped += 1
                continue
            keep.append(elem)
        slide['elements'] = keep
        clean.append(slide)
    doc['slides'] = clean
    if dropped:
        doc['import_note'] = (f'{dropped} shape(s) could not be represented and were skipped.')
    return doc


def _pptx_title(presentation) -> str:
    try:
        core = presentation.core_properties
        return str(core.title or '')
    except Exception:
        return ''


def _import_shape(settings, shape, scale, Emu, MSO_SHAPE_TYPE) -> dict | None:
    kind = shape.shape_type
    x = _pt(shape.left) * scale if shape.left is not None else 0.0
    y = _pt(shape.top) * scale if shape.top is not None else 0.0
    w = _pt(shape.width) * scale if shape.width is not None else 0.0
    h = _pt(shape.height) * scale if shape.height is not None else 0.0
    rotation = float(shape.rotation) if getattr(shape, 'rotation', 0) else 0.0

    if kind == MSO_SHAPE_TYPE.PICTURE:
        blob = shape.image.blob
        from .harness import media
        stored = media.store_bytes(settings, blob, title='imported image')
        if not stored and not _sha_in_index(settings, blob):
            return None
        sha = hashlib.sha256(blob).hexdigest()
        return {'id': _new_id('el'), 'kind': 'image', 'x': x, 'y': y,
                'w': w or 200.0, 'h': h or 150.0, 'rotation': rotation, 'z': 0,
                'style': dict(DEFAULT_TEXT_STYLE),
                'image': {'sha256': sha, 'fit': 'contain', 'alt': str(shape.name or '')}}

    if kind == MSO_SHAPE_TYPE.TABLE and getattr(shape, 'has_table', False) and shape.has_table:
        rows = [[cell.text for cell in row.cells] for row in shape.table.rows]
        if not rows or not any(rows):
            return None
        return {'id': _new_id('el'), 'kind': 'table', 'x': x, 'y': y,
                'w': w or 300.0, 'h': h or 120.0, 'rotation': rotation, 'z': 0,
                'style': dict(DEFAULT_TEXT_STYLE), 'table': {'rows': rows, 'col_widths': []}}

    has_text = getattr(shape, 'has_text_frame', False) and shape.has_text_frame
    if has_text and shape.text_frame.text.strip():
        paragraphs = _import_paragraphs(shape.text_frame)
        if not paragraphs:
            return None
        first = paragraphs[0]['runs'][0]['style']
        return {'id': _new_id('el'), 'kind': 'text', 'x': x, 'y': y,
                'w': w or 300.0, 'h': h or 80.0, 'rotation': rotation, 'z': 0,
                'style': dict(first), 'text': {'paragraphs': paragraphs}}

    if kind == MSO_SHAPE_TYPE.LINE:
        return {'id': _new_id('el'), 'kind': 'shape', 'x': x, 'y': y,
                'w': w or 100.0, 'h': h or 0.01, 'rotation': rotation, 'z': 0,
                'style': {**DEFAULT_TEXT_STYLE, 'stroke': '#24312A', 'fill': None},
                'shape': 'line'}

    # An empty text box or placeholder carries nothing; importing it would litter the deck
    # with invisible boxes. An autoshape or freeform with no text is still a real drawing,
    # so it becomes a shape element.
    if has_text and kind in (MSO_SHAPE_TYPE.TEXT_BOX, MSO_SHAPE_TYPE.PLACEHOLDER):
        return None
    if kind == MSO_SHAPE_TYPE.FREEFORM:
        return {'id': _new_id('el'), 'kind': 'shape', 'x': x, 'y': y,
                'w': w or 100.0, 'h': h or 100.0, 'rotation': rotation, 'z': 0,
                'style': {**DEFAULT_TEXT_STYLE, 'fill': None, 'stroke': '#24312A'},
                'shape': 'rect'}
    return {'id': _new_id('el'), 'kind': 'shape', 'x': x, 'y': y,
            'w': w or 100.0, 'h': h or 100.0, 'rotation': rotation, 'z': 0,
            'style': {**DEFAULT_TEXT_STYLE, 'fill': '#F5F3EC', 'stroke': '#DFE2D6'},
            'shape': _import_autoshape(shape, MSO_SHAPE_TYPE)}


def _sha_in_index(settings, blob: bytes) -> bool:
    from .harness import media
    sha = hashlib.sha256(blob).hexdigest()
    return any(row.get('sha256') == sha for row in media.cached_assets(settings))


def _import_autoshape(shape, MSO_SHAPE_TYPE) -> str:
    try:
        from pptx.enum.shapes import MSO_SHAPE
        mapping = {MSO_SHAPE.OVAL: 'ellipse', MSO_SHAPE.ROUNDED_RECTANGLE: 'roundRect',
                   MSO_SHAPE.ISOSCELES_TRIANGLE: 'triangle', MSO_SHAPE.RECTANGLE: 'rect'}
        return mapping.get(shape.auto_shape_type, 'rect')
    except Exception:
        return 'rect'


def _import_paragraphs(text_frame) -> list[dict]:
    paragraphs: list[dict] = []
    for para in text_frame.paragraphs:
        runs: list[dict] = []
        for run in para.runs:
            runs.append({'text': run.text, 'style': _import_run_style(run)})
        if not runs and para.text:
            runs.append({'text': para.text, 'style': dict(DEFAULT_TEXT_STYLE)})
        if not runs:
            continue
        paragraphs.append({'runs': runs, 'level': int(para.level or 0),
                           'align': _import_align(para.alignment),
                           'line_spacing': float(para.line_spacing) if isinstance(
                               para.line_spacing, (int, float)) else 1.0,
                           'space_after': 0})
    return paragraphs


def _import_run_style(run) -> dict:
    style = dict(DEFAULT_TEXT_STYLE)
    font = run.font
    if font.size is not None:
        style['size'] = _pt(font.size)
    if font.name:
        style['font'] = font.name
    style['bold'] = bool(font.bold)
    style['italic'] = bool(font.italic)
    style['underline'] = bool(font.underline)
    try:
        rgb = font.color.rgb
        if rgb is not None:
            style['color'] = '#' + str(rgb).upper()
    except Exception:
        pass
    return style


def _import_align(alignment) -> str:
    from pptx.enum.text import PP_ALIGN
    return {PP_ALIGN.CENTER: 'center', PP_ALIGN.RIGHT: 'right',
            PP_ALIGN.JUSTIFY: 'justify', PP_ALIGN.LEFT: 'left'}.get(alignment, 'left')


# --------------------------------------------------------------------- curriculum


def from_presentation(payload: dict, *, owner_id: str = '') -> dict:
    """Turn a ``harness.presentation.compose`` payload into an editable deck.

    Each narrated slide becomes a slide with a real title box, a real bullet box and, when
    the visual is a licence-cleared photograph, a real image element. A generated SVG figure
    is *not* embedded: a .pptx cannot carry a vector SVG, and this project refuses to
    substitute a synthesised picture, so the figure stays in the source presentation's HTML
    export and the slide's notes point at it. That is a limitation, stated rather than hidden.
    """
    title = str(payload.get('title') or 'Narrated deck')
    doc = new_deck(title, owner_id=owner_id)
    theme = doc['theme']
    ink = theme['colors']['text']
    accent = theme['colors']['accent1']

    for source in payload.get('slides', []):
        layout = PRESENTATION_LAYOUT.get(str(source.get('layout') or ''), 'idea')
        slide = new_slide(layout)
        slide['notes'] = str(source.get('speaker_notes') or source.get('narration') or '')[:MAX_NOTES]
        slide['elements'].append(new_text_element(
            48, 36, 864, 78, str(source.get('title') or ''), {
                'size': 34, 'bold': True, 'color': ink, 'anchor': 'middle'}))
        bullets = [str(b) for b in (source.get('bullets') or []) if str(b).strip()]
        if bullets:
            paragraphs = [{'runs': [{'text': b, 'style': {}}], 'level': 0,
                           'align': 'left', 'line_spacing': 1.15} for b in bullets]
            slide['elements'].append({
                'id': _new_id('el'), 'kind': 'text', 'x': 48, 'y': 132, 'w': 560, 'h': 320,
                'rotation': 0.0, 'z': 1, 'style': {**DEFAULT_TEXT_STYLE, 'size': 19},
                'text': {'paragraphs': paragraphs}})
        formula = str(source.get('formula') or '').strip()
        if formula:
            slide['elements'].append(new_text_element(
                48, 452, 560, 48, formula, {'size': 20, 'italic': True, 'color': accent}))
        visual = source.get('visual') or {}
        if visual.get('sha256'):
            slide['elements'].append({
                'id': _new_id('el'), 'kind': 'image', 'x': 624, 'y': 132, 'w': 288, 'h': 320,
                'rotation': 0.0, 'z': 2, 'style': dict(DEFAULT_TEXT_STYLE),
                'image': {'sha256': visual['sha256'], 'fit': 'contain',
                          'alt': str(visual.get('title') or ''),
                          'attribution': str(visual.get('attribution') or '')}})
        citation = str(source.get('citation') or '').strip()
        if citation:
            slide['elements'].append(new_text_element(
                48, 506, 864, 26, citation, {'size': 12, 'color': '#5C6A60'}))
        doc['slides'].append(slide)

    return normalise_document(doc, owner_id=owner_id)
