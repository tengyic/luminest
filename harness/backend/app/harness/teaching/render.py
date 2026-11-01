"""The prompt sections, *rendered from* the teacher profile.

This is the module that makes the configuration real. A prompt that is written by
hand drifts: the policy gains a rule, the prose is not updated, and the model is
told to do something the scorer no longer rewards. Rendering the pedagogy sections
from the same :class:`TeacherProfile` the policy reads means the two cannot
disagree - editing the profile changes the prompt and the decision together,
because they are the same object.

The sections are deliberately plain prose rather than structured data. The model
reads them; a human auditing "why did it do that" reads them; and the client's
transparency panel shows the same string. One rendering, three readers, no
paraphrase in between.

Adapted from JushBJJ/Mr.-Ranedeer-AI-Tutor (~29.6k stars, verified 2026-10-13),
whose tutor prompt is a rendered configuration block rather than a personality
description. The adaptation here is that the *whole* pedagogy renders, not only the
persona: the moves, the schedule, the difficulty policy and the modality mix are all
sections, so none of them can be prose that quietly stopped being true.
"""

from __future__ import annotations

from typing import Any, Mapping

__all__ = ['render_move_section', 'render_modalities_section', 'render_persona_section',
           'render_plan_block', 'render_retrieval_section', 'render_profile_sections']

#: Depth is a 1-10 scale; these are the labels the prompt uses so the model is not
#: left to interpret a bare integer.
_DEPTH_LABELS = (
    (2, 'a bare sketch: name the idea and stop'),
    (4, 'a concise treatment: the idea, one worked example, no tangents'),
    (6, 'a full treatment: the idea, why it holds, worked examples, one edge case'),
    (8, 'a deep treatment: derivation, edge cases, and where the idea breaks'),
    (10, 'an exhaustive treatment: derivation, counterexamples, history, and open ends'),
)


def _depth_label(depth: int) -> str:
    for ceiling, label in _DEPTH_LABELS:
        if depth <= ceiling:
            return label
    return _DEPTH_LABELS[-1][1]


def render_move_section(profile) -> str:
    """The moves, and when the policy considers each appropriate.

    The wording comes from ``MoveSpec.summary`` in the profile, so a teacher that
    redefines what "simulate" means redefines it for the model and the scorer at
    once. Order is the profile's own order, which is also the policy's tie-break
    order - the list the model reads is the list the scorer uses.
    """
    lines = ['The moves you choose between, and when each is appropriate:']
    lines.extend(f'- {spec.name}: {spec.summary}' for spec in profile.moves)
    return '\n'.join(lines)


def render_persona_section(profile) -> str:
    """The tutor's voice, as declared data.

    Depth scales how much scaffolding a move carries; it never changes *which*
    move is chosen. That separation is stated in the prompt itself, because a
    model told "depth 9" will otherwise start answering questions the evidence
    has not earned yet - the persona must be visibly subordinate to the policy.
    """
    persona = profile.persona
    return ('Your voice for this learner (a setting, not a licence - it changes how '
            'much you say, never which move the evidence selects):\n'
            f'- Depth {persona.depth}/10: {_depth_label(persona.depth)}.\n'
            f'- Tone: {persona.tone}.\n'
            f'- Pace: {persona.pace}.\n'
            f'- Spoken output: {"on" if persona.spoken_output else "off"}.'
            + (' Speak explanations in addition to writing them; audio never replaces '
               'the text.' if persona.spoken_output else ''))


def render_retrieval_section(profile, plan: Mapping[str, Any] | None = None) -> str:
    """The schedule: the retention point, the session shape, and what is due now.

    ``plan`` is the serialised :class:`~app.harness.teaching.retrieval.RetrievalPlan`
    for this learner when one has been built, so the prompt states the actual
    calendar rather than only the rule that produces it. A rule with no instance is
    something the model has to invent an application for, and it invents badly.
    """
    retrieval = profile.retrieval
    lines = [
        'Retrieval schedule:',
        f'- A review is due when retrievability decays to '
        f'{retrieval.desired_retention:.2f}. Reviewing earlier is easy and adds little; '
        'reviewing later is a lapse.',
        f'- Serve at most {retrieval.per_session} review(s) per session, weakest memory '
        'first.',
        f'- Interleave one new concept after every {retrieval.interleave_every} '
        f'review(s), and introduce at most {retrieval.max_new_per_session} new '
        'concept(s) in a session. Novelty is expensive; retrieval is durable.',
    ]
    if plan:
        items = plan.get('items') or []
        if items:
            lines.append('- Due or scheduled right now, in service order:')
            for item in items[:retrieval.per_session]:
                if item.get('new'):
                    lines.append(f"    - {item.get('concept_id')}: new material.")
                else:
                    recall = item.get('recall')
                    shown = 'unknown' if recall is None else f'{recall:.2f}'
                    lines.append(f"    - {item.get('concept_id')}: retrievability "
                                 f'{shown}, {item.get("lapses", 0)} lapse(s).')
        else:
            lines.append('- Nothing is due at this retention point; the session is '
                         'free to introduce new material within the cap.')
        if plan.get('rationale'):
            lines.append(f"- Why this order: {plan['rationale']}")
    return '\n'.join(lines)


