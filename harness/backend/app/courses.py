"""Course registry: many subjects, one harness.

The harness is not a mathematics app. A *course* is a named, licence-cleared
knowledge graph plus the metadata a learner needs to choose it. Everything the
learner sees - the map, the practice items, the figures - is scoped to the course
they are enrolled in.

Two design decisions are load-bearing here.

1. **Subject kind decides whether the symbolic engine applies.** ``template_for``
   builds a figure by matching a concept against mathematics templates. Handed a
   physics concept it does not fail: it silently returns a generic quadratic. That
   is worse than no figure, because it presents a meaningless curve as though it
   were about Newton's second law. So the subject kind is explicit, and only
   ``mathematics`` courses route through the symbolic engine.

2. **A graph is not a course.** The algebra pack has 164 nodes but only 30 authored
   lessons. The graph gives structure; the lesson layer gives depth. Courses that
   have no authored lessons are still real courses - they are simply served by
   generated content rather than hand-written content, and the registry says so
   rather than pretending otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from .knowledge_graph import KnowledgeGraph, load_pack

PACK_DIR = Path(__file__).resolve().parent / 'curriculum_packs'

#: Subject kinds. Only ``mathematics`` may be routed through the symbolic engine.
MATHEMATICS = 'mathematics'
SCIENCE = 'science'
COMPUTING = 'computing'
SOCIAL_SCIENCE = 'social_science'
#: Language and composition. It exists because ACT English is a real course with its own
#: skill families (organisation, usage, punctuation); folding it into ``social_science``
#: would misreport what the learner is studying. It never uses the symbolic engine.
LANGUAGE_ARTS = 'language_arts'


@dataclass(frozen=True)
class Course:
    """One enrolled course."""

    id: str
    title: str
    subject: str
    subject_kind: str
    description: str
    pack: str
    expected_weeks: int
    #: True when this course has hand-authored lessons and questions behind it.
    authored: bool

    @property
    def uses_symbolic_engine(self) -> bool:
        return self.subject_kind == MATHEMATICS

    def to_dict(self) -> dict[str, Any]:
        return {'id': self.id, 'title': self.title, 'subject': self.subject,
                'subject_kind': self.subject_kind, 'description': self.description,
                'expected_weeks': self.expected_weeks, 'authored': self.authored,
                'uses_symbolic_engine': self.uses_symbolic_engine}


#: Every course the harness ships. Order is the order the picker shows them in.
COURSES: tuple[Course, ...] = (
    Course(
        id='integrated_math_1',
        title='Integrated Mathematics I',
        subject='Mathematics',
        subject_kind=MATHEMATICS,
        description='A full-year integrated mathematics course: number and quantity, algebra, '
                    'functions, geometry and measurement, statistics and probability.',
        pack='algebra_one_year',
        expected_weeks=36,
        authored=True,
    ),
    Course(
        id='physics',
        title='Physics',
        subject='Physics',
        subject_kind=SCIENCE,
        description='Algebra-based physics: measurement and modelling, mechanics, waves and '
                    'optics, electricity and magnetism, thermal and modern physics.',
        pack='physics',
        expected_weeks=36,
        authored=False,
    ),
    Course(
        id='chemistry',
        title='Chemistry',
        subject='Chemistry',
        subject_kind=SCIENCE,
        description='Atomic structure and periodicity, bonding and structure, quantitative '
                    'chemistry, reactions and energetics, equilibrium, organic and analytical.',
        pack='chemistry',
        expected_weeks=36,
        authored=False,
    ),
    Course(
        id='biology',
        title='Biology',
        subject='Biology',
        subject_kind=SCIENCE,
        description='The chemistry of life, cell structure and transport, bioenergetics, '
                    'genetics and inheritance, evolution, and ecology and physiology.',
        pack='biology',
        expected_weeks=36,
        authored=False,
    ),
    Course(
        id='computer_science',
        title='Computer Science',
        subject='Computer Science',
        subject_kind=COMPUTING,
        description='Computational thinking, programming fundamentals, data structures and '
                    'algorithms, systems and networks, and the ethics of computing.',
        pack='computer_science',
        expected_weeks=36,
        authored=False,
    ),
    Course(
        id='earth_space_science',
        title='Earth and Space Science',
        subject='Earth Science',
        subject_kind=SCIENCE,
        description="Earth's place in the universe, plate tectonics and Earth's structure, "
                    'weather and climate, and resources and human impact.',
        pack='earth_space_science',
        expected_weeks=36,
        authored=False,
    ),
    # The six courses the study harness was asked to ship. Each is an original CC0 outline
    # whose units follow the publicly published course framework, with Khan Academy and
    # OpenStax carried as link-only study references rather than as ingested content. Their
    # concept ids are namespaced with the course id (see scripts/build_requested_courses.py)
    # because AP Biology and AP Chemistry genuinely share ideas with the shipped Biology and
    # Chemistry courses, and Algebra 2 shares ideas with the authored algebra course.
    Course(
        id='ap_macroeconomics',
        title='AP Macroeconomics',
        subject='Economics',
        subject_kind=SOCIAL_SCIENCE,
        description='The whole-economy view: scarcity and market fundamentals, national income '
                    'and price determination, the financial sector, stabilisation policy and its '
                    'long-run consequences, and the open economy.',
        pack='ap_macroeconomics',
        expected_weeks=30,
        authored=False,
    ),
    Course(
        id='ap_microeconomics',
        title='AP Microeconomics',
        subject='Economics',
        subject_kind=SOCIAL_SCIENCE,
        description='The firm-and-market view: scarcity and marginal analysis, supply and demand '
                    'with elasticity, production and cost, market structure from perfect '
                    'competition to oligopoly, factor markets, and market failure.',
        pack='ap_microeconomics',
        expected_weeks=30,
        authored=False,
    ),
    Course(
        id='ap_biology',
        title='AP Biology',
        subject='Biology',
        subject_kind=SCIENCE,
        description='The chemistry of life, cell structure and function, cellular energetics, '
                    'cell communication and the cell cycle, heredity, gene expression and '
                    'regulation, natural selection, and ecology.',
        pack='ap_biology',
        expected_weeks=34,
        authored=False,
    ),
    Course(
        id='ap_chemistry',
        title='AP Chemistry',
        subject='Chemistry',
        subject_kind=SCIENCE,
        description='Atomic structure and properties, compound structure and properties, '
                    'properties of substances and mixtures, chemical reactions, kinetics, '
                    'thermodynamics, equilibrium, acids and bases, and applications of '
                    'thermodynamics.',
        pack='ap_chemistry',
        expected_weeks=34,
        authored=False,
    ),
    Course(
        id='ap_psychology',
        title='AP Psychology',
        subject='Psychology',
        subject_kind=SOCIAL_SCIENCE,
        description='The vocabulary of evidence, biological bases of behaviour, cognition, '
                    'development and learning, social psychology and personality, and mental '
                    'and physical health.',
        pack='ap_psychology',
        expected_weeks=30,
        authored=False,
    ),
    Course(
        id='algebra_2',
        title='Algebra 2',
        subject='Mathematics',
        subject_kind=MATHEMATICS,
        description='Polynomial and rational functions, complex numbers, exponents, radicals and '
                    'logarithms, transformations, trigonometry, conic sections, sequences and '
                    'series, probability and matrices.',
        pack='algebra_2',
        expected_weeks=36,
        authored=False,
    ),
    Course(
        id='ap_calculus',
        title='AP Calculus',
        subject='Mathematics',
        subject_kind=MATHEMATICS,
        description='Limits and continuity, differentiation and its applications, integration '
                    'and accumulation, differential equations, applications of integration, and '
                    'the parametric, polar, vector and series topics of the BC course.',
        pack='ap_calculus',
        expected_weeks=36,
        authored=False,
    ),
    # The mathematics on-ramp. Its outline is an original CC0 scope and sequence following
    # the twelve-unit Algebra 1 framework (372 skills), and every unit is anchored to the
    # OpenStax section that teaches it (see the pack's ``textbook_alignment`` metadata and
    # scripts/verify_algebra_1.py). No hand-authored lessons yet, so the generated layer
    # materialises its concepts and practice items like the other graph-only courses.
    Course(
        id='algebra_1',
        title='Algebra 1',
        subject='Mathematics',
        subject_kind=MATHEMATICS,
        description='The algebra on-ramp: expression language, linear equations and '
                    'inequalities, linear functions and modelling, statistics and data, '
                    'systems, functions, exponents and radicals, exponential functions, '
                    'polynomials and factoring, quadratic functions and quadratic equations.',
        pack='algebra_1',
        expected_weeks=36,
        authored=False,
    ),
    # ---- The 2026-11-10 course build ------------------------------------------------
    # Each of these carries an outline under scripts/outlines/ and a verification report
    # under outputs/course_verification_<id>.json. Where a CC BY OpenStax book exists, the
    # units are anchored to real sections that the verifier re-fetches through the licence
    # gate; where none exists (organic chemistry, linear algebra, ACT English, both calculus
    # courses, Earth Science) the pack declares ``no_cc_by_anchor`` with a reason instead of
    # borrowing an unrelated book.
    Course(
        id='astrophysics',
        title='Astrophysics',
        subject='Physics',
        subject_kind=SCIENCE,
        description='Astronomical measurement and the celestial sphere, Newtonian gravity '
                    'and orbits, radiation and magnitudes, spectra, telescopes, binary stars, '
                    'stellar structure and evolution, compact objects, galaxies, cosmology '
                    'and planetary systems.',
        pack='astrophysics',
        expected_weeks=30,
        authored=False,
    ),
    Course(
        id='organic_chemistry',
        title='Organic Chemistry',
        subject='Chemistry',
        subject_kind=SCIENCE,
        description='Structure and bonding, acid-base and electronic effects, stereochemistry, '
                    'curved-arrow mechanisms, substitution and elimination, spectroscopy, '
                    'aromaticity, carbonyl and acyl chemistry, enolates, amines, multistep '
                    'synthesis and bioorganic materials.',
        pack='organic_chemistry',
        expected_weeks=36,
        authored=False,
    ),
    Course(
        id='linear_algebra',
        title='Linear Algebra',
        subject='Mathematics',
        subject_kind=MATHEMATICS,
        description='Vectors and span, elimination and the complete solution, matrix algebra '
                    'and inverses, subspaces and basis, the four fundamental subspaces, '
                    'transformations, orthogonality and least squares, determinants, '
                    'eigenvalues, the spectral theorem and the SVD.',
        pack='linear_algebra',
        expected_weeks=30,
        authored=False,
    ),
    Course(
        id='act_math',
        title='ACT Math',
        subject='Mathematics',
        subject_kind=MATHEMATICS,
        description='ACT mathematics preparation: number and quantity, algebra, functions, '
                    'geometry, statistics and probability, integrating essential skills and '
                    'modelling, matched to the reporting categories and their ranges.',
        pack='act_math',
        expected_weeks=24,
        authored=False,
    ),
    Course(
        id='act_english',
        title='ACT English',
        subject='English',
        subject_kind=LANGUAGE_ARTS,
        description='ACT English preparation: production of writing (purpose, focus, '
                    'organisation, unity, cohesion), knowledge of language (clarity, style) '
                    'and the conventions of standard English (sentence structure, usage, '
                    'punctuation).',
        pack='act_english',
        expected_weeks=20,
        authored=False,
    ),
    Course(
        id='ap_calculus_ab',
        title='AP Calculus AB',
        subject='Mathematics',
        subject_kind=MATHEMATICS,
        description='The AP Calculus AB course: limits and continuity, differentiation and '
                    'its fundamental properties, composite/implicit/inverse functions, '
                    'contextual and analytical applications, integration and accumulation, '
                    'differential equations and applications of integration.',
        pack='ap_calculus_ab',
        expected_weeks=36,
        authored=False,
    ),
    Course(
        id='ap_calculus_bc',
        title='AP Calculus BC',
        subject='Mathematics',
        subject_kind=MATHEMATICS,
        description='The AP Calculus BC course: everything in AB plus integration by parts, '
                    'partial fractions, improper integrals, Euler and logistic models, arc '
                    'length, parametric/polar/vector calculus and infinite sequences and '
                    'series with Taylor polynomials and error bounds.',
        pack='ap_calculus_bc',
        expected_weeks=36,
        authored=False,
    ),
)

COURSE_BY_ID: dict[str, Course] = {course.id: course for course in COURSES}

#: The course a learner gets before they have chosen one.
DEFAULT_COURSE_ID = COURSES[0].id


class UnknownCourse(ValueError):
    """Raised when a course id is not in the registry."""


def course(course_id: str | None) -> Course:
    """Look up a course, falling back to the default for an empty id."""
    key = (course_id or '').strip() or DEFAULT_COURSE_ID
    found = COURSE_BY_ID.get(key)
    if found is None:
        raise UnknownCourse(f'Unknown course {course_id!r}. Available: {sorted(COURSE_BY_ID)}')
    return found


def enrolled_for(user) -> Course:
    """The course a learner account is enrolled in, defaulting rather than failing.

    A stale or unknown id in the database must not take the server down, so an
    unresolvable course falls back to the default and the learner keeps working.

    This lives here, not in the application module, because more than one surface now
    needs it - the API and the playground router both resolve a learner's course - and
    a second copy of "fall back to the default" is a second place for the fallback to
    be forgotten.
    """
    try:
        return course(getattr(user, 'course_id', None))
    except UnknownCourse:
        return course(DEFAULT_COURSE_ID)


@lru_cache(maxsize=len(COURSES))
def graph_for(course_id: str) -> KnowledgeGraph:
    """The knowledge graph for one course, loaded once and cached.

    A missing pack yields an empty graph rather than an exception, so a course that
    was declared but whose pack failed to build degrades to "no concepts yet"
    instead of taking the whole server down.

    The lesson layer is attached here, not left to the caller. The pack on disk knows
    nothing about hand-authored lessons - ``has_lesson`` is written by
    ``curriculum`` when it joins the two layers - so a graph loaded straight from the
    pack reports every node as outline-only. That made the course picker claim the one
    course with 30 authored lessons had none, which is precisely the number a learner
    uses to decide whether a course can teach them anything.
    """
    spec = course(course_id)
    path = PACK_DIR / f'{spec.pack}.json'
    if not path.exists():
        return KnowledgeGraph()
    graph, _ = load_pack(path)
    _attach_lessons(graph)
    return graph


def _attach_lessons(graph: KnowledgeGraph) -> None:
    """Mark the nodes that have a hand-authored lesson behind them.

    Imported lazily: ``curriculum`` pulls in the ingest policy and the whole authored
    lesson layer, and doing that at module import time would make every caller of
    ``courses`` pay for it - and would risk an import cycle if the authored layer ever
    needs the registry.
    """
    try:
        from .curriculum import LESSON_TARGETS
    except Exception:  # noqa: BLE001 - a missing lesson layer must not hide the graph
        return
    for lesson_id, node_id in LESSON_TARGETS.items():
        node = graph.nodes.get(node_id)
        if node is not None:
            node.has_lesson = True
            node.lesson_id = lesson_id


def stats_for(course_id: str) -> dict[str, Any]:
    """Counts a learner needs to judge whether a course is worth enrolling in."""
    graph = graph_for(course_id)
    return graph.stats()


def catalogue() -> list[dict[str, Any]]:
    """Every course with its size, for the picker."""
    out: list[dict[str, Any]] = []
    for spec in COURSES:
        payload = spec.to_dict()
        try:
            payload['stats'] = stats_for(spec.id)
        except Exception as exc:  # noqa: BLE001 - a broken pack must not hide the others
            payload['stats'] = {}
            payload['error'] = str(exc)
        out.append(payload)
    return out


def total_concepts() -> int:
    return sum(len(graph_for(spec.id).nodes) for spec in COURSES)


@lru_cache(maxsize=1)
def _node_index() -> dict[str, str]:
    """Concept id -> owning course id, across every course. Built once, then cached.

    Concept slugs are globally unique because they are derived from distinct scope and
    sequence documents, so a single flat index is unambiguous.
    """
    index: dict[str, str] = {}
    for spec in COURSES:
        for node_id in graph_for(spec.id).nodes:
            index.setdefault(node_id, spec.id)
    return index


def course_for_node(concept_id: str) -> str:
    """Which course owns this concept. Empty string when no course does.

    This is what lets a component that was handed only a concept id - a telemetry
    event, a stored attempt, a memory note - find the graph it belongs to without the
    caller having to thread a course through every call.
    """
    return _node_index().get(concept_id, '')


def graph_for_node(concept_id: str) -> KnowledgeGraph | None:
    """The graph containing this concept, or ``None`` if no course claims it."""
    owner = course_for_node(concept_id)
    return graph_for(owner) if owner else None


def subject_kind_for(concept_id: str) -> str:
    """The subject kind of the course that owns this concept."""
    owner = course_for_node(concept_id)
    return course(owner).subject_kind if owner else MATHEMATICS


__all__ = ['COURSES', 'COURSE_BY_ID', 'DEFAULT_COURSE_ID', 'MATHEMATICS', 'SCIENCE',
           'COMPUTING', 'SOCIAL_SCIENCE', 'Course', 'UnknownCourse', 'course', 'graph_for',
           'stats_for', 'catalogue', 'total_concepts', 'course_for_node', 'graph_for_node',
           'subject_kind_for']
