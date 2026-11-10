"""The tutor's voice and its hands: activity labels, draw-aloud, and spoken replies.

Three behaviours that all serve the same lesson - a tutor that teaches out loud while
it draws - and they are tested together because they fail together. Every one of them
runs against fakes: no test here touches the real VoiceStudio on loopback, reads a key,
or waits for a real synthesis.
"""

import time

import pytest

from app.config import Settings
from app.harness import agent_loop, speech, toolbox
from app.harness.agent_loop import run_agent, tool_label
from app.harness.toolbox import ToolResult

from test_api import account, client  # noqa: F401 - shared fixtures


# --------------------------------------------------------------------- helpers

def fake_engine(monkeypatch, payload: bytes = b'ID3fake-audio-bytes'):
    """A VoiceStudio that answers instantly with fixed bytes.

    The render path is exactly the production one - same digest, same staging file,
    same thread - so what is stubbed is only the 20-40 s of engine work.
    """
    monkeypatch.setattr(speech.voice_backend, 'synthesize',
                        lambda settings, text, **kwargs: payload)
    return payload


def voice_settings(tmp_path, monkeypatch, *, voice_enabled=True, media_enabled=False):
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HARNESS_TUTOR_PROVIDER', raising=False)
    monkeypatch.setenv('HARNESS_VOICE_ENABLED', '1' if voice_enabled else '0')
    monkeypatch.setenv('HARNESS_MEDIA_ENABLED', '1' if media_enabled else '0')
    return Settings.from_env()


@pytest.fixture
def agent_client(tmp_path, monkeypatch):
    """An agent client whose provider is 'configured' but never touched on the network:
    tests monkeypatch ``provider.chat_tools`` before hitting the routes."""
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('HARNESS_TUTOR_PROVIDER', 'openai')
    monkeypatch.setenv('HARNESS_TUTOR_URL', 'https://provider.example.test/v1')
    monkeypatch.setenv('HARNESS_TUTOR_MODEL', 'test-model')
    monkeypatch.setenv('HARNESS_TUTOR_KEY', 'test-key-not-real')
    monkeypatch.setenv('HARNESS_TUTOR_TIMEOUT_SECONDS', '5')
    from fastapi.testclient import TestClient
    from app.main import create_app
    with TestClient(create_app(Settings.from_env())) as test_client:
        yield test_client


def answering(monkeypatch, content='The friction force opposes relative motion.'):
    """A provider that answers in one step, so the turn is deterministic."""
    from app.harness import provider

    def fake_chat_tools(settings, messages, **kwargs):
        return {'content': content, 'tool_calls': [], 'finish_reason': 'stop',
                'usage': {'prompt_tokens': 3, 'completion_tokens': 5}, 'reasoning': None}

    monkeypatch.setattr(provider, 'chat_tools', fake_chat_tools)


def system_of(monkeypatch) -> dict:
    """Capture the system prompt a turn assembled."""
    from app.harness import provider
    captured = {}

    def fake_chat_tools(settings, messages, **kwargs):
        captured['system'] = messages[0]['content'] if messages else ''
        return {'content': 'ok', 'tool_calls': [], 'finish_reason': 'stop',
                'usage': {}, 'reasoning': None}

    monkeypatch.setattr(provider, 'chat_tools', fake_chat_tools)
    return captured


# --------------------------------------------------------- activity labels

def test_a_label_names_the_action_not_the_tool():
    """A chip that says "whiteboard_apply" teaches the learner the API instead of the
    concept. The label is the sentence the tutor would say while it works."""
    assert tool_label('whiteboard_apply') == 'Drawing on the whiteboard'
    assert tool_label('whiteboard_place_image') == 'Pinning a picture on the whiteboard'
    assert tool_label('check_understanding') == 'Preparing a question for you'
    # Every label is prose: no underscores, no empty string, no trailing whitespace.
    for name, label in agent_loop.TOOL_LABELS.items():
        assert label and label == label.strip(), name
        assert '_' not in label, name
        assert label[0].isupper(), name


def test_every_registered_tool_has_a_readable_label():
    """The map must not rot as tools are added. An unlisted tool still gets a readable
    fallback rather than a blank chip or "unknown tool"."""
    for name in toolbox.REGISTRY:
        label = tool_label(name)
        assert label and '_' not in label, name
        assert label != 'unknown tool'


def test_the_fallback_title_cases_an_unlisted_tool():
    assert tool_label('some_future_tool') == 'Some future tool'
    assert tool_label('') == 'Working on it'


