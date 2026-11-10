"""Grounded OpenStax textbook sections: fetched from the publisher, licence-gated, stored
with provenance, quoted with attribution.

Before this module existed the harness named OpenStax books only as external link-only
reference cards (``app.ingest.policy.RESTRICTED``), and every line of lesson text was either
hand-authored or model-tightened authored prose. That is the honest description of the
system's own audit trail, and it is why the textbook layer was *not* grounded. This module
adds the grounded layer without weakening the gate:

1. **The licence is read from the publisher, not assumed.** The book's rights position comes
   from OpenStax's own CMS API (``license_name`` / ``license_version`` / ``license_url``) and
   is classified with the same fail-close classifier every other source uses
   (:func:`app.ingest.policy.classify_licence`). An unknown licence is refused, not rounded
   to the nearest permissive one.

2. **Only audited books are eligible.** A book slug must appear in :data:`AUDITED_BOOKS`,
   which is the complete OpenStax catalogue as the publisher's own CMS API reports it
   (snapshotted by ``scripts/refresh_openstax_catalogue.py`` and audited in
   ``app.ingest.policy``), and the live API licence is cross-checked against the audited
   entry at fetch time: if OpenStax ever changes the licence of a cleared book, the next
   fetch refuses to store text.

3. **Non-commercial and unknown licences stay link-only, by evaluation.** Most current
   OpenStax editions report CC BY-NC-SA 4.0. ``CC_BY_NC_SA`` is not in ``INGESTIBLE``, so
   ``assert_ingestible`` refuses and the section is stored as a *link-only* record with the
   refusal reason and no text. The publisher-reported CC BY books -- 38 of 129 at the
   2026-11-10 audit, mostly retired first editions plus Physics, Statistics and a few live
   titles -- are the text-eligible set, and each still re-verifies against the live API at
   fetch time. Books the publisher serves with **no licence fields at all** are registered
   as known-and-refused: they are withheld with zero network requests and a reason that
   says so, because an unknown licence is not a permissive licence.

4. **A stored section is never sent to a model.** OpenStax's own notices prohibit ingesting
   their content into LLMs or generative-AI offerings. The lesson surface therefore exposes
   a stored section as a verbatim quote with its citation inside a ``callout`` block --
   a block type the prose-rewriting pass (``app.harness.generate._enhance``) never reads,
   because it only rewrites ``paragraph`` blocks -- and every payload bound for a model
   (the agent loop's tool results) passes through
   ``app.harness.generate.redact_textbook_quotes``, which replaces the verbatim text with
   a withholding notice while keeping the citation. The guarantee holds on both paths:
   the enhancement pass cannot read the quote, and the agent loop cannot see it.

5. **Provenance travels with the text.** Every stored record carries the source URL, book
   slug and uuid, page slug and title, author, licence fields, retrieval timestamp and a
   sha256 of the served HTML, so any quote in a lesson can be traced back to the exact bytes
   it came from.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlencode

import httpx

from ..policy import (AssetRefused, IngestionRefused, OPENSTAX_BOOK_POLICIES,
                      OPENSTAX_UNLICENSED, SourcePolicy, assert_ingestible, classify_licence,
                      openstax_catalogue_posture)

USER_AGENT = ('LuminfestLearningHarness/1.0 (educational, offline-first; local single-learner '
              'instance; stores section text only from licence-cleared OpenStax books)')

OPENSTAX_HOST = 'https://openstax.org'
#: Wagtail CMS endpoint that lists and details the books.
CMS_API = OPENSTAX_HOST + '/apps/cms/api/v2/pages/'
#: The publisher-served webview for a section; its HTML is server-rendered prose plus
#: ``citation_*`` metadata tags, which is what makes a verbatim quote with real provenance
#: possible without a headless browser.
SECTION_URL = OPENSTAX_HOST + '/books/{book_slug}/pages/{page_slug}'

#: How much of a section is quoted into a lesson. A quote, not a replacement textbook: the
#: lesson's own teaching prose stays authored, and the textbook paragraph anchors it to a
#: citable source.
QUOTE_CHARS = 480

#: Books with an audited, evidence-backed rights position in ``app.ingest.policy``: the
#: complete OpenStax catalogue as the publisher reports it. Every CC BY book in the
#: catalogue is text-eligible *subject to the live re-verification below*; every NC book is
#: audited link-only; every book the publisher serves with no licence fields at all is
#: registered in ``OPENSTAX_UNLICENSED`` and refused with zero network requests. A book
#: slug outside this map is still an unknown book, and an unknown book is refused -- the
#: catalogue widens what is audited, never what is assumed.
AUDITED_BOOKS: dict[str, SourcePolicy] = OPENSTAX_BOOK_POLICIES

#: Concept -> (book slug, page slug) for the grounding exposure. Every page slug here was
#: read from the live table of contents of the named book (the ``pages/index`` webview
#: embeds the full TOC as ``data-page-slug`` attributes); none is guessed. The mapping
#: prefers the first edition of *Algebra and Trigonometry* because its content covers the
#: Khan Academy Algebra 2 sequence and its licence (CC BY 4.0) permits text storage.
SECTION_MAP: dict[str, tuple[str, str]] = {
    'equations': ('algebra-and-trigonometry', '2-2-linear-equations-in-one-variable'),
    'inequalities': ('algebra-and-trigonometry', '2-7-linear-inequalities-and-absolute-value-inequalities'),
    'linear_functions': ('algebra-and-trigonometry', '4-1-linear-functions'),
    'quadratics': ('algebra-and-trigonometry', '5-1-quadratic-functions'),
    'systems': ('algebra-and-trigonometry', '11-1-systems-of-linear-equations-two-variables'),

    # ---- Algebra 1 (course ``algebra_1``) -------------------------------------------
    # One anchor per teaching unit of the twelve-unit Algebra 1 framework, so a generated
    # lesson for an entry concept can quote the textbook section that actually teaches it.
    # Every slug was resolved against the publisher's own table of contents or fetched and
    # confirmed (HTTP 200) on 2026-11-10; ``scripts/verify_algebra_1.py`` re-checks the
    # whole set. Books: elementary-algebra (1e, CC BY), algebra-and-trigonometry (1e, CC BY)
    # for function/sequence/exponential topics, introductory-statistics (1e, CC BY) for the
    # statistics unit. ``algebra-1`` is CC BY-NC-SA and therefore never appears here.
    'algebra_1_variables_and_expressions':
        ('elementary-algebra', '1-2-use-the-language-of-algebra'),
    'algebra_1_units_and_unit_conversion':
        ('elementary-algebra', '1-10-systems-of-measurement'),
    'algebra_1_one_step_equations':
        ('elementary-algebra', '2-1-solve-equations-using-the-subtraction-and-addition-properties-of-equality'),
    'algebra_1_variables_on_both_sides':
        ('elementary-algebra', '2-3-solve-equations-with-variables-and-constants-on-both-sides'),
    'algebra_1_rearranging_a_formula':
        ('elementary-algebra', '2-6-solve-a-formula-for-a-specific-variable'),
    'algebra_1_reversing_the_symbol':
        ('elementary-algebra', '2-7-solve-linear-inequalities'),
    'algebra_1_constraints_as_inequalities':
        ('elementary-algebra', '3-6-solve-applications-with-linear-inequalities'),
    'algebra_1_the_slope_formula':
        ('elementary-algebra', '4-4-understand-slope-of-a-line'),
    'algebra_1_slope_intercept_form':
        ('elementary-algebra', '4-5-use-the-slope-intercept-form-of-an-equation-of-a-line'),
    'algebra_1_common_difference':
        ('algebra-and-trigonometry', '13-2-arithmetic-sequences'),
    'algebra_1_center_and_spread':
        ('introductory-statistics', '2-5-measures-of-the-center-of-the-data'),
    'algebra_1_association':
        ('introductory-statistics', '12-2-scatter-plots'),
    'algebra_1_residuals':
        ('introductory-statistics', '12-3-the-regression-equation'),
    'algebra_1_the_substitution_method':
        ('elementary-algebra', '5-2-solve-systems-of-equations-by-substitution'),
    'algebra_1_the_elimination_method':
        ('elementary-algebra', '5-3-solve-systems-of-equations-by-elimination'),
    'algebra_1_overlapping_regions':
        ('elementary-algebra', '5-6-graphing-systems-of-linear-inequalities'),
    'algebra_1_the_function_definition':
        ('algebra-and-trigonometry', '3-1-functions-and-function-notation'),
    'algebra_1_domain':
        ('algebra-and-trigonometry', '3-2-domain-and-range'),
    'algebra_1_negative_exponents':
        ('elementary-algebra', '6-7-integer-exponents-and-scientific-notation'),
    'algebra_1_the_principal_square_root':
        ('elementary-algebra', '9-1-simplify-and-use-square-roots'),
    'algebra_1_fractional_exponents':
        ('elementary-algebra', '9-8-rational-exponents'),
    'algebra_1_the_exponential_growth_pattern':
        ('algebra-and-trigonometry', '6-1-exponential-functions'),
    'algebra_1_common_ratio':
        ('algebra-and-trigonometry', '13-3-geometric-sequences'),
    'algebra_1_multiplying_polynomials':
        ('elementary-algebra', '6-3-multiply-polynomials'),
    'algebra_1_the_greatest_common_factor':
        ('elementary-algebra', '7-1-greatest-common-factor-and-factor-by-grouping'),
    'algebra_1_leading_coefficient_one':
        ('elementary-algebra', '7-2-factor-quadratic-trinomials-with-leading-coefficient-1'),
    'algebra_1_vertex_and_axis_of_symmetry':
        ('algebra-and-trigonometry', '5-1-quadratic-functions'),
    'algebra_1_standard_form_of_a_parabola':
        ('elementary-algebra', '10-5-graphing-quadratic-equations'),
    'algebra_1_the_zero_product_property':
        ('elementary-algebra', '7-6-quadratic-equations'),
    'algebra_1_the_quadratic_formula':
        ('elementary-algebra', '10-3-solve-quadratic-equations-using-the-quadratic-formula'),
    'algebra_1_the_discriminant':
        ('elementary-algebra', '10-3-solve-quadratic-equations-using-the-quadratic-formula'),
}


def store_path(settings) -> Path:
    """Where fetched sections live. Data, not code: a licence withdrawal is a deletion."""
    return Path(settings.data_dir) / 'textbook' / 'sections.json'


def _client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    return httpx.Client(timeout=20.0, follow_redirects=True, trust_env=False,
                        transport=transport, headers={'User-Agent': USER_AGENT})


def _now() -> str:
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


# ------------------------------------------------------------------- licence gate

def book_policy(meta: Mapping[str, Any], *, book_slug: str = '') -> SourcePolicy:
    """The rights position for one book, derived from the publisher's own API data.

    Fail-close in three independent ways: an unrecognised licence string classifies as
    ``None`` and is refused; a book slug with no audited entry is refused; and, for an
    audited *ingestible* book, a live licence that contradicts the audit is refused -- the
    audit and the publisher must agree at fetch time, not just at review time. (A link-only
    audit is confirmed when the live licence classifies at all; the actual refusal for those
    books is :func:`app.ingest.policy.assert_ingestible`, whose reason says ``link-only``.)
    """
    slug = book_slug or str(meta.get('slug') or '')
    if slug in OPENSTAX_UNLICENSED:
        raise IngestionRefused(
            f'{slug!r}: OpenStax\'s catalogue reports no licence for this book, so there is '
            f'no rights position to rely on. An unknown licence is refused, not rounded to '
            f'the nearest permissive one; text storage stays refused until the publisher '
            f'declares one.')
    audited = AUDITED_BOOKS.get(slug)
    if audited is None:
        raise IngestionRefused(
            f'{slug!r} has no audited rights position in this project. OpenStax books differ '
            f'edition by edition (CC BY for some first editions, CC BY-NC-SA for current 2e '
            f'editions), so eligibility is per book and must be added as an evidence-backed '
            f'policy entry before anything is fetched.')
    licence_text = ' '.join(str(part) for part in (
        meta.get('license_name'), meta.get('license_version')) if part)
    klass = classify_licence(licence_text)
    if klass is None:
        raise IngestionRefused(
            f'{slug!r}: OpenStax\'s API reports {licence_text!r}, which does not classify as '
            f'any licence class this project has ruled on. An unknown licence is refused, not '
            f'treated as permissive.')
    if audited.ingestible and klass is not audited.licence_class:
        raise IngestionRefused(
            f'{slug!r}: OpenStax\'s API now reports {licence_text!r}, which classifies as '
            f'{klass.value}, not {audited.licence_class.value} as audited. The audited entry '
            f'and the publisher no longer agree, so text storage is refused until the audit '
            f'is re-reviewed.')
    return SourcePolicy(
        name=audited.name, url=audited.url, licence=f'{licence_text} ({meta.get("license_url")})',
        licence_class=klass, scope=audited.scope, attribution=audited.attribution,
        evidence_id=audited.evidence_id)


# ------------------------------------------------------------------- fetchers

def fetch_book_meta(slug: str, *, transport: httpx.BaseTransport | None = None) -> dict[str, Any]:
    """The publisher's own record for a book, including its licence fields."""
    with _client(transport) as client:
        listing = client.get(CMS_API, params={'type': 'books.Book', 'slug': slug, 'format': 'json'})
        listing.raise_for_status()
        items = listing.json().get('items') or []
        if not items:
            raise ValueError(f'OpenStax CMS has no book with slug {slug!r}')
        detail = client.get(CMS_API + f"{items[0]['id']}/")
        detail.raise_for_status()
        data = detail.json()
    return {'slug': data.get('meta', {}).get('slug', slug), 'title': data.get('title', ''),
            'book_uuid': data.get('book_uuid', ''), 'book_state': data.get('book_state', ''),
            'license_name': data.get('license_name', ''),
            'license_version': data.get('license_version', ''),
            'license_url': data.get('license_url', '')}


