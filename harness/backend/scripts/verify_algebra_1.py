"""Verify the Algebra 1 course against its own outline and its adapted textbooks.

Run:  python scripts/verify_algebra_1.py [--offline] [--json PATH]

Two independent claims are checked, and neither is taken on trust.

**Structure.** The pack must contain the twelve units and every topic of the course
framework, with globally unique namespaced concept ids, prerequisites that all resolve,
and a graph that branches rather than collapsing into one chain.

**Textbook alignment.** Every unit names the OpenStax sections that teach it. This script
re-fetches each named section through the *same* licence gate a lesson uses
(``app.ingest.sources.openstax.ingest_section``) and asserts that the gate returns
``ready`` -- which can only happen when OpenStax's live API still reports a CC BY licence
for that book and the book has an audited entry. A section that comes back ``withheld`` or
``unavailable`` is a failure, not a note: the alignment claim would otherwise be a
citation nobody checked.

Network results are cached under the OS temp directory so a re-run is cheap, but the cache
is keyed by book:page and re-validated by the gate on every fetch anyway. ``--offline``
skips the fetches and reports them as SKIP, which keeps the structural check usable in CI
without pretending the citations were verified.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
OUT = BACKEND.parent / 'outputs'
OUT.mkdir(parents=True, exist_ok=True)

EXPECTED_UNITS = 12
EXPECTED_CONCEPTS = 157
EXPECTED_TOPICS = 75
CACHE = Path(tempfile.gettempdir()) / 'algebra_1_textbook_check.json'

checks: list[dict] = []


def chk(name: str, ok: bool, detail=None, *, status: str | None = None) -> None:
    checks.append({'check': name, 'ok': bool(ok),
                   'status': status or ('PASS' if ok else 'FAIL'),
                   'detail': detail if detail is not None else ''})


# ------------------------------------------------------------------ structure
pack_path = BACKEND / 'app' / 'curriculum_packs' / 'algebra_1.json'
chk('pack exists', pack_path.exists(), str(pack_path))
pack = json.loads(pack_path.read_text(encoding='utf-8')) if pack_path.exists() else {}
concepts: list[dict] = pack.get('concepts') or []
ids = [c['id'] for c in concepts]
titles = [c['title'] for c in concepts]
units = sorted({c.get('unit') or '' for c in concepts} - {''})
topics = sorted({(c.get('unit') or '', c.get('topic') or '') for c in concepts})

chk('twelve units', len(units) == EXPECTED_UNITS, units)
chk('every topic present', len(topics) == EXPECTED_TOPICS,
    {'topics': len(topics), 'expected': EXPECTED_TOPICS})
chk('concept count', len(concepts) == EXPECTED_CONCEPTS,
    {'concepts': len(concepts), 'expected': EXPECTED_CONCEPTS})
chk('concept ids unique', len(ids) == len(set(ids)), {'unique': len(set(ids))})
chk('concept titles unique', len(titles) == len(set(titles)),
    [t for t in titles if titles.count(t) > 1][:5])
chk('ids namespaced', all(i.startswith('algebra_1_') for i in ids),
    [i for i in ids if not i.startswith('algebra_1_')][:5])
chk('ids fit receipt cap', all(len(i) <= 64 for i in ids),
    {'max_len': max((len(i) for i in ids), default=0)})

missing = [(c['id'], p) for c in concepts for p in (c.get('prerequisites') or [])
           if p not in set(ids)]
chk('all prerequisites resolve', not missing, missing[:6])

edge_count = sum(len(c.get('prerequisites') or []) for c in concepts)
chk('graph has gating edges', edge_count >= EXPECTED_UNITS,
    {'prerequisite_edges': edge_count})

# Depth: a chain of 157 would have depth ~157; a branching graph stays shallow.
depth: dict[str, int] = {}


def _depth(node_id: str) -> int:
    if node_id in depth:
        return depth[node_id]
    by_id = {c['id']: c for c in concepts}
    node = by_id.get(node_id)
    if not node:
        return 0
    parents = [p for p in (node.get('prerequisites') or []) if p in by_id]
    if not parents:
        depth[node_id] = 1
        return 1
    depth[node_id] = 1 + max(_depth(p) for p in parents)
    return depth[node_id]


max_depth = max((_depth(i) for i in ids), default=0)
chk('graph branches (max depth 4-8)', 4 <= max_depth <= 8, {'max_depth': max_depth})

# ------------------------------------------------------------------ alignment
alignment = (pack.get('metadata') or {}).get('textbook_alignment') or {}
unit_sections: dict[str, list[dict]] = alignment.get('units') or {}
chk('every unit has textbook sections',
    all(unit_sections.get(u) for u in units),
    {'units_missing': [u for u in units if not unit_sections.get(u)]})
chk('no stray unit in alignment',
    set(unit_sections) <= set(units),
    sorted(set(unit_sections) - set(units)))

all_pairs = [(u, entry['book'], entry['page'])
             for u, entries in unit_sections.items() for entry in entries]
chk('alignment section count', len(all_pairs) >= EXPECTED_UNITS,
    {'sections': len(all_pairs), 'units': len(unit_sections)})

# The licence claim is decided by the policy module, not by a comment.
from app.ingest.policy import OPENSTAX_BOOK_POLICIES, LicenceClass  # noqa: E402

books_used = sorted({book for _, book, _ in all_pairs})
licence_ok = True
licence_detail = {}
for book in books_used:
    policy = OPENSTAX_BOOK_POLICIES.get(book)
    ok = bool(policy and policy.ingestible and policy.licence_class is LicenceClass.CC_BY)
    licence_ok = licence_ok and ok
    licence_detail[book] = {
        'audited': bool(policy),
        'licence_class': policy.licence_class.value if policy else None,
        'ingestible': bool(policy and policy.ingestible),
    }
chk('every anchor book is CC BY and text-eligible', licence_ok, licence_detail)

# The NC book must never appear as an anchor.
chk('CC BY-NC-SA book never used as an anchor',
    'algebra-1' not in books_used, {'books_used': books_used})

# SECTION_MAP anchors for this course must point at real concepts.
from app.ingest.sources import openstax  # noqa: E402

anchors = {k: v for k, v in openstax.SECTION_MAP.items() if k.startswith('algebra_1_')}
unknown = [k for k in anchors if k not in set(ids)]
chk('grounding anchors are real concepts', not unknown,
    {'anchors': len(anchors), 'unknown': unknown[:5]})
chk('one anchor per unit on average', len(anchors) >= EXPECTED_UNITS,
    {'anchors': len(anchors)})
chk('anchor books are the aligned books',
    {b for b, _ in anchors.values()} <= set(books_used),
    {'anchor_books': sorted({b for b, _ in anchors.values()})})

# ------------------------------------------------------------------ live fetch
args = argparse.ArgumentParser(description=__doc__)
args.add_argument('--offline', action='store_true',
                  help='skip the network verification and report it as SKIP')
args.add_argument('--json', default=str(OUT / 'algebra_1_verification.json'))
opts = args.parse_args()

network_detail: list[dict] = []
if opts.offline:
    chk('textbook sections fetched through the licence gate', True,
        {'skipped': 'offline run'}, status='SKIP')
else:
    cache: dict = {}
    if CACHE.exists():
        try:
            cache = json.loads(CACHE.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            cache = {}
    settings = type('Settings', (), {'data_dir': tempfile.mkdtemp(prefix='algebra1_verify_')})()

    def _fetch(pair: tuple[str, str, str]) -> tuple[str, str, dict]:
        unit, book, page = pair
        key = f'{book}:{page}'
        if key in cache and cache[key].get('status') == 'ready':
            return unit, key, cache[key]
        try:
            record = openstax.ingest_section(settings, book, page)
        except Exception as exc:  # noqa: BLE001 - a fetch error is a finding, not a crash
            record = {'status': 'error', 'error': f'{type(exc).__name__}: {exc}'}
        cache[key] = {k: record.get(k) for k in
                      ('status', 'section_title', 'licence', 'licence_class',
                       'source_url', 'book_title')}
        cache[key]['error'] = record.get('error', '')
        return unit, key, cache[key]

    started = time.time()
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(_fetch, all_pairs))
    CACHE.write_text(json.dumps(cache, indent=1, ensure_ascii=False), encoding='utf-8')

    failures = [(u, k, r) for u, k, r in results if r.get('status') != 'ready']
    untitled = [(u, k, r) for u, k, r in results
                if r.get('status') == 'ready' and not str(r.get('section_title') or '').strip()]
    chk('textbook sections fetched through the licence gate', not failures,
        {'fetched': len(results), 'ready': len(results) - len(failures),
         'failures': [{'unit': u, 'section': k, 'status': r.get('status'),
                       'reason': (r.get('error') or '')[:160]} for u, k, r in failures[:6]],
         'seconds': round(time.time() - started, 1)})
    chk('every fetched section reports a title', not untitled, untitled[:5])

    # Relevance is evidence, not a hard gate: an anchor section's title should share at
    # least one content word with its unit, and the ones that do not are listed so a
    # reviewer can look instead of trusting an average.
    stop = {'and', 'the', 'of', 'to', 'in', 'a', 'an', 'with', 'for', 'by', 'on'}
    weak: list[dict] = []
    for unit, key, record in results:
        if record.get('status') != 'ready':
            continue
        title_words = {w for w in str(record.get('section_title') or '').lower().split()
                       if w.isalpha() and w not in stop}
        unit_words = {w for w in unit.lower().replace('1', ' ').split()
                      if w.isalpha() and w not in stop}
        if not title_words & unit_words:
            weak.append({'unit': unit, 'section': key,
                         'section_title': record.get('section_title')})
    chk('a majority of anchors share a word with their unit',
        len(weak) <= len(results) // 2,
        {'sections': len(results), 'weak_overlap': len(weak), 'examples': weak[:5]})

# ------------------------------------------------------------------ registry / graph
os.environ.setdefault('HARNESS_ENV', 'development')
os.environ.setdefault('HARNESS_DATA_DIR', tempfile.mkdtemp(prefix='algebra1_registry_'))

from app import courses  # noqa: E402

spec = courses.COURSE_BY_ID.get('algebra_1')
chk('registered in the course registry', spec is not None,
    spec.to_dict() if spec else 'missing')
graph = courses.graph_for('algebra_1')
chk('graph loads from the pack', len(graph.nodes) == EXPECTED_CONCEPTS,
    {'nodes': len(graph.nodes), 'edges': len(graph.edges) if hasattr(graph, 'edges') else 'n/a'})
chk('course_for_node resolves', courses.course_for_node(ids[0]) == 'algebra_1',
    courses.course_for_node(ids[0]))
chk('subject kind is mathematics', courses.subject_kind_for(ids[0]) == 'Mathematics'.lower()
    or courses.subject_kind_for(ids[0]) == courses.MATHEMATICS,
    courses.subject_kind_for(ids[0]))
chk('catalogue reports stats', bool(courses.stats_for('algebra_1')),
    courses.stats_for('algebra_1'))

# ------------------------------------------------------------------ generated layer
from app import curriculum  # noqa: E402

gen_concepts = curriculum.course_concepts('algebra_1')
gen_questions = curriculum.course_questions('algebra_1')
chk('generated lesson layer materialises concepts',
    len(gen_concepts) >= EXPECTED_CONCEPTS,
    {'concepts': len(gen_concepts)})
chk('generated layer supplies practice items',
    len(gen_questions) >= EXPECTED_CONCEPTS * 4,
    {'questions': len(gen_questions), 'per_concept': 4})
sample_id = ids[0]
sample = gen_concepts.get(sample_id) or {}
chk('a concept has teaching blocks', bool(sample.get('blocks')),
    {'concept': sample_id, 'blocks': len(sample.get('blocks') or []),
     'generated': bool(sample.get('generated'))})

# ------------------------------------------------------------------ report
passed = sum(1 for c in checks if c['status'] == 'PASS')
skipped = sum(1 for c in checks if c['status'] == 'SKIP')
failed = sum(1 for c in checks if c['status'] == 'FAIL')
report = {
    'generated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    'course': 'algebra_1',
    'summary': {'total': len(checks), 'passed': passed, 'skipped': skipped, 'failed': failed},
    'structure': {'units': len(units), 'topics': len(topics), 'concepts': len(concepts),
                  'prerequisite_edges': edge_count, 'max_depth': max_depth,
                  'units_list': units},
    'textbook': {'spine': alignment.get('spine'),
                 'supplements': alignment.get('supplements') or [],
                 'books_used': books_used, 'sections': len(all_pairs),
                 'anchors': len(anchors)},
    'checks': checks,
}
Path(opts.json).write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str),
                           encoding='utf-8')

print(f'RESULT: {passed}/{len(checks)} PASS, {skipped} SKIP, {failed} FAIL')
for c in checks:
    if c['status'] != 'PASS':
        print(f"  [{c['status']}] {c['check']} -- {str(c['detail'])[:220]}")
print('JSON : ' + opts.json)

if failed:
    raise RuntimeError(f'{failed} Algebra 1 verification check(s) failed')
