"""A unit-level grade book scored against the course's declared objectives.

Why this module exists
----------------------
The brief asks for formally graded unit tests judged against academic standards. What
existed were graded *items* (``Attempt`` rows) and a curriculum practice exam that
deliberately returns ``grade: None`` when abandoned. There was no unit-level record: a
learner could answer two hundred questions and still have no answer to "how did I do in
this unit, and against what?".

A grade book is not a percentage over whatever attempts happen to exist. Three decisions
keep this one honest:

* **Standards are declared, not invented at grading time.** Each standard is a topic
  inside a unit of the learner's enrolled course graph, with the concept ids it covers.
  The declaration is returned alongside the score so a learner can see what was judged.
* **One lucky answer is not a grade.** A standard needs at least
  ``MIN_ATTEMPTS_PER_STANDARD`` scored attempts before it contributes. A unit with any
  unevidenced standard has no overall grade at all — it is ``incomplete``, never an
  average over the easy half of the syllabus.
* **Only genuinely graded attempts count.** Withheld exam items are excluded by
  ``main.graded_attempts`` before the list reaches this module; this module never
  re-implements that rule.

The result is explicitly *formative and course-local*: this is a mastery-based score
against this course's own declared objectives. It is not an accredited, proctored,
externally moderated or AP-aligned grade, and the API says so in ``scope_note``. Calling
it a "formal grade" without that sentence would be the exact overclaim the audit warned
about.

New table, no ``SCHEMA_VERSION`` bump — see ``course_builder.CreatedCourse`` and the
registration comment in ``scripts/init_db.py``.
"""
from __future__ import annotations

import hashlib
import os
import re
from collections import defaultdict

from sqlalchemy import (JSON, Float, ForeignKey, Index, Integer, String, Text,
                        UniqueConstraint, select)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, now_ts, uid

#: A topic needs this many scored attempts before a score is reported for it. Two is a
#: deliberate floor, not a statistical claim: it prevents a single correct guess from
#: manufacturing a "met standard" while still being reachable in one short lesson.
MIN_ATTEMPTS_PER_STANDARD = 2
#: 0.70 is the course's own mastery threshold, already used elsewhere in the teaching
#: policy. It is a course rule, not an external grading scale.
MASTERY_THRESHOLD = 0.70

SCOPE_NOTE = (
    'Formative mastery score against this course\'s own declared unit objectives. '
    'Not an accredited, proctored, externally moderated or AP/official grade. '
    'Scores come from server-graded attempts only; no unsubmitted item is counted.'
)


class ProjectGrade(Base):
    """Append-only human rubric judgement for a submitted project.

    A second score supersedes the first but never rewrites it. No automated
    correctness, creativity or integrity judgement is stored here.
    """
    __tablename__ = 'project_grades'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    criteria: Mapped[list] = mapped_column(JSON)
    total: Mapped[float] = mapped_column(Float)
    max_total: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(30))
    rationale: Mapped[str] = mapped_column(Text)
    reviewer_email: Mapped[str] = mapped_column(String(254))
    supersedes: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=now_ts)

    def public(self) -> dict:
        return {'id': self.id, 'project_id': self.project_id, 'criteria': self.criteria,
                'total': self.total, 'max_total': self.max_total, 'status': self.status,
                'rationale': self.rationale, 'reviewer_email': self.reviewer_email,
                'supersedes': self.supersedes, 'created_at': self.created_at,
                'scope': 'Configured human reviewer judgement against the visible rubric. '
                         'Not automated correctness, accreditation or proof of unaided work.'}


def reviewer_emails() -> frozenset[str]:
    """Configured summative reviewers. No account is a reviewer by default."""
    return frozenset(email.strip().casefold() for email in
                     os.getenv('HARNESS_REVIEWERS', '').split(',') if email.strip())


