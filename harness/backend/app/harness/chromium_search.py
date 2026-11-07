"""Headless-Chromium search provider: real results without a search API key.

Why this module exists
----------------------
``web_search`` and the teacher's video discovery both depended on ``ddgs`` (the
DuckDuckGo SERP client). On networks where DuckDuckGo's HTML endpoint answers 403,
and in builds where the optional ``ddgs`` wheel was not installed, the tools
correctly refused -- but the learner saw "search is not configured" rather than a
result. A browser is already an optional declared dependency of this project
(``requirements-optional.txt`` pins ``playwright``), and a real Chromium renders
the pages that a bare HTTP client cannot: Bing's SERP and YouTube's results page.

So this module supplies the *same DDGS-shaped rows* (``title``/``href``/``body``)
from a headless browser, and YouTube HTML that ``video_search._page_hits`` already
knows how to parse. No API key, no quota, no third-party search contract.

Honesty rules:

* A failure is raised, never converted into an empty result set. "No results" and
  "search could not run" are different facts and the callers print one of them.
* Only public result pages are read. No cookies are loaded, no authenticated
  session exists, and no page content is sent to a model by this module -- the
  existing licence gate in ``tools_creation`` decides what may be quoted.
* The browser is launched per call and closed in a ``finally``. It is never left
  running, and a proxy failure is retried once as a direct connection.
"""

from __future__ import annotations

import base64
import glob
import os
import re
import sys
import threading
from typing import Any, Mapping, Sequence

from urllib.parse import urlencode

__all__ = [
    'available', 'web', 'youtube_html', 'decode_bing_href', 'normalise_rows',
    'ChromiumUnavailable', 'ChromiumSearchError',
]

USER_AGENT = (
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
)

#: Bing wraps organic links in ``/ck/a?...&u=a1<base64url>``. ``u=`` is decoded
#: in :func:`decode_bing_href` so the licence gate sees the real hostname.
_BING_JS = r"""() => Array.from(document.querySelectorAll('li.b_algo')).slice(0, 25).map(li => ({
  title: (li.querySelector('h2')?.textContent || '').trim(),
  href: li.querySelector('h2 a')?.href || '',
  body: (li.querySelector('.b_caption p')?.textContent
         || li.querySelector('p')?.textContent || '').trim()
}))"""

_BING_SELECTOR = 'li.b_algo'
_YT_SELECTOR = 'a#video-title'
_TIMEOUT_MS = 30_000
_SETTLE_MS = 900


class ChromiumUnavailable(RuntimeError):
    """The browser cannot be used at all (package or binary missing)."""


class ChromiumSearchError(RuntimeError):
    """The browser ran but the results could not be read. Carries the attempt log."""


_available_cache: tuple[bool, str] | None = None
_available_guard = threading.Lock()


def chromium_executable() -> str:
    """Locate a downloaded Chromium without starting a Playwright driver.

    Starting the driver purely to read ``chromium.executable_path`` leaves its
    event-loop task un-awaited on some Python/driver combinations, which prints
    a ``TargetClosedError`` at process exit. Looking at the install layout is
    enough for a readiness probe; a real launch in :func:`_fetch` is the final
    authority and reports its own failure if the binary is unusable.
    """
    root = (os.getenv('PLAYWRIGHT_BROWSERS_PATH') or '').strip()
    if not root:
        if sys.platform == 'darwin':
            root = os.path.expanduser('~/Library/Caches/ms-playwright')
        elif sys.platform == 'win32':
            root = os.path.join(os.getenv('LOCALAPPDATA', ''), 'ms-playwright')
        else:
            root = os.path.expanduser('~/.cache/ms-playwright')
    relatives = (
        'chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/'
        'Google Chrome for Testing',
        'chrome-mac/Google Chrome for Testing.app/Contents/MacOS/'
        'Google Chrome for Testing',
        'chrome-linux64/chrome', 'chrome-linux/chrome', 'chrome-win/chrome.exe',
        'chrome-linux/headless_shell', 'chrome-linux64/headless_shell',
    )
    for folder in sorted(glob.glob(os.path.join(root, 'chromium-*')), reverse=True):
        for relative in relatives:
            candidate = os.path.join(folder, relative)
            if os.path.isfile(candidate):
                return candidate
    return ''


def available() -> tuple[bool, str]:
    """Whether a usable headless Chromium exists, with a sentence either way.

    Deliberately does not launch a browser: this is called by readiness probes on
    every capability sweep, and a cold launch there would turn a status page into
    a several-second network operation. Importing the driver and checking that
    its executable is on disk is enough to answer "is the provider installed".
    """
    global _available_cache
    if _available_cache is not None:
        return _available_cache
    with _available_guard:
        if _available_cache is not None:
            return _available_cache
        try:
            import playwright.sync_api  # noqa: F401 - importability is the check
        except ImportError:
            _available_cache = (False,
                                'The playwright package is not installed in this environment.')
            return _available_cache
        executable = chromium_executable()
        if not executable:
            _available_cache = (False,
                                'Chromium is not downloaded. Run `playwright install chromium`.')
        else:
            _available_cache = (True, f'Headless Chromium is available at {executable}.')
        return _available_cache


def reset_cache() -> None:
    """Forget the cached answer. Used by tests that install/remove the browser."""
    global _available_cache
    with _available_guard:
        _available_cache = None


