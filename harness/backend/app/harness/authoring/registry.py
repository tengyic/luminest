"""Making an authored course real, and keeping it real across a restart.

A course that exists only in the process that built it is a demo, not a capability. So
this module does the two unglamorous things that turn the foundry into part of the
product:

**It persists the course as an artefact, not as a recipe.** The stored file carries the
blueprint *and* the materialised lessons and items, because what was audited must be
what is served. Re-synthesizing on load would mean a code change could silently alter a
course a learner is halfway through - and the audit that let it in would no longer
describe it. The blueprint is stored too, so the course can be re-built deliberately,
with a new digest, when someone decides to change it.

**It publishes into the registries the rest of the harness already reads.** Not into a
parallel registry with its own routes: into ``courses.COURSE_BY_ID``,
``courses.COURSES``, ``curriculum.CONCEPTS``, ``curriculum.QUESTIONS`` and
``curriculum.CONCEPT_COURSE``. The map, the lesson view, grading, diagnosis, memory,
spaced review, the tutor's concept lookup and the picker all serve an authored course
through the code they already had, which is the only definition of "migrated into the
harness" that means anything.

The patch is additive and idempotent, exactly as ``app.course_builder`` does it: an
unknown id still falls through to the shipped lookup and still raises ``UnknownCourse``,
and with no authored course published the behaviour is identical to before this module
existed. The two patches chain - whichever installs second wraps the first - so a
learner-built course and an authored one can coexist without either knowing about the
other.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping

from ... import courses, curriculum
from ...knowledge_graph import KnowledgeGraph
from . import audit as audit_module
from . import blueprint, synthesize

log = logging.getLogger('luminfest.authoring.registry')

#: On-disk schema for a stored course. Bumped when the record's shape changes; an
#: unreadable record is withheld with its reason rather than crashing the boot.
SCHEMA = 1

#: Directory under ``settings.data_dir``. One file per course, named by course id, so a
#: course can be inspected, diffed and deleted by hand when an operator needs to.
ROOT = 'authored_courses'

#: The shipped catalogue, captured before anything is published. Rebinding
#: ``courses.COURSES`` is how an authored course reaches the picker, and this is what it
#: is rebuilt from on every change - appending to the live tuple would accumulate.
_SHIPPED: tuple[courses.Course, ...] = tuple(courses.COURSES)

#: Published courses, by id. The value is the record, because every consumer of this
#: module (routes, tools, the picker) wants the same few facts.
_RUNTIME: dict[str, 'Record'] = {}
_INSTALLED = False
_HYDRATED = False
_WITHHELD: list[dict[str, str]] = []

#: What an overlay replaced, so withdrawing it can put the shipped course back exactly.
#: Keyed by concept id; populated at publish time from the live registry, which is rebuilt
#: from the packs on every boot. That is why it does not need to be persisted: a restart
#: restores the generated layer first, then replays the overlay on top of it.
_OVERLAY_ORIGINAL: dict[str, dict[str, Any]] = {}

#: The generated items an overlay displaced, so withdrawing it puts them back. Without
#: this, withdrawing the overlay would leave those concepts with *no* items at all - the
#: audit-passed items are ours, the generated four were deleted to stop the lesson and its
#: items disagreeing, and the pack never carried a third set.
_OVERLAY_ITEMS: dict[str, dict[str, Any]] = {}

#: Overlay-replaced course specs, by course id. An overlay does not add a course to the
#: picker; it upgrades one that is already there, so ``authored`` becomes true and the
#: picker's honesty column changes with it.
_OVERLAID: dict[str, courses.Course] = {}


@dataclass
class Record:
    """One authored course, as stored and as served."""

    id: str
    course: courses.Course
    graph: KnowledgeGraph
    concepts: dict[str, dict[str, Any]]
    questions: dict[str, dict[str, Any]]
    blueprint: dict[str, Any]
    audit: dict[str, Any] = field(default_factory=dict)
    digest: str = ''
    created_at: float = 0.0
    updated_at: float = 0.0
    #: ``course`` for a whole course the foundry built; ``overlay`` for lessons written
    #: into a course that already shipped. The two are published differently: a course
    #: adds itself to the catalogue, an overlay deepens a course that is already in it.
    kind: str = 'course'

    def card(self) -> dict[str, Any]:
        """What the picker and the authoring list show."""
        return {
            'id': self.id, 'title': self.course.title, 'subject': self.course.subject,
            'description': self.course.description,
            'expected_weeks': self.course.expected_weeks,
            'concepts': len(self.concepts), 'questions': len(self.questions),
            'origin': 'harness_authoring', 'kind': self.kind,
            'profile': (self.blueprint.get('course') or {}).get('profile') or 'default',
            'author': (self.blueprint.get('course') or {}).get('author') or 'operator',
            'digest': self.digest or _stable_digest(self.blueprint),
            'created_at': self.created_at, 'updated_at': self.updated_at,
            'audit_ok': bool(self.audit.get('ok')),
        }

    def to_document(self) -> dict[str, Any]:
        document = {
            'schema': SCHEMA, 'id': self.id, 'digest': self.digest, 'kind': self.kind,
            'created_at': self.created_at, 'updated_at': self.updated_at,
            'course': {'id': self.course.id, 'title': self.course.title,
                       'subject': self.course.subject,
                       'subject_kind': self.course.subject_kind,
                       'description': self.course.description,
                       'pack': self.course.pack,
                       'expected_weeks': self.course.expected_weeks,
                       'authored': self.course.authored},
            'blueprint': self.blueprint, 'audit': self.audit,
            'concepts': self.concepts, 'questions': self.questions,
        }
        # An overlay's graph is the shipped pack's. Writing a copy into the record would
        # freeze a structure the course does not own, and a later pack revision would then
        # disagree with the record that claims to describe it.
        if self.kind != 'overlay':
            document['graph'] = self.graph.to_pack(name=self.id, title=self.course.title,
                                                   metadata={'origin': synthesize.ORIGIN})
        return document

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> 'Record':
        version = int(document.get('schema') or 0)
        if version != SCHEMA:
            raise ValueError(f'record schema {version} is not readable (reads {SCHEMA})')
        meta = document.get('course') or {}
        course = courses.Course(
            id=str(meta.get('id') or document.get('id') or ''),
            title=str(meta.get('title') or ''), subject=str(meta.get('subject') or ''),
            subject_kind=str(meta.get('subject_kind') or 'custom'),
            description=str(meta.get('description') or ''),
            pack=str(meta.get('pack') or f'foundry/{meta.get("id") or ""}'),
            expected_weeks=int(meta.get('expected_weeks') or 12),
            authored=bool(meta.get('authored')),
        )
        if not course.id:
            raise ValueError('record carries no course id')
        kind = str(document.get('kind') or 'course')
        if kind == 'overlay':
            # The pack owns the graph, so the record must not smuggle a second one in.
            graph = courses.graph_for(course.id)
        else:
            graph = KnowledgeGraph.from_pack(document.get('graph') or {})
        return cls(id=course.id, course=course, graph=graph,
                   concepts=dict(document.get('concepts') or {}),
                   questions=dict(document.get('questions') or {}),
                   blueprint=dict(document.get('blueprint') or {}),
                   audit=dict(document.get('audit') or {}),
                   digest=str(document.get('digest') or ''),
                   created_at=float(document.get('created_at') or 0.0),
                   updated_at=float(document.get('updated_at') or 0.0),
                   kind=kind)


def _stable_digest(document: Mapping[str, Any]) -> str:
    """A content hash of the stored blueprint, for a record written by an older build.

    New records carry the digest the plan computed at authoring time; this fallback
    exists so a record from before that field existed is still identifiable rather than
    anonymous.
    """
    import hashlib
    return hashlib.sha256(json.dumps(document, sort_keys=True,
                                     ensure_ascii=False).encode('utf-8')).hexdigest()[:16]


# ------------------------------------------------------------------------ storage

def root(settings) -> Path:
    return Path(settings.data_dir) / ROOT


def _path(settings, course_id: str) -> Path:
    safe = blueprint.course_id(course_id)
    return root(settings) / f'{safe}.json'


def _write(settings, record: Record) -> Path:
    """Write the record atomically, so a crash cannot leave half a course on disk."""
    path = _path(settings, record.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(record.to_document(), ensure_ascii=False),
                         encoding='utf-8')
    os.replace(temporary, path)
    return path


def store(settings, course: synthesize.AuthoredCourse,
          report: audit_module.Audit | None = None, *,
          replace: bool = False) -> Record:
    """Audit, persist and publish one synthesized course.

    The audit runs here even when the caller already ran it, because this is the last
    point before a course becomes real and the check is cheap. A caller that skipped it -
    a tool, a script, a future route - cannot accidentally publish an unaudited course.
    """
    result = report or audit_module.audit(course)
    if not result.ok:
        raise audit_module.CourseRefused(result)
    existing = get(course.plan.id)
    if existing is not None and not replace:
        raise ValueError(f'An authored course {course.plan.id!r} already exists; pass '
                         f'replace=True to publish a new version')
    now = time.time()
    record = Record(
        id=course.plan.id, course=course.course, graph=course.graph,
        concepts=dict(course.concepts), questions=dict(course.questions),
        blueprint=course.plan.to_dict(), audit=result.to_dict(),
        digest=course.plan.digest(),
        created_at=(existing.created_at if existing else now), updated_at=now,
    )
    _write(settings, record)
    publish(record)
    return record


def store_overlay(settings, course: synthesize.AuthoredCourse,
                  report: audit_module.Audit | None = None, *,
                  replace: bool = False) -> Record:
    """Persist lessons written *into* a shipped course.

    Same contract as :func:`store` - audit first, then write, then publish - with one
    addition: the store is keyed by the shipped course id, so a second run replaces the
    first rather than creating ``ap_microeconomics-2``. That is deliberate. Two overlays
    for one course would mean two answers to "what lesson does this node have", and the
    registry would have to pick one at random.
    """
    result = report or audit_module.audit(course, overlay=True)
    if not result.ok:
        raise audit_module.CourseRefused(result)
    spec = courses.course(course.plan.id)
    if spec.id != course.plan.id:
        raise ValueError(f'{course.plan.id!r} is not a shipped course; an overlay may only '
                         f'deepen a course that already exists')
    for concept_id in course.concepts:
        owner = curriculum.CONCEPT_COURSE.get(concept_id)
        if owner != spec.id:
            raise ValueError(f'Concept {concept_id!r} belongs to {owner or "no course"!r}, '
                             f'not {spec.id!r}; an overlay may not move a concept between '
                             f'courses')
    existing = get(spec.id)
    if existing is not None and existing.kind != 'overlay' and not replace:
        raise ValueError(f'{spec.id!r} already has an authored course record; pass '
                         f'replace=True to overwrite it')
    now = time.time()
    record = Record(
        id=spec.id, course=spec, graph=course.graph,
        concepts=dict(course.concepts), questions=dict(course.questions),
        blueprint=course.plan.to_dict(), audit=result.to_dict(),
        digest=course.plan.digest(),
        created_at=(existing.created_at if existing and existing.kind == 'overlay' else now),
        updated_at=now, kind='overlay',
    )
    _write(settings, record)
    publish(record)
    return record


def delete(settings, course_id: str) -> bool:
    """Remove a course from disk, from every registry, and its images from the index.

    The lesson-image index is keyed by concept id and knows nothing about courses, so a
    withdrawn course would otherwise leave photograph assignments pointing at lessons no
    route can reach - a slow leak of rows and, worse, a concept id that a later course
    reusing that id would silently inherit images from.
    """
    from .. import media

    record = get(course_id)
    path = _path(settings, course_id)
    existed = path.exists()
    if existed:
        path.unlink()
    if record is not None:
        unregister(course_id)
        for concept_id in record.concepts:
            media.forget_lesson_images(settings, str(concept_id))
    return existed or record is not None


def load_all(settings) -> list[Record]:
    """Every stored course, newest first. Unreadable records are withheld, not fatal."""
    directory = root(settings)
    if not directory.exists():
        return []
    records: list[Record] = []
    for path in sorted(directory.glob('*.json')):
        try:
            document = json.loads(path.read_text(encoding='utf-8'))
            records.append(Record.from_document(document))
        except Exception as exc:  # noqa: BLE001 - one bad file must not hide the rest
            log.warning('authored course %s is unreadable: %s', path.name, exc)
            _WITHHELD.append({'file': path.name, 'reason': str(exc)})
    records.sort(key=lambda record: record.updated_at, reverse=True)
    return records


def get(course_id: str) -> Record | None:
    return _RUNTIME.get((course_id or '').strip())


def listing() -> list[dict[str, Any]]:
    return [record.card() for record in
            sorted(_RUNTIME.values(), key=lambda record: record.updated_at, reverse=True)]


def withheld() -> list[dict[str, str]]:
    """Stored courses that could not be published, with the reason. Reported, not hidden."""
    return list(_WITHHELD)


# ---------------------------------------------------------------------- publishing

def _rebind_catalogue() -> None:
    """Rebuild the picker's tuple: the shipped courses, then the authored ones.

    Overlay records are in ``_RUNTIME`` too, and they must be skipped here. An overlay
    names a course that already shipped, so appending its record would list AP
    Microeconomics twice - once with lessons, once without - and the picker would offer a
    learner a choice that is not a choice.
    """
    courses.COURSES = _SHIPPED + tuple(
        record.course for record in
        sorted(_RUNTIME.values(), key=lambda item: item.created_at)
        if record.kind != 'overlay')


def publish(record: Record) -> None:
    """Put one course into the shared registries. Refuses rather than shadowing.

    Three collisions are refused outright, because each would silently change what an
    existing learner is studying: the id of a shipped course, the id of a learner-built
    course, and a concept id that already belongs to a different course.

    An overlay is the one record allowed to name a shipped course id - that is what it is
    for - so it takes its own path, and the collision it must refuse is different: a
    concept that belongs to some *other* course.
    """
    if record.kind == 'overlay':
        _publish_overlay(record)
        return
    shipped = {spec.id for spec in _SHIPPED}
    if record.id in shipped:
        raise ValueError(f'{record.id!r} is a shipped course id; an authored course may '
                         f'not shadow it')
    from ... import course_builder
    if record.id in course_builder.runtime_courses():
        raise ValueError(f'{record.id!r} belongs to a course a learner built')
    for concept_id in record.concepts:
        owner = curriculum.CONCEPT_COURSE.get(concept_id)
        if owner not in (None, record.id):
            raise ValueError(f'Concept id {concept_id!r} already belongs to course '
                             f'{owner!r}')

    _RUNTIME[record.id] = record
    courses.COURSE_BY_ID[record.id] = record.course
    curriculum.CONCEPTS.update(record.concepts)
    curriculum.QUESTIONS.update(record.questions)
    for concept_id in record.concepts:
        curriculum.CONCEPT_COURSE[concept_id] = record.id
    _rebind_catalogue()
    _install()


def _publish_overlay(record: Record) -> None:
    """Deepen a shipped course without touching its structure.

    Four registries are touched, and each one for a reason a learner would notice:

    1. ``CONCEPTS`` - the entry keeps the pack's structural fields and gains the written
       blocks, project and hint. Merged rather than replaced so a field the overlay does
       not carry (a prerequisite added to the pack later) survives.
    2. ``QUESTIONS`` - the generated four "which statement best describes X" items are
       removed for these concepts. Leaving them would mean a lesson whose items test a
       different sentence than the one it teaches, which is the exact failure the audit
       exists to prevent.
    3. The course graph's nodes - ``has_lesson`` and ``lesson_id`` are set, so the map
       draws the lesson badge and ``simulation_node`` resolves the lesson id.
    4. The catalogue - the same course object with ``authored`` now true, because the
       picker's honesty column is a claim about the course, not about the process.
    """
    shipped = {spec.id for spec in _SHIPPED}
    if record.id not in shipped:
        raise ValueError(f'{record.id!r} is not a shipped course; an overlay may only '
                         f'deepen a course that already exists')
    for concept_id, entry in record.concepts.items():
        current = curriculum.CONCEPTS.get(concept_id)
        if current is None:
            raise ValueError(f'Concept {concept_id!r} is not in the curriculum registry')
        _OVERLAY_ORIGINAL.setdefault(concept_id, dict(current))
        merged = dict(current)
        merged.update(entry)
        curriculum.CONCEPTS[concept_id] = merged

    for question_id, item in list(curriculum.QUESTIONS.items()):
        if item.get('concept_id') in record.concepts and item.get('generated'):
            _OVERLAY_ITEMS.setdefault(question_id, dict(item))
            curriculum.QUESTIONS.pop(question_id, None)
    curriculum.QUESTIONS.update(record.questions)

    graph = courses.graph_for(record.id)
    for concept_id in record.concepts:
        node = graph.nodes.get(concept_id)
        if node is not None:
            node.has_lesson = True
            node.lesson_id = concept_id

    _RUNTIME[record.id] = record
    _rebind_catalogue()
    _install()


def unregister(course_id: str) -> None:
    """Withdraw a course from every registry. Its concepts and items go with it."""
    record = _RUNTIME.pop(course_id, None)
    if record is not None and record.kind == 'overlay':
        _withdraw_overlay(record)
        return
    courses.COURSE_BY_ID.pop(course_id, None)
    for concept_id, owner in list(curriculum.CONCEPT_COURSE.items()):
        if owner != course_id:
            continue
        curriculum.CONCEPT_COURSE.pop(concept_id, None)
        curriculum.CONCEPTS.pop(concept_id, None)
    for question_id, item in list(curriculum.QUESTIONS.items()):
        if record is not None and question_id in record.questions:
            curriculum.QUESTIONS.pop(question_id, None)
    _rebind_catalogue()


def _withdraw_overlay(record: Record) -> None:
    """Put a shipped course back the way the pack left it.

    The generated layer is restored from :data:`_OVERLAY_ORIGINAL` rather than
    re-materialised, because re-materialising would also wipe the items of concepts the
    overlay never touched. Withdrawing one overlay must not quietly downgrade the rest of
    the course.
    """
    # Both loops delete from the dict they walk, so they walk a list of its keys. Popping
    # while iterating raised ``dictionary changed size during iteration`` - and the failure
    # landed mid-restore, after some concepts had already been put back.
    for concept_id in list(_OVERLAY_ORIGINAL):
        original = _OVERLAY_ORIGINAL.pop(concept_id)
        if concept_id in record.concepts:
            curriculum.CONCEPTS[concept_id] = dict(original)
    for question_id in list(record.questions):
        curriculum.QUESTIONS.pop(question_id, None)
    for question_id in list(_OVERLAY_ITEMS):
        item = _OVERLAY_ITEMS.pop(question_id)
        if item.get('concept_id') in record.concepts:
            curriculum.QUESTIONS[question_id] = dict(item)
    graph = courses.graph_for(record.id)
    for concept_id in record.concepts:
        node = graph.nodes.get(concept_id)
        if node is not None:
            node.has_lesson = False
            node.lesson_id = ''
    _OVERLAID.pop(record.id, None)
    _rebind_catalogue()


def _install() -> None:
    """Route ``courses.course``/``graph_for`` through the authored registry.

    Wrapping whatever is currently installed - rather than replacing it - is what lets
    this coexist with ``app.course_builder``'s identical patch: whichever module installs
    second wraps the first, a miss falls through both, and an unknown id still raises
    ``UnknownCourse`` exactly as before.
    """
    global _INSTALLED
    if _INSTALLED:
        return
    original_course = courses.course
    original_graph_for = courses.graph_for

    def course(course_id: str | None) -> courses.Course:
        try:
            return original_course(course_id)
        except courses.UnknownCourse:
            key = (course_id or '').strip()
            record = _RUNTIME.get(key)
            if record is not None:
                return record.course
            raise

    def graph_for(course_id: str) -> KnowledgeGraph:
        record = _RUNTIME.get((course_id or '').strip())
        return record.graph if record is not None else original_graph_for(course_id)

    courses.course = course
    courses.graph_for = graph_for
    _INSTALLED = True


def hydrate(settings, *, force: bool = False) -> dict[str, Any]:
    """Publish every stored course. Idempotent, and safe to call on every boot.

    Called from ``create_app`` so a restart is invisible to a learner who enrolled in an
    authored course: the id they hold still resolves, because the record that produced it
    is still on disk.
    """
    global _HYDRATED
    if _HYDRATED and not force:
        return {'published': len(_RUNTIME), 'withheld': withheld(), 'skipped': True}
    _install()
    published, failed = 0, []
    for record in load_all(settings):
        try:
            publish(record)
            published += 1
        except Exception as exc:  # noqa: BLE001 - a broken record must not stop the boot
            log.warning('authored course %s could not be published: %s', record.id, exc)
            failed.append({'id': record.id, 'reason': str(exc)})
            _WITHHELD.append({'file': record.id, 'reason': str(exc)})
    _HYDRATED = True
    return {'published': published, 'failed': failed, 'withheld': withheld(),
            'skipped': False}


def reset() -> None:
    """Withdraw every authored course and forget the hydration flag.

    For tests, and for the one operator action that needs it (rebuilding the catalogue
    from disk). Not a product surface.
    """
    global _HYDRATED
    for course_id in list(_RUNTIME):
        unregister(course_id)
    _OVERLAY_ORIGINAL.clear()
    _OVERLAY_ITEMS.clear()
    _OVERLAID.clear()
    _WITHHELD.clear()
    _HYDRATED = False


__all__ = ['ROOT', 'Record', 'SCHEMA', 'delete', 'get', 'hydrate', 'listing', 'load_all',
           'publish', 'reset', 'root', 'store', 'store_overlay', 'unregister', 'withheld']
