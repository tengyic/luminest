"""The VoiceStudio bridge: probe, launch-on-miss, and honest failure reporting.

No GUI is ever opened in these tests. ``launch_app`` and ``probe`` are both
replaced, so the assertions are about the decision the script makes, not about
whatever VoiceStudio happens to be running on the developer's Mac.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from urllib.error import URLError

SCRIPT = (Path(__file__).resolve().parents[2] / 'scripts'
          / 'ensure_voicestudio.py')


def _bridge():
    spec = importlib.util.spec_from_file_location('ensure_voicestudio_under_test', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _Response:
    status = 200

    def __init__(self, payload: bytes):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self._payload


def test_the_script_is_packaged_and_loadable():
    assert SCRIPT.is_file()
    bridge = _bridge()
    assert bridge.DEFAULT_URL == 'http://127.0.0.1:3900'
    assert callable(bridge.ensure)


def test_probe_reads_the_openai_model_list(monkeypatch):
    bridge = _bridge()
    body = json.dumps({'data': [{'id': 'tts-1'}, {'id': 'omnivoice'}]}).encode()
    seen = {}

    def fake_open(request, timeout=None):
        seen['url'] = request.full_url
        seen['timeout'] = timeout
        return _Response(body)

    monkeypatch.setattr(bridge.OPEN_URL, 'open', fake_open)
    ready, models = bridge.probe('http://127.0.0.1:3900/')
    assert ready is True
    assert models == ['tts-1', 'omnivoice']
    assert seen['url'] == 'http://127.0.0.1:3900/v1/models'


def test_probe_refuses_a_body_that_is_not_a_model_list(monkeypatch):
    bridge = _bridge()
    monkeypatch.setattr(bridge.OPEN_URL, 'open',
                        lambda *a, **k: _Response(b'{"data": []}'))
    assert bridge.probe('http://127.0.0.1:3900') == (False, [])

    monkeypatch.setattr(bridge.OPEN_URL, 'open',
                        lambda *a, **k: _Response(b'not json'))
    assert bridge.probe('http://127.0.0.1:3900') == (False, [])

    def refused(*_a, **_k):
        raise URLError('connection refused')

    monkeypatch.setattr(bridge.OPEN_URL, 'open', refused)
    assert bridge.probe('http://127.0.0.1:3900') == (False, [])


def test_a_running_service_is_never_launched_twice(monkeypatch):
    bridge = _bridge()
    monkeypatch.setattr(bridge, 'probe', lambda *a, **k: (True, ['tts-1']))
    monkeypatch.setattr(bridge, 'launch_app',
                        lambda: (_ for _ in ()).throw(AssertionError('launched')))
    out = bridge.ensure(wait=0)
    assert out['ready'] is True
    assert out['action'] == 'already running'
    assert out['models'] == ['tts-1']


def test_a_missing_service_is_launched_and_waited_for(monkeypatch):
    bridge = _bridge()
    answers = iter([(False, []), (False, []), (True, ['omnivoice'])])
    monkeypatch.setattr(bridge, 'probe', lambda *a, **k: next(answers))
    monkeypatch.setattr(bridge.time, 'sleep', lambda _seconds: None)
    monkeypatch.setattr(bridge, 'launch_app', lambda: (True, 'opened'))
    out = bridge.ensure(wait=60)
    assert out['ready'] is True
    assert out['action'] == 'launched'
    assert out['models'] == ['omnivoice']


def test_no_launch_never_starts_the_app_and_reports_why(monkeypatch):
    bridge = _bridge()
    monkeypatch.setattr(bridge, 'probe', lambda *a, **k: (False, []))
    monkeypatch.setattr(bridge, 'launch_app',
                        lambda: (_ for _ in ()).throw(AssertionError('launched')))
    out = bridge.ensure(wait=0, allow_launch=False)
    assert out['ready'] is False
    assert out['action'] == 'probe only (launch disabled)'
    assert 'start VoiceStudio' in out['detail']


def test_launch_is_refused_off_macos(monkeypatch):
    bridge = _bridge()
    monkeypatch.setattr(bridge.platform, 'system', lambda: 'Linux')
    ok, why = bridge.launch_app()
    assert ok is False and 'macOS' in why


def test_main_returns_nonzero_when_the_service_stays_down(monkeypatch, capsys):
    bridge = _bridge()
    monkeypatch.setattr(bridge, 'ensure', lambda *a, **k: {
        'ready': False, 'url': 'http://127.0.0.1:3900', 'action': 'launch failed',
        'detail': 'not installed', 'models': [], 'elapsed_seconds': 0.1})
    assert bridge.main(['--no-launch']) == 1
    assert 'NOT READY' in capsys.readouterr().out
