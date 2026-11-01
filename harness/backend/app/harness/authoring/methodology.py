"""The authoring methodology: how this harness designs a course, as inspectable data.

Until this module existed, course design was the one capability the harness did not
own. The courses shipped in ``app/curriculum_packs`` were designed *outside* the
running system - in an editing session, by a person or an agent - and then committed
as JSON. That works for a fixed catalogue and fails at the only question that
matters next: "can the system produce a new course by itself?"

The answer is yes only if the *method* is in the system, not in whoever wrote the
packs. So the method is declared here, in the same spirit as
``app/harness/teaching/config.py`` declares the tutoring method: a profile is a
named, versioned, diffable object, and every authoring decision reads from it.

What a profile fixes
--------------------
**Shape.** How many units, how many concepts per unit, how deep the prerequisite
graph may get. A course that violates the shape is not "unusual", it is unauditable.

**Load.** How much prose a learner meets per concept, per block. The number exists
because a lesson that is 900 words long is not taught, it is assigned.

**Sequence.** Whether prerequisites may cross units, how difficulty ramps, whether a
unit opens by naming what the previous one established.

**Assessment.** How many items per concept, of which kinds, and - the rule that makes
generated items trustworthy - that every correct answer must be *pointable at a
sentence the learner was actually given*. An item whose answer is nowhere in the
lesson measures nothing except the model's confidence.

**Honesty.** Whether a concept may ship with a summary and no worked example. It may
not: the audit refuses, because a course that is a list of titles teaches nothing and
looks complete while doing it.

Why the numbers are what they are
---------------------------------
:data:`LINEAGE` records the finding each section rests on. The citations are real
published work, deliberately not "best practice" hand-waving, and none of them is
cited as evidence that *this* product works - a design rationale is not an efficacy
claim. The distinction matters: a harness that cites research for its own
effectiveness is doing marketing, not design.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping

#: Profile schema version. Bumped when a field changes meaning, so a persisted
#: blueprint that recorded ``version: 1`` is not silently read under new rules.
SCHEMA = 1

#: Where the design of each section comes from. Kept in code, next to the section it
#: justifies, for the same reason ``teaching/config.py`` keeps its lineage: the
#: provenance of a pedagogical rule should be one attribute lookup away, not folklore.
LINEAGE: dict[str, dict[str, str]] = {
    'retrieval_and_spacing': {
        'source': 'Roediger & Karpicke (2006), Psych. Science 17(3); '
                  'Cepeda et al. (2006), Psych. Bulletin 132(3)',
        'finding': 'Recalling material produces more durable retention than re-reading it, '
                   'and spacing those recalls outperforms massing them.',
        'becomes': 'ItemPolicy.retrieval_per_concept; LessonBlockSpec("retrieval") required.',
    },
    'worked_example_fade': {
        'source': 'Sweller & Cooper (1985), Cognition & Instruction 2(1); '
                  'Kalyuga et al. (2003), Educational Psychologist 38(1)',
        'finding': 'Novices learn more from studying a worked example than from solving '
                   'the same problem, but the advantage reverses as expertise grows.',
        'becomes': 'LessonBlockSpec("worked_example") required early, replaced by a '
                   'faded prompt in the last unit of a course.',
    },
    'misconception_targeting': {
        'source': 'Hattie & Timperley (2007), Review of Educational Research 77(1)',
        'finding': 'Feedback changes learning when it names the specific error and what '
                   'to do next, not when it reports that an answer was wrong.',
        'becomes': 'LessonBlockSpec("misconception") required; every distractor carries a '
                   'diagnosis and a next action.',
    },
    'mastery_sequencing': {
        'source': 'Bloom (1984), Educational Researcher 13(6); '
                  'Kulik, Kulik & Bangert-Drowns (1990), Review of Educational Research 60(2)',
        'finding': 'Sequencing on demonstrated prerequisites, with correction before '
                   'moving on, outperforms fixed-pace coverage.',
        'becomes': 'Shape.max_prerequisites, acyclic graph requirement, unit checkpoints.',
    },
    'interleaving': {
        'source': 'Rohrer & Taylor (2007), Instructional Science 35(6)',
        'finding': 'Mixing problem types improves later discrimination between them, even '
                   'though it feels harder and produces worse practice accuracy.',
        'becomes': 'Assessment.interleave_units - checkpoint items draw on earlier units.',
    },
}

#: Block kinds the lesson layer understands. The first four are the ones
#: ``generated_curriculum`` already emits, so a foundry lesson renders through the
#: same client path with no special case; ``worked_example`` and ``misconception`` are
#: the depth a foundry course adds.
BLOCK_KINDS = ('concept', 'worked_example', 'misconception', 'retrieval', 'reflection',
               'transfer')

#: Item kinds, in the order a concept meets them. The order is deliberate: recall
#: before discrimination before application, because an item that asks for transfer
#: before the idea is retrievable measures guessing.
ITEM_KINDS = ('definition_recall', 'prerequisite_structure', 'misconception_repair',
              'application_transfer')


@dataclass(frozen=True)
class BlockSpec:
    """One required block of a lesson, with its word budget."""

    kind: str
    title: str
    min_words: int
    max_words: int
    #: Field on the concept plan that supplies this block's prose. Empty means the
    #: synthesizer composes it from the graph (a structural block, not an authored one).
    source: str = ''
    required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {'kind': self.kind, 'title': self.title, 'min_words': self.min_words,
                'max_words': self.max_words, 'source': self.source,
                'required': self.required}


@dataclass(frozen=True)
class Shape:
    """How big a course may be, and how deep its prerequisite graph may go."""

    min_units: int = 3
    max_units: int = 12
    min_concepts: int = 9
    max_concepts: int = 60
    concepts_per_unit_min: int = 2
    concepts_per_unit_max: int = 6
    #: A concept with more than this many direct prerequisites is a topic, not a concept.
    max_prerequisites: int = 2
    #: Whether a prerequisite may point into a later unit. Forward edges are how a graph
    #: stops being teachable in the order it is presented.
    allow_cross_unit_prerequisites: bool = False
    #: Difficulty ramp by unit position, as a fraction of the course. A course whose
    #: every concept is difficulty 3 is flat and cannot be sequenced.
    difficulty_min: int = 1
    difficulty_max: int = 5


@dataclass(frozen=True)
class Load:
    """How much reading one concept may ask for."""

    max_words_per_block: int = 180
    max_words_per_concept: int = 700
    #: A course whose every summary is one short clause is a glossary. This is the floor.
    min_summary_words: int = 12
    #: Worked examples are steps, not paragraphs. Fewer than this is a hint.
    min_example_steps: int = 2
    max_example_steps: int = 6


@dataclass(frozen=True)
class Assessment:
    """What the learner is asked, and how much of it."""

    #: Items per concept, including the structural ones the generated layer supplies.
    min_items_per_concept: int = 4
    max_items_per_concept: int = 10
    options_per_item: int = 4
    #: Seconds a well-prepared learner should need. Recorded on every item so a
    #: response-time signal has something to be compared against.
    expected_seconds: int = 60
    #: Checkpoint items draw on earlier units, not only the current one.
    interleave_units: bool = True
    #: A unit ends with an applied task, not only items.
    unit_project: bool = True


@dataclass(frozen=True)
class AuthoringProfile:
    """The whole authoring method. Every field is read; nothing is defaulted in code."""

    name: str
    version: int
    shape: Shape
    load: Load
    assessment: Assessment
    blocks: tuple[BlockSpec, ...]
    #: Blocks dropped in the final unit of a course, replaced by a faded prompt. This is
    #: the worked-example fade: the scaffold is removed where the learner should be
    #: carrying the method alone.
    fade_in_final_unit: tuple[str, ...] = ('worked_example',)
    #: Whether a concept may ship without the prose a required block needs. Never, in the
    #: default profile: the audit refuses rather than shipping a title list.
    allow_scaffold_only_concepts: bool = False

    def block(self, kind: str) -> BlockSpec:
        for spec in self.blocks:
            if spec.kind == kind:
                return spec
        raise KeyError(f'Profile {self.name!r} declares no {kind!r} block')

    def to_dict(self) -> dict[str, Any]:
        return {'schema': SCHEMA, 'name': self.name, 'version': self.version,
                'shape': self.shape.__dict__, 'load': self.load.__dict__,
                'assessment': self.assessment.__dict__,
                'blocks': [b.to_dict() for b in self.blocks],
                'fade_in_final_unit': list(self.fade_in_final_unit),
                'allow_scaffold_only_concepts': self.allow_scaffold_only_concepts}


def _default_blocks() -> tuple[BlockSpec, ...]:
    return (
        BlockSpec('concept', 'Core idea', 30, 140, 'summary'),
        BlockSpec('concept', 'What it is, precisely', 25, 140, 'definition'),
        BlockSpec('worked_example', 'Worked example', 40, 180, 'example'),
        BlockSpec('misconception', 'The mistake to expect', 20, 120, 'misconception'),
        BlockSpec('retrieval', 'Retrieve it without notes', 15, 80, ''),
        BlockSpec('transfer', 'Use it somewhere new', 20, 120, 'application'),
    )


def default_profile() -> AuthoringProfile:
    """The method this harness ships with.

    Three units is the floor because a course with two units has no middle: it can
    introduce and it can conclude, but it cannot develop anything. Nine concepts is the
    floor for the same reason the course builder refuses a source under four concepts -
    a four-option item needs three plausible, course-grounded distractors, and a course
    that cannot supply them cannot assess anything.
    """
    return AuthoringProfile(
        name='default',
        version=1,
        shape=Shape(),
        load=Load(),
        assessment=Assessment(),
        blocks=_default_blocks(),
    )


def compact_profile() -> AuthoringProfile:
    """A shorter course: three units, two to three concepts each.

    For a unit of study rather than a year. The load and assessment rules are identical
    to the default profile on purpose - a short course is not a lax one.
    """
    return replace(default_profile(), name='compact',
                   shape=replace(Shape(), min_units=2, max_units=4, min_concepts=5,
                                 max_concepts=14, concepts_per_unit_min=2,
                                 concepts_per_unit_max=3))


def seminar_profile() -> AuthoringProfile:
    """A reading-and-discussion course: fewer items, more transfer, no fade.

    Declared rather than assumed, so a humanities course is not forced through a
    mathematics-shaped method. The prerequisite rules still apply; only the assessment
    mix changes, because a seminar's evidence of understanding is an argument, not a
    four-option item.
    """
    return replace(default_profile(), name='seminar',
                   assessment=replace(Assessment(), min_items_per_concept=4,
                                      unit_project=True),
                   fade_in_final_unit=())


PROFILES: dict[str, AuthoringProfile] = {
    'default': default_profile(),
    'compact': compact_profile(),
    'seminar': seminar_profile(),
}

#: Fields an override may not touch. These decide whether a course can be audited at
#: all, so letting a caller (or a model) relax them would let it author something the
#: audit then has to wave through.
_IMMUTABLE = ('name', 'version')


def profile(name: str = 'default', overrides: Mapping[str, Any] | None = None) -> AuthoringProfile:
    """Resolve a profile by name, applying a validated override.

    An unknown name raises rather than falling back: a blueprint that asked for
    ``"profile": "graduate"`` and silently got ``default`` would be authored under a
    method nobody chose. An override naming a field that does not exist raises for the
    same reason - a typo in ``"max_consepts"`` would otherwise be a silently ignored
    limit, which is worse than a refused request.
    """
    key = (name or 'default').strip().lower()
    base = PROFILES.get(key)
    if base is None:
        raise KeyError(f'Unknown authoring profile {name!r}. Available: {sorted(PROFILES)}')
    if not overrides:
        return base
    return apply_overrides(base, overrides)


def apply_overrides(base: AuthoringProfile, overrides: Mapping[str, Any]) -> AuthoringProfile:
    """Return ``base`` with a small, validated set of changes.

    Only numeric limits and booleans in the three section objects may move. The block
    list and the fade rule are structure, not tuning: changing them changes what a
    course *is*, and that belongs in a named profile, not in a per-course override.
    """
    sections: dict[str, Any] = {'shape': base.shape, 'load': base.load,
                                'assessment': base.assessment}
    changes: dict[str, Any] = {}
    for section_name, values in (overrides or {}).items():
        if section_name in _IMMUTABLE:
            raise ValueError(f'Override may not set {section_name!r}')
        target = sections.get(section_name)
        if target is None:
            raise ValueError(f'Override names unknown section {section_name!r}; '
                             f'expected one of {sorted(sections)}')
        if not isinstance(values, Mapping):
            raise ValueError(f'Override section {section_name!r} must be an object')
        allowed = set(target.__dict__)
        applied = {}
        for key, value in values.items():
            if key not in allowed:
                raise ValueError(f'Override names unknown {section_name}.{key}; '
                                 f'expected one of {sorted(allowed)}')
            expected = type(target.__dict__[key])
            if expected is bool and not isinstance(value, bool):
                raise ValueError(f'{section_name}.{key} must be a boolean')
            if expected is int and (isinstance(value, bool) or not isinstance(value, int)):
                raise ValueError(f'{section_name}.{key} must be an integer')
            applied[key] = value
        changes[section_name] = replace(target, **applied)
    return replace(base, **changes)


def describe(name: str = 'default') -> dict[str, Any]:
    """The profile as JSON, for the API and for a teacher reading what will be enforced."""
    resolved = profile(name)
    return {**resolved.to_dict(), 'lineage': LINEAGE, 'block_kinds': list(BLOCK_KINDS),
            'item_kinds': list(ITEM_KINDS)}


__all__ = ['Assessment', 'AuthoringProfile', 'BLOCK_KINDS', 'BlockSpec', 'ITEM_KINDS',
           'LINEAGE', 'Load', 'PROFILES', 'SCHEMA', 'Shape', 'apply_overrides', 'describe',
           'default_profile', 'profile']
