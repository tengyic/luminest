"""A small, honest declarative runtime for generated interactive teaching objects.

This is not a general UI language. It is the *approved vocabulary* a model may emit when
it wants a native, stateful interaction: a handful of inputs, derived readouts, and
authored feedback. Everything else is refused. The refusal is the feature — a generative
runtime that accepts arbitrary HTML or Python is a remote-code-execution feature with a
friendlier name.

The contract has three halves, matching the audit's G8 finding:

1. :func:`registry` publishes the component and expression vocabulary. The UI renders
   from that vocabulary, never from a string the model invented.
2. :func:`validate` turns an untrusted spec into a normalized one or a named reason.
   No `eval`, no imports, no DOM, no network: references are ids and operators are an
   enum, so the tree can be checked before anything renders it.
3. :func:`evaluate` recomputes readouts and feedback from learner state. Evidence is
   returned with the reading, and explicitly refuses to call itself a grade.

What remains deliberately absent: arbitrary drawing, file access, third-party embeds,
model-supplied scripts, and persistence of interaction evidence as an ``Attempt``. Those
are separate decisions with separate gates, not things to smuggle into a validator.
"""

from __future__ import annotations

import math
import re
from typing import Any, Mapping

SCHEMA_VERSION = 1
MAX_COMPONENTS = 40
MAX_INPUTS = 16
MAX_EXPRESSION_DEPTH = 8
MAX_OPTIONS = 8
MAX_STRING = 400

_ID = re.compile(r'^[A-Za-z][A-Za-z0-9_]{0,31}$')
_INPUT_TYPES = frozenset({'slider', 'number', 'choice'})
_COMPONENT_TYPES = (_INPUT_TYPES | {'text', 'readout', 'feedback', 'reset'})
_OPS = frozenset({
    'add', 'sub', 'mul', 'div', 'min', 'max', 'abs',
    'eq', 'ne', 'lt', 'le', 'gt', 'ge', 'and', 'or', 'not',
})
_ARITY = {
    'add': (2, 8), 'sub': (2, 2), 'mul': (2, 8), 'div': (2, 2),
    'min': (2, 8), 'max': (2, 8), 'abs': (1, 1),
    'eq': (2, 2), 'ne': (2, 2), 'lt': (2, 2), 'le': (2, 2),
    'gt': (2, 2), 'ge': (2, 2), 'and': (2, 8), 'or': (2, 8), 'not': (1, 1),
}

_COMPONENT_FIELDS: dict[str, frozenset[str]] = {
    'text': frozenset({'id', 'type', 'content'}),
    'slider': frozenset({'id', 'type', 'label', 'min', 'max', 'step', 'initial'}),
    'number': frozenset({'id', 'type', 'label', 'min', 'max', 'initial'}),
    'choice': frozenset({'id', 'type', 'label', 'options', 'initial'}),
    'readout': frozenset({'id', 'type', 'label', 'expr'}),
    'feedback': frozenset({'id', 'type', 'when', 'correct', 'incorrect'}),
    'reset': frozenset({'id', 'type', 'label'}),
}
_REQUIRED_FIELDS: dict[str, frozenset[str]] = {
    'text': frozenset({'id', 'type', 'content'}),
    'slider': frozenset({'id', 'type', 'label', 'min', 'max', 'step'}),
    'number': frozenset({'id', 'type', 'label', 'min', 'max'}),
    'choice': frozenset({'id', 'type', 'label', 'options'}),
    'readout': frozenset({'id', 'type', 'label', 'expr'}),
    'feedback': frozenset({'id', 'type', 'when', 'correct', 'incorrect'}),
    'reset': frozenset({'id', 'type'}),
}


def registry() -> dict[str, Any]:
    """The vocabulary a client may render, published so it cannot drift silently."""
    return {
        'schema_version': SCHEMA_VERSION,
        'components': {
            name: {'fields': sorted(fields), 'required': sorted(_REQUIRED_FIELDS[name]),
                   'role': 'input' if name in _INPUT_TYPES else 'presentation'}
            for name, fields in sorted(_COMPONENT_FIELDS.items())
        },
        'expression': {
            'operators': sorted(_OPS),
            'forms': ['number', '{"const": value}', '{"ref": input_id}',
                      '{"op": operator, "args": [...]}'],
            'max_depth': MAX_EXPRESSION_DEPTH,
        },
        'limits': {'max_components': MAX_COMPONENTS, 'max_inputs': MAX_INPUTS,
                   'max_options': MAX_OPTIONS, 'max_string': MAX_STRING},
        'note': ('Declarative native interaction only. No scripts, network, DOM, file '
                 'access, or arbitrary markup. Feedback is authored guidance, not a '
                 'grade, and interaction state is not an Attempt.'),
    }


def _text(value: Any, field: str, *, required: bool = True) -> str:
    if value is None and not required:
        return ''
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{field} must be a non-empty string')
    if len(value) > MAX_STRING:
        raise ValueError(f'{field} exceeds {MAX_STRING} characters')
    return value


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f'{field} must be a number')
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f'{field} must be finite')
    return result