def fetch_toc(slug: str, *, transport: httpx.BaseTransport | None = None) -> list[dict[str, Any]]:
    """The book's section list, read from the server-rendered ``pages/index`` webview.

    The webview embeds the full table of contents as ``data-page-slug`` attributes on its
    navigation entries, so one request yields every real section slug. A slug from this list
    is a real section; a slug from anywhere else is a guess, and guesses become dead links
    presented as lesson material.
    """
    with _client(transport) as client:
        response = client.get(SECTION_URL.format(book_slug=slug, page_slug='index'))
        response.raise_for_status()
    seen: dict[str, str] = {}
    for slug_value, uuid in re.findall(
            r'data-page-slug="([^"]+)"[^>]*data-page-uuid="([^"]+)"', response.text):
        seen.setdefault(slug_value, uuid)
    return [{'page_slug': page_slug, 'page_uuid': uuid,
             'source_url': SECTION_URL.format(book_slug=slug, page_slug=page_slug)}
            for page_slug, uuid in sorted(seen.items())]


_TITLE_RE = re.compile(r'<title>(.*?)</title>', re.S)
_META_RE = {'author': re.compile(r'name="citation_author" content="([^"]*)"'),
            'date': re.compile(r'name="citation_date" content="([^"]*)"')}


def _section_title(html: str) -> str:
    """The ``<title>`` element is server-rendered as
    ``"<section> - <book> | OpenStax"``; the section part is what a citation names."""
    match = _TITLE_RE.search(html)
    raw = match.group(1) if match else ''
    return raw.split(' - ')[0].strip() if raw else ''


