"""End-to-end G8: model emission -> persisted artifact -> turn attachment -> evidence."""

import copy

from app.harness import agent_loop, provider, toolbox
from test_agent_loop import agent_client  # noqa: F401 - configured, network-free client
from test_api import account  # noqa: F401
from test_telemetry import app  # noqa: F401 - authenticated HTTP fixture

SPEC = {
    'schema_version': 1,
    'title': 'Area explorer',
    'concept_id': 'fractions',
    'components': [
        {'id': 'width', 'type': 'slider', 'label': 'Width',
         'min': 1, 'max': 8, 'step': 1, 'initial': 2},
        {'id': 'height', 'type': 'slider', 'label': 'Height',
         'min': 1, 'max': 8, 'step': 1, 'initial': 3},
        {'id': 'area', 'type': 'readout', 'label': 'Area',
         'expr': {'op': 'mul', 'args': [{'ref': 'width'}, {'ref': 'height'}]}},
        {'id': 'check', 'type': 'feedback',
         'when': {'op': 'eq', 'args': [{'ref': 'area'}, 12]},
         'correct': 'Twelve. Which dimension changed the area most?',
         'incorrect': 'Not twelve yet. Try one slider at a time.'},
        {'id': 'reset', 'type': 'reset'},
    ],
}


def test_emit_tool_persists_a_validated_artifact(app):
    _, client = app
    headers, _ = account(client, 'emit-owner')
    tool_spec, fn = toolbox.REGISTRY['emit_interactive']
    assert tool_spec.argument_schema['properties']['spec']['type'] == 'object'

    # A direct dispatch proves persistence does not depend on the SSE route.
    from sqlalchemy import select

    from app.db import InteractiveArtifact

    with client.app.state.factory() as db:
        from app.db import User

        user = db.scalar(select(User).where(User.email == 'emit-owner@example.test'))
        result = fn(toolbox.ToolContext(db=db, user=user), SPEC, concept_id='fractions')
        assert result.ok, result.refused
        assert result.data['artifact_id']
        assert db.scalar(select(InteractiveArtifact).where(
            InteractiveArtifact.id == result.data['artifact_id'],
            InteractiveArtifact.user_id == user.id)) is not None
        db.commit()

    bad = copy.deepcopy(SPEC)
    bad['components'][0]['onclick'] = 'fetch("/x")'
    with client.app.state.factory() as db:
        user = db.scalar(select(User).where(User.email == 'emit-owner@example.test'))
        refused = fn(toolbox.ToolContext(db=db, user=user), bad)
    assert not refused.ok and 'rejected' in refused.refused


def test_agent_turn_carries_the_artifact_and_records_bounded_evidence(
        agent_client, monkeypatch):
    calls = {'n': 0}

    def fake_chat_tools(settings, messages, **kwargs):
        calls['n'] += 1
        if calls['n'] == 1:
            return {'content': None, 'tool_calls': [{
                'id': 'emit-1', 'name': 'emit_interactive', 'arguments': {'spec': SPEC}}],
                'finish_reason': 'tool_calls', 'usage': {}, 'reasoning': None}
        return {'content': 'Move the sliders and watch the area.', 'tool_calls': [],
                'finish_reason': 'stop', 'usage': {}, 'reasoning': None}

    monkeypatch.setattr(provider, 'chat_tools', fake_chat_tools)
    headers, _ = account(agent_client, 'agent-interactive')
    turn = agent_client.post('/api/v1/agent/chat', headers=headers, json={
        'message': 'Show me why area changes.', 'context': {'concept_id': 'fractions'}})
    assert turn.status_code == 200, turn.text
    assert calls['n'] == 2
    attachments = turn.json()['interactive']
    assert len(attachments) == 1
    artifact = attachments[0]
    assert artifact['artifact_id'] and artifact['spec']['title'] == SPEC['title']

    reload = agent_client.get('/api/v1/interactive/artifacts/' + artifact['artifact_id'],
                              headers=headers)
    assert reload.status_code == 200, reload.text
    assert reload.json()['spec']['inputs'] == ['height', 'width']

    frame = agent_client.post('/api/v1/interactive/evidence', headers=headers, json={
        'artifact_id': artifact['artifact_id'], 'state': {'width': 3, 'height': 4}})
    assert frame.status_code == 200, frame.text
    body = frame.json()
    assert body['recorded'] is True
    assert body['readouts']['area'] == 12
    assert body['feedback'][0]['passed'] is True
    assert 'not a grade' in body['evidence']['note']

    # A forged frame cannot smuggle a new spec or an undeclared input into the ledger.
    refused = agent_client.post('/api/v1/interactive/evidence', headers=headers, json={
        'artifact_id': artifact['artifact_id'], 'state': {'admin': True}})
    assert refused.status_code == 422, refused.text

    # Another learner cannot read or write evidence against this artifact.
    other, _ = account(agent_client, 'other-interactive')
    assert agent_client.get('/api/v1/interactive/artifacts/' + artifact['artifact_id'],
                            headers=other).status_code == 404
    assert agent_client.post('/api/v1/interactive/evidence', headers=other, json={
        'artifact_id': artifact['artifact_id'], 'state': {'width': 1}}).status_code == 422


def test_published_tool_schemas_are_structural():
    payload = agent_loop.tools_payload(spec for spec, _ in toolbox.REGISTRY.values())
    schemas = {tool['function']['name']: tool['function']['parameters'] for tool in payload}
    emit = schemas['emit_interactive']
    assert emit['additionalProperties'] is False
    assert emit['properties']['spec']['type'] == 'object'
    assert set(emit['required']) == {'spec'}
