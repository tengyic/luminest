"""The lesson procedure: the run of show, compiled from evidence and available assets.

The move policy decides *this turn*. A learner does not experience turns; they
experience a lesson - a sequence of activities with a beginning, a budget and an end.
Assembling that sequence ad hoc each turn is how a tutor explains for twenty minutes
and never checks anything, or shows a slide deck to someone who already scores 90%.

So the sequence is compiled, not improvised. This module owns one decision and owns it
completely: **which activities run, in which order, for how many minutes, bound to
which concrete artifact, and why.** The answer is a pure function of the evidence
record, the concept, the assets that actually exist on this instance, and the
:class:`~app.harness.teaching.config.ProcedureConfig` - so two identical learners
receive identical lessons, and a decision can be replayed and reviewed.

Four rules shape everything below.

**An activity is chosen by what it does to evidence, not by what it looks like.**
A deck, a video and an explanation are all *input*: they change what the learner has
seen and produce no observation. A simulation, a set of example questions and a
discussion are *commitments*: the learner does something checkable. A lesson that is
all input teaches nothing the harness can see, and a lesson that is all commitment
asks a learner to perform a skill nobody taught them.

**One input per lesson.** Two representations of the same idea in one session is not
variety, it is a second lecture; the evidence that moves is practice, not another
video. The compiler therefore picks exactly one of deck / video / worked example /
explanation and records the others as *skipped, with the reason*. That record is part
of the product: a learner asking "why no video?" gets the true answer rather than a
shrug, and an operator can see which asset is missing.

**Only artifacts that exist may be promised.** A video block appears only when a
concept-specific, licence-cleared video is curated for this course - a generic
provider link is a reference, not a lesson. A simulation block appears only when a
first-party interactive is genuinely bound to the concept; for a non-mathematics
concept the symbolic engine's generic template would draw a parabola and call it
acceleration, which is worse than no simulation. When an asset is absent the block is
skipped with the reason, never faked.

**The budget is a contract.** The learner agreed to twenty minutes. Blocks are added
only while they fit, and trimming removes the least valuable activity first - never
the practice, never the exit. A procedure that overruns is a procedure that ignored
the only constraint the learner actually stated.

The compiler is deliberately independent of the database, the HTTP layer and the
model. :mod:`app.procedure_service` resolves the assets and persists the run; this
module only decides.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .config import default_profile
from .evidence import ConceptFacts, LearnerEvidence

__all__ = ['ACTIVITIES', 'INPUT_KINDS', 'CourseProcedure', 'ProcedureAssets',
           'ProcedureBlock', 'compile_procedure', 'procedure_hash',
           'render_procedure_block', 'served_items']


#: Every activity a lesson may contain, with the two facts the planner needs about it:
#: what role it plays in the evidence, and what the learner does. A closed vocabulary -
#: an activity outside it cannot be planned, rendered or advanced, which is what stops
#: a model (or a future caller) from inventing "quick quiz break".
ACTIVITIES: dict[str, dict[str, str]] = {
    'diagnostic': {
        'role': 'commitment',
        'label': 'Quick check',
        'does': 'Answer a few questions so the lesson starts from evidence rather than '
                'from an assumption about what you know.',
    },
    'deck': {
        'role': 'input',
        'label': 'Slides',
        'does': 'Read a short, ordered deck built from this concept\'s own lesson.',
    },
    'video': {
        'role': 'input',
        'label': 'Video',
        'does': 'Watch a curated video for this concept in its provider\'s player.',
    },
    'explain': {
        'role': 'input',
        'label': 'Explanation',
        'does': 'Work through the idea with the tutor, one step at a time.',
    },
    'worked_example': {
        'role': 'input',
        'label': 'Worked example',
        'does': 'Follow a solved example step by step, then say which step you would '
                'change for a new problem.',
    },
    'simulation': {
        'role': 'commitment',
        'label': 'Interactive',
        'does': 'Change one thing, predict what happens, then check the prediction.',
    },
    'practice': {
        'role': 'commitment',
        'label': 'Example questions',
        'does': 'Answer questions on this concept, with feedback on each one.',
    },
    'discussion': {
        'role': 'commitment',
        'label': 'Explain it back',
        'does': 'Explain the relationship in your own words and defend it against a '
                'counter-example.',
    },
    'recap': {
        'role': 'commitment',
        'label': 'Recap',
        'does': 'Connect this idea to its neighbours and answer one exit question.',
    },
    'close': {
        'role': 'exit',
        'label': 'Stop here',
        'does': 'End the session without adding new material.',
    },
}

#: The activities that *teach* rather than *test*. Exactly one of these runs per lesson.
INPUT_KINDS: frozenset[str] = frozenset({'deck', 'video', 'explain', 'worked_example'})

#: The order trimming removes activities in. The least valuable goes first, and the
#: diagnostic is absent on purpose: for a learner with no evidence it is the block that
#: makes the rest of the lesson more than a guess, so it is the last thing dropped.
#: Practice is also absent - it is shrunk item by item rather than removed, because a
#: lesson without a commitment is a presentation, not a lesson.
_DROP_ORDER: tuple[str, ...] = ('recap', 'discussion', 'simulation', 'video',
                                'worked_example', 'deck', 'explain')

#: Placeholder-free artifact keys. Kept as data so the renderer and the tests agree on
#: what an artifact must carry, instead of each checking its own subset.
_ARTIFACT_KINDS = frozenset({'questions', 'slides', 'video', 'simulation', 'text',
                             'prose', 'dialogue', 'summary', 'stop'})


@dataclass(frozen=True)
class ProcedureAssets:
    """What this instance can actually deliver for this concept, right now.

    The compiler may not go looking for assets - it is a pure function - so the
    resolver hands it a complete, honest inventory. Every optional field carries the
    reason it is empty in ``reasons``, because "no video" and "a video exists but was
    withdrawn" are different facts and the learner-facing skip note must be able to
    say which one happened.
    """

    concept_id: str
    concept_title: str = ''
    course_id: str = ''
    #: The exact slides the harness will build, in order. Empty when the concept has no
    #: authored lesson to build them from.
    deck_sections: tuple[Mapping[str, Any], ...] = ()
    #: One first-party interactive. ``observable`` decides whether its outcome can feed
    #: mastery: a playground game reports what the learner committed to, an exploratory
    #: figure does not.
    simulation: Mapping[str, Any] | None = None
    #: A concept-specific, licence-cleared video. Never a generic provider link.
    video: Mapping[str, Any] | None = None
    worked_example: Mapping[str, Any] | None = None
    #: Authored retrieval prompts, verbatim, for the in-chat example questions.
    practice_prompts: tuple[str, ...] = ()
    #: The concept's scored items, in the order the scheduler would serve them.
    #:
    #: A commitment block binds the ids it promises, and that list is the whole point:
    #: before it existed a practice block said "3 example questions" and carried no
    #: questions, so a client could mark it done without one ever being served or
    #: answered. The ids come from the resolver, not from the compiler, because ordering
    #: them needs the learner's states and the compiler is a pure function of its inputs.
    #: Empty means "no scored items exist for this concept", which the compiler reports
    #: rather than filling with something invented.
    practice_items: tuple[str, ...] = ()
    #: How many scored items the question bank holds for this concept.
    practice_count: int = 0
    prerequisites: tuple[str, ...] = ()
    dependants: tuple[str, ...] = ()
    #: kind -> why it is unavailable. Published, not hidden.
    reasons: Mapping[str, str] = field(default_factory=dict)

    def unavailable(self, kind: str) -> str:
        return str(self.reasons.get(kind) or '')

    def summary(self) -> dict[str, Any]:
        return {
            'deck': ({'slides': len(self.deck_sections),
                      'headings': [str(s.get('heading') or '') for s in self.deck_sections]}
                     if self.deck_sections else None),
            'simulation': dict(self.simulation) if self.simulation else None,
            'video': dict(self.video) if self.video else None,
            'worked_example': bool(self.worked_example),
            'questions': self.practice_count,
            'unavailable': dict(self.reasons),
        }


@dataclass(frozen=True)
class ProcedureBlock:
    """One activity, bound to one artifact, with the evidence rule that chose it."""

    order: int
    kind: str
    minutes: int
    title: str
    purpose: str
    why: str
    artifact: Mapping[str, Any] = field(default_factory=dict)
    produces: tuple[str, ...] = ()
    optional: bool = True

    @property
    def role(self) -> str:
        return ACTIVITIES[self.kind]['role']

    @property
    def label(self) -> str:
        return ACTIVITIES[self.kind]['label']

    def to_dict(self) -> dict[str, Any]:
        return {'order': self.order, 'kind': self.kind, 'label': self.label,
                'role': self.role, 'minutes': self.minutes, 'title': self.title,
                'purpose': self.purpose, 'why': self.why,
                'artifact': dict(self.artifact), 'produces': list(self.produces),
                'optional': self.optional}


@dataclass(frozen=True)
class CourseProcedure:
    """The compiled lesson: the blocks, what was left out, and the reasoning.

    ``skipped`` is not a debug field. A lesson is defined as much by what it refuses to
    do as by what it does, and every entry there is a decision a learner or an operator
    may legitimately ask about ("why no video?"). Keeping only the chosen blocks would
    make the refusals invisible and the lesson unauditable.
    """

    concept_id: str
    concept_title: str
    course_id: str
    blocks: tuple[ProcedureBlock, ...] = ()
    skipped: tuple[Mapping[str, str], ...] = ()
    budget_minutes: int = 0
    total_minutes: int = 0
    profile_name: str = 'default'
    assets: Mapping[str, Any] = field(default_factory=dict)
    rationale: str = ''
    enabled: bool = True
    version: str = '1'

    @property
    def kinds(self) -> tuple[str, ...]:
        return tuple(block.kind for block in self.blocks)

    @property
    def current(self) -> ProcedureBlock | None:
        return self.blocks[0] if self.blocks else None

    def block(self, order: int) -> ProcedureBlock | None:
        for item in self.blocks:
            if item.order == order:
                return item
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            'concept_id': self.concept_id,
            'concept_title': self.concept_title,
            'course_id': self.course_id,
            'profile': self.profile_name,
            'version': self.version,
            'hash': procedure_hash(self),
            'enabled': self.enabled,
            'budget_minutes': self.budget_minutes,
            'total_minutes': self.total_minutes,
            'blocks': [block.to_dict() for block in self.blocks],
            'skipped': [dict(row) for row in self.skipped],
            'assets': dict(self.assets),
            'rationale': self.rationale,
        }


# --------------------------------------------------------------------- the compiler


def _budget(requested: Any, cfg) -> int:
    """The session length, clamped to the profile's declared bounds.

    A caller may ask for fewer minutes (a learner with ten minutes before a lecture) but
    never fewer than the minimum a lesson can run in, and never more than the profile
    allows. A typo of ``600`` becomes the maximum rather than a six-hour plan.
    """
    try:
        value = int(requested)
    except (TypeError, ValueError):
        value = cfg.max_minutes
    return max(cfg.min_minutes, min(cfg.max_minutes, value))


def _minutes_for(kind: str, cfg) -> int:
    return int(cfg.minutes.get(kind, cfg.default_minutes))


def _practice_size(evidence: LearnerEvidence, assets: ProcedureAssets, cfg) -> int:
    """How many example questions this learner gets, and why.

    The size is not a constant. A learner below the mastery threshold gets the floor
    done properly - more items at that point is more failure, not more practice. A
    consolidating learner gets one more, because the goal has shifted from accuracy to
    durability. A *second* item is added when the interactive is unobservable: the
    harness saw nothing inside an exploratory figure, so the only honest way to learn
    something from that block is to ask a question afterwards.
    """
    count = int(cfg.practice_min_items)
    if evidence.mastery >= 0.75:
        count += 1
    if evidence.mastery >= 0.9:
        count += 1
    if assets.simulation and not assets.simulation.get('observable', False):
        count += 1
    available = int(assets.practice_count or 0)
    if available:
        count = min(count, available)
    return max(1, min(int(cfg.practice_max_items), count))


def _video_first(evidence: LearnerEvidence) -> bool:
    """Whether a video should orient this learner before any other input.

    Only on first exposure. A video is excellent at *introducing* a concept and poor at
    repairing a specific error - a learner who has already attempted it needs the
    representation their error points at, not a four-minute overview.

    The subject gate that used to sit here admitted only science, social science and
    computing, on the grounds that a mathematics concept with an authored deck is better
    served by the deck's own structure. That was reversed by operator decision: a curated,
    embed-verified video is the fastest way to put a learner in front of the idea, and the
    deck is still there for consolidation on the next pass. The caller already requires
    ``assets.video``, so "no video curated" still means "the deck opens", and the subject
    no longer decides it - what exists does.
    """
    return evidence.attempts == 0


def _simulation_gate(evidence: LearnerEvidence, assets: ProcedureAssets, cfg,
                     *, diagnostic: bool) -> tuple[bool, str]:
    """Whether the interactive runs, and the sentence that explains the answer."""
    sim = assets.simulation
    if not sim:
        return False, (assets.unavailable('simulation')
                       or 'No first-party interactive is bound to this concept.')
    if evidence.simulation_touched:
        return False, ('An interactive was already used in this session; a second run '
                       'adds novelty without new information.')
    if evidence.mastery < cfg.simulation_min_mastery and not diagnostic:
        return False, (f'Mastery {evidence.mastery:.2f} is below the '
                       f'{cfg.simulation_min_mastery:.2f} needed to predict what the '
                       'interactive will do, and nothing has oriented the learner yet. '
                       'An interaction without a prediction is a toy, not an experiment.')
    if (evidence.mastery >= cfg.simulation_skip_mastery
            and evidence.top_error != 'procedural'):
        return False, (f'Mastery {evidence.mastery:.2f} is at or above the '
                       f'{cfg.simulation_skip_mastery:.2f} point where the mechanic is '
                       'already fluent; exploring it again teaches nothing new.')
    return True, ''


def compile_procedure(facts: ConceptFacts, evidence: LearnerEvidence,
                      assets: ProcedureAssets, profile=None, *,
                      minutes_budget: int = 20,
                      recent_kinds: Sequence[str] = ()) -> CourseProcedure:
    """Compile this learner's lesson on this concept, right now.

    Deterministic: the same evidence, assets, profile and budget always produce the same
    blocks in the same order. Nothing here reads the clock, the database or the network,
    which is what makes a lesson reviewable after the fact.

    ``recent_kinds`` is what ran in the learner's last couple of sessions. It exists so
    the same deck is not served three days running: repetition of an *input* is the one
    form of repetition that produces no new evidence at all.
    """
    profile = profile or default_profile()
    cfg = profile.procedure
    budget = _budget(minutes_budget, cfg)
    recent = {str(kind) for kind in recent_kinds}

    if not cfg.enabled:
        return CourseProcedure(
            concept_id=facts.id, concept_title=facts.title,
            course_id=assets.course_id, budget_minutes=budget, enabled=False,
            assets=assets.summary(), profile_name=profile.name,
            rationale='The lesson procedure is switched off on this instance; the '
                      'tutor follows the move policy only.')

    skipped: list[dict[str, str]] = []
    blocks: list[ProcedureBlock] = []

    def skip(kind: str, reason: str) -> None:
        # One entry per activity, and the *latest* reason wins. A block that was first
        # "replaced by the deck" and then dropped for budget must not leave the learner
        # reading the superseded explanation: the operative reason is the last one.
        row = {'kind': kind, 'label': ACTIVITIES[kind]['label'], 'reason': reason}
        for index, existing in enumerate(skipped):
            if existing['kind'] == kind:
                skipped[index] = row
                return
        skipped.append(row)

    def push(kind: str, minutes: int, title: str, purpose: str, why: str,
             artifact: Mapping[str, Any] | None = None,
             produces: Sequence[str] = (), optional: bool = True) -> None:
        if kind in {'diagnostic', 'practice'} and not assets.practice_items:
            skip(kind, 'No scored items are available for this concept. Teaching can '
                       'continue, but this lesson cannot produce quiz evidence until '
                       'the course question bank is rebuilt.')
            return
        blocks.append(ProcedureBlock(
            order=len(blocks) + 1, kind=kind, minutes=max(1, int(minutes)),
            title=title, purpose=purpose, why=why,
            artifact=dict(artifact or {}), produces=tuple(produces),
            optional=optional))

    # ---- the two stop conditions ----------------------------------------
    # Both mean "do not start a lesson". Overload is the more specific of the two: a
    # learner whose recent attempts are fast and wrong is not helped by a shorter
    # version of the thing that is failing, so the session ends rather than shrinking.
    if evidence.frustrated:
        push('close', _minutes_for('close', cfg), 'Stop here',
             ACTIVITIES['close']['does'],
             'Recent attempts are fast and wrong, the signature of overload. Adding '
             'material now - of any kind - is one more failure, so the lesson ends '
             'instead of being rescheduled.', {'kind': 'stop', 'reason': 'overload'},
             produces=(), optional=False)
        for kind in ('diagnostic', 'deck', 'video', 'explain', 'worked_example',
                     'simulation', 'practice', 'discussion', 'recap'):
            skip(kind, 'Not offered: the learner is overloaded, and the useful '
                       'intervention is a shorter session, not another activity.')
        return _finish(facts, assets, profile, budget, blocks, skipped,
                       'Session closed on the overload rule; no new material was added.')

    if evidence.session_minutes >= profile.difficulty.long_session_minutes:
        push('close', _minutes_for('close', cfg), 'Stop here',
             ACTIVITIES['close']['does'],
             f'{evidence.session_minutes:.0f} minutes of measured interaction exceeds '
             f'the {profile.difficulty.long_session_minutes:.0f}-minute point where '
             'continued instruction stops paying for itself.',
             {'kind': 'stop', 'reason': 'over_budget'}, optional=False)
        for kind in ('diagnostic', 'deck', 'video', 'explain', 'worked_example',
                     'simulation', 'practice', 'discussion', 'recap'):
            skip(kind, 'Not offered: the session has already run past its useful '
                       'length.')
        return _finish(facts, assets, profile, budget, blocks, skipped,
                       'Session closed on the long-session rule.')

    # ---- 1. diagnostic ---------------------------------------------------
    # No evidence means no basis for choosing an input. Two items buy more information
    # than a guess about what the learner needs, and they are the only block that can
    # legitimately run before anything has been taught.
    diagnostic = False
    diagnostic_items: list[str] = []
    if evidence.attempts == 0:
        diagnostic = bool(assets.practice_items)
        size = max(1, int(cfg.diagnostic_items))
        if assets.practice_count:
            size = min(size, assets.practice_count)
        diagnostic_items = _promised_items(assets, size)
        push('diagnostic', _minutes_for('diagnostic', cfg), 'Quick check',
             ACTIVITIES['diagnostic']['does'],
             'No scored attempt exists for this concept, so there is no evidence to '
             'teach against yet. Two low-stakes questions cost three minutes and '
             'replace an assumption with a measurement.',
             {'kind': 'questions', 'mode': 'practice', 'concept_id': facts.id,
              'count': len(diagnostic_items) or size, 'purpose': 'diagnostic',
              'scored': True, 'items': diagnostic_items},
             produces=('accuracy',))
    else:
        skip('diagnostic', f'Not needed: {evidence.attempts} recorded attempt(s) '
                           'already say where this learner is, and a diagnostic would '
                           're-measure the record.')

    # ---- 2. the one input block -----------------------------------------
    accuracy = evidence.recent_accuracy
    capable = ((accuracy is not None and accuracy >= cfg.skip_input_accuracy)
               or evidence.mastery >= cfg.skip_input_mastery)
    input_kind = ''
    if capable:
        detail = (f'measured accuracy {accuracy:.2f}' if accuracy is not None
                  else f'mastery {evidence.mastery:.2f}')
        skip('deck', f'Not needed: {detail} is at or above the '
                     f'{cfg.skip_input_accuracy:.2f} bar, so practice teaches this '
                     'learner and a deck would spend the budget on what they know.')
        skip('video', 'Not needed: the learner is already answering this concept at '
                      'the input-skip bar; a video would be review, not orientation.')
        skip('worked_example', 'Not needed: the learner is already answering this '
                               'concept at the input-skip bar.')
        skip('explain', 'Not needed: the learner is already answering this concept at '
                        'the input-skip bar.')
    elif evidence.top_error == 'procedural' and assets.worked_example:
        input_kind = 'worked_example'
        skip('deck', 'Replaced by the worked example: the recorded error is '
                     'procedural, and a solved example repairs a wrong *process* in a '
                     'way an ordered deck does not.')
        skip('video', 'Replaced by the worked example: a video shows someone else\'s '
                      'process, while the authored example can be stopped at the exact '
                      'step this learner gets wrong.')
        skip('explain', 'Replaced by the worked example, which carries the same '
                        'explanation with a concrete solved instance.')
    elif _video_first(evidence) and assets.video:
        input_kind = 'video'
        skip('deck', 'Replaced by the video: this is first exposure to the concept and a '
                     'verified video is curated for it, so the video orients and one input '
                     'per lesson is the rule. The deck is the consolidation tool, not the '
                     'opener.')
        skip('worked_example', 'Not this lesson: orientation comes first; a worked '
                               'example is for repairing a process the learner has '
                               'already attempted.')
        skip('explain', 'Replaced by the video, which orients the same idea without '
                        'spending the tutor turn.')
    elif assets.deck_sections and 'deck' not in recent:
        input_kind = 'deck'
        skip('video', assets.unavailable('video')
             or 'Replaced by the deck: the deck is built from this concept\'s own '
                'authored lesson and one input per lesson is the rule.')
        skip('worked_example', 'Not this lesson: a structured first pass through the '
                               'concept comes before a single solved instance.')
        skip('explain', 'Replaced by the deck, which covers the same ground in a form '
                        'the learner can revisit.')
    elif assets.video:
        input_kind = 'video'
        skip('deck', 'No deck is available for this concept (or one was already shown '
                     'recently), so the verified video carries the orientation.')
        skip('worked_example', 'Not this lesson: orientation comes first.')
        skip('explain', 'Replaced by the video, which orients the same idea.')
    elif assets.worked_example:
        input_kind = 'worked_example'
        skip('deck', 'No deck is available for this concept, so the authored worked '
                     'example carries the teaching.')
        skip('video', assets.unavailable('video') or 'No verified video is curated '
                                                     'for this concept.')
        skip('explain', 'Replaced by the worked example, which is the same explanation '
                        'with a concrete instance.')
    else:
        input_kind = 'explain'
        skip('deck', assets.unavailable('deck')
             or 'No authored lesson exists to build a deck from.')
        skip('video', assets.unavailable('video')
             or 'No verified, concept-specific video is curated for this course.')
        skip('worked_example', assets.unavailable('worked_example')
             or 'This concept has no authored worked example.')

    if input_kind:
        block = _input_block(input_kind, facts, evidence, assets, cfg)
        push(block['kind'], block['minutes'], block['title'], block['purpose'],
             block['why'], block['artifact'], produces=block['produces'])

    # ---- 3. the interactive ---------------------------------------------
    # After the input, never before: a learner predicts what a model will do only once
    # they have something to predict with. The gate states its own refusal.
    include_sim, sim_reason = _simulation_gate(evidence, assets, cfg,
                                               diagnostic=diagnostic)
    if include_sim:
        sim = assets.simulation or {}
        observable = bool(sim.get('observable'))
        push('simulation', _minutes_for('simulation', cfg),
             # A game's own title can be a full sentence; the card heading needs a label.
             # The artifact line keeps the exact name, so nothing is lost by shortening.
             str(sim.get('title') or 'Interactive')[:90],
             ACTIVITIES['simulation']['does'],
             ('A first-party interactive is bound to this concept and the learner has '
              'enough grasp to predict its behaviour. '
              + ('It reports what was committed to, so the run counts as evidence.'
                 if observable else
                 'It is exploratory: it reports nothing, so a scored check must follow '
                 'for the harness to learn anything from it.')),
             {**dict(sim), 'kind': 'simulation', 'concept_id': facts.id},
             produces=('mastery',) if observable else ())
    else:
        skip('simulation', sim_reason or 'No first-party interactive is bound to this '
                                         'concept.')

    # ---- 4. practice -----------------------------------------------------
    # Always present. This is the block that produces evidence, and a lesson without it
    # is a presentation. Its size is evidence-driven, and its prompts are the authored
    # retrieval items verbatim so the tutor cannot paraphrase them into something easier.
    size = _practice_size(evidence, assets, cfg)
    # Practice is priced per item rather than per block. A fixed five-minute block made
    # a two-item check cost the same as a four-item one, which is how a six-minute
    # session ended up unable to afford a diagnostic and a single question.
    practice_minutes = max(2, math.ceil(size * float(cfg.practice_minutes_per_item)))
    push('practice', practice_minutes,
         f'{size} example question' + ('s' if size != 1 else ''),
         ACTIVITIES['practice']['does'],
         ('Practice is the only activity that produces a scored observation. Its size '
          'is set by mastery: a learner below the threshold gets the floor done '
          'properly, and a consolidating learner gets one more for durability. '
          + ('One extra item is added because the interactive before it was '
             'unobservable and the harness saw nothing inside it.'
             if assets.simulation and not assets.simulation.get('observable', False)
             else 'The scheduler chooses the items; the harness chooses how many.')),
         {'kind': 'questions', 'mode': 'practice', 'concept_id': facts.id,
          'count': size, 'selection': 'scheduler',
          'items': _practice_pool(assets, diagnostic_items),
          'examples': [prompt for prompt in assets.practice_prompts[:2]]},
         produces=('attempts', 'mastery'), optional=False)

    # ---- 5. discussion ---------------------------------------------------
    # A conceptual error at adequate mastery is the one case where saying it aloud is
    # the intervention: the wrong model is in the learner's words, not in their marks.
    if (evidence.top_error == 'conceptual'
            and evidence.mastery >= profile.difficulty.mastery_threshold):
        push('discussion', _minutes_for('discussion', cfg), 'Explain it back',
             ACTIVITIES['discussion']['does'],
             'The recorded errors are conceptual and mastery '
             f'{evidence.mastery:.2f} is high enough to reason from, so stating the '
             'relationship aloud is what surfaces a wrong model - a correct '
             'explanation from the tutor does not.',
             {'kind': 'dialogue', 'concept_id': facts.id,
              'prompt': 'Explain the relationship in your own words, then say what '
                        'would have to change for it to stop being true.'})
    else:
        skip('discussion', 'Not this lesson: a discussion needs a conceptual error to '
                           'surface and enough mastery to reason from; neither holds '
                           'right now.')

    # ---- 6. recap --------------------------------------------------------
    # Only if there is a structure to connect and budget left to connect it.
    connect = list(assets.prerequisites[:2]) + list(assets.dependants[:2])
    if connect and evidence.mastery >= profile.difficulty.mastery_threshold:
        push('recap', _minutes_for('recap', cfg), 'Recap',
             ACTIVITIES['recap']['does'],
             f'Mastery {evidence.mastery:.2f} is at or above the '
             f'{profile.difficulty.mastery_threshold:.2f} threshold and this concept '
             'has neighbours in the graph, so making the structure explicit is worth '
             'more than another isolated item.',
             {'kind': 'summary', 'concept_id': facts.id, 'connect': connect,
              'exit_question': 'In one sentence, how does this idea connect to the '
                               'concept before it?'})
    else:
        skip('recap', 'Not this lesson: there is not yet a structure to connect, or the '
                      'concept has no recorded neighbours.')

    # ---- 7. fit the budget ----------------------------------------------
    blocks = _allocate(blocks, budget, cfg, skip,
                       bank_size=int(assets.practice_count or 0))

    return _finish(facts, assets, profile, budget, blocks, skipped,
                   _rationale(evidence, blocks, skipped, budget, profile))


def _input_block(kind: str, facts: ConceptFacts, evidence: LearnerEvidence,
                 assets: ProcedureAssets, cfg) -> dict[str, Any]:
    """Build the chosen input block, with its exact artifact binding.

    Kept as one function so the four inputs cannot drift into four different notions of
    "why this one". The caller has already decided *which*; this decides *what it
    carries*.
    """
    minutes = _minutes_for(kind, cfg)
    if kind == 'deck':
        return {'kind': 'deck', 'minutes': minutes,
                # The card heading a learner reads. "5 slides" is a count, not a title;
                # the slide count belongs in the artifact line, where it is a fact about
                # what will be presented rather than the name of the activity.
                'title': 'Lesson deck',
                'purpose': ACTIVITIES['deck']['does'],
                'why': ('First exposure is better served by an ordered, revisitable '
                        'deck built from this concept\'s own authored lesson than by a '
                        'single worked instance.'
                        if evidence.attempts == 0 else
                        'Mastery is below the consolidation point and no verified video '
                        'is curated, so the authored deck is the honest first pass.'),
                'artifact': {'kind': 'slides', 'concept_id': facts.id,
                             # Carried so the materialiser can title the deck without
                             # re-reading the course; it is not part of the hash. The
                             # resolver's title wins over the graph's: it is the authored
                             # lesson name, which is what a deck header should say.
                             'concept_title': assets.concept_title or facts.title,
                             'sections': [dict(section) for section in assets.deck_sections],
                             'slide_count': len(assets.deck_sections),
                             'tool': 'generate_slides'},
                'produces': ()}
    if kind == 'video':
        video = dict(assets.video or {})
        return {'kind': 'video', 'minutes': minutes,
                'title': str(video.get('title') or 'Video'),
                'purpose': ACTIVITIES['video']['does'],
                'why': ('This is first exposure to a concept whose subject is a '
                        'phenomenon or a process, and a verified, concept-specific '
                        'video is curated for it: watching it orients the learner '
                        'before they commit to an answer.'),
                'artifact': {'kind': 'video', 'concept_id': facts.id,
                             'provider': video.get('provider', ''),
                             'title': video.get('title', ''),
                             'channel': video.get('channel', ''),
                             'watch_url': video.get('watch_url', ''),
                             'embed_url': video.get('embed_url', ''),
                             'licence_class': video.get('licence_class', 'embed_only'),
                             'attribution': video.get('attribution', ''),
                             'verify_on_open': True},
                'produces': ()}
    if kind == 'worked_example':
        example = dict(assets.worked_example or {})
        return {'kind': 'worked_example', 'minutes': minutes,
                'title': 'Worked example',
                'purpose': ACTIVITIES['worked_example']['does'],
                'why': ('The recorded error is procedural, and a solved example can be '
                        'stopped at the exact step this learner gets wrong - which is '
                        'the only way to repair a wrong process.'),
                'artifact': {'kind': 'text', 'concept_id': facts.id,
                             'body': str(example.get('body') or ''),
                             'block_index': int(example.get('block_index') or 0)},
                'produces': ()}
    return {'kind': 'explain', 'minutes': minutes,
            'title': 'Explanation',
            'purpose': ACTIVITIES['explain']['does'],
            'why': ('No deck, verified video or worked example is available for this '
                    'concept, so the tutor teaches it directly rather than pretending '
                    'an asset exists.'),
            'artifact': {'kind': 'prose', 'concept_id': facts.id},
            'produces': ()}


def _allocate(blocks: list[ProcedureBlock], budget: int, cfg, skip,
              *, bank_size: int = 0) -> list[ProcedureBlock]:
    """Choose the lesson's final shape under the budget, by priority rather than by cut.

    Building the richest lesson and then chopping its tail produces the wrong lesson: a
    twelve-minute session would lose its deck while keeping four questions, because the
    deck happened to be earlier in the list. Allocation instead spends the budget in a
    fixed order of value:

    1. one practice item - a lesson with no commitment is a presentation;
    2. the diagnostic, when the learner has no evidence;
    3. the one input block - teaching, when there is budget to teach;
    4. practice up to its preferred size - the evidence the lesson exists to produce;
    5. the interactive - a second commitment, valuable but not essential;
    6. a discussion and a recap - the closing moves;
    7. any remaining budget, as extra practice items.

    Each step either fits or is refused with the budget as the reason, so a short lesson
    is a *smaller* lesson rather than a truncated one.

    ``bank_size`` is the number of scored items that actually exist for this concept.
    Leftover budget buys more practice, but never more questions than the bank holds: a
    card reading "4 example questions" over an artifact that can only fill one is a lie in
    the interface, and the learner finds out at question two.
    """
    by_kind: dict[str, ProcedureBlock] = {block.kind: block for block in blocks}
    practice = by_kind.pop('practice', None)
    chosen: list[ProcedureBlock] = []
    total = 0

    def add(block: ProcedureBlock | None) -> bool:
        nonlocal total
        if block is None:
            return False
        if total + block.minutes > budget:
            skip(block.kind, f'Dropped to fit the {budget}-minute budget; the activity '
                             'was appropriate, the session is simply too short for it.')
            return False
        chosen.append(block)
        total += block.minutes
        return True

    # 1. one practice item, always. The size the evidence asked for is remembered so
    # step 4 can grow back toward it if the budget allows.
    preferred = _practice_count_of(practice) if practice else 1
    practice_block = _set_practice(practice, 1, cfg) if practice else None
    if practice_block is not None:
        chosen.append(practice_block)
        total += practice_block.minutes
        practice = practice_block

    # 2. the diagnostic.
    add(by_kind.pop('diagnostic', None))

    # 3. the single input block.
    for kind in ('worked_example', 'deck', 'video', 'explain'):
        candidate = by_kind.pop(kind, None)
        if candidate is not None:
            add(candidate)
            break

    # 4. practice up to the size the evidence asked for.
    if practice is not None:
        while preferred and _practice_count_of(practice) < preferred:
            grown = _set_practice(practice, _practice_count_of(practice) + 1, cfg)
            if (_practice_count_of(grown) <= _practice_count_of(practice)
                    or total - practice.minutes + grown.minutes > budget):
                break
            total += grown.minutes - practice.minutes
            chosen[chosen.index(practice)] = grown
            practice = grown

    # 5. the interactive.
    add(by_kind.pop('simulation', None))

    # 6. the closing moves.
    add(by_kind.pop('discussion', None))
    add(by_kind.pop('recap', None))

    # 7. whatever is left buys more practice, one item at a time - up to the ceiling the
    # bank can actually fill.
    limit = int(cfg.practice_max_items)
    if bank_size:
        limit = min(limit, bank_size)
    if practice is not None:
        while _practice_count_of(practice) < limit:
            grown = _set_practice(practice, _practice_count_of(practice) + 1, cfg)
            if (_practice_count_of(grown) <= _practice_count_of(practice)
                    or total - practice.minutes + grown.minutes > budget):
                break
            total += grown.minutes - practice.minutes
            chosen[chosen.index(practice)] = grown
            practice = grown

    # Anything the learner was told about but the budget could not hold must still be
    # reported. A block silently missing from both lists is the one failure mode this
    # whole record exists to prevent.
    for kind, block in by_kind.items():
        if block not in chosen:
            skip(kind, f'Dropped to fit the {budget}-minute budget; the activity was '
                       'appropriate, the session is simply too short for it.')

    return _order(chosen)


#: The canonical display order. Allocation spends the budget by value; the learner still
#: experiences a lesson in pedagogical order - input before interaction, practice before
#: the closing moves.
_DISPLAY_ORDER: tuple[str, ...] = ('diagnostic', 'deck', 'video', 'explain',
                                   'worked_example', 'simulation', 'practice',
                                   'discussion', 'recap', 'close')


def _order(blocks: Sequence[ProcedureBlock]) -> list[ProcedureBlock]:
    ranked = sorted(enumerate(blocks),
                    key=lambda pair: (_DISPLAY_ORDER.index(pair[1].kind)
                                      if pair[1].kind in _DISPLAY_ORDER else 99,
                                      pair[0]))
    return [ProcedureBlock(order=index, kind=block.kind, minutes=block.minutes,
                           title=block.title, purpose=block.purpose, why=block.why,
                           artifact=block.artifact, produces=block.produces,
                           optional=block.optional)
            for index, (_, block) in enumerate(ranked, start=1)]


def _practice_count_of(block: ProcedureBlock) -> int:
    try:
        return int(block.artifact.get('count') or 1)
    except (TypeError, ValueError):
        return 1


def _promised_items(assets: ProcedureAssets, size: int) -> list[str]:
    """The items a commitment block binds: at most ``size``, never more than exist.

    A block promising three questions over a two-item bank is a lie in the interface, and
    the learner discovers it at question three - which is also why the caller has already
    clamped ``size`` to ``practice_count``. An empty list is a real answer here (the
    concept has no scored items); it is not a placeholder for "some questions somewhere".
    """
    return [str(item) for item in assets.practice_items[:max(0, int(size))]]


def _practice_pool(assets: ProcedureAssets, already_promised: Sequence[str]) -> list[str]:
    """The pool a practice block draws from, after the diagnostic has taken its items.

    A lesson whose diagnostic asks 1/2 + 1/4 and whose practice then asks the same item
    records two attempts that look like two observations and are one. The practice pool is
    therefore the scheduler's order minus what the diagnostic already bound, so a normal
    four-item bank yields four distinct questions instead of a two-item bank asked twice.

    When the bank cannot cover both blocks, repetition is the honest fallback rather than
    an empty practice block: the lesson still needs the evidence practice produces, and the
    alternative - a practice block with nothing to ask - is the defect this whole change
    exists to remove.
    """
    pool = [str(item) for item in assets.practice_items]
    remaining = [item for item in pool if item not in set(already_promised)]
    return remaining or pool


def served_items(artifact: Mapping[str, Any]) -> list[str]:
    """The items a block will actually serve, in the order it will serve them.

    Two numbers, one list. ``count`` says how much of the pool this session spends (the
    allocator moves it as the budget changes); ``items`` says which items the pool holds.
    Everything that asks "is this block answered yet?" reads this function, so the guard
    in the route, the client's progress badge and the tutor's prompt cannot each decide
    the question differently.

    Blocks compiled before item binding existed carry no ``items`` key and therefore an
    empty list: they are not refused, they simply have no commitment to enforce, which is
    the honest reading of a plan that only ever promised an activity.
    """
    raw = artifact.get('items') if isinstance(artifact, Mapping) else None
    pool = [str(item) for item in (raw or []) if str(item)]
    try:
        count = int(artifact.get('count') or len(pool) or 0)
    except (TypeError, ValueError):
        count = len(pool)
    return pool[:count] if count >= 0 else pool


def _set_practice(block: ProcedureBlock, count: int, cfg) -> ProcedureBlock:
    """One practice block at an exact item count, with every field moved together.

    A block whose title says "4 example questions" while its artifact says ``count: 2``
    is worse than either number alone: the prompt and the client would disagree about
    what the learner is doing.

    ``count`` is how many items the lesson will *serve*; ``items`` is the fixed,
    scheduler-ordered pool it serves them from, and it is deliberately not truncated.
    Truncating it looked tidier and was wrong: allocation cuts the block to one item
    first and grows it back as budget allows, so the cut would have thrown away the
    second and third ids and a block that grew back to three questions could only ever
    serve one. The pool is the promise; ``count`` is how much of it this session uses
    (``served_items``) - clamped to the pool, because growing to four questions over a
    three-item pool is the same lie in the other direction.
    """
    count = max(1, int(count))
    artifact = dict(block.artifact)
    pool = artifact.get('items')
    if pool:
        count = max(1, min(count, len(pool)))
    artifact['count'] = count
    minutes = max(1, math.ceil(count * float(cfg.practice_minutes_per_item)))
    return ProcedureBlock(
        order=block.order, kind=block.kind, minutes=minutes,
        title=f'{count} example question' + ('s' if count != 1 else ''),
        purpose=block.purpose, why=block.why, artifact=artifact,
        produces=block.produces, optional=block.optional)


def _renumber(blocks: Sequence[ProcedureBlock]) -> list[ProcedureBlock]:
    return [ProcedureBlock(order=index, kind=block.kind, minutes=block.minutes,
                           title=block.title, purpose=block.purpose, why=block.why,
                           artifact=block.artifact, produces=block.produces,
                           optional=block.optional)
            for index, block in enumerate(blocks, start=1)]


def _rationale(evidence: LearnerEvidence, blocks: Sequence[ProcedureBlock],
               skipped: Sequence[Mapping[str, str]], budget: int, profile) -> str:
    """One auditable sentence: the shape, the evidence, and what was refused."""
    shape = ' -> '.join(block.kind for block in blocks) or 'nothing'
    return (f'{len(blocks)} block(s) in {sum(b.minutes for b in blocks)} of '
            f'{budget} minutes: {shape}. Evidence: mastery {evidence.mastery:.2f} over '
            f'{evidence.attempts} attempt(s), recent accuracy '
            f'{evidence.recent_accuracy if evidence.recent_accuracy is None else round(evidence.recent_accuracy, 2)}, '
            f'top error {evidence.top_error or "none"}, '
            f'{len(skipped)} activity/activities refused with reasons. Profile '
            f'{profile.name!r}.')


def _finish(facts: ConceptFacts, assets: ProcedureAssets, profile, budget: int,
            blocks: Sequence[ProcedureBlock], skipped: Sequence[Mapping[str, str]],
            rationale: str) -> CourseProcedure:
    return CourseProcedure(
        concept_id=facts.id, concept_title=facts.title or assets.concept_title,
        course_id=assets.course_id, blocks=tuple(blocks),
        skipped=tuple(dict(row) for row in skipped), budget_minutes=budget,
        total_minutes=sum(block.minutes for block in blocks),
        profile_name=profile.name, assets=assets.summary(), rationale=rationale)


def procedure_hash(procedure: CourseProcedure) -> str:
    """A stable fingerprint of the plan, for resuming a run and spotting drift.

    Hashes the *decision*, not the prose: concept, budget, and each block's kind,
    minutes and artifact identity. A recompiled lesson whose evidence has not changed
    produces the same hash and resumes; one whose evidence moved produces a new hash
    and is a genuinely different lesson.
    """
    payload = {
        'concept_id': procedure.concept_id,
        'course_id': procedure.course_id,
        'budget': procedure.budget_minutes,
        'profile': procedure.profile_name,
        'blocks': [
            {'kind': block.kind, 'minutes': block.minutes,
             'artifact': _artifact_identity(block.artifact)}
            for block in procedure.blocks
        ],
        'skipped': [row.get('kind') for row in procedure.skipped],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()[:32]


def _artifact_identity(artifact: Mapping[str, Any]) -> dict[str, Any]:
    """The stable part of an artifact, without volatile ids or full bodies.

    A materialised deck gains an ``artifact_id`` and a re-rendered body; neither should
    change the plan's identity, or resuming a lesson after opening its deck would look
    like a new lesson. What matters is *which* artifact was chosen, not where its bytes
    happen to live today.
    """
    keep = ('kind', 'concept_id', 'mode', 'slug', 'title', 'count', 'purpose',
            'provider', 'watch_url', 'slide_count', 'items')
    return {key: artifact[key] for key in keep if key in artifact}


# ------------------------------------------------------------------- the prompt


def _artifact_line(block: ProcedureBlock) -> str:
    """What the block is bound to, in the fewest words that are still exact."""
    artifact = block.artifact
    kind = artifact.get('kind')
    if kind == 'questions':
        count = artifact.get('count', 1)
        return (f'{count} question(s) from the question bank for concept '
                f'{artifact.get("concept_id") or block.title!r}; the scheduler chooses '
                'the items, you do not.')
    if kind == 'slides':
        headings = ', '.join(str(s.get('heading') or '') for s in
                             (artifact.get('sections') or [])[:6])
        return (f'the bound deck ({artifact.get("slide_count", 0)} slides: {headings}). '
                'Present it; do not write your own slides.')
    if kind == 'video':
        return (f'the curated video "{artifact.get("title")}" by '
                f'{artifact.get("channel")} at {artifact.get("watch_url")} '
                f'({artifact.get("licence_class")}). Embed or link it; never '
                'transcribe, download or summarise its audio.')
    if kind == 'simulation':
        if artifact.get('mode') == 'playground':
            return (f'the first-party interactive "{artifact.get("title")}" at '
                    f'{artifact.get("play_url")}; it reports the learner\'s committed '
                    'answer, so the run counts as evidence.')
        params = ', '.join(str(p.get('label') or p.get('id'))
                           for p in (artifact.get('parameters') or [])[:4])
        return (f'the exploratory interactive "{artifact.get("title")}"'
                + (f' (controls: {params})' if params else '')
                + '. It reports nothing; a scored question must follow.')
    if kind == 'text':
        return 'the authored worked example below, verbatim. Do not substitute one.'
    if kind == 'dialogue':
        return f'one Socratic exchange: {artifact.get("prompt")}'
    if kind == 'summary':
        connect = ', '.join(artifact.get('connect') or [])
        return (f'a short structure summary connecting this concept to {connect}.'
                if connect else 'a short structure summary.')
    if kind == 'stop':
        return 'no artifact. End the session.'
    return 'the tutor\'s own prose, grounded in the supplied lesson.'


def render_procedure_block(procedure: Any, *, completed: Sequence[int] = (),
                           max_chars: int = 3500) -> str:
    """The lesson, rendered into the system prompt as the plan this turn must follow.

    The move block (:func:`app.harness.teaching.render.render_plan_block`) names the
    decision for one turn. This names the *sequence* the turn sits inside - without it a
    model reads the move, does it well, and then invents the next activity from its own
    preferences. The two blocks are complementary and both are required: the move says
    "teach", this says "teach as block 2 of 5, through the bound deck, for five minutes".

    Server-authored text only. The concept title and artifact labels are bounded; the
    learner's own words never enter this block.
    """
    data = procedure.to_dict() if hasattr(procedure, 'to_dict') else procedure
    if not isinstance(data, Mapping) or not data.get('enabled', True):
        return ''
    blocks = [row for row in (data.get('blocks') or []) if isinstance(row, Mapping)]
    if not blocks:
        return ''
    done = {int(order) for order in completed}
    current = next((row for row in blocks if int(row.get('order') or 0) not in done),
                   None)

    lines = ['This session follows a lesson procedure compiled by the harness from this '
             'learner\'s evidence and the assets that exist for this concept. You may '
             'not add, remove, reorder or substitute an activity:']
    title = str(data.get('concept_title') or data.get('concept_id') or '')[:120]
    lines.append(f'- Concept: {title} ({data.get("course_id") or "course"})')
    lines.append(f'- Budget: {data.get("budget_minutes")} minutes across '
                 f'{len(blocks)} block(s), {data.get("total_minutes")} planned.')
    for row in blocks[:10]:
        order = int(row.get('order') or 0)
        mark = ('[done]' if order in done
                else ('[NOW]' if current is not None
                      and order == int(current.get('order') or 0) else '[next]'))
        lines.append(f'{order}. {mark} {str(row.get("kind") or "")[:24]} '
                     f'({row.get("minutes")} min) - {str(row.get("title") or "")[:80]}')
        lines.append(f'   Do: {str(row.get("purpose") or "")[:200]}')
        lines.append(f'   Because: {str(row.get("why") or "")[:240]}')
        lines.append('   Bound artifact: ' + _artifact_line(
            ProcedureBlock(order=order, kind=str(row.get('kind') or 'explain'),
                           minutes=int(row.get('minutes') or 1),
                           title=str(row.get('title') or ''), purpose='', why='',
                           artifact=row.get('artifact') or {})))
    skipped = [row for row in (data.get('skipped') or []) if isinstance(row, Mapping)]
    if skipped:
        lines.append('- Not in this lesson. Do not offer these; if the learner asks for '
                     'one, give the stated reason:')
        for row in skipped[:8]:
            lines.append(f'    - {str(row.get("kind") or "")[:24]}: '
                         f'{str(row.get("reason") or "")[:220]}')
    if current is not None and (current.get('artifact') or {}).get('kind') == 'questions':
        info = current.get('answers') or {}
        lines.insert(3, '- Answer channel: the native lesson question sheet serves the bound '
                        'items with signed receipts and sends answers through /attempts. '
                        f'Recorded for this block: {info.get("answered", 0)} of '
                        f'{info.get("total", (current.get("artifact") or {}).get("count", 0))}. '
                        'Do not interpret a chat claim, a timer or Done as a scored answer. '
                        'Keep error diagnoses tentative and use their next_action for support.')
    if current is not None:
        lines.append(f'- This turn runs block {current.get("order")} only. Do not '
                     'preview later blocks in detail, and do not start a later block '
                     'because it seems more useful.')
    else:
        lines.append('- Every block is complete. Close the session and do not invent a '
                     'new activity.')
    lines.append('- If the learner asks to skip a block, acknowledge it and move to the '
                 'next one; never silently reorder the lesson. If they ask an off-topic '
                 'question, answer it briefly and return to the current block.')
    if current is not None and str(current.get('kind') or '') == 'deck':
        # The deck is rendered on the learner's screen, not in the transcript. Naming the
        # tool here is what turns "let's look at the next slide" into a slide that moves:
        # the capability existed and was never advertised at the moment it was needed.
        lines.append('- The deck is open on the learner\'s screen. Move it with '
                     'deck_control (next, prev, first, last or goto) as you teach, and '
                     'say which slide you moved to. Do not describe a slide they are not '
                     'looking at.')
    lines.append('- The artifacts above are already bound. Name them as they are; do '
                 'not invent an alternative deck, video, simulation or question set.')
    text = '\n'.join(lines)
    return text[:max_chars]
