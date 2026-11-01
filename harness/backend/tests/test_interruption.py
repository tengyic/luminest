"""Being interrupted, and the difference between answering and announcing.

A tutor that is spoken aloud has a problem a text tutor does not: two of its utterances can
be in the air at once. The learner talking over an explanation, and the harness deciding on
its own to say something, are not the same event, and treating them the same is what makes
a voice assistant feel deaf.

Three things are pinned here:

1. An interruption is *told* to the model, so it does not finish the sentence it was cut
   off in.
2. The clip that answers an interruption is tagged ``replace``: it may stop what is playing.
3. An interval-check notice is tagged ``idle_only`` and is never invented when the
   supervisor chose to stay quiet.
"""

from app.harness import speech
from app.routes_supervision import _notice

from test_tutor_voice import agent_client, system_of  # noqa: F401 - fixtures and helpers

API = '/api/v1/agent/chat'


def _turn(client, payload):
    body = {'message': 'wait, why is it divided by r factorial?', **payload}
    return client.post(API, json=body, headers={'Authorization': 'Bearer ' + _token(client)})


def _token(client) -> str:
    response = client.post('/api/v1/auth/register',
                           json={'name': 't', 'email': 'interrupt@class.test',
                                 'password': 'long-secret-password'})
    return response.json()['token']


def test_an_interruption_is_named_to_the_model(agent_client, monkeypatch):
    captured = system_of(monkeypatch)
    response = _turn(agent_client, {'interrupted': True})
    assert response.status_code == 200
    assert 'interrupted you mid-sentence' in captured['system']
    assert 'Do not finish or resume' in captured['system']


def test_an_ordinary_message_does_not_claim_to_be_an_interruption(agent_client, monkeypatch):
    captured = system_of(monkeypatch)
    assert _turn(agent_client, {}).status_code == 200
    assert 'interrupted' not in captured['system'].casefold()


def test_an_answer_may_replace_what_is_playing():
    clip = speech.classify({'digest': 'abc', 'state': 'pending'}, 'answer')
    assert clip['kind'] == 'answer'
    assert clip['delivery'] == 'replace'


def test_an_explanation_queues_behind_what_is_playing():
    assert speech.classify({}, 'explanation')['delivery'] == 'append'


def test_a_notice_never_cuts_across_the_teacher():
    assert speech.classify({}, 'notification')['delivery'] == 'idle_only'


def test_an_unknown_kind_falls_back_to_an_explanation():
    assert speech.classify({}, 'shouting')['kind'] == 'explanation'


def test_the_interval_check_stays_silent_when_the_learner_is_working():
    notice = _notice({'move': {'kind': 'continue', 'why': 'working steadily'}, 'quiet': False})
    assert notice['say'] is False
    assert notice['delivery'] == 'idle_only'
    assert 'Nothing to say' in notice['reason']


def test_a_nudge_is_offered_as_an_idle_only_notification():
    notice = _notice({'move': {'kind': 'nudge', 'why': 'You have not moved for a while.'},
                      'quiet': False})
    assert notice['say'] is True
    assert notice['text'] == 'You have not moved for a while.'
    assert notice['delivery'] == 'idle_only'


def test_a_notice_inside_its_cooldown_is_withheld():
    notice = _notice({'move': {'kind': 'nudge', 'why': 'again'}, 'quiet': True})
    assert notice['say'] is False
    assert 'cooldown' in notice['reason']


# ------------------------------------- the interval check actually reaching a client

ASSESS = '/api/v1/supervision/assess'


def _assess(client, body):
    return client.post(ASSESS, json=body,
                       headers={'Authorization': 'Bearer ' + _token(client)})


def test_a_spoken_notice_carries_a_clip_the_client_can_play(agent_client, monkeypatch):
    """The silent half is only *supervision* if the learner can hear it.

    The client's interval check has no text to render: it gets a notice back from the
    server. So the clip has to arrive with the notice, rendered through the same voice a
    tutor turn uses - otherwise "silently, on an interval" is a line of text nobody is
    looking at. Patched here so the test does not need a synthesis engine.
    """
    rendered = {}

    def fake_request_sequence(settings, text, **kwargs):
        rendered['text'] = text
        return {'state': 'pending', 'digest': 'd1',
                'url': '/api/v1/media/audio/d1'}

    monkeypatch.setattr(speech, 'request_sequence', fake_request_sequence)
    response = _assess(agent_client, {'idle_seconds': 400, 'window_seconds': 300})
    assert response.status_code == 200
    notice = response.json()['notice']
    assert notice['say'] is True, notice
    assert notice['speech']['delivery'] == 'idle_only', 'a notice must not cut across speech'
    assert notice['speech']['kind'] == 'notification'
    assert notice['speech']['state'] == 'pending'
    assert rendered['text'] == notice['text'], 'the clip is of the sentence in the notice'


def test_a_withheld_notice_never_spends_a_synthesis(agent_client, monkeypatch):
    """No sentence means no clip: rendering the thought it chose to keep would leak it."""
    called = []
    monkeypatch.setattr(speech, 'request_sequence',
                        lambda *a, **k: called.append(1) or {})
    response = _assess(agent_client, {'idle_seconds': 0, 'window_seconds': 300})
    assert response.status_code == 200
    notice = response.json()['notice']
    assert notice['say'] is False
    assert 'speech' not in notice
    assert not called
