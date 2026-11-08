"""Build a course from the learner's own material, and make it studyable.

The harness ships six courses. This module is the other half of that promise: a
learner pastes, uploads or links their own source, and gets a real course - a
knowledge graph, lessons and diagnostic quizzes - stored on their own account.

Three rules shape everything here.

1. **No provenance, no concept.** Every concept carries the *verbatim* span of
   the source it was extracted from. A generated claim that cannot be pointed at
   a sentence in the learner's own material is not generated at all - it is
   invented, and this module does not invent content.

2. **Offline and deterministic.** There is no model provider in the loop. The
   extractor is regular expressions and the graph builder is the same
   ``app.ingest`` classifier the shipped packs are built with, so the same source
   always yields the same course and a machine with no API key behaves exactly
   like one with.

3. **Refuse rather than fabricate.** A source too thin to support a course is
   refused with a machine-readable reason and a stated minimum
   (:data:`REFUSAL_RULES`). Turning one paragraph into a "course" would be a lie
   dressed as a feature.

The material is stored with the course so the learner can inspect where every
concept came from. It is used only inside that account: it is never added to the
shared catalogue, never served to another learner, and the learner remains
responsible for having the right to use what they supply.
"""

from __future__ import annotations

import hashlib
import io
import ipaddress
import json
import re
import socket
import zipfile
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.parse import urlparse
from uuid import uuid4
from xml.etree import ElementTree

from sqlalchemy import Float, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from . import courses, curriculum
from .db import Base, now_ts
from .ingest import policy as ingest_policy
from .ingest.classify import ClassificationRules, Classifier, tokens
from .ingest.policy import LicenceClass, SourcePolicy
from .ingest.sources.base import RawNode
from .knowledge_graph import ConceptNode, KnowledgeGraph, slug

# --------------------------------------------------------------------- limits
#: A course is a set of ideas, not a paragraph. These are the floors a source has
#: to clear before a course can honestly be built from it.
MIN_SOURCE_CHARS = 400
MIN_SOURCE_WORDS = 80
MIN_SOURCE_PARAGRAPHS = 2
#: Four concepts is the smallest set that still lets a four-option item have
#: three plausible, course-grounded distractors.
MIN_CONCEPTS = 4
#: Bound on how large a single generated course can get. A learner's own source
#: is not a textbook; past this the right move is to split it, not to emit a
#: thousand-node graph nobody will finish.
MAX_CONCEPTS = 60

#: Documented URL fetch ceiling. A page larger than this is refused rather than
#: truncated, because a silently truncated source would produce concepts whose
#: spans no longer match what the learner sees.
URL_MAX_BYTES = 2_000_000
URL_USER_AGENT = 'Luminfest-Learning-Harness/1.0 (learner-supplied source; +https://luminfest.local)'

#: ``subjects`` column width for the runtime course id (``mine_`` + 10 hex).
COURSE_ID_PREFIX = 'mine_'
#: Concept ids, question ids and the columns that carry them are all capped here.
MAX_ID = 64

#: The subject kind a learner-built course is declared under. Deliberately *not*
#: ``mathematics``: the symbolic figure engine matches a concept against
#: mathematics templates and silently falls back to a generic quadratic, which
#: would present a meaningless curve as though it were about the learner's own
#: idea. Anything that is not ``mathematics`` gets the graph-derived concept map,
#: which is real content. See ``app.courses`` and ``app.figures``.
CUSTOM_SUBJECT_KIND = 'custom'

#: The rights position for learner-supplied material. ``CC_BY`` is the closest
#: honest fit in the existing vocabulary - it is ingestible and it requires an
#: attribution, which is exactly right here: the attribution is the learner, and
#: the material never leaves their account.
LEARNER_SOURCE = SourcePolicy(
    name='Learner-supplied source material',
    url='',
    licence='Supplied by the learner for their own account; not redistributed by Luminfest',
    licence_class=LicenceClass.CC_BY,
    scope='Text the learner pasted, uploaded or linked is stored with their course so the '
          'provenance of every concept is inspectable. It is used only inside that account, '
          'is never added to the shared catalogue, and is never served to another learner.',
    attribution='The learner, who supplied this material.',
)

# ------------------------------------------------------------- refusal rules
#: Why a source can be refused, as data rather than as branches buried in the
#: extractor. The API serves this list, so a refusal tells the learner the exact
#: bar they did not clear instead of a vague apology.
REFUSAL_RULES: tuple[dict[str, Any], ...] = (
    {'code': 'source_too_short',
     'minimum': {'characters': MIN_SOURCE_CHARS, 'words': MIN_SOURCE_WORDS},
     'reason': f'A course needs at least {MIN_SOURCE_CHARS} characters and {MIN_SOURCE_WORDS} '
               f'words of source text. Below that there is not enough material to extract '
               f'concepts from, and inventing the missing content would not be a course.'},
    {'code': 'too_few_paragraphs',
     'minimum': {'paragraphs': MIN_SOURCE_PARAGRAPHS},
     'reason': f'A course needs at least {MIN_SOURCE_PARAGRAPHS} paragraphs. A single block of '
               f'text has no internal structure to build a prerequisite order from.'},
    {'code': 'too_few_concepts',
     'minimum': {'concepts': MIN_CONCEPTS},
     'reason': f'At least {MIN_CONCEPTS} distinct concepts must be extractable from the source. '
               f'Fewer than that cannot support a four-option item with course-grounded '
               f'distractors, so no quiz could be built honestly.'},
)


def refusal_rules() -> list[dict[str, Any]]:
    """The refusal contract, for the API and for a learner who wants the numbers."""
    return [dict(rule) for rule in REFUSAL_RULES]


#: Stated on every response that carries learner-supplied material, because the
#: rights position of what a learner supplies is theirs to establish, not ours.
RIGHTS_NOTE = ('This material is stored only in your account and is never added to the shared '
               'catalogue or shown to another learner. You are responsible for having the right '
               'to use what you supply.')


@dataclass
class Refusal:
    """A structured, non-fatal "no", with the minimum that was not met."""

    code: str
    reason: str
    minimum: dict[str, Any] = field(default_factory=dict)
    detail: str = ''

    def to_dict(self) -> dict[str, Any]:
        payload = {'refused': True, 'code': self.code, 'reason': self.reason,
                   'minimum': dict(self.minimum)}
        if self.detail:
            payload['detail'] = self.detail
        payload['rules'] = refusal_rules()
        return payload


class IntakeRefused(RuntimeError):
    """The source could not be read. Carries the :class:`Refusal`."""

    def __init__(self, refusal: Refusal):
        super().__init__(refusal.reason)
        self.refusal = refusal


class BuildRefused(RuntimeError):
    """The source was readable but cannot support a course."""

    def __init__(self, refusal: Refusal):
        super().__init__(refusal.reason)
        self.refusal = refusal


def _refuse(code: str, detail: str = '') -> Refusal:
    rule = next((rule for rule in REFUSAL_RULES if rule['code'] == code), None)
    if rule is None:
        return Refusal(code=code, reason=detail or code, detail=detail)
    return Refusal(code=code, reason=rule['reason'], minimum=dict(rule['minimum']), detail=detail)


# ------------------------------------------------------------------- intake
@dataclass
class Intake:
    """Source text plus where it came from, so provenance survives the pipeline."""

    text: str
    source_kind: str          # 'text' | 'file' | 'url'
    label: str
    url: str = ''
    byte_size: int = 0
    format: str = ''

    def to_dict(self) -> dict[str, Any]:
        # ``kind``, not ``source_kind``: ``CreatedCourse.to_dict()`` already reports the
        # stored row under ``source.kind``, and two spellings of the same fact in two
        # payloads is a client bug waiting to be written.
        return {'kind': self.source_kind, 'label': self.label, 'url': self.url,
                'byte_size': self.byte_size, 'format': self.format,
                'characters': len(self.text)}


_WORD = re.compile(r'[A-Za-z0-9][A-Za-z0-9\'’_-]*')


def word_count(text: str) -> int:
    return len(_WORD.findall(text))


def paragraph_count(text: str) -> int:
    return len([block for block in re.split(r'\n[ \t]*\n+', text) if block.strip()])


def _looks_like_text(text: str) -> bool:
    """True when a decode produced prose rather than binary noise."""
    if not text.strip():
        return False
    control = sum(1 for ch in text if ord(ch) < 32 and ch not in '\n\r\t')
    return control / max(1, len(text)) < 0.02


def _decode_text(data: bytes) -> str | None:
    for encoding in ('utf-8-sig', 'utf-16', 'latin-1'):
        try:
            text = data.decode(encoding)
        except (UnicodeDecodeError, UnicodeError):
            continue
        if _looks_like_text(text):
            return text
    return None


def _pdf_paragraphs(text: str) -> str:
    """Rebuild paragraphs from the lines pypdf hands back.

    pypdf returns one line per drawn text run and flattens the layout, so a
    paragraph break and a hard wrap both arrive as the same single ``\n``. The
    builder counts paragraphs by blank lines, so without this pass a perfectly
    good PDF is refused for having "no internal structure to build a prerequisite
    order from". A line that ends with sentence-final punctuation ends a
    paragraph; anything else is a wrap and continues the one before it.
    """
    paragraphs: list[str] = []
    for raw_line in text.split('\n'):
        line = raw_line.strip()
        if not line:
            continue
        if paragraphs and not paragraphs[-1].endswith(('.', '!', '?', ':')):
            paragraphs[-1] = f'{paragraphs[-1]} {line}'
        else:
            paragraphs.append(line)
    return '\n\n'.join(paragraphs)


#: A font name that carries weight. Subset prefixes are stripped by pypdf's
#: reader before this sees the name (``/AJISGU+SourceSansPro-Semibold``).
_WEIGHTED_FONT = re.compile(r'bold|semibold|black|heavy|w700|w800|w900', re.I)

#: A run whose text is mostly unmapped glyphs is a logo or a rule, not prose:
#: pypdf renders the missing glyph as ``\x00``, so a decorative "LT" monogram
#: arrives as ``L\x00\x00\x00\x00 T\x00\x00\x00`` and would otherwise be read
#: as a heading.
_DECORATIVE = re.compile(r'\x00')


