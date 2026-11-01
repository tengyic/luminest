"""Tests for the image *fetch* capability: the acquisition path, its refusals, and its scope.

The defect these lock down is the one a learner reported: the lesson and the deck showed no
real photographs, because nothing in the product ever triggered a search-and-download. The
acquisition pipeline existed and worked, but no user-facing action called it, and the route
that listed images returned only what was already cached - always empty.

Two things are asserted here that a passing "happy path" would not catch. First, a fetch
that cannot reach the network returns a *structured refusal*, never an exception: the module
promises that an offline instance is a reported state. Second, the library is scoped to the
account that fetched the image, because "the images this instance holds" and "the images this
learner asked for" are different lists and only the second is safe to show.

No test makes a real network call: the transport is stubbed at ``media._client`` (and, where
the point is the download rather than the search, at ``media._download_bytes``).
"""

from __future__ import annotations

import base64
from dataclasses import replace

import httpx
import pytest

from app.harness import media
from test_api import account, client, settings  # noqa: F401 - fixtures and helper

#: A real 1x1 PNG. The bytes matter: the cache sniffs the magic number before it will store
#: anything, so a placeholder string would be refused for the wrong reason.
PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')


@pytest.fixture
def media_settings(settings):  # noqa: F811 - depends on the imported fixture
    """The default test settings, with outbound media explicitly permitted."""
    return replace(settings, media_enabled=True)


def _no_network(*args, **kwargs):
    raise httpx.ConnectError('the network is unavailable')


class _FakeResponse:
    def __init__(self, payload, status=200):
        self._payload, self.status_code, self.headers = payload, status, {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError('boom', request=None, response=None)

    def json(self):
        return self._payload


class _FakeClient:
    """A stand-in for ``httpx.Client`` that answers one canned payload."""

    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, *args, **kwargs):
        return _FakeResponse(self._payload)

    def post(self, *args, **kwargs):
        return _FakeResponse({'access_token': 'token'})

    def stream(self, *args, **kwargs):
        raise AssertionError('a search must not download anything')


def _cleared_candidate(**over):
    base = dict(source='wikimedia', source_id='1', title='Cell division',
                creator='A Photographer', licence_code='CC BY 4.0', licence_class='cc_by',
                licence_url='https://creativecommons.org/licenses/by/4.0/',
                attribution_text='"Cell division" by A Photographer — CC BY 4.0',
                landing_page_url='https://commons.example/File:Cell.png',
                file_url='https://example.invalid/cell.png', width=1200, height=800,
                mime='image/png', tags=['cell', 'division'])
    base.update(over)
    return media.Candidate(**base)


def _stub_search(monkeypatch, candidates):
    monkeypatch.setattr(media, 'search', lambda *a, **k: {
        'query': 'cell division', 'candidates': list(candidates),
        'providers': [], 'notes': []})


def _stub_download(monkeypatch):
    monkeypatch.setattr(media, '_download_bytes', lambda *a, **k: (PNG, 'image/png'))


# ----------------------------------------------------------- the offline promise

def test_fetch_reports_a_refusal_when_the_network_is_unavailable(monkeypatch, media_settings):
    """A fetch that cannot reach the network is a result, not an exception."""
    monkeypatch.setattr(media, '_client', _no_network)
    result = media.fetch(media_settings, 'photosynthesis in a leaf')
    assert result['assets'] == []
    assert result['asset'] is None
    assert result['cached'] is False
    assert result['outcome'] in {'no_cleared_candidate', 'unavailable'}
    # The provider report is what makes the refusal checkable: it names the transport as the
    # reason rather than implying the search simply found nothing.
    assert any('unavailable' in str(row.get('status', '')) for row in result['providers'])


def test_fetch_never_raises_even_when_the_transport_raises_something_unexpected(
        monkeypatch, media_settings):
    """The module's docstring promises nothing raises; hold it to that for a non-HTTP error."""
    monkeypatch.setattr(media, '_client', lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError('transport exploded')))
    result = media.fetch(media_settings, 'cell division')
    assert result['outcome'] == 'unavailable'
    assert result['assets'] == []
    assert result['notes'], 'a refusal with no reason is a black box'


