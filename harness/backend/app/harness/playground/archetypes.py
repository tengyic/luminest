"""The archetype contract: what a game template *is*, and how content is checked.

An archetype is a reusable interaction - "shift a curve", "sort tiles into
columns", "drag a point along a number line". It owns the mechanic, the rendering
and the feedback; it owns no content at all. Content arrives as a *spec*: a small
JSON object whose shape the archetype declares up front.

That split is the whole point of the playground. Twenty-four games exist because
twenty-four archetypes exist, each with one or two specs; a new game in an
existing shape costs a JSON object, not a page of JavaScript. And because the
shape is declared rather than assumed, a spec can be validated *before* anything
is rendered - which is what makes it safe to let a model author one.

Three rules the contract enforces on every archetype
----------------------------------------------------
**A spec is validated, not trusted.** :func:`validate_spec` checks required
fields, types, numeric bounds and list cardinality, and returns human-readable
problems. A generator that produces a malformed spec gets told what is wrong
instead of shipping a blank stage to a learner.

**Every archetype reports.** ``telemetry`` names what the game sends back. An
archetype that produces no checkable outcome must say so by declaring
``scored=False`` - which the harness then treats as a resource, never as
evidence. The distinction is the same one :mod:`app.simulation_map` draws for
third-party simulations, applied to our own.

**A spec is content, never code.** The spec is embedded as JSON and read by the
archetype's own script. Nothing in it is evaluated, so an authored spec cannot
smuggle behaviour past :func:`app.harness.sims_store.validate_html`.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Any, Callable, Iterable, Mapping, Sequence

from . import runtime

#: Spec field kinds. Deliberately a small closed set: each one has a validator
#: and a documented JSON shape, so an authoring model has nothing to guess at.
KINDS = ('text', 'int', 'float', 'bool', 'list', 'table')

#: When an archetype is allowed to post a committed outcome. See ``Archetype.commits_on``.
COMMIT_STATES = ('check', 'completion')

#: Hard ceiling on a rendered page, matching ``sims_store``'s own cap. A spec that
#: renders past this is refused here with a clearer message than the store's.
MAX_PAGE_BYTES = 400_000


@dataclass(frozen=True)
class Field:
    """One declared slot in an archetype's content schema."""

    key: str
    kind: str
    doc: str
    required: bool = True
    minimum: float | None = None
    maximum: float | None = None
    #: For ``list``: the shape of each element. For ``table``: the shape of each row.
    item_fields: tuple['Field', ...] = ()
    minimum_items: int = 0
    maximum_items: int = 40
    #: A closed vocabulary, for fields where any other value is a bug rather than a
    #: style choice - "left"/"right" for a shift direction, not "sideways". An
    #: authoring model that invents a value is told immediately, instead of
    #: producing a game whose correct answer can never be reached.
    choices: tuple[str, ...] = ()

    def describe(self) -> dict[str, Any]:
        out: dict[str, Any] = {'key': self.key, 'kind': self.kind, 'doc': self.doc,
                               'required': self.required}
        if self.minimum is not None:
            out['minimum'] = self.minimum
        if self.maximum is not None:
            out['maximum'] = self.maximum
        if self.choices:
            out['choices'] = list(self.choices)
        if self.kind in ('list', 'table'):
            out['minimum_items'] = self.minimum_items
            out['maximum_items'] = self.maximum_items
            if self.item_fields:
                out['item_fields'] = [f.describe() for f in self.item_fields]
        return out


@dataclass(frozen=True)
class Archetype:
    """A reusable interaction, plus the content schema it will accept."""

    id: str
    title: str
    blurb: str
    #: One short phrase naming the mechanic, e.g. "drag a curve and watch the
    #: intersection move". Shown in the playground gallery.
    interaction: str
    subjects: tuple[str, ...]
    tags: tuple[str, ...]
    #: The declared content schema. Order is presentation order.
    spec_fields: tuple[Field, ...]
    #: ``body(spec) -> str``: markup placed inside the stage element.
    body: Callable[[Mapping[str, Any]], str]
    #: ``engine(spec) -> str``: JavaScript defining ``build(root, spec)``. Runs
    #: after the runtime is in scope, with no wrapper and no imports.
    engine: Callable[[Mapping[str, Any]], str]
    width: int = 860
    height: int = 460
    #: Whether a completed run yields a checkable right/wrong. An unscored
    #: archetype is a sandbox: worth playing, never counted as evidence.
    scored: bool = True
    #: What counts as *committing* an answer, which is the only moment an archetype
    #: may post a ``luminfest:outcome``. ``'check'`` means the learner presses the Check
    #: button. ``'completion'`` means the interaction has a terminal state that is
    #: itself the answer - sorting every tile into a column, say - and reaching it
    #: commits, with no separate button.
    #:
    #: This is declared rather than inferred because it is the one thing that decides
    #: whether exploration can masquerade as mastery. A verifier cannot guess it from
    #: the markup, and guessing wrong means either waving through a game that scores
    #: a stray drag, or condemning a game that is behaving exactly as designed.
    commits_on: str = 'check'
    #: Plain-English statement of what the game sends back to the harness.
    telemetry: str = ''
    #: Where the idea came from, for the provenance record.
    reference: str = ''

    def describe(self) -> dict[str, Any]:
        return {
            'id': self.id, 'title': self.title, 'blurb': self.blurb,
            'interaction': self.interaction, 'subjects': list(self.subjects),
            'tags': list(self.tags), 'scored': self.scored,
            'commits_on': self.commits_on,
            'telemetry': self.telemetry, 'reference': self.reference,
            'schema': [f.describe() for f in self.spec_fields],
            'stage': {'width': self.width, 'height': self.height},
        }


