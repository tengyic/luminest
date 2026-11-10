"""The harness: memory, toolbox, sandbox, generation and the agentic loop.

Why these five modules and not one big agent file: each of them answers a question that
has to be answerable on its own.

``memory``    What does the harness believe about this learner, and how strongly?
``toolbox``   What is it allowed to do, and what may it read?
``sandbox``   Where does generated code run, and inside which boundary?
``generate``  What content can it produce, grounded in what it retrieved?
``loop``      Given the evidence, what should it do next?

The package exports a small facade so the API layer never reaches into internals.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import (attention, classroom, conduct, generate, guided_sim, leveling, loop, media,
               memory, modality, presentation, prompt, provider, psychometrics, render,
               rewards, sandbox, socratic, speech, telemetry, toolbox, video, vla)
from .toolbox import ToolContext, ToolResult

__all__ = ['attention', 'classroom', 'conduct', 'generate', 'guided_sim', 'leveling', 'loop',
           'media', 'memory', 'modality', 'presentation', 'prompt', 'provider',
           'psychometrics', 'render', 'rewards', 'sandbox', 'socratic', 'speech',
           'telemetry', 'toolbox', 'video', 'vla',
           'ToolContext', 'ToolResult', 'context_for', 'status', 'plan_for', 'run_move']


@dataclass
class HarnessContext(ToolContext):
    """A tool context with the workspace already bound to the learner."""


def context_for(settings, user, db, *, now: float | None = None, graph=None,
                subject_kind: str = '', course_id: str = '') -> HarnessContext:
    """Bind a settings/user/database triple to a workspace, ready for tool calls.

    ``graph``, ``subject_kind`` and ``course_id`` scope the call to the learner's own
    course. All are optional so an existing caller keeps working: without them the context
    falls back to the mathematics course, which is the default course and the only one the
    symbolic engine is valid for.
    """
    from ..db import now_ts
    user_id = getattr(user, 'id', '') or ''
    return HarnessContext(db=db, user=user, settings=settings, now=now or now_ts(),
                          workspace=sandbox.workspace_for(settings, user_id),
                          graph=graph, subject_kind=subject_kind or 'mathematics',
                          course_id=course_id)


def status(settings=None) -> dict[str, Any]:
    """The harness's posture, for the health endpoint and the transparency panel."""
    return {'moves': list(loop.MOVES),
            'tools': toolbox.catalogue(),
            'tool_postures': toolbox.postures(),
            'artefacts': list(generate.KINDS),
            'memory_kinds': list(memory.KINDS),
            'memory_half_life_days': round(memory.half_life_days(), 1),
            'sandbox': sandbox.describe(),
            'modality': modality.describe(),
            'dialogue_ladder': socratic.describe(),
            'simulation_cycle': guided_sim.describe(),
            'psychometrics': psychometrics.describe(),
            'conduct_rules': list(conduct.CONDUCT_RULES),
            'vla': vla.describe(settings),
            'attention': attention.describe(settings),
            'classroom': classroom.describe(),
            'rewards': rewards.describe(),
            'leveling': leveling.describe(),
            'telemetry': telemetry.describe(),
            'media': media.describe(settings),
            'video': video.describe(settings),
            'generation': {'required': 'a configured language model; there is no offline '
                                       'generation mode',
                           'unconfigured': 'model-required: a declared grounded fallback with '
                                           'a reason, never presented as the product',
                           'with_provider': 'the model clarifies prose only; structure, figures, '
                                            'citations and items stay generated and grounded'}}


def plan_for(settings, user, db, concept_id: str, *, exam_active: bool = False):
    """Convenience wrapper: bind a context and run the loop's decision step."""
    ctx = context_for(settings, user, db)
    return loop.plan(ctx, concept_id, exam_active=exam_active)


def run_move(settings, user, db, concept_id: str, *, exam_active: bool = False) -> dict[str, Any]:
    """Decide the next move and execute its planned tools, returning both.

    The tools are executed through the same registry the loop advertises, so what the
    harness says it will do and what it actually does cannot diverge.
    """
    ctx = context_for(settings, user, db)
    decision = loop.plan(ctx, concept_id, exam_active=exam_active)
    results = []
    for step in decision.tool_plan:
        arguments = dict(step.get('arguments') or {})
        results.append(toolbox.invoke(ctx, step['tool'], arguments).to_dict())
    return {'decision': decision.to_dict(), 'explanation': loop.explain(decision),
            'results': results}