def test_fetch_downloads_nothing_when_media_is_disabled(settings, monkeypatch):
    """A disabled instance refuses before the network is touched at all."""
    offline = replace(settings, media_enabled=False)

    def _forbidden(*args, **kwargs):
        raise AssertionError('a disabled instance reached for the network')

    monkeypatch.setattr(media, '_client', _forbidden)
    monkeypatch.setattr(media, '_download_bytes', _forbidden)
    result = media.fetch(offline, 'cell division')
    assert result['outcome'] == 'network_disabled'
    assert result['assets'] == []


# ----------------------------------------------------------- the licence gate

def test_an_unknown_licence_is_dropped_and_the_reason_is_present(monkeypatch, media_settings):
    """An unclassified code must drop the candidate *before* anything is downloaded."""
    _stub_search(monkeypatch, [_cleared_candidate(licence_code='Bespoke-Open-2.0',
                                                  licence_class='')])
    downloads = []
    monkeypatch.setattr(media, '_download_bytes',
                        lambda *a, **k: downloads.append(a) or (b'', ''))
    result = media.fetch(media_settings, 'cell division')
    assert result['outcome'] == 'no_cleared_candidate'
    assert result['assets'] == []
    assert not downloads, 'an uncleared licence was downloaded'
    assert any('not a code this project has classified' in row['why']
               for row in result['rejections'])


def test_a_non_commercial_licence_is_dropped_with_its_reason(monkeypatch, media_settings):
    _stub_search(monkeypatch, [_cleared_candidate(licence_code='CC BY-NC 4.0',
                                                  licence_class='cc_by_nc')])
    result = media.fetch(media_settings, 'cell division')
    assert result['assets'] == []
    assert any('may not cache a copy' in row['why'] for row in result['rejections'])


def test_normalise_mime_is_applied_at_the_provider_boundary(monkeypatch, media_settings):
    """A provider answering a bare extension must not be rejected on the MIME branch.

    This is the regression the module already fixed; it is re-asserted here from the fetch
    side so the fix cannot be undone by a later change to the fetch path.
    """
    payload = {'results': [{
        'id': '1', 'title': 'Cell division', 'creator': 'A', 'license': 'cc0',
        'license_version': '1.0', 'filetype': 'jpg', 'url': 'https://example.invalid/a.jpg',
        'width': 1200, 'height': 800, 'tags': []}]}
    monkeypatch.setattr(media, '_client', lambda *a, **k: _FakeClient(payload))
    hits = media._search_openverse(media_settings, 'cell division', 5)
    assert hits and hits[0].mime == 'image/jpeg', hits[0].mime if hits else 'no hits'
    accepted, rejected = media.filter_candidates(hits, 'cell division')
    assert accepted and not rejected, [c.rejected for c in rejected]


def test_fetch_caches_a_cleared_image_and_carries_its_attribution(monkeypatch, media_settings):
    _stub_search(monkeypatch, [_cleared_candidate()])
    _stub_download(monkeypatch)
    result = media.fetch(media_settings, 'cell division')
    assert result['outcome'] == 'downloaded'
    asset = result['asset']
    for key in ('sha256', 'attribution_text', 'licence_class', 'licence_url',
                'landing_page_url', 'width', 'height'):
        assert asset.get(key) not in (None, ''), key
    assert asset['licence_class'] == 'cc_by'
    assert asset['attribution_text'].startswith('"Cell division"')


# ----------------------------------------------------------- the fetch route

def test_fetch_route_requires_a_token_and_accepts_one(client, monkeypatch):  # noqa: F811
    monkeypatch.setattr(media, '_client', _no_network)
    assert client.post('/api/v1/images/fetch',
                       json={'query': 'cell division'}).status_code == 401
    headers, _ = account(client, 'image-fetch')
    response = client.post('/api/v1/images/fetch', headers=headers,
                           json={'query': 'cell division'})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['outcome'] in {'no_cleared_candidate', 'unavailable'}
    assert 'rejections' in body and 'providers' in body