def _validate_expr(node: Any, inputs: set[str], depth: int = 0) -> None:
    if depth > MAX_EXPRESSION_DEPTH:
        raise ValueError(f'expression exceeds depth {MAX_EXPRESSION_DEPTH}')
    if isinstance(node, bool):
        raise ValueError('boolean literals must be written as {"const": true}')
    if isinstance(node, (int, float)):
        _number(node, 'expression constant')
        return
    if not isinstance(node, Mapping):
        raise ValueError('expression must be a number, const, ref, or op object')
    keys = set(node)
    if keys == {'const'}:
        value = node['const']
        if isinstance(value, str):
            if len(value) > MAX_STRING:
                raise ValueError('expression string exceeds limit')
        elif isinstance(value, bool):
            pass
        else:
            _number(value, 'expression constant')
        return
    if keys == {'ref'}:
        ref = node['ref']
        if not isinstance(ref, str) or ref not in inputs:
            raise ValueError(f'expression references unknown input {ref!r}')
        return
    if keys == {'op', 'args'} or keys == {'op', 'args', 'note'}:
        op = node['op']
        if not isinstance(op, str) or op not in _OPS:
            raise ValueError(f'unsupported expression operator {op!r}')
        args = node['args']
        if not isinstance(args, list):
            raise ValueError('expression args must be a list')
        low, high = _ARITY[op]
        if not low <= len(args) <= high:
            raise ValueError(f'operator {op} needs {low} to {high} arguments')
        for child in args:
            _validate_expr(child, inputs, depth + 1)
        return
    raise ValueError('expression object has unknown or missing keys')


def validate(spec: Any) -> dict[str, Any]:
    """Validate and normalize a model-produced spec. Raises ``ValueError`` on refusal."""
    if not isinstance(spec, Mapping):
        raise ValueError('spec must be an object')
    unknown = set(spec) - {'schema_version', 'title', 'concept_id', 'components'}
    if unknown:
        raise ValueError(f'unknown spec fields: {", ".join(sorted(unknown))}')
    if spec.get('schema_version') != SCHEMA_VERSION:
        raise ValueError(f'schema_version must be {SCHEMA_VERSION}')
    title = _text(spec.get('title'), 'title')
    concept_id = spec.get('concept_id')
    if concept_id is not None:
        concept_id = _text(concept_id, 'concept_id')
    components = spec.get('components')
    if not isinstance(components, list) or not 1 <= len(components) <= MAX_COMPONENTS:
        raise ValueError(f'components must be a list of 1 to {MAX_COMPONENTS} entries')

    seen: set[str] = set()
    inputs: set[str] = set()
    readouts: set[str] = set()
    normalized: list[dict[str, Any]] = []
    resets = 0
    for raw in components:
        if not isinstance(raw, Mapping):
            raise ValueError('each component must be an object')
        kind = raw.get('type')
        if not isinstance(kind, str) or kind not in _COMPONENT_TYPES:
            raise ValueError(f'unsupported component type {kind!r}')
        unknown = set(raw) - _COMPONENT_FIELDS[kind]
        if unknown:
            raise ValueError(f'unknown fields for {kind}: {", ".join(sorted(unknown))}')
        missing = _REQUIRED_FIELDS[kind] - set(raw)
        if missing:
            raise ValueError(f'{kind} is missing: {", ".join(sorted(missing))}')
        cid = _text(raw.get('id'), 'component id')
        if not _ID.fullmatch(cid):
            raise ValueError(f'component id {cid!r} must be a short identifier')
        if cid in seen:
            raise ValueError(f'duplicate component id {cid!r}')
        seen.add(cid)
        item: dict[str, Any] = {'id': cid, 'type': kind}
        if kind == 'text':
            item['content'] = _text(raw.get('content'), 'content')
        elif kind in ('slider', 'number'):
            item['label'] = _text(raw.get('label'), 'label')
            low = _number(raw.get('min'), 'min')
            high = _number(raw.get('max'), 'max')
            if low >= high:
                raise ValueError(f'{cid}: min must be less than max')
            item.update({'min': low, 'max': high})
            if kind == 'slider':
                step = _number(raw.get('step'), 'step')
                if step <= 0 or step > high - low:
                    raise ValueError(f'{cid}: step must be positive and within the range')
                item['step'] = step
            initial = raw.get('initial')
            item['initial'] = min(high, max(low, _number(initial, 'initial'))) if initial is not None else low
            inputs.add(cid)
        elif kind == 'choice':
            item['label'] = _text(raw.get('label'), 'label')
            options = raw.get('options')
            if not isinstance(options, list) or not 2 <= len(options) <= MAX_OPTIONS:
                raise ValueError(f'{cid}: options must contain 2 to {MAX_OPTIONS} strings')
            item['options'] = [_text(option, 'option') for option in options]
            if len(set(item['options'])) != len(item['options']):
                raise ValueError(f'{cid}: options must be unique')
            initial = raw.get('initial')
            if initial is None:
                item['initial'] = item['options'][0]
            elif initial not in item['options']:
                raise ValueError(f'{cid}: initial must be one of the options')
            else:
                item['initial'] = initial
            inputs.add(cid)
        elif kind == 'readout':
            item['label'] = _text(raw.get('label'), 'label')
            _validate_expr(raw.get('expr'), inputs | readouts)
            item['expr'] = raw['expr']
            readouts.add(cid)
        elif kind == 'feedback':
            _validate_expr(raw.get('when'), inputs | readouts)
            item.update({'when': raw['when'],
                         'correct': _text(raw.get('correct'), 'correct'),
                         'incorrect': _text(raw.get('incorrect'), 'incorrect')})
        elif kind == 'reset':
            resets += 1
            if 'label' in raw:
                item['label'] = _text(raw.get('label'), 'label')
            else:
                item['label'] = 'Reset'
        normalized.append(item)
    if len(inputs) > MAX_INPUTS:
        raise ValueError(f'at most {MAX_INPUTS} interactive inputs are allowed')
    if resets > 1:
        raise ValueError('only one reset component is allowed')
    return {
        'schema_version': SCHEMA_VERSION,
        'title': title,
        'concept_id': concept_id,
        'components': normalized,
        'inputs': sorted(inputs),
        'note': ('Validated against the published declarative component registry. '
                 'Feedback is authored guidance, not a certified grade.'),
    }