def _section_text(html: str) -> str:
    """The server-rendered prose, scripts and markup stripped.

    Sliced from ``main-content`` so site navigation, footers and cookie banners do not
    masquerade as textbook text. Whitespace is collapsed: the quote is for reading aloud,
    not for reproducing typography.
    """
    start = html.find('id="main-content"')
    if start >= 0:
        # Slice past the element's own opening tag so attribute text cannot leak into prose.
        body = html[html.find('>', start) + 1:]
    else:
        body = html
    body = re.sub(r'<script.*?</script>|<style.*?</style>|<nav.*?</nav>', '', body, flags=re.S)
    text = re.sub(r'<[^>]+>', ' ', body)
    return ' '.join(text.split())


def fetch_section(book_slug: str, page_slug: str, *,
                  transport: httpx.BaseTransport | None = None) -> dict[str, Any]:
    """One section from the publisher's webview, with its citation metadata and a sha256
    of the exact HTML served."""
    url = SECTION_URL.format(book_slug=book_slug, page_slug=page_slug)
    with _client(transport) as client:
        response = client.get(url)
        response.raise_for_status()
    html = response.text
    return {'book_slug': book_slug, 'page_slug': page_slug, 'source_url': url,
            'section_title': _section_title(html),
            'author': _META_RE['author'].search(html).group(1) if _META_RE['author'].search(html) else '',
            'published': _META_RE['date'].search(html).group(1) if _META_RE['date'].search(html) else '',
            'text': _section_text(html), 'html_sha256': hashlib.sha256(html.encode('utf-8')).hexdigest()}


