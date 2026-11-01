"""Presenting the app's own window in a browser.

The client is SwiftUI, so this capability is a remote-desktop bridge rather than a web
frontend, and the tests are about the three things a bridge must get right:

1. **Off means off.** With the switch down, nothing is captured, no subprocess is started,
   and the refusal names the switch. A route that quietly 404s would look like a missing
   feature; a route that quietly captures would be a privacy incident.
2. **The window, not the desktop.** A capture is cropped to the frame the app reported, and
   a region that was never reported is a refusal — never "capture the whole screen instead".
3. **A missing permission is a sentence.** macOS grants Screen Recording and Accessibility
   per binary; when either is absent the caller gets a reason it can display, not a black
   rectangle and not a silent no-op.

No network and no real capture: the tool is stubbed, so these assert the contract rather
than the machine.
"""

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.harness import screen
from app.main import create_app

STREAM = '/api/v1/stream'


@pytest.fixture
def app_factory(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_ENV', 'development')   # first account becomes the operator
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    monkeypatch.delenv('HARNESS_SECRET', raising=False)
    monkeypatch.setenv('HARNESS_TUTOR_PROVIDER', 'offline')

    def build(stream_enabled: bool):
        monkeypatch.setenv('HARNESS_STREAM_ENABLED', '1' if stream_enabled else '0')
        return create_app(Settings.from_env())

    return build


def _sign_in(client, email='owner@local.test'):
    body = client.post('/api/v1/auth/register', json={
        'name': email.split('@')[0], 'email': email, 'password': 'Correct-Horse-9'}).json()
    return {'Authorization': 'Bearer ' + body['token']}, body['user']


@pytest.fixture(autouse=True)
def _forget_the_last_capture(monkeypatch):
    """Both memories in this module are process-global, so one test must not answer the next."""
    blank = {'at': 0.0, 'ok': False, 'detail': '', 'bytes': 0}
    screen._last_capture.update(blank)
    screen._recent_events.clear()
    # And the console state is the *machine's*, not the test's: without pinning it, these
    # tests would say different things depending on whether the Mac running them happened to
    # be asleep. The three states are each asserted explicitly where they matter.
    monkeypatch.setattr(screen, 'console_state', lambda: 'awake')
    yield
    screen._last_capture.update(blank)
    screen._recent_events.clear()


def _fake_capture(monkeypatch, payload=b'\xff\xd8fake-jpeg' * 100):
    """Replace the capture tool, not the module: the region check still has to run."""
    calls = []

    def fake_run(command, timeout=10.0):
        calls.append(command)
        if command[0] == screen.SCREENCAPTURE:
            target = command[-1]
            with open(target, 'wb') as handle:
                handle.write(payload)
        return 0, ''

    monkeypatch.setattr(screen, '_run', fake_run)
    return calls


def test_off_means_off_and_says_which_switch(app_factory, monkeypatch):
    calls = _fake_capture(monkeypatch)
    with TestClient(app_factory(False)) as client:
        headers, _user = _sign_in(client)
        status = client.get(STREAM + '/status', headers=headers).json()
        assert status['enabled'] is False
        assert 'HARNESS_STREAM_ENABLED' in status['reason']
        assert not calls, 'a switched-off instance must not start the capture tool'

        frame = client.get(STREAM + '/frame', headers=headers)
        assert frame.status_code == 503
        assert 'HARNESS_STREAM_ENABLED' in frame.json()['detail']


def test_the_window_is_the_frame_the_app_reported(app_factory, monkeypatch):
    calls = _fake_capture(monkeypatch)
    with TestClient(app_factory(True)) as client:
        headers, _user = _sign_in(client)

        missing = client.get(STREAM + '/frame', headers=headers)
        assert missing.status_code == 503
        assert 'has not reported its window' in missing.json()['detail']

        reported = client.post(STREAM + '/window', headers=headers,
                               json={'x': 120, 'y': 64, 'width': 1100, 'height': 720,
                                     'scale': 2.0})
        assert reported.status_code == 200
        assert reported.json()['window']['width'] == 1100

        frame = client.get(STREAM + '/frame', headers=headers)
        assert frame.status_code == 200
        assert frame.headers['content-type'] == 'image/jpeg'
        assert frame.headers['cache-control'].startswith('no-store')

    region = [call for call in calls if '-R' in call][-1]
    assert region[region.index('-R') + 1] == '120,64,1100,720'


def test_a_region_that_was_never_reported_is_not_the_whole_screen(app_factory, monkeypatch):
    """The tempting fallback — capture everything — is exactly what must not happen."""
    calls = _fake_capture(monkeypatch)
    with TestClient(app_factory(True)) as client:
        headers, _user = _sign_in(client)
        client.get(STREAM + '/frame', headers=headers)
    assert not [call for call in calls if '-R' in call]


def test_a_missing_screen_recording_permission_is_a_sentence(app_factory, monkeypatch):
    def refusing_run(command, timeout=10.0):
        if command[0] == screen.SCREENCAPTURE:
            return 1, 'could not create image from rect'
        return 0, ''

    monkeypatch.setattr(screen, '_run', refusing_run)
    with TestClient(app_factory(True)) as client:
        headers, _user = _sign_in(client)
        client.post(STREAM + '/window', headers=headers,
                    json={'x': 0, 'y': 0, 'width': 900, 'height': 600})
        frame = client.get(STREAM + '/frame', headers=headers)
    assert frame.status_code == 503
    assert 'Screen Recording' in frame.json()['detail']


def test_a_sleeping_display_is_not_blamed_on_screen_recording(app_factory, monkeypatch):
    """The commonest reason a stream stops on a Mac nobody is touching.

    Measured on this machine: ``screencapture -R`` fails with ``could not create image from
    rect`` while the display is asleep, exactly as it does without Screen Recording, and a
    whole-screen capture still *succeeds* — returning 93 KiB instead of 773 KiB. Telling the
    operator to grant a permission they already granted is the wrong answer, so the console
    is asked first.
    """
    monkeypatch.setattr(screen, 'console_state', lambda: 'asleep')
    monkeypatch.setattr(screen, '_run',
                        lambda command, timeout=10.0: (1, 'could not create image from rect'))
    with TestClient(app_factory(True)) as client:
        headers, _user = _sign_in(client)
        client.post(STREAM + '/window', headers=headers,
                    json={'x': 0, 'y': 0, 'width': 900, 'height': 600})
        frame = client.get(STREAM + '/frame', headers=headers)
        status = client.get(STREAM + '/status', headers=headers).json()

    assert frame.status_code == 503
    detail = frame.json()['detail']
    assert 'display is asleep' in detail
    assert 'Screen Recording' not in detail, 'that grant is not what is missing here'
    # And the status agrees, without listing a sleeping display as a permission problem.
    assert status['console'] == 'asleep'
    assert status['capture'] == 'refused'
    assert 'display is asleep' in status['capture_reason']
    assert not any('asleep' in line for line in status['permissions'])


def test_a_locked_screen_is_not_blamed_on_screen_recording(app_factory, monkeypatch):
    """A locked console fails the capture tool with the same message as a missing grant.

    Measured on this machine: ``screencapture -R`` says ``could not create image from rect``
    whether the screen is locked or Screen Recording is ungranted, and a *whole-screen*
    capture still succeeds while locked. Sending the operator to System Settings to grant a
    permission they already granted is the kind of wrong answer that costs an hour, so the
    lock state is read before the refusal is worded.
    """
    monkeypatch.setattr(screen, 'console_state', lambda: 'locked')
    monkeypatch.setattr(screen, '_run',
                        lambda command, timeout=10.0: (1, 'could not create image from rect'))
    with TestClient(app_factory(True)) as client:
        headers, _user = _sign_in(client)
        client.post(STREAM + '/window', headers=headers,
                    json={'x': 0, 'y': 0, 'width': 900, 'height': 600})
        frame = client.get(STREAM + '/frame', headers=headers)

    assert frame.status_code == 503
    detail = frame.json()['detail']
    assert 'locked' in detail
    assert 'Screen Recording' not in detail, 'that grant is not what is missing here'


def test_status_reports_the_last_capture_instead_of_taking_another(app_factory, monkeypatch):
    """The page asks for status every 15 s. Answering it by capturing would make the cheapest
    route on the page cost as much as the most expensive one, on a host that is also busy
    rendering the app being streamed."""
    calls = _fake_capture(monkeypatch)
    with TestClient(app_factory(True)) as client:
        headers, _user = _sign_in(client)
        client.post(STREAM + '/window', headers=headers,
                    json={'x': 0, 'y': 0, 'width': 900, 'height': 600})

        before = client.get(STREAM + '/status', headers=headers).json()
        assert before['capture'] == 'unknown', 'nothing has been captured, so nothing is known'
        assert 'last_frame_bytes' not in before, 'a size may not be invented'
        assert 'nothing is captured' in before['reason'].lower()

        client.get(STREAM + '/frame', headers=headers)
        after = client.get(STREAM + '/status', headers=headers).json()
        assert after['capture'] == 'permitted'
        assert after['last_frame_bytes'] > 512

        # An outcome older than the freshness window is not an answer either: the page is
        # told it is unknown rather than shown a verdict the server is not standing behind.
        monkeypatch.setattr(screen, '_CAPTURE_FRESH_SECONDS', 0.0)
        stale = client.get(STREAM + '/status', headers=headers).json()
        assert stale['capture'] == 'unknown'

    captures = [call for call in calls if call[0] == screen.SCREENCAPTURE]
    assert len(captures) == 1, 'only the frame request may start the capture tool'


def test_status_carries_the_reason_a_capture_failed(app_factory, monkeypatch):
    """A blank box is the failure mode this replaces: the page has to be able to say why."""
    def refusing_run(command, timeout=10.0):
        if command[0] == screen.SCREENCAPTURE:
            return 1, 'could not create image from rect'
        return 0, ''

    monkeypatch.setattr(screen, '_run', refusing_run)
    with TestClient(app_factory(True)) as client:
        headers, _user = _sign_in(client)
        client.post(STREAM + '/window', headers=headers,
                    json={'x': 0, 'y': 0, 'width': 900, 'height': 600})
        assert client.get(STREAM + '/frame', headers=headers).status_code == 503
        status = client.get(STREAM + '/status', headers=headers).json()

    assert status['capture'] == 'refused'
    assert any('Screen Recording' in line for line in status['permissions'])


def test_input_is_refused_for_a_learner_and_reports_a_missing_grant(app_factory, monkeypatch):
    monkeypatch.setattr(screen, '_run', lambda command, timeout=10.0: (1, '权限违例 (-10004)'))
    with TestClient(app_factory(True)) as client:
        teacher, _ = _sign_in(client, 'owner@local.test')
        learner, _ = _sign_in(client, 'pupil@local.test')

        assert client.get(STREAM + '/status', headers=learner).status_code == 403
        assert client.post(STREAM + '/input', headers=learner,
                           json={'kind': 'click', 'x': 1, 'y': 1}).status_code == 403

        client.post(STREAM + '/window', headers=teacher,
                    json={'x': 0, 'y': 0, 'width': 900, 'height': 600})
        answer = client.post(STREAM + '/input', headers=teacher,
                             json={'kind': 'click', 'x': 10, 'y': 10})
        assert answer.status_code == 200, 'a refusal is a state the page displays'
        assert answer.json()['ok'] is False
        assert 'Accessibility' in answer.json()['reason']


def test_an_unknown_event_kind_is_refused_by_name(app_factory, monkeypatch):
    monkeypatch.setattr(screen, '_run', lambda command, timeout=10.0: (0, 'Finder'))
    with TestClient(app_factory(True)) as client:
        headers, _user = _sign_in(client)
        client.post(STREAM + '/window', headers=headers,
                    json={'x': 0, 'y': 0, 'width': 900, 'height': 600})
        answer = client.post(STREAM + '/input', headers=headers,
                             json={'kind': 'teleport'}).json()
    assert answer['ok'] is False
    assert 'teleport' in answer['reason']


def test_a_reported_window_with_no_size_is_refused(app_factory):
    with TestClient(app_factory(True)) as client:
        headers, _user = _sign_in(client)
        response = client.post(STREAM + '/window', headers=headers,
                               json={'x': 0, 'y': 0, 'width': 0, 'height': 0})
    assert response.status_code == 422


def test_the_region_is_clamped_rather_than_trusted(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    settings = Settings.from_env()

    frame = screen.save_region(settings, {'x': -40, 'y': -8, 'width': 4, 'height': 4})
    assert frame['x'] == 0 and frame['y'] == 0
    assert frame['width'] == screen.MIN_SIDE and frame['height'] == screen.MIN_SIDE


def test_the_event_budget_bounds_a_held_key(monkeypatch, tmp_path):
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('HARNESS_STREAM_ENABLED', '1')
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    settings = Settings.from_env()

    screen._recent_events.clear()
    sent = []
    monkeypatch.setattr(screen, '_input_permitted', lambda: (True, ''))
    monkeypatch.setattr(screen, '_key', lambda code, **k: sent.append(code))
    screen.save_region(settings, {'x': 0, 'y': 0, 'width': 800, 'height': 600})

    results = [screen.send_input(settings, {'kind': 'key', 'code': 36})
               for _ in range(screen.MAX_EVENTS_PER_SECOND + 5)]

    assert len(sent) == screen.MAX_EVENTS_PER_SECOND
    assert results[-1]['ok'] is False
    assert 'dropped' in results[-1]['reason']


# --------------------------------------------------------------- throwing the switch

def test_the_switch_can_be_thrown_without_relaunching_the_app(app_factory, monkeypatch):
    """The defect this exists for.

    ``HARNESS_STREAM_ENABLED`` was read once, when the backend process started, and Settings
    said so ("takes effect the next time Luminfest starts"). A person who turned the switch on
    therefore got a browser tab that still said "switched off", and the only reading available
    to them was that the switch was broken. The switch now reaches the running instance.
    """
    calls = _fake_capture(monkeypatch)
    with TestClient(app_factory(False)) as client:
        headers, _user = _sign_in(client)
        assert client.get(STREAM + '/status', headers=headers).json()['enabled'] is False

        turned_on = client.post(STREAM + '/enable', headers=headers, json={'enabled': True})
        assert turned_on.status_code == 200
        assert turned_on.json()['enabled'] is True

        # Every streaming route reads the settings per request, so the next one sees the new
        # value. If any of them had closed over the object at import, this is where it shows.
        assert client.get(STREAM + '/status', headers=headers).json()['enabled'] is True
        client.post(STREAM + '/window', headers=headers,
                    json={'x': 10, 'y': 20, 'width': 800, 'height': 600})
        assert client.get(STREAM + '/frame', headers=headers).status_code == 200
    assert calls, 'with the switch on, the capture tool has to actually run'


def test_the_switch_can_be_turned_off_again(app_factory, monkeypatch):
    """On, then off, on one process: the privacy answer has to be symmetric."""
    calls = _fake_capture(monkeypatch)
    with TestClient(app_factory(True)) as client:
        headers, _user = _sign_in(client)
        client.post(STREAM + '/window', headers=headers,
                    json={'x': 0, 'y': 0, 'width': 800, 'height': 600})
        assert client.get(STREAM + '/frame', headers=headers).status_code == 200
        before = len(calls)

        off = client.post(STREAM + '/enable', headers=headers, json={'enabled': False})
        assert off.json()['enabled'] is False
        refused = client.get(STREAM + '/frame', headers=headers)
        assert refused.status_code == 503
        assert 'HARNESS_STREAM_ENABLED' in refused.json()['detail']
    assert len(calls) == before, 'nothing may be captured once the switch is off'


def test_a_hosted_instance_keeps_the_switch_with_its_operator(app_factory):
    """A teacher is not the operator of a hosted deployment.

    Where the backend runs on someone else's server, ``HARNESS_STREAM_ENABLED`` is that
    operator's policy about *their* screen, and an account inside the app must not overrule
    it. The environment is what distinguishes the two cases; it is replaced here the same way
    the route itself replaces the settings.
    """
    import dataclasses

    with TestClient(app_factory(False)) as client:
        headers, _user = _sign_in(client)
        client.app.state.settings = dataclasses.replace(
            client.app.state.settings, environment='production')
        refused = client.post(STREAM + '/enable', headers=headers, json={'enabled': True})
        assert refused.status_code == 403
        assert 'operator' in refused.json()['detail']
        assert client.app.state.settings.stream_enabled is False


def test_a_learner_cannot_throw_the_switch(app_factory):
    """The switch is the same teacher gate as every other operator tool, for the same reason:
    it is the host's screen."""
    with TestClient(app_factory(False)) as client:
        _headers, _user = _sign_in(client)
        learner = client.post('/api/v1/auth/register', json={
            'name': 'learner', 'email': 'learner@local.test',
            'password': 'Correct-Horse-9'}).json()
        refused = client.post(STREAM + '/enable',
                              headers={'Authorization': 'Bearer ' + learner['token']},
                              json={'enabled': True})
    assert refused.status_code == 403
