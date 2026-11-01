"""One routing layer for every course's curriculum.

The harness serves three families of course, and they were built at different times
by different paths:

* the hand-authored mathematics courses, whose concepts live in ``app.curriculum``;
* the generated science, computing and social-science courses, materialised into the
  same registries by ``app.generated_curriculum``;
* the courses a learner builds from their own material, published into those
  registries by ``app.course_builder``.

They converge on one set of registries - ``CONCEPTS``, ``QUESTIONS`` and
``CONCEPT_COURSE`` - and then diverged again at the edges. ``/curriculum``
hand-built its concept payload from a whitelist of keys and the list did not
include ``course_id``, so a lesson from a course the learner had built arrived
without the course it belonged to. Reference cards were composed three different
ways: the mathematics course wrote its own list inline, the generated layer called
``policy.reference_media``, and a learner's own course got ``[]``. Three paths is
three chances for one of them to skip the licence gate.

This module is the single answer to "what is in this course". Every surface that
needs concepts, questions or references for a course asks here, so a course family
cannot be served by a path that forgot the gate, and a concept cannot reach a
client without the course that owns it. The count does not matter to it: two courses
or twenty, a new family registers in the same registries and is routed here for
free, which is the whole point of not writing a route per family.

What this deliberately does *not* do: cache. ``publish`` and ``unregister`` mutate
the registries while the process is running, so a cached route would serve a deleted
course. The work is dict comprehensions over a few hundred entries.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from . import courses, curriculum, figures
from .curriculum import SIMULATION_KINDS
from .ingest import policy

#: The concept fields a learner-facing surface reads, and their defaults.
#:
#: The defaults matter. An authored mathematics concept carries no ``strand``,
#: ``topic``, ``tier`` or ``difficulty``; a generated one carries all four. Reading
#: the registry with ``concept[key]`` worked only because the authored layer happened
#: to have been normalised at import, which is a property of today's data rather than
#: a guarantee. A course that arrives from somewhere new should degrade to a sensible
#: value, not raise a ``KeyError`` in the middle of a page render.
CONCEPT_FIELDS: tuple[tuple[str, Any], ...] = (
    ('id', ''),
    ('title', ''),
    ('unit', ''),
    ('prerequisites', ()),
    ('summary', ''),
    ('strand', ''),
    ('topic', ''),
    ('tier', 'core'),
    ('difficulty', 3),
    ('graph_id', ''),
)


@dataclass(frozen=True)
class CourseRoute:
    """Everything a learner-facing surface needs for one course, resolved once."""

    course: courses.Course
    concepts: dict[str, dict[str, Any]]
    questions: dict[str, dict[str, Any]]
    sources: list[dict[str, Any]]
    share: dict[str, int]

    @property
    def symbolic(self) -> bool:
        """Whether this course routes through the symbolic mathematics engine.

        Only mathematics does. Handed a physics concept, ``template_for`` does not
        fail - it silently returns a generic quadratic, which would present a
        meaningless curve as though it were about the subject the learner is
        studying. See ``app.courses`` for the full reasoning.
        """
        return self.course.uses_symbolic_engine

    def payload(self, concept_id: str) -> dict[str, Any] | None:
        """One concept in the learner-facing shape, or ``None`` if this course lacks it."""
        entry = self.concepts.get(concept_id)
        return None if entry is None else concept_payload(
            entry, course_id=self.course.id, symbolic=self.symbolic)

    def payloads(self) -> list[dict[str, Any]]:
        return [concept_payload(entry, course_id=self.course.id, symbolic=self.symbolic)
                for entry in self.concepts.values()]

    def owns(self, concept_id: str) -> bool:
        """Whether this course is the one that owns this concept."""
        return concept_id in self.concepts

    def stats(self) -> dict[str, Any]:
        """The graph's own counts, for the learner's map and the course header."""
        return courses.graph_for(self.course.id).stats()


def concept_payload(concept: Mapping[str, Any], *, course_id: str, symbolic: bool) -> dict[str, Any]:
    """The canonical learner-facing concept, with its owning course stamped on it.

    ``course_id`` is the field this function exists for. Without it a client holding
    a concept id cannot tell which course the concept came from, which is invisible
    while every learner studies the same shipped course and becomes a real bug the
    moment they build their own.

    ``simulation_kind`` is resolved here rather than at the route for the same reason:
    it depends on the course's subject kind, and a surface that computed it locally
    could disagree with this one about whether a figure is a real model. A mathematics
    concept's kind comes from the maths template map, a science concept's comes from
    the figure map, and a concept that declares its own exploration wins over both -
    the map is a fallback, never a way to override what the concept says it can do.
    """
    payload: dict[str, Any] = {}
    for key, default in CONCEPT_FIELDS:
        value = concept.get(key, default)
        payload[key] = list(value) if isinstance(value, tuple) else value
    # A registry entry that predates the `graph_id` field still resolves: the concept
    # id *is* the node id for every generated and learner-built concept, and the
    # authored layer is the only one that separates the two.
    payload['graph_id'] = payload['graph_id'] or payload['id']
    payload['course_id'] = course_id
    payload['generated'] = bool(concept.get('generated'))
    # A concept is taught unless it says otherwise. Every concept in every registry
    # carries a lesson today; a concept that declared itself untaught would still be
    # schedulable, so the flag is reported rather than assumed either way.
    payload['has_lesson'] = bool(concept.get('has_lesson', True))
    # The concept's own declaration of what it can be explored with, first. Every
    # registry entry carries a ``simulation`` block; the maps below are the fallback
    # for an entry that does not, and resolving in this order is what stops a
    # mathematics course added later (``algebra_2``, ``ap_calculus``) from reporting
    # no simulation at all just because the maths template map predates it.
    declared = concept.get('simulation')
    declared_kind = (str(declared.get('kind') or '')
                     if isinstance(declared, Mapping) else '')
    payload['simulation_kind'] = declared_kind or (
        SIMULATION_KINDS.get(payload['graph_id'], '') if symbolic else figures.CONCEPT_MAP)
    return payload


def _source_card(card: Mapping[str, Any]) -> dict[str, Any]:
    """One course-level reference card, in the single shape the client reads.

    ``license`` and ``licence`` both travel. The native client has rendered
    ``source["license"]`` since before this layer existed, and the licence gate speaks
    ``licence``/``licence_class``. Emitting one spelling and translating at the client
    would put the rights vocabulary in two places; emitting both keeps the gate's
    words authoritative and the existing view working.
    """
    licence = str(card.get('licence') or card.get('license') or '')
    return {
        'title': str(card.get('title') or ''),
        'url': str(card.get('url') or ''),
        'license': licence,
        'licence': licence,
        'licence_class': str(card.get('licence_class') or ''),
        # Every card leaves with an explicit status. A consumer reading "status is
        # absent, therefore ready" would be inferring a rights position from a missing
        # field, which is the same mistake as treating a missing licence as permissive.
        'status': str(card.get('status') or 'reference_link'),
        'scope': str(card.get('scope') or ''),
        'kind': str(card.get('kind') or 'reading'),
        'policy_name': str(card.get('policy_name') or ''),
    }


def references_for(course_id: str, *, commercial: bool = False) -> list[dict[str, Any]]:
    """Every external reference offered for a course, deduplicated and rights-stamped.

    The list is the union of two things, both of which come from the licence gate:

    * the media cards the course's own concepts carry - this is the list the tutor
      cites as curriculum grounding, so a learner reading the top of the course sees
      the same sources the tutor will quote;
    * the course-level cards from :func:`policy.reference_media`, which is what a
      course whose concepts carry no reading list is entitled to by subject.

    A learner-built course gets ``[]``. That is the routed answer, not a gap: the
    material is the learner's own, no external source was consulted, and inventing a
    generic hub link would tell them nothing about what they are studying.
    """
    seen: set[tuple[str, str]] = set()
    cards: list[dict[str, Any]] = []
    for entry in curriculum.course_concepts(course_id).values():
        for card in entry.get('media') or ():
            if not isinstance(card, Mapping):
                continue
            key = (str(card.get('title') or ''), str(card.get('url') or ''))
            if key in seen:
                continue
            seen.add(key)
            cards.append(_source_card(card))
    for card in policy.reference_media(course_id, commercial=commercial):
        key = (str(card.get('title') or ''), str(card.get('url') or ''))
        if key in seen:
            continue
        seen.add(key)
        cards.append(_source_card(card))
    return cards


def route(course_id: str | None) -> CourseRoute:
    """Resolve one course's curriculum. The entry point every surface should use.

    ``courses.course`` is asked first so an unknown id raises ``UnknownCourse`` here,
    at the edge, rather than surfacing as an empty course that looks like a course
    with no content.
    """
    spec = courses.course(course_id)
    return CourseRoute(
        course=spec,
        concepts=curriculum.course_concepts(spec.id),
        questions=curriculum.course_questions(spec.id),
        sources=references_for(spec.id),
        share=curriculum.authored_share(spec.id),
    )


def route_for_user(user) -> CourseRoute:
    """The route for the course a learner is enrolled in.

    A stale or unknown ``course_id`` on the account must not take the server down, so
    an unresolvable id falls back to the default course - the same rule
    ``main.enrolled_course`` applies, kept here so both agree.
    """
    try:
        return route(getattr(user, 'course_id', None))
    except courses.UnknownCourse:
        return route(courses.DEFAULT_COURSE_ID)


__all__ = ['CONCEPT_FIELDS', 'CourseRoute', 'concept_payload', 'references_for', 'route',
           'route_for_user']
