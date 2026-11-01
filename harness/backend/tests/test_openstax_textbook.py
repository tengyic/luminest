"""The grounded OpenStax textbook layer.

These tests replay *real* saved responses from openstax.org (fixtures fetched live on
2026-10-11) through an httpx MockTransport, so the fetch path is exercised against the
publisher's actual response shapes without a network. The licence-gate tests encode the
rights position the audited policy entry declares: text storage for the CC BY 4.0 first
edition of Algebra and Trigonometry only, and a hard refusal -- with no section text
requested, fetched or stored -- for the CC BY-NC-SA 2e editions.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.ingest.policy import (IngestionRefused, LicenceClass, OPENSTAX_ALGEBRA_TRIG,
                               assert_ingestible, classify_licence, registry)
from app.ingest.sources import openstax

FIXTURES = Path(__file__).parent / 'fixtures' / 'openstax'

BOOK_ID = {'algebra-and-trigonometry': 38, 'algebra-and-trigonometry-2e': 553}
META_FILE = {'algebra-and-trigonometry': 'book_meta_algebra_and_trigonometry.json',
             'algebra-and-trigonometry-2e': 'book_meta_algebra_and_trigonometry_2e.json'}


@pytest.fixture
def settings(tmp_path):
    return SimpleNamespace(data_dir=str(tmp_path))


def _fixture_response(path: Path, content_type: str) -> httpx.Response:
    return httpx.Response(200, headers={'Content-Type': content_type},
                          content=path.read_bytes())


def openstax_transport(requested: list[str]) -> httpx.BaseTransport:
    """Serve the saved fixtures, and *record* every URL asked for so tests can assert that
    refused books never trigger a section-text request at all."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        requested.append(url)
        path = request.url.path
        params = request.url.params
        if path == '/apps/cms/api/v2/pages/' and params.get('type') == 'books.Book':
            slug = str(params.get('slug', ''))
            if slug in BOOK_ID:
                body = json.dumps({'meta': {'total_count': 1}, 'items': [
                    {'id': BOOK_ID[slug], 'meta': {'slug': slug}}]})
                return httpx.Response(200, json=json.loads(body))
            return httpx.Response(200, json={'meta': {'total_count': 0}, 'items': []})
        if path.startswith('/apps/cms/api/v2/pages/'):
            page_id = int(path.rstrip('/').rsplit('/', 1)[-1])
            slug = {v: k for k, v in BOOK_ID.items()}.get(page_id)
            if slug:
                return _fixture_response(FIXTURES / META_FILE[slug], 'application/json')
        if path.startswith('/books/algebra-and-trigonometry/pages/'):
            page = path.rsplit('/', 1)[-1]
            if page == 'index':
                return _fixture_response(
                    FIXTURES / 'toc_index_algebra_and_trigonometry.html', 'text/html')
            if page == '1-1-real-numbers-algebra-essentials':
                return _fixture_response(
                    FIXTURES / 'section_1-1-real-numbers-algebra-essentials.html', 'text/html')
        return httpx.Response(404, text='fixture transport: not mapped')

    return httpx.MockTransport(handler)


# ---------------------------------------------------------------- licence classification

@pytest.mark.parametrize('name,version,expected', [
    ('Creative Commons Attribution License', '4.0', LicenceClass.CC_BY),
    ('Creative Commons Attribution-NonCommercial-ShareAlike License', '4.0',
     LicenceClass.CC_BY_NC_SA),
    ('Open Publication License', '1.0', None),
])
def test_openstax_licence_strings_classify_fail_closed(name, version, expected):
    """The exact licence strings the OpenStax API emits must classify correctly, and an
    unfamiliar string must classify as None (refused), never as permissive."""
    assert classify_licence(f'{name} {version}') is expected


