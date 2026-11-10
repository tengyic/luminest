"""Curate the shipped video seed: one pass, at build time, so runtime stays offline.

The desktop build runs with outbound media **off** — the privacy policy says so and the
audit indicted the bundle for contradicting it. But the video in a lesson is produced by
curation, and curation is a search. Turning media off therefore removed video from eleven of
twelve courses: ``/ta/prepare`` answered "video search needs network media", the plan fell
back to the deck, and nothing local could fill the gap because ``SEED_ALLOWLIST`` held four
rows for one course.

This closes that without loosening anything. Curation happens here, once, with the network
available; the result is a data file the bundle ships, and ``video.resolve`` reads it with no
network at all. Every candidate still has to pass the same oEmbed embeddability probe, the
same title-relevance test, and the same trusted-source preference a human curator's row
does — this is a faster curator, not a weaker gate.

**Keys are lesson ids, not graph node ids.** ``procedure_service._video`` looks the allowlist
up by the authored lesson id, which is what a client addresses and what a run is filed
under. Curating by graph node id writes rows nothing ever reads.

Run from ``harness/``::

    ui-tests/.venv/bin/python scripts/curate_videos.py --courses integrated_math_1
    ui-tests/.venv/bin/python scripts/curate_videos.py --per-course 12
    ui-tests/.venv/bin/python scripts/curate_videos.py --dry-run --courses physics

It writes ``backend/app/media_packs/video_allowlist_seed.json`` after every lesson, so an
interrupted pass keeps what it already curated and the same command resumes from there
instead of starting over. Re-running merges into the existing seed, so a second pass adds
coverage instead of replacing it; ``--refresh`` reopens concepts that already have a row.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS / 'backend'))

DEFAULT_OUT = HARNESS / 'backend' / 'app' / 'media_packs' / 'video_allowlist_seed.json'


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--per-course', type=int, default=0,
                        help='curate only the first N lessons of each course; 0 means all')
    parser.add_argument('--courses', default='',
                        help='comma-separated course ids; default is every course')
    parser.add_argument('--out', default=str(DEFAULT_OUT))
    parser.add_argument('--pause', type=float, default=0.4,
                        help='seconds between concepts, so the provider is not hammered')
    parser.add_argument('--refresh', action='store_true',
                        help='re-curate concepts that already have a row')
    parser.add_argument('--dry-run', action='store_true',
                        help='report what would be curated, write nothing')
    args = parser.parse_args()

    # A throwaway data directory: curation writes an allowlist as it goes, and this must not
    # touch the operator's real one. It is read back at the end and written to the seed file.
    state = Path(tempfile.mkdtemp(prefix='curate-'))
    for key in list(os.environ):
        if key.startswith('HARNESS_'):
            del os.environ[key]
    os.environ.update({
        'HARNESS_ENV': 'development',
        'HARNESS_MEDIA_ENABLED': '1',      # the whole point: the network is available *here*
        'HARNESS_DATA_DIR': str(state),
        'HARNESS_ALLOWED_HOSTS': 'localhost,127.0.0.1',
    })

    import app.config as cfg
    cfg.load_dotenv = lambda path=None: {}       # an operator .env must not steer this
    settings = cfg.Settings.from_env()
    print(f'state: {state}')

    from app import courses
    from app.curriculum import course_concepts
    from app.harness import video as video_module
    from app.harness import video_search

    wanted = {name.strip() for name in args.courses.split(',') if name.strip()}
    specs = [spec for spec in courses.COURSES if not wanted or spec.id in wanted]
    if not specs:
        raise SystemExit(f'no such course: {args.courses}')

    out = Path(args.out)
    merged: dict[str, list[dict]] = {}
    if out.is_file():
        try:
            merged = {k: list(v) for k, v in json.loads(out.read_text()).items()
                      if isinstance(v, list)}
        except ValueError:
            merged = {}
    else:
        # First run: start from the rows that were verified by hand, so the shipped file is
        # a superset of them and the in-code seed stops being the only copy.
        merged = {course: [dict(row) for row in rows]
                  for course, rows in video_module.SEED_ALLOWLIST.items()}

    curated = skipped = failed = 0
    started = time.time()

    def save() -> None:
        """Merge what has been curated so far into the seed file and write it.

        Called after every lesson, not once at the end. A full pass is hundreds of network
        searches and runs for hours, so an interrupted pass has to leave the work it already
        did in the file: three earlier passes were killed mid-flight and took their results
        with them. Because ``merged`` is also what decides what is still ``todo``, the same
        command afterwards resumes instead of starting over.
        """
        produced = video_module.load_allowlist(settings)
        for course_id, rows in produced.items():
            existing = {str(row.get('concept_id')) for row in merged.get(course_id, [])}
            merged.setdefault(course_id, [])
            merged[course_id].extend(row for row in rows
                                     if str(row.get('concept_id')) not in existing)
        ordered = {k: v for k, v in sorted(merged.items()) if v}
        out.parent.mkdir(parents=True, exist_ok=True)
        # Written to a sibling and renamed: this file is rewritten after every lesson, and a
        # reader that opens it mid-write would find truncated JSON — which ``load_allowlist``
        # treats as "no seed at all", i.e. a lesson silently loses its video.
        staged = out.with_suffix('.json.tmp')
        staged.write_text(json.dumps(ordered, indent=2, ensure_ascii=False) + '\n',
                          encoding='utf-8')
        os.replace(staged, out)

    for spec in specs:
        lessons = course_concepts(spec.id)
        ids = list(lessons)
        if args.per_course:
            ids = ids[:args.per_course]
        # Every lesson title in the course, so a candidate that belongs to a neighbouring
        # lesson ("One-step equations" for the two-step lesson) is refused rather than
        # curated. This is the check that makes a one-word difference between lessons safe.
        siblings = [str(lesson.get('title') or '') for lesson in lessons.values()]
        have = {str(row.get('concept_id')) for row in merged.get(spec.id, [])}
        todo = [lesson_id for lesson_id in ids if args.refresh or lesson_id not in have]
        print(f'\n=== {spec.id} ({len(todo)} of {len(lessons)} lessons to curate)')
        for lesson_id in todo:
            lesson = lessons[lesson_id]
            # The lesson's own topic and strand are the authored subject words. The summary
            # is prose and the title alone is often generic ("Fractions"), so this is what
            # gives the relevance test something to match on.
            concept = {'id': lesson_id, 'title': str(lesson.get('title') or ''),
                       'keywords': [str(lesson.get('topic') or ''),
                                    str(lesson.get('strand') or '')]}
            try:
                result = video_search.curate_for_concept(
                    settings, concept, spec.id, limit=4, siblings=siblings,
                    # A shipped list is held to a higher bar than an operator's ad-hoc
                    # curation: an unfamiliar channel whose title shares one word with the
                    # lesson is not evidence, and the deck opens with a published reason.
                    # Two shared words ("equivalent fractions") is.
                    min_untrusted_score=2)
            except Exception as error:                  # one bad lesson must not stop the pass
                failed += 1
                print(f'  ! {lesson_id}: {type(error).__name__}: {error}')
                continue
            if result.get('curated'):
                curated += 1
                video = result.get('video') or {}
                mark = '=' if result.get('trusted') else '~'
                print(f'  {mark} {lesson_id[:38]:40} {str(video.get("channel"))[:22]:24} '
                      f'{str(video.get("title"))[:44]}')
            else:
                skipped += 1
                print(f'  - {lesson_id[:38]:40} {str(result.get("reason"))[:60]}')
            if not args.dry_run:
                save()
            time.sleep(args.pause)

    if args.dry_run:
        print(f'\ndry run: curated {curated} · no candidate {skipped} · errors {failed}'
              f' · {time.time() - started:.0f}s · nothing written')
        return 0

    save()
    total = sum(len(rows) for rows in merged.values())
    print(f'\ncurated this pass: {curated} · no candidate: {skipped} · errors: {failed}'
          f' · {time.time() - started:.0f}s')
    print(f'seed now holds {total} row(s) across {len(merged)} course(s): {out}')
    return 0 if curated else 1


if __name__ == '__main__':
    sys.exit(main())
