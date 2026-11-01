"""Foundry tools: authoring reachable from inside a teaching turn.

The HTTP surface lets a client author a course. This module is the other half: the tutor
can do it *during* a session, which is what makes "the harness authors its own content" a
capability rather than an admin endpoint. A teacher says "build me a unit on enzymes for
next week" and the agent can, without leaving the conversation and without anyone opening
a JSON editor.

Three rules, inherited from the toolbox these tools feed.

**Teacher-gated, fail-closed.** Authoring produces shared content, so the role is read
from the authenticated principal - never from a tool argument - and anything that is not
exactly ``teacher``, ``staff`` or ``admin`` is refused with a reason. A learner who asks
the tutor to author a course gets an honest refusal, not a hidden failure.

**Audited before stored.** Every tool here runs the same audit the HTTP route runs. There
is no "draft it now, check it later" path, because a course that is stored but
unauditable is exactly the thing the audit exists to prevent.

**Refusals are informative.** A refused blueprint comes back with the validator's own
findings, so the model can fix the document and try again in the same turn. A tool that
says only "invalid" spends the turn; one that says which JSON path broke which rule does
not.
"""

from __future__ import annotations

from typing import Any, Mapping

from . import audit as audit_module
from . import blueprint, draft as draft_module, illustrate as illustrate_module
from . import methodology, registry, synthesize
from ..toolbox import ToolResult

_TOOL = 'authoring'


def _settings(ctx):
    return getattr(ctx, 'settings', None)


def _gate(ctx, tool: str) -> ToolResult | None:
    from .. import toolbox
    return toolbox._require_teacher(ctx, tool)


def _rebuild(record: registry.Record) -> synthesize.AuthoredCourse | None:
    """Re-synthesize a stored course from its blueprint.

    The record's materialised concepts are what is *served*; the blueprint is what is
    *designed*. Image work needs the lesson blocks (to decide what a photograph would
    illustrate), and re-building from the blueprint is how ``extend_course`` already gets
    them, so there is one reconstruction path rather than a second one that could drift.
    """
    plan, _ = blueprint.parse(dict(record.blueprint), author=record.blueprint.get('author')
                              or 'operator')
    if plan is None:
        return None
    return synthesize.build(plan)


def _problems(problems) -> list[str]:
    return [str(problem) for problem in problems[:10]]


def _card(record: registry.Record) -> dict[str, Any]:
    return record.card()


# ------------------------------------------------------------------------- tools

def author_course(ctx, blueprint_json: Mapping[str, Any] | str, replace: bool = False,
                  illustrate: bool = True) -> ToolResult:
    """Build a course from a blueprint document, audit it, illustrate it, and publish it."""
    gate = _gate(ctx, 'author_course')
    if gate is not None:
        return gate
    settings = _settings(ctx)
    if settings is None:
        return ToolResult('author_course', False, refused='No settings in this context')
    document = blueprint_json
    if isinstance(document, str):
        import json
        try:
            document = json.loads(document)
        except ValueError as exc:
            return ToolResult('author_course', False,
                              refused=f'blueprint_json is not valid JSON: {exc}')
    if not isinstance(document, Mapping):
        return ToolResult('author_course', False,
                          refused='blueprint_json must be a JSON object')
    plan, problems = blueprint.parse(document, author='operator')
    if plan is None:
        return ToolResult('author_course', False,
                          refused='The blueprint could not be read: '
                                  + '; '.join(_problems(problems)),
                          data={'problems': [problem.to_dict() for problem in problems]})
    course = synthesize.build(plan)
    report = audit_module.audit(course)
    if not report.ok:
        return ToolResult(
            'author_course', False,
            refused=f'The course failed the audit with {len(report.errors)} blocking '
                    f'finding(s); fix them and call again.',
            data={'audit': report.to_dict(), 'course': course.summary(),
                  'problems': [problem.to_dict() for problem in problems]})
    try:
        record = registry.store(settings, course, report, replace=replace)
    except audit_module.CourseRefused as refused:
        return ToolResult('author_course', False, refused=str(refused),
                          data={'audit': refused.audit.to_dict()})
    except ValueError as exc:
        return ToolResult('author_course', False, refused=str(exc))
    notes = [f'Published {record.id}; it is now in the course picker and '
             f'studyable through the existing lesson and practice routes.']
    payload: dict[str, Any] = {'course': _card(record), 'audit': record.audit,
                               'units': [unit.get('title') for unit in
                                         record.blueprint.get('units') or []]}
    if illustrate:
        # Illustration runs *after* the course is published, never before: the audit decides
        # whether the content may ship, and a network call must not sit in the path that
        # decides it. A failure here leaves a complete, text-only textbook.
        illustrated = illustrate_module.illustrate(settings, course)
        payload['illustration'] = illustrated.summary()
        notes.extend(illustrated.notes[:2])
    return ToolResult('author_course', True, data=payload, notes=notes[:5])


