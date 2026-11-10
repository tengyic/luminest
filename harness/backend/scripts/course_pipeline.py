"""Generic course pipeline: outline module -> seed -> pack -> verification.

One command builds any course that has an outline module under ``scripts/outlines/``:

    python scripts/course_pipeline.py build --course algebra_1
    python scripts/course_pipeline.py verify --course algebra_1 [--offline]

An outline module is data, not logic. It must expose:

    ID, TITLE, DESCRIPTION, SUBJECT_KIND, EXPECTED_WEEKS, COURSE_LINE
    UNITS: list of {
        'unit': str,
        'about': str,
        'sections': [(book_slug, page_slug), ...],   # verified OpenStax sections
        'topics': [(topic_name, [(concept_title, concept_summary, [keywords]), ...]), ...],
    }
    TEXTBOOK: {'spine': str, 'supplements': [str], 'link_only_note': str}

Everything else -- id namespacing, prerequisite wiring, the textbook_alignment
metadata block -- is derived here so every course is built the same way and a
reviewer reads one implementation instead of thirteen.

The licence position is enforced, not documented: a section whose book is not
CC BY and text-eligible is refused before any request leaves the machine, and the
NC ``algebra-1`` style books can never become anchors.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / 'scripts'))

OUT = BACKEND.parent / 'outputs'
OUT.mkdir(parents=True, exist_ok=True)
PACK_DIR = BACKEND / 'app' / 'curriculum_packs'
CACHE = Path(tempfile.gettempdir()) / 'course_textbook_check.json'


def load_outline(course_id: str):
    return importlib.import_module(f'outlines.{course_id}')


def _course_dict(mod) -> dict:
    strands = []
    previous_unit = None
    for unit in mod.UNITS:
        topics = []
        for name, rows in unit['topics']:
            concepts = []
            previous_title = None
            for title, summary, keywords in rows:
                entry = {'title': title, 'summary': summary, 'keywords': list(keywords)}
                if previous_title is not None:
                    entry['prerequisites'] = [previous_title]
                concepts.append(entry)
                previous_title = title
            topics.append({'topic': name, 'concepts': concepts})
        unit_entry = {'unit': unit['unit'], 'topics': topics}
        if previous_unit is not None:
            unit_entry['prerequisites'] = [previous_unit]
        strands.append({'strand': unit['unit'], 'units': [unit_entry]})
        previous_unit = unit['unit']
    return {
        'id': mod.ID, 'title': mod.TITLE, 'subject': getattr(mod, 'SUBJECT', ''),
        'subject_kind': mod.SUBJECT_KIND, 'expected_weeks': mod.EXPECTED_WEEKS,
        'description': mod.DESCRIPTION, 'course': mod.COURSE_LINE,
        'strands': strands,
    }


def _alignment(mod) -> dict:
    return {unit['unit']: [{'book': book, 'page': page} for book, page in unit['sections']]
            for unit in mod.UNITS}


# --------------------------------------------------------------------- build
def build(course_id: str) -> int:
    from build_requested_courses import build_pack, write_seed

    mod = load_outline(course_id)
    course = _course_dict(mod)
    print(f"building {mod.ID} ({mod.TITLE})")
    seed = write_seed(course)
    print(f'  wrote {seed.relative_to(BACKEND)}')
    pack_path = build_pack(course)
    print(f'  wrote {pack_path.relative_to(BACKEND)}')

    pack = json.loads(pack_path.read_text(encoding='utf-8'))
    pack['metadata']['textbook_alignment'] = {
        'spine': mod.TEXTBOOK.get('spine', ''),
        'supplements': list(mod.TEXTBOOK.get('supplements') or []),
        'link_only_note': mod.TEXTBOOK.get('link_only_note', ''),
        'units': _alignment(mod),
    }
    pack_path.write_text(json.dumps(pack, indent=1, ensure_ascii=False) + '\n',
                         encoding='utf-8')
    total = sum(len(u['sections']) for u in mod.UNITS)
    print(f'  anchored {total} textbook sections across {len(mod.UNITS)} units')
    print('\ndone. Register the course in app/courses.py and app/ingest/policy.py, then '
          'run: python scripts/course_pipeline.py verify --course ' + course_id)
    return 0


# -------------------------------------------------------------------- verify
def _chk(checks: list[dict], name: str, ok: bool, detail=None, *, status=None) -> None:
    checks.append({'check': name, 'ok': bool(ok), 'status': status or ('PASS' if ok else 'FAIL'),
                   'detail': detail if detail is not None else ''})


def verify(course_id: str, *, offline: bool = False, json_path: str | None = None) -> int:
    from app.ingest.policy import OPENSTAX_BOOK_POLICIES, LicenceClass
    from app.ingest.sources import openstax

    mod = load_outline(course_id)
    checks: list[dict] = []
    pack_path = PACK_DIR / f'{mod.ID}.json'
    _chk(checks, 'pack exists', pack_path.exists(), str(pack_path))
    if not pack_path.exists():
        return _finish(course_id, checks, json_path)
    pack = json.loads(pack_path.read_text(encoding='utf-8'))
    concepts = pack.get('concepts') or []
    ids = [c['id'] for c in concepts]
    titles = [c['title'] for c in concepts]
    units = sorted({c.get('unit') or '' for c in concepts} - {''})
    topics = sorted({(c.get('unit') or '', c.get('topic') or '') for c in concepts})

    expected_units = [u['unit'] for u in mod.UNITS]
    expected_topics = sum(len(u['topics']) for u in mod.UNITS)
    expected_concepts = sum(len(rows) for u in mod.UNITS for _, rows in u['topics'])

    _chk(checks, 'unit count matches the outline', len(units) == len(expected_units),
         {'pack': len(units), 'outline': len(expected_units), 'missing': sorted(set(expected_units) - set(units))})
    _chk(checks, 'topic count matches the outline', len(topics) == expected_topics,
         {'pack': len(topics), 'outline': expected_topics})
    _chk(checks, 'concept count matches the outline', len(concepts) == expected_concepts,
         {'pack': len(concepts), 'outline': expected_concepts})
    _chk(checks, 'concept ids unique', len(ids) == len(set(ids)))
    _chk(checks, 'concept titles unique', len(titles) == len(set(titles)),
         [t for t in titles if titles.count(t) > 1][:5])
    prefix = f'{mod.ID}_'
    _chk(checks, 'ids namespaced', all(i.startswith(prefix) for i in ids),
         [i for i in ids if not i.startswith(prefix)][:5])
    _chk(checks, 'ids fit receipt cap', all(len(i) <= 64 for i in ids),
         {'max_len': max((len(i) for i in ids), default=0)})

    id_set = set(ids)
    missing = [(c['id'], p) for c in concepts for p in (c.get('prerequisites') or [])
               if p not in id_set]
    _chk(checks, 'all prerequisites resolve', not missing, missing[:6])
    edges = sum(len(c.get('prerequisites') or []) for c in concepts)
    _chk(checks, 'graph has gating edges', edges >= len(expected_units),
         {'prerequisite_edges': edges})

    by_id = {c['id']: c for c in concepts}
    depth: dict[str, int] = {}

    def _depth(nid: str) -> int:
        if nid in depth:
            return depth[nid]
        node = by_id.get(nid)
        if not node:
            return 0
        parents = [p for p in (node.get('prerequisites') or []) if p in by_id]
        depth[nid] = 1 if not parents else 1 + max(_depth(p) for p in parents)
        return depth[nid]

    max_depth = max((_depth(i) for i in ids), default=0)
    _chk(checks, 'graph branches (max depth 3-9)', 3 <= max_depth <= 9, {'max_depth': max_depth})

    alignment = (pack.get('metadata') or {}).get('textbook_alignment') or {}
    unit_sections = alignment.get('units') or {}
    no_anchor = bool(mod.TEXTBOOK.get('no_cc_by_anchor'))
    if no_anchor:
        # Honest declaration path. Some subjects have no CC BY textbook in the publisher's
        # catalogue at all (calculus and organic chemistry are NC; Earth Science, Linear
        # Algebra and ACT English have no OpenStax book). Such a course states the reason
        # instead of silently borrowing an unrelated book as an anchor, and this check
        # reports SKIP with that reason rather than a green tick it has not earned.
        _chk(checks, 'textbook anchoring', True,
             {'declared_no_cc_by_anchor': True,
              'reason': mod.TEXTBOOK.get('reason', '')}, status='SKIP')
    else:
        _chk(checks, 'every unit has textbook sections',
             all(unit_sections.get(u) for u in expected_units),
             {'units_missing': [u for u in expected_units if not unit_sections.get(u)]})
    all_pairs = [(u, e['book'], e['page']) for u, es in unit_sections.items() for e in es]
    if no_anchor:
        # The declaration is an assertion that nothing is anchored, so the count check flips
        # rather than disappears: a course that declares no anchor and still carries sections
        # has done exactly the stand-in borrowing the declaration exists to rule out.
        _chk(checks, 'alignment section count', not all_pairs,
             {'sections': len(all_pairs), 'expected': 0,
              'reason': 'no CC BY anchor declared, so no section may be listed'})
    else:
        _chk(checks, 'alignment section count', len(all_pairs) >= len(expected_units),
             {'sections': len(all_pairs)})

    books_used = sorted({b for _, b, _ in all_pairs})
    detail = {}
    licence_ok = True
    for book in books_used:
        policy = OPENSTAX_BOOK_POLICIES.get(book)
        ok = bool(policy and policy.ingestible and policy.licence_class is LicenceClass.CC_BY)
        licence_ok = licence_ok and ok
        detail[book] = {'audited': bool(policy),
                        'licence_class': policy.licence_class.value if policy else None,
                        'ingestible': bool(policy and policy.ingestible)}
    _chk(checks, 'every anchor book is CC BY and text-eligible', licence_ok, detail)
    nc_books = [b for b in books_used if str(detail.get(b, {}).get('licence_class')) == 'cc_by_nc_sa']
    _chk(checks, 'no NC book used as a text anchor', not nc_books, nc_books)

    anchors = {k: v for k, v in openstax.SECTION_MAP.items() if k.startswith(prefix)}
    unknown = [k for k in anchors if k not in id_set]
    _chk(checks, 'grounding anchors are real concepts', not unknown,
         {'anchors': len(anchors), 'unknown': unknown[:5]})
    _chk(checks, 'anchor books are aligned books',
         {b for b, _ in anchors.values()} <= set(books_used),
         sorted({b for b, _ in anchors.values()} - set(books_used)))

    if no_anchor:
        # Nothing to fetch: the declaration above is the single honest non-result for this
        # course, and a second SKIP for an empty section list would just report the same fact
        # twice.
        pass
    elif offline:
        _chk(checks, 'textbook sections fetched through the licence gate', True,
             {'skipped': 'offline run'}, status='SKIP')
    else:
        cache = {}
        if CACHE.exists():
            try:
                cache = json.loads(CACHE.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                cache = {}
        settings = type('Settings', (), {'data_dir': tempfile.mkdtemp(prefix='verify_')})()

        def _fetch(pair):
            unit, book, page = pair
            key = f'{book}:{page}'
            if key in cache and cache[key].get('status') == 'ready':
                return unit, key, cache[key]
            try:
                rec = openstax.ingest_section(settings, book, page)
            except Exception as exc:  # noqa: BLE001
                rec = {'status': 'error', 'error': f'{type(exc).__name__}: {exc}'}
            cache[key] = {k: rec.get(k) for k in
                          ('status', 'section_title', 'licence', 'licence_class', 'source_url')}
            cache[key]['error'] = rec.get('error', '')
            return unit, key, cache[key]

        started = time.time()
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(_fetch, all_pairs))
        CACHE.write_text(json.dumps(cache, indent=1, ensure_ascii=False), encoding='utf-8')
        failures = [(u, k, r) for u, k, r in results if r.get('status') != 'ready']
        _chk(checks, 'textbook sections fetched through the licence gate', not failures,
             {'fetched': len(results), 'ready': len(results) - len(failures),
              'failures': [{'unit': u, 'section': k, 'status': r.get('status'),
                            'reason': (r.get('error') or '')[:160]} for u, k, r in failures[:6]],
              'seconds': round(time.time() - started, 1)})
        untitled = [k for u, k, r in results
                    if r.get('status') == 'ready' and not str(r.get('section_title') or '').strip()]
        _chk(checks, 'every fetched section reports a title', not untitled, untitled[:5])

    # Registry is optional at build time: build/verify before registering is a normal
    # order, and a missing registration is reported as SKIP rather than a failure.
    from app import courses
    body_text = pack_path.read_text(encoding='utf-8')
    if mod.ID in courses.COURSE_BY_ID:
        graph = courses.graph_for(mod.ID)
        _chk(checks, 'graph loads from the pack', len(graph.nodes) == expected_concepts,
             {'nodes': len(graph.nodes)})
        _chk(checks, 'course_for_node resolves', courses.course_for_node(ids[0]) == mod.ID,
             courses.course_for_node(ids[0]))
        from app import curriculum
        gen_concepts = curriculum.course_concepts(mod.ID)
        gen_questions = curriculum.course_questions(mod.ID)
        _chk(checks, 'generated lesson layer materialises concepts',
             len(gen_concepts) >= expected_concepts, {'concepts': len(gen_concepts)})
        _chk(checks, 'generated layer supplies practice items',
             len(gen_questions) >= expected_concepts * 4, {'questions': len(gen_questions)})
    else:
        _chk(checks, 'registered in the course registry', True,
             {'skipped': 'not registered yet'}, status='SKIP')

    del body_text
    return _finish(course_id, checks, json_path, structure={
        'units': len(units), 'topics': len(topics), 'concepts': len(concepts),
        'prerequisite_edges': edges, 'max_depth': max_depth},
        textbook={'spine': alignment.get('spine'), 'books_used': books_used,
                  'sections': len(all_pairs), 'anchors': len(anchors)})


def _finish(course_id: str, checks: list[dict], json_path: str | None,
            structure: dict | None = None, textbook: dict | None = None) -> int:
    passed = sum(1 for c in checks if c['status'] == 'PASS')
    skipped = sum(1 for c in checks if c['status'] == 'SKIP')
    failed = sum(1 for c in checks if c['status'] == 'FAIL')
    report = {
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'course': course_id,
        'summary': {'total': len(checks), 'passed': passed, 'skipped': skipped, 'failed': failed},
        'structure': structure or {},
        'textbook': textbook or {},
        'checks': checks,
    }
    target = Path(json_path) if json_path else OUT / f'course_verification_{course_id}.json'
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str),
                      encoding='utf-8')
    print(f'RESULT: {passed}/{len(checks)} PASS, {skipped} SKIP, {failed} FAIL')
    for c in checks:
        if c['status'] != 'PASS':
            print(f"  [{c['status']}] {c['check']} -- {str(c['detail'])[:200]}")
    print('JSON : ' + str(target))
    return 1 if failed else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('command', choices=['build', 'verify'])
    ap.add_argument('--course', required=True)
    ap.add_argument('--offline', action='store_true')
    ap.add_argument('--json', default=None)
    args = ap.parse_args()
    if args.command == 'build':
        return build(args.course)
    return verify(args.course, offline=args.offline, json_path=args.json)


if __name__ == '__main__':
    raise SystemExit(main())