# --------------------------------------------------------------------- registry

_REGISTRY: dict[str, Archetype] = {}


def _validate_declaration(archetype: Archetype) -> None:
    """Refuse an archetype whose own schema is malformed.

    Checked once at registration rather than on every spec, because a schema bug is
    a bug in this repository - not something a content author did - and it should
    stop the process at import, where it is trivial to find, instead of surfacing
    as a confusing validation message against somebody else's JSON.
    """
    def walk(fields: tuple[Field, ...], path: str) -> None:
        for item in fields:
            where = f'{archetype.id}.{path}{item.key}'
            if item.kind not in KINDS:
                raise ValueError(f'{where} declares unknown kind {item.kind!r}')
            if item.choices and item.kind != 'text':
                raise ValueError(f'{where} declares choices on a {item.kind} field; '
                                 'choices are only meaningful for text')
            if item.kind in ('list', 'table') and item.minimum_items > item.maximum_items:
                raise ValueError(f'{where} has minimum_items above maximum_items')
            if item.minimum is not None and item.maximum is not None \
                    and item.minimum > item.maximum:
                raise ValueError(f'{where} has minimum above maximum')
            if item.kind == 'table' and not item.item_fields:
                raise ValueError(f'{where} is a table with no declared row shape')
            walk(item.item_fields, f'{path}{item.key}[].')

    walk(archetype.spec_fields, '')
    if not archetype.body or not archetype.engine:
        raise ValueError(f'{archetype.id} must supply both body() and engine()')
    if archetype.scored and not archetype.telemetry:
        raise ValueError(f'{archetype.id} is scored but does not say what it reports; '
                         'a scored game with no stated telemetry cannot be evidence')
    if archetype.commits_on not in COMMIT_STATES:
        raise ValueError(f'{archetype.id} declares commits_on={archetype.commits_on!r}, '
                         f'which is not one of {list(COMMIT_STATES)}; the verifier reads '
                         'this to decide when an outcome is allowed to appear')
    if archetype.commits_on == 'completion' and not archetype.scored:
        raise ValueError(f'{archetype.id} commits on completion but is unscored; an '
                         'unscored sandbox must never post an outcome')


def register(archetype: Archetype) -> Archetype:
    """Add one archetype to the catalogue. Duplicate ids are refused, loudly.

    A silently overwritten archetype would mean two different games claiming one
    template - and whichever module happened to import second would win, which is
    the kind of order-dependent bug that only shows up in a frozen build.
    """
    if not archetype.id or not archetype.id.replace('_', '').isalnum():
        raise ValueError(f'Archetype id must be a simple identifier: {archetype.id!r}')
    if archetype.id in _REGISTRY:
        raise ValueError(f'Archetype {archetype.id!r} is already registered')
    _validate_declaration(archetype)
    _REGISTRY[archetype.id] = archetype
    return archetype


def register_all(items: Iterable[Archetype]) -> list[Archetype]:
    return [register(item) for item in items]


def all_archetypes() -> list[Archetype]:
    """Every registered archetype, in id order so listings are stable."""
    return [_REGISTRY[key] for key in sorted(_REGISTRY)]


def get(archetype_id: str) -> Archetype | None:
    return _REGISTRY.get(archetype_id)


def by_subject(subject: str) -> list[Archetype]:
    return [a for a in all_archetypes() if subject in a.subjects]


# ------------------------------------------------------------------- validation