def draft_course(ctx, topic: str, units: int = 3, level: str = 'intro',
                 profile: str = 'default', illustrate: bool = True) -> ToolResult:
    """Author a course from a topic, using the configured model provider."""
    gate = _gate(ctx, 'draft_course')
    if gate is not None:
        return gate
    settings = _settings(ctx)
    if settings is None:
        return ToolResult('draft_course', False, refused='No settings in this context')
    try:
        drafted = draft_module.draft(settings, topic, units=int(units), level=level,
                                     profile_name=profile)
    except draft_module.DraftUnavailable as exc:
        return ToolResult('draft_course', False, refused=str(exc))
    except draft_module.DraftRefused as exc:
        return ToolResult('draft_course', False, refused=str(exc),
                          data={'findings': [finding.to_dict()
                                             for finding in exc.findings]})
    try:
        record = registry.store(settings, drafted.course, drafted.report)
    except (audit_module.CourseRefused, ValueError) as exc:
        return ToolResult('draft_course', False, refused=str(exc))
    notes = list(drafted.notes)[:6]
    payload: dict[str, Any] = {'course': _card(record), 'audit': record.audit,
                               'attempts': drafted.attempts}
    if illustrate:
        illustrated = illustrate_module.illustrate(settings, drafted.course)
        payload['illustration'] = illustrated.summary()
        notes.extend(illustrated.notes[:2])
    return ToolResult('draft_course', True, data=payload, notes=notes[:8])


def illustrate_course(ctx, course_id: str, limit: int = 1,
                      concept_ids: list[str] | None = None) -> ToolResult:
    """Attach real, licence-cleared photographs to an authored textbook.

    The images come from the same pipeline that serves the shipped courses: search, licence
    gate, cache, attribution. A concept that finds nothing is reported with the reason its
    candidates were dropped and is left without a photograph - nothing is fabricated and no
    placeholder is inserted.
    """
    gate = _gate(ctx, 'illustrate_course')
    if gate is not None:
        return gate
    settings = _settings(ctx)
    if settings is None:
        return ToolResult('illustrate_course', False, refused='No settings in this context')
    registry.hydrate(settings)
    record = registry.get(course_id)
    if record is None:
        return ToolResult('illustrate_course', False,
                          refused=f'No authored course {course_id!r}')
    course = _rebuild(record)
    if course is None:
        return ToolResult('illustrate_course', False,
                          refused=f'The blueprint for {course_id!r} could not be rebuilt, so '
                                  f'its lessons cannot be identified.')
    illustrated = illustrate_module.illustrate(settings, course, limit=int(limit or 1),
                                               only=concept_ids or None)
    payload = illustrated.to_dict()
    payload['coverage'] = illustrate_module.coverage(settings, course)
    return ToolResult('illustrate_course',
                      illustrated.outcome in {'ok', 'partial', 'nothing_to_illustrate',
                                              'offline'},
                      data=payload, notes=illustrated.notes,
                      refused='' if illustrated.assigned else
                      'No photograph could be attached; the reasons are per concept below.')


def attach_lesson_image(ctx, course_id: str, concept_id: str, query: str = '',
                        sha256: str = '', block_index: int = 1,
                        caption: str = '') -> ToolResult:
    """Put one chosen photograph into one lesson of an authored textbook.

    Two ways to name the image: ``query`` acquires and attaches in one step, or ``sha256``
    attaches an asset you already found with ``image_search``/``find_image`` - which is the
    right move when you have looked at the candidates and chosen one. The lesson serves it
    on the next read, with its author, licence and attribution.
    """
    gate = _gate(ctx, 'attach_lesson_image')
    if gate is not None:
        return gate
    settings = _settings(ctx)
    if settings is None:
        return ToolResult('attach_lesson_image', False,
                          refused='No settings in this context')
    registry.hydrate(settings)
    record = registry.get(course_id)
    if record is None:
        return ToolResult('attach_lesson_image', False,
                          refused=f'No authored course {course_id!r}')
    course = _rebuild(record)
    if course is None:
        return ToolResult('attach_lesson_image', False,
                          refused=f'The blueprint for {course_id!r} could not be rebuilt.')
    result = illustrate_module.attach(settings, course, concept_id, query=query,
                                      sha256=sha256, block_index=int(block_index or 1),
                                      caption=caption)
    block = result.get('block') or {}
    citations = []
    if block:
        citations.append({'kind': 'image', 'title': block.get('title'),
                          'source': block.get('source'), 'url': block.get('source_url'),
                          'licence': block.get('licence'),
                          'licence_class': block.get('licence_class')})
    return ToolResult('attach_lesson_image', bool(result.get('attached')), result,
                      citations=citations, notes=list(result.get('notes') or []),
                      refused='' if result.get('attached') else str(result.get('outcome')))


