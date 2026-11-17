"""The learner-owned concept graph and the production BKT registry."""

from sqlalchemy import select

from app.db import BktModel, ConceptEvidenceLedger, LearnerConceptFacet, State, User
from test_api import account, answer, client, next_q, settings  # noqa: F401 - fixtures


def _metrics(logloss=0.42):
    return {
        'parameters': {'prior': 0.15, 'learn': 0.14, 'guess': 0.20, 'slip': 0.08},
        'evaluation': {'heldout_sequences': 60, 'heldout_students': 24,
                       'logloss': logloss, 'calibration_error': 0.03},
        'baseline': {'logloss': 0.51},
        'privacy': {'training_consent_only': True},
        'licence': {'note': 'Fitted locally on consented synthetic beta data.'},
    }


def _digits(seed):
    return format(seed, '064x')


def test_answer_writes_provenance_and_served_bkt_estimates(client):
    headers, registered = account(client, 'graph-learner')
    learner_id = registered['user']['id']
    question = next_q(client, headers, mode='practice', concept='fractions')
    response = client.post('/api/v1/attempts', headers=headers, json=answer(question, correct=True))
    assert response.status_code == 200, response.text
    body = response.json()
    estimates = body['model_estimates']
    assert estimates['facet'] in {'conceptual', 'procedural', 'calculation', 'retrieval'}
    assert estimates['facet_estimate'] > 0.15
    assert estimates['bkt']['model_version'] == 'builtin-default-v1'
    assert estimates['bkt']['p_next_correct'] > 0.15

    concept_id = question['concept_id']
    graph = client.get('/api/v1/learner-graph', headers=headers,
                       params={'concept_id': concept_id})
    assert graph.status_code == 200, graph.text
    payload = graph.json()
    assert len(payload['facets']) == 4 * len({concept_id})  # one row per facet
    assert {row['facet'] for row in payload['facets']} == set(payload['facet_vocabulary'])
    known = [row for row in payload['facets'] if row['mastery_known']]
    assert len(known) == 1 and known[0]['facet'] == estimates['facet']
    assert known[0]['provenance']['last_source_type'] == 'attempt'
    assert 'not a certified mastery score' in payload['note']

    with client.app.state.factory() as db:
        ledger = list(db.scalars(select(ConceptEvidenceLedger).where(
            ConceptEvidenceLedger.user_id == learner_id,
            ConceptEvidenceLedger.source_type == 'attempt')))
        assert ledger and ledger[-1].payload['correct'] is True
        facets = list(db.scalars(select(LearnerConceptFacet).where(
            LearnerConceptFacet.user_id == learner_id,
            LearnerConceptFacet.concept_id == concept_id)))
        assert len(facets) == 1
        state = db.scalar(select(State).where(
            State.user_id == learner_id, State.concept_id == concept_id))
        assert state.data['bkt_p_l'] > 0.15
        assert state.data['bkt']['method'] == 'bkt-forward-update-v1'


def _admin_headers(client, email='registry-admin'):
    headers, _ = account(client, email)
    with client.app.state.factory() as db:
        user = db.scalar(select(User).where(User.email == f'{email}@example.test'))
        user.role = 'admin'
        db.commit()
    return headers


def test_registry_promotes_shadow_and_rolls_back_to_the_previous_active(client):
    admin = _admin_headers(client)
    learner, _ = account(client, 'registry-learner')

    def register(version, seed, logloss=0.42):
        response = client.post('/api/v1/bkt/models', headers=admin, json={
            'version': version, 'artifact_path': f'models/{version}.json',
            'digest': _digits(seed), 'metrics': _metrics(logloss),
            'licence_note': 'Consented local fit.'})
        assert response.status_code == 200, response.text
        return response.json()

    register('bkt-v1', 1)
    register('bkt-v2', 2, logloss=0.55)

    # A candidate cannot be promoted straight to active: the gate is not optional.
    refused = client.post('/api/v1/bkt/models/bkt-v1/promote', headers=admin,
                          json={'stage': 'active', 'reason': 'looks good'})
    assert refused.status_code == 422, refused.text

    # A worse model fails the gate even after shadow evaluation.
    assert client.post('/api/v1/bkt/models/bkt-v2/promote', headers=admin,
                       json={'stage': 'shadow', 'reason': 'evaluate'}).status_code == 200
    worse = client.post('/api/v1/bkt/models/bkt-v2/promote', headers=admin,
                        json={'stage': 'active', 'reason': 'worse logloss'})
    assert worse.status_code == 422 and 'gate failed' in worse.text

    assert client.post('/api/v1/bkt/models/bkt-v1/promote', headers=admin,
                       json={'stage': 'shadow', 'reason': 'evaluate'}).status_code == 200
    active = client.post('/api/v1/bkt/models/bkt-v1/promote', headers=admin,
                         json={'stage': 'active', 'reason': 'passed heldout gate'})
    assert active.status_code == 200, active.text
    assert active.json()['stage'] == 'active'

    status = client.get('/api/v1/bkt/registry', headers=learner)
    assert status.status_code == 200, status.text
    assert status.json()['serving']['version'] == 'bkt-v1'
    assert any(model['version'] == 'bkt-v2' and model['stage'] == 'shadow'
               for model in status.json()['models'])

    # A learner cannot promote anything, even knowing the exact endpoint.
    denied = client.post('/api/v1/bkt/models/bkt-v2/promote', headers=learner,
                         json={'stage': 'active', 'reason': 'please'})
    assert denied.status_code == 403, denied.text

    # Promote the shadow candidate properly, then roll it back to the known-good model.
    better = _metrics(logloss=0.36)
    with client.app.state.factory() as db:
        row = db.scalar(select(BktModel).where(BktModel.version == 'bkt-v2'))
        row.metrics = better
        db.commit()
    assert client.post('/api/v1/bkt/models/bkt-v2/promote', headers=admin,
                       json={'stage': 'active', 'reason': 'improved logloss'}).status_code == 200
    rollback = client.post('/api/v1/bkt/models/bkt-v2/rollback', headers=admin,
                           json={'reason': 'drift in live answers'})
    assert rollback.status_code == 200, rollback.text
    assert rollback.json()['restored'] == 'bkt-v1'
    assert client.get('/api/v1/bkt/registry', headers=learner).json()['serving']['version'] == 'bkt-v1'