def _number_value(value: Any) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def _eval(node: Any, state: Mapping[str, Any]) -> Any:
    if isinstance(node, (int, float)) and not isinstance(node, bool):
        return float(node)
    if isinstance(node, Mapping):
        if 'const' in node:
            return node['const']
        if 'ref' in node:
            return state.get(node['ref'], 0.0)
        op, args = node['op'], [_eval(arg, state) for arg in node['args']]
        if op == 'add':
            return sum(_number_value(arg) for arg in args)
        if op == 'sub':
            return _number_value(args[0]) - _number_value(args[1])
        if op == 'mul':
            result = 1.0
            for arg in args:
                result *= _number_value(arg)
            return result
        if op == 'div':
            denominator = _number_value(args[1])
            if abs(denominator) < 1e-12:
                return 0.0
            return _number_value(args[0]) / denominator
        if op == 'min':
            return min(_number_value(arg) for arg in args)
        if op == 'max':
            return max(_number_value(arg) for arg in args)
        if op == 'abs':
            return abs(_number_value(args[0]))
        if op == 'eq':
            return args[0] == args[1]
        if op == 'ne':
            return args[0] != args[1]
        comparisons = {
            'lt': lambda a, b: a < b, 'le': lambda a, b: a <= b,
            'gt': lambda a, b: a > b, 'ge': lambda a, b: a >= b,
        }
        if op in comparisons:
            return comparisons[op](_number_value(args[0]), _number_value(args[1]))
        if op == 'and':
            return all(bool(arg) for arg in args)
        if op == 'or':
            return any(bool(arg) for arg in args)
        if op == 'not':
            return not bool(args[0])
    raise ValueError('unsupported expression')


def evaluate(spec: Mapping[str, Any], state: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Recompute one frame from learner state. The spec must already be validated."""
    supplied = dict(state or {})
    values: dict[str, Any] = {}
    for component in spec['components']:
        if component['type'] in _INPUT_TYPES:
            cid = component['id']
            value = supplied.get(cid, component['initial'])
            if component['type'] == 'choice':
                values[cid] = value if value in component['options'] else component['initial']
            else:
                number = _number_value(value)
                values[cid] = min(component['max'], max(component['min'], number))
    readouts: dict[str, Any] = {}
    feedback: list[dict[str, Any]] = []
    for component in spec['components']:
        if component['type'] == 'readout':
            result = _eval(component['expr'], {**values, **readouts})
            readouts[component['id']] = round(result, 6) if isinstance(result, float) else result
        elif component['type'] == 'feedback':
            passed = bool(_eval(component['when'], {**values, **readouts}))
            feedback.append({
                'id': component['id'], 'passed': passed,
                'text': component['correct'] if passed else component['incorrect'],
            })
    return {
        'inputs': values,
        'readouts': readouts,
        'feedback': feedback,
        'reset_state': {component['id']: component['initial']
                        for component in spec['components']
                        if component['type'] in _INPUT_TYPES},
        'evidence': {
            'inputs_touched': sorted(key for key in supplied if key in values),
            'checks_passed': sum(1 for item in feedback if item['passed']),
            'checks_total': len(feedback),
            'note': ('Interaction evidence for an authored task. It is not an Attempt, '
                     'not a receipt-bound answer, and not a grade.'),
        },
    }


__all__ = ['SCHEMA_VERSION', 'evaluate', 'registry', 'validate']