def _repair_glyphs(text: str) -> str:
    """Undo the two glyph faults subset fonts exhibit in pypdf's output.

    A missing ``ft`` ligature mapping arrives as ``\\x00`` between two letters
    (``o\\x00en`` is ``often``), and the ``fi``/``fl`` ligatures arrive as their
    own codepoints. Neither is legitimate text, so both are repaired rather
    than stored: the span a concept cites has to be readable by the learner.
    """
    text = _DECORATIVE.sub('ft', text) if text.count('\x00') <= len(text) // 3 else text
    return (text.replace('\ufb01', 'fi').replace('\ufb02', 'fl')
                .replace('\ufb00', 'ff').replace('\ufb03', 'ffi').replace('\ufb04', 'ffl'))


def _pdf_structured_text(data: bytes) -> str | None:
    """The page text *with its formatting*, as markdown-ish markers.

    Plain ``extract_text`` flattens a textbook into one typeface: the bold run
    that names a term, the larger line that heads a module and the folio number
    in the margin all arrive as identical prose, and the concept extractor then
    reads running headers as concepts. The visitor API still sees the font per
    run, so the structure is recoverable - and the extractor already understands
    ``**bold**`` runs and standalone heading lines, which is what a textbook
    actually is.

    Returns ``None`` when the visitor yields nothing usable (a scanned or
    unusual PDF), so the caller can fall back to the plain extraction instead
    of storing an empty source.
    """
    try:
        from pypdf import PdfReader  # imported lazily: an optional dependency
    except ImportError:  # pragma: no cover - pypdf ships in this environment
        return None
    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception:  # noqa: BLE001 - a broken reader object is a fallback, not a crash
        return None

    # (page, y, x, size, font, text) per run. The page index is the primary
    # sort key: pages overlap in their coordinate ranges, so sorting by position
    # alone would interleave the last line of one page with the first of the next.
    runs: list[tuple[int, float, float, float, str, str]] = []
    page_index = 0

    def visitor(text, cm, tm, font_dict, font_size):  # noqa: ANN001 - pypdf's signature
        if not text:
            return
        name = str(font_dict.get('/BaseFont', '') or '') if isinstance(font_dict, dict) else ''
        try:
            size = float(font_size)
        except (TypeError, ValueError):
            size = 0.0
        try:
            # The text matrix is *relative to the line*; the current matrix
            # carries the absolute offset. Using tm alone interleaves the lines
            # of a paragraph, because each line restarts at its own origin.
            x = float(cm[0]) * float(tm[4]) + float(cm[2]) * float(tm[5]) + float(cm[4])
            y = float(cm[1]) * float(tm[4]) + float(cm[3]) * float(tm[5]) + float(cm[5])
        except (TypeError, ValueError, IndexError):
            x, y = 0.0, 0.0
        runs.append((page_index, y, x, size, name, text))

    try:
        for page in reader.pages:
            page.extract_text(visitor_text=visitor)
            page_index += 1
    except Exception:  # noqa: BLE001 - any visitor failure falls back to plain text
        return None
    if not runs:
        return None

    # The body size is the size most text is drawn at, weighted by characters:
    # a textbook's prose dwarfs its headings, objectives and margin notes.
    weight: dict[float, int] = {}
    for _, _, _, size, _, text in runs:
        cleaned = _repair_glyphs(text)
        if cleaned.strip() and '\x00' not in cleaned:
            weight[size] = weight.get(size, 0) + len(cleaned.strip())
    if not weight:
        return None
    body = max(weight, key=weight.get)
    if body <= 0:
        return None

    # Flatten runs to pieces: one showing operation can carry several visual
    # lines inside it (a pasted PDF often arrives as a single run holding the
    # whole paragraph breaks included), and each piece needs its own line key.
    # Embedded pieces step down by a line, and by a paragraph when the source
    # had a blank line between them, so the paragraph splitter below sees the
    # structure the author wrote rather than one wall of prose.
    tolerance = max(1.5, body * 0.12)
    line_step = tolerance * 3
    para_step = tolerance * 8
    pieces: list[tuple[float, float, float, str, str]] = []
    for _, y, x, size, font, text in sorted(runs, key=lambda row: (row[0], -row[1], row[2])):
        cleaned = _repair_glyphs(text)
        if not cleaned.strip() or '\x00' in cleaned:
            continue  # a decorative run (a logo, a rule): not prose, not a term
        offset = 0.0
        blank = False
        for piece in cleaned.split('\n'):
            if not piece.strip():
                blank = True
                continue
            step = para_step if blank else line_step
            offset += step
            blank = False
            pieces.append((y - offset, x, size, font, piece))

    lines: list[list[tuple[float, float, float, str, str]]] = []
    for piece in pieces:
        if lines and abs(lines[-1][0][0] - piece[0]) <= tolerance:
            lines[-1].append(piece)
        else:
            lines.append([piece])

    out: list[str] = []
    previous_y: float | None = None
    #: True while the last emitted body line ended mid-sentence. A weighted run
    #: on a *continuation* line is a fragment of the sentence above it ("…the
    #: tendency to | perceive order in random events illustrate why | …"), never
    #: a term: a term starts a sentence.
    open_sentence = False
    #: Text of consecutive all-weighted lines. A wrapped weighted heading is one
    #: phrase the font subsetter split across baselines, so the lines are joined
    #: before anything decides where the terms are.
    pending_weighted: list[str] = []

    def flush_weighted() -> None:
        """Emit the joined weighted block as term markers.

        The block carries no terminal punctuation of its own, so the paragraph
        splitter glues it to the prose that follows and the bold path reads it
        as a term - which is what a sidehead is.
        """
        nonlocal open_sentence
        if not pending_weighted:
            return
        joined = ' '.join(pending_weighted)
        pending_weighted.clear()
        segments = [segment.strip() for segment in re.split(r'(?<=[.!?])\s+', joined)
                    if segment.strip()]
        if not segments:
            return
        out.append(' '.join(f'**{segment}**' for segment in segments) + '\n')
        open_sentence = not joined.rstrip().endswith(('.', '!', '?', ':'))

    def emit(rendered: str, line_y: float, *, heading: bool = False) -> None:
        nonlocal previous_y, open_sentence
        if heading:
            # A larger line is a heading: it stands alone, so the paragraph
            # splitter gives it its own block instead of gluing it to prose.
            flush_weighted()
            out.append('\n\n' + rendered + '\n\n')
            open_sentence = False
        else:
            flush_weighted()
            if previous_y is not None and (previous_y - line_y) > tolerance * 4:
                out.append('\n\n' + rendered)  # a visual paragraph gap
                open_sentence = False
            else:
                out.append(rendered + '\n')
            open_sentence = not rendered.rstrip().endswith(('.', '!', '?', ':'))
        previous_y = line_y

    for line in lines:
        max_size = max((run[2] for run in line), default=body)
        big = max_size > body * 1.35
        # A header band carries the module title *and* the learning objective on
        # one baseline: the large runs are the heading, the small ones are body
        # text that must not be swallowed into it. Split by index, not by value:
        # two identical runs are two runs.
        if big:
            keep_flags = [run[2] > body * 1.35 for run in line]
        else:
            keep_flags = [True] * len(line)
        kept = [run for run, keep in zip(line, keep_flags) if keep]
        dropped = [run for run, keep in zip(line, keep_flags) if not keep]
        weighted_runs = [run for run in kept
                         if _WEIGHTED_FONT.search(run[3]) and 2 <= len(run[4].strip()) <= 120
                         and re.search(r'[A-Za-z]', run[4])]
        if kept and len(weighted_runs) == len(kept):
            # A wholly weighted line: hold it, because the next line may be the
            # rest of the same wrapped heading.
            pending_weighted.append(' '.join(run[4].strip() for run in kept))
            continue
        # A weighted run only names a term where a sentence can start; elsewhere
        # it is emphasis inside prose and stays plain text.
        mark_terms = not open_sentence
        rendered_pieces: list[str] = []
        bold_buffer: list[str] = []

        def flush_bold() -> None:
            """Adjacent weighted runs are one term split by the font subsetter
            ("Did We Know It All Along? Hindsight" + "Bias" is one phrase), so
            they are joined before the sentence split, not after it."""
            if not bold_buffer:
                return
            joined = ' '.join(bold_buffer)
            bold_buffer.clear()
            if not mark_terms:
                rendered_pieces.append(joined)
                return
            # A question half is dropped and the term half kept: a feature-box
            # heading names its concept after the question mark.
            for segment in re.split(r'(?<=[.!?])\s+', joined):
                if segment.strip():
                    rendered_pieces.append(f'**{segment.strip()}**')

        for _, _, size, font, piece in kept:
            text = piece.strip()
            if re.fullmatch(r'\d{1,4}', text) and len(kept) == 1:
                continue  # a folio: the page number in the margin
            if mark_terms and _WEIGHTED_FONT.search(font) and 2 <= len(text) <= 120 \
                    and re.search(r'[A-Za-z]', text):
                bold_buffer.append(text)
            else:
                flush_bold()
                rendered_pieces.append(text)
        flush_bold()
        if rendered_pieces:
            emit(' '.join(rendered_pieces), line[0][0], heading=big)
        # The small runs that shared the heading's baseline keep their own line.
        if dropped:
            remainder = ' '.join(run[4].strip() for run in dropped if run[4].strip())
            if remainder:
                emit(remainder, line[0][0])
    flush_weighted()
    structured = ''.join(out).strip()
    return structured or None


def _extract_pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader  # imported lazily: an optional dependency
    except ImportError as exc:  # pragma: no cover - pypdf ships in this environment
        raise IntakeRefused(Refusal(
            code='pdf_support_unavailable',
            reason='PDF support is not installed on this server, so the file was not read. '
                   'Paste the text or upload a .txt, .md or .docx file instead.')) from exc
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [(page.extract_text() or '').strip() for page in reader.pages]
    except Exception as exc:  # noqa: BLE001 - any parse failure is a refusal, not a crash
        raise IntakeRefused(Refusal(
            code='unparseable_file',
            reason='That file looks like a PDF but could not be parsed, so no text was stored '
                   'rather than storing garbage.',
            detail=type(exc).__name__)) from exc
    plain = '\n\n'.join(page for page in pages if page).strip()
    # The structured pass is preferred when it actually sees the document: a
    # visitor that yields a fraction of the plain text has mis-read the file,
    # and half a source is worse than a flattened one.
    structured = _pdf_structured_text(data)
    if structured is not None and len(structured) >= 0.5 * max(len(plain), 1):
        return _pdf_paragraphs(structured)
    return _pdf_paragraphs(plain)