def test_fetch_route_rejects_an_empty_query(client):  # noqa: F811
    headers, _ = account(client, 'image-empty')
    assert client.post('/api/v1/images/fetch', headers=headers,
                       json={'query': ''}).status_code == 422


# ----------------------------------------------------------- account-scoped library

def test_library_returns_only_the_calling_accounts_images(client, monkeypatch):  # noqa: F811
    one, _ = account(client, 'image-one')
    two, _ = account(client, 'image-two')
    _stub_search(monkeypatch, [_cleared_candidate()])
    _stub_download(monkeypatch)

    fetched = client.post('/api/v1/images/fetch', headers=one, json={'query': 'cell division'})
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()['assets'], fetched.json()

    mine = client.get('/api/v1/images/library', headers=one).json()
    theirs = client.get('/api/v1/images/library', headers=two).json()
    assert mine['total'] == 1, mine
    assert theirs['total'] == 0, theirs
    row = mine['assets'][0]
    # The library is a picker, so attribution has to travel with the row or the picker is
    # inviting an unattributed reuse.
    for key in ('sha256', 'attribution_text', 'licence_code', 'licence_url', 'landing_page_url'):
        assert key in row, key
    assert row['attribution_text']


def test_library_can_be_filtered_by_query(client, monkeypatch):  # noqa: F811
    headers, _ = account(client, 'image-filter')
    _stub_search(monkeypatch, [_cleared_candidate()])
    _stub_download(monkeypatch)
    client.post('/api/v1/images/fetch', headers=headers, json={'query': 'cell division'})
    assert client.get('/api/v1/images/library', headers=headers,
                      params={'q': 'cell'}).json()['total'] == 1
    assert client.get('/api/v1/images/library', headers=headers,
                      params={'q': 'nebula'}).json()['total'] == 0


def test_library_requires_a_token(client):  # noqa: F811
    assert client.get('/api/v1/images/library').status_code == 401


# ----------------------------------------------------------- attribution + delete

def test_attribution_route_returns_the_credit_and_404s_an_unknown_sha(client, monkeypatch):  # noqa: F811
    headers, _ = account(client, 'image-credit')
    _stub_search(monkeypatch, [_cleared_candidate()])
    _stub_download(monkeypatch)
    fetched = client.post('/api/v1/images/fetch', headers=headers, json={'query': 'cell division'})
    sha = fetched.json()['assets'][0]['sha256']
    credit = client.get(f'/api/v1/images/{sha}/attribution', headers=headers)
    assert credit.status_code == 200, credit.text
    assert credit.json()['credit'].startswith('"Cell division"')
    assert client.get(f"/api/v1/images/{'a' * 64}/attribution",
                      headers=headers).status_code == 404


def test_delete_removes_an_image_from_the_library(client, monkeypatch):  # noqa: F811
    headers, _ = account(client, 'image-delete')
    _stub_search(monkeypatch, [_cleared_candidate()])
    _stub_download(monkeypatch)
    fetched = client.post('/api/v1/images/fetch', headers=headers, json={'query': 'cell division'})
    sha = fetched.json()['assets'][0]['sha256']

    assert client.delete(f'/api/v1/images/{sha}', headers=headers).status_code == 200
    assert client.get('/api/v1/images/library', headers=headers).json()['total'] == 0
    assert client.get(f'/api/v1/images/{sha}/attribution', headers=headers).status_code == 404
    # Deleting something this account never had is a 404, not a silent success.
    assert client.delete(f"/api/v1/images/{'b' * 64}", headers=headers).status_code == 404


# ----------------------------------------------------------- lesson batch + block attachment

def test_for_lesson_attaches_a_photograph_block_to_the_lesson(client, monkeypatch):  # noqa: F811
    """The end-to-end path the learner complained about: fetch, then a real image in the lesson."""
    headers, _ = account(client, 'image-lesson')
    _stub_search(monkeypatch, [_cleared_candidate()])
    _stub_download(monkeypatch)

    batch = client.post('/api/v1/images/for-lesson', headers=headers,
                        json={'concept_id': 'fractions'})
    assert batch.status_code == 200, batch.text
    assert batch.json()['assigned'] >= 1, batch.json()
    assert batch.json()['blocks'], 'no photograph block was assigned to a lesson position'

    lesson = client.get('/api/v1/lessons/fractions', headers=headers)
    assert lesson.status_code == 200, lesson.text
    photographs = [b for b in lesson.json()['blocks'] if b.get('kind') == 'photograph']
    assert photographs, 'the lesson carried no photograph block after a fetch'
    block = photographs[0]
    for key in ('src', 'sha256', 'credit', 'licence', 'alt'):
        assert block.get(key), key
    assert block['src'].startswith('/api/v1/media/images/')


