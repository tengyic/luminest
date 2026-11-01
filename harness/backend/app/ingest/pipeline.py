"""Command-line orchestration for curriculum ingestion.

    python -m app.ingest.pipeline policy
    python -m app.ingest.pipeline build  --seed algebra_one_year --out pack.json
    python -m app.ingest.pipeline build  --outline my_course.json --out pack.json
    python -m app.ingest.pipeline enrich --pack pack.json --limit 40
    python -m app.ingest.pipeline verify --pack pack.json
    python -m app.ingest.pipeline textbook --concept equations

``build`` is offline and deterministic. ``enrich`` (CC0 Wikidata) and
``textbook`` (audited OpenStax books) are the only subcommands that may touch
the network, and each stays inside its own licence gate.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from ..knowledge_graph import KnowledgeGraph, Taxonomy
from .classify import ClassificationRules, Classifier
from .policy import WIKIDATA, registry
from .sources.base import RawNode, Source
from .sources.bundled import available, bundled_outline
from .sources.scope_sequence import ScopeSequenceSource, course_metadata
from .sources.wikidata import WikidataRoot, WikidataSource

#: Wikidata branches used for optional enrichment. Chosen because these are the
#: roots whose subclass/part-of hierarchies are actually populated.
ENRICHMENT_ROOTS = (
    WikidataRoot('Q395', 'mathematics'),
    WikidataRoot('Q3968', 'algebra'),
    WikidataRoot('Q12483', 'statistics'),
    WikidataRoot('Q8087', 'geometry'),
)


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, sort_keys=False, ensure_ascii=False) + '\n',
                    encoding='utf-8')


def _taxonomy_from_sources(sources: Sequence[Source]) -> Taxonomy:
    """Declare the strand/unit skeleton from the outline itself, in source order."""
    taxonomy = Taxonomy()
    for source in sources:
        document = getattr(source, 'document', None)
        if not isinstance(document, dict):
            continue
        for strand_block in document.get('strands') or []:
            strand = str(strand_block.get('strand') or 'Unclassified')
            for unit_block in strand_block.get('units') or []:
                unit = str(unit_block.get('unit') or 'Unclassified')
                topics = [str(t.get('topic') or '') for t in unit_block.get('topics') or []]
                taxonomy.declare(strand, unit, [t for t in topics if t])
    return taxonomy


def cmd_policy(_: argparse.Namespace) -> int:
    for entry in registry():
        flag = 'INGEST' if entry['ingestible'] else 'LINK-ONLY'
        print(f"[{flag:9}] {entry['name']}")
        print(f"            licence: {entry['licence']}")
        print(f"            scope:   {entry['scope']}")
    return 0


def _collect(sources: Sequence[Source]) -> list[RawNode]:
    records: list[RawNode] = []
    for source in sources:
        records.extend(source.fetch())
    return records


def cmd_build(args: argparse.Namespace) -> int:
    sources: list[Source] = []
    if args.seed:
        for name in args.seed:
            sources.append(bundled_outline(name))
    for outline in args.outline or []:
        sources.append(ScopeSequenceSource(outline))
    if not sources:
        print(f'Nothing to build. Use --seed (available: {", ".join(available()) or "none"}) '
              f'or --outline PATH.', file=sys.stderr)
        return 2

    taxonomy = _taxonomy_from_sources(sources)
    rules = ClassificationRules(sequence_within=args.sequence_within)
    classifier = Classifier(taxonomy, rules)
    records = _collect(sources)
    policies = [s.policy() for s in sources]
    graph, report = classifier.build(records, policies, pack_name=args.name, pack_title=args.title or args.name)

    errors = graph.errors()
    if errors:
        print('Graph is invalid; refusing to write a pack:', file=sys.stderr)
        for issue in errors[:12]:
            print(f'  - {issue.kind} [{issue.concept_id}] {issue.detail}', file=sys.stderr)
        return 1

    metadata = {'generated_by': 'app.ingest.pipeline', 'rules': vars(rules)}
    if len(sources) == 1 and isinstance(sources[0], ScopeSequenceSource):
        metadata.update(course_metadata(sources[0].document))

    pack = graph.to_pack(name=args.name, title=args.title or args.name, metadata=metadata)
    out = Path(args.out)
    _write(out, pack)
    if args.report:
        _write(Path(args.report), {**report.to_dict(), 'stats': graph.stats()})

    stats = graph.stats()
    print(f'Wrote {out} — {stats["concepts"]} concepts, {stats["edges"]} prerequisite edges, '
          f'{stats["sequence_edges"]} teaching-order edges, {stats["units"]} units, '
          f'max depth {stats["max_depth"]}')
    print(f'Edges: declared={report.edges_declared} structural={report.edges_sequence} '
          f'keyword={report.edges_keyword} teaching_order={report.edges_teaching_order} '
          f'refused={len(report.edges_refused)} (cycles avoided: {report.cycles_avoided})')
    return 0


def cmd_enrich(args: argparse.Namespace) -> int:
    pack_path = Path(args.pack)
    pack = json.loads(pack_path.read_text(encoding='utf-8'))
    graph = KnowledgeGraph.from_pack(pack)

    source = WikidataSource(ENRICHMENT_ROOTS, offline=args.offline,
                            limit_per_root=args.limit, min_interval=args.interval)
    try:
        records = source.fetch()
    except Exception as exc:  # noqa: BLE001 - surfaced to the operator verbatim
        print(f'Wikidata enrichment unavailable: {exc}', file=sys.stderr)
        return 1

    qid_to_title = {}
    for raw in records:
        qid = raw.external_ids.get('wikidata')
        if qid:
            qid_to_title[qid] = raw

    resolved = source.resolve_titles([n.title for n in graph.nodes.values()])
    matched = 0
    for node in graph.nodes.values():
        hit = resolved.get(node.title)
        if not hit:
            continue
        node.external_ids.update(hit)
        matched += 1

    pack['concepts'] = [graph.nodes[cid].to_dict() for cid in sorted(graph.nodes)]
    pack.setdefault('metadata', {})['wikidata_enrichment'] = {
        'endpoint': 'https://query.wikidata.org/sparql',
        'licence': WIKIDATA.licence,
        'records_fetched': len(records),
        'titles_matched': matched,
        'cache_hits': source.cache_hits,
        'network_calls': source.network_calls,
    }
    _write(pack_path, pack)
    print(f'Enriched {pack_path}: {matched}/{len(graph.nodes)} titles resolved to Wikidata QIDs '
          f'({source.cache_hits} cache hits, {source.network_calls} network calls).')
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    pack = json.loads(Path(args.pack).read_text(encoding='utf-8'))
    graph = KnowledgeGraph.from_pack(pack)
    stats = graph.stats()
    issues = graph.validate()
    print(json.dumps(stats, indent=1))
    if issues:
        print(f'{len(issues)} issue(s):')
        for issue in issues[:20]:
            print(f'  - {issue.severity}: {issue.kind} [{issue.concept_id}] {issue.detail}')
        return 1
    print('Graph is valid: acyclic, all prerequisites resolve, all concepts classified.')
    return 0


def cmd_textbook(args) -> int:
    """Fetch real OpenStax sections for the grounded textbook layer.

    This is the only command in this module besides ``enrich`` that touches the
    network, and it exists because nothing else does: ``ingest_section`` is the
    one place that fetches publisher prose, and before this command existed a
    caller had to drive it from a Python shell for the textbook quote callout in
    a lesson ever to appear. ``enrich`` reads CC0 Wikidata; this reads a book the
    project has already audited, so the two are gated separately.

    Every fetch still goes through ``openstax.ingest_section``, which owns the
    licence gate: an unaudited book is refused with zero requests, a licence that
    contradicts its audit is refused, and a network failure is stored as
    ``unavailable`` rather than invented. This command changes *whether the fetch
    is reachable*, never *what is allowed to be stored*.
    """
    from ..config import Settings
    from ..ingest.sources import openstax as openstax_textbook

    settings = Settings.from_env()
    mapped = openstax_textbook.SECTION_MAP
    if args.concept:
        if args.concept not in mapped:
            print(f'No mapped textbook section for {args.concept!r}.')
            print(f'Mapped concepts: {", ".join(sorted(mapped))}')
            return 1
        mapped = {args.concept: mapped[args.concept]}

    counts = {'ready': 0, 'withheld': 0, 'unavailable': 0}
    for concept, (book, page) in sorted(mapped.items()):
        record = openstax_textbook.ingest_section(settings, book, page)
        status = str(record.get('status') or '')
        counts[status if status in counts else 'unavailable'] += 1
        print(f'  [{status or "unknown"}] {concept} <- {book}/{page}')
        if status == 'withheld':
            print(f'      withheld: {str(record.get("withheld_reason") or "")[:200]}')
        elif status == 'unavailable':
            print(f'      unavailable: {str(record.get("unavailable_reason") or "")[:200]}')
        else:
            print(f'      {str(record.get("section_title") or "")[:90]} '
                  f'({str(record.get("licence_class") or "")})')

    posture = openstax_textbook.describe(settings)
    print(f'\nStored {posture["sections_stored"]} section(s), '
          f'{posture["sections_ready"]} ready; '
          f'audited books: {", ".join(posture["books_audited"])}.')
    print(f'this run: {counts["ready"]} fetched, {counts["withheld"]} withheld, '
          f'{counts["unavailable"]} unavailable.')
    return 0 if counts['ready'] else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='app.ingest.pipeline', description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)

    sub.add_parser('policy', help='print the source licence registry').set_defaults(func=cmd_policy)

    build = sub.add_parser('build', help='build a graph pack from course outlines')
    build.add_argument('--seed', action='append', default=[],
                       help=f'bundled outline name (available: {", ".join(available())})')
    build.add_argument('--outline', action='append', default=[],
                       help='path to a scope-and-sequence JSON file')
    build.add_argument('--out', default='pack.json', help='where to write the pack')
    build.add_argument('--report', default='', help='optional path for the classification report')
    build.add_argument('--name', default='course', help='pack name')
    build.add_argument('--title', default='', help='human-readable pack title')
    build.add_argument('--sequence-within', default='topic', choices=['topic', 'unit', 'none'])
    build.set_defaults(func=cmd_build)

    enrich = sub.add_parser('enrich', help='attach Wikidata QIDs to pack concepts (network)')
    enrich.add_argument('--pack', required=True)
    enrich.add_argument('--limit', type=int, default=200)
    enrich.add_argument('--interval', type=float, default=1.0, help='seconds between requests')
    enrich.add_argument('--offline', action='store_true', help='use the on-disk cache only')
    enrich.set_defaults(func=cmd_enrich)

    verify = sub.add_parser('verify', help='validate a pack and print its stats')
    verify.add_argument('--pack', required=True)
    verify.set_defaults(func=cmd_verify)

    textbook = sub.add_parser('textbook', help='fetch OpenStax sections for the grounded textbook layer (network)')
    textbook.add_argument('--concept', default='',
                          help='fetch only this mapped concept (default: every mapped concept)')
    textbook.set_defaults(func=cmd_textbook)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == '__main__':
    raise SystemExit(main())
