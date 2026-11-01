"""Ingestion adapters. Every adapter declares a licence policy and is gated on it."""

from .base import RawNode, Source, SourceError, StaticSource
from .bundled import available, bundled_outline
from .scope_sequence import ScopeSequenceSource, course_metadata
from .wikidata import WikidataRoot, WikidataSource

__all__ = ['RawNode', 'Source', 'SourceError', 'StaticSource', 'ScopeSequenceSource',
           'course_metadata', 'WikidataSource', 'WikidataRoot', 'available', 'bundled_outline']