def test_a_lesson_with_no_fetch_gains_no_photograph_block(client):  # noqa: F811
    """The change is additive: an untouched lesson is exactly what it always was."""
    headers, _ = account(client, 'image-none')
    lesson = client.get('/api/v1/lessons/fractions', headers=headers)
    assert lesson.status_code == 200, lesson.text
    assert not [b for b in lesson.json()['blocks'] if b.get('kind') == 'photograph']


def test_for_lesson_rejects_an_unknown_concept_and_needs_a_token(client):  # noqa: F811
    assert client.post('/api/v1/images/for-lesson',
                       json={'concept_id': 'fractions'}).status_code == 401
    headers, _ = account(client, 'image-unknown')
    assert client.post('/api/v1/images/for-lesson', headers=headers,
                       json={'concept_id': 'not-a-real-concept'}).status_code == 404


def test_lesson_image_needs_is_capped_and_skips_thin_blocks():
    blocks = [{'kind': 'concept', 'title': f'Block {i}', 'body': 'word ' * 20}
              for i in range(10)]
    blocks.append({'kind': 'retrieval', 'title': 'Recall', 'body': 'short'})
    needs = media.lesson_image_needs(title='Mitosis', summary='stages of cell division',
                                     blocks=blocks)
    assert len(needs) == media.MAX_LESSON_IMAGES
    assert all(need['query'] for need in needs)


# ------------------------------------- the ranking is the judgement, so respect it

def test_a_concept_query_is_the_title_because_a_phrase_returns_nothing():
    """The measured reason this is not "title plus the summary's first clause".

    ``"Cytoplasm The aqueous interior of the cell where most metabolic reactions take
    place"`` returns **zero** candidates from the live providers; ``"Cytoplasm"`` returns
    forty-one. Appending the clause did not make the search more precise, it made it empty,
    and the empty result was then reported as "no photograph exists for this concept".
    """
    assert media._concept_query('Cytoplasm',
                                'The aqueous interior of the cell where most metabolic '
                                'reactions take place.') == 'Cytoplasm'
    assert media._concept_query('  Cell   membrane ', 'anything') == 'Cell membrane'
    assert media._concept_query('', 'anything') == ''


def test_support_ranks_candidates_without_rejecting_any():
    """The summary orders the list; it is not a requirement a curated asset can fail.

    The two candidates differ in area on purpose, so the two orderings cannot agree by
    accident: without support the bigger file wins, with support the one that mentions the
    summary wins. Both are still accepted - ranking must never become a second gate.
    """
    plain = _cleared_candidate(source_id='plain', title='Osmosis power station',
                               description='a pressure-retarded osmosis plant', tags=[],
                               width=1600, height=1200)
    biology = _cleared_candidate(source_id='bio', title='Osmosis in a red blood cell',
                                 description='water crosses the membrane of a cell',
                                 tags=['osmosis', 'cell'], width=1200, height=800)
    accepted, rejected = media.filter_candidates([plain, biology], 'Osmosis',
                                                 support='water moves across a cell membrane')
    assert not rejected, [c.rejected for c in rejected]
    assert [c.source_id for c in accepted] == ['bio', 'plain'], 'support did not reorder'
    # With no support the ordering is the old one: pixel area first.
    by_area, _ = media.filter_candidates([plain, biology], 'Osmosis')
    assert by_area[0].source_id == 'plain'


