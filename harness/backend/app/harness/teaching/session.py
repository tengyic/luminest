"""The session plan: the teaching loop, assembled and executable.

A move choice is one decision. What the learner actually experiences is a
*sequence* - and a sequence assembled ad hoc each turn is how a tutor ends up
explaining for twenty minutes and never checking anything. This module turns the
policy's chosen move plus the profile's wrap configuration into an ordered plan of
steps, each carrying the tool calls that deliver it, so the loop is a thing that can
be run, inspected and tested rather than a habit.

The shape of the loop comes from microsoft/AI-For-Beginners (~55.7k stars, verified
2026-08-14): every lesson is bracketed by a pre-quiz and a post-quiz, so retrieval
practice sits on both sides of the instruction. Generalised here to:

    elicit  ->  teach  ->  practice  ->  transfer  ->  consolidate  ->  close

with every phase after ``teach`` gated on evidence rather than always emitted. A
plan that emits all six phases for every learner is a template, not a plan: the
wrap configuration says *when* a bracket applies, and the evidence says whether it
applies to this learner right now. Both brackets are skippable by evidence -
eliciting from a learner who has just failed a retrieval is salt in a wound.

The loop is not a pipeline that must finish. ``close`` can win the whole session
(a frustrated learner is not owed a transfer task), and a plan whose steps are
empty is a plan that says "stop", which is a legitimate teaching decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .evidence import ConceptFacts, LearnerEvidence
from .modalities import ModalityChoice, ToolCall, choose_modality
from .policy import MoveScore, select_move

__all__ = ['TeachingPlan', 'TeachingStep', 'plan_session']

#: The phases, in the order they are assembled. Exported as data so a test can
#: assert the loop's shape without hard-coding strings, and so a caller rendering a
#: progress rail shows the same order the planner used.
PHASES: tuple[str, ...] = ('elicit', 'teach', 'practice', 'transfer', 'consolidate',
                           'close')


@dataclass(frozen=True)
class TeachingStep:
    """One executable step: a move, the channel it runs through, and why.

    ``tools`` are the registry calls that deliver the step. They may still carry the
    router's placeholders (``{board_id}``, ``{course_id}``) because the planner has
    no business inventing a board id; :meth:`resolved_tools` substitutes the real
    values at the call site, and an unfilled placeholder stays visible so the tool
    refuses instead of drawing on a board nobody named.
    """

    order: int
    phase: str
    move: str
    modality: str
    why: str
    tools: tuple[ToolCall, ...] = ()
    fallback: tuple[ToolCall, ...] = ()
    needs_teacher: bool = False
    skippable: bool = True

    def resolved_tools(self, *, board_id: str = '',
                       course_id: str = '') -> tuple[tuple[str, dict[str, Any]], ...]:
        return tuple(call.resolved(board_id=board_id, course_id=course_id)
                     for call in self.tools)

    def resolved_fallback(self, *, board_id: str = '',
                          course_id: str = '') -> tuple[tuple[str, dict[str, Any]], ...]:
        return tuple(call.resolved(board_id=board_id, course_id=course_id)
                     for call in self.fallback)

    def to_dict(self) -> dict[str, Any]:
        return {'order': self.order, 'phase': self.phase, 'move': self.move,
                'modality': self.modality, 'why': self.why,
                'tools': [call.to_dict() for call in self.tools],
                'fallback': [call.to_dict() for call in self.fallback],
                'needs_teacher': self.needs_teacher, 'skippable': self.skippable}


@dataclass(frozen=True)
class TeachingPlan:
    """The assembled session: the chosen move, the steps, and the reasoning.

    ``move`` is the policy's decision and ``steps`` is how it is delivered. They are
    both kept because they answer different questions - "what did the evidence say
    to do" and "what will the learner actually see" - and a plan where the two
    disagree is a bug worth being able to see.
    """

    concept_id: str
    move: MoveScore
    steps: tuple[TeachingStep, ...] = ()
    profile_name: str = 'default'
    retrieval: Mapping[str, Any] | None = None
    rationale: str = ''

    @property
    def phases(self) -> tuple[str, ...]:
        return tuple(step.phase for step in self.steps)

    @property
    def moves(self) -> tuple[str, ...]:
        return tuple(step.move for step in self.steps)

    @property
    def modalities(self) -> tuple[str, ...]:
        return tuple(step.modality for step in self.steps)

    def step(self, phase: str) -> TeachingStep | None:
        for item in self.steps:
            if item.phase == phase:
                return item
        return None

    def to_dict(self) -> dict[str, Any]:
        return {'concept_id': self.concept_id, 'profile': self.profile_name,
                'move': self.move.to_dict(),
                'steps': [step.to_dict() for step in self.steps],
                'phases': list(self.phases),
                'retrieval': dict(self.retrieval) if self.retrieval else None,
                'rationale': self.rationale}


def plan_session(evidence: LearnerEvidence, facts: ConceptFacts, profile, *,
                 board_id: str = '', course_id: str = '', media_enabled: bool = False,
                 last_modality: str = '',
                 retrieval_plan: Mapping[str, Any] | None = None) -> TeachingPlan:
    """Assemble the teaching loop for this learner on this concept, right now.

    The chosen move comes from :func:`~app.harness.teaching.policy.select_move` and
    the channel from :func:`~app.harness.teaching.modalities.choose_modality`; this
    function only decides *which phases the evidence supports*. Every gate below
    names the evidence that opens it, and the default is to omit the phase - a step
    the evidence does not call for is a step that wastes the learner's session.
    """
    decision = select_move(evidence, profile)
    modality: ModalityChoice = choose_modality(
        facts, evidence, profile, last_modality=last_modality, board_id=board_id,
        course_id=course_id, media_enabled=media_enabled)

    # ``rest`` is terminal, not a step inside a longer loop. When the policy chooses
    # it the session is over: appending a retrieval check or a transfer task after
    # "stop" is the tutor ignoring its own decision, and the learner experiences that
    # as not being listened to. The whole plan is the exit.
    if decision.move == 'rest':
        return TeachingPlan(
            concept_id=facts.id, move=decision,
            steps=(TeachingStep(order=1, phase='close', move='rest', modality='text',
                                why=decision.reason, skippable=False),),
            profile_name=profile.name, retrieval=retrieval_plan,
            rationale=(f"Chose 'rest' (score {decision.score:.3f}); the session closes "
                       f'without further steps. {decision.reason}'))

    # A session already past its budget gets the chosen move and an exit, not the
    # full loop. Starting a six-phase sequence that cannot be finished is worse than
    # not starting it: the learner leaves mid-explanation, which is exactly the state
    # the long-session rule exists to prevent.
    over_budget = evidence.session_minutes >= profile.difficulty.long_session_minutes

    steps: list[TeachingStep] = []

    def push(phase: str, move: str, channel: str, why: str,
             tools: Sequence[ToolCall] = (), fallback: Sequence[ToolCall] = (),
             needs_teacher: bool = False, skippable: bool = True) -> None:
        steps.append(TeachingStep(order=len(steps) + 1, phase=phase, move=move,
                                  modality=channel, why=why, tools=tuple(tools),
                                  fallback=tuple(fallback),
                                  needs_teacher=needs_teacher, skippable=skippable))

    # ---- elicit ----------------------------------------------------------
    # The pre-quiz half of the wrap. Skipped when the learner is overloaded: a
    # diagnostic question asked of someone who has just failed three fast attempts
    # is one more failure, and it buys information the evidence already has.
    if not over_budget and profile.wrap.elicit_before and not evidence.frustrated:
        push('elicit', 'orient', 'text',
             'Elicit what the learner already thinks before teaching: it gives the new '
             'material something to attach to, and it tests the tutor\'s starting belief '
             'instead of assuming it.',
             (ToolCall('check_understanding', {'concept_id': facts.id},
                       'A low-stakes elicitation, scored but not counted against the '
                       'learner.'),),
             skippable=True)

    # ---- teach -----------------------------------------------------------
    # The policy's decision, delivered through the routed channel. Not skippable:
    # this is the move the evidence selected, and everything else is scaffolding
    # around it.
    push('teach', decision.move, modality.modality, decision.reason,
         modality.tools, modality.fallback, modality.needs_teacher, skippable=False)

    # ---- practice --------------------------------------------------------
    # Retrieval practice, which is also the post-quiz half of the wrap: the learner
    # leaves having *retrieved* the idea rather than having read it (the testing
    # effect). Omitted when the teach step already was retrieval - asking for recall
    # twice in one turn is one retrieval and one annoyance.
    if (not over_budget and profile.wrap.check_after and decision.move != 'retrieve'
            and evidence.attempts > 0):
        push('practice', 'retrieve', 'text',
             f'A fresh check after the instruction, so the session ends on retrieval '
             f'rather than on reading. Scheduled at the '
             f'{profile.retrieval.desired_retention:.2f} retention point; a concept '
             'never attempted has no memory to retrieve yet.',
             (ToolCall('check_understanding', {'concept_id': facts.id},
                       'Scored retrieval practice on the concept just taught.'),
              ToolCall('read_learner_evidence', {'concept_id': facts.id},
                       'Read back what the practice measured, so the next decision sees '
                       'it.')),
             skippable=True)

    # ---- transfer --------------------------------------------------------
    # The freeCodeCamp gate in plan form: recognition is not transfer, so the
    # applied task is emitted exactly when the learner has the mastery to attempt
    # it and the gate still wants it.
    if (not over_budget and profile.wrap.transfer_check
            and profile.completion.transfer_required
            and evidence.mastery >= profile.difficulty.consolidation_threshold
            and evidence.project_status != 'completed'):
        push('transfer', 'project', 'text',
             f'Mastery {evidence.mastery:.2f} is at the consolidation threshold and the '
             f'applied task is {evidence.project_status}; the completion gate requires '
             'transfer evidence, and this is the step that produces it.',
             (ToolCall('prepare_case_study', {'concept_id': facts.id},
                       'An applied task with a rubric and limited AI use, which is what '
                       'the completion gate measures.'),),
             skippable=True)

    # ---- consolidate -----------------------------------------------------
    # Connecting the concept to its neighbours, emitted once there is a structure
    # worth connecting and neighbours to connect to. Below the mastery threshold
    # there is no structure yet, and a summary of nothing is noise.
    if (not over_budget and evidence.mastery >= profile.difficulty.mastery_threshold
            and (evidence.dependants or evidence.unit_coverage >= 0.5)):
        push('consolidate', 'consolidate', 'text',
             f'Mastery {evidence.mastery:.2f} is at or above the '
             f'{profile.difficulty.mastery_threshold:.2f} threshold'
             + (f' and {evidence.dependants} concept(s) build on this one'
                if evidence.dependants else '')
             + ', so making the structure explicit is worth more than another isolated '
               'idea.',
             (ToolCall('read_concept', {'concept_id': facts.id},
                       'Read the concept and its edges so the summary names the real '
                       'neighbours.'),
              ToolCall('recall_learner_memory', {'concept_id': facts.id},
                       'Connect to what the learner was already told, not to a fresh '
                       'introduction.')),
             skippable=True)

    # ---- close -----------------------------------------------------------
    # The step that says stop, reached either because the session ran long or
    # because the learner is overloaded. Not skippable: an exit the model can talk
    # itself out of is not an exit.
    if over_budget or evidence.frustrated:
        reason = ('Attempts are fast and wrong, the signature of overload; a shorter '
                  'session teaches more than a different explanation.'
                  if evidence.frustrated else
                  f'{evidence.session_minutes:.0f} minutes of measured interaction '
                  f'exceeds the {profile.difficulty.long_session_minutes:.0f}-minute '
                  'point where continued instruction stops paying for itself.')
        push('close', 'rest', 'text',
             reason + ' Stop adding new material; offer the learner an exit.',
             skippable=False)

    rationale = _rationale(decision, modality, steps, evidence, profile)
    return TeachingPlan(concept_id=facts.id, move=decision, steps=tuple(steps),
                        profile_name=profile.name, retrieval=retrieval_plan,
                        rationale=rationale)


def _rationale(decision: MoveScore, modality: ModalityChoice,
               steps: Sequence[TeachingStep], evidence: LearnerEvidence,
               profile) -> str:
    """One auditable sentence: the decision, the channel, and the loop's shape."""
    shape = ' -> '.join(step.phase for step in steps) or 'nothing'
    return (f'Chose {decision.move!r} (score {decision.score:.3f}) through the '
            f'{modality.modality} channel; loop {shape}. '
            f'Evidence: mastery {evidence.mastery:.2f} over {evidence.attempts} '
            f'attempt(s), prerequisite debt {evidence.prerequisite_debt:.2f}, '
            f'session {evidence.session_minutes:.0f} min, profile '
            f'{profile.name!r}.')
