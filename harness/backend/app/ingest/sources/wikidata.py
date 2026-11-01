"""Wikidata ingestion source (CC0).

Wikidata is the one large concept graph this project can ingest without a rights
problem: its data is dedicated to the public domain under CC0, which explicitly
permits reuse, redistribution and use for training machine-learning models.

What we take is *structure* - labels, one-line descriptions, aliases, and the
subclass/part-of/follows relations that let us derive a teaching order. We do not
take Wikipedia article prose.

The source is cache-first and can run fully offline (``offline=True``), so a pack
build is reproducible even without network access.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from ..policy import WIKIDATA, SourcePolicy
from .base import RawNode, SourceError

ENDPOINT = 'https://query.wikidata.org/sparql'
USER_AGENT = 'LuminfestLearningHarness/1.0 (curriculum structure ingest; CC0 Wikidata)'
DEFAULT_CACHE = Path(__file__).resolve().parent.parent / 'cache' / 'wikidata'

#: Wikidata properties we rely on.
P_SUBCLASS = 'P279'      # subclass of
P_PART_OF = 'P361'       # part of
P_FOLLOWS = 'P155'       # follows  (this concept comes after ...)
P_FOLLOWED_BY = 'P156'   # followed by (this concept comes before ...)
P_INSTANCE = 'P31'       # instance of


@dataclass
class WikidataRoot:
    """A branch of mathematics to pull concepts from."""

    qid: str
    label: str
    strand_hint: str = ''
    unit_hint: str = ''


class WikidataSource:
    """Fetch concept nodes and sequence edges from the Wikidata Query Service."""

    name = 'Wikidata'

    def __init__(self, roots: Sequence[WikidataRoot], *, cache_dir: Path | str | None = None,
                 offline: bool = False, limit_per_root: int = 400, timeout: float = 45.0,
                 language: str = 'en', min_interval: float = 1.0):
        self.roots = list(roots)
        self.cache_dir = Path(cache_dir) if cache_dir else DEFAULT_CACHE
        self.offline = offline
        self.limit_per_root = limit_per_root
        self.timeout = timeout
        self.language = language
        self.min_interval = min_interval
        self._last_request = 0.0
        self.cache_hits = 0
        self.network_calls = 0

    # ------------------------------------------------------------------ policy

    def policy(self) -> SourcePolicy:
        return WIKIDATA

    # ------------------------------------------------------------------ transport

    def _cache_path(self, query: str) -> Path:
        digest = hashlib.sha256(query.encode('utf-8')).hexdigest()[:24]
        return self.cache_dir / f'{digest}.json'

    def _run(self, query: str) -> list[dict[str, Any]]:
        """Run a SPARQL query, preferring the on-disk cache."""
        path = self._cache_path(query)
        if path.exists():
            self.cache_hits += 1
            return json.loads(path.read_text(encoding='utf-8'))['bindings']
        if self.offline:
            raise SourceError(
                f'Wikidata cache miss while offline. Missing query digest {path.stem}. '
                f'Run once with network access to populate {self.cache_dir}.')

        elapsed = time.monotonic() - self._last_request
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        request = urllib.request.Request(
            ENDPOINT,
            data=urllib.parse.urlencode({'query': query}).encode('utf-8'),
            headers={'Accept': 'application/sparql-results+json', 'User-Agent': USER_AGENT},
            method='POST')
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode('utf-8'))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            raise SourceError(f'Wikidata query failed: {exc}') from exc
        finally:
            self._last_request = time.monotonic()

        self.network_calls += 1
        bindings = payload.get('results', {}).get('bindings', [])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({'query': query, 'bindings': bindings}, indent=1), encoding='utf-8')
        return bindings

    # ------------------------------------------------------------------ queries

    def _concepts_query(self, root: WikidataRoot) -> str:
        return f'''SELECT DISTINCT ?item ?itemLabel ?itemDescription ?alias WHERE {{
  {{ ?item wdt:{P_SUBCLASS} wd:{root.qid} . }}
  UNION
  {{ ?item wdt:{P_PART_OF} wd:{root.qid} . }}
  UNION
  {{ ?item wdt:{P_INSTANCE} ?cls . ?cls wdt:{P_SUBCLASS} wd:{root.qid} . }}
  ?item rdfs:label ?itemLabel . FILTER(lang(?itemLabel) = "{self.language}")
  OPTIONAL {{ ?item schema:description ?itemDescription . FILTER(lang(?itemDescription) = "{self.language}") }}
  OPTIONAL {{ ?item skos:altLabel ?alias . FILTER(lang(?alias) = "{self.language}") }}
}} LIMIT {self.limit_per_root}'''

    def _sequence_query(self, qids: Sequence[str]) -> str:
        values = ' '.join(f'wd:{q}' for q in qids)
        return f'''SELECT ?item ?follows ?followedBy WHERE {{
  VALUES ?item {{ {values} }}
  OPTIONAL {{ ?item wdt:{P_FOLLOWS} ?follows . }}
  OPTIONAL {{ ?item wdt:{P_FOLLOWED_BY} ?followedBy . }}
}}'''

    def _search_query(self, title: str) -> str:
        escaped = title.replace('\\', '').replace('"', '')
        return f'''SELECT ?item ?itemLabel ?itemDescription WHERE {{
  ?item rdfs:label "{escaped}"@{self.language} .
  ?item wdt:{P_INSTANCE} ?cls .
  OPTIONAL {{ ?item schema:description ?itemDescription . FILTER(lang(?itemDescription) = "{self.language}") }}
  BIND("{escaped}" AS ?itemLabel)
}} LIMIT 5'''

    # ------------------------------------------------------------------ fetching

    @staticmethod
    def _qid(uri: str) -> str:
        return uri.rsplit('/', 1)[-1]

    def fetch(self) -> list[RawNode]:
        """Fetch concept nodes for every declared root."""
        nodes: list[RawNode] = []
        for root in self.roots:
            bindings = self._run(self._concepts_query(root))
            grouped: dict[str, RawNode] = {}
            for row in bindings:
                qid = self._qid(row['item']['value'])
                label = row.get('itemLabel', {}).get('value', '').strip()
                if not label or label.startswith('Q') and label[1:].isdigit():
                    continue
                node = grouped.get(qid)
                if node is None:
                    node = RawNode(
                        title=label,
                        order=len(nodes) + len(grouped),
                        strand_hint=root.strand_hint,
                        unit_hint=root.unit_hint,
                        summary=row.get('itemDescription', {}).get('value', '').strip(),
                        external_ids={'wikidata': qid},
                        ordered=True,
                        raw={'root': root.qid},
                    )
                    grouped[qid] = node
                alias = row.get('alias', {}).get('value', '').strip()
                if alias and alias != label and alias not in node.keywords:
                    node.keywords.append(alias)
            nodes.extend(grouped.values())
        return nodes

    def sequence_edges(self, qids: Sequence[str]) -> list[tuple[str, str]]:
        """Return ``(earlier, later)`` QID pairs asserted by follows/followed-by.

        Wikidata's ``follows`` means "this item comes after that one", so the
        edge points from the followed item to the following item.
        """
        if not qids:
            return []
        edges: set[tuple[str, str]] = set()
        batch = 180
        for start in range(0, len(qids), batch):
            bindings = self._run(self._sequence_query(qids[start:start + batch]))
            for row in bindings:
                item = self._qid(row['item']['value'])
                if 'follows' in row:
                    edges.add((self._qid(row['follows']['value']), item))
                if 'followedBy' in row:
                    edges.add((item, self._qid(row['followedBy']['value'])))
        return sorted(edges)

    def resolve_titles(self, titles: Iterable[str]) -> dict[str, dict[str, str]]:
        """Look up Wikidata identity for plain concept titles. Cache-friendly."""
        resolved: dict[str, dict[str, str]] = {}
        for title in titles:
            if not title.strip():
                continue
            try:
                bindings = self._run(self._search_query(title))
            except SourceError:
                continue
            for row in bindings:
                qid = self._qid(row['item']['value'])
                resolved[title] = {'wikidata': qid,
                                   'description': row.get('itemDescription', {}).get('value', '').strip()}
                break
        return resolved