def test_the_fetch_stops_at_the_attempt_cap_instead_of_taking_a_lower_ranked_image(
        monkeypatch, media_settings):
    """The regression behind a concert photograph becoming a biology figure.

    Every download fails, so the old loop walked the whole ranked list and attached
    whatever finally answered - in the observed case, the ninth candidate, a photograph of
    a band called "The Cell Theory". Walking past the ranking means shipping something the
    ranking did not choose, so the fetch stops and says so.
    """
    candidates = [_cleared_candidate(source_id=str(i), title=f'Candidate {i}')
                  for i in range(8)]
    _stub_search(monkeypatch, candidates)
    attempts = []

    def _fail(*args, **kwargs):
        attempts.append(1)
        raise httpx.ConnectError('host is down')

    monkeypatch.setattr(media, '_download_bytes', _fail)
    result = media.fetch(media_settings, 'cell division')
    assert result['assets'] == []
    assert result['asset'] is None
    assert result['outcome'] == 'all_downloads_failed'
    assert result['stop'] == 'attempt_cap'
    assert len(attempts) == media.MAX_DOWNLOAD_ATTEMPTS
    assert len(result['skipped']) == media.MAX_DOWNLOAD_ATTEMPTS
    assert any('better-ranked' in note for note in result['notes'])


def test_a_rate_limited_host_stops_the_fetch_immediately(monkeypatch, media_settings):
    """A 429 is about the instance, not the file: nine more attempts are rude and futile."""
    _stub_search(monkeypatch, [_cleared_candidate(source_id=str(i)) for i in range(6)])
    attempts = []

    def _throttled(*args, **kwargs):
        attempts.append(1)
        request = httpx.Request('GET', 'https://example.invalid/a.png')
        response = httpx.Response(429, request=request)
        raise httpx.HTTPStatusError('429 Too many requests', request=request,
                                    response=response)

    monkeypatch.setattr(media, '_download_bytes', _throttled)
    result = media.fetch(media_settings, 'cell division')
    assert result['outcome'] == 'rate_limited'
    assert result['stop'] == 'rate_limited'
    assert len(attempts) == 1, 'the host was asked again after saying stop'
    assert any('rate-limited' in note for note in result['notes'])


def test_a_successful_fetch_reports_the_candidates_it_skipped(monkeypatch, media_settings):
    """"We took the second choice" is a fact the caller needs, not a detail to hide."""
    first = _cleared_candidate(source_id='first', title='Dead link')
    second = _cleared_candidate(source_id='second', title='Working image')
    _stub_search(monkeypatch, [first, second])
    calls = []

    def _one_fails(settings, url):
        calls.append(url)
        if len(calls) == 1:
            raise httpx.ConnectError('host is down')
        return PNG, 'image/png'

    monkeypatch.setattr(media, '_download_bytes', _one_fails)
    result = media.fetch(media_settings, 'cell division')
    assert result['asset']['title'] == 'Working image'
    assert result['stop'] == ''
    assert [row['title'] for row in result['skipped']] == ['Dead link']


# ------------------------------------------------- the agent identity providers require

def test_the_user_agent_carries_a_contact_route(media_settings):
    """Wikimedia refuses a User-Agent with no contact with a 403 that looks like "no results".

    Measured against the live API on 2026-10-26: the identifier line alone returns 403, and
    the same line plus a contact returns 200. That single header decided whether the largest
    cacheable photograph collection in the world was reachable at all, and nothing in the
    product said so.
    """
    without = media.user_agent(replace(media_settings, media_contact=''))
    assert media.DEFAULT_MEDIA_CONTACT in without
    assert media.contact_configured(replace(media_settings, media_contact='')) is False

    with_contact = media.user_agent(replace(media_settings, media_contact='ops@school.example'))
    assert 'ops@school.example' in with_contact
    assert media.DEFAULT_MEDIA_CONTACT not in with_contact
    # A dotted domain is what the policy check looks for; "operator@localhost" is refused.
    assert '.' in with_contact.split('@')[-1].split(')')[0]

    url_form = media.user_agent(replace(media_settings, media_contact='https://school.example'))
    assert 'https://school.example' in url_form

    named = media.user_agent(replace(media_settings, media_contact='the ops team'))
    assert '(the ops team)' in named


