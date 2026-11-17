"""The generative-interactive vocabulary: closed, checkable, and stateful."""

import copy

import pytest

from app import declarative_ui
from app.harness import toolbox
from test_telemetry import app, _learner  # noqa: F401

SPEC = {
    'schema_version': 1,
    'title': 'Product probe',
    'components': [
        {'id': 'a', 'type': 'slider', 'label': 'First factor',
         'min': 0, 'max': 10, 'step': 1, 'initial': 2},
        {'id': 'b', 'type': 'slider', 'label': 'Second factor',
         'min': 0, 'max': 10, 'step': 1, 'initial': 3},
        {'id': 'product', 'type': 'readout', 'label': 'Product',
         'expr': {'op': 'mul', 'args': [{'ref': 'a'}, {'ref': 'b'}]}},
        {'id': 'check', 'type': 'feedback',
         'when': {'op': 'eq', 'args': [{'ref': 'product'}, 12]},
         'correct': 'Twelve. What changed when one factor doubled?',
         'incorrect': 'Not twelve yet. Try moving one factor.'},
        {'id': 'reset', 'type': 'reset'},
    ],
}


def test_registry_publishes_a_closed_vocabulary():
    published = declarative_ui.registry()
    assert published['schema_version'] == declarative_ui.SCHEMA_VERSION
    assert {'slider', 'number', 'choice', 'readout', 'feedback', 'reset'} <= set(
        published['components'])
    assert {'add', 'mul', 'eq', 'not'} <= set(published['expression']['operators'])
    assert 'No scripts' in published['note']


def test_validation_normalizes_a_valid_spec():
    validated = declarative_ui.validate(SPEC)
    assert validated['inputs'] == ['a', 'b']
    assert [item['id'] for item in validated['components']] == [
        'a', 'b', 'product', 'check', 'reset']
    assert declarative_ui.validate(SPEC) == validated  # pure, idempotent


@pytest.mark.parametrize('mutation', [
    lambda spec: spec.update({'script': 'alert(1)'}),
    lambda spec: spec['components'][0].update({'onclick': 'fetch("/x")'}),
    lambda spec: spec['components'][2].update({'expr': {'op': 'eval', 'args': ['1+1']}}),
    lambda spec: spec['components'][2].update({'expr': {'ref': 'missing'}}),
    lambda spec: spec['components'].append(dict(spec['components'][0])),
    lambda spec: spec.update({'schema_version': 99}),
])
def test_validation_refuses_untrusted_shapes(mutation):
    spec = copy.deepcopy(SPEC)
    mutation(spec)
    with pytest.raises(ValueError):
        declarative_ui.validate(spec)


def test_evaluation_recalculates_and_keeps_honest_evidence():
    validated = declarative_ui.validate(SPEC)
    frame = declarative_ui.evaluate(validated, {'a': 3, 'b': 4, 'stranger': 9})
    assert frame['readouts']['product'] == 12
    assert frame['feedback'][0]['passed'] is True
    assert frame['inputs']['a'] == 3
    assert frame['reset_state'] == {'a': 2, 'b': 3}
    assert frame['evidence']['inputs_touched'] == ['a', 'b']
    assert frame['evidence']['checks_passed'] == 1
    assert 'not a grade' in frame['evidence']['note']

    clamped = declarative_ui.evaluate(validated, {'a': 99, 'b': -5})
    assert clamped['inputs'] == {'a': 10, 'b': 0}
    assert clamped['feedback'][0]['passed'] is False


def test_toolbox_exposes_the_same_contract():
    spec, fn = toolbox.REGISTRY['validate_interactive']
    assert spec.argument_schema['properties']['spec']['type'] == 'object'
    result = fn(toolbox.ToolContext(), SPEC)
    assert result.ok and result.data['title'] == SPEC['title']
    bad = copy.deepcopy(SPEC)
    bad['components'][0]['html'] = '<script>'
    refused = fn(toolbox.ToolContext(), bad)
    assert not refused.ok and 'rejected' in refused.refused
    # A closed vocabulary has to be learnable from the refusal itself: a model that is
    # only told "no" invents component names, and the next call fails the same way.
    assert refused.data['components'] and 'slider' in refused.data['components']
    assert 'mul' in refused.data['operators']
    assert refused.data['limits']['max_components'] == declarative_ui.MAX_COMPONENTS
    assert 'only these' in refused.data['retry']


def test_authenticated_routes_validate_and_evaluate(app):
    _, client = app
    headers, _ = _learner(client.app, client, 'interactive@example.com')
    registry = client.get('/api/v1/interactive/registry', headers=headers)
    assert registry.status_code == 200, registry.text
    assert 'slider' in registry.json()['components']

    example = client.get('/api/v1/interactive/example', headers=headers)
    assert example.status_code == 200, example.text
    assert 'slider' in [item['type'] for item in example.json()['components']]

    validated = client.post('/api/v1/interactive/validate', headers=headers, json=SPEC)
    assert validated.status_code == 200, validated.text
    assert validated.json()['inputs'] == ['a', 'b']

    frame = client.post('/api/v1/interactive/evaluate', headers=headers,
                        json={'spec': SPEC, 'state': {'a': 3, 'b': 4}})
    assert frame.status_code == 200, frame.text
    assert frame.json()['readouts']['product'] == 12

    bad = copy.deepcopy(SPEC)
    bad['components'][0]['onclick'] = 'evil()'
    refused = client.post('/api/v1/interactive/validate', headers=headers, json=bad)
    assert refused.status_code == 422, refused.text
    assert 'unknown fields' in refused.json()['detail']
