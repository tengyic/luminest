"""The content foundry: the harness authors its own courses.

Why this package exists
-----------------------
The harness could already *teach*. It decided the next move from evidence, generated
artefacts for a concept, drafted a game from a topic, built a course from a learner's own
document. What it could not do was design a course of its own: every shipped course was
designed outside the running system and committed as JSON, so the ability to produce a
*new* course lived in whoever wrote the pack, not in the product. That is the gap this
package closes, and it is a gap in capability rather than in code volume - a hundred
functions that all depend on someone else's authoring session are one capability short.

The four layers, and why they are separate
------------------------------------------
:mod:`~app.harness.authoring.methodology`
    *How* a course is designed: shape, load, sequence, assessment, honesty - as a named,
    versioned profile. Changing the method is editing data, not code.
:mod:`~app.harness.authoring.blueprint`
    *What* the course contains: a JSON document with units, concepts, prose and
    prerequisite intent. The only artefact a model is ever asked to write.
:mod:`~app.harness.authoring.synthesize`
    *Materialise*: blueprint to knowledge graph, lesson and items, in exactly the shapes
    ``app.curriculum`` and ``app.generated_curriculum`` already serve.
:mod:`~app.harness.authoring.audit`
    *Refuse*: the checks that stop a course which looks complete and teaches nothing.

Above them sit the three entry points that mirror ``app.harness.playground.pipeline``:
:func:`~app.harness.authoring.draft.draft` (a topic, filled by the configured model),
:func:`~app.harness.authoring.synthesize.build` (a blueprint, invented by nobody) and
:func:`~app.harness.authoring.registry.publish` (make it real, and keep it).

:mod:`~app.harness.authoring.illustrate` sits beside them rather than inside the chain: it
puts *real photographs* into a built textbook, through the same licence-gated media
pipeline the shipped courses use. It is deliberately after the audit and outside the
record - a network call must not sit in the path that decides whether content may ship,
and an image whose bytes were later deleted must not be claimable by a stored record.

The rule that holds the package together
----------------------------------------
**Nothing here writes code, and nothing here evaluates a string.** A blueprint is data;
the model fills a declared schema; the synthesizer reads that data and emits dicts in
shapes the rest of the harness already consumes. The worst a bad blueprint can do is
fail the audit, which is the property that makes accepting machine-authored course
content defensible at all.

Names are exported lazily so that importing one layer does not drag in the others -
``registry`` depends on ``curriculum``, which depends on ``generated_curriculum``, and an
eager package import would put a cycle between the foundry and the thing it feeds.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    'AuthoredCourse', 'Audit', 'CoursePlan', 'CourseRefused', 'Illustration', 'Problem',
    'attach', 'audit', 'build', 'build_from_document', 'coverage', 'describe_profile',
    'draft', 'illustrate', 'parse', 'profile', 'require', 'store', 'synthesize',
]

_LAZY = {
    'AuthoredCourse': ('.synthesize', 'AuthoredCourse'),
    'Audit': ('.audit', 'Audit'),
    'CoursePlan': ('.blueprint', 'CoursePlan'),
    'CourseRefused': ('.audit', 'CourseRefused'),
    'Illustration': ('.illustrate', 'Illustration'),
    'Problem': ('.blueprint', 'Problem'),
    'attach': ('.illustrate', 'attach'),
    'audit': ('.audit', 'audit'),
    'build': ('.synthesize', 'build'),
    'build_from_document': ('.synthesize', 'build_from_document'),
    'coverage': ('.illustrate', 'coverage'),
    'describe_profile': ('.methodology', 'describe'),
    'draft': ('.draft', 'draft'),
    'illustrate': ('.illustrate', 'illustrate'),
    'parse': ('.blueprint', 'parse'),
    'profile': ('.methodology', 'profile'),
    'require': ('.audit', 'require'),
    'store': ('.registry', 'store'),
    'synthesize': ('.synthesize', None),
}


def __getattr__(name: str) -> Any:  # PEP 562
    entry = _LAZY.get(name)
    if entry is None:
        raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
    module_name, attribute = entry
    from importlib import import_module

    module = import_module(module_name, __name__)
    return module if attribute is None else getattr(module, attribute)


def __dir__() -> list[str]:
    return sorted(__all__)
