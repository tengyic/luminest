"""The simulator playground: a template system for interactive learning games.

An *archetype* is a reusable interaction (shift a curve, sort tiles into columns,
drag a point along a number line). A *game* is an archetype plus a content spec.
The pipeline in :mod:`pipeline` turns one into the other and stores the result as
a normal harness artifact, so a generated game is playable in the workbench by
exactly the same path as a hand-authored one.

Why this exists alongside :mod:`app.simulation_map`
---------------------------------------------------
``simulation_map`` offers *third-party* simulations - PhET embeds and Gizmos deep
links. Those are marked ``observable: false`` and can never be evidence, because
PhET exposes no telemetry in its free tier and Gizmos is a per-seat product we may
not instrument. That is a correct and permanent limitation, and it left the
harness unable to learn anything from a learner experimenting.

A first-party game has no such limitation. It runs in the workbench's own web
view, so it reports its outcome directly, and that outcome is recorded as
evidence. This package is what turns "the learner can play with a simulation" into
"the learner's play is part of what the harness knows about them".

Layout
------
``runtime``       the shared page shell, CSS tokens and JavaScript helpers
``archetypes``    the contract: what an archetype is, and how a spec is validated
``archetypes_*``  the archetype implementations, one module per subject family
``catalogue``     the bundled games, and lookup by slug, subject or course
``pipeline``      spec -> validated page -> stored artifact; the generation path
``evidence``      what a completed game means, and when it may move mastery
"""

from __future__ import annotations

from .archetypes import (Archetype, Field, all_archetypes, by_subject, get, register,
                         register_all, render, validate_spec)

# Imported statically, never by discovery. PyInstaller only bundles modules it can see
# imported, and this project has already shipped one build whose feature routers were
# absent from the frozen archive for exactly this reason. Adding an archetype module
# means adding one line here - and that line is what puts it in the shipped app.
from . import archetypes_core
from . import archetypes_economics
from . import archetypes_general
from . import archetypes_math_a
from . import archetypes_math_b
from . import archetypes_science_a
from . import archetypes_science_b

register_all((
    archetypes_core.CURVE_SHIFT,
) + archetypes_economics.ECONOMICS_ARCHETYPES
  + archetypes_math_a.MATH_A_ARCHETYPES
  + archetypes_math_b.MATH_B_ARCHETYPES
  + archetypes_science_a.SCIENCE_A_ARCHETYPES
  + archetypes_science_b.SCIENCE_B_ARCHETYPES
  + archetypes_general.GENERAL_ARCHETYPES)

__all__ = ['Archetype', 'Field', 'all_archetypes', 'by_subject', 'get', 'register',
           'register_all', 'render', 'validate_spec']