def test_loop_events_carry_a_label_while_the_tool_runs(tmp_path, monkeypatch):
    """The chip is shown *before* there is a result, so ``tool_call`` carries the label
    too - a client that only renders on results would show nothing until the work is
    already done, which is the one moment the chip is useless."""
    from app.harness import provider
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('HARNESS_TUTOR_PROVIDER', 'openai')
    monkeypatch.setenv('HARNESS_TUTOR_URL', 'https://provider.example.test/v1')
    monkeypatch.setenv('HARNESS_TUTOR_MODEL', 'test-model')
    monkeypatch.setenv('HARNESS_TUTOR_KEY', 'test-key-not-real')
    settings = Settings.from_env()

    def fake_chat_tools(settings, messages, **kwargs):
        return {'content': None,
                'tool_calls': [{'id': 'c1', 'name': 'whiteboard_apply',
                                'arguments': {'ops': []}}],
                'finish_reason': 'tool_calls', 'usage': {}, 'reasoning': None}

    monkeypatch.setattr(provider, 'chat_tools', fake_chat_tools)
    events = list(run_agent(settings, [{'role': 'user', 'content': 'draw it'}],
                            {'whiteboard_apply': lambda a, ctx: ToolResult('whiteboard_apply',
                                                                          True, {})},
                            None))
    call = next(event for event in events if event['type'] == 'tool_call')
    result = next(event for event in events if event['type'] == 'tool_result')
    assert call['label'] == 'Drawing on the whiteboard'
    assert result['label'] == 'Drawing on the whiteboard'


# --------------------------------------------------------- draw-aloud protocol

def test_the_draw_aloud_protocol_arrives_only_when_a_board_is_in_scope(agent_client,
                                                                      monkeypatch):
    """The protocol's rules are about a surface that exists only when a board id is in
    context. Injecting it everywhere would have a model promising diagrams it cannot
    draw."""
    captured = system_of(monkeypatch)
    headers, _ = account(agent_client)
    assert agent_client.post('/api/v1/agent/chat', headers=headers, json={
        'message': 'Explain friction', 'context': {'concept_id': 'fractions',
                                                   'board_id': 'wb-fractions'}}).status_code == 200
    assert 'the whiteboard is the classroom' in captured['system']
    assert 'whiteboard_apply' in captured['system']

    captured.clear()
    assert agent_client.post('/api/v1/agent/chat', headers=headers, json={
        'message': 'Explain friction', 'context': {'concept_id': 'fractions'}}).status_code == 200
    assert 'the whiteboard is the classroom' not in captured['system']


def test_an_invalid_board_id_gets_no_board_framing(agent_client, monkeypatch):
    """A client-supplied id is data until it matches the board id shape; a malformed one
    must not open the whiteboard section of the prompt."""
    captured = system_of(monkeypatch)
    headers, _ = account(agent_client)
    agent_client.post('/api/v1/agent/chat', headers=headers, json={
        'message': 'Explain friction',
        'context': {'concept_id': 'fractions', 'board_id': 'not a board id'}})
    assert 'the whiteboard is the classroom' not in captured['system']


def test_the_protocol_asks_for_drawing_discipline_not_impersonation():
    """"Draw like Sal Khan" is a request for a technique. A tutor that claims an identity
    is a different defect from one that will not pick up the chalk, and the prompt has
    to be explicit about which one it is asking for."""
    from app import tutor
    assert 'never claim to be a real person' in tutor.DRAW_ALOUD_PROTOCOL
    assert 'Build, do not reveal' in tutor.DRAW_ALOUD_PROTOCOL
    assert 'Draw as you say it' in tutor.DRAW_ALOUD_PROTOCOL


# --------------------------------------------------------- spoken replies

def test_a_spoken_turn_asks_the_model_to_write_for_the_ear(agent_client, monkeypatch):
    """Speech is rendered from the reply text, so the reply has to be written for a
    speaker: short sentences, no tables, no formulas. Without this framing the audio
    says "vertical bar x vertical bar" for three minutes."""
    captured = system_of(monkeypatch)
    headers, _ = account(agent_client)
    agent_client.post('/api/v1/agent/chat', headers=headers,
                      json={'message': 'Teach me friction', 'speak': True})
    assert 'Write for the ear' in captured['system']
    assert 'Do not call text_to_speech' in captured['system']

    captured.clear()
    agent_client.post('/api/v1/agent/chat', headers=headers,
                      json={'message': 'Teach me friction'})
    assert 'Write for the ear' not in captured['system']


