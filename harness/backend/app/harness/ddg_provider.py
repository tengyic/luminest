"""Resolve a DuckDuckGo search provider, preferring the maintained package.

The project originally pinned ``duckduckgo-search``. That package was renamed to
``ddgs`` and the final ``duckduckgo-search`` release (8.1.1) is a rename stub whose
search backend returns nothing, so a call through it succeeds and reports zero
results -- the worst failure mode for a tool whose whole value is that it returns
real ones. ``ddgs`` is the continuation, has the same ``DDGS().text(query,
max_results=...)`` shape, and returns real hits.

Both names live in one loader on purpose: the web-search tool and the teacher
video search each imported the provider directly, so a rename cost two edits and
could leave one of them silently broken. Resolving in one place also means the
two tools cannot disagree about which package is actually installed.
"""

from __future__ import annotations

import importlib
import re
from typing import Any

#: Resolution order. The maintained package first, the legacy name second so an
#: environment that has not migrated yet keeps working.
NAMES = ('ddgs', 'duckduckgo_search')


def load():
    """Return the installed package's ``DDGS`` class, or ``None``.

    A missing package and a ``sys.modules[name] is None`` entry (how the tests
    simulate absence) both come back as ``None``, so callers get one answer for
    "no provider" instead of two different exceptions.

    This loader is deliberately *package-only*. :func:`resolve` is the entry
    point that also considers the headless-Chromium provider, so a test that
    simulates "no ddgs installed" still observes the refusal it asserts.
    """
    for name in NAMES:
        try:
            module = importlib.import_module(name)
        except ImportError:
            continue
        ddgs = getattr(module, 'DDGS', None)
        if ddgs is not None:
            return ddgs
    return None


def installed() -> bool:
    """Whether a search *package* is importable. The packaging gate's question."""
    return load() is not None


class ChromiumDDGS:
    """A DDGS-shaped adapter backed by a real headless Chromium.

    ``tools_creation.web_search`` and ``video_search._ddg_search`` both call
    ``DDGS().text(query, max_results=...)`` and expect ``title``/``href``/``body``
    rows. Implementing that one method here means neither call site needs to
    know which provider answered.

    A ``site:youtube.com`` query is answered from YouTube's own results page
    rather than a SERP: Bing ignores the ``site:`` operator often enough that
    the fallback used to return calculator pages for a video search.
    """

    backend = 'chromium'

    def text(self, query: str, max_results: int = 6) -> list[dict[str, Any]]:
        from . import chromium_search

        asked = ' '.join((query or '').split())[:200]
        try:
            limit = max(1, min(int(max_results or 6), 25))
        except (TypeError, ValueError):
            limit = 6
        if re.search(r'site\s*:\s*youtube\.com', asked, re.IGNORECASE):
            cleaned = re.sub(r'site\s*:\s*youtube\.com', '', asked,
                             flags=re.IGNORECASE).strip()
            html = chromium_search.youtube_html(cleaned)
            # Local import: video_search imports this module's package through
            # ``_keyless_search``, so a module-level import would be circular.
            from .video_search import _page_hits
            return [
                {'title': str(hit.get('title') or ''),
                 'href': f'https://www.youtube.com/watch?v={hit["video_id"]}',
                 'body': f'{hit.get("channel") or ""} '
                         f'({int(hit.get("seconds") or 0)}s)'}
                for hit in _page_hits(html, limit)
            ]
        return chromium_search.web(asked, limit)


def resolve(settings=None) -> tuple[Any, str]:
    """Return ``(provider_class_or_None, source)`` for the current instance.

    The browser wins when it is enabled *and* installed: measured against the
    networks this app runs on, DuckDuckGo's HTML endpoint answers 403 while a
    rendered Bing/YouTube page succeeds. The packaged ``ddgs`` remains the
    fallback for builds that exclude ``playwright`` (the desktop bundle does,
    to save ~40 MB), so no deployment loses search by turning the browser off.
    """
    if settings is not None and getattr(settings, 'chromium_search_enabled', False):
        try:
            from . import chromium_search
            ready, _why = chromium_search.available()
            if ready:
                return ChromiumDDGS, 'chromium'
        except ImportError:
            pass
    packaged = load()
    if packaged is not None:
        return packaged, 'ddgs'
    return None, ''