# ------------------------------------------------------------------- store

def _blank(book_slug: str, page_slug: str) -> dict[str, Any]:
    return {'book_slug': book_slug, 'page_slug': page_slug,
            'fetched_at': _now(), 'status': 'unavailable'}


def load_sections(settings) -> dict[str, dict[str, Any]]:
    """The stored sections, keyed ``book_slug:page_slug``. Corrupt or absent store -> {}."""
    path = store_path(settings)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (ValueError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(settings, sections: Mapping[str, Mapping[str, Any]]) -> None:
    path = store_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(sections), indent=1, ensure_ascii=False) + '\n',
                    encoding='utf-8')


def ingest_section(settings, book_slug: str, page_slug: str, *,
                   transport: httpx.BaseTransport | None = None) -> dict[str, Any]:
    """Fetch one section, run the licence gate, and store the result.

    Returns the stored record. Three outcomes, each legible in the record's ``status``:

    * ``ready`` -- the licence gate cleared the book; the record carries the full text,
      an excerpt and complete provenance.
    * ``withheld`` -- the gate refused (NC licence, unaudited book, licence drift). The
      record carries the reason and **no text**; the section page itself is never even
      requested on the refusal paths that the gate decides from book metadata.
    * ``unavailable`` -- the network fetch failed. Nothing is invented to fill the gap.
    """
    sections = load_sections(settings)
    key = f'{book_slug}:{page_slug}'
    record: dict[str, Any] = dict(sections.get(key) or _blank(book_slug, page_slug))
    if book_slug in OPENSTAX_UNLICENSED:
        # Known-and-refused, decided entirely from the audited catalogue: the publisher
        # serves no licence fields for this book, so there is nothing the live API could
        # add and no reason to spend a request asking.
        record.update({'status': 'withheld', 'fetched_at': _now(),
                       'withheld_reason': (
                           f'{book_slug!r}: OpenStax\'s catalogue reports no licence for this '
                           f'book, so there is no rights position to rely on. An unknown '
                           f'licence is refused, not rounded to the nearest permissive one; '
                           f'text storage stays refused until the publisher declares one.'),
                       'source_url': SECTION_URL.format(book_slug=book_slug, page_slug=page_slug),
                       'book_title': '', 'section_title': '', 'page_slug': page_slug,
                       'licence': '', 'licence_class': 'refused'})
        record.pop('text', None)
        record.pop('excerpt', None)
        sections[key] = record
        _save(settings, sections)
        return record
    if book_slug not in AUDITED_BOOKS:
        # Audited before any request leaves the machine: an unaudited book is not a
        # permissive book, it is an unknown one, and it costs zero network calls to refuse.
        record.update({'status': 'withheld', 'fetched_at': _now(),
                       'withheld_reason': (
                           f'{book_slug!r} has no audited rights position in this project. '
                           f'OpenStax books differ edition by edition (CC BY for some first '
                           f'editions, CC BY-NC-SA for current 2e editions), so eligibility is '
                           f'per book and must be added as an evidence-backed policy entry '
                           f'before anything is fetched.'),
                       'source_url': SECTION_URL.format(book_slug=book_slug, page_slug=page_slug),
                       'page_slug': page_slug, 'licence': '', 'licence_class': 'refused'})
        record.pop('text', None)
        record.pop('excerpt', None)
        sections[key] = record
        _save(settings, sections)
        return record
    try:
        meta = fetch_book_meta(book_slug, transport=transport)
        policy = book_policy(meta, book_slug=book_slug)
        assert_ingestible(policy)
    except (IngestionRefused, AssetRefused) as exc:
        record.update({'status': 'withheld', 'fetched_at': _now(),
                       'withheld_reason': str(exc),
                       'source_url': SECTION_URL.format(book_slug=book_slug, page_slug=page_slug),
                       'book_title': '', 'section_title': '', 'page_slug': page_slug,
                       'licence': '', 'licence_class': 'refused'})
        record.pop('text', None)
        record.pop('excerpt', None)
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        record.update({'status': 'unavailable', 'fetched_at': _now(),
                       'unavailable_reason': f'{type(exc).__name__}: {exc}'})
    else:
        try:
            section = fetch_section(book_slug, page_slug, transport=transport)
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            # The section page itself failed. Same contract as the metadata path
            # above -- and the one this function's own docstring promises: a network
            # failure is recorded as ``unavailable``, never invented around, and
            # never allowed to escape as an exception. The fetch lives outside the
            # guarded block only because it must not run when the licence gate has
            # already refused, which is why it needs its own except clause.
            record.update({'status': 'unavailable', 'fetched_at': _now(),
                           'unavailable_reason': f'{type(exc).__name__}: {exc}'})
            sections[key] = record
            _save(settings, sections)
            return record
        record.update({
            'status': 'ready', 'fetched_at': _now(),
            'book_slug': book_slug, 'book_title': meta['title'], 'book_uuid': meta['book_uuid'],
            'page_slug': page_slug, 'section_title': section['section_title'],
            'source_url': section['source_url'], 'author': section['author'],
            'published': section['published'],
            'license_name': meta['license_name'], 'license_version': meta['license_version'],
            'license_url': meta['license_url'], 'licence': policy.licence,
            'licence_class': policy.licence_class.value, 'policy_name': policy.name,
            'html_sha256': section['html_sha256'],
            'text': section['text'],
            'excerpt': section['text'][:QUOTE_CHARS] + ('…' if len(section['text']) > QUOTE_CHARS else ''),
        })
    sections[key] = record
    _save(settings, sections)
    return record