def course_images(ctx, course_id: str) -> ToolResult:
    """What photographs an authored textbook currently carries, with their credits."""
    settings = _settings(ctx)
    if settings is None:
        return ToolResult('course_images', False, refused='No settings in this context')
    registry.hydrate(settings)
    record = registry.get(course_id)
    if record is None:
        return ToolResult('course_images', False, refused=f'No authored course {course_id!r}')
    course = _rebuild(record)
    if course is None:
        return ToolResult('course_images', False,
                          refused=f'The blueprint for {course_id!r} could not be rebuilt.')
    return ToolResult('course_images', True, illustrate_module.coverage(settings, course))



def list_authored_courses(ctx) -> ToolResult:
    """What the foundry has produced in this deployment."""
    settings = _settings(ctx)
    if settings is None:
        return ToolResult('list_authored_courses', False,
                          refused='No settings in this context')
    registry.hydrate(settings)
    return ToolResult('list_authored_courses', True,
                      data={'courses': registry.listing(),
                            'withheld': registry.withheld()})


def read_course_blueprint(ctx, course_id: str) -> ToolResult:
    """The design document behind an authored course, with its audit status."""
    settings = _settings(ctx)
    if settings is None:
        return ToolResult('read_course_blueprint', False,
                          refused='No settings in this context')
    registry.hydrate(settings)
    record = registry.get(course_id)
    if record is None:
        return ToolResult('read_course_blueprint', False,
                          refused=f'No authored course {course_id!r}')
    return ToolResult('read_course_blueprint', True,
                      data={'course': _card(record), 'blueprint': record.blueprint,
                            'audit': record.audit})


def extend_course(ctx, course_id: str, unit_json: Mapping[str, Any] | str) -> ToolResult:
    """Append a unit to an authored course and rebuild it under the same audit."""
    gate = _gate(ctx, 'extend_course')
    if gate is not None:
        return gate
    settings = _settings(ctx)
    if settings is None:
        return ToolResult('extend_course', False, refused='No settings in this context')
    registry.hydrate(settings)
    record = registry.get(course_id)
    if record is None:
        return ToolResult('extend_course', False,
                          refused=f'No authored course {course_id!r}')
    unit = unit_json
    if isinstance(unit, str):
        import json
        try:
            unit = json.loads(unit)
        except ValueError as exc:
            return ToolResult('extend_course', False,
                              refused=f'unit_json is not valid JSON: {exc}')
    if not isinstance(unit, Mapping):
        return ToolResult('extend_course', False, refused='unit_json must be an object')
    document = dict(record.blueprint)
    document['units'] = list(document.get('units') or []) + [dict(unit)]
    plan, problems = blueprint.parse(document, author='operator')
    if plan is None:
        return ToolResult('extend_course', False,
                          refused='The extended blueprint could not be read: '
                                  + '; '.join(_problems(problems)),
                          data={'problems': [problem.to_dict() for problem in problems]})
    course = synthesize.build(plan)
    report = audit_module.audit(course)
    if not report.ok:
        return ToolResult('extend_course', False,
                          refused='The extended course failed the audit: '
                                  + '; '.join(f'{finding.code} ({finding.path})'
                                              for finding in report.errors[:5]),
                          data={'audit': report.to_dict()})
    rebuilt = registry.store(settings, course, report, replace=True)
    return ToolResult('extend_course', True,
                      data={'course': _card(rebuilt), 'audit': rebuilt.audit,
                            'previous_digest': record.digest})


def describe_methodology(ctx, profile: str = 'default') -> ToolResult:
    """What the foundry will enforce: the profile, its limits and the research behind it."""
    try:
        return ToolResult('describe_methodology', True,
                          data=methodology.describe(profile))
    except KeyError as exc:
        return ToolResult('describe_methodology', False, refused=str(exc))


__all__ = ['attach_lesson_image', 'author_course', 'course_images', 'describe_methodology',
           'draft_course', 'extend_course', 'illustrate_course', 'list_authored_courses',
           'read_course_blueprint']