def test_audited_policy_is_cc_by_and_registered():
    assert OPENSTAX_ALGEBRA_TRIG.licence_class is LicenceClass.CC_BY
    assert OPENSTAX_ALGEBRA_TRIG.ingestible
    assert OPENSTAX_ALGEBRA_TRIG.evidence_id == 'openstax_algebra_trig_1e_cc_by'
    entries = {entry['name']: entry for entry in registry()}
    assert 'OpenStax Algebra and Trigonometry (1e)' in entries
    assert entries['OpenStax Algebra and Trigonometry (1e)']['ingestible'] is True


# ------------------------------------------------------------------- book policy gate

def test_book_policy_from_live_api_meta_cc_by():
    meta = json.loads((FIXTURES / 'book_meta_algebra_and_trigonometry.json').read_text())
    policy = openstax.book_policy(meta, book_slug='algebra-and-trigonometry')
    assert policy.licence_class is LicenceClass.CC_BY
    assert policy.evidence_id == OPENSTAX_ALGEBRA_TRIG.evidence_id


def test_book_policy_for_nc_2e_is_link_only_and_refused_at_gate():
    """The current 2e edition is CC BY-NC-SA per OpenStax's own API. The classification
    succeeds, but the ingestible gate refuses it: link-only, exactly as audited."""
    meta = json.loads(
        (FIXTURES / 'book_meta_algebra_and_trigonometry_2e.json').read_text())
    policy = openstax.book_policy(meta, book_slug='algebra-and-trigonometry-2e')
    assert policy.licence_class is LicenceClass.CC_BY_NC_SA
    with pytest.raises(IngestionRefused, match='link-only'):
        assert_ingestible(policy)


def test_book_policy_refuses_unaudited_slug():
    meta = {'slug': 'college-physics-2e', 'license_name': 'Creative Commons Attribution License',
            'license_version': '4.0'}
    with pytest.raises(IngestionRefused, match='no audited rights position'):
        openstax.book_policy(meta, book_slug='college-physics-2e')


def test_book_policy_refuses_licence_drift():
    """If OpenStax flips the 1e to NC, the audit and the publisher disagree and the gate
    fails closed even though the slug is audited."""
    meta = {'slug': 'algebra-and-trigonometry',
            'license_name': 'Creative Commons Attribution-NonCommercial-ShareAlike License',
            'license_version': '4.0'}
    with pytest.raises(IngestionRefused, match='no longer agree'):
        openstax.book_policy(meta, book_slug='algebra-and-trigonometry')


# ------------------------------------------------------------------------- fetch + store

def test_toc_comes_from_real_index_fixture():
    toc = openstax.fetch_toc('algebra-and-trigonometry',
                             transport=openstax_transport([]))
    slugs = [entry['page_slug'] for entry in toc]
    assert '1-1-real-numbers-algebra-essentials' in slugs
    assert '4-1-linear-functions' in slugs
    assert all(entry['source_url'].startswith('https://openstax.org/books/') for entry in toc)


def test_section_fetch_extracts_real_text_and_provenance():
    section = openstax.fetch_section(
        'algebra-and-trigonometry', '1-1-real-numbers-algebra-essentials',
        transport=openstax_transport([]))
    assert section['section_title'] == '1.1 Real Numbers: Algebra Essentials'
    assert section['author'] == 'Jay Abramson'
    # Real prose from the served page, not fixture-baked: the extractor must have produced it.
    assert 'mathematics is the language of science' in section['text']
    assert len(section['text']) > 10_000
    assert section['source_url'] == ('https://openstax.org/books/algebra-and-trigonometry/'
                                     'pages/1-1-real-numbers-algebra-essentials')
    assert len(section['html_sha256']) == 64


def test_ingest_stores_text_with_full_provenance_for_cc_by_book(settings):
    record = openstax.ingest_section(
        settings, 'algebra-and-trigonometry', '1-1-real-numbers-algebra-essentials',
        transport=openstax_transport([]))
    assert record['status'] == 'ready'
    for field in ('source_url', 'book_slug', 'book_uuid', 'book_title', 'page_slug',
                  'section_title', 'author', 'license_name', 'license_version',
                  'license_url', 'licence_class', 'fetched_at', 'html_sha256'):
        assert record.get(field), f'missing provenance field {field}'
    assert record['license_name'] == 'Creative Commons Attribution License'
    assert record['licence_class'] == 'cc_by'
    assert 'mathematics is the language of science' in record['text']
    assert record['excerpt'].endswith('…') or len(record['text']) <= openstax.QUOTE_CHARS
    # The store persists, and grounding reads from it without touching the network.
    stored = openstax.load_sections(settings)
    assert stored['algebra-and-trigonometry:1-1-real-numbers-algebra-essentials']['status'] == 'ready'