def _proxy_modes() -> list[str]:
    """Proxy first when the host declares one, then a direct attempt.

    WorkBuddy-style sandboxes export ``HTTPS_PROXY`` and only allow outbound
    traffic through it; a plain server install has no proxy at all. Trying both
    costs one extra launch only when the first path fails.
    """
    for name in ('HTTPS_PROXY', 'https_proxy', 'HTTP_PROXY', 'http_proxy'):
        value = (os.getenv(name) or '').strip()
        if value:
            return [value, '']
    return ['']


def _fetch(url: str, *, selector: str, js: str | None = None,
           settle_ms: int = _SETTLE_MS,
           timeout_ms: int = _TIMEOUT_MS) -> tuple[str, list[dict[str, Any]]]:
    """Render one public results page, returning ``(html, extracted_rows)``."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ChromiumUnavailable('The playwright package is not installed.') from exc

    failures: list[str] = []
    for mode in _proxy_modes():
        label = 'proxy' if mode else 'direct'
        try:
            with sync_playwright() as driver:
                kwargs: dict[str, Any] = {
                    'headless': True,
                    'args': ['--no-sandbox', '--disable-dev-shm-usage'],
                }
                if mode:
                    kwargs['proxy'] = {
                        'server': mode,
                        'bypass': '127.0.0.1,localhost,<-loopback>',
                    }
                browser = driver.chromium.launch(**kwargs)
                try:
                    page = browser.new_page(user_agent=USER_AGENT, locale='en-US')
                    response = page.goto(url, wait_until='domcontentloaded',
                                         timeout=timeout_ms)
                    if response is not None and response.status >= 400:
                        raise ChromiumSearchError(f'HTTP {response.status}')
                    if selector:
                        try:
                            page.wait_for_selector(selector, timeout=12_000)
                        except Exception:  # noqa: BLE001 - a slow SERP still has HTML
                            pass
                    if settle_ms:
                        page.wait_for_timeout(settle_ms)
                    rows = page.evaluate(js) if js else []
                    return page.content(), list(rows or [])
                finally:
                    browser.close()
        except Exception as exc:  # noqa: BLE001 - try the other network path
            failures.append(f'{label}: {type(exc).__name__}: {str(exc)[:180]}')
    raise ChromiumSearchError('Chromium search failed (' + '; '.join(failures) + ')')


_BING_REDIRECT = re.compile(r'[?&]u=a1([A-Za-z0-9_-]+)')


def decode_bing_href(href: str) -> str:
    """Unwrap a Bing ``/ck/a`` redirect, or return the href unchanged.

    The redirect encodes the destination as ``a1`` followed by unpadded URL-safe
    base64. Decoding here is not cosmetic: ``tools_creation._domain_rights``
    classifies by hostname, and a wrapped click URL would make every result look
    like an unaudited ``bing.com`` link.
    """
    match = _BING_REDIRECT.search(href or '')
    if not match:
        return href or ''
    token = match.group(1)
    try:
        return base64.urlsafe_b64decode(token + '=' * (-len(token) % 4)).decode(
            'utf-8', 'replace')
    except ValueError:
        return href


def normalise_rows(rows: Sequence[Mapping[str, Any]] | None,
                   limit: int = 6) -> list[dict[str, str]]:
    """Pure shaping of extracted SERP rows into the DDGS row contract."""
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    ceiling = max(1, min(int(limit or 6), 25))
    for row in rows or []:
        if not isinstance(row, Mapping):
            continue
        href = decode_bing_href(str(row.get('href') or ''))
        if not href.startswith(('http://', 'https://')) or href in seen:
            continue
        seen.add(href)
        out.append({
            'title': str(row.get('title') or '')[:200],
            'href': href,
            'body': str(row.get('body') or '')[:600],
        })
        if len(out) >= ceiling:
            break
    return out


def web(query: str, limit: int = 6) -> list[dict[str, str]]:
    """Real web results shaped exactly like ``DDGS().text()`` rows."""
    cleaned = ' '.join((query or '').split())[:200]
    if not cleaned:
        raise ChromiumSearchError('No query supplied.')
    url = 'https://www.bing.com/search?' + urlencode(
        {'q': cleaned, 'count': max(10, min(30, int(limit or 6) * 3))})
    _html, rows = _fetch(url, selector=_BING_SELECTOR, js=_BING_JS)
    results = normalise_rows(rows, limit)
    if not results:
        raise ChromiumSearchError('The browser results page carried no usable rows.')
    return results


def youtube_html(query: str) -> str:
    """Rendered YouTube results page, ready for ``video_search._page_hits``.

    The page's own ``ytInitialData`` carries the video id, title, channel and
    duration, which is better provenance than a SERP's concatenated snippet.
    """
    cleaned = ' '.join((query or '').split())[:200]
    if not cleaned:
        raise ChromiumSearchError('No query supplied.')
    url = 'https://www.youtube.com/results?' + urlencode(
        {'search_query': cleaned, 'hl': 'en', 'gl': 'US'})
    html, _rows = _fetch(url, selector=_YT_SELECTOR, settle_ms=800)
    if 'ytInitialData' not in html:
        raise ChromiumSearchError('The browser results page carried no ytInitialData.')
    return html
