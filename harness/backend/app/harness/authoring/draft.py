"""Drafting a blueprint with the harness's own model provider.

This is the arm of the foundry that produces a *new* course from a topic, and it is the
one that answers the question the subsystem was built for: can the product author
course content without a person (or an agent outside the product) sitting in the loop?

It can, and the shape of how is deliberate. Drafting is **two passes**, not one.

1. **Skeleton.** The model is asked for course metadata, unit titles, concept titles and
   prerequisite intent - structure, no prose. This is cheap, it is where sequencing
   errors live, and it is reviewable at a glance.
2. **Expansion, unit by unit.** Each unit is then asked for the prose its concepts need:
   summary, definition, worked example, misconception and repair, transfer task.

One pass would be simpler to write and worse in every way that matters. A model asked
for twelve fully-written concepts in a single response truncates, or rushes the last
four, and the truncation is invisible until the audit runs. Asking for one unit at a
time keeps every request inside a token budget where the model can actually finish, and
it makes a partial failure recoverable: one thin unit is one retry, not a discarded
course.

The retry is the other half of the design, and it is copied deliberately from
:func:`app.harness.playground.pipeline.draft`. A retry that re-asks the same question
without telling the model what was wrong is a second coin flip, not a retry. So the
validator's own complaints - the exact JSON path and the rule it broke - are appended to
the conversation before the second attempt, and the audit's findings are fed back the
same way at the end.

What this module will not do
----------------------------
It will not draft without a model. There is no template that turns the string
"thermodynamics" into a course, and pretending otherwise would produce exactly the
thing the rest of the harness is built to avoid: content that looks authored and says
nothing. With no provider configured, :func:`draft` refuses with a reason and points at
the path that does work offline - supply a blueprint, which a teacher, an operator or an
in-product tool can write with no model at all.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Mapping, Sequence

from . import audit as audit_module
from . import blueprint, methodology, synthesize
from .. import provider

#: Attempts per pass. Three, not two.
#:
#: The original comment argued that "a third attempt has never been the difference
#: between a course and no course". Measurement disagreed: on the outline pass a
#: first attempt succeeds about five times in six, and the one failure in six is
#: usually a completion that never parses as JSON at all (a stray sentence, or a
#: truncated object) rather than a blueprint the validator could correct. Two
#: attempts therefore leave roughly a one-in-ten chance of refusing a topic that is
#: perfectly draftable, which is what a user sees as "it cannot do my topic". The
#: third attempt costs one more completion only in the rare case the first two fail,
#: and takes that chance to about one in two hundred.
ATTEMPTS = 3

#: Token ceilings, derived from the profile rather than fixed.
#:
#: They were fixed constants, and that was the bug: the profile permits up to 60
#: concepts and 180-word blocks, while the skeleton ceiling was sized for a course a
#: third that size. A two-unit draft of "combinations and permutations" needs ~2,900
#: characters of JSON — roughly 1,000 tokens — but a six-unit draft of the same topic
#: needs several times that, and at 1,600 the completion came back either empty or
#: truncated mid-string, which :func:`provider.chat_json` returns as ``None``. The
#: caller then saw "the model did not produce a usable outline" for a model that had
#: produced a perfectly good one and been cut off. The ceiling now scales with the
#: shape actually being asked for, so a bigger course gets a bigger budget and a
#: stuck model is still bounded.
#:
#: Both stay bounded so a stuck model cannot spend a session's budget on one request;
#: the bounds are generous rather than tight, because a truncated completion is
#: indistinguishable from a refusal and costs the same tokens.
SKELETON_FLOOR = 2000
SKELETON_PER_CONCEPT = 90
UNIT_FLOOR = 4000
UNIT_PER_CONCEPT = 1100

#: Concepts asked for in one expansion call. The token ceiling above is not the limit that
#: binds: what binds is that a nine-concept unit is nine lessons of up to seven hundred
#: words in a single JSON answer, and a model that runs long either truncates the object or
#: returns fewer concepts than asked. Both look like "no prose for this concept" and cost
#: the whole answer. A batch of four is roughly where a completion stays reliable, and it
#: degrades in the safe direction - a lost batch loses four lessons, not a whole unit.
EXPAND_BATCH = 4


def skeleton_tokens(profile: methodology.AuthoringProfile, units: int) -> int:
    """Ceiling for the outline pass, scaled to the units being requested."""
    concepts = min(profile.shape.max_concepts,
                   max(units, 1) * profile.shape.concepts_per_unit_max)
    return SKELETON_FLOOR + concepts * SKELETON_PER_CONCEPT


def unit_tokens(profile: methodology.AuthoringProfile) -> int:
    """Ceiling for one unit's prose pass, scaled to the profile's own load limits."""
    concepts = profile.shape.concepts_per_unit_max
    return UNIT_FLOOR + concepts * UNIT_PER_CONCEPT

#: Upper bound on units drafted per course, matching the default profile's ceiling. A
#: model that answers with fourteen units is trimmed rather than obeyed: the profile is
#: the authority on shape, not the completion.
MAX_UNITS = 12


class DraftUnavailable(RuntimeError):
    """No model is configured. Carries the alternative path, because a bare refusal is
    useless to the caller that has to decide what to do next."""


class DraftRefused(RuntimeError):
    """The model answered, but nothing it produced survived the audit."""

    def __init__(self, message: str, *, findings: Sequence[audit_module.Finding] = (),
                 attempts: int = 0):
        self.findings = list(findings)
        self.attempts = attempts
        super().__init__(message)


@dataclass
class Draft:
    """A drafted course and the record of how it was produced."""

    plan: blueprint.CoursePlan
    course: synthesize.AuthoredCourse
    report: audit_module.Audit
    attempts: int = 0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {'course': self.course.summary(), 'audit': self.report.to_dict(),
                'attempts': self.attempts, 'notes': list(self.notes),
                'blueprint': self.plan.to_dict()}


# ------------------------------------------------------------------------ prompts

def _skeleton_system(profile: methodology.AuthoringProfile, units: int) -> str:
    shape, load = profile.shape, profile.load
    # The per-unit floor the audit will actually accept. The profile states a
    # course-wide concept floor (min_concepts) and a per-unit range; a short course
    # can satisfy one and violate the other, and the prompt used to name only the
    # per-unit range - so a two-unit draft was told "2 to 6 concepts per unit" and
    # then refused for having fewer than nine concepts in total. The floor is lifted
    # so units x floor clears min_concepts, and the total is named outright, so what
    # the model is asked for is what the validator will accept.
    per_unit_floor = max(shape.concepts_per_unit_min,
                         -(-shape.min_concepts // max(units, 1)))
    per_unit_floor = min(per_unit_floor, shape.concepts_per_unit_max)
    target = per_unit_floor * units
    return (
        'You are designing a course blueprint for an adaptive tutoring system. '
        'Reply with one JSON object and nothing else - no prose, no code fence.\n\n'
        'Schema:\n'
        '{"course": {"title": str, "subject": str, "description": str, '
        '"expected_weeks": int, "level": "intro"|"core"|"advanced"},\n'
        ' "units": [{"title": str, "strand": str, "objective": str,\n'
        '            "concepts": [{"title": str, "summary": str, '
        '"prerequisites": [str]}]}]}\n\n'
        'Rules, all enforced by a validator:\n'
        f'- exactly {units} units; {per_unit_floor} to '
        f'{shape.concepts_per_unit_max} concepts per unit, so about {target} '
        'concepts in total\n'
        f'- "objective" is one sentence saying what the unit is for\n'
        f'- "summary" is at least {load.min_summary_words} words and states the idea, '
        f'not the topic name\n'
        f'- a prerequisite names another concept in this same document, by title, and only '
        f'one that appears EARLIER; at most {shape.max_prerequisites} per concept\n'
        f'- the first concept of the course has no prerequisites\n'
        '- concepts inside a unit should build on each other; the first concept of a unit '
        'may rest on an earlier unit\n'
        '- write structure only in this pass. Do not write lesson prose, examples or '
        'exercises yet; those come in the next pass.\n\n'
        'Write for a learner who has the stated level and no prior knowledge of this '
        'subject. Do not pad the outline with units that are really the same unit.'
    )


def _expansion_system(profile: methodology.AuthoringProfile) -> str:
    load = profile.load
    return (
        'You are writing the lesson prose for ONE unit of an existing course blueprint. '
        'Reply with one JSON object and nothing else - no prose, no code fence.\n\n'
        'Schema:\n'
        '{"concepts": [{"title": str, "summary": str, "definition": str,\n'
        '               "example": [str, str, ...], "misconception": str,\n'
        '               "correction": str, "application": str, "objective": str}]}\n\n'
        'Rules, all enforced by a validator:\n'
        '- keep every title EXACTLY as given, in the same order, and add no new concepts\n'
        f'- "summary": {load.min_summary_words}+ words; what the idea is, precisely\n'
        '- "definition": the conditions and limits under which the idea holds\n'
        f'- "example": {load.min_example_steps} to {load.max_example_steps} numbered steps '
        f'that work one case end to end, with the arithmetic or the reasoning shown\n'
        '- "misconception": the mistake a learner at this level actually makes, phrased as '
        'the claim they would make\n'
        '- "correction": why that claim is wrong and what to do instead\n'
        '- "application": one concrete task that REQUIRES this idea and cannot be done '
        'with a neighbouring one\n'
        '- "objective": one sentence a learner could self-check against\n'
        f'- no block longer than {load.max_words_per_block} words\n\n'
        'Write plainly. No marketing language, no "in today\'s world", no restating the '
        'title as the definition. If a claim needs a number, give the number.'
    )


def _unit_prompt(plan: blueprint.CoursePlan, index: int,
                 batch: Sequence[blueprint.ConceptPlan] | None = None) -> str:
    """The prompt for one unit, or for one batch within a unit.

    ``batch`` exists because a nine-concept unit is nine lessons of up to seven hundred
    words each in a single JSON answer - more than one call reliably returns. The batch is
    a *slice of the same unit*, not a smaller unit: the header still names the unit, the
    objective still governs, and the concepts are still written in the course's order.
    """
    unit = plan.units[index]
    earlier = [f'{c.title} ({c.unit})' for c in plan.concepts()[:sum(
        len(u.concepts) for u in plan.units[:index])]]
    chosen = list(batch) if batch is not None else list(unit.concepts)
    header = (f'Unit {index + 1} of {len(plan.units)}: "{unit.title}" '
              f'(strand {unit.strand}).')
    if batch is not None and len(chosen) < len(unit.concepts):
        header += (f' This request covers {len(chosen)} of the unit\'s '
                   f'{len(unit.concepts)} concepts.')
    lines = [f'Course: {plan.title} ({plan.subject}), level {plan.level}.',
             header]
    # An overlay frames a unit the pack already declares, and a pack does not state a
    # unit-level objective. Printing "Unit objective:" with nothing after it invites the
    # model to invent one, so the line is omitted unless there is something to say.
    if unit.objective.strip():
        lines.append(f'Unit objective: {unit.objective}')
    lines.append('Concepts to write, in this order:')
    for concept in chosen:
        prereq = (f'; rests on {", ".join(concept.prerequisites)}'
                  if concept.prerequisites else '; no prerequisite')
        lines.append(f'- {concept.title}: {concept.summary}{prereq}')
    if earlier:
        lines.append('Concepts already taught earlier in the course: '
                     + ', '.join(earlier[:24]) + '.')
    lines.append('Write the prose for each concept listed above.')
    return '\n'.join(lines)


# -------------------------------------------------------------------- extraction

def _as_object(value: Any) -> dict[str, Any] | None:
    """A completion as an object, tolerating the two shapes a model actually returns.

    A model asked for ``{"units": [...]}`` sometimes answers with the bare list, and
    sometimes wraps the object in a ``{"course": ...}`` envelope that already has the
    shape we wanted. Both are accepted; anything else is a failed attempt.
    """
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, list):
        return {'units': value}
    return None


def title_key(text: Any) -> str:
    """The comparison key for a concept title.

    Not just ``casefold()``, because the two passes do not always use the same shape for a
    title. A model asked to write a concept often answers with the title *and* a one-line
    summary joined by a colon: ``"accounting profit versus economic profit: economic profit
    subtracts implicit cost as well"``. Matching on the whole string then matches nothing,
    every concept in that batch loses its prose, and the audit - correctly - refuses the
    course for lessons that are titles with no teaching in them. Measured on a real AP
    Microeconomics overlay: five written lessons in one unit failed to match, and the patch
    was refused for 170 thin-lesson errors that all came from here.

    So the key is the part before the first colon. An exact title with no colon keys to
    itself, which is why the fallback is not needed in the ordinary case.
    """
    cleaned = ' '.join(str(text or '').split()).strip()
    head, separator, _rest = cleaned.partition(':')
    if separator and head.strip():
        cleaned = head.strip()
    return cleaned.rstrip('.').casefold()


def _merge(skeleton: Mapping[str, Any], expansions: Mapping[int, Mapping[str, Any]],
           notes: list[str] | None = None) -> dict[str, Any]:
    """Skeleton structure plus per-unit prose, as one blueprint document.

    The expansion may not rename, reorder or add concepts: the merge walks the skeleton
    and copies prose fields only. That is the whole safety property of the two-pass
    design - a second pass that could restructure the course would be a second author,
    and the audit would be checking a document nobody designed.

    Matching is by :func:`title_key`, which tolerates the model appending a summary to the
    title. What it does not tolerate is ambiguity: if two concepts in a unit claim the same
    key the prose is dropped rather than attached to whichever came last, because attaching
    a lesson to the wrong concept is worse than reporting a thin one.
    """
    document = {'schema': blueprint.SCHEMA,
                'course': dict(skeleton.get('course') or {}),
                'units': []}
    for index, unit in enumerate(skeleton.get('units') or []):
        prose = (expansions.get(index) or {}).get('concepts') or []
        by_key: dict[str, Mapping[str, Any]] = {}
        ambiguous: set[str] = set()
        for item in prose:
            if not isinstance(item, Mapping):
                continue
            key = title_key(item.get('title'))
            if key in by_key:
                ambiguous.add(key)
            by_key[key] = item
        for key in ambiguous:
            by_key.pop(key, None)
            if notes is not None:
                notes.append(f'unit {index + 1}: two answers claimed the title {key!r}; '
                             f'neither is used, because guessing would attach a lesson to '
                             f'the wrong concept')
        matched: set[str] = set()
        merged_unit = {'title': unit.get('title'), 'strand': unit.get('strand'),
                       'objective': unit.get('objective'), 'concepts': []}
        for concept in unit.get('concepts') or []:
            if not isinstance(concept, Mapping):
                continue
            entry = dict(concept)
            key = title_key(concept.get('title'))
            written = by_key.get(key)
            if written:
                matched.add(key)
                for field in ('summary', 'definition', 'example', 'misconception',
                              'correction', 'application', 'objective'):
                    if written.get(field):
                        entry[field] = written[field]
            elif notes is not None:
                notes.append(f'{concept.get("id") or concept.get("title")}: the model '
                             f'returned no prose for this concept')
            merged_unit['concepts'].append(entry)
        if notes is not None:
            for extra in sorted(set(by_key) - matched):
                notes.append(f'unit {index + 1}: the model wrote {extra!r}, which is not '
                             f'a concept in this unit')
        document['units'].append(merged_unit)
    return document


def _feedback(problems: Sequence[blueprint.Problem]) -> str:
    return ('The validator refused that blueprint. Fix exactly these problems and reply '
            'with the corrected JSON object only:\n'
            + '\n'.join(f'- {problem.path}: {problem.message}' for problem in problems[:12]))


def _disambiguate(document: Mapping[str, Any], course: str) -> Mapping[str, Any]:
    """Prefix concept ids that would collide with a concept another course already owns.

    Concept ids are global - they key learner state, attempts and memory notes - so
    :func:`registry.store` refuses a course whose concept id already belongs to a
    different course. That refusal is right: the alternative silently rewrites what an
    existing learner is studying. The problem was upstream of it. The drafter derives
    an id from the concept *title*, so a course on "combinations and permutations"
    produced a concept titled "Probability", whose id ``probability`` already belongs
    to ``integrated_math_1``, and the whole course was refused for a title clash while
    its actual content was new.

    The shipped packs already solve this by prefixing every id with the course name
    (see the ``reason`` field in ``curriculum_packs/*.json``). This applies the same
    rule to a drafted course, but only where it is needed: an id that is already unique
    keeps its plain form, so a draft that does not clash is byte-for-byte what it was.
    Prerequisites are resolved by *title* later in :func:`blueprint._resolve_prerequisites`,
    so rewriting an id here cannot orphan an edge.
    """
    from ... import curriculum  # local: curriculum imports the course registry

    units = document.get('units')
    if not isinstance(units, list):
        return document
    taken: set[str] = set()
    for unit in units:
        concepts = unit.get('concepts') if isinstance(unit, Mapping) else None
        if not isinstance(concepts, list):
            continue
        for concept in concepts:
            if not isinstance(concept, dict):
                continue
            source = str(concept.get('id') or concept.get('title') or '').strip()
            candidate = blueprint.concept_id(source)
            owner = curriculum.CONCEPT_COURSE.get(candidate)
            if owner is None and candidate not in taken:
                taken.add(candidate)
                continue
            # Clash: scope the id to this course, and keep going until it is unique.
            stem = candidate
            for _ in range(8):
                stem = f'{course}_{stem}'[:blueprint.MAX_CONCEPT_ID]
                if curriculum.CONCEPT_COURSE.get(stem) is None and stem not in taken:
                    break
            concept['id'] = stem
            taken.add(stem)
    return document


# ------------------------------------------------------------------------ drafting

def _ask(settings, messages: list[dict[str, Any]], *, max_tokens: int,
         usage_out: dict | None) -> Any:
    return provider.chat_json(settings, messages, max_tokens=max_tokens, usage_out=usage_out)


def expand(settings, plan: blueprint.CoursePlan, *, attempts: int = ATTEMPTS,
           usage_out: dict | None = None,
           notes_out: list[str] | None = None,
           progress: Callable[[str], None] | None = None) -> blueprint.CoursePlan:
    """Write the prose for a plan whose structure is already decided.

    Why this is a separate entry point rather than a flag on :func:`draft`: the two
    failure modes are different. ``draft`` can fail because the model cannot design a
    sequence - and it retries the design. ``expand`` cannot: the sequence is the course's
    own graph, handed in. A retry here can only fix prose, so a skeleton complaint would
    be a bug in the caller, not something to ask the model about again.

    This is the path an overlay takes. The concepts are the pack's, so the expansion pass
    is asked about exactly those concepts, one unit at a time, and the validator's
    complaints about *those* concepts are fed back the same way ``draft`` feeds them back.

    ``notes_out`` is how a caller finds out that a unit came back empty or that the model
    renamed a concept: the returned plan still has every concept, so nothing downstream
    can tell a thin lesson from a missing answer. Returns the plan, not a :class:`Draft` -
    there is no course to build until the caller decides what graph to build it against.
    """
    if not provider.available(settings):
        raise DraftUnavailable(
            'No model provider is configured, so the harness cannot write the prose for '
            'this course. Configure one (HARNESS_TUTOR_PROVIDER and HARNESS_PROVIDER_KEY), '
            'or supply a blueprint with the lessons already written.')
    profile = plan.profile
    notes: list[str] = notes_out if notes_out is not None else []
    # Progress is reported, not logged. An expansion of a fifty-seven concept course is
    # a dozen or more model calls and can run for the better part of an hour; a caller
    # that only prints once it finishes cannot tell "still writing lesson six" from
    # "died on the first request", and both look like a hung process.
    say = progress or (lambda _line: None)
    spent = 0
    document = plan.to_dict()
    expansions: dict[int, Mapping[str, Any]] = {}
    total_batches = sum(max(1, -(-len(unit.concepts) // EXPAND_BATCH))
                        for unit in plan.units)
    done = 0
    for index, unit in enumerate(plan.units):
        collected: dict[str, dict[str, Any]] = {}
        batches = [list(unit.concepts)[start:start + EXPAND_BATCH]
                   for start in range(0, len(unit.concepts), EXPAND_BATCH)] or [[]]
        for number, batch in enumerate(batches, 1):
            label = (f'unit {index + 1}' if len(batches) == 1
                     else f'unit {index + 1} batch {number}/{len(batches)}')
            # ``pending`` shrinks. An answer that covers some of the batch is neither a
            # success nor a failure, and treating it as a success is how a run ends with
            # every concept present and half of them without a lesson: the count of
            # concepts returned was checked, the count of *these* concepts was not.
            pending = list(batch)
            complaint = ''
            for attempt in range(1, attempts + 1):
                spent += 1
                say(f'  [{done + 1}/{total_batches}] {label}: {len(pending)} concept(s), '
                    f'attempt {attempt}...')
                messages: list[dict[str, Any]] = [
                    {'role': 'system', 'content': _expansion_system(profile)},
                    {'role': 'user', 'content': _unit_prompt(plan, index, pending)},
                ]
                if complaint:
                    # A retry with an identical prompt is the same request and gets the
                    # same answer. The complaint is what makes it a different one.
                    messages.append({'role': 'user', 'content': complaint})
                payload = _as_object(_ask(settings, messages,
                                          max_tokens=unit_tokens(profile),
                                          usage_out=usage_out))
                concepts = (payload or {}).get('concepts')
                got = [item for item in (concepts if isinstance(concepts, list) else [])
                       if isinstance(item, Mapping)]
                asked = {title_key(concept.title): concept for concept in pending}
                for item in got:
                    key = title_key(item.get('title'))
                    concept_plan = asked.get(key)
                    if concept_plan is None:
                        notes.append(f'{label}: the model wrote '
                                     f'{str(item.get("title") or "")!r}, which is not one '
                                     f'of the concepts it was asked for')
                        continue
                    # The title is rewritten to the skeleton's own string. Whatever shape
                    # the model answered in, the merge then sees the course's own title,
                    # and the concept id the pack owns is what the lesson lands on.
                    entry = dict(item)
                    entry['title'] = concept_plan.title
                    collected[key] = entry
                pending = [concept for concept in batch
                           if title_key(concept.title) not in collected]
                if not pending:
                    say(f'  [{done + 1}/{total_batches}] {label}: '
                        f'{len(batch)} lesson(s) written')
                    break
                if got:
                    notes.append(f'{label} attempt {attempt}: {len(pending)} of '
                                 f'{len(batch)} still unwritten: '
                                 + ', '.join(concept.title for concept in pending))
                    complaint = ('That answer covered other concepts. Write the prose for '
                                 'each of these, using its title exactly as given: '
                                 + '; '.join(concept.title for concept in pending) + '.')
                else:
                    notes.append(f'{label} attempt {attempt} produced no concepts')
                    complaint = ('The reply had no "concepts" array. Answer with '
                                 '{"concepts": [...]} for exactly the concepts listed, and '
                                 'nothing else.')
            done += 1
        if collected:
            expansions[index] = {'concepts': list(collected.values())}
    merged = _merge(document, expansions, notes)
    written, problems = blueprint.parse(merged, author='model')
    if written is None:
        raise DraftRefused('The expanded blueprint could not be read: '
                           + '; '.join(str(problem) for problem in problems[:4]),
                           attempts=spent)
    return written


#: ``concept '<id>'`` in a finding's path. The audit names the thing it refused, and that
#: name is what a repair pass needs in order to know what to rewrite.
_FINDING_CONCEPT = re.compile(r"concept '([^']+)'")


def refused_prose(report) -> dict[str, list[str]]:
    """Which concepts an audit refused, and what it said about each.

    Only findings that name a concept are returned. A course-level finding -
    ``unit_too_thin``, ``category_missing`` - is not repairable by rewriting one lesson, and
    asking a model to fix it would produce prose for a structural problem.
    """
    complaints: dict[str, list[str]] = {}
    for finding in report.errors:
        match = _FINDING_CONCEPT.search(str(getattr(finding, 'path', '')))
        if not match:
            continue
        complaints.setdefault(match.group(1), []).append(
            f'{getattr(finding, "code", "")}: {getattr(finding, "message", "")}')
    return complaints


def _repair_prompt(plan: blueprint.CoursePlan, batch: Sequence[blueprint.ConceptPlan],
                   complaints: Mapping[str, Sequence[str]]) -> str:
    lines = [f'Course: {plan.title}. The lessons you wrote were refused by the validator.',
             'Each line below is one refused concept and the reasons given:']
    for concept in batch:
        lines.append(f'- {concept.title}')
        for complaint in complaints.get(concept.id, ()):
            lines.append(f'    {complaint}')
    lines.append('')
    lines.append('Rewrite the lesson for each of these concepts. Use each title exactly as '
                 'written above. Fix the complaints named; leave what was not complained '
                 'about alone. Meet every length the schema asks for - a summary below the '
                 'minimum is refused however accurate it is.')
    return '\n'.join(lines)


def repair(settings, plan: blueprint.CoursePlan, complaints: Mapping[str, Sequence[str]],
           *, progress: Callable[[str], None] | None = None,
           usage_out: dict | None = None) -> blueprint.CoursePlan:
    """Rewrite the lessons an audit refused, quoting the refusal back to the model.

    Why this exists: the two-pass design already feeds the validator's complaints to the
    model for the *structure*, which is what makes a retry a correction rather than a
    second coin flip. The prose had no such loop, so a lesson refused for being three
    words short of the summary floor was refused permanently - the run then either stored
    nothing or gave up after an hour of writing. Measured on a local model: 57 of 57
    lessons written, 9 refused, every one of them for a length the model had been told
    about and had overshot.

    One round, and only the refused concepts, so a passing lesson is never rewritten and
    never loses prose it did not have to lose.
    """
    if not provider.available(settings):
        raise DraftUnavailable(
            'No model provider is configured, so the harness cannot repair the lessons the '
            'audit refused.')
    say = progress or (lambda _line: None)
    by_id = {concept.id: concept for concept in plan.concepts()}
    targets = [by_id[concept_id] for concept_id in complaints if concept_id in by_id]
    if not targets:
        return plan
    profile = plan.profile
    rewritten: dict[str, dict[str, Any]] = {}
    for start in range(0, len(targets), EXPAND_BATCH):
        batch = targets[start:start + EXPAND_BATCH]
        say(f'  repair: {len(batch)} concept(s) ({start + len(batch)}/{len(targets)})...')
        messages = [{'role': 'system', 'content': _expansion_system(profile)},
                    {'role': 'user', 'content': _repair_prompt(plan, batch, complaints)}]
        payload = _as_object(_ask(settings, messages, max_tokens=unit_tokens(profile),
                                  usage_out=usage_out))
        concepts = (payload or {}).get('concepts')
        asked = {title_key(concept.title): concept for concept in batch}
        for item in (concepts if isinstance(concepts, list) else []):
            if not isinstance(item, Mapping):
                continue
            concept = asked.get(title_key(item.get('title')))
            if concept is None:
                continue
            rewritten[concept.id] = dict(item)
        say(f'  repair: {len(rewritten)} of {len(targets)} rewritten so far')
    if not rewritten:
        return plan

    units = []
    for unit in plan.units:
        kept = []
        for concept in unit.concepts:
            fresh = rewritten.get(concept.id)
            if fresh is None:
                kept.append(concept)
                continue
            # Only the fields the repair answered are replaced. A rewrite that drops the
            # worked example must not delete the one that was there and passing.
            updates: dict[str, Any] = {}
            for field_name in ('summary', 'definition', 'misconception', 'correction',
                               'application', 'objective'):
                if fresh.get(field_name):
                    updates[field_name] = str(fresh[field_name])
            if fresh.get('example'):
                example = fresh['example']
                updates['example'] = tuple(str(step) for step in example
                                           if str(step).strip())
            kept.append(replace(concept, **updates) if updates else concept)
        units.append(replace(unit, concepts=kept))
    return replace(plan, units=units)


def draft(settings, topic: str, *, units: int = 3, level: str = 'intro',
          profile_name: str = 'default', overrides: Mapping[str, Any] | None = None,
          attempts: int = ATTEMPTS, usage_out: dict | None = None) -> Draft:
    """Author a course from a topic, in two passes, and audit the result.

    Raises :class:`DraftUnavailable` when no provider is configured and
    :class:`DraftRefused` when the model's output never survives the audit. Both carry
    enough detail for a caller to explain the failure to a teacher without guessing.
    """
    if not provider.available(settings):
        raise DraftUnavailable(
            'No model provider is configured, so the harness cannot draft a course from '
            'a topic. Configure one (HARNESS_TUTOR_PROVIDER and HARNESS_PROVIDER_KEY), or '
            'supply a blueprint instead - a teacher or an in-product tool can write one '
            'with no model at all, and the same synthesizer and audit will build it.')
    topic = ' '.join((topic or '').split())
    if not topic:
        raise ValueError('A draft needs a topic')

    profile = methodology.profile(profile_name, overrides)
    bounded = max(profile.shape.min_units, min(units, profile.shape.max_units, MAX_UNITS))
    notes: list[str] = []
    spent = 0

    skeleton_messages: list[dict[str, Any]] = [
        {'role': 'system', 'content': _skeleton_system(profile, bounded)},
        {'role': 'user', 'content': f'Design the course outline for: {topic}\n'
                                    f'Level: {level}.'},
    ]
    skeleton: dict[str, Any] | None = None
    for attempt in range(1, attempts + 1):
        spent += 1
        payload = _as_object(_ask(settings, skeleton_messages,
                                  max_tokens=skeleton_tokens(profile, bounded),
                                  usage_out=usage_out))
        if payload is None:
            skeleton_messages.append({'role': 'user', 'content':
                                      'That was not a JSON object. Reply with the JSON '
                                      'object only.'})
            continue
        candidate, problems = blueprint.parse(payload, author='model')
        blocking = blueprint.blocking(problems)
        if candidate is not None and not blocking:
            skeleton = payload
            notes.extend(str(problem) for problem in problems[:6])
            break
        skeleton_messages.append({'role': 'assistant',
                                  'content': json.dumps(payload, ensure_ascii=False)[:8000]})
        skeleton_messages.append({'role': 'user', 'content': _feedback(
            blocking or problems or [blueprint.Problem('empty', 'units', 'no units found')])})
        notes.append(f'skeleton attempt {attempt} refused: '
                     f'{len(blocking or problems)} problem(s)')
    if skeleton is None:
        raise DraftRefused(f'The model did not produce a usable outline for {topic!r} in '
                           f'{attempts} attempt(s).', attempts=spent)

    skeleton_plan, _ = blueprint.parse(skeleton, author='model')
    assert skeleton_plan is not None  # guaranteed by the loop above
    expansions: dict[int, Mapping[str, Any]] = {}
    for index in range(len(skeleton_plan.units)):
        messages: list[dict[str, Any]] = [
            {'role': 'system', 'content': _expansion_system(profile)},
            {'role': 'user', 'content': _unit_prompt(skeleton_plan, index)},
        ]
        for attempt in range(1, attempts + 1):
            spent += 1
            payload = _as_object(_ask(settings, messages,
                                      max_tokens=unit_tokens(profile),
                                      usage_out=usage_out))
            concepts = (payload or {}).get('concepts')
            if isinstance(concepts, list) and concepts:
                expansions[index] = {'concepts': concepts}
                break
            messages.append({'role': 'user', 'content':
                             'Reply with {"concepts": [...]} for exactly the concepts '
                             'listed, and nothing else.'})
            notes.append(f'unit {index + 1} attempt {attempt} produced no concepts')

    document = _merge(skeleton, expansions)
    # Scope any concept id that another course already owns, before the plan is built.
    # Doing it here rather than in the registry keeps ``blueprint.parse`` free of
    # catalogue lookups and keeps ``registry.store`` strict about the invariant it
    # exists to protect.
    document = _disambiguate(
        document, blueprint.course_id(str((document.get('course') or {}).get('title') or topic)))
    plan, problems = blueprint.parse(document, author='model')
    if plan is None:
        raise DraftRefused('The drafted blueprint could not be read: '
                           + '; '.join(str(problem) for problem in problems[:4]),
                           attempts=spent)
    course = synthesize.build(plan)
    report = audit_module.audit(course, profile=profile)
    if not report.ok:
        raise DraftRefused(
            f'The drafted course failed the audit with {len(report.errors)} blocking '
            f'finding(s): ' + '; '.join(f'{finding.code} ({finding.path})'
                                        for finding in report.errors[:4]),
            findings=report.errors, attempts=spent)
    return Draft(plan=plan, course=course, report=report, attempts=spent, notes=notes)


__all__ = ['ATTEMPTS', 'Draft', 'DraftRefused', 'DraftUnavailable', 'draft',
           'skeleton_tokens', 'unit_tokens']