def test_a_spoken_turn_carries_a_speech_descriptor_and_renders_it(agent_client,
                                                                  monkeypatch, tmp_path):
    """The reply is spoken once, by the server, and the descriptor says where the bytes
    are and whether they exist yet. Rendering is off the request path, so the first
    answer is ``pending`` and the clip lands moments later."""
    answering(monkeypatch)
    fake_engine(monkeypatch)
    headers, _ = account(agent_client)
    response = agent_client.post('/api/v1/agent/chat', headers=headers, json={
        'message': 'Teach me friction', 'speak': True,
        'context': {'concept_id': 'fractions', 'board_id': 'wb-fractions'}})
    assert response.status_code == 200, response.text
    body = response.json()
    descriptor = body['speech']
    assert descriptor and descriptor['state'] == 'pending'
    assert descriptor['url'].startswith('/api/v1/media/audio/')
    # The same descriptor rides on the turn_end event, so the SSE client gets it too.
    final = body['events'][-1]
    assert final['type'] == 'turn_end' and final['speech'] == descriptor

    deadline = time.time() + 5
    while time.time() < deadline:
        state = agent_client.get(descriptor['url'] + '/state', headers=headers).json()
        if state['state'] != 'pending':
            break
        time.sleep(0.05)
    assert state['state'] == 'ready', state
    audio = agent_client.get(descriptor['url'], headers=headers)
    assert audio.status_code == 200
    assert audio.content == b'ID3fake-audio-bytes'


def test_a_repeated_answer_is_spoken_from_the_cache(agent_client, monkeypatch):
    """The same explanation for a second learner must not pay for synthesis twice: the
    cache is keyed by content, never by learner."""
    answering(monkeypatch)
    fake_engine(monkeypatch)
    headers, _ = account(agent_client)
    first = agent_client.post('/api/v1/agent/chat', headers=headers,
                              json={'message': 'Teach me friction', 'speak': True}).json()
    digest = first['speech']['digest']
    for _ in range(100):
        if speech.state(agent_client.app.state.settings, digest)['state'] == 'ready':
            break
        time.sleep(0.05)
    second = agent_client.post('/api/v1/agent/chat', headers=headers,
                               json={'message': 'Teach me friction', 'speak': True}).json()
    assert second['speech']['digest'] == digest
    assert second['speech']['state'] == 'ready'
    assert second['speech']['cached'] is True


def test_a_turn_nobody_asked_to_speak_carries_no_speech(agent_client, monkeypatch):
    answering(monkeypatch)
    headers, _ = account(agent_client)
    body = agent_client.post('/api/v1/agent/chat', headers=headers,
                             json={'message': 'Teach me friction'}).json()
    assert body['speech'] is None
    assert 'speech' not in body['events'][-1]


def test_a_turn_with_no_reply_says_nothing(agent_client, monkeypatch):
    """An offline turn with nothing to ground an answer in has no content, and a voice
    reading an empty string is a file that exists and says nothing."""
    headers, _ = account(agent_client)
    body = agent_client.post('/api/v1/agent/chat', headers=headers, json={
        'message': 'Hello', 'speak': True}).json()
    assert body['message'] is None
    assert body['speech'] is None


def test_voice_output_switched_off_is_reported_not_faked(agent_client, monkeypatch,
                                                         tmp_path):
    """An instance with ``voice_enabled=0`` must say "voice output is switched off"
    rather than rendering nothing and letting the learner wonder why the speaker
    button does nothing."""
    answering(monkeypatch)
    monkeypatch.setenv('HARNESS_VOICE_ENABLED', '0')
    # Rebuild the app so the route closure sees the operator's decision.
    from fastapi.testclient import TestClient
    from app.main import create_app
    with TestClient(create_app(Settings.from_env())) as off_client:
        headers, _ = account(off_client)
        body = off_client.post('/api/v1/agent/chat', headers=headers, json={
            'message': 'Teach me friction', 'speak': True}).json()
    assert body['speech']['state'] == 'unavailable'
    assert 'switched off' in body['speech']['reason']
    # The reason names the switch that actually decides this, so an operator is not sent to
    # the wrong variable when they go looking.
    assert 'HARNESS_VOICE_ENABLED' in body['speech']['reason']


def test_the_audio_route_needs_authentication(agent_client):
    assert agent_client.get('/api/v1/media/audio/' + '0' * 16).status_code == 401
    assert agent_client.get('/api/v1/media/audio/' + '0' * 16 + '/state').status_code == 401


def test_a_recording_that_does_not_exist_is_a_404(agent_client):
    headers, _ = account(agent_client)
    assert agent_client.get('/api/v1/media/audio/deadbeefdeadbeef',
                            headers=headers).status_code == 404
    assert agent_client.get('/api/v1/media/audio/deadbeefdeadbeef/state',
                            headers=headers).json()['state'] == 'unknown'


# --------------------------------------------------------- speech module

def test_plan_names_every_refusal_reason(tmp_path, monkeypatch):
    """Each refusal has a different fix, so each gets its own sentence - reachable here
    without a VoiceStudio on the machine."""
    on = voice_settings(tmp_path, monkeypatch)
    off = voice_settings(tmp_path, monkeypatch, voice_enabled=False)
    assert speech.plan(on, '   ')['reason'] == 'There is nothing to speak.'
    assert 'switched off' in speech.plan(off, 'Hello.')['reason']
    assert 'one utterance' in speech.plan(on, 'word ' * 20000)['reason']


