"""Bundled course outlines that ship with the harness.

These live on disk as ordinary scope-and-sequence files so that the same code path
that ingests a customer's outline also builds the bundled ones. Nothing here is
special-cased: if the bundled seed were deleted, the harness would simply start
with an empty graph.
"""

from __future__ import annotations

from pathlib import Path

from .base import SourceError
from .scope_sequence import ScopeSequenceSource

SEED_DIR = Path(__file__).resolve().parent.parent / 'seed'


def available() -> list[str]:
    """Names of bundled outlines, sorted."""
    if not SEED_DIR.exists():
        return []
    return sorted(p.stem for p in SEED_DIR.glob('*.json'))


def bundled_outline(name: str) -> ScopeSequenceSource:
    """Load a bundled outline by name (without the ``.json`` suffix)."""
    path = SEED_DIR / f'{name}.json'
    if not path.exists():
        raise SourceError(f'No bundled outline named {name!r}. Available: {available()}')
    return ScopeSequenceSource(path)
