"""Tests for the curation-facing tools added for teacher material search.

Around the guarantees, not the internals: every gate asserted by its *refusal* (a gate
never exercised is a gate that quietly died), every pack row checked against the audited
licence registry, and no test needs the network -- the offline paths prove the harness
stays offline.
"""

from dataclasses import replace
from types import SimpleNamespace

from app.ingest import policy
from app.harness import toolbox
from app.harness.toolbox import ToolContext
from test_api import settings  # noqa: F401 - fixture


def _ctx(settings_obj, role: str) -> ToolContext:
    user = SimpleNamespace(id='u1', role=role) if role else None
    return ToolContext(settings=settings_obj, user=user, now=1_700_000_000.0)


# ------------------------------------------------------------------ pack invariants

def test_every_pack_row_is_registered_and_https(settings):
    from app.harness import game_search
    registered = {entry.name for entry in policy.MEDIA_SOURCES}
    for game in game_search.pack_games():
        assert game['policy_name'] in registered, (
            f"{game['slug']} names {game['policy_name']!r}, which is not in the audited "
            "registry -- an unregistered policy_name would be withheld on re-evaluation")
        assert game['url'].startswith('https://'), game['url']


def test_game_sources_are_all_link_only():
    for entry in policy.GAME_SOURCES:
        assert entry.licence_class == policy.LicenceClass.LINK_ONLY, entry.name


def test_wikipedia_policy_is_ingestible():
    assert policy.WIKIPEDIA_REST.licence_class == policy.LicenceClass.CC_BY_SA
    assert policy.WIKIPEDIA_REST in policy.MEDIA_SOURCES


# ------------------------------------------------------------------ find_game

def test_find_game_refuses_learner_role(settings):
    result = toolbox._find_game(_ctx(settings, 'learner'), 'fractions')
    assert not result.ok and 'teacher-facing' in result.refused


def test_find_game_refuses_missing_user(settings):
    result = toolbox._find_game(_ctx(settings, ''), 'fractions')
    assert not result.ok and 'teacher-facing' in result.refused


def test_find_game_returns_registered_cards(settings):
    result = toolbox._find_game(_ctx(replace(settings, commercial_use=False), 'teacher'),
                                'fractions manipulatives')
    assert result.ok
    cards = result.data['games']
    assert cards and all(card['policy_name'] in
                         {e.name for e in policy.MEDIA_SOURCES} for card in cards)
    assert all(card['integration_mode'] == 'deep_link' for card in cards)


def test_find_game_names_the_gap(settings):
    result = toolbox._find_game(_ctx(settings, 'teacher'), 'xylophone calculus')
    assert not result.ok
    assert 'operator-curated' in ' '.join(result.notes)


def test_find_game_withholds_under_commercial_use(settings):
    result = toolbox._find_game(_ctx(replace(settings, commercial_use=True), 'teacher'),
                                'fractions')
    assert all(card['status'] == 'withheld' for card in result.data['games'])


# ------------------------------------------------------------------ fetch_page_text

def test_fetch_page_text_refuses_when_media_disabled(settings):
    result = toolbox._tools_creation.fetch_page_text(
        _ctx(replace(settings, media_enabled=False), 'teacher'),
        'https://en.wikipedia.org/wiki/Parabola')
    assert not result.ok and 'HARNESS_MEDIA_ENABLED' in result.refused


def test_fetch_page_text_refuses_uncleared_domain_without_network(settings):
    result = toolbox._tools_creation.fetch_page_text(
        _ctx(replace(settings, media_enabled=True), 'teacher'),
        'https://example.com/whatever')
    assert not result.ok and 'link_only' in str(result.data)
    # The gate fires before any fetch: the refusal names the licence position.
    assert 'licence-cleared' in result.refused


def test_fetch_page_text_refuses_non_http_scheme(settings):
    result = toolbox._tools_creation.fetch_page_text(
        _ctx(replace(settings, media_enabled=True), 'teacher'), 'file:///etc/passwd')
    assert not result.ok and 'http(s)' in result.refused


def test_fetch_page_text_reads_cleared_domain(settings, monkeypatch):
    calls = {}

    class FakeResponse:
        url = 'https://en.wikipedia.org/wiki/Parabola'
        text = '<html><head><style>.x{}</style></head><body><p>A parabola is a curve.</p></body></html>'
        headers = {'content-type': 'text/html; charset=utf-8'}
        def raise_for_status(self): pass

    class FakeClient:
        def __init__(self, *a, **k): calls['ua'] = (k.get('headers') or {}).get('User-Agent')
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, url): return FakeResponse()

    import httpx
    monkeypatch.setattr(httpx, 'Client', FakeClient)
    result = toolbox._tools_creation.fetch_page_text(
        _ctx(replace(settings, media_enabled=True), 'teacher'),
        'https://en.wikipedia.org/wiki/Parabola')
    assert result.ok and 'parabola' in result.data['text']
    assert result.data['licence_class'] == 'cc_by_sa'


def test_fetch_page_text_re_gates_redirects(settings, monkeypatch):
    class FakeResponse:
        url = 'https://khanacademy.org/math'   # redirect landed on a PROHIBITED domain
        text = '<html><body>lessons</body></html>'
        headers = {'content-type': 'text/html'}
        def raise_for_status(self): pass

    class FakeClient:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, url): return FakeResponse()

    import httpx
    monkeypatch.setattr(httpx, 'Client', FakeClient)
    result = toolbox._tools_creation.fetch_page_text(
        _ctx(replace(settings, media_enabled=True), 'teacher'),
        'https://en.wikipedia.org/wiki/Parabola')
    assert not result.ok and 'redirected' in result.refused


# ------------------------------------------------------------------ wikipedia_summary

def test_wikipedia_summary_refuses_when_media_disabled(settings):
    result = toolbox._tools_creation.wikipedia_summary(
        _ctx(replace(settings, media_enabled=False), 'teacher'), 'Parabola')
    assert not result.ok and 'HARNESS_MEDIA_ENABLED' in result.refused


def test_wikipedia_summary_refuses_bad_lang(settings):
    result = toolbox._tools_creation.wikipedia_summary(
        _ctx(replace(settings, media_enabled=True), 'teacher'), 'Parabola', lang='../etc')
    assert not result.ok and 'invalid' in result.refused


# ------------------------------------------------------------------ browser_snapshot

def test_browser_snapshot_refuses_learner(settings):
    result = toolbox._browser_snapshot(_ctx(settings, 'learner'), 'https://example.com')
    assert not result.ok and 'teacher-facing' in result.refused


def test_browser_snapshot_refuses_when_disabled(settings):
    result = toolbox._browser_snapshot(_ctx(replace(settings, browser_enabled=False), 'teacher'),
                                       'https://example.com')
    assert not result.ok and 'HARNESS_BROWSER_ENABLED' in result.refused


def test_search_videos_refuses_learner(settings):
    result = toolbox._search_videos(_ctx(settings, 'learner'), 'parabola')
    assert not result.ok and 'teacher-facing' in result.refused


def test_search_videos_refuses_when_media_disabled(settings):
    result = toolbox._search_videos(
        _ctx(replace(settings, media_enabled=False), 'teacher'), 'parabola')
    assert not result.ok and 'HARNESS_MEDIA_ENABLED' in result.refused