def test_ingest_refuses_nc_book_and_never_requests_section_text(settings):
    requested: list[str] = []
    record = openstax.ingest_section(
        settings, 'algebra-and-trigonometry-2e', '1-1-real-numbers-algebra-essentials',
        transport=openstax_transport(requested))
    assert record['status'] == 'withheld'
    assert 'NonCommercial' in record['withheld_reason'] or 'non-commercial' in \
        record['withheld_reason'].lower() or 'cc_by_nc_sa' in record['withheld_reason']
    assert 'text' not in record and 'excerpt' not in record
    # The refusal is decided from book metadata alone: no section page was ever requested,
    # so no NC text could have been seen even transiently.
    assert not any('/pages/1-1-' in url for url in requested)


def test_ingest_refuses_unaudited_book(settings):
    record = openstax.ingest_section(settings, 'college-physics-2e', '1-introduction',
                                     transport=openstax_transport([]))
    assert record['status'] == 'withheld'
    assert 'no audited rights position' in record['withheld_reason']
    assert 'text' not in record


def test_ingest_unavailable_on_network_failure(settings):
    def failing(url: httpx.URL) -> httpx.Response:
        raise httpx.ConnectError('offline')

    record = openstax.ingest_section(
        settings, 'algebra-and-trigonometry', '1-1-real-numbers-algebra-essentials',
        transport=httpx.MockTransport(failing))
    assert record['status'] == 'unavailable'
    assert 'ConnectError' in record['unavailable_reason']
    assert 'text' not in record


# -------------------------------------------------------------------- lesson grounding

def _seed_ready(settings):
    openstax.ingest_section(settings, 'algebra-and-trigonometry',
                            '1-1-real-numbers-algebra-essentials',
                            transport=openstax_transport([]))


def test_grounding_ready_card_carries_quote_and_citation(settings):
    _seed_ready(settings)
    # Grounding for a mapped concept reads the record stored under the mapped page slug;
    # copy the ready record onto the mapped key so the real route is exercised.
    record = openstax.load_sections(settings)[
        'algebra-and-trigonometry:1-1-real-numbers-algebra-essentials']
    store = openstax.load_sections(settings)
    store['algebra-and-trigonometry:4-1-linear-functions'] = record
    openstax._save(settings, store)

    cards = openstax.grounding(settings, 'linear_functions')
    assert len(cards) == 1
    card = cards[0]
    assert card['status'] == 'ready'
    assert card['quote'] and 'mathematics is the language of science' in card['quote']
    citation = card['citation']
    assert citation['source_url'].startswith('https://openstax.org/books/')
    assert citation['license_name'] == 'Creative Commons Attribution License'
    assert citation['fetched_at'].endswith('Z')
    assert card['attribution'].startswith('OpenStax Algebra and Trigonometry')


def test_grounding_withholds_without_inventing_text(settings):
    record = openstax.ingest_section(settings, 'algebra-and-trigonometry-2e',
                                     '1-1-real-numbers-algebra-essentials',
                                     transport=openstax_transport([]))
    assert record['status'] == 'withheld'
    # Grounding reads the store only; map the concept to the withheld record to assert the
    # card shape a lesson would receive.
    store = openstax.load_sections(settings)
    store['algebra-and-trigonometry:4-1-linear-functions'] = record
    openstax._save(settings, store)
    cards = openstax.grounding(settings, 'linear_functions')
    assert cards[0]['status'] == 'withheld'
    assert cards[0]['quote'] == ''
    assert cards[0]['withheld_reason']


