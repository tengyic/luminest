"""Ingest an operator-supplied course outline.

This is the general-purpose path for *any* course: point the harness at a JSON
scope-and-sequence file and it becomes a classified knowledge graph. The file must
declare its own licence, and that licence must be cleared for ingestion - the
policy gate is not bypassable.

Outline format::

    {
      "course": "Algebra I (one year)",
      "licence": "cc0",
      "source_url": "https://example.org/algebra-one",
      "attribution": "Example Board of Education",
      "strands": [
        {"strand": "Number & Quantity",
         "units": [
           {"unit": "Number foundations",
            "topics": [
              {"topic": "Fractions",
               "concepts": [
                 {"title": "Equivalent fractions",
                  "summary": "...",
                  "keywords": ["common denominator"],
                  "prerequisites": ["Place value"]}
               ]}
            ]}
         ]}
      ]
    }

Only titles, ordering and prerequisite *intent* are read. Any prose a file happens
to contain is discarded unless the licence permits reuse.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from ..policy import IngestionRefused, LicenceClass, SourcePolicy, assert_ingestible
from .base import RawNode, SourceError

_LICENCE_ALIASES = {
    'public_domain': LicenceClass.PUBLIC_DOMAIN,
    'public domain': LicenceClass.PUBLIC_DOMAIN,
    'cc0': LicenceClass.CC0,
    'cc-0': LicenceClass.CC0,
    'cc_by': LicenceClass.CC_BY,
    'cc-by': LicenceClass.CC_BY,
    'cc_by_sa': LicenceClass.CC_BY_SA,
    'cc-by-sa': LicenceClass.CC_BY_SA,
    'link_only': LicenceClass.LINK_ONLY,
    'prohibited': LicenceClass.PROHIBITED,
}


def _licence_class(raw: str) -> LicenceClass:
    key = (raw or '').strip().casefold()
    if key in _LICENCE_ALIASES:
        return _LICENCE_ALIASES[key]
    raise SourceError(f'Unknown licence declaration {raw!r} in scope-and-sequence file')


class ScopeSequenceSource:
    """Load a declared, licence-cleared course outline into raw concept records."""

    def __init__(self, path: str | Path, *, name: str | None = None):
        self.path = Path(path)
        if not self.path.exists():
            raise SourceError(f'Scope-and-sequence file not found: {self.path}')
        self.document: dict[str, Any] = json.loads(self.path.read_text(encoding='utf-8'))
        self.name = name or str(self.document.get('course') or self.path.stem)
        licence_raw = str(self.document.get('licence') or '')
        if not licence_raw:
            raise SourceError(f'{self.path.name} does not declare a licence; refusing to ingest')
        self._policy = SourcePolicy(
            name=self.name,
            url=str(self.document.get('source_url') or ''),
            licence=licence_raw,
            licence_class=_licence_class(licence_raw),
            scope=str(self.document.get('scope') or
                      'Course outline structure only (titles, unit order, prerequisite intent).'),
            attribution=str(self.document.get('attribution') or ''),
            evidence_id=str(self.document.get('evidence_id') or ''),
        )
        assert_ingestible(self._policy)

    def policy(self) -> SourcePolicy:
        return self._policy

    def fetch(self) -> list[RawNode]:
        nodes: list[RawNode] = []
        order = 0
        for strand_block in self.document.get('strands') or []:
            strand = str(strand_block.get('strand') or 'Unclassified')
            for unit_block in strand_block.get('units') or []:
                unit = str(unit_block.get('unit') or 'Unclassified')
                # Unit-level prerequisites are bridged by the classifier: the last concept
                # of each named unit becomes a prerequisite of this unit's first concept.
                unit_prerequisites = [str(u) for u in unit_block.get('prerequisites') or []]
                for topic_block in unit_block.get('topics') or []:
                    topic = str(topic_block.get('topic') or '')
                    for concept in topic_block.get('concepts') or []:
                        title = str(concept.get('title') or '').strip()
                        if not title:
                            continue
                        order += 1
                        nodes.append(RawNode(
                            title=title,
                            order=order,
                            strand_hint=strand,
                            unit_hint=unit,
                            topic_hint=topic,
                            summary=str(concept.get('summary') or ''),
                            keywords=[str(k) for k in concept.get('keywords') or []],
                            prerequisites=[str(p) for p in concept.get('prerequisites') or []],
                            external_ids=dict(concept.get('external_ids') or {}),
                            ordered=True,
                            raw={'source': self.name, 'declared': True,
                                 'unit_prerequisites': unit_prerequisites},
                        ))
        if not nodes:
            raise SourceError(f'{self.path.name} produced no concepts')
        return nodes


def course_metadata(document: Mapping[str, Any]) -> dict[str, Any]:
    """Pull the human-facing course metadata out of an outline document."""
    keys = ('course', 'licence', 'source_url', 'attribution', 'scope', 'description', 'evidence_id')
    return {k: document[k] for k in keys if k in document}


__all__ = ['ScopeSequenceSource', 'course_metadata', 'IngestionRefused']