_DOCX_NS = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


def _extract_docx(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if 'word/document.xml' not in archive.namelist():
                raise IntakeRefused(Refusal(
                    code='unparseable_file',
                    reason='That .docx archive has no word/document.xml, so it is not a Word '
                           'document this server can read.'))
            xml = archive.read('word/document.xml')
    except IntakeRefused:
        raise
    except (zipfile.BadZipFile, OSError) as exc:
        raise IntakeRefused(Refusal(
            code='unparseable_file',
            reason='That file could not be opened as a Word document.',
            detail=type(exc).__name__)) from exc
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        raise IntakeRefused(Refusal(
            code='unparseable_file',
            reason='The Word document XML could not be parsed.',
            detail=type(exc).__name__)) from exc
    paragraphs: list[str] = []
    for paragraph in root.iter(f'{_DOCX_NS}p'):
        text = ''.join(node.text or '' for node in paragraph.iter(f'{_DOCX_NS}t')).strip()
        paragraphs.append(text)
    return '\n\n'.join(paragraphs).strip()


def _detect_and_extract(data: bytes) -> tuple[str, str]:
    """Return ``(text, format)`` for an uploaded file, detecting by *content*.

    The extension is a hint at best. A file renamed to ``.txt`` that is really a
    PDF, or a ``.md`` that is really a zip, is handled by what it actually is -
    and anything that cannot be parsed is refused rather than stored.
    """
    head = data[:1024]
    if head.lstrip().startswith(b'%PDF-'):
        return _extract_pdf(data), 'pdf'
    # ``PK\x03\x04`` is a zip's local-file-header magic. Detection is by this
    # magic and by the ``word/`` entry verified in :func:`_extract_docx`, never by
    # the filename: a real .docx renamed to .txt is read as the document it is,
    # and a zip that is not a Word document is refused as unreadable rather than
    # silently mis-parsed.
    if data[:4] == b'PK\x03\x04':
        return _extract_docx(data), 'docx'
    text = _decode_text(data)
    if text is None:
        raise IntakeRefused(Refusal(
            code='unparseable_file',
            reason='That file is not text this server can read (PDF, DOCX, TXT or MD). '
                   'Nothing was stored, so no garbage can enter your course.'))
    stripped = text.lstrip()
    fmt = 'markdown' if re.search(r'^\s{0,3}#{1,6}\s', text, re.M) or '**' in text else 'text'
    if stripped.startswith('<'):  # an .html saved with a .txt extension
        return _extract_html(text)[0], 'html'
    return text, fmt


def intake_text(text: str, label: str = 'Pasted text') -> Intake:
    return Intake(text=text, source_kind='text', label=label or 'Pasted text',
                  byte_size=len(text.encode('utf-8')), format='text')


def intake_bytes(filename: str, data: bytes) -> Intake:
    """Read an uploaded file, or refuse with a reason. Never stores unparsed bytes."""
    if not data:
        raise IntakeRefused(Refusal(code='empty_file', reason='That file is empty.'))
    text, fmt = _detect_and_extract(data)
    if not text.strip():
        raise IntakeRefused(Refusal(
            code='empty_source',
            reason='No text could be extracted from that file. A scanned PDF, for example, '
                   'contains images rather than text and needs OCR before it can be used.'))
    return Intake(text=text, source_kind='file', label=filename or 'Uploaded file',
                  byte_size=len(data), format=fmt)


# ------------------------------------------------------------------ url fetch
class _HTMLText(HTMLParser):
    """Minimal, dependency-free HTML-to-text with a login-wall signal.

    A password field is the tell that a page is behind a sign-in form. Fetching
    it would return the login page, not the material, and the resulting "course"
    would be about somebody's sign-in form.
    """

    _BLOCK = frozenset({'p', 'div', 'br', 'li', 'tr', 'section', 'article', 'header',
                        'footer', 'blockquote', 'pre', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'})
    _SKIP = frozenset({'script', 'style', 'noscript', 'head', 'template', 'svg'})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.has_password = False
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP:
            self._skip += 1
        if tag == 'input':
            attributes = {key.lower(): (value or '').lower() for key, value in attrs}
            if attributes.get('type') == 'password':
                self.has_password = True
        if tag in self._BLOCK:
            self.parts.append('\n\n')

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP and self._skip:
            self._skip -= 1
        if tag in self._BLOCK:
            self.parts.append('\n\n')

    def handle_data(self, data: str) -> None:
        if not self._skip and data.strip():
            self.parts.append(data)

    def text(self) -> str:
        raw = ''.join(self.parts)
        raw = re.sub(r'[ \t\r\f\v]+', ' ', raw)
        raw = re.sub(r'\n[ \t]+', '\n', raw)
        raw = re.sub(r'\n{3,}', '\n\n', raw)
        return raw.strip()


def _extract_html(source: str) -> tuple[str, bool]:
    parser = _HTMLText()
    parser.feed(source)
    parser.close()
    return parser.text(), parser.has_password


#: How many redirect hops a source URL may take. Each hop is re-validated, so the
#: cap is about loops rather than about safety.
MAX_URL_REDIRECTS = 5

#: Said once, so every refusal about a non-public address reads the same.
_BLOCKED_ADDRESS_REASON = (
    'That address resolves to a private, loopback or otherwise non-public network, so '
    'the server will not fetch it on your behalf. Link to a page on the public web.')


def _is_non_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
            or ip.is_reserved or ip.is_unspecified)


def _assert_public_target(url: str) -> str:
    """Refuse a URL whose host resolves to an address only the server can reach.

    Scheme validation alone is not enough: ``https://127.0.0.1/`` and
    ``https://169.254.169.254/`` are both perfectly valid https, and a learner-supplied
    link is exactly the input an SSRF probe uses. The check runs on the *resolved*
    addresses, so a hostname pointing at a private range is refused whether it is
    spelled ``localhost`` or ``internal.example.com``. Returns the URL for chaining.
    """
    parts = urlparse(url)
    if parts.scheme != 'https':
        raise IntakeRefused(Refusal(
            code='insecure_url',
            reason='Only https:// URLs can be fetched. A non-https address, or one with no '
                   'scheme at all, is refused so source material never travels in cleartext.'))
    host = (parts.hostname or '').strip().rstrip('.')
    if not host:
        raise IntakeRefused(Refusal(code='missing_url', reason='That URL has no host.'))
    if host.lower() in {'localhost', 'localhost.localdomain'}:
        raise IntakeRefused(Refusal(code='blocked_address', reason=_BLOCKED_ADDRESS_REASON))
    try:
        port = parts.port or 443
    except ValueError as exc:
        raise IntakeRefused(Refusal(code='missing_url',
                                    reason='That URL has an invalid port.',
                                    detail=type(exc).__name__)) from exc
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise IntakeRefused(Refusal(
            code='fetch_failed',
            reason='That host could not be resolved. Check the address, or paste the text instead.',
            detail=type(exc).__name__)) from exc
    addresses = sorted({info[4][0] for info in infos})
    if not addresses:
        raise IntakeRefused(Refusal(code='fetch_failed',
                                    reason='That host resolved to no address.'))
    for raw in addresses:
        try:
            address = ipaddress.ip_address(raw.split('%', 1)[0])
        except ValueError:
            continue
        if _is_non_public(address):
            raise IntakeRefused(Refusal(code='blocked_address',
                                        reason=_BLOCKED_ADDRESS_REASON, detail=raw))
    return url


def _default_url_fetch(url: str, max_bytes: int) -> tuple[str, str, bytes]:
    """Fetch an HTTPS page, streaming so an oversized body is refused mid-flight.

    Redirects are followed by hand rather than by ``httpx``. ``follow_redirects=True``
    would validate the first hop and then hand the rest to the client, and a redirect
    to ``https://169.254.169.254/`` is the classic way past an address check. Every hop
    is re-validated here, and the hop count is bounded.
    """
    import httpx

    current = _assert_public_target(url)
    try:
        with httpx.Client(timeout=15.0, follow_redirects=False, trust_env=False,
                          headers={'User-Agent': URL_USER_AGENT}) as client:
            for _ in range(MAX_URL_REDIRECTS + 1):
                with client.stream('GET', current) as response:
                    if response.is_redirect:
                        location = response.headers.get('location', '')
                        if not location:
                            raise IntakeRefused(Refusal(
                                code='fetch_failed',
                                reason='That page redirected without saying where.'))
                        current = _assert_public_target(str(response.url.join(location)))
                        continue
                    response.raise_for_status()
                    content_type = response.headers.get('content-type', '')
                    chunks: list[bytes] = []
                    total = 0
                    for chunk in response.iter_bytes():
                        total += len(chunk)
                        if total > max_bytes:
                            raise IntakeRefused(Refusal(
                                code='source_too_large',
                                reason=f'That page is larger than the {max_bytes} byte limit. '
                                       f'Fetching a part of it would produce concept spans that '
                                       f'do not match the page, so it is refused rather than '
                                       f'truncated.',
                                minimum={'bytes': max_bytes}))
                        chunks.append(chunk)
                    return str(response.url), content_type, b''.join(chunks)
    except IntakeRefused:
        raise
    except Exception as exc:  # noqa: BLE001 - a network failure is a refusal, not a 500
        raise IntakeRefused(Refusal(
            code='fetch_failed',
            reason='That page could not be fetched. Check the address, or paste the text instead.',
            detail=type(exc).__name__)) from exc
    raise IntakeRefused(Refusal(
        code='too_many_redirects',
        reason=f'That address redirected more than {MAX_URL_REDIRECTS} times, so the fetch was '
               f'abandoned rather than followed further.'))


#: The fetch seam. Tests (and any deployment with its own egress policy) replace
#: this rather than reaching into the function.
URL_FETCHER: Callable[[str, int], tuple[str, str, bytes]] = _default_url_fetch


def intake_url(url: str, *, max_bytes: int = URL_MAX_BYTES) -> Intake:
    """Fetch an HTTPS URL and extract its text.

    What this refuses, deliberately and by name:

    * anything that is not ``https`` (a learner's source is not worth a downgrade
      to cleartext);
    * a redirect that lands on a non-https origin;
    * a body larger than ``max_bytes`` (see :data:`URL_MAX_BYTES`);
    * a response that is not ``text/html``, ``text/plain`` or XHTML;
    * a page carrying a password field - a login wall, where the fetch would
      return the sign-in form rather than the material;
    * a fetch that fails, and a page whose extracted text is empty.
    """
    target = (url or '').strip()
    if not target:
        raise IntakeRefused(Refusal(code='missing_url', reason='No URL was given.'))
    scheme = target.split('://', 1)[0].lower() if '://' in target else ''
    if scheme != 'https':
        raise IntakeRefused(Refusal(
            code='insecure_url',
            reason='Only https:// URLs can be fetched. A non-https address, or one with no '
                   'scheme at all, is refused so source material never travels in cleartext.'))
    final, content_type, body = URL_FETCHER(target, max_bytes)
    if not final.lower().startswith('https://'):
        raise IntakeRefused(Refusal(
            code='insecure_redirect',
            reason='That URL redirected to a non-https address, so the fetch was abandoned.'))
    media = (content_type or '').split(';', 1)[0].strip().lower()
    if media not in ('text/html', 'text/plain', 'application/xhtml+xml'):
        raise IntakeRefused(Refusal(
            code='unsupported_content_type',
            reason=f'That URL served {media or "an unknown content type"}, which is not text. '
                   f'Only HTML and plain-text pages can be turned into a course.',
            detail=media))
    raw = _decode_text(body) or ''
    if media == 'text/plain':
        text, has_password = raw, False
    else:
        text, has_password = _extract_html(raw)
    if has_password:
        raise IntakeRefused(Refusal(
            code='login_walled',
            reason='That page contains a password field, so it is behind a sign-in wall. Fetching '
                   'it would return the login form, not the material. Download the text and paste '
                   'it instead.'))
    if not text.strip():
        raise IntakeRefused(Refusal(
            code='empty_source',
            reason='No readable text was found at that URL. The page may be rendered by '
                   'JavaScript, in which case paste the text instead.'))
    return Intake(text=text, source_kind='url', label=target, url=target,
                  byte_size=len(body), format='html' if media != 'text/plain' else 'text')


def intake_from(source: Mapping[str, Any], files: Mapping[str, bytes] | None = None) -> Intake:
    """One entry point for the three source kinds, for the routes to share."""
    text = str(source.get('text') or '')
    url = str(source.get('url') or '')
    if url.strip():
        return intake_url(url)
    if text.strip():
        return intake_text(text)
    if files:
        name, data = next(iter(files.items()))
        return intake_bytes(name, data)
    raise IntakeRefused(Refusal(
        code='missing_source',
        reason='Supply pasted text, an uploaded file, or an https URL.'))


# --------------------------------------------------------- concept extraction
@dataclass
class ExtractedConcept:
    """One concept, with the exact slice of source text that produced it."""

    id: str
    title: str
    summary: str
    span: str
    span_start: int
    span_end: int
    kind: str              # 'heading' | 'definition' | 'term'
    section: str = ''      # the nearest preceding heading, for the taxonomy

    def to_dict(self) -> dict[str, Any]:
        return {'id': self.id, 'title': self.title, 'summary': self.summary, 'span': self.span,
                'span_range': [self.span_start, self.span_end], 'kind': self.kind,
                'section': self.section}


#: A sentence, with decimal points kept inside it: "Module 0.2 The Need for
#: Psychological Science" is one sentence, not three, and a term split across
#: the fragments of a version number is a term lost.
_SENTENCE = re.compile(r'(?:[^.!?\n]|(?<=\d)\.|\.(?=\d))+[.!?]*')
#: "X is the …", "X refers to …" - a *defining* predicate. The bare
#: ``is|are`` this used to accept also matches narrative prose ("Armend is
#: certain that electric cars will…") and quiz stems ("Which of the following
#: is an example of…"), and a course whose concepts are the names in the
#: practice questions is not a course. Requiring the article or a dictionary
#: verb keeps the definitions and drops the stories.
_DEFINITION = re.compile(
    r'^(?P<term>[A-Z][\w\'’-]*(?:\s+[A-Za-z][\w\'’-]*){0,5})\s+'
    r'(?P<verb>refers to|means|is defined as|is called|describes|consists of|involves|'
    r'i[ns]\s+(?:the|a|an|another|each|every|any|some|one|no)|'
    r'are\s+(?:the|a|an|another|each|every|any|some|no))\b')
_BOLD = re.compile(r'\*\*(?P<term>[^*\n]{3,60})\*\*')
_MARKDOWN_HEADING = re.compile(r'^\s{0,3}#{1,6}\s+')
_BULLET = re.compile(r'^\s*(?:[-*+•]|\d+[.)])\s+')
_STOP_TITLES = frozenset({
    'it', 'this', 'that', 'these', 'those', 'there', 'they', 'the', 'he', 'she', 'we', 'you',
    'however', 'therefore', 'for example', 'in summary', 'in short', 'summary', 'introduction',
    'overview', 'contents', 'chapter', 'section', 'note', 'notes', 'example', 'examples',
    'because', 'also', 'thus', 'hence', 'then', 'so', 'and', 'but', 'if', 'when', 'while',
})
#: A concept title is a noun phrase, never a question. A weighted run in a
#: textbook often carries a feature-box heading ("Did We Know It All Along?
#: Hindsight Bias"); the question half is dropped and the term half kept.
_QUESTION_LEAD = frozenset({
    'which', 'what', 'why', 'how', 'who', 'whom', 'whose', 'when', 'where', 'whether',
    'asked', 'ask', 'consider', 'suppose', 'imagine', 'explain', 'describe', 'discuss',
    'compare', 'contrast', 'define', 'identify', 'list', 'name', 'show', 'state',
    # Sentence openers: a paragraph that *begins* with one of these is narrative,
    # and the words after it are its subject, not a term ("After the resulting
    # oil spill, the cobia population…" defines no oil spill).
    'after', 'before', 'during', 'although', 'though', 'since', 'unless', 'until',
    'once', 'despite', 'unlike', 'according', 'among', 'between', 'both', 'each',
    'either', 'neither', 'some', 'many', 'most', 'several', 'other', 'others',
    'another', 'such', 'more', 'less', 'few', 'all', 'any', 'not', 'nor', 'yet',
    'still', 'even', 'just', 'only', 'very', 'rather', 'quite', 'indeed', 'perhaps',
    'maybe', 'usually', 'often', 'sometimes', 'always', 'never', 'here', 'there',
    'these', 'those', 'its', 'their', 'our', 'his', 'her',
})
#: A bold run made *entirely* of these words is a textbook's furniture - a box
#: label, a review prompt - rather than a term the course should teach.
_FURNITURE = frozenset({
    'the', 'a', 'an', 'of', 'and', 'or', 'for', 'to', 'in', 'on', 'your', 'you',
    'we', 'our', 'it', 'its', 'is', 'are', 'check', 'understand', 'understanding',
    'apply', 'concept', 'concepts', 'key', 'terms', 'points', 'question',
    'questions', 'answer', 'answers', 'review', 'summary', 'tip', 'tips',
    'practice', 'exercise', 'exercises', 'example', 'examples', 'exam', 'multiple',
    'choice', 'developing', 'arguments', 'box', 'panel', 'margin', 'note', 'notes',
})
#: A running header or a folio ("Module 0.2 …", "0.2-1 …") is page furniture,
#: not a concept. Stripped before the title is judged.
_RUNNING_PREFIX = re.compile(r'^(?:module|unit|chapter|section|part|lesson)\s+[\divx]+(?:[.:]\d+)*\s+',
                             re.I)


def _clean_title(raw: str) -> str:
    title = _MARKDOWN_HEADING.sub('', raw).strip()
    title = _BULLET.sub('', title).strip()
    title = title.strip('*_`#').strip()
    title = re.sub(r'\s+', ' ', title)
    title = title.strip(' :;,-').strip()
    return _RUNNING_PREFIX.sub('', title).strip()


def _trim(text: str, start: int, end: int) -> tuple[str, int, int]:
    """Trim whitespace while keeping the result an exact slice of ``text``."""
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return text[start:end], start, end


def _paragraph_spans(text: str) -> list[tuple[int, int]]:
    separators = [match for match in re.finditer(r'\n[ \t]*\n+', text)]
    bounds = [0] + [match.end() for match in separators] + [len(text)]
    spans: list[tuple[int, int]] = []
    for index in range(len(bounds) - 1):
        start, end = _trim(text, bounds[index], bounds[index + 1])[1:]
        if end > start:
            spans.append((start, end))
    return spans


def _is_heading(block: str) -> bool:
    stripped = block.strip()
    if not stripped or len(stripped) > 90:
        return False
    if _MARKDOWN_HEADING.match(stripped):
        return True
    if len(stripped.split()) > 12:
        return False
    # A heading does not contain sentence punctuation; a short sentence does.
    return not re.search(r'[.!?]', stripped)


def _plain_span(text: str, limit: int | None = None) -> str:
    """Strip this module's private ``**term`` markers from learner-visible text.

    The markers exist only so the concept extractor can see which runs the font
    drew with weight. A learner reading a lesson, or a quiz option quoting the
    source, must see the words the document actually contains. ``limit`` caps a
    summary; a span is stored whole because prerequisite detection reads it.
    """
    plain = text.replace('**', '').strip()
    return plain[:limit] if limit else plain


def _title_is_usable(title: str) -> bool:
    """Judge a candidate title against the junk a real document produces."""
    cleaned = title.strip()
    if not 3 <= len(cleaned) <= 60:
        return False
    if cleaned.casefold() in _STOP_TITLES:
        return False
    if not re.search(r'[A-Za-z]', cleaned):
        return False
    if len(cleaned.split()) > 8:
        return False
    # A question is never a concept, and "of the following" is the tell that a
    # quiz stem is being read as a term.
    if '?' in cleaned or ' of the following' in cleaned.casefold():
        return False
    # A comma means the run was a list fragment ("bias, overconfidence, and the
    # tendency to"), and a trademark mark means it is a brand, not a subject.
    if ',' in cleaned or '®' in cleaned or '™' in cleaned:
        return False
    words = [word.casefold().strip('.,;:!?\'"()[]') for word in cleaned.split()]
    if words[0] in _QUESTION_LEAD:
        return False
    # A title made entirely of pedagogical function words is a textbook's
    # furniture - a box label, a review prompt - whatever font it arrived in.
    if words and all(word in _FURNITURE for word in words if word):
        return False
    return True


def extract_concepts(text: str, *, limit: int = MAX_CONCEPTS) -> list[ExtractedConcept]:
    """Derive concepts and their verbatim spans from prose, deterministically.

    Three signals, all of them *in the source*:

    * a short standalone line (a markdown heading, a title line) is a concept,
      with the following paragraph's first sentence as its summary;
    * a sentence of the form "X is ...", "X refers to ...", "X means ..." defines
      X, and the whole sentence is the span;
    * a bold run ``**term**`` names a term, and the containing sentence is the span.

    Concepts are de-duplicated by slug and returned in source order. Nothing here
    is inferred from outside the text, which is what makes it reproducible.
    """
    paragraphs = _paragraph_spans(text)
    found: list[tuple[int, ExtractedConcept]] = []
    seen: set[str] = set()
    section = ''

    def consider(title: str, summary: str, span: str, start: int, end: int, kind: str) -> None:
        cleaned = _clean_title(title)
        if not _title_is_usable(cleaned):
            return
        # ``slug`` is the same id function the classifier and the graph use, so a
        # concept's extracted id and its graph node id are the same string by
        # construction rather than by coincidence.
        key = slug(cleaned)
        if key in seen:
            return
        seen.add(key)
        # The ``**`` term markers are this module's private notation for "the
        # font was weighted here"; they were never in the learner's document, so
        # they are stripped before the span is stored, shown in a lesson, or
        # offered as a quiz option.
        found.append((start, ExtractedConcept(
            id=key, title=cleaned, summary=_plain_span(summary, 240), span=_plain_span(span),
            span_start=start, span_end=end, kind=kind, section=section)))

    for index, (start, end) in enumerate(paragraphs):
        block, block_start, block_end = _trim(text, start, end)
        if _is_heading(block):
            heading = _clean_title(block)
            section = heading or section
            following = ''
            if index + 1 < len(paragraphs):
                nxt_start, nxt_end = paragraphs[index + 1]
                following_block, _, _ = _trim(text, nxt_start, nxt_end)
                first = _SENTENCE.match(following_block)
                following = (first.group().strip() if first else following_block)[:240]
            # An explicit markdown heading names a concept at any length; an
            # inferred one (a short standalone line in a flattened PDF) has to
            # earn it with a second word, because "Why" and "It" are lines too.
            explicit = bool(_MARKDOWN_HEADING.match(block))
            if explicit or len(heading.split()) >= 2:
                consider(heading, following or heading, block, block_start, block_end,
                         'heading')
            continue

        for sentence in _SENTENCE.finditer(text, start, end):
            raw, sent_start, sent_end = _trim(text, sentence.start(), sentence.end())
            if len(raw) < 20:
                continue
            match = _DEFINITION.match(raw)
            if match:
                consider(match.group('term'), raw, raw, sent_start, sent_end, 'definition')
            for bold in _BOLD.finditer(raw):
                consider(bold.group('term'), raw, raw, sent_start, sent_end, 'term')

    found.sort(key=lambda row: (row[0], row[1].id))
    return [concept for _, concept in found[:limit]]


def _source_health(intake: Intake) -> Refusal | None:
    """Check the source against the published minimums, in a fixed order."""
    text = intake.text
    if len(text) < MIN_SOURCE_CHARS or word_count(text) < MIN_SOURCE_WORDS:
        return _refuse('source_too_short',
                       detail=f'{len(text)} characters, {word_count(text)} words')
    if paragraph_count(text) < MIN_SOURCE_PARAGRAPHS:
        return _refuse('too_few_paragraphs', detail=f'{paragraph_count(text)} paragraph(s)')
    return None


# ------------------------------------------------------- graph construction
def _prefix_for(course_id: str) -> str:
    return f'{course_id}_'


def namespaced_id(course_id: str, raw_id: str) -> str:
    """A concept id that cannot collide with a shipped course's concept.

    Concept ids are global - they key learner state, attempts and memory notes -
    so a learner's ``fractions`` must not overwrite the shipped ``fractions``.
    The course id prefix makes the two namespaces disjoint by construction.
    """
    prefix = _prefix_for(course_id)
    room = MAX_ID - len(prefix)
    return f'{prefix}{raw_id[:room]}'


def _mentions(haystack: str, title: str) -> bool:
    """True when ``haystack`` names ``title`` as a whole phrase.

    The phrase has to be at least three characters so that a stray article cannot
    link half the course to itself (three-letter concept names such as "ATP" are
    real and are kept), and it must match on a word boundary so that "ratio" does
    not fire inside "rational".
    """
    needle = title.strip()
    if len(needle) < 3:
        return False
    return re.search(r'(?<![A-Za-z0-9])' + re.escape(needle) + r'(?![A-Za-z0-9])',
                     haystack, re.IGNORECASE) is not None


def _declared_prerequisites(concepts: Sequence[ExtractedConcept], index: int) -> list[str]:
    """Earlier concepts that this concept's own text refers to.

    This is the *declared intent* signal of the ingest classifier, read from the
    source rather than from an authoring form: a passage that defines an idea in
    terms of an earlier one has declared the dependency. Nothing is inferred from
    mere proximity, which is why a list of unrelated bullets produces no
    prerequisite edges at all - it produces teaching order instead.
    """
    current = concepts[index]
    haystack = f'{current.span} {current.summary}'
    return [other.title for other in concepts[:index] if _mentions(haystack, other.title)]


def build_graph(concepts: Sequence[ExtractedConcept], *, course_id: str,
                course_label: str, subject: str,
                source: SourcePolicy = LEARNER_SOURCE) -> tuple[KnowledgeGraph, dict[str, ExtractedConcept]]:
    """Order the concepts into a prerequisite DAG, reusing the ingest classifier.

    Two edge kinds, both of them from the source:

    * a **hard prerequisite** where one concept's own passage names an earlier
      one - the classifier's "declared intent" signal, and the only thing strong
      enough to gate progress;
    * a **teaching-order** edge chaining the source's own sequence, which orders
      the course without claiming a dependency the source never stated.

    The classifier refuses any edge that would close a cycle, so the result is
    acyclic by construction; the graph is validated afterwards anyway, because
    "the builder says so" is not the same as "the graph is valid".

    ``source`` is the rights position the concepts are stamped with. It defaults to
    learner-supplied material because that was the only kind of source this module
    used to accept, but it is a parameter because a course built from a licence-cleared
    outside source - a CC BY-SA encyclopedia article, say - must not have its
    provenance recorded as "supplied by the learner". That would be a false statement
    about where the material came from, stored in the graph and shown on the concept.
    """
    records: list[RawNode] = []
    for order, concept in enumerate(concepts):
        records.append(RawNode(
            title=concept.title,
            order=order,
            strand_hint=subject or 'Your material',
            unit_hint=course_label or 'Your material',
            topic_hint=concept.section or 'General',
            summary=concept.summary,
            keywords=tokens(concept.title),
            prerequisites=_declared_prerequisites(concepts, order),
        ))

    classifier = Classifier(rules=ClassificationRules(
        sequence_within='unit',   # the source's own order, as teaching order only
        keyword_edges=False,      # title word-overlap is not evidence of a prerequisite
        unit_bridge=False,
    ))
    graph, _report = classifier.build(records, [source],
                                      pack_name=course_id, pack_title=course_label)

    by_slug = {concept.id: concept for concept in concepts}
    mapping = {node_id: by_slug[node_id] for node_id in graph.nodes if node_id in by_slug}
    renamed, id_map = _rekey(graph, course_id)
    spans = {id_map[node_id]: concept for node_id, concept in mapping.items()}
    for concept_id, concept in spans.items():
        node = renamed.nodes[concept_id]
        node.summary = concept.summary or node.summary
        node.provenance.update({
            'source': source.name,
            'url': source.url,
            'licence': source.licence,
            'licence_class': source.licence_class.value,
            'attribution': source.attribution,
            'span': concept.span,
            'span_range': [concept.span_start, concept.span_end],
            'span_kind': concept.kind,
        })
        node.keywords = sorted({*node.keywords, concept.section.casefold()} - {''})

    issues = renamed.errors()
    if issues:
        summary = '; '.join(f'{issue.kind}({issue.concept_id})' for issue in issues[:5])
        raise BuildRefused(Refusal(
            code='graph_invalid',
            reason='The concepts in this source could not be ordered into a cycle-free prerequisite '
                   'graph, so no course was built from it.',
            detail=summary))
    return renamed, spans


def _rekey(graph: KnowledgeGraph, course_id: str) -> tuple[KnowledgeGraph, dict[str, str]]:
    """Namespace every node id and rewrite the edges that name them."""
    mapping = {node_id: namespaced_id(course_id, node_id) for node_id in graph.nodes}
    renamed = KnowledgeGraph(graph.taxonomy)
    for node_id in graph.topological_order():
        original = graph.nodes[node_id]
        clone = ConceptNode.from_dict(original.to_dict())
        clone.id = mapping[node_id]
        clone.prerequisites = [mapping.get(p, p) for p in original.prerequisites]
        clone.sequence_predecessors = [mapping.get(p, p) for p in original.sequence_predecessors]
        clone.has_lesson = True
        renamed.add(clone)
    return renamed, mapping


# ------------------------------------------------------------------- content
_EQUATION = re.compile(r'[^.\n]{0,80}?=[^.\n]{1,80}')


def _formula_in(span: str) -> str:
    """A formula, but only one the source actually states."""
    match = _EQUATION.search(span)
    if not match:
        return ''
    candidate = match.group().strip(' ,;:')
    if len(candidate) > 80 or not re.search(r'[A-Za-z0-9]', candidate):
        return ''
    return candidate


def _worked_walkthrough(title: str, span: str,
                        prerequisites: list[ConceptNode],
                        dependants: list[ConceptNode]) -> str:
    """A worked example that is a *method*, not a second copy of the source.

    The ``concept`` block already states the idea and ``source_span`` preserves the
    exact wording. Repeating that sentence as the worked example left the learner
    with nothing to work through - the first-person acceptance run recorded it as
    the generated lesson's missing independent example.

    Every step below is an operation on words the learner supplied or on edges in
    their own course graph. Nothing about the subject matter is invented, so the
    example stays honest while being a different artefact from the passage: it can
    be read, performed, and checked, which is what makes it a worked example.
    """
    quote = ' '.join(str(span or '').split())
    neighbour = (prerequisites[0].title if prerequisites
                 else (dependants[0].title if dependants else ''))
    steps = [
        f'Step 1 - Read the exact passage you supplied for {title}: "{quote}"',
        'Step 2 - Mark the words that say what this idea is or does. Put one bracket '
        'around its subject and another around the claim made about that subject.',
        'Step 3 - Close the source and restate the bracketed claim in one sentence of '
        'your own words. Reopen the passage and check that your sentence kept the same '
        'subject and the same claim.',
    ]
    if neighbour:
        steps.append(
            f'Step 4 - Say how {title} differs from {neighbour} using only what your '
            'source states. If you cannot name a difference, write down the exact words '
            'you would need to look up rather than guessing one.')
        steps.append(
            'Step 5 - Write one statement that would be wrong if this passage were wrong. '
            'That is the claim to retrieve tomorrow: the retrieval block below asks for '
            'it with the source closed.')
    else:
        steps.append(
            f'Step 4 - {title} has no neighbouring concept in your source yet. Write one '
            'statement that would be wrong if this passage were wrong, and name the words '
            'in the passage that make your statement right.')
        steps.append(
            'Step 5 - Retrieve that statement tomorrow with the source closed, then '
            'compare it against the passage and note any word you had to add yourself.')
    return ' '.join(steps)


def lesson_blocks(node: ConceptNode, graph: KnowledgeGraph, concept: ExtractedConcept) -> list[dict[str, Any]]:
    """Teaching blocks in the schema ``app.curriculum`` already renders.

    The verbatim passage stays on the ``concept`` block as ``source_span`` (and on
    the concept itself as provenance). The ``worked_example`` is now an independent
    walkthrough of that passage: it quotes the learner's own words, then gives a
    numbered method for working with them. No fact about the subject is invented.
    """
    title = node.title
    prerequisites = [graph.nodes[p] for p in graph.parents(node.id) if p in graph.nodes]
    dependants = [graph.nodes[c] for c in graph.children(node.id) if c in graph.nodes]
    depth = len(graph.ancestors(node.id))
    core = concept.summary or node.summary or f'{title} comes from your own source material.'
    if prerequisites:
        core += (' It builds on ' + ', '.join(p.title for p in prerequisites[:3]) +
                 ' earlier in your source.')
    else:
        core += ' Nothing in your source has to come before it, so it is a place you can start.'

    return [
        {'kind': 'concept', 'title': 'Core idea', 'body': core,
         'formula': _formula_in(concept.span), 'source_span': concept.span},
        {'kind': 'worked_example', 'title': 'Work through your source',
         'body': _worked_walkthrough(title, concept.span, prerequisites, dependants),
         'formula': ''},
        {'kind': 'retrieval', 'title': 'Check before you go on',
         'body': (f'Close the source and say what {title} means in your own words. Then reopen it '
                  f'and compare against the passage you supplied'
                  + (f', and against {prerequisites[0].title}, which comes first.' if prerequisites
                     else '.')),
         'formula': ''},
        {'kind': 'reflection', 'title': 'Reflect',
         'body': (f'Which part of {title} is still unclear to you? Name the specific term or step '
                  f'rather than the whole idea'
                  + (f'. Understanding it unlocks {len(dependants)} later concept(s): '
                     + ', '.join(d.title for d in dependants[:4]) + '.' if dependants else '.')
                  + (' ' + f'It sits {depth} step(s) deep in your source\'s order.' if depth else '')
                  + ' If you used any AI tool while studying this, say where.'),
         'formula': ''},
    ]


def concept_entry(course_id: str, node: ConceptNode, graph: KnowledgeGraph,
                  concept: ExtractedConcept) -> dict[str, Any]:
    """One concept in the ``CONCEPTS`` registry shape, so every route works unchanged."""
    prerequisites = [p for p in graph.parents(node.id) if p in graph.nodes]
    return {
        'id': node.id,
        'title': node.title,
        'unit': node.unit or '',
        'strand': node.strand or '',
        'topic': node.topic or '',
        'tier': node.tier or 'core',
        'difficulty': int(node.difficulty or 3),
        'graph_id': node.id,
        'has_lesson': True,
        'generated': True,
        'course_id': course_id,
        'prerequisites': prerequisites,
        'summary': concept.summary or node.summary or '',
        'blocks': lesson_blocks(node, graph, concept),
        # Provenance, surfaced on the concept itself so a learner never has to take
        # the lesson's word for where an idea came from.
        'source_span': concept.span,
        'source_range': [concept.span_start, concept.span_end],
        'source_kind': concept.kind,
        'simulation': {
            'kind': 'concept_map',
            'title': f'{node.title}: how it connects',
            'scope': ("A concept map derived from your own source's prerequisite order and your "
                      'recorded mastery. It is not a physical or mathematical model.'),
            'parameters': [],
        },
        'project': {
            'title': f'{node.title}: explain and apply',
            'prompt': (f'Explain {node.title} in your own words using only what your source states, '
                       f'then apply it to one example of your own.'),
            'rubric': [
                'State the idea in your own words, not the source wording.',
                'Point to the passage in your source it came from.',
                'Connect it explicitly to at least one concept that comes before it.',
                'Name one thing you are still unsure about, and disclose any AI assistance.',
            ],
        },
        'media': [],
        'hint': (f'Start from {graph.nodes[prerequisites[0]].title}, not from this concept.'
                 if prerequisites else
                 f'Read the passage you supplied for {node.title} before trying to use it.'),
    }


# ------------------------------------------------------------------ questions
OPTION_IDS = ('a', 'b', 'c', 'd')
OPTIONS = 4
#: Variants per concept. Four keeps every concept answerable more than once without
#: asking the same thing twice, and matches the generated layer's contract.
VARIANTS = 4


def _short(value: str, length: int = 12) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()[:length]


def _question_id(course_id: str, node_id: str, variant: int) -> str:
    # The prefix is the *whole* course id, not a slice of it. Question ids live in
    # one global ``curriculum.QUESTIONS`` dict, so two courses that truncated to the
    # same short prefix would collide and one course's item would silently replace
    # the other's. Ten hex characters of id is a collision-free namespace; five is
    # not (a few hundred created courses make a birthday collision likely).
    prefix = course_id
    candidate = f'{prefix}-{node_id}-{variant}'
    if len(candidate) <= MAX_ID:
        return candidate
    room = MAX_ID - len(prefix) - len(str(variant)) - len(_short(node_id, 10)) - 3
    return f'{prefix}-{node_id[:max(1, room)]}-{_short(node_id, 10)}-{variant}'


def _excerpt(text: str, limit: int = 150) -> str:
    collapsed = re.sub(r'\s+', ' ', text).strip()
    return collapsed if len(collapsed) <= limit else collapsed[:limit - 1].rstrip() + '…'


def _assemble(course_id: str, node: ConceptNode, concept: ExtractedConcept, variant: int, *,
              prompt: str, correct_text: str, distractors: Sequence[tuple[str, str]],
              category: str, explanation: str, next_action: str) -> dict[str, Any]:
    """One four-option item: deterministic shuffle, one correct, three diagnoses."""
    seed = f'{course_id}|{node.id}|{variant}'
    entries: list[tuple[bool, str, str]] = [(True, node.id, correct_text)]
    entries.extend((False, source_id, text) for source_id, text in distractors)
    entries = sorted(entries, key=lambda row: hashlib.sha256(
        f'{seed}|{row[1]}|{row[2]}'.encode('utf-8')).hexdigest())[:OPTIONS]

    options: list[dict[str, str]] = []
    diagnoses: dict[str, dict[str, str]] = {}
    answer_id = OPTION_IDS[0]
    for index, (is_correct, source_id, text) in enumerate(entries):
        option_id = OPTION_IDS[index]
        options.append({'id': option_id, 'text': text})
        if is_correct:
            answer_id = option_id
            continue
        confused = source_id
        diagnoses[option_id] = {
            'category': 'conceptual',
            'reason': (f'This belongs to "{confused}", not to "{node.title}". Naming which idea a '
                       f'wrong option belongs to turns a wrong answer into a diagnosis.'
                       if confused else 'This belongs to a different part of your course.'),
            'next_action': next_action,
        }

    band = ('foundation' if node.difficulty <= 2 else
            'core' if node.difficulty <= 4 else 'extension')
    return {
        'id': _question_id(course_id, node.id, variant),
        'concept_id': node.id,
        'concept_title': node.title,
        'prompt': prompt,
        'options': options,
        'kind': 'generated_multiple_choice',
        'generated': True,
        'expected_seconds': 45,
        'answer_id': answer_id,
        'answer_text': correct_text,
        'explanation': explanation,
        'category': category,
        'difficulty': int(node.difficulty or 3),
        'difficulty_band': band,
        'source_span': concept.span,
        'distractor_diagnoses': diagnoses,
    }


def _other_nodes(node: ConceptNode, graph: KnowledgeGraph) -> list[ConceptNode]:
    return sorted((other for other in graph.nodes.values() if other.id != node.id),
                  key=lambda other: other.id)


def build_questions(course_id: str, graph: KnowledgeGraph,
                    spans: Mapping[str, ExtractedConcept]) -> dict[str, dict[str, Any]]:
    """Four grounded variants per concept, each citing the concept and its span.

    Every correct answer is a fact from the source or from the graph built out of
    it: the concept's own summary, a real prerequisite edge, a real teaching-order
    edge, or the verbatim passage. No item asks the learner to guess at something
    the harness does not actually hold.
    """
    questions: dict[str, dict[str, Any]] = {}
    for node_id in sorted(graph.nodes):
        node = graph.nodes[node_id]
        concept = spans[node_id]
        others = _other_nodes(node, graph)
        prerequisites = [graph.nodes[p] for p in graph.parents(node_id) if p in graph.nodes]
        dependants = [graph.nodes[c] for c in graph.children(node_id) if c in graph.nodes]

        # 1. Definition: the concept's own summary, with other concepts' summaries as distractors.
        pool = [other for other in others if other.summary]
        definition_distractors = [(other.title, other.summary) for other in pool[:OPTIONS - 1]]
        while len(definition_distractors) < OPTIONS - 1 and pool:
            definition_distractors.append((pool[0].title, pool[0].summary))
        items = [_assemble(
            course_id, node, concept, 0,
            prompt=f'Which statement best describes {node.title}?',
            correct_text=concept.summary or node.summary,
            distractors=definition_distractors,
            category='definition_recall',
            explanation=('The correct option is the sentence your own source uses for '
                         f'{node.title}. The others are the source\'s statements about different '
                         'concepts, which is what makes them plausible.'),
            next_action=f'Re-read the passage you supplied for {node.title}.')]

        # 2. Prerequisite: a real edge, or the reverse edge when the concept is a root.
        if prerequisites:
            correct = prerequisites[0]
            prompt = f'Which idea must you understand first to make sense of {node.title}?'
            explanation = (f'{correct.title} comes before {node.title} in the order your source '
                           f'presents them.')
            banned = {p.id for p in prerequisites} | {node_id}
        elif dependants:
            correct = dependants[0]
            prompt = f'Which of these does your source present after {node.title}?'
            explanation = (f'{correct.title} lists {node.title} as a prerequisite in your course '
                           f'graph, so it cannot be met first.')
            banned = {d.id for d in dependants} | {node_id}
        else:
            correct = others[0]
            prompt = f'Which of these is a different concept from {node.title} in your course?'
            explanation = (f'{correct.title} is a separate concept in your own material; '
                           f'{node.title} stands alone in the order your source gives.')
            banned = {node_id}
        distractors = [(other.title, other.title) for other in others if other.id not in banned]
        while len(distractors) < OPTIONS - 1:
            distractors.append((others[0].title, others[0].title))
        items.append(_assemble(
            course_id, node, concept, 1, prompt=prompt, correct_text=correct.title,
            distractors=distractors[:OPTIONS - 1], category='prerequisite_structure',
            explanation=explanation,
            next_action=f'Open the knowledge map for {node.title} and read what it rests on.'))

        # 3. Teaching order: what the source presents next, or what comes before it.
        if dependants:
            correct = dependants[0]
            prompt = f'Which of these does your source present later than {node.title}?'
            explanation = (f'{correct.title} depends on {node.title} in your course graph, so the '
                           f'source meets it later.')
            banned = {d.id for d in dependants} | {node_id}
        elif prerequisites:
            correct = prerequisites[-1]
            prompt = f'Which of these does your source present earlier than {node.title}?'
            explanation = (f'{correct.title} is a prerequisite of {node.title} in your course '
                           f'graph, so it is met earlier.')
            banned = {p.id for p in prerequisites} | {node_id}
        else:
            correct = others[0]
            prompt = f'Which of these is a separate part of your source from {node.title}?'
            explanation = (f'{correct.title} is a distinct concept in your own material, with no '
                           f'ordering relation to {node.title}.')
            banned = {node_id}
        distractors = [(other.title, other.title) for other in others if other.id not in banned]
        while len(distractors) < OPTIONS - 1:
            distractors.append((others[0].title, others[0].title))
        items.append(_assemble(
            course_id, node, concept, 2, prompt=prompt, correct_text=correct.title,
            distractors=distractors[:OPTIONS - 1], category='teaching_order',
            explanation=explanation,
            next_action=f'Look at what {node.title} comes before on the concept map.'))

        # 4. Provenance: match the concept to the passage it came from. This is the item
        #    that makes provenance checkable rather than merely displayed.
        span_distractors = [(other.id, _excerpt(spans[other.id].span)) for other in others]
        items.append(_assemble(
            course_id, node, concept, 3,
            prompt=f'Which passage from your source is the one that defines {node.title}?',
            correct_text=_excerpt(concept.span),
            distractors=span_distractors[:OPTIONS - 1], category='source_provenance',
            explanation=(f'The correct option is the verbatim passage in your source that '
                         f'{node.title} was extracted from. The others are passages about other '
                         f'concepts in the same material.'),
            next_action=f'Search your source for the words in the correct passage.'))

        for item in items:
            questions[item['id']] = item
    return questions


# ---------------------------------------------------------------------- plan
@dataclass
class CoursePlan:
    """Everything a course needs, before it is stored anywhere."""

    course_id: str
    title: str
    subject: str
    level: str
    intake: Intake
    graph: KnowledgeGraph
    concepts: dict[str, dict[str, Any]]
    questions: dict[str, dict[str, Any]]
    extracted: list[ExtractedConcept]
    #: The rights position the material came in under. Carried rather than re-derived
    #: because a course built from a CC BY-SA article and one built from a learner's
    #: own notes are different facts, and both the preview and the stored row have to
    #: be able to say which one this is.
    source: SourcePolicy = LEARNER_SOURCE

    def stats(self) -> dict[str, Any]:
        return self.graph.stats()

    def to_preview(self) -> dict[str, Any]:
        """What the learner sees *before* committing: concepts, graph and questions."""
        return {
            'course_id': self.course_id,
            'title': self.title,
            'subject': self.subject,
            'level': self.level,
            'source': self.intake.to_dict(),
            # Where the material came from and what may be done with it. A learner is
            # entitled to see the rights position before they commit a course to it,
            # and a CC BY-SA source carries an attribution and a share-alike obligation
            # that "your own notes" does not.
            'source_rights': {
                'name': self.source.name,
                'url': self.source.url,
                'licence': self.source.licence,
                'licence_class': self.source.licence_class.value,
                'attribution': self.source.attribution,
                'needs_attribution': self.source.needs_attribution,
            },
            'concepts': [self.concepts[cid] for cid in self.concepts],
            'graph': self.graph.to_payload(),
            'graph_stats': self.stats(),
            'questions': [self.questions[qid] for qid in sorted(self.questions)],
            'questions_total': len(self.questions),
            'rights_note': RIGHTS_NOTE,
            'honesty': [
                'Every concept is extracted from your source and carries the verbatim passage it '
                'came from.',
                'The prerequisite order comes from the passages that name an earlier idea, plus the '
                'order your source presents them in. No subject-matter model was applied.',
                'No language model was used. The same source always produces the same course.',
            ],
        }


def _course_id() -> str:
    return f'{COURSE_ID_PREFIX}{uuid4().hex[:10]}'


def plan_course(intake: Intake, *, title: str = '', subject: str = '', level: str = 'custom',
                course_id: str | None = None,
                source: SourcePolicy = LEARNER_SOURCE) -> CoursePlan:
    """Extract, order, write and quiz. Raises :class:`BuildRefused` rather than faking."""
    refusal = _source_health(intake)
    if refusal is not None:
        raise BuildRefused(refusal)

    extracted = extract_concepts(intake.text)
    if len(extracted) < MIN_CONCEPTS:
        raise BuildRefused(_refuse(
            'too_few_concepts',
            detail=f'{len(extracted)} concept(s) found: '
                   + ', '.join(concept.title for concept in extracted[:8])))

    cid = course_id or _course_id()
    course_label = (title or '').strip() or _default_title(intake)
    chosen_subject = (subject or '').strip() or 'Your material'
    graph, spans = build_graph(extracted, course_id=cid, course_label=course_label,
                               subject=chosen_subject, source=source)
    # Read order: prerequisites first, then the order the source itself uses. A
    # learner opening the course should meet the ideas in the sequence they wrote
    # them in, without ever meeting one before what it rests on.
    depths = graph.depths()
    ordered_ids = sorted(graph.nodes,
                         key=lambda node_id: (depths.get(node_id, 0),
                                              spans[node_id].span_start, node_id))
    concepts = {node_id: concept_entry(cid, graph.nodes[node_id], graph, spans[node_id])
                for node_id in ordered_ids}
    questions = build_questions(cid, graph, spans)
    return CoursePlan(course_id=cid, title=course_label, subject=chosen_subject,
                      level=(level or 'custom').strip() or 'custom', intake=intake,
                      graph=graph, concepts=concepts, questions=questions,
                      extracted=[spans[node_id] for node_id in ordered_ids],
                      source=source)


def _default_title(intake: Intake) -> str:
    if intake.source_kind == 'url':
        host = intake.url.split('://', 1)[-1].split('/', 1)[0]
        return f'My course from {host}'
    if intake.source_kind == 'file':
        stem = re.sub(r'\.[A-Za-z0-9]{1,5}$', '', intake.label or 'my source')
        return f'My course from {stem}'
    first = re.split(r'\n[ \t]*\n+', intake.text.strip())[0].strip()
    if _is_heading(first):
        return _clean_title(first)[:120] or 'My course'
    return 'My course from pasted text'


# -------------------------------------------------------------- persistence
class CreatedCourse(Base):
    """A course a learner built from their own material.

    One row holds the whole course: the source text (so provenance is inspectable
    long after the paste), the graph pack and the two materialised registries.
    Storing the materialised layers rather than re-deriving them on read is what
    makes a course byte-identical every time it is opened.

    No ``SCHEMA_VERSION`` bump accompanies this table. A version bump is for a
    *column* added to a table that already shipped, which ``create_all`` cannot
    apply; a brand-new table is created on both a fresh database and an upgraded
    one by ``scripts/init_db.initialize``, so the two build paths agree already.
    """

    __tablename__ = 'created_courses'
    __table_args__ = (
        Index('created_courses_user_idx', 'user_id', 'created_at'),
    )
    id: Mapped[str] = mapped_column(String(MAX_ID), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    title: Mapped[str] = mapped_column(String(200))
    subject: Mapped[str] = mapped_column(String(80), default='Your material')
    level: Mapped[str] = mapped_column(String(40), default='custom')
    source_kind: Mapped[str] = mapped_column(String(16))
    source_label: Mapped[str] = mapped_column(String(300))
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source_format: Mapped[str] = mapped_column(String(16), default='text')
    source_chars: Mapped[int] = mapped_column(Integer, default=0)
    source_text: Mapped[str] = mapped_column(Text)
    pack: Mapped[dict] = mapped_column(JSON)
    concepts: Mapped[dict] = mapped_column(JSON)
    questions: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[float] = mapped_column(Float, default=now_ts)

    def to_dict(self, *, with_graph: bool = False) -> dict[str, Any]:
        payload = {
            'id': self.id,
            'title': self.title,
            'subject': self.subject,
            'level': self.level,
            'authored': False,
            'generated': True,
            'custom': True,
            'expected_weeks': max(1, round(len(self.concepts) / 5)),
            'source': {'kind': self.source_kind, 'label': self.source_label,
                       'url': self.source_url or '', 'format': self.source_format,
                       'characters': self.source_chars},
            'concepts': len(self.concepts),
            'questions': len(self.questions),
            'stats': self.graph().stats(),
            'created_at': self.created_at,
        }
        if with_graph:
            payload['graph'] = self.graph().to_payload()
        return payload

    def graph(self) -> KnowledgeGraph:
        return KnowledgeGraph.from_pack(self.pack)

    def spec(self) -> courses.Course:
        return courses.Course(
            id=self.id, title=self.title, subject=self.subject,
            subject_kind=CUSTOM_SUBJECT_KIND,
            description=(f'A course you built from your own material '
                         f'({self.source_label}). Every concept carries the passage it came from.'),
            pack='learner_material', expected_weeks=max(1, round(len(self.concepts) / 5)),
            authored=False,
        )


# ------------------------------------------- runtime registration / studyability
#: Created courses are registered into the same registries the shipped courses
#: live in, so every existing endpoint serves them with no special case:
#:
#: * ``courses.COURSE_BY_ID`` / ``courses.graph_for`` - so ``enrolled_course`` and
#:   ``course_graph`` resolve them for ``/curriculum`` and ``/knowledge-graph``;
#: * ``curriculum.CONCEPTS`` / ``QUESTIONS`` / ``CONCEPT_COURSE`` - so
#:   ``course_concepts`` / ``course_questions`` scope them for ``/lessons/{id}``
#:   and ``/questions/next``.
_RUNTIME_COURSES: dict[str, courses.Course] = {}
_RUNTIME_GRAPHS: dict[str, KnowledgeGraph] = {}
_STORE_FACTORY: Any = None
_INSTALLED = False


def attach_store(factory: Any) -> None:
    """Remember the session factory so a persisted course can be re-hydrated later.

    Without this a created course would be studyable only in the process that
    built it: after a restart the registry is empty and the learner would silently
    land on the default course. With it, the first lookup re-reads the row.
    """
    global _STORE_FACTORY
    _STORE_FACTORY = factory


def _hydrate(course_id: str) -> bool:
    """Load a persisted course into the runtime registry. Never raises."""
    if course_id in _RUNTIME_COURSES:
        return True
    if _STORE_FACTORY is None:
        return False
    try:
        with _STORE_FACTORY() as db:
            row = db.get(CreatedCourse, course_id)
            if row is None:
                return False
            publish(row)
        return True
    except Exception:  # noqa: BLE001 - a lookup that cannot hydrate degrades to "unknown"
        return False


def publish(row: CreatedCourse) -> None:
    """Make one stored course resolvable and studyable through the existing endpoints."""
    graph = row.graph()
    for concept_id, entry in row.concepts.items():
        if concept_id in curriculum.CONCEPTS and \
                curriculum.CONCEPT_COURSE.get(concept_id) not in (None, row.id):
            raise ValueError(f'Concept id {concept_id!r} already belongs to another course')
    _RUNTIME_COURSES[row.id] = row.spec()
    _RUNTIME_GRAPHS[row.id] = graph
    courses.COURSE_BY_ID[row.id] = _RUNTIME_COURSES[row.id]
    curriculum.CONCEPTS.update(row.concepts)
    curriculum.QUESTIONS.update(row.questions)
    for concept_id in row.concepts:
        curriculum.CONCEPT_COURSE[concept_id] = row.id


def runtime_courses() -> tuple[str, ...]:
    """The ids of the learner-built courses currently resident in this process.

    Exposed because ``publish`` puts a created course's concepts into the *shared*
    ``curriculum.CONCEPTS`` index - that is how ``course_concepts`` and the tutor's
    concept lookup resolve a course that exists only in the database. The consequence
    is that the global registry holds three populations, not two: authored,
    generated, and learner-built. Anything asserting a count over the registry (the
    invariant that the generated layer never overwrites authored material, and the
    health endpoint's reporting) has to account for the third, and guessing at it by
    filtering ids is how that assertion silently rots. So the population is published
    rather than inferred.
    """
    return tuple(_RUNTIME_COURSES)


def unregister(course_id: str) -> None:
    """Remove a deleted course from the runtime registries.

    A course nobody can open must not keep serving lessons, so the concepts *and*
    the questions they own are withdrawn from the shared registries together.
    """
    _RUNTIME_COURSES.pop(course_id, None)
    _RUNTIME_GRAPHS.pop(course_id, None)
    courses.COURSE_BY_ID.pop(course_id, None)
    for concept_id, owner in list(curriculum.CONCEPT_COURSE.items()):
        if owner != course_id:
            continue
        curriculum.CONCEPT_COURSE.pop(concept_id, None)
        curriculum.CONCEPTS.pop(concept_id, None)
        for question_id, question in list(curriculum.QUESTIONS.items()):
            if question.get('concept_id') == concept_id:
                curriculum.QUESTIONS.pop(question_id, None)


def _install_course_resolution() -> None:
    """Route ``courses.course`` and ``courses.graph_for`` through the runtime registry.

    ``courses`` is the seam the whole API resolves a learner's course through, and
    it is a shared module. Rather than editing it - and taking a dependency on
    another workstream's file - this feature registers itself, the same way a
    feature module registers its router. The patch is additive and idempotent:
    unknown ids still fall through to the original functions and still raise
    ``UnknownCourse``, and with no created course in play the behaviour is
    unchanged.
    """
    global _INSTALLED
    if _INSTALLED:
        return
    original_course = courses.course
    original_graph_for = courses.graph_for

    def course(course_id: str | None) -> courses.Course:
        try:
            return original_course(course_id)
        except courses.UnknownCourse:
            key = (course_id or '').strip()
            if key and _hydrate(key):
                return _RUNTIME_COURSES[key]
            raise

    def graph_for(course_id: str) -> KnowledgeGraph:
        key = (course_id or '').strip()
        if key and key not in _RUNTIME_GRAPHS:
            _hydrate(key)
        graph = _RUNTIME_GRAPHS.get(key)
        return graph if graph is not None else original_graph_for(course_id)

    courses.course = course
    courses.graph_for = graph_for
    _INSTALLED = True


def _register_user_scope_guard() -> None:
    """Put ``created_courses`` under the multi-tenant read guard.

    ``app.user_scope`` guards a reviewed list of table names, and its own docstring
    says that adding a user-owned table without listing it "recreates the leak this
    guard exists to close". The list is a module-level frozenset, so the feature
    registers its table by rebinding it rather than by editing that module.
    """
    from . import user_scope
    user_scope.USER_SCOPED_TABLES = user_scope.USER_SCOPED_TABLES | {CreatedCourse.__tablename__}


def save_course(db, user, plan: CoursePlan) -> CreatedCourse:
    """Persist a plan on the learner's account and make it immediately studyable."""
    row = CreatedCourse(
        id=plan.course_id,
        user_id=user.id,
        title=plan.title,
        subject=plan.subject,
        level=plan.level,
        source_kind=plan.intake.source_kind,
        source_label=plan.intake.label[:300],
        source_url=plan.intake.url or None,
        source_format=plan.intake.format,
        source_chars=len(plan.intake.text),
        source_text=plan.intake.text,
        pack=plan.graph.to_pack(name=plan.course_id, title=plan.title,
                                metadata={'generated_by': 'app.course_builder',
                                          'source_kind': plan.intake.source_kind,
                                          'source_policy': plan.source.name,
                                          'source_licence': plan.source.licence,
                                          'source_licence_class': plan.source.licence_class.value,
                                          'source_url': plan.source.url}),
        concepts=plan.concepts,
        questions=plan.questions,
    )
    db.add(row)
    db.commit()
    publish(row)
    return row


def courses_for(db, user) -> list[CreatedCourse]:
    """This learner's own courses, newest first. Scoped by ``user_id``, always."""
    from sqlalchemy import select
    return list(db.scalars(select(CreatedCourse)
                           .where(CreatedCourse.user_id == user.id)
                           .order_by(CreatedCourse.created_at.desc())))


def find_course(db, user, course_id: str) -> CreatedCourse | None:
    """One of this learner's courses. A stranger's id resolves to ``None``."""
    from sqlalchemy import select
    return db.scalar(select(CreatedCourse).where(CreatedCourse.id == course_id,
                                                 CreatedCourse.user_id == user.id))


def delete_course(db, user, course_id: str) -> bool:
    """Remove one of this learner's courses and everything derived from it."""
    row = find_course(db, user, course_id)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    unregister(course_id)
    return True


_register_user_scope_guard()
_install_course_resolution()


__all__ = ['CUSTOM_SUBJECT_KIND', 'CreatedCourse', 'CoursePlan', 'ExtractedConcept', 'Intake',
           'IntakeRefused', 'BuildRefused', 'Refusal', 'REFUSAL_RULES', 'RIGHTS_NOTE',
           'URL_MAX_BYTES', 'attach_store', 'build_graph', 'build_questions', 'courses_for',
           'delete_course', 'extract_concepts', 'find_course', 'intake_bytes', 'intake_from',
           'intake_text', 'intake_url', 'namespaced_id', 'plan_course', 'publish', 'refusal_rules',
           'save_course', 'unregister', 'word_count', 'paragraph_count', 'URL_FETCHER',
           'LEARNER_SOURCE']