def test_the_client_sends_the_configured_contact(monkeypatch, media_settings):
    """The UA has to reach the wire, not only the helper's return value."""
    seen = {}

    class _Recorder:
        def __init__(self, *args, **kwargs):
            seen.update(kwargs.get('headers') or {})

        def get(self, *args, **kwargs):
            return _FakeResponse({'query': {'pages': {}}})

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    import httpx as _httpx
    monkeypatch.setattr(_httpx, 'Client', _Recorder)
    configured = replace(media_settings, media_contact='ops@school.example')
    media._search_wikimedia(configured, 'elasticity', 5)
    assert 'ops@school.example' in seen.get('User-Agent', '')


def test_an_agent_policy_refusal_is_named_rather_than_reported_as_a_transport_fault(
        monkeypatch, media_settings):
    """A 403 is the provider answering. Reporting it as "unavailable" sends a reviewer to
    look for a network fault that does not exist, and the search notes then have to say so."""
    class _Refusing:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, *args, **kwargs):
            response = httpx.Response(403, request=httpx.Request('GET', 'https://example.invalid'))
            raise httpx.HTTPStatusError('403', request=response.request, response=response)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    import httpx as _httpx
    monkeypatch.setattr(_httpx, 'Client', _Refusing)
    result = media.search(media_settings, 'price elasticity of demand')
    statuses = {row['provider']: row['status'] for row in result['providers']}
    assert statuses['wikimedia'] == 'refused_agent_policy'
    assert any('agent policy' in note for note in result['notes'])


def test_an_unset_contact_is_reported_rather_than_hidden(monkeypatch, media_settings):
    # Stubbed transport: the note is built whether or not a provider answered, and a test
    # must not depend on the live network to find that out.
    monkeypatch.setattr(media, '_client', _no_network)
    result = media.search(replace(media_settings, media_contact=''), 'elasticity')
    assert any('HARNESS_MEDIA_CONTACT' in note for note in result['notes'])


def test_a_block_slot_searches_the_concept_title_not_a_ten_word_phrase(media_settings):
    """Appending the block's aspect words to the query lowers recall to zero on the live
    APIs, because they AND their terms. The aspect belongs in ``support``, which ranks."""
    needs = media.lesson_image_needs(
        title='Least-cost combination of inputs', summary='Isoquants and input prices.',
        blocks=[{'kind': 'concept', 'title': 'Core idea',
                 'body': 'The firm chooses the input mix that minimises cost for a given '
                         'output, which happens where the isoquant is tangent to the isocost.'}],
        limit=3)
    assert needs, 'a concept block is an image-bearing block'
    for need in needs:
        assert need['query'] == 'Least-cost combination of inputs', need['query']


# ------------------------------------------------- a shared word is not a shared subject
def test_one_coincidental_word_is_not_enough_to_illustrate_a_concept():
    """The AP Microeconomics pass is the measurement behind this test.

    Twenty-two concepts were given a photograph and about ten of them were wrong, every one
    with an impeccable credit line: "Asymmetric Ashes (artist's impression)" for asymmetric
    information, a 1907 gyroscope car for short-run cost curves, a street named Lower Price
    Hill for price ceilings. Each shared exactly one word with the concept, and covering
    half of a two-word title *is* one word, so the overlap score passed them.
    """
    asserted = [
        ('Asymmetric information', 'Asymmetric Ashes (artists impression)',
         'ESO image of a planetary nebula'),
        ('Short-run cost curves', 'Brennan Gyroscope Car, 1907 (01)',
         'a gyroscope car built in 1907'),
        ('Price ceilings and floors', '8th Street, Lower Price Hill, Cincinnati, OH',
         'a street scene'),
        ('Common resources and the tragedy of the commons',
         'Topographic map of United Kingdom of Libya', 'a map'),
        ('Perfect competition characteristics', 'Hiller XHOE-1 Hornet', 'an aircraft'),
    ]
    for query, title, description in asserted:
        assert not media.head_mentioned(query, title, description), title

    # The clearest case is the two-word title: covering half of it is one word, and one
    # shared word was enough for the old gate to accept the asset.
    assert media.lexical_overlap('Asymmetric information',
                                 'Asymmetric Ashes (artists impression)',
                                 'a planetary nebula') == 0.5

    # And the correct ones still pass: a rule that refuses everything is not a filter.
    accepted = [
        ('Taxes and tax incidence', 'TopTaxIncidence PikettySaez2007',
         'tax incidence across the top of the distribution'),
        ('Deadweight loss of taxation', 'Detailed tax wedge',
         'per-unit tax and the wedge between buyer and seller price'),
        ('Long-run average total cost and economies of scale', 'Economies-of-Scale',
         'economies of scale and the long run average cost curve'),
        ('Monopsony', 'Monopsony Labour Market', 'a single buyer of labour'),
    ]
    for query, title, description in accepted:
        assert media.head_mentioned(query, title, description), title


