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

#: Resolution order. The maintained package first, the legacy name second so an
#: environment that has not migrated yet keeps working.
NAMES = ('ddgs', 'duckduckgo_search')


def load():
    """Return the provider's ``DDGS`` class, or ``None`` when none is installed.

    A missing package and a ``sys.modules[name] is None`` entry (how the tests
    simulate absence) both come back as ``None``, so callers get one answer for
    "no provider" instead of two different exceptions.
    """
    import importlib

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
    """Whether any provider is importable. The readiness probe's question."""
    return load() is not None