def test_grounding_returns_empty_for_unmapped_concept_or_empty_store(settings):
    assert openstax.grounding(settings, 'linear_functions') == []
    assert openstax.grounding(settings, 'fractions') == []
    assert openstax.grounding(None, 'linear_functions') == []


def test_describe_reports_store_state(settings):
    _seed_ready(settings)
    posture = openstax.describe(settings)
    assert posture['sections_stored'] == 1
    assert posture['sections_ready'] == 1
    assert 'algebra-and-trigonometry' in posture['books_audited']


# ------------------------------------------------------------- model-facing redaction

#: A distinctive substring of the *real* stored fixture excerpt, so assertions are exact.
QUOTE_MARKER = 'mathematics is the language of science'


def _store_ready_on_mapped_key(settings):
    _seed_ready(settings)
    record = openstax.load_sections(settings)[
        'algebra-and-trigonometry:1-1-real-numbers-algebra-essentials']
    store = openstax.load_sections(settings)
    store['algebra-and-trigonometry:4-1-linear-functions'] = record
    openstax._save(settings, store)


def test_tool_result_redacts_verbatim_quote_but_lesson_keeps_it(settings):
    """The redaction invariant, on both surfaces.

    The lesson artefact keeps the verbatim quote (licence-cleared, cited) for the rendered
    lesson. The ``compose_content`` tool result -- which the agent loop serialises into a
    ``role:'tool'`` message the model reads -- must carry the citation and a withholding
    notice, never the verbatim OpenStax text.
    """
    from app.harness import generate, toolbox
    _store_ready_on_mapped_key(settings)
    ctx = toolbox.ToolContext(settings=settings)

    artifact = generate.compose(ctx, 'linear_functions', 'explanation')
    local = json.dumps(artifact.to_dict(), default=str)
    assert QUOTE_MARKER in local, 'the rendered lesson must keep the verbatim quote'

    result = toolbox.compose_content(ctx, 'linear_functions', 'explanation')
    assert result.ok
    wire = json.dumps(result.to_dict(), default=str)
    assert QUOTE_MARKER not in wire, 'tool result must not carry the verbatim quote'
    assert 'withheld from model context' in wire, 'the withholding notice must travel instead'
    assert 'openstax.org/books/algebra-and-trigonometry/pages/' in wire, \
        'the citation must still be available to the agent'

    # Through the exact serialization the agent loop puts on the wire.
    from app.harness.agent_loop import _tool_message
    assert QUOTE_MARKER not in _tool_message(result)


def test_redaction_is_lossless_outside_marked_blocks():
    """Only blocks marked model_facing=REDACT_TEXTBOOK are redacted; everything else,
    including ordinary callouts, survives byte-for-byte, and the input is not mutated."""
    from app.harness import generate
    data = {'blocks': [{'type': 'callout', 'model_facing': generate.REDACT_TEXTBOOK,
                        'title': 'From the textbook: Linear Functions',
                        'text': 'verbatim quote'},
                       {'type': 'paragraph', 'text': 'keep me'},
                       {'type': 'callout', 'text': 'ordinary callout stays'}],
            'nested': [{'deeper': {'blocks': [{'model_facing': generate.REDACT_TEXTBOOK,
                                               'title': 't', 'text': 'deep quote'}]}}]}
    out = generate.redact_textbook_quotes(data)
    assert out['blocks'][0]['text'] == generate.TEXTBOOK_REDACTED_TEXT
    assert 'model_facing' not in out['blocks'][0]
    assert out['blocks'][0]['title'] == 'From the textbook: Linear Functions'
    assert out['blocks'][1] == {'type': 'paragraph', 'text': 'keep me'}
    assert out['blocks'][2] == {'type': 'callout', 'text': 'ordinary callout stays'}
    deep = out['nested'][0]['deeper']['blocks'][0]
    assert deep['text'] == generate.TEXTBOOK_REDACTED_TEXT and deep['title'] == 't'
    assert data['blocks'][0]['text'] == 'verbatim quote'  # input untouched