# ------------------------------------------------------------------- lesson exposure

def _attribution_line(record: Mapping[str, Any]) -> str:
    book = record.get('book_title') or record.get('book_slug', '')
    author = record.get('author') or ''
    licence = ' '.join(part for part in (str(record.get('license_name') or ''),
                                         str(record.get('license_version') or '')) if part)
    who = f', {author}' if author else ''
    return f'OpenStax {book}{who}, {licence}'.strip()


def grounding(settings, concept_id: str) -> list[dict[str, Any]]:
    """The textbook grounding cards for one concept, in the lesson card shape.

    A ``ready`` card quotes the stored section and carries its citation; a ``withheld``
    card names the reason and carries no quote. This function never touches the network:
    it reads only what :func:`ingest_section` stored, so a lesson can never turn into a
    blocking fetch, and the licence evaluation happened once, at fetch time, under the
    same gate every other source passes.
    """
    mapping = SECTION_MAP.get(concept_id)
    if settings is None or mapping is None:
        return []
    book_slug, page_slug = mapping
    record = load_sections(settings).get(f'{book_slug}:{page_slug}')
    if not isinstance(record, Mapping):
        return []
    card: dict[str, Any] = {
        'kind': 'reading', 'media_kind': 'textbook_section',
        'title': f"{record.get('section_title') or page_slug} — OpenStax",
        'url': record.get('source_url', ''),
        'policy_name': record.get('policy_name', ''),
        'licence': record.get('licence', ''), 'licence_class': record.get('licence_class', ''),
        'attribution': _attribution_line(record),
        'source_url': record.get('source_url', ''),
        'fetched_at': record.get('fetched_at', ''),
    }
    if record.get('status') == 'ready' and record.get('excerpt'):
        card['status'] = 'ready'
        card['quote'] = record['excerpt']
        card['citation'] = {field: record.get(field, '') for field in
                            ('book_title', 'book_slug', 'page_slug', 'section_title',
                             'source_url', 'author', 'license_name', 'license_version',
                             'license_url', 'fetched_at', 'html_sha256')}
    else:
        card['status'] = 'withheld'
        card['quote'] = ''
        card['withheld_reason'] = str(record.get('withheld_reason')
                                      or record.get('unavailable_reason')
                                      or 'No licence-cleared section text is stored.')
    return [card]


