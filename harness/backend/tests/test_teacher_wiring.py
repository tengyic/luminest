"""The teaching decision reaches the live tutor, not only the plan object.

``test_teacher_core.py`` proves the policy is right. This file proves the policy is
*used*: that a real ``POST /chat`` turn carries the selected move into the system
prompt, that the move is derived from the learner's stored state rather than from a
constant, and that a learner with no plan still gets a normal turn.

That distinction matters because it is exactly how the previous teacher failed. The
prompt described nine moves beautifully and the model picked one itself; nothing
checked that the prose and the scorer agreed. A block that is rendered but never
delivered would be the same bug with better plumbing, so the assertion here is on
the bytes the provider would actually receive.
"""

import httpx
import pytest
from sqlalchemy import select

from app import tutor as tutor_module
from app.config import Settings
from app.db import State, User
from app.harness.teaching import (build_evidence, concept_facts, default_profile,
                                  plan_session, render_plan_block)
from test_api import account  # noqa: F401 - shared fixture helper

CONCEPT = 'fractions'


@pytest.fixture
def wired(tmp_path, monkeypatch):
    """A real app whose provider is configured but never reached over the network."""
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('HARNESS_TUTOR_PROVIDER', 'openai')
    monkeypatch.setenv('HARNESS_TUTOR_URL', 'https://provider.example.test/v1')
    monkeypatch.setenv('HARNESS_TUTOR_MODEL', 'test-model')
    monkeypatch.setenv('HARNESS_TUTOR_KEY', 'test-key-not-real')
    from fastapi.testclient import TestClient
    from app.main import create_app
    with TestClient(create_app(Settings.from_env())) as test_client:
        yield test_client


def _capture_system(monkeypatch):
    """Replace the provider client so the test sees the exact messages sent."""
    captured = {}

    class FakeResponse:
        content = b'{}'

        def raise_for_status(self):
            pass

        def json(self):
            return {'choices': [{'message': {'content': 'Here is the next step.'}}]}

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, json=None, headers=None):
            captured['messages'] = [dict(message) for message in json['messages']]
            return FakeResponse()

    monkeypatch.setattr(tutor_module.httpx, 'Client', FakeClient)
    return captured


def _system_of(captured):
    return next(message['content'] for message in captured['messages']
                if message['role'] == 'system')


def _set_state(client, email, **data):
    """Write the learner's stored state the way a practice answer would."""
    with client.app.state.factory() as db:
        user = db.scalar(select(User).where(User.email == email))
        assert user is not None, email
        db.add(State(user_id=user.id, concept_id=CONCEPT, data=data))
        db.commit()


def _turn(client, headers, message='Where do I start?'):
    response = client.post('/api/v1/chat', headers=headers,
                           json={'concept_id': CONCEPT, 'message': message})
    assert response.status_code == 200, response.text
    return response


def test_the_policy_decision_is_in_the_prompt_the_provider_receives(wired, monkeypatch):
    captured = _capture_system(monkeypatch)
    headers, _ = account(wired)
    _turn(wired, headers)
    system = _system_of(captured)
    assert "This turn's teaching decision" in system
    assert '- Move: ' in system
    assert '- Because: ' in system
    # The decision names a move the profile actually declares - never a free-text
    # improvisation that happens to read like one.
    names = {spec.name for spec in default_profile().moves}
    move = system.split('- Move: ', 1)[1].split('\n', 1)[0].split(' (', 1)[0].strip()
    assert move in names, move


def test_the_decision_follows_the_learners_stored_state(wired, monkeypatch):
    """Two learners, same concept, different evidence: the prompt must differ.

    A block that is present but constant would pass the test above and still be a
    hand-written prompt wearing a plan's clothes.
    """
    captured = _capture_system(monkeypatch)
    fresh_headers, _ = account(wired, 'fresh')
    _turn(wired, fresh_headers)
    fresh_move = _system_of(captured).split('- Move: ', 1)[1].split('\n', 1)[0]

    mastered_headers, _ = account(wired, 'mastered')
    _set_state(wired, 'mastered@example.test', mastery=0.95, attempts=9,
               correct_count=9, last_correct=True, stability=40.0,
               last_review=1_700_000_000.0, elapsed_trend='steady')
    _turn(wired, mastered_headers)
    mastered_move = _system_of(captured).split('- Move: ', 1)[1].split('\n', 1)[0]
    assert fresh_move != mastered_move, (fresh_move, mastered_move)


def test_a_mastered_learner_is_not_sent_back_to_the_introduction(wired, monkeypatch):
    """The specific failure the rebuilt policy exists to prevent: teaching a concept
    the learner has already demonstrated, because the prompt had no evidence in it."""
    captured = _capture_system(monkeypatch)
    headers, _ = account(wired, 'expert')
    _set_state(wired, 'expert@example.test', mastery=0.95, attempts=9,
               correct_count=9, last_correct=True, stability=40.0,
               last_review=1_700_000_000.0, elapsed_trend='steady')
    _turn(wired, headers)
    assert '- Move: explain' not in _system_of(captured)


def test_the_plan_block_lists_the_phases_in_order(wired):
    facts = concept_facts(CONCEPT)
    plan = plan_session(build_evidence(facts, {'mastery': 0.4, 'attempts': 3}),
                        facts, default_profile())
    block = render_plan_block(plan)
    assert block.startswith("This turn's teaching decision")
    positions = [block.index(f'- {phase}:') for phase in plan.phases]
    assert positions == sorted(positions), plan.phases


def test_no_plan_renders_nothing_rather_than_a_placeholder(wired):
    """A caller without learner state is a normal case. An empty block is honest; a
    placeholder would be something the model tries to satisfy."""
    assert render_plan_block(None) == ''
    assert tutor_module._plan_section(None) == ''


def test_the_agent_loop_carries_the_decision_to_the_tool_registry(wired, monkeypatch):
    """The agent route is where the loop is actually executed - the whiteboard,
    simulation, image and speech tools all live in its registry. A decision delivered
    only to the prose route would leave the tool-calling teacher choosing its own move,
    which is the defect the rebuild exists to remove."""
    from app.harness import provider

    captured = {}

    def fake_chat_tools(settings, messages, **kwargs):
        captured['messages'] = [dict(message) for message in messages]
        return {'content': 'Drew the number line.', 'tool_calls': [], 'finish_reason': 'stop',
                'usage': {}, 'reasoning': None}

    monkeypatch.setattr(provider, 'chat_tools', fake_chat_tools)
    headers, _ = account(wired, 'agentic')
    response = wired.post('/api/v1/agent/chat', headers=headers, json={
        'session_id': 's1', 'message': 'Teach me fractions',
        'context': {'concept_id': CONCEPT}})
    assert response.status_code == 200, response.text
    system = _system_of(captured)
    assert "This turn's teaching decision" in system
    assert '- Move: ' in system


def test_a_failing_plan_does_not_fail_the_turn(wired, monkeypatch):
    """Losing the decision degrades the turn; losing the turn is worse."""
    captured = _capture_system(monkeypatch)

    def broken(*args, **kwargs):
        raise RuntimeError('policy exploded')

    monkeypatch.setattr(tutor_module, 'render_plan_block', broken)
    headers, _ = account(wired, 'resilient')
    _turn(wired, headers)
    system = _system_of(captured)
    assert "This turn's teaching decision" not in system
    assert 'You are a supportive, evidence-grounded tutor' in system
