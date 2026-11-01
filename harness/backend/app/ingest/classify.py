"""Classification engine: raw source records -> a validated concept graph.

This is the part that makes large-scale ingestion tractable. Given hundreds of raw
concept records from any source, it:

1. normalises titles into stable ids and de-duplicates near-identical entries;
2. assigns strand / unit / topic, inferring them from rules when the source does
   not declare them;
3. derives prerequisite edges from three independent signals, in priority order -
   declared intent, in-sequence ordering, and keyword containment - refusing any
   edge that would introduce a cycle;
4. derives tier and a 1-5 difficulty from graph depth plus complexity markers;
5. reports what it did, including every edge it refused and why.

Every step is deterministic: the same input always produces a byte-identical pack.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from ..knowledge_graph import TIERS, ConceptNode, KnowledgeGraph, Taxonomy, slug
from .policy import SourcePolicy, provenance_for
from .sources.base import RawNode

#: Words that mark a concept as genuinely harder than its position alone suggests.
COMPLEXITY_MARKERS = (
    'quadratic', 'polynomial', 'rational', 'radical', 'exponential', 'logarithm',
    'system', 'inequalit', 'absolute', 'inverse', 'composition', 'function notation',
    'regression', 'inference', 'conditional probability', 'binomial', 'discriminant',
    'completing the square', 'asymptote', 'transformation', 'sequence', 'series',
)

#: Fallback strand inference when a source declares no strand.
STRAND_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ('Number & Quantity', ('fraction', 'integer', 'decimal', 'percent', 'ratio', 'proportion',
                           'exponent', 'radical', 'scientific notation', 'absolute value',
                           'order of operations', 'number line', 'signed number', 'unit rate',
                           'place value', 'factor', 'multiple', 'divisib')),
    ('Algebra', ('expression', 'equation', 'inequalit', 'polynomial', 'factor', 'quadratic',
                 'linear', 'slope', 'system', 'variable', 'distribut', 'like term',
                 'sequence', 'arithmetic sequence', 'exponent rule', 'binomial')),
    ('Functions', ('function', 'domain', 'range', 'intercept', 'graph', 'transform',
                   'notation', 'rate of change', 'piecewise', 'inverse', 'composition')),
    ('Geometry & Measurement', ('area', 'volume', 'perimeter', 'angle', 'triangle', 'circle',
                               'coordinate', 'distance', 'midpoint', 'similar', 'congruen',
                               'pythagorean', 'transform', 'parallel', 'perpendicular')),
    ('Statistics & Probability', ('mean', 'median', 'mode', 'spread', 'standard deviation',
                                  'quartile', 'box plot', 'histogram', 'scatter', 'correlation',
                                  'regression', 'sample', 'population', 'probability',
                                  'outcome', 'independent event', 'conditional', 'survey',
                                  'bias', 'distribution', 'data')),
)

#: Unit-level fallback names when a source declares none.
UNCLASSIFIED = 'Unclassified'

_WORD = re.compile(r"[a-z0-9]+")
#: Tokens too generic to establish a dependency on their own.
STOPWORDS = frozenset({
    'and', 'or', 'of', 'the', 'a', 'an', 'to', 'in', 'on', 'for', 'with', 'from', 'by',
    'introduction', 'intro', 'basic', 'basics', 'review', 'using', 'use', 'apply', 'applying',
    'solve', 'solving', 'write', 'writing', 'find', 'finding', 'understand', 'understanding',
    'explore', 'exploring', 'model', 'modeling', 'represent', 'representing', 'interpret',
    'interpreting', 'graph', 'graphing', 'i', 'ii', 'iii', 'part', 'unit', 'lesson',
})


def tokens(text: str) -> list[str]:
    """Content-bearing lowercase tokens of ``text``."""
    return [t for t in _WORD.findall(text.casefold()) if t not in STOPWORDS and len(t) > 2]


def stem(token: str) -> str:
    """Very small suffix stripper - enough to match 'fractions' to 'fraction'."""
    for suffix in ('ies', 'ing', 'ions', 'ion', 'es', 's'):
        if len(token) > len(suffix) + 3 and token.endswith(suffix):
            return token[:-len(suffix)]
    return token


@dataclass
class ClassificationRules:
    """Tunable knobs for the classifier. Kept explicit so behaviour is inspectable."""

    #: How to chain concepts inside a unit when the source declares no prerequisites.
    sequence_within: str = 'topic'          # 'topic' | 'unit' | 'none'
    #: Allow keyword-containment edges (a concept whose title contains another's term).
    #: OFF by default. Word overlap between two concept titles ("...solution method"
    #: and "sampling methods") is not evidence of a prerequisite relationship, and
    #: this project does not ship inferred structure it cannot defend. The rule is
    #: kept because it is useful for exploring a corpus you intend to review by hand.
    keyword_edges: bool = False
    #: Minimum shared stem length before a keyword edge is considered.
    min_stem_length: int = 6
    #: Words that never establish a dependency even when they appear in a title.
    keyword_blocklist: tuple[str, ...] = (
        'method', 'methods', 'problem', 'problems', 'example', 'examples', 'introduction',
        'application', 'applications', 'comparison', 'comparing', 'concept', 'concepts',
        'notation', 'vocabulary', 'review', 'practice', 'model', 'models', 'modelling',
        'modeling', 'context', 'contexts', 'word', 'words', 'basic', 'basics',
    )
    #: Fraction of the graph's maximum depth below which a concept is 'foundation'.
    #: Relative rather than absolute so the same rules work for 15 nodes or 5,000.
    foundation_fraction: float = 0.2
    #: Fraction of the maximum depth above which a concept is 'extension'.
    extension_fraction: float = 0.6
    #: Bridge units that declare unit-level prerequisites.
    unit_bridge: bool = True


@dataclass
class ClassificationReport:
    """Everything the classifier decided, so a human can audit it."""

    source_policies: list[dict[str, Any]] = field(default_factory=list)
    raw_records: int = 0
    concepts: int = 0
    duplicates_merged: list[dict[str, str]] = field(default_factory=list)
    edges_declared: int = 0
    edges_sequence: int = 0
    edges_keyword: int = 0
    edges_teaching_order: int = 0
    edges_refused: list[dict[str, str]] = field(default_factory=list)
    inferred_strands: int = 0
    inferred_units: int = 0
    cycles_avoided: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            'source_policies': self.source_policies,
            'raw_records': self.raw_records,
            'concepts': self.concepts,
            'duplicates_merged': self.duplicates_merged,
            'edges': {'declared': self.edges_declared, 'sequence': self.edges_sequence,
                      'keyword': self.edges_keyword, 'teaching_order': self.edges_teaching_order,
                      'refused': len(self.edges_refused)},
            'edges_refused': self.edges_refused,
            'inferred_strands': self.inferred_strands,
            'inferred_units': self.inferred_units,
            'cycles_avoided': self.cycles_avoided,
        }


class Classifier:
    """Turn raw records into a classified, cycle-free concept graph."""

    def __init__(self, taxonomy: Taxonomy | None = None,
                 rules: ClassificationRules | None = None):
        self.taxonomy = taxonomy or Taxonomy()
        self.rules = rules or ClassificationRules()

    # ------------------------------------------------------------------ normalise

    def _assign_strand(self, raw: RawNode) -> tuple[str, bool]:
        if raw.strand_hint:
            return raw.strand_hint, False
        haystack = ' '.join([raw.title, raw.topic_hint, raw.unit_hint, raw.summary,
                             ' '.join(raw.keywords)]).casefold()
        best, best_hits = '', 0
        for strand, markers in STRAND_RULES:
            hits = sum(1 for marker in markers if marker in haystack)
            if hits > best_hits:
                best, best_hits = strand, hits
        return (best or UNCLASSIFIED), bool(best)

    def normalise(self, records: Iterable[RawNode], policy: SourcePolicy,
                  report: ClassificationReport) -> list[ConceptNode]:
        """Convert raw records into de-duplicated :class:`ConceptNode` objects."""
        provenance = provenance_for(policy)
        by_id: dict[str, ConceptNode] = {}
        title_index: dict[str, str] = {}
        order: list[str] = []

        for raw in records:
            concept_id = slug(raw.title)
            existing_id = title_index.get(concept_id)
            if existing_id is not None:
                keeper = by_id[existing_id]
                self._absorb(keeper, raw)
                report.duplicates_merged.append({'kept': existing_id, 'merged': raw.title})
                continue

            strand, strand_inferred = self._assign_strand(raw)
            unit = raw.unit_hint or strand
            if not raw.unit_hint:
                report.inferred_units += 1
            if strand_inferred:
                report.inferred_strands += 1

            node = ConceptNode(
                id=concept_id,
                title=raw.title.strip(),
                strand=strand,
                unit=unit,
                topic=raw.topic_hint or unit,
                difficulty=3,
                keywords=sorted({*raw.keywords}),
                summary=raw.summary.strip(),
                external_ids=dict(raw.external_ids),
                provenance={**provenance, 'order': raw.order,
                            **({'declared_licence': policy.licence} if policy.needs_attribution else {})},
            )
            by_id[concept_id] = node
            title_index[concept_id] = concept_id
            order.append(concept_id)
            self.taxonomy.declare(strand, unit, [node.topic] if node.topic else [])

        # Preserve the source's own ordering for deterministic downstream passes.
        ordered = [by_id[cid] for cid in sorted(by_id, key=lambda c: (by_id[c].provenance.get('order', 0), c))]
        return ordered

    @staticmethod
    def _absorb(keeper: ConceptNode, raw: RawNode) -> None:
        """Merge a duplicate record into the concept already kept."""
        if len(raw.summary) > len(keeper.summary):
            keeper.summary = raw.summary.strip()
        keeper.keywords = sorted({*keeper.keywords, *raw.keywords})
        keeper.external_ids = {**raw.external_ids, **keeper.external_ids}
        for prerequisite in raw.prerequisites:
            if prerequisite not in keeper.prerequisites:
                keeper.prerequisites.append(prerequisite)

    # ------------------------------------------------------------------ edges

    def _resolve(self, reference: str, title_index: Mapping[str, str]) -> str | None:
        """Resolve a source's prerequisite reference (a title or id) to a concept id."""
        key = slug(reference)
        if key in title_index:
            return title_index[key]
        return None

    def build(self, records: Iterable[RawNode], policies: Sequence[SourcePolicy],
              *, pack_name: str = 'pack', pack_title: str = '') -> tuple[KnowledgeGraph, ClassificationReport]:
        """Run the whole pipeline over raw records and return the graph plus a report."""
        report = ClassificationReport(source_policies=[p.to_dict() for p in policies])
        records = list(records)
        report.raw_records = len(records)
        policy = policies[0] if policies else None
        if policy is None:
            raise ValueError('At least one source policy is required')

        nodes = self.normalise(records, policy, report)
        graph = KnowledgeGraph(self.taxonomy)
        graph.add_many(nodes)
        report.concepts = len(nodes)

        by_id = {n.id: n for n in nodes}
        title_index = {n.id: n.id for n in nodes}
        order_of = {n.id: n.provenance.get('order', 0) for n in nodes}
        raw_by_id: dict[str, RawNode] = {}
        for raw in records:
            raw_by_id.setdefault(slug(raw.title), raw)

        declared: list[tuple[str, str]] = []
        for node in nodes:
            raw = raw_by_id.get(node.id)
            if not raw:
                continue
            for reference in raw.prerequisites:
                source_id = self._resolve(reference, title_index)
                if source_id and source_id != node.id:
                    declared.append((source_id, node.id))
        declared = sorted(set(declared), key=lambda e: (order_of.get(e[1], 0), order_of.get(e[0], 0), e))

        sequence, teaching_order = (self._sequence_edges(nodes, raw_by_id, declared)
                                    if self.rules.sequence_within != 'none' else ([], []))
        keyword = self._keyword_edges(nodes, order_of) if self.rules.keyword_edges else []

        # Priority: declared intent beats structural inference, which beats keyword hints.
        for source_id, target_id in declared:
            if self._accept(graph, source_id, target_id, report):
                report.edges_declared += 1
        for source_id, target_id in sequence:
            if self._accept(graph, source_id, target_id, report):
                report.edges_sequence += 1
        for source_id, target_id in keyword:
            if self._accept(graph, source_id, target_id, report):
                report.edges_keyword += 1
        # Teaching order is added last and only ever as a soft edge, so it can never
        # be the thing that makes a hard prerequisite unsatisfiable.
        for source_id, target_id in teaching_order:
            if self._accept_sequence(graph, source_id, target_id, report):
                report.edges_teaching_order += 1

        self._assign_levels(graph)
        return graph, report

    def _sequence_edges(self, nodes: Sequence[ConceptNode], raw_by_id: Mapping[str, RawNode],
                        declared: Sequence[tuple[str, str]]
                        ) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
        """Derive the source's teaching order, split by relation strength.

        Returns ``(hard, sequence)``:

        * ``hard`` - concepts inside one topic chain to each other, because a topic
          is a tight conceptual group where each step genuinely rests on the last,
          plus the declared unit bridges;
        * ``sequence`` - the last concept of a topic precedes the first concept of
          the next topic in the same unit. This orders the course but does not gate
          it, so it is recorded as teaching order rather than as a prerequisite.

        With ``sequence_within='unit'`` the whole unit chains as teaching order.
        """
        hard: list[tuple[str, str]] = []
        soft: list[tuple[str, str]] = []
        by_unit: dict[str, list[ConceptNode]] = {}
        for node in nodes:
            by_unit.setdefault(node.unit, []).append(node)

        for members in by_unit.values():
            members.sort(key=lambda n: (n.provenance.get('order', 0), n.id))
            if self.rules.sequence_within == 'unit':
                soft.extend((a.id, b.id) for a, b in zip(members, members[1:]))
                continue

            topics: dict[str, list[ConceptNode]] = {}
            topic_order: list[str] = []
            for node in members:
                key = node.topic or node.unit
                if key not in topics:
                    topics[key] = []
                    topic_order.append(key)
                topics[key].append(node)
            for topic in topic_order:
                chain = topics[topic]
                hard.extend((a.id, b.id) for a, b in zip(chain, chain[1:]))
            for previous, following in zip(topic_order, topic_order[1:]):
                soft.append((topics[previous][-1].id, topics[following][0].id))

        if self.rules.unit_bridge:
            # Unit-level prerequisites declared on the source's unit blocks.
            unit_prereqs: dict[str, list[str]] = {}
            for raw in raw_by_id.values():
                for reference in (raw.raw or {}).get('unit_prerequisites', []) or []:
                    unit_prereqs.setdefault(raw.unit_hint, []).append(str(reference))
            last_in_unit: dict[str, str] = {}
            first_in_unit: dict[str, str] = {}
            for node in sorted(nodes, key=lambda n: (n.provenance.get('order', 0), n.id)):
                first_in_unit.setdefault(node.unit, node.id)
                last_in_unit[node.unit] = node.id
            for unit, references in unit_prereqs.items():
                for reference in references:
                    source_id = last_in_unit.get(reference)
                    target_id = first_in_unit.get(unit)
                    if source_id and target_id and source_id != target_id:
                        hard.append((source_id, target_id))
        return sorted(set(hard)), sorted(set(soft))

    def _keyword_edges(self, nodes: Sequence[ConceptNode],
                       order_of: Mapping[str, int]) -> list[tuple[str, str]]:
        """Link a concept to earlier concepts whose core term its title contains.

        Opt-in and deliberately narrow: blocklisted words are ignored, and a match
        is only accepted from a concept that appears earlier in the source order.
        """
        blocked = {stem(w) for w in self.rules.keyword_blocklist}
        index: dict[str, str] = {}
        for node in sorted(nodes, key=lambda n: (order_of.get(n.id, 0), n.id)):
            for term in tokens(node.title):
                root = stem(term)
                if len(root) >= self.rules.min_stem_length and root not in blocked:
                    index.setdefault(root, node.id)

        edges: set[tuple[str, str]] = set()
        for node in nodes:
            node_terms = {stem(t) for t in tokens(node.title)}
            node_terms |= {stem(t) for t in tokens(' '.join(node.keywords))}
            for term in sorted(node_terms):
                if len(term) < self.rules.min_stem_length or term in blocked:
                    continue
                candidate = index.get(term)
                if candidate and candidate != node.id and order_of.get(candidate, 0) < order_of.get(node.id, 0):
                    edges.add((candidate, node.id))
        return sorted(edges, key=lambda e: (order_of.get(e[1], 0), order_of.get(e[0], 0), e))

    def _accept(self, graph: KnowledgeGraph, source_id: str, target_id: str,
                report: ClassificationReport) -> bool:
        """Add a hard prerequisite edge unless it exists or would close a cycle."""
        if source_id == target_id or source_id not in graph.nodes or target_id not in graph.nodes:
            return False
        if source_id in graph.nodes[target_id].prerequisites:
            return False
        if self._reachable(graph, target_id, source_id):
            report.cycles_avoided += 1
            report.edges_refused.append({
                'edge': f'{source_id} -> {target_id}',
                'reason': f'{source_id} is already reachable from {target_id}; the edge would close a cycle',
            })
            return False
        graph.link(source_id, target_id)
        return True

    def _accept_sequence(self, graph: KnowledgeGraph, source_id: str, target_id: str,
                         report: ClassificationReport) -> bool:
        """Add a teaching-order edge unless it exists or would close a cycle."""
        if source_id == target_id or source_id not in graph.nodes or target_id not in graph.nodes:
            return False
        if source_id in graph.nodes[target_id].sequence_predecessors:
            return False
        if source_id in graph.nodes[target_id].prerequisites:
            return False  # already implied by a stronger relation
        if self._reachable(graph, target_id, source_id):
            report.cycles_avoided += 1
            report.edges_refused.append({
                'edge': f'{source_id} -> {target_id} (teaching order)',
                'reason': f'{source_id} is already reachable from {target_id}; the edge would close a cycle',
            })
            return False
        graph.link_sequence(source_id, target_id)
        return True

    @staticmethod
    def _reachable(graph: KnowledgeGraph, start: str, goal: str) -> bool:
        """Is ``goal`` reachable by walking prerequisites *and* teaching order forward from ``start``?"""
        seen = {start}
        queue = [start]
        while queue:
            current = queue.pop()
            if current == goal:
                return True
            for child in (*graph.children(current), *graph.sequence_children(current)):
                if child not in seen:
                    seen.add(child)
                    queue.append(child)
        return False

    # ------------------------------------------------------------------ levels

    def _assign_levels(self, graph: KnowledgeGraph) -> None:
        """Derive tier and difficulty from graph depth plus declared complexity.

        Thresholds are *relative* to the graph's own maximum depth. A fixed cutoff
        would label almost everything 'extension' in a 150-concept course while
        labelling almost nothing that way in a 15-concept sample, so the rule is
        expressed as a fraction of the depth range instead.
        """
        depths = graph.depths()
        deepest = max(depths.values()) if depths else 0
        foundation_cut = deepest * self.rules.foundation_fraction
        extension_cut = deepest * self.rules.extension_fraction

        for node in graph.nodes.values():
            depth = depths.get(node.id, 0)
            rank = (depth / deepest) if deepest else 0.0
            if depth <= foundation_cut:
                node.tier = 'foundation'
            elif depth >= extension_cut:
                node.tier = 'extension'
            else:
                node.tier = 'core'
            # Difficulty tracks position in the prerequisite chain, then earns one
            # extra point for concepts carrying genuinely demanding machinery. The
            # spread is relative so the histogram stays informative at any scale.
            base = 1 + round(3.0 * rank)
            haystack = f'{node.title} {" ".join(node.keywords)}'.casefold()
            if any(marker in haystack for marker in COMPLEXITY_MARKERS) and base < 5:
                base += 1
            node.difficulty = max(1, min(5, base))
            node.keywords = sorted(set(node.keywords))


def classify(records: Iterable[RawNode], policies: Sequence[SourcePolicy], *,
             taxonomy: Taxonomy | None = None, rules: ClassificationRules | None = None,
             pack_name: str = 'pack', pack_title: str = '') -> tuple[KnowledgeGraph, ClassificationReport]:
    """Convenience wrapper around :class:`Classifier`."""
    classifier = Classifier(taxonomy, rules)
    return classifier.build(records, policies, pack_name=pack_name, pack_title=pack_title)


__all__ = ['Classifier', 'ClassificationRules', 'ClassificationReport', 'classify',
           'tokens', 'stem', 'COMPLEXITY_MARKERS', 'STRAND_RULES', 'UNCLASSIFIED']