def _check_value(field: Field, value: Any, path: str, problems: list[str]) -> None:
    """Validate one value against one field, appending any problems."""
    if value is None:
        if field.required:
            problems.append(f'{path} is required ({field.doc})')
        return
    if field.kind == 'text':
        if not isinstance(value, str):
            problems.append(f'{path} must be a string')
        elif not value.strip():
            problems.append(f'{path} must not be blank')
        elif field.choices and value not in field.choices:
            problems.append(f'{path} must be one of {list(field.choices)}, got {value!r}')
    elif field.kind == 'bool':
        if not isinstance(value, bool):
            problems.append(f'{path} must be true or false')
    elif field.kind in ('int', 'float'):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            problems.append(f'{path} must be a number')
            return
        if field.kind == 'int' and float(value) != int(value):
            problems.append(f'{path} must be a whole number')
        if field.minimum is not None and value < field.minimum:
            problems.append(f'{path} must be at least {field.minimum:g} (got {value:g})')
        if field.maximum is not None and value > field.maximum:
            problems.append(f'{path} must be at most {field.maximum:g} (got {value:g})')
    elif field.kind == 'list':
        if not isinstance(value, list):
            problems.append(f'{path} must be a list')
            return
        if len(value) < field.minimum_items:
            problems.append(f'{path} needs at least {field.minimum_items} item(s), got {len(value)}')
        if len(value) > field.maximum_items:
            problems.append(f'{path} allows at most {field.maximum_items} item(s), got {len(value)}')
        for index, item in enumerate(value):
            if field.item_fields:
                if not isinstance(item, Mapping):
                    problems.append(f'{path}[{index}] must be an object')
                    continue
                for sub in field.item_fields:
                    _check_value(sub, item.get(sub.key), f'{path}[{index}].{sub.key}', problems)
            elif not isinstance(item, (str, int, float, bool)):
                problems.append(f'{path}[{index}] must be a simple value')
    elif field.kind == 'table':
        if not isinstance(value, list):
            problems.append(f'{path} must be a list of rows')
            return
        if len(value) < field.minimum_items:
            problems.append(f'{path} needs at least {field.minimum_items} row(s), got {len(value)}')
        if len(value) > field.maximum_items:
            problems.append(f'{path} allows at most {field.maximum_items} row(s), got {len(value)}')
        for index, row in enumerate(value):
            if not isinstance(row, Mapping):
                problems.append(f'{path}[{index}] must be an object')
                continue
            for sub in field.item_fields:
                _check_value(sub, row.get(sub.key), f'{path}[{index}].{sub.key}', problems)
    else:  # pragma: no cover - guarded at registration time
        problems.append(f'{path} uses unknown field kind {field.kind!r}')


def validate_spec(spec: Mapping[str, Any], archetype: Archetype) -> list[str]:
    """Every reason this spec cannot render, or an empty list when it can.

    Problems are returned rather than raised because the caller is usually an
    authoring model or a teacher, and "field ``rows`` needs at least 2 items, got
    1" is actionable while a stack trace is not.
    """
    problems: list[str] = []
    if not isinstance(spec, Mapping):
        return ['The spec must be a JSON object.']
    declared = {f.key for f in archetype.spec_fields}
    for key in spec:
        if key not in declared:
            problems.append(
                f'{key!r} is not part of the {archetype.id!r} schema; '
                f'it accepts {sorted(declared)}')
    for field in archetype.spec_fields:
        _check_value(field, spec.get(field.key), field.key, problems)
    return problems


# -------------------------------------------------------------------- rendering


def render(archetype: Archetype, spec: Mapping[str, Any], *, title: str = '',
           instruction: str = '', subject: str = '') -> str:
    """Build the self-contained page for one spec.

    Raises ``ValueError`` on an invalid spec: rendering is the last step, and a
    caller that reaches it with a bad spec has skipped :func:`validate_spec`.

    ``subject`` overrides the archetype's first declared subject for the eyebrow.
    It matters because an archetype is shared across subjects - ``order_sequence``
    is used by both a mitosis game and a linear-search game - so the archetype's
    own subject list cannot know which one is on screen. Passing the *game's*
    subject is the difference between "BIOLOGY - PUT IT IN ORDER" and a biology
    game labelled MATHEMATICS, which is what the first version shipped.
    """
    problems = validate_spec(spec, archetype)
    if problems:
        raise ValueError('; '.join(problems))
    page = runtime.render_page(
        archetype_id=archetype.id,
        title=title or str(spec.get('title') or archetype.title),
        instruction=instruction or str(spec.get('instruction') or archetype.blurb),
        body_html=archetype.body(spec),
        engine_js=archetype.engine(spec),
        spec=spec,
        width=archetype.width, height=archetype.height,
        # The eyebrow names the subject and the *interaction*, not the game, so a
        # learner who met "drag a point along a number line" in maths recognises it
        # in science. That recognition is the point of having archetypes at all.
        subject=(subject or (archetype.subjects[0] if archetype.subjects else '')),
        archetype_title=archetype.title)
    if len(page.encode('utf-8')) > MAX_PAGE_BYTES:
        raise ValueError(f'The rendered page is {len(page)} characters, over the '
                         f'{MAX_PAGE_BYTES} cap; reduce the spec.')
    return page


def problems_for_page(page: str) -> list[str]:
    """Validate a rendered page with the same rules the artifact store will use."""
    from .. import sims_store
    return sims_store.validate_html(page, kind='simulation')
