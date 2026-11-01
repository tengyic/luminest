"""Report the honest gap between the authored lesson layer and the course graph.

Run:  python scripts/check_lesson_coverage.py

Prints a per-course gap report and writes app/curriculum_packs/coverage_gaps.json.
Exits non-zero only on structural drift (a LESSON_TARGETS entry that names a missing
graph node, or an authored lesson with fewer than four question variants) - a large
remaining gap is an expected, reported fact, not a failure.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import curriculum  # noqa: E402  (import-time validation must pass to get here)
from app import courses  # noqa: E402


def main() -> int:
    problems: list[str] = []

    # Structural drift: every target must resolve, every authored lesson needs 4 variants.
    for lesson_id, node_id in curriculum.LESSON_TARGETS.items():
        if node_id not in curriculum.KNOWLEDGE_GRAPH.nodes:
            problems.append(f'LESSON_TARGETS names missing graph node {node_id!r}')
        if lesson_id not in curriculum.CONCEPTS:
            problems.append(f'authored lesson {lesson_id!r} has no concept entry')
    for qid, count in sorted(
            {cid: sum(1 for q in curriculum.QUESTIONS.values()
                      if q.get('concept_id') == cid)
             for cid in list(curriculum.CONCEPTS)[:len(curriculum.LESSON_TARGETS)]}.items()):
        if cid_is_authored := (cid := qid) in curriculum.LESSON_TARGETS:
            if count < 4:
                problems.append(f'authored lesson {cid!r} has {count} question variants (< 4)')

    graph = curriculum.KNOWLEDGE_GRAPH
    stats = graph.stats()
    total = stats['concepts']
    with_lesson = stats['with_lesson']

    per_course: dict[str, dict] = {}
    for course in courses.COURSES:
        share = curriculum.authored_share(course.id)
        per_course[course.id] = share
        # ``graph_remaining`` used to be written for the algebra course alone, which made
        # the report answer "what is left to author" for one course out of twelve. The
        # question is the same for every pack, and the answer is what an overlay run would
        # be pointed at, so every course gets the list.
        #
        # Membership comes from the course's graph; lesson-ness comes from the curriculum
        # registry. They are two different sources on purpose: the pack declares the scope
        # and the registry declares what has been written. Reading lesson-ness off the
        # graph alone would report zero for the algebra course too, because the pack JSON
        # carries no lesson flags and the registry sets them on its own graph instance.
        course_graph = courses.graph_for(course.id)
        # What counts as taught: a lesson a person wrote, or one the harness wrote into
        # this course as an overlay. A concept the *generated* layer materialised does not
        # count, and not because it is bad - it is what makes the outline usable - but
        # because it carries no teaching prose, and counting it would report every course
        # as fully covered on the day its pack was built.
        #
        # The node id is ``graph_id``, not the registry key: an authored lesson is keyed by
        # its own lesson id ('fractions') while the graph node it teaches has a different
        # id, and 15 of the algebra course's 30 lessons differ. Using the key directly
        # counted half the lessons as missing from a graph that contains all of them.
        taught = {str(entry.get('graph_id') or concept_id)
                  for concept_id, entry in curriculum.course_concepts(course.id).items()
                  if not entry.get('generated') or entry.get('overlay')}
        per_course[course.id]['graph_remaining'] = sorted(
            node_id for node_id in course_graph.nodes if node_id not in taught)
        print(f"{course.id:24s} authored {share['authored_concepts']:4d}/{share['concepts']:4d} concepts, "
              f"{share['authored_questions']:4d}/{share['questions']:4d} questions, "
              f"{share['model_drafted_concepts']:4d} model-drafted, "
              f"{len(per_course[course.id]['graph_remaining']):4d} nodes still outline-only "
              f"({'authored course' if course.authored else 'generated course'})")
    if any(problems):
        for problem in problems:
            print(f'DRIFT: {problem}')

    # The totals used to describe the algebra graph alone, which read as a statement about
    # the product: "30 of 164 concepts have lessons" is true and, as a summary of twelve
    # courses and 944 nodes, badly incomplete. Both are reported now, labelled.
    all_nodes = sum(len(courses.graph_for(spec.id).nodes) for spec in courses.COURSES)
    all_taught = sum(len(courses.graph_for(spec.id).nodes)
                     - len(per_course[spec.id]['graph_remaining']) for spec in courses.COURSES)
    report = {
        'generated': date.today().isoformat(),
        'note': 'Generated by scripts/check_lesson_coverage.py; never hand-edited. '
                'Remaining gaps are reported facts, not failures: an outline node takes part '
                'in prerequisite reasoning and coverage accounting but has no authored lesson yet.',
        'totals': {'courses': len(courses.COURSES),
                   'graph_concepts': all_nodes, 'with_lesson': all_taught,
                   'outline_only': all_nodes - all_taught,
                   'authored_share_all_courses': round(all_taught / all_nodes, 3),
                   'algebra_graph_concepts': total, 'algebra_with_lesson': with_lesson,
                   'authored_share_algebra': round(with_lesson / total, 3)},
        'per_course': per_course,
        'structural_problems': problems,
    }
    out = curriculum.PACK_DIR / 'coverage_gaps.json'
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f"\nwrote {out}")
    print(f"authored lesson coverage: {all_taught}/{all_nodes} nodes across "
          f"{len(courses.COURSES)} courses ({100 * all_taught / all_nodes:.1f}%), "
          f"{all_nodes - all_taught} remaining")
    print(f"  algebra alone: {with_lesson}/{total} ({100 * with_lesson / total:.1f}%)")
    return 1 if problems else 0


if __name__ == '__main__':
    raise SystemExit(main())