def catalogue() -> dict[str, Any]:
    """The full publisher-reported catalogue with each book's audited rights position.

    Read-only and network-free: it is the bundled snapshot interpreted through the same
    fail-close classifier, not a fresh fetch, so the transparency surface can never become
    a blocking call -- and it can never claim a rights position the audit does not hold.
    """
    return openstax_catalogue_posture()


def describe(settings=None) -> dict[str, Any]:
    """The module's posture, for the transparency panel."""
    stored = 0
    ready = 0
    if settings is not None:
        for record in load_sections(settings).values():
            stored += 1
            ready += 1 if record.get('status') == 'ready' else 0
    return {
        'books_audited': sorted(AUDITED_BOOKS),
        'concepts_mapped': sorted(SECTION_MAP),
        'sections_stored': stored,
        'sections_ready': ready,
        'catalogue': openstax_catalogue_posture(),
        'guarantees': [
            'A book is text-eligible only when its slug has an audited policy entry AND the '
            'publisher\'s own API still reports the licence that entry was audited against.',
            'NC and unknown licences are stored as link-only records with the refusal reason '
            'and no text.',
            'Stored sections carry source URL, book slug/uuid, page slug, author, licence '
            'fields, retrieval timestamp and the served HTML\'s sha256.',
            'A stored quote is never sent to a model: it travels in a callout block the '
            'prose-rewriting pass does not read, and agent-loop tool results are '
            'redacted by generate.redact_textbook_quotes.',
        ],
    }
