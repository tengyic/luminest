"""The teaching core: a configuration-driven teacher for one learner.

This package holds the pedagogy that used to be scattered across prompt strings and
scoring constants. The design rule is that *the teacher is data*: a
:class:`~app.harness.teaching.config.TeacherProfile` declares which moves exist, when
each is chosen, the retrieval schedule, the difficulty policy and the multimodality
mix, and everything else in this package reads that declaration instead of
hard-coding its own constants. Changing the teacher is editing a profile; the system
prompt is then *rendered* from it (see :mod:`app.harness.teaching.render`), so the
prompt cannot drift out of step with the policy the way a hand-written prompt does.

Lineage - the techniques adopted from open-source teaching systems, and where each
one lives now (all repos verified at >=10k GitHub stars on 2026-10-13; see
``LINEAGE`` in :mod:`app.harness.teaching.config` for counts and provenance):

===========================  ========  ============================================
repo                        stars     technique taken, and where it was adapted
===========================  ========  ============================================
ankitects/anki               ~31.0k    retrieval scheduled at the desired-retention
                                         point of the forgetting curve, weakest
                                         memory first -> ``retrieval.py``
freeCodeCamp/freeCodeCamp    ~456k     mastery gated on a completed applied project,
                                         not on quiz passes -> ``config.CompletionConfig``
ossu/computer-science        ~209.9k   prerequisite-closure sequencing: never teach
                                         past an unmet prerequisite -> ``config.SequencingConfig``
microsoft/AI-For-Beginners   ~55.7k    every lesson wrapped by a pre-quiz and a
                                         post-quiz -> ``config.WrapConfig``
JushBJJ/Mr.-Ranedeer-AI-Tutor ~29.6k   the tutor persona is a configuration block the
                                         prompt is rendered from -> ``config.PersonaConfig``
===========================  ========  ============================================

Nothing is copied from those repositories; each mechanism was re-implemented against
this app's own FSRS-6 memory model (``app.memory``), BKT-style mastery
(``app.learning``) and knowledge graph (``app.knowledge_graph``), because a scheduler
that does not read the same states as the rest of the harness is two truths.

The public surface is deliberately small:

``TeacherProfile`` / ``default_profile``   the configuration, as data
``LearnerEvidence`` / ``build_evidence``   the learner state the policy reads
``select_move`` / ``score_moves``          the move policy
``choose_modality``                        the multimodal routing rules
``plan_retrieval``                         the FSRS-6-driven review calendar
``plan_session``                           the assembled teaching plan (the loop)
``supervise`` / ``describe_supervision``   whether to interrupt at all, right now
``streak`` / ``quiz_streak`` / ``badges``   the positive record: days, practice runs, badges
``render_*``                               prompt rendering from the configuration
"""

from __future__ import annotations

from .config import (CompletionConfig, DifficultyConfig, LearnedPreferenceConfig,
                     LINEAGE, ModalityConfig, MoveSpec, PersonaConfig, ProcedureConfig,
                     RetrievalConfig, SequencingConfig, TeacherProfile, WrapConfig,
                     default_profile)
from .evidence import (ConceptFacts, LearnerEvidence, build_evidence, concept_facts,
                       parent_states_for)
from .modalities import ModalityChoice, choose_modality
from .motivation import badges, certificate, node_milestone, quiz_streak, streak
from .policy import MoveScore, score_moves, select_move
from .procedure import (ACTIVITIES, INPUT_KINDS, CourseProcedure, ProcedureAssets,
                        ProcedureBlock, compile_procedure, procedure_hash,
                        render_procedure_block, served_items)
from .retrieval import RetrievalPlan, ReviewItem, due_concepts, is_due, plan_retrieval
from .render import (render_modalities_section, render_move_section, render_persona_section,
                     render_plan_block, render_retrieval_section)
from .session import TeachingPlan, TeachingStep, plan_session
from .supervision import assess as supervise, describe as describe_supervision

__all__ = [
    'ACTIVITIES', 'CompletionConfig', 'ConceptFacts', 'CourseProcedure',
    'DifficultyConfig', 'INPUT_KINDS', 'LearnedPreferenceConfig',
    'LINEAGE', 'LearnerEvidence', 'ModalityChoice', 'ModalityConfig', 'MoveScore',
    'MoveSpec', 'PersonaConfig', 'ProcedureAssets', 'ProcedureBlock', 'ProcedureConfig',
    'RetrievalConfig', 'RetrievalPlan', 'ReviewItem',
    'SequencingConfig', 'TeacherProfile', 'TeachingPlan', 'TeachingStep', 'WrapConfig',
    'badges', 'build_evidence', 'certificate', 'choose_modality', 'compile_procedure',
    'concept_facts',
    'default_profile', 'describe_supervision',
    'due_concepts', 'is_due', 'node_milestone', 'parent_states_for', 'plan_retrieval',
    'plan_session', 'procedure_hash', 'quiz_streak',
    'render_modalities_section', 'render_move_section', 'render_persona_section',
    'render_plan_block', 'render_procedure_block', 'render_retrieval_section',
    'score_moves', 'select_move', 'served_items', 'streak', 'supervise',
]