def score_project(db, project, criteria: list[dict], status: str,
                  rationale: str, reviewer_email: str) -> ProjectGrade:
    """Record a rubric score. Every score is a new row; an override links to its predecessor."""
    rubric = {item['id']: float(item['max_points']) for item in (project.rubric or [])}
    if not rubric or {row['criterion_id'] for row in criteria} != set(rubric):
        raise ValueError('Score every visible rubric criterion exactly once')
    ordered = []
    for row in sorted(criteria, key=lambda item: item['criterion_id']):
        points = float(row['points'])
        if not 0 <= points <= rubric[row['criterion_id']]:
            raise ValueError(f'Points for {row["criterion_id"]} exceed the rubric ceiling')
        if len(str(row.get('rationale', '')).strip()) < 3:
            raise ValueError('Each criterion needs a short reviewer rationale')
        ordered.append({'criterion_id': row['criterion_id'], 'points': points,
                        'rationale': str(row['rationale']).strip()[:2000]})
    # Scope the predecessor lookup to the project's owner: the tenant guard rejects a
    # project_id-only predicate, and a grade chain must never cross accounts even if two
    # projects ever shared an id.
    previous = db.scalar(select(ProjectGrade)
                         .where(ProjectGrade.user_id == project.user_id,
                                ProjectGrade.project_id == project.id)
                         .order_by(ProjectGrade.created_at.desc(), ProjectGrade.id.desc()))
    record = ProjectGrade(user_id=project.user_id, project_id=project.id, criteria=ordered,
                          total=float(sum(row['points'] for row in ordered)),
                          max_total=float(sum(rubric.values())), status=status,
                          rationale=rationale.strip()[:4000], reviewer_email=reviewer_email,
                          supersedes=previous.id if previous else None)
    db.add(record)
    db.flush()
    return record


def project_grade_history(db, user_id: str, project_id: str) -> list[ProjectGrade]:
    """All recorded judgements, oldest first, so an override is visible as such."""
    return list(db.scalars(select(ProjectGrade).where(
        ProjectGrade.user_id == user_id, ProjectGrade.project_id == project_id)
        .order_by(ProjectGrade.created_at, ProjectGrade.id)))


def slug(value: str) -> str:
    """A URL-safe, collision-resistant key for a strand/unit or unit/topic pair."""
    text = re.sub(r'[^a-z0-9]+', '-', (value or '').casefold()).strip('-') or 'unnamed'
    digest = hashlib.sha1(value.encode('utf-8')).hexdigest()[:8]  # noqa: S324 - key only
    return f'{text[:48]}-{digest}'


def unit_key(strand: str, unit: str) -> str:
    return slug(f'{strand}/{unit}')


def units_of(graph) -> list[dict]:
    """The declared units of a course graph with their standards.

    Pure over the graph object, so it can be tested without a database and so the same
    declaration is used for display and for grading. A standard is one topic within a
    unit; a unit whose concepts carry no topic still gets one unit-wide standard, because
    a generated course must not silently become ungradeable.
    """
    result = []
    for strand in graph.strands():
        for unit in graph.units(strand):
            members = graph.in_unit(unit, strand)
            if not members:
                continue
            grouped: dict[str, list] = defaultdict(list)
            for member in members:
                grouped[(member.topic or unit).strip() or unit].append(member)
            standards = []
            for topic, concepts in sorted(grouped.items()):
                standards.append({
                    'code': f'{slug(unit)}.{slug(topic)}',
                    'title': topic,
                    'concept_ids': sorted({m.id for m in concepts}),
                    'concept_count': len({m.id for m in concepts}),
                    'aliases': _aliases(concepts),
                })
            result.append({
                'key': unit_key(strand, unit),
                'strand': strand,
                'unit': unit,
                'concept_count': len({m.id for m in members}),
                'standards': standards,
            })
    return result


def _aliases(concepts) -> list[str]:
    """Both concept id namespaces can appear on an ``Attempt``.

    An authored lesson id (``fraction_equivalence``) and its graph node id name the same
    idea; ``concept_meta`` already bridges them for display. Grading must bridge them too
    or a learner's authored-course attempts would never reach their own unit standard.
    """
    from .curriculum import GRAPH_TO_LESSON  # local: keeps this module import-light

    names = set()
    for concept in concepts:
        names.add(concept.id)
        lesson = GRAPH_TO_LESSON.get(concept.id)
        if lesson:
            names.add(lesson)
    return sorted(names)


