"""Scalable concept graph: nodes, prerequisite edges, taxonomy, validation and analytics.

This module is deliberately dependency-free and data-driven. It separates two layers
that were previously conflated in a single hand-written table:

* the **graph layer** (this module) holds *scale* - hundreds or thousands of concept
  nodes with strand/unit/topic classification and prerequisite edges;
* the **lesson layer** (``curriculum_packs/*.json`` -> ``CONCEPTS``/``QUESTIONS``)
  holds *depth* - the fully authored blocks, simulations, projects and question
  variants for the subset of nodes that have been written up.

They are joined by the concept id, and ``ConceptNode.has_lesson`` records whether the
deep layer exists for that node. A node without a lesson is a legitimate outline node:
it still participates in prerequisite reasoning, coverage accounting and
recommendation, it simply cannot yet serve a full lesson.

Nothing here copies text from an external curriculum. Nodes carry ``provenance``
metadata describing which source contributed them and under which licence.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

GRAPH_SCHEMA = 1

#: Ordered tiers. Order matters: ``foundation`` is assumed to precede ``core``.
TIERS = ('foundation', 'core', 'extension')

_SLUG_STRIP = re.compile(r'[^a-z0-9]+')


def slug(text: str) -> str:
    """Return a stable, ASCII, lowercase identifier fragment for ``text``."""
    normalised = unicodedata.normalize('NFKD', text)
    ascii_only = normalised.encode('ascii', 'ignore').decode('ascii').casefold()
    collapsed = _SLUG_STRIP.sub('_', ascii_only).strip('_')
    return collapsed or 'unnamed'


def _coerce_id_list(value: Any) -> list[str]:
    """Coerce an incoming id/keyword field into a clean ``list[str]``.

    A well-formed pack always carries a list. A malformed one can carry a bare
    string, and iterating that would explode one reference into one entry per
    character (``'oops'`` -> ``['o', 'o', 'p', 's']``) - a corrupt node that
    still passes validation as four unknown-prerequisite errors far from the
    cause. A bare string is therefore taken as a single reference.
    """
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [str(item) for item in value or []]


@dataclass
class ConceptNode:
    """A single concept in the knowledge graph.

    Two relations are tracked separately, because conflating them over-claims:

    ``prerequisites``
        A genuine dependency. You cannot sensibly attempt this concept without the
        listed ones. Used for gating, for depth and for prerequisite closure.

    ``sequence_predecessors``
        Teaching order only. The source puts this concept after those, but the
        dependency is not hard - a strong learner could skip ahead. Used to order
        recommendations and to lay out a course, never to gate.
    """

    id: str
    title: str
    strand: str
    unit: str
    topic: str = ''
    tier: str = 'core'
    difficulty: int = 3
    prerequisites: list[str] = field(default_factory=list)
    sequence_predecessors: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    summary: str = ''
    #: True when a fully authored lesson exists for this node (see ``lesson_id``).
    has_lesson: bool = False
    #: Identifier of the authored lesson in the lesson layer, when one exists.
    lesson_id: str = ''
    external_ids: dict[str, str] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> 'ConceptNode':
        known = {f for f in cls.__dataclass_fields__}
        payload = {k: v for k, v in raw.items() if k in known}
        payload['id'] = str(payload.get('id') or slug(str(payload.get('title', ''))))
        payload.setdefault('title', payload['id'])
        payload.setdefault('strand', 'Unclassified')
        payload.setdefault('unit', 'Unclassified')
        payload['prerequisites'] = _coerce_id_list(payload.get('prerequisites'))
        payload['sequence_predecessors'] = _coerce_id_list(payload.get('sequence_predecessors'))
        payload['keywords'] = _coerce_id_list(payload.get('keywords'))
        try:
            payload['difficulty'] = int(payload.get('difficulty', 3))
        except (TypeError, ValueError):
            payload['difficulty'] = 3
        return cls(**payload)


@dataclass
class Issue:
    """A structural problem found while validating a graph."""

    kind: str
    concept_id: str
    detail: str
    severity: str = 'error'

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class Taxonomy:
    """strand -> unit -> ordered topics. Purely descriptive; drives navigation and reporting."""

    def __init__(self, strands: Mapping[str, Mapping[str, Sequence[str]]] | None = None):
        self.strands: dict[str, dict[str, list[str]]] = {}
        for strand, units in (strands or {}).items():
            self.strands[str(strand)] = {str(u): [str(t) for t in topics] for u, topics in units.items()}

    def declare(self, strand: str, unit: str, topics: Iterable[str] = ()) -> None:
        units = self.strands.setdefault(strand, {})
        bucket = units.setdefault(unit, [])
        for topic in topics:
            if topic not in bucket:
                bucket.append(str(topic))

    def units(self, strand: str | None = None) -> list[str]:
        if strand is None:
            seen: list[str] = []
            for units in self.strands.values():
                for unit in units:
                    if unit not in seen:
                        seen.append(unit)
            return seen
        return list(self.strands.get(strand, {}))

    def topics(self, strand: str, unit: str) -> list[str]:
        return list(self.strands.get(strand, {}).get(unit, []))

    def has(self, strand: str, unit: str) -> bool:
        return unit in self.strands.get(strand, {})

    def to_dict(self) -> dict[str, Any]:
        return {'strands': self.strands,
                'order': [{'strand': s, 'units': list(u)} for s, u in self.strands.items()]}

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any] | None) -> 'Taxonomy':
        return cls((raw or {}).get('strands') or {})


class KnowledgeGraph:
    """A validated directed acyclic concept graph.

    Edges always point *forward in learning order*: ``prerequisite -> concept``.
    """

    def __init__(self, taxonomy: Taxonomy | None = None):
        self.nodes: dict[str, ConceptNode] = {}
        self.taxonomy = taxonomy or Taxonomy()
        self._issues: list[Issue] = []

    # ------------------------------------------------------------------ building

    def add(self, node: ConceptNode, *, replace: bool = False) -> ConceptNode:
        if node.id in self.nodes and not replace:
            raise ValueError(f'Duplicate concept id: {node.id}')
        self.nodes[node.id] = node
        self.taxonomy.declare(node.strand, node.unit, [node.topic] if node.topic else [])
        return node

    def add_many(self, nodes: Iterable[ConceptNode], *, replace: bool = False) -> None:
        for node in nodes:
            self.add(node, replace=replace)

    def link(self, prerequisite: str, concept: str) -> None:
        """Declare that ``prerequisite`` must be learned before ``concept``."""
        node = self.nodes[concept]
        if prerequisite not in node.prerequisites:
            node.prerequisites.append(prerequisite)

    def link_sequence(self, predecessor: str, concept: str) -> None:
        """Declare that the source teaches ``concept`` after ``predecessor``.

        Softer than :meth:`link`: it orders the course but does not gate progress.
        """
        node = self.nodes[concept]
        if predecessor not in node.sequence_predecessors:
            node.sequence_predecessors.append(predecessor)

    def merge(self, other: 'KnowledgeGraph', *, replace: bool = False) -> None:
        for node in other.nodes.values():
            self.add(ConceptNode.from_dict(node.to_dict()), replace=replace)
        for strand, units in other.taxonomy.strands.items():
            for unit, topics in units.items():
                self.taxonomy.declare(strand, unit, topics)

    def __len__(self) -> int:
        return len(self.nodes)

    def __contains__(self, concept_id: object) -> bool:
        return concept_id in self.nodes

    def __iter__(self) -> Iterator[ConceptNode]:
        return iter(self.nodes.values())

    # ------------------------------------------------------------------ edges

    @property
    def edges(self) -> list[tuple[str, str]]:
        """Hard prerequisite edges as ``(prerequisite, concept)`` pairs, deterministically ordered."""
        pairs = {(p, n.id) for n in self.nodes.values() for p in n.prerequisites}
        return sorted(pairs)

    @property
    def sequence_edges(self) -> list[tuple[str, str]]:
        """Teaching-order edges as ``(earlier, later)`` pairs."""
        pairs = {(p, n.id) for n in self.nodes.values() for p in n.sequence_predecessors}
        return sorted(pairs)

    def parents(self, concept_id: str) -> list[str]:
        """Direct hard prerequisites of ``concept_id`` that exist in the graph."""
        return [p for p in self.nodes[concept_id].prerequisites if p in self.nodes]

    def all_parents(self, concept_id: str) -> list[str]:
        """Direct prerequisites and teaching-order predecessors, combined.

        A node can be named in both lists (a hard dependency that is also the
        source's teaching order), so the union is de-duplicated in place: hard
        prerequisites first, then teaching-order predecessors not already named.
        Callers feed this straight into learner-facing artefacts (explanation
        bullets, tutor context), where the same concept twice reads as a mistake.
        """
        node = self.nodes[concept_id]
        seen: list[str] = []
        for parent in (*node.prerequisites, *node.sequence_predecessors):
            if parent in self.nodes and parent not in seen:
                seen.append(parent)
        return seen

    def children(self, concept_id: str) -> list[str]:
        """Direct dependants: concepts that list ``concept_id`` as a hard prerequisite."""
        return sorted(n.id for n in self.nodes.values() if concept_id in n.prerequisites)

    def sequence_children(self, concept_id: str) -> list[str]:
        """Concepts the source teaches directly after ``concept_id``."""
        return sorted(n.id for n in self.nodes.values()
                      if concept_id in n.sequence_predecessors)

    def ancestors(self, concept_id: str) -> list[str]:
        """Every prerequisite reachable backwards from ``concept_id`` (excluding itself)."""
        seen: set[str] = set()
        queue = deque(self.parents(concept_id))
        while queue:
            current = queue.popleft()
            if current in seen:
                continue
            seen.add(current)
            queue.extend(self.parents(current))
        return sorted(seen)

    def descendants(self, concept_id: str) -> list[str]:
        """Every concept that transitively depends on ``concept_id`` (excluding itself)."""
        seen: set[str] = set()
        queue = deque(self.children(concept_id))
        while queue:
            current = queue.popleft()
            if current in seen:
                continue
            seen.add(current)
            queue.extend(self.children(current))
        return sorted(seen)

    def prerequisite_closure(self, concept_id: str) -> list[str]:
        """Alias of :meth:`ancestors`, named for the learning-science framing."""
        return self.ancestors(concept_id)

    # ------------------------------------------------------------------ validation

    def validate(self) -> list[Issue]:
        """Return every structural issue. Errors mean the graph must not be shipped."""
        issues: list[Issue] = []
        for node in self.nodes.values():
            if not node.title.strip():
                issues.append(Issue('empty_title', node.id, 'Concept has no title'))
            if node.tier not in TIERS:
                issues.append(Issue('invalid_tier', node.id, f'tier {node.tier!r} not in {TIERS}', 'warning'))
            if not 1 <= node.difficulty <= 5:
                issues.append(Issue('invalid_difficulty', node.id,
                                    f'difficulty {node.difficulty} outside 1..5', 'warning'))
            for prerequisite in node.prerequisites:
                if prerequisite == node.id:
                    issues.append(Issue('self_loop', node.id, 'Concept lists itself as a prerequisite'))
                elif prerequisite not in self.nodes:
                    issues.append(Issue('unknown_prerequisite', node.id,
                                        f'prerequisite {prerequisite!r} is not a known concept'))
            for predecessor in node.sequence_predecessors:
                if predecessor == node.id:
                    issues.append(Issue('self_loop', node.id, 'Concept lists itself as a sequence predecessor'))
                elif predecessor not in self.nodes:
                    issues.append(Issue('unknown_sequence_predecessor', node.id,
                                        f'sequence predecessor {predecessor!r} is not a known concept'))
        issues.extend(Issue('cycle', node_id, detail) for node_id, detail in self._cycles())
        issues.extend(Issue('sequence_cycle', node_id, detail)
                      for node_id, detail in self._cycles(include_sequence=True, skip_existing=True))
        return issues

    def errors(self) -> list[Issue]:
        return [i for i in self.validate() if i.severity == 'error']

    def _cycles(self, include_sequence: bool = False, skip_existing: bool = False) -> list[tuple[str, str]]:
        """Find cycles, reporting the concrete path for each one.

        With ``include_sequence`` the teaching-order relation is walked as well, which
        catches a course whose ordering contradicts its own prerequisites.
        """
        neighbours = (lambda cid: self.all_parents(cid)) if include_sequence else (lambda cid: self.parents(cid))
        already = {frozenset(loop.split(' -> ')[:-1]) for _, loop in self._cycles()} if skip_existing else set()
        WHITE, GREY, BLACK = 0, 1, 2
        colour = {cid: WHITE for cid in self.nodes}
        found: list[tuple[str, str]] = []
        reported: set[frozenset[str]] = set()

        for start in sorted(self.nodes):
            if colour[start] != WHITE:
                continue
            stack: list[str] = [start]
            path: list[str] = []
            while stack:
                current = stack[-1]
                if colour[current] == WHITE:
                    colour[current] = GREY
                    path.append(current)
                advanced = False
                for parent in neighbours(current):
                    if colour[parent] == GREY:
                        loop = path[path.index(parent):] + [parent]
                        key = frozenset(loop)
                        if key not in reported and key not in already:
                            reported.add(key)
                            found.append((loop[0], ' -> '.join(loop)))
                    elif colour[parent] == WHITE:
                        stack.append(parent)
                        advanced = True
                        break
                if not advanced:
                    stack.pop()
                    colour[current] = BLACK
                    if path and path[-1] == current:
                        path.pop()
        return sorted(found)

    def raise_if_invalid(self) -> None:
        errors = self.errors()
        if errors:
            summary = '; '.join(f'{i.kind}({i.concept_id}): {i.detail}' for i in errors[:6])
            raise ValueError(f'Knowledge graph is invalid: {summary}')

    # ------------------------------------------------------------------ structure

    def roots(self) -> list[str]:
        """Concepts with no in-graph prerequisite."""
        return sorted(cid for cid in self.nodes if not self.parents(cid))

    def leaves(self) -> list[str]:
        return sorted(cid for cid in self.nodes if not self.children(cid))

    def topological_order(self) -> list[str]:
        """Deterministic Kahn topological order over prerequisite edges.

        Ties are broken by concept id so that two runs over the same graph always
        produce byte-identical output - required for reproducible pack generation.
        """
        indegree = {cid: len(self.parents(cid)) for cid in self.nodes}
        ready = sorted(cid for cid, degree in indegree.items() if degree == 0)
        order: list[str] = []
        while ready:
            current = ready.pop(0)
            order.append(current)
            for child in self.children(current):
                indegree[child] -= 1
                if indegree[child] == 0:
                    ready.append(child)
                    ready.sort()
        if len(order) != len(self.nodes):
            raise ValueError('Knowledge graph contains a cycle; no topological order exists')
        return order

    def depths(self) -> dict[str, int]:
        """Longest prerequisite chain length reaching each concept (roots are 0)."""
        depth = {cid: 0 for cid in self.nodes}
        for cid in self.topological_order():
            for child in self.children(cid):
                depth[child] = max(depth[child], depth[cid] + 1)
        return depth

    def subgraph(self, concept_ids: Iterable[str], radius: int = 0) -> set[str]:
        """``concept_ids`` plus every node within ``radius`` prerequisite edges either way."""
        selected = {cid for cid in concept_ids if cid in self.nodes}
        frontier = set(selected)
        for _ in range(max(0, radius)):
            grown: set[str] = set()
            for cid in frontier:
                grown.update(self.parents(cid))
                grown.update(self.children(cid))
            grown -= selected
            selected |= grown
            frontier = grown
        return selected

    # ------------------------------------------------------------------ queries

    def strands(self) -> list[str]:
        return list(self.taxonomy.strands) or sorted({n.strand for n in self.nodes.values()})

    def units(self, strand: str | None = None) -> list[str]:
        declared = self.taxonomy.units(strand)
        present = {n.unit for n in self.nodes.values() if strand is None or n.strand == strand}
        ordered = [u for u in declared if u in present]
        return ordered + sorted(present - set(ordered))

    def in_unit(self, unit: str, strand: str | None = None) -> list[ConceptNode]:
        depth = self.depths()
        members = [n for n in self.nodes.values()
                   if n.unit == unit and (strand is None or n.strand == strand)]
        return sorted(members, key=lambda n: (depth.get(n.id, 0), n.id))

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Deterministic relevance search across title, keywords, topic and id."""
        needle = query.strip().casefold()
        if not needle:
            return []
        scored: list[tuple[int, str, ConceptNode]] = []
        for node in self.nodes.values():
            title = node.title.casefold()
            score = 0
            if node.id == needle:
                score = 100
            elif title == needle:
                score = 90
            elif title.startswith(needle):
                score = 70
            elif needle in title:
                score = 55
            elif any(needle in k.casefold() for k in node.keywords):
                score = 40
            elif needle in node.topic.casefold():
                score = 25
            elif needle in node.summary.casefold():
                score = 15
            if score:
                scored.append((score, node.id, node))
        scored.sort(key=lambda row: (-row[0], row[1]))
        return [{'id': n.id, 'title': n.title, 'strand': n.strand, 'unit': n.unit,
                 'topic': n.topic, 'tier': n.tier, 'difficulty': n.difficulty,
                 'has_lesson': n.has_lesson, 'score': s} for s, _, n in scored[:limit]]

    def classify(self, node: ConceptNode) -> dict[str, Any]:
        """Report how ``node`` sits in the taxonomy, and flag anything unclassified."""
        notes: list[str] = []
        if not self.taxonomy.has(node.strand, node.unit):
            notes.append('unit is not declared in the taxonomy')
        if node.topic and node.topic not in self.taxonomy.topics(node.strand, node.unit):
            notes.append('topic is not declared in the taxonomy')
        depth = self.depths().get(node.id, 0)
        return {'id': node.id, 'strand': node.strand, 'unit': node.unit, 'topic': node.topic,
                'tier': node.tier, 'difficulty': node.difficulty, 'depth': depth,
                'prerequisite_count': len(self.parents(node.id)),
                'dependant_count': len(self.children(node.id)),
                'notes': notes}

    # ------------------------------------------------------------------ analytics

    def stats(self) -> dict[str, Any]:
        depths = self.depths() if self.nodes else {}
        edges = self.edges
        sequence = self.sequence_edges
        by_strand: dict[str, int] = defaultdict(int)
        by_unit: dict[str, int] = defaultdict(int)
        by_tier: dict[str, int] = defaultdict(int)
        for node in self.nodes.values():
            by_strand[node.strand] += 1
            by_unit[node.unit] += 1
            by_tier[node.tier] += 1
        total = len(self.nodes)
        return {
            'concepts': total,
            'edges': len(edges),
            'sequence_edges': len(sequence),
            'strands': len({n.strand for n in self.nodes.values()}),
            'units': len({n.unit for n in self.nodes.values()}),
            'topics': len({(n.unit, n.topic) for n in self.nodes.values() if n.topic}),
            'roots': len(self.roots()),
            'leaves': len(self.leaves()),
            'max_depth': max(depths.values()) if depths else 0,
            'mean_prerequisites': round(sum(len(self.parents(c)) for c in self.nodes) / total, 3) if total else 0.0,
            'with_lesson': sum(1 for n in self.nodes.values() if n.has_lesson),
            'outline_only': sum(1 for n in self.nodes.values() if not n.has_lesson),
            'by_strand': dict(sorted(by_strand.items())),
            'by_unit': dict(sorted(by_unit.items())),
            'by_tier': dict(sorted(by_tier.items())),
            'difficulty_histogram': {str(d): sum(1 for n in self.nodes.values() if n.difficulty == d)
                                     for d in range(1, 6)},
            'density': round(len(edges) / (total * (total - 1)) if total > 1 else 0.0, 5),
        }

    def coverage(self, states: Mapping[str, Mapping[str, Any]], threshold: float = 0.6) -> dict[str, Any]:
        """Report per-strand and per-unit coverage against learner evidence."""
        mastered = {cid for cid, s in states.items() if s.get('mastery', 0.0) >= threshold}
        per_unit: dict[str, dict[str, Any]] = {}
        for unit in self.units():
            members = [n.id for n in self.in_unit(unit)]
            if not members:
                continue
            done = [cid for cid in members if cid in mastered]
            per_unit[unit] = {'total': len(members), 'mastered': len(done),
                              'ratio': round(len(done) / len(members), 3)}
        ready = []
        for node in self.nodes.values():
            if node.id in mastered:
                continue
            if all(p in mastered for p in self.parents(node.id)):
                ready.append(node.id)
        return {'threshold': threshold, 'mastered': len(mastered & set(self.nodes)),
                'total': len(self.nodes), 'units': per_unit, 'ready': sorted(ready)[:50]}

    def classification_report(self) -> dict[str, Any]:
        """Audit how well the graph is classified - used by the ingestion pipeline."""
        notes: list[dict[str, str]] = []
        for node in self.nodes.values():
            for note in self.classify(node)['notes']:
                notes.append({'id': node.id, 'note': note})
        return {'concepts': len(self.nodes), 'issues': self.validate(),
                'classification_notes': notes,
                'unclassified_units': sorted({n.unit for n in self.nodes.values()
                                              if not self.taxonomy.has(n.strand, n.unit)})}

    # ------------------------------------------------------------------ serialisation

    def to_pack(self, *, name: str, title: str = '', metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return {'schema': GRAPH_SCHEMA, 'name': name, 'title': title or name,
                'metadata': dict(metadata or {}), 'taxonomy': self.taxonomy.to_dict(),
                'concepts': [self.nodes[cid].to_dict() for cid in sorted(self.nodes)]}

    @classmethod
    def from_pack(cls, pack: Mapping[str, Any]) -> 'KnowledgeGraph':
        graph = cls(Taxonomy.from_dict(pack.get('taxonomy')))
        for raw in pack.get('concepts') or []:
            graph.add(ConceptNode.from_dict(raw))
        return graph

    def to_payload(self, *, include_edges: bool = True) -> dict[str, Any]:
        """The shape served over HTTP to the native client."""
        depths = self.depths() if self.nodes else {}
        nodes = []
        for cid in self.topological_order() if self.nodes else []:
            node = self.nodes[cid]
            nodes.append({**node.to_dict(), 'depth': depths.get(cid, 0),
                          'dependant_count': len(self.children(cid))})
        payload: dict[str, Any] = {'schema': GRAPH_SCHEMA, 'taxonomy': self.taxonomy.to_dict(),
                                   'stats': self.stats(), 'nodes': nodes}
        if include_edges:
            payload['edges'] = [{'from': a, 'to': b, 'kind': 'prerequisite'} for a, b in self.edges]
            payload['edges'] += [{'from': a, 'to': b, 'kind': 'sequence'} for a, b in self.sequence_edges]
        return payload


def load_pack(path: str | Path) -> tuple[KnowledgeGraph, dict[str, Any]]:
    """Load a graph pack from disk, returning the graph and its raw metadata."""
    raw = json.loads(Path(path).read_text(encoding='utf-8'))
    return KnowledgeGraph.from_pack(raw), raw


def combine(graphs: Iterable[KnowledgeGraph], *, taxonomy: Taxonomy | None = None) -> KnowledgeGraph:
    """Merge several packs into one graph. Later packs replace earlier duplicate ids."""
    merged = KnowledgeGraph(taxonomy)
    for graph in graphs:
        merged.merge(graph, replace=True)
    return merged
