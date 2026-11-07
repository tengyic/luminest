"""The Chromium search provider: parsing, provider resolution, no network.

These tests never launch a browser. They cover the two things a live SERP
cannot be trusted to keep stable: the Bing redirect unwrapping that decides
which hostname the licence gate sees, and the provider-resolution order that
decides whether a build without ``playwright`` still gets an honest refusal.
"""

from __future__ import annotations

import base64
import json
import sys
import types
from types import SimpleNamespace

from app.harness import chromium_search as cs
from app.harness import ddg_provider


def _bing_wrap(url: str) -> str:
    token = base64.urlsafe_b64encode(url.encode()).decode().rstrip('=')
    return f'https://www.bing.com/ck/a?u=a1{token}&ptn=3&ver=2'


def test_a_bing_redirect_is_unwrapped_before_the_licence_gate_sees_it():
    href = _bing_wrap('https://en.wikipedia.org/wiki/Fraction')
    assert cs.decode_bing_href(href) == 'https://en.wikipedia.org/wiki/Fraction'


def test_a_plain_href_is_left_alone_and_garbage_is_not_decoded():
    assert cs.decode_bing_href('https://example.com/a?b=1') == 'https://example.com/a?b=1'
    assert cs.decode_bing_href('') == ''
    assert cs.decode_bing_href('https://www.bing.com/ck/a?u=a1!!!') == \
        'https://www.bing.com/ck/a?u=a1!!!'


def test_normalise_rows_deduplicates_unwrapped_urls_and_caps_the_batch():
    rows = [
        {'title': 'First', 'href': _bing_wrap('https://example.com/'), 'body': 'one'},
        {'title': 'Duplicate', 'href': 'https://example.com/', 'body': 'two'},
        {'title': 'Not a URL', 'href': 'javascript:void(0)', 'body': ''},
        {'title': 'Empty', 'href': '', 'body': ''},
        {'title': 'Second', 'href': 'https://other.example/', 'body': 'x' * 900},
    ]
    out = cs.normalise_rows(rows, 5)
    assert [row['href'] for row in out] == ['https://example.com/', 'https://other.example/']
    assert out[0]['title'] == 'First'
    assert len(out[1]['body']) == 600


def test_normalise_rows_honours_the_limit_and_rejects_bad_shapes():
    rows = [{'title': str(i), 'href': f'https://e.example/{i}', 'body': ''}
            for i in range(10)]
    assert len(cs.normalise_rows(rows, 3)) == 3
    assert cs.normalise_rows(None) == []
    assert cs.normalise_rows(['not a mapping']) == []


def test_available_is_false_without_playwright(monkeypatch):
    cs.reset_cache()
    monkeypatch.setitem(sys.modules, 'playwright.sync_api', None)
    ok, why = cs.available()
    assert ok is False
    assert 'playwright' in why.casefold()
    cs.reset_cache()


def _install_fake_playwright(monkeypatch):
    """Satisfy the importability gate without installing the optional package.

    ``available()`` checks two independent gates: ``playwright.sync_api`` must
    import, *and* a Chromium executable must be on disk. Tests of the second
    gate have to satisfy the first explicitly. A clean dev venv deliberately
    excludes the optional ``playwright`` distribution, so the import gate used
    to short-circuit here and the assertion failed with ``assert False is True``
    even though binary discovery was correct.
    """
    package = types.ModuleType('playwright')
    package.__path__ = []  # a package, not a leaf module
    sync_api = types.ModuleType('playwright.sync_api')
    package.sync_api = sync_api
    monkeypatch.setitem(sys.modules, 'playwright', package)
    monkeypatch.setitem(sys.modules, 'playwright.sync_api', sync_api)


def test_available_reports_the_browser_binary(monkeypatch, tmp_path):
    cs.reset_cache()
    _install_fake_playwright(monkeypatch)
    (tmp_path / 'chromium-9999').mkdir()
    exe = tmp_path / 'chromium-9999' / 'chrome-linux64' / 'chrome'
    exe.parent.mkdir()
    exe.write_bytes(b'')
    monkeypatch.setenv('PLAYWRIGHT_BROWSERS_PATH', str(tmp_path))
    ok, why = cs.available()
    assert ok is True
    assert 'chromium-9999' in why
    cs.reset_cache()


def test_available_still_requires_a_binary_when_playwright_imports(monkeypatch, tmp_path):
    """Regression: importability alone must never be reported as a usable browser."""
    cs.reset_cache()
    _install_fake_playwright(monkeypatch)
    monkeypatch.setenv('PLAYWRIGHT_BROWSERS_PATH', str(tmp_path))  # empty: no chromium-* dir
    ok, why = cs.available()
    assert ok is False
    assert 'not downloaded' in why.casefold()
    cs.reset_cache()


def test_resolve_prefers_a_working_browser_when_enabled(monkeypatch):
    monkeypatch.setattr(cs, 'available', lambda: (True, 'ready'))
    provider, source = ddg_provider.resolve(
        SimpleNamespace(chromium_search_enabled=True))
    assert source == 'chromium'
    assert provider is ddg_provider.ChromiumDDGS


def test_resolve_falls_back_to_the_package_when_the_browser_is_off(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(ddg_provider, 'load', lambda: sentinel)
    provider, source = ddg_provider.resolve(
        SimpleNamespace(chromium_search_enabled=False))
    assert source == 'ddgs' and provider is sentinel


def test_resolve_is_an_honest_absence_when_nothing_is_available(monkeypatch):
    monkeypatch.setattr(cs, 'available', lambda: (False, 'no binary'))
    monkeypatch.setattr(ddg_provider, 'load', lambda: None)
    provider, source = ddg_provider.resolve(
        SimpleNamespace(chromium_search_enabled=True))
    assert provider is None and source == ''


def _yt_html(video_id: str = 'abcdefghijk') -> str:
    """A minimal results page carrying one videoRenderer with a 5:30 duration."""
    data = {'contents': {'twoColumnSearchResultsRenderer': {'primaryContents': {
        'sectionListRenderer': {'contents': [{'itemSectionRenderer': {'contents': [
            {'videoRenderer': {
                'videoId': video_id,
                'title': {'runs': [{'text': 'Fractions for kids'}]},
                'ownerText': {'runs': [{'text': 'Math Antics'}]},
                'lengthText': {'simpleText': '5:30'},
            }}]}}]}}}}}
    return '<html><script>var ytInitialData = ' + json.dumps(data) + ';</script></html>'


def test_a_youtube_site_query_is_answered_from_the_providers_own_page(monkeypatch):
    monkeypatch.setattr(cs, 'youtube_html', lambda q: _yt_html())
    monkeypatch.setattr(cs, 'web',
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError('a site:youtube.com query must not hit a SERP')))
    rows = ddg_provider.ChromiumDDGS().text('site:youtube.com fractions', 3)
    assert len(rows) == 1
    assert rows[0]['href'] == 'https://www.youtube.com/watch?v=abcdefghijk'
    assert rows[0]['title'] == 'Fractions for kids'
    assert 'Math Antics' in rows[0]['body']


def test_an_ordinary_query_goes_to_the_web_serp(monkeypatch):
    seen = {}

    def fake_web(query, limit):
        seen['query'], seen['limit'] = query, limit
        return [{'title': 'Rent control', 'href': 'https://example.com/rent',
                 'body': 'A case study.'}]

    monkeypatch.setattr(cs, 'web', fake_web)
    rows = ddg_provider.ChromiumDDGS().text('rent control case study', 2)
    assert seen == {'query': 'rent control case study', 'limit': 2}
    assert rows[0]['href'] == 'https://example.com/rent'