def test_a_rejected_shared_word_says_which_term_is_missing(media_settings):
    """The reason a reviewer reads has to name the term, not the score.

    "Only 50% of the query words appear" is true and useless here: the half that appeared is
    the half that means nothing. The rejection names the head term the asset never mentions.
    """
    # A four-word query, so the coverage rule is satisfied by half of it: the asset mentions
    # "monopoly" and "market" and never says what the lesson is about - the word "power".
    # This is the measured case: "Internet Key Layers.png" illustrated monopoly's sources of
    # market power on the strength of two words, neither of which is the head term.
    candidate = _cleared_candidate(
        title='Internet Key Layers',
        description='the market for internet access under a monopoly',
        tags=['internet', 'layers'])
    accepted, rejected = media.filter_candidates([candidate],
                                                'Monopoly sources of market power',
                                                min_overlap=0.5)
    assert not accepted
    assert len(rejected) == 1
    assert "'power'" in rejected[0].rejected
    assert 'coincidental word' in rejected[0].rejected


def test_the_head_term_survives_inflection(media_settings):
    """"Taxation" has to reach a caption that says "tax".

    Requiring four characters after stripping the suffix left "taxation" unmatched against
    the tax-incidence diagram whose own caption says "per-unit tax", so a correct figure was
    refused for using the shorter word.
    """
    assert media.head_mentioned('Deadweight loss of taxation', 'tax wedge',
                               'the per-unit tax and its incidence')
    assert media.head_mentioned('Price elasticity of demand', 'Elastic demand',
                               'a steep demand curve')
    assert media.head_mentioned('Production possibilities curve', 'PPF curve', 'a frontier')
    assert not media.head_mentioned('Deadweight loss of taxation', 'Portrait of a merchant',
                                    'oil on canvas, 1640')


def test_a_withdrawn_photograph_stops_being_served(settings):
    """The index is append-only, so "no photograph" needs a row of its own.

    After a stricter relevance gate, re-running illustration reported concepts with no
    photograph while the lessons still carried the pictures an earlier pass had attached -
    the report and the page disagreeing, with the page being what a learner reads. The
    tombstone makes the withdrawal as recorded as the assignment was.
    """
    import json as _json

    concept = 'concept_withdrawn'
    media.record_lesson_images(settings, concept, [
        {'slot': 'concept', 'block_index': 1, 'sha256': 'a' * 64, 'caption': 'an old pick'}])
    assert len(media.lesson_image_assignments(settings, concept)) == 1

    media.withdraw_lesson_images(settings, concept)
    assert media.lesson_image_assignments(settings, concept) == []

    lines = media.lesson_index_path(settings).read_text(encoding='utf-8').splitlines()
    rows = [row for row in (_json.loads(line) for line in lines if line.strip())
            if row.get('concept_id') == concept]
    assert any(row.get('withdrawn') for row in rows), 'the withdrawal is on the record'

    # A later assignment is not blocked by an earlier withdrawal.
    media.record_lesson_images(settings, concept, [
        {'slot': 'concept', 'block_index': 1, 'sha256': 'b' * 64, 'caption': 'a new pick'}])
    current = media.lesson_image_assignments(settings, concept)
    assert [row['sha256'] for row in current] == ['b' * 64]

    # And another concept is untouched by a neighbour's withdrawal.
    media.record_lesson_images(settings, 'neighbour', [
        {'slot': 'concept', 'block_index': 1, 'sha256': 'c' * 64}])
    media.withdraw_lesson_images(settings, concept)
    assert len(media.lesson_image_assignments(settings, 'neighbour')) == 1