def test_media_off_does_not_take_the_tutors_voice_with_it(tmp_path, monkeypatch):
    """The shipped desktop configuration: ``media_enabled=0``, voice on.

    This is the regression that made the app mute. ``media_enabled`` is off there to keep
    the privacy policy's "no outbound media" line true, and speech was gated on it, so every
    reply was refused before synthesis was attempted -- the tutor had a speaker button that
    could not work. A loopback call to the learner's own VoiceStudio is not an outbound
    fetch, so the two switches are separate and this combination must plan speech normally.
    """
    desktop_like = voice_settings(tmp_path, monkeypatch, voice_enabled=True,
                                  media_enabled=False)

    descriptor = speech.plan(desktop_like, 'Air masses meet at a front.')

    assert descriptor['state'] != speech.UNAVAILABLE
    assert 'switched off' not in str(descriptor.get('reason') or '')


def test_spoken_text_strips_markdown_for_the_ear():
    assert speech.spoken_text('See **friction** and [this](http://x) ## Step 2') == \
        'See friction and this Step 2'
    assert speech.spoken_text('  spaced   out  ') == 'spaced out'
    assert speech.spoken_text('') == ''


def test_a_long_reply_is_cut_at_a_sentence_boundary_never_mid_word():
    text = 'This sentence is exactly long enough to matter here. ' * 200
    utterance, truncated = speech._clip(text)
    assert truncated is True
    assert len(utterance) <= speech.MAX_UTTERANCE_CHARS
    assert utterance.endswith('.')
    assert not utterance.endswith(' ')


def test_the_digest_covers_everything_that_changes_the_bytes():
    """One passage, one file - and a different voice or speed is a different recording,
    so it must not collide with the first."""
    base = speech._digest('omnivoice', 'default', 1.0, '', 'Friction opposes motion.')
    assert base == speech._digest('omnivoice', 'default', 1.0, '', 'Friction opposes motion.')
    assert base != speech._digest('omnivoice', 'default', 1.0, '', 'Different text.')
    assert base != speech._digest('omnivoice', 'other-voice', 1.0, '', 'Friction opposes motion.')
    assert base != speech._digest('omnivoice', 'default', 1.5, '', 'Friction opposes motion.')
    assert base != speech._digest('omnivoice', 'default', 1.0, 'warm', 'Friction opposes motion.')


def test_the_cache_serves_a_clip_once_and_forgets_it(tmp_path, monkeypatch):
    on = voice_settings(tmp_path, monkeypatch)
    fake_engine(monkeypatch)
    first = speech.request(on, 'Friction opposes relative motion.')
    assert first['state'] == 'pending'
    deadline = time.time() + 5
    while time.time() < deadline:
        if speech.state(on, first['digest'])['state'] != 'pending':
            break
        time.sleep(0.05)
    assert speech.state(on, first['digest'])['state'] == 'ready'
    assert speech.file_for(on, first['digest']).read_bytes() == b'ID3fake-audio-bytes'

    replay = speech.request(on, 'Friction opposes relative motion.')
    assert replay['state'] == 'ready' and replay['cached'] is True

    assert speech.forget(on, first['digest']) is True
    assert speech.file_for(on, first['digest']) is None
    assert speech.forget(on, first['digest']) is False


def test_a_digest_never_reaches_the_filesystem(tmp_path, monkeypatch):
    """The digest is the only client-controlled string that reaches a path here, so it
    is validated before it is joined - a traversal attempt is a missing recording."""
    on = voice_settings(tmp_path, monkeypatch)
    assert speech.file_for(on, '../../etc/passwd') is None
    assert speech.file_for(on, '') is None
    assert speech.file_for(on, 'a' * 200) is None
    assert speech.state(on, '../secrets')['state'] == 'unknown'


def test_a_render_failure_is_reported_with_the_engines_own_reason(tmp_path, monkeypatch):
    """A VoiceStudio that is not running is a state an operator fixes; the descriptor
    must carry the engine's sentence rather than a generic error."""
    from app.harness.voice import VoiceError

    def refuse(settings, text, **kwargs):
        raise VoiceError('not_running', 'No VoiceStudio is listening on '
                                        'http://127.0.0.1:3900.')

    monkeypatch.setattr(speech.voice_backend, 'synthesize', refuse)
    on = voice_settings(tmp_path, monkeypatch)
    descriptor = speech.render(on, 'Friction opposes relative motion.')
    assert descriptor['state'] == 'failed'
    assert 'No VoiceStudio is listening' in descriptor['reason']
    assert descriptor['code'] == 'not_running'
    # And nothing was written: a failed render must not leave a file that looks cached.
    assert speech.file_for(on, descriptor['digest']) is None