def render_modalities_section(profile) -> str:
    """The channels that exist, the default routing, and the variety bound.

    Naming the *ceiling* matters as much as naming the defaults: a model told it may
    draw will draw, so an instance that has switched a channel off has to say so
    here or the refusal arrives as a tool error instead of a plan.
    """
    modalities = profile.modalities
    lines = [
        'Teaching channels available to you (the list is the ceiling - a channel not '
        'named here is switched off on this instance):',
        f'- Available: {", ".join(modalities.allowed)}.',
        '- Default channel by concept type:',
    ]
    lines.extend(f'    - {kind}: {channel}' for kind, channel in modalities.prefer.items())
    lines.append(
        f'- Do not repeat the previous channel for the same concept; the profile '
        f'penalises an exact repeat by {modalities.variety_penalty:.2f}. Variety never '
        'overrides fit: if the learner is confused, keep drawing the structure.')
    lines.append(
        '- A channel is chosen because it teaches *this* concept type, never because a '
        'learner "is a visual learner". Learning styles are not an input.')
    return '\n'.join(lines)


def render_profile_sections(profile, plan: Mapping[str, Any] | None = None) -> dict[str, str]:
    """Every rendered section at once, keyed by name.

    The client's transparency panel and :func:`app.harness.prompt.payload` both read
    this, so the panel cannot show a different teacher from the one that acted.
    """
    return {
        'moves': render_move_section(profile),
        'persona': render_persona_section(profile),
        'retrieval': render_retrieval_section(profile, plan),
        'modalities': render_modalities_section(profile),
    }


def _as_mapping(plan: Any) -> Mapping[str, Any] | None:
    """Accept a :class:`TeachingPlan`, its ``to_dict()``, or nothing."""
    if plan is None:
        return None
    if isinstance(plan, Mapping):
        return plan
    to_dict = getattr(plan, 'to_dict', None)
    return to_dict() if callable(to_dict) else None


def render_plan_block(plan: Any) -> str:
    """The decision this turn must run, stated as an instruction.

    The profile sections describe the *space* of legal moves; this block names the
    one the policy actually selected for this learner on this concept right now,
    with the evidence that produced it. Without it the model reads the whole policy
    and picks its own move - which is how a prompt-rendered teacher quietly turns
    back into a hand-written one, because the model's preference, not the scorer's
    arithmetic, decides.

    The block is trusted server text: it is generated from the learner's own
    evidence and contains no learner-authored strings except the concept title,
    which is bounded here like every other value that reaches the system channel.
    """
    data = _as_mapping(plan)
    if not data:
        return ''
    move = data.get('move') or {}
    name = str(move.get('move') or move.get('name') or '')[:40]
    if not name:
        return ''
    score = move.get('score')
    reason = str(move.get('reason') or '')[:600]
    lines = ['This turn\'s teaching decision (chosen from the evidence below, not from '
             'your own preference - follow it, and say what you are doing):']
    lines.append(f'- Move: {name}' + (f' (score {float(score):.3f})' if isinstance(score, (int, float)) else ''))
    if reason:
        lines.append(f'- Because: {reason}')
    steps = data.get('steps') or []
    if steps:
        lines.append('- The session runs these phases in order; this turn runs the first '
                     'one that has not happened yet:')
        for step in steps[:8]:
            if not isinstance(step, Mapping):
                continue
            phase = str(step.get('phase') or '')[:24]
            step_move = str(step.get('move') or '')[:24]
            channel = str(step.get('modality') or '')[:24]
            why = str(step.get('why') or '')[:240]
            lines.append(f'    - {phase}: {step_move} via {channel}' + (f' - {why}' if why else ''))
        tools = [call for step in steps if isinstance(step, Mapping)
                 for call in (step.get('tools') or []) if isinstance(call, Mapping)]
        if tools:
            names = ', '.join(str(call.get('tool') or call.get('name') or '')[:40]
                              for call in tools[:6])
            lines.append(f'- Tools this session may call: {names}. A tool that refuses has '
                         'a declared fallback; take it rather than inventing a substitute.')
    rationale = str(data.get('rationale') or '')[:600]
    if rationale:
        lines.append(f'- Planner note: {rationale}')
    return '\n'.join(lines)