def test_the_other_half_of_the_concept_is_a_wrong_answer_not_a_near_miss():
    """A short-run diagram under a long-run question.

    Measured on the third AP Microeconomics pass: "Monopolistic competition in the long run"
    was illustrated with the short-run equilibrium diagram. Entry and exit are exactly what
    separate the two, and that picture shows neither, so the lesson would have taught the
    case it was not about with a legitimate credit line under it.
    """
    assert media.contradicts(
        'Monopolistic competition in the long run',
        'Short-run equilibrium of the firm under monopolistic competition') == \
        ('long run', 'short run')
    # Hyphens and en dashes are the same word to a reader, so they are the same word here.
    assert media.contradicts('Long-run average cost', 'short–run cost curves')
    # The asset that *is* on the right side is untouched.
    assert media.contradicts('Long-run average cost', 'Long-run cost curves') is None
    assert media.contradicts('Short-run cost curves', 'Short run cost curves') is None
    # The same shape, on the axis of information rather than time: a graph about *perfect*
    # information for a lesson on the asymmetric case is the opposite claim.
    assert media.contradicts('Asymmetric information', 'Balance of Power Graph',
                             'Balance of Power with Perfect Information') == \
        ('asymmetric information', 'perfect information')
    assert media.contradicts('Asymmetric information',
                             'Asymmetric information and lemons') is None

    candidate = _cleared_candidate(
        title='Short-run equilibrium of the firm under monopolistic competition',
        description='a diagram', tags=['monopolistic competition'])
    accepted, rejected = media.filter_candidates(
        [candidate], 'Monopolistic competition in the long run', min_overlap=0.5)
    assert not accepted
    assert 'wrong answer with a credit line' in rejected[0].rejected


def test_infographics_is_not_information():
    """A prefix rule was tried and removed within the hour.

    It matched ``infographic`` against ``information``, so a chart captioned "Balance of power
    graph" and tagged *infographics* was attached to the lesson on asymmetric information.
    Roots must be equal, not merely alike at the start.
    """
    assert not media.head_mentioned('Asymmetric information', 'Balance of Power Graph',
                                    'infographics balance of power')
    # Equality after stemming still lets the inflected form reach the short one.
    assert media.head_mentioned('Deadweight loss of taxation', 'Tax deadweight', 'tax')
    assert media.head_mentioned('Price elasticity of demand', 'Demand curves', 'demand')


def test_a_two_word_query_needs_both_words(settings):
    """A short query is cheap to satisfy by accident, so it has to be covered completely.

    "Asymmetric information" was illustrated with a heritage photograph of "The Old Coach
    House, Parkview Clinic" because the record's tags say *information*. One word out of two
    was 50%, and 50% was the floor. A query of three or more words keeps the floor, because
    demanding all of "long-run average total cost and economies of scale" would refuse the
    one asset that is exactly about it.
    """
    half = _cleared_candidate(title='The Old Coach House', description='a listed building',
                              tags=['building', 'information'])
    accepted, rejected = media.filter_candidates([half], 'Asymmetric information',
                                                min_overlap=0.5)
    assert not accepted, 'half of a two-word title is one word, which is a coincidence'
    assert 'title, description or tags' in rejected[0].rejected

    both = _cleared_candidate(title='Adverse selection under asymmetric information',
                              description='a lemons market',
                              tags=['asymmetric information', 'adverse selection'])
    accepted, _ = media.filter_candidates([both], 'Asymmetric information', min_overlap=0.5)
    assert accepted, 'the asset that says both words is accepted'

    long_query = _cleared_candidate(title='Economies-of-Scale.jpg',
                                    description='economies of scale and the long run average '
                                                'cost curve')
    accepted, _ = media.filter_candidates(
        [long_query], 'Long-run average total cost and economies of scale', min_overlap=0.5)
    assert accepted, 'a long query is still judged by the floor, not by total coverage'
