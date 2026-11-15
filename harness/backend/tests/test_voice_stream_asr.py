"""The live course's ASR is a streaming turn, not a batch job.

These tests pin the measured protocol facts from VoiceStudio 0.5.6 without
opening a socket: wait for ``ready`` before feeding audio, send only ``pcm``
and ``sr`` on the query, let trailing silence commit before the end control,
accept a summary final, and always degrade to the batch endpoint when the
stream cannot serve the utterance.
"""

from __future__ import annotations

import array
import io
import json
import wave
from types import SimpleNamespace

import pytest

from app.harness import voice


def _settings(**overrides):
    base = dict(voice_enabled=True, voice_base_url='http://127.0.0.1:3900',
                voice_api_key='', voice_timeout=120.0)
    base.update(overrides)
    return SimpleNamespace(**base)


def _wav(*, rate=8000, channels=1, seconds=0.5) -> bytes:
    frames = array.array('h', [1000 if i % 4 else -1000
                               for i in range(int(rate * seconds) * channels)])
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(frames.tobytes())
    return buffer.getvalue()


class _FakeSocket:
    """A scripted WebSocket. ``recv`` returns one event per call, then idles."""

    def __init__(self, events):
        self.events = list(events)
        self.sent_bytes: list[bytes] = []
        self.sent_text: list[str] = []
        self.closed = False

    def send_bytes(self, data):
        self.sent_bytes.append(data)

    def send_text(self, text):
        self.sent_text.append(text)

    def recv(self, timeout=None):
        return self.events.pop(0) if self.events else None

    def close(self):
        self.closed = True


class _BatchClient:
    response = {'text': 'batch heard this'}

    def __init__(self, *args, **kwargs):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return _Response()


class _Response:
    status_code = 200

    def json(self):
        return _BatchClient.response


# ------------------------------------------------------------------- decoding

def test_wav_is_decoded_to_mono_16k_pcm16():
    pcm = voice.decode_pcm(_wav(rate=8000, channels=2, seconds=0.5), 'audio/wav')
    assert pcm is not None
    # 0.5 s at 16 kHz mono s16le is 16 000 bytes; a linear resample may stop a
    # couple of samples short of the last input frame, and stereo was downmixed.
    assert 15990 <= len(pcm) <= 16000
    assert len(pcm) % 2 == 0


def test_tiny_or_undecodable_input_is_not_sent_to_the_stream():
    assert voice.decode_pcm(b'audio', 'audio/webm') is None
    assert voice.decode_pcm(b'x' * 400, 'audio/wav') is None


def test_no_ffmpeg_degrades_to_batch(monkeypatch):
    monkeypatch.setattr(voice.shutil, 'which', lambda name: None)
    monkeypatch.setattr(voice, '_client', lambda s, *, read_timeout: _BatchClient())
    out = voice.transcribe(_settings(), b'x' * 400, content_type='audio/webm')
    assert out['ok'] is True and out['transport'] == 'batch'
    assert out['text'] == 'batch heard this'


# -------------------------------------------------------------- streaming wire

def test_stream_waits_for_ready_and_accepts_summary_final(monkeypatch):
    socket = _FakeSocket([
        json.dumps({'type': 'status', 'stage': 'loading'}),
        json.dumps({'type': 'status', 'stage': 'ready'}),
        json.dumps({'type': 'partial', 'text': '这道'}),
        json.dumps({'type': 'final', 'final_kind': 'summary',
                    'text': '这道题的答案是什么'}),
    ])
    captured = {}

    def connect(url, timeout=5.0, extra_headers=None):
        captured['url'] = url
        return socket

    monkeypatch.setattr(voice.voice_ws, 'connect', connect)
    pcm = voice.decode_pcm(_wav(rate=16000, seconds=0.5), 'audio/wav')
    result = voice._stream_transcribe(_settings(), pcm)

    assert captured['url'].endswith('/v1/audio/transcriptions/stream?pcm=1&sr=16000')
    assert 'language=' not in captured['url']
    assert result['text'] == '这道题的答案是什么'
    assert result['partials'] == ['这道']
    assert len(socket.sent_bytes) > 20          # audio frames plus trailing silence
    assert b'\x00\x00' * 320 in socket.sent_bytes
    assert socket.closed is True


def test_stream_prefers_utterance_finals_and_joins_pauses(monkeypatch):
    socket = _FakeSocket([
        json.dumps({'type': 'status', 'stage': 'ready'}),
        json.dumps({'type': 'final', 'final_kind': 'utterance', 'text': '第一句'}),
        json.dumps({'type': 'final', 'final_kind': 'utterance', 'text': '第二句'}),
    ])
    monkeypatch.setattr(voice.voice_ws, 'connect', lambda *a, **k: socket)
    result = voice._stream_transcribe(_settings(), b'\x00\x00' * 320)
    assert result['text'] == '第一句 第二句'


def test_stream_error_frame_is_a_named_failure(monkeypatch):
    socket = _FakeSocket([
        json.dumps({'type': 'status', 'stage': 'ready'}),
        json.dumps({'type': 'error', 'message': 'model not loaded'}),
    ])
    monkeypatch.setattr(voice.voice_ws, 'connect', lambda *a, **k: socket)
    with pytest.raises(voice._StreamFailure) as caught:
        voice._stream_transcribe(_settings(), b'\x00\x00' * 320)
    assert caught.value.reason == 'voice-stream-error'
    assert 'model not loaded' in caught.value.detail


def test_stream_unreachable_falls_back_to_batch(monkeypatch):
    def refused(*_a, **_k):
        raise OSError('connection refused')

    monkeypatch.setattr(voice.voice_ws, 'connect', refused)
    monkeypatch.setattr(voice, '_client', lambda s, *, read_timeout: _BatchClient())
    out = voice.transcribe(_settings(), _wav(rate=16000, seconds=0.5),
                           content_type='audio/wav')
    assert out['ok'] is True and out['transport'] == 'batch'
    assert out['text'] == 'batch heard this'


def test_stream_success_reports_its_transport_and_latency(monkeypatch):
    monkeypatch.setattr(voice, '_stream_transcribe',
                        lambda s, pcm: {'text': 'stream heard this', 'stt_ms': 1432.0})
    out = voice.transcribe(_settings(), _wav(rate=16000, seconds=0.5),
                           content_type='audio/wav')
    assert out['ok'] is True and out['transport'] == 'stream'
    assert out['text'] == 'stream heard this'
    assert out['stt_ms'] == 1432.0 and out['latency_ms'] >= 0


def test_silence_is_not_retried_as_a_batch_job(monkeypatch):
    monkeypatch.setattr(voice, '_stream_transcribe',
                        lambda s, pcm: {'text': '', 'stt_ms': 900.0})

    def must_not_run(*_a, **_k):
        raise AssertionError('silence must not trigger the slow batch retry')

    monkeypatch.setattr(voice, '_client', must_not_run)
    out = voice.transcribe(_settings(), _wav(rate=16000, seconds=0.5),
                           content_type='audio/wav')
    assert out['ok'] is False and out['reason'] == 'no-speech'
    assert out['text'] == '' and out['transport'] == 'stream'
    assert out['next_action']


# ------------------------------------------------------------------- old guards

def test_original_refusals_still_hold():
    off = voice.transcribe(_settings(voice_enabled=False), b'audio')
    assert off['reason'] == 'voice-disabled' and off['text'] == ''
    assert voice.transcribe(_settings(), b'')['reason'] == 'empty-audio'
    huge = voice.transcribe(_settings(), b'x' * (voice.MAX_ASR_BYTES + 1))
    assert huge['reason'] == 'audio-too-large'
