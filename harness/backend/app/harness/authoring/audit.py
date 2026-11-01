"""The audit: the reason a generated course is allowed to exist.

Every other module in this package produces something. This one refuses things. It
exists because the failure mode of an authoring system is not a crash - it is a course
that looks complete. A graph with forty nodes, a lesson for each, four options on every
item: nothing errors, nothing is empty, and a learner spends three weeks on material
that never taught them anything because no sentence in it answered the questions it
asked.

So the audit is mechanical, and it checks the properties that make a course teachable
rather than the properties that make it look finished:

**Every item's answer is in the lesson.** Not "the item is well formed" - that the
correct option is literally present in a block the learner receives, in the block the
item claims. An item whose answer is nowhere in the lesson measures the model's prior,
not the learner's understanding.

**Every concept has the depth the profile requires.** A summary and four items is a
flashcard. The profile names the blocks a lesson must carry; a missing worked example or
misconception is an error, not a style note.

**The graph is teachable in the order it is presented.** Acyclic, prerequisites inside
the unit, no forward edges, no concept resting on more than the profile allows.

**The course has a shape.** Units within bounds, difficulty that actually ramps, item
kinds that cover recall *and* discrimination *and* transfer. A course whose every item
is definition recall has not assessed anything.

Severity is two-valued on purpose. ``error`` means do not publish; ``warning`` means a
human should look. A three-valued scale invites the argument about which middle tier a
problem belongs in, and that argument is how a blocking check becomes advisory.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from . import blueprint, methodology
from .synthesize import ORIGIN, AuthoredCourse

#: Item categories the profile requires the course to cover. Recall alone is a quiz;
#: discrimination and transfer are what the lesson is for.
REQUIRED_CATEGORIES = ('definition_recall', 'misconception_repair', 'application_transfer')


@dataclass(frozen=True)
class Finding:
    """One audit result, with the location that carries it."""

    code: str
    path: str
    message: str
    severity: str = 'error'

    @property
    def blocking(self) -> bool:
        return self.severity == 'error'

    def to_dict(self) -> dict[str, str]:
        return {'code': self.code, 'path': self.path, 'message': self.message,
                'severity': self.severity}


@dataclass
class Audit:
    findings: list[Finding] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    @property
    def errors(self) -> list[Finding]:
        return [finding for finding in self.findings if finding.blocking]

    @property
    def warnings(self) -> list[Finding]:
        return [finding for finding in self.findings if not finding.blocking]

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {'ok': self.ok, 'errors': [f.to_dict() for f in self.errors],
                'warnings': [f.to_dict() for f in self.warnings], 'stats': self.stats}


def _words(text: str) -> int:
    return len([part for part in re.split(r'\s+', (text or '').strip()) if part])


def _normalise(text: str) -> str:
    """Comparison form for "is this answer in the lesson".

    Case-folded and whitespace-collapsed, and nothing else. A stemmer or a fuzzy match
    would make the check pass on a paraphrase, which is exactly the failure it is meant
    to catch: if the answer is only *implied* by the lesson, the learner was asked to
    infer something they were never told.
    """
    return re.sub(r'\s+', ' ', (text or '').strip().casefold())


def _block_text(concept_entry: Mapping[str, Any], kinds: Iterable[str]) -> str:
    wanted = set(kinds)
    return ' '.join(str(block.get('body') or '') for block in concept_entry.get('blocks') or []
                    if block.get('kind') in wanted)


def _block_kinds(concept_entry: Mapping[str, Any]) -> list[str]:
    return [str(block.get('kind') or '') for block in concept_entry.get('blocks') or []]


def _final_unit(course: AuthoredCourse) -> str:
    """The course's last unit, which is where the worked example is faded.

    Read from the graph rather than from the plan's last unit, because the two differ for
    an overlay: a patch's plan covers only the units it wrote, so ``plan.units[-1]`` is the
    last unit *touched today*. Fading is keyed off this same function in
    :func:`synthesize.build_overlay`, so a disagreement here would refuse a lesson for
    being faded and refuse it again for not being faded.
    """
    units = course.graph.units()
    if units:
        return units[-1]
    return course.plan.units[-1].title if course.plan.units else ''


# ----------------------------------------------------------------------- checks

def _audit_concept(course: AuthoredCourse, concept: blueprint.ConceptPlan,
                   entry: Mapping[str, Any], items: Sequence[Mapping[str, Any]],
                   profile: methodology.AuthoringProfile) -> list[Finding]:
    findings: list[Finding] = []
    path = f'concept {concept.id!r}'
    kinds = _block_kinds(entry)

    # The prose floors live here rather than in the parser because this is the one gate
    # that decides whether a course may ship. A parser that refused a nine-word summary
    # would have to refuse the whole blueprint, including the eight concepts that were
    # fine, and the author could not preview any of it.
    if _words(concept.summary) < profile.load.min_summary_words:
        findings.append(Finding(
            'summary_thin', path,
            f'the summary is {_words(concept.summary)} words; the floor is '
            f'{profile.load.min_summary_words}. A summary is the first thing the learner '
            f'reads, and a clause is not a summary'))
    if len(concept.example) < profile.load.min_example_steps:
        findings.append(Finding(
            'example_thin', path,
            f'the worked example has {len(concept.example)} steps; the floor is '
            f'{profile.load.min_example_steps}. One line is a hint, not an example'))
    if not concept.misconception.strip():
        findings.append(Finding(
            'misconception_missing', path,
            'the lesson names no misconception, so it cannot teach the discrimination '
            'the items then test'))
    if _words(concept.application) < 6:
        findings.append(Finding(
            'application_thin', path,
            'the transfer task is missing or too short to require the concept'))

    for spec in profile.blocks:
        if spec.required and spec.kind not in kinds:
            # The fade is a deliberate absence: in the final unit the worked example is
            # withdrawn and replaced by a prompt that keeps the method and drops the
            # worked content. Checking only for the block would make the profile's own
            # rule an audit failure, so the replacement is what is required there.
            if spec.kind in profile.fade_in_final_unit and concept.unit == _final_unit(course):
                if 'reflection' not in kinds:
                    findings.append(Finding(
                        'fade_replacement_missing', path,
                        f'the {spec.kind!r} block is faded here, but nothing replaced it: '
                        f'the learner gets neither the model nor the prompt'))
                continue
            findings.append(Finding(
                'block_missing', path,
                f'the lesson has no {spec.kind!r} block ({spec.title!r}); the profile '
                f'requires it'))
    for block in entry.get('blocks') or []:
        words = _words(str(block.get('body') or ''))
        if words > profile.load.max_words_per_block:
            findings.append(Finding(
                'block_too_long', path,
                f'the {block.get("kind")!r} block is {words} words; the budget is '
                f'{profile.load.max_words_per_block}', 'warning'))

    total_words = sum(_words(str(block.get('body') or ''))
                      for block in entry.get('blocks') or [])
    if total_words > profile.load.max_words_per_concept:
        findings.append(Finding(
            'lesson_too_long', path,
            f'the lesson is {total_words} words; a concept is budgeted at '
            f'{profile.load.max_words_per_concept}', 'warning'))
    if total_words < 60:
        findings.append(Finding(
            'lesson_thin', path,
            f'the whole lesson is {total_words} words; that is a note, not a lesson'))

    if len(items) < profile.assessment.min_items_per_concept:
        findings.append(Finding(
            'items_too_few', path,
            f'{len(items)} items; the profile requires at least '
            f'{profile.assessment.min_items_per_concept}'))
    if len(items) > profile.assessment.max_items_per_concept:
        findings.append(Finding(
            'items_too_many', path,
            f'{len(items)} items; the ceiling is '
            f'{profile.assessment.max_items_per_concept}', 'warning'))

    findings.extend(_audit_items(course, concept, entry, items, profile))
    return findings


def _audit_items(course: AuthoredCourse, concept: blueprint.ConceptPlan,
                 entry: Mapping[str, Any], items: Sequence[Mapping[str, Any]],
                 profile: methodology.AuthoringProfile) -> list[Finding]:
    findings: list[Finding] = []
    for item in items:
        item_id = str(item.get('id') or '')
        path = f'item {item_id!r}'
        options = item.get('options') or []
        texts = [str(option.get('text') or '') for option in options]
        if len(texts) != profile.assessment.options_per_item:
            findings.append(Finding(
                'item_option_count', path,
                f'{len(texts)} options; every item has exactly '
                f'{profile.assessment.options_per_item}'))
        if len(set(_normalise(text) for text in texts)) != len(texts):
            findings.append(Finding(
                'item_duplicate_option', path,
                'two options carry the same text, so the item has no single right answer'))
        answer_id = str(item.get('answer_id') or '')
        matching = [option for option in options if str(option.get('id')) == answer_id]
        if not matching:
            findings.append(Finding(
                'item_answer_missing', path,
                f'answer_id {answer_id!r} is not one of the options'))
        elif _normalise(str(matching[0].get('text') or '')) != \
                _normalise(str(item.get('answer_text') or '')):
            findings.append(Finding(
                'item_answer_mismatch', path,
                'answer_id points at a different option than answer_text'))
        if not str(item.get('explanation') or '').strip():
            findings.append(Finding(
                'item_no_explanation', path,
                'the item has no explanation, so a wrong answer teaches nothing',
                'warning'))

        answerable_from = str(item.get('answerable_from') or '')
        if answerable_from:
            findings.extend(_check_answerable(concept, entry, item, answerable_from, path))
    return findings


def _check_answerable(concept: blueprint.ConceptPlan, entry: Mapping[str, Any],
                      item: Mapping[str, Any], answerable_from: str,
                      path: str) -> list[Finding]:
    """Prove the correct option is present in the block the item claims.

    Three of the categories are answerable from a *structural* fact rather than a
    sentence - a real prerequisite edge, a real unit membership, a real teaching-order
    relation - and those are checked against the graph instead. The rest must appear in
    the lesson text, verbatim after whitespace normalisation.
    """
    answer = str(item.get('answer_text') or '')
    if answerable_from == 'structure':
        return []
    kinds = {
        'summary': ('concept',),
        'definition': ('concept',),
        'example': ('worked_example',),
        'misconception': ('misconception',),
        'transfer': ('transfer', 'reflection'),
    }.get(answerable_from, (answerable_from,))
    haystack = _normalise(_block_text(entry, kinds))
    if _normalise(answer) and _normalise(answer) in haystack:
        return []
    return [Finding(
        'item_unanswerable', path,
        f'the correct option is not present in the {answerable_from!r} block, so the '
        f'item asks for something the lesson never stated')]


def _audit_shape(course: AuthoredCourse, profile: methodology.AuthoringProfile,
                 *, overlay: bool = False) -> list[Finding]:
    findings: list[Finding] = []
    plan = course.plan
    shape = profile.shape
    # An overlay is a patch on a design somebody else made. Course-level shape rules -
    # how many units, how big the course is, how wide a unit may be - describe *the*
    # course, and applying them to a patch refuses the patch because the course is the
    # course. The rules that survive are the ones a patch can violate on its own terms:
    # whether its own items assess more than one kind of knowing.
    if not overlay:
        if len(plan.units) < shape.min_units or len(plan.units) > shape.max_units:
            findings.append(Finding('course_unit_count', 'course',
                                    f'{len(plan.units)} units; profile {profile.name!r} '
                                    f'allows {shape.min_units}-{shape.max_units}'))
        total = course.concept_count
        if total < shape.min_concepts:
            findings.append(Finding('course_too_small', 'course',
                                    f'{total} concepts; the floor is {shape.min_concepts}'))
        if total > shape.max_concepts:
            findings.append(Finding('course_too_large', 'course',
                                    f'{total} concepts; the ceiling is {shape.max_concepts}'))

        for index, unit in enumerate(plan.units):
            if _words(unit.objective) < 6:
                findings.append(Finding(
                    'unit_objective_thin', f'units[{index}]',
                    'the unit has no one-sentence objective, so nothing states what the '
                    'unit is for'))
            if len(unit.concepts) < shape.concepts_per_unit_min:
                findings.append(Finding(
                    'unit_too_thin', f'units[{index}]',
                    f'{len(unit.concepts)} concepts; a unit needs at least '
                    f'{shape.concepts_per_unit_min}'))
            if len(unit.concepts) > shape.concepts_per_unit_max:
                findings.append(Finding(
                    'unit_too_dense', f'units[{index}]',
                    f'{len(unit.concepts)} concepts; the ceiling per unit is '
                    f'{shape.concepts_per_unit_max}'))

        difficulties = [node.difficulty for node in course.graph.nodes.values()]
        if len(set(difficulties)) < 2 and total > 3:
            findings.append(Finding(
                'difficulty_flat', 'course',
                'every concept has the same difficulty, so the course cannot be sequenced '
                'from easier to harder'))

    # Which kinds of knowing the *course* assesses. Another course-level claim, and it
    # fails an overlay for a reason the overlay cannot fix: the two deeper categories
    # exist only where a written lesson exists, so a patch that deepens one unit - the
    # whole point of the overlay path, and how a 57-concept pack gets covered at all -
    # would be refused until the whole course was written in one pass. In a patch the
    # same observation is still worth making, and still worth reading, so it is reported
    # as a warning: the patch is allowed, and the teacher is told what it does not cover.
    categories = {str(item.get('category') or '') for item in course.questions.values()}
    for required in REQUIRED_CATEGORIES:
        if required not in categories:
            if overlay:
                findings.append(Finding(
                    'category_missing', 'course',
                    f'this patch asks no {required!r} question; the course will assess that '
                    f'kind of knowing only where another pass writes it', 'warning'))
            else:
                findings.append(Finding(
                    'category_missing', 'course',
                    f'no item in the course asks a {required!r} question; the course '
                    f'assesses one kind of knowing only'))
    return findings


def _audit_graph(course: AuthoredCourse) -> list[Finding]:
    findings: list[Finding] = []
    for issue in course.graph.validate():
        findings.append(Finding(f'graph_{issue.kind}', f'concept {issue.concept_id!r}',
                                issue.detail,
                                'error' if issue.severity == 'error' else 'warning'))
    for node in course.graph.nodes.values():
        if not node.summary.strip():
            findings.append(Finding('concept_no_summary', f'concept {node.id!r}',
                                    'the concept has no summary'))
    return findings


def _audit_honesty(course: AuthoredCourse) -> list[Finding]:
    """The provenance checks. Cheap, and the only defence against silent authorship.

    A course whose concepts do not all carry the same origin, or whose plan is not
    recorded, cannot be told apart from a reviewed one later. That is not a
    documentation problem: it is the difference between a learner trusting a course
    because it was reviewed and trusting it because it was well formatted.
    """
    findings: list[Finding] = []
    if not course.plan.digest():
        findings.append(Finding('no_digest', 'course',
                                'the blueprint digest is empty, so the design cannot be '
                                'identified'))
    for concept_id_value, entry in course.concepts.items():
        if entry.get('origin') != ORIGIN:
            findings.append(Finding('origin_missing', f'concept {concept_id_value!r}',
                                    f'origin is {entry.get("origin")!r}, not {ORIGIN!r}'))
        if not entry.get('generated'):
            findings.append(Finding(
                'not_marked_derived', f'concept {concept_id_value!r}',
                'the concept is not marked as derived, so a learner cannot tell it from '
                'hand-written material'))
    return findings


# ------------------------------------------------------------------------- entry

def audit(course: AuthoredCourse, *,
          profile: methodology.AuthoringProfile | None = None,
          overlay: bool = False) -> Audit:
    """Run every check. Returns the findings, not a verdict on whether to publish.

    ``overlay`` relaxes exactly one family of rules: the course-level shape checks that
    describe a whole course's design. Everything that decides whether a *lesson* may ship -
    the answer is in the text, the depth blocks are present, the items cover more than
    recall - runs unchanged, because a patch can fail those on its own.
    """
    resolved = profile or course.profile
    findings: list[Finding] = []
    findings.extend(_audit_shape(course, resolved, overlay=overlay))
    findings.extend(_audit_graph(course))
    findings.extend(_audit_honesty(course))

    by_concept: dict[str, list[dict[str, Any]]] = {cid: [] for cid in course.concepts}
    for item in course.questions.values():
        by_concept.setdefault(str(item.get('concept_id') or ''), []).append(dict(item))

    for concept in course.plan.concepts():
        entry = course.concepts.get(concept.id)
        if entry is None:
            findings.append(Finding('concept_not_materialised', f'concept {concept.id!r}',
                                    'the concept was planned but no lesson was built'))
            continue
        findings.extend(_audit_concept(course, concept, entry, by_concept.get(concept.id, []),
                                       resolved))

    stats = {
        'units': len(course.plan.units),
        'concepts': course.concept_count,
        'questions': course.question_count,
        'items_per_concept': round(course.question_count / max(1, course.concept_count), 2),
        'words_per_concept': round(sum(
            _words(str(block.get('body') or ''))
            for entry in course.concepts.values()
            for block in entry.get('blocks') or []) / max(1, course.concept_count), 1),
        'difficulty_histogram': {
            str(level): sum(1 for node in course.graph.nodes.values()
                            if node.difficulty == level) for level in range(1, 6)},
        'categories': sorted({str(item.get('category') or '')
                              for item in course.questions.values()}),
        'profile': resolved.name,
        'digest': course.plan.digest(),
    }
    return Audit(findings=findings, stats=stats)


def require(course: AuthoredCourse, *,
            profile: methodology.AuthoringProfile | None = None) -> Audit:
    """Audit and raise when the course must not be published.

    The exception carries the blocking findings as data, because the caller that most
    needs them is the drafter's retry loop: it turns each finding into one line of
    feedback for the model, and a message string would have to be parsed back apart.
    """
    result = audit(course, profile=profile)
    if not result.ok:
        raise CourseRefused(result)
    return result


class CourseRefused(ValueError):
    """A synthesized course that failed the audit. Carries the findings, not just prose."""

    def __init__(self, audit_result: Audit):
        self.audit = audit_result
        self.findings = audit_result.errors
        super().__init__('; '.join(str(finding) for finding in self.findings[:6]) or
                         'course refused')

    def feedback(self, limit: int = 12) -> str:
        """The blocking findings as lines a model can act on."""
        lines = [f'- {finding.path}: {finding.message}'
                 for finding in self.findings[:limit]]
        if len(self.findings) > limit:
            lines.append(f'- ({len(self.findings) - limit} more of the same kind)')
        return '\n'.join(lines)


__all__ = ['Audit', 'CourseRefused', 'Finding', 'REQUIRED_CATEGORIES', 'audit', 'require']