def evaluate(units: list[dict], attempts, *, course_id: str) -> list[dict]:
    """Score every unit from graded attempts. No writes, no hidden state.

    ``attempts`` is the already filtered list from ``main.graded_attempts``. Anything
    passed here is treated as graded, which is why the route is the only caller.
    """
    by_concept: dict[str, list] = defaultdict(list)
    for attempt in attempts:
        by_concept[attempt.concept_id].append(attempt)

    rows = []
    for unit in units:
        standards = []
        for standard in unit['standards']:
            seen = {}
            for alias in standard['aliases']:
                for attempt in by_concept.get(alias, []):
                    seen[attempt.id] = attempt
            matched = sorted(seen.values(), key=lambda a: a.created_at)
            answered = len(matched)
            correct = sum(1 for a in matched if a.correct)
            if answered < MIN_ATTEMPTS_PER_STANDARD:
                status, score = 'insufficient_evidence', None
            else:
                score = round(correct / answered, 4)
                status = 'met' if score >= MASTERY_THRESHOLD else 'not_yet_met'
            standards.append({
                'code': standard['code'], 'title': standard['title'],
                'concept_count': standard['concept_count'],
                'answered': answered, 'correct': correct,
                'score': score, 'status': status,
                'evidence_attempt_ids': [a.id for a in matched][:50],
                'requirement': (f'At least {MIN_ATTEMPTS_PER_STANDARD} graded attempts; '
                                f'met at {MASTERY_THRESHOLD:.0%}.'),
            })
        complete = all(s['status'] != 'insufficient_evidence' for s in standards)
        total = sum(s['answered'] for s in standards)
        correct = sum(s['correct'] for s in standards)
        met = sum(1 for s in standards if s['status'] == 'met')
        rows.append({
            'key': unit['key'], 'strand': unit['strand'], 'unit': unit['unit'],
            'course_id': course_id,
            'concept_count': unit['concept_count'],
            'standards': standards,
            'standards_met': met,
            'standards_total': len(standards),
            'answered': total, 'correct': correct,
            'percent': round(correct / total, 4) if complete and total else None,
            'status': 'evidenced' if complete else 'incomplete',
            'gradeable': complete,
            'missing': [s['title'] for s in standards if s['status'] == 'insufficient_evidence'],
            'scope_note': SCOPE_NOTE,
        })
    return rows


def grade_json(row: UnitGrade) -> dict:
    return {
        'id': row.id, 'key': row.unit_key, 'strand': row.strand, 'unit': row.unit,
        'course_id': row.course_id, 'standards': row.standards,
        'score': row.score, 'max_score': row.max_score, 'percent': row.percent,
        'standards_met': row.standards_met, 'standards_total': row.standards_total,
        'attempts': row.attempts, 'graded_at': row.graded_at,
        'status': 'final', 'scope_note': row.scope_note,
    }


class UnitGrade(Base):
    """A frozen unit grade, stored only when every declared standard has evidence."""

    __tablename__ = 'unit_grades'
    __table_args__ = (
        Index('unit_grades_user_course_idx', 'user_id', 'course_id'),
        UniqueConstraint('user_id', 'course_id', 'unit_key', name='unit_grades_once'),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    course_id: Mapped[str] = mapped_column(String(64))
    unit_key: Mapped[str] = mapped_column(String(120))
    strand: Mapped[str] = mapped_column(String(200))
    unit: Mapped[str] = mapped_column(String(200))
    #: The standards as they were declared at grading time. Re-grading later must not
    #: silently rewrite history if the course graph changes.
    standards: Mapped[dict] = mapped_column(JSON)
    score: Mapped[float] = mapped_column(Float)
    max_score: Mapped[int] = mapped_column(Integer)
    percent: Mapped[float] = mapped_column(Float)
    standards_met: Mapped[int] = mapped_column(Integer)
    standards_total: Mapped[int] = mapped_column(Integer)
    attempts: Mapped[int] = mapped_column(Integer)
    graded_at: Mapped[float] = mapped_column(Float, default=now_ts)
    scope_note: Mapped[str] = mapped_column(Text, default=SCOPE_NOTE)


__all__ = ['MIN_ATTEMPTS_PER_STANDARD', 'MASTERY_THRESHOLD', 'SCOPE_NOTE', 'UnitGrade',
           'evaluate', 'grade_json', 'unit_key', 'units_of']
