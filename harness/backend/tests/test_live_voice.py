"""Live, turn-taking voice: provider decision, discovery, framing and one turn.

Every test runs against fakes. No test opens a socket, reads a key, waits for a
real synthesis, or touches the VoiceStudio backend on :3900 -- the same rule the
rest of the voice suite follows. The real loopback turn is measured once, out of
band, by ``scripts/live_turn_verify.py`` and its evidence JSON.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from app.harness import live_voice as lv


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeConnection:
    def __init__(self, incoming: list):
        self.incoming = list(incoming)
        self.sent_bytes: list[bytes] = []
        self.sent_json: list[dict] = []
        self.closed = False

    async def send_bytes(self, data: bytes) -> None:
        self.sent_bytes.append(bytes(data))

    async def send_json(self, obj: dict) -> None:
        self.sent_json.append(obj)

    async def recv(self):
        if not self.incoming:
            # The real transport signals "provider idle" with a recv timeout;
            # the fake does the same so the turn-end path is what gets tested.
            raise TimeoutError('scripted frames exhausted (provider idle)')
        return self.incoming.pop(0)

    async def aclose(self) -> None:
        self.closed = True


class FakeTransport:
    def __init__(self, stt_frames: list, tts_frames: list):
        self.stt = FakeConnection(stt_frames)
        self.tts_frames = list(tts_frames)
        self.stt_url = ''
        self.tts_url = ''
        self.tts_called = False
        self.tts_text = ''
        self.tts_num_step = None
        self._t = 0.0

    async def open_stt(self, url: str):
        self.stt_url = url
        self._t = 10.0
        return self.stt

    async def stream_tts(self, url: str, *, text: str, num_step: int):
        self.tts_url = url
        self.tts_called = True
        self.tts_text = text
        self.tts_num_step = num_step
        self._t += 0.5
        for frame in self.tts_frames:
            if isinstance(frame, (bytes, bytearray, memoryview)):
                yield frame

    def now(self) -> float:
        self._t += 0.01
        return self._t


class FailingTtsTransport(FakeTransport):
    """stream_tts raises LiveVoiceUnavailable to exercise the fail-closed path."""
    async def stream_tts(self, url: str, *, text: str, num_step: int):
        await asyncio.sleep(0)   # ensure an await point so async-for closes cleanly
        raise lv.LiveVoiceUnavailable('tts_error', 'engine load failed')


CAP_DOC = {
    'schema': 'voicestudio.speech-capabilities',
    'protocol': 'voicestudio.speech.v1',
    'protocol_version': '1.0',
    'service_version': '0.5.6',
    'endpoints': {
        'capabilities': {'path': '/.well-known/voicestudio-speech'},
        'streaming_transcription': {
            'path': '/v1/audio/transcriptions/stream', 'transport': 'websocket'},
    },
    'stream_input': {'formats': ['audio/pcm;encoding=s16le;channels=1']},
    'stream_output': {'events': ['session.started', 'status', 'partial', 'final', 'error']},
    'features': {'streaming_transcription': True, 'partial_transcripts': True,
                 'utterance_finals': True, 'acoustic_echo_cancellation': True},
}
OPENAPI = {'paths': {'/ws/tts': {'get': {}}, '/v1/audio/speech': {'post': {}}}}


def opener(cap=None, spec=None):
    cap = CAP_DOC if cap is None else cap
    spec = OPENAPI if spec is None else spec
    def _open(url: str):
        if 'openapi.json' in url:
            return spec
        return cap
    return _open


async def tutor(text: str) -> str:
    return f'好，我们来看：{text}'


def endpoints():
    return lv.discover_endpoints('http://127.0.0.1:3900', opener=opener())


# ---------------------------------------------------------------------------
# Provider decision table
# ---------------------------------------------------------------------------

def test_active_provider_is_local_and_has_provenance():
    d = lv.PROVIDERS[lv.ACTIVE_PROVIDER]
    assert d.available and d.state == 'ACTIVE'
    assert d.rule and d.reasons and d.sources          # every assertion traceable
    assert all('://' in s or s.startswith('harness/') for s in d.sources)


def test_retired_and_overkill_providers_are_not_available():
    assert lv.PROVIDERS['openai-realtime'].state == 'RETIRED'
    assert lv.PROVIDERS['openai-realtime'].available is False
    assert lv.PROVIDERS['livekit'].state == 'OVERKILL'
    assert lv.PROVIDERS['livekit'].available is False


def test_retired_decision_cites_the_shutdown():
    d = lv.PROVIDERS['openai-realtime']
    assert any('2026-05-07' in r for r in d.reasons)
    assert any('deprecations' in s for s in d.sources)


def test_validate_refuses_retired_and_overkill_providers():
    for name in ('openai-realtime', 'livekit'):
        cfg = lv.LiveTurnConfig(provider=name)
        with pytest.raises(lv.LiveVoiceUnavailable) as e:
            cfg.validate()
        assert e.value.code == 'provider_unavailable'


def test_validate_refuses_unknown_provider():
    with pytest.raises(lv.LiveVoiceUnavailable) as e:
        lv.LiveTurnConfig(provider='some-new-thing').validate()
    assert e.value.code == 'unknown_provider'


def test_validate_refuses_offhost_base_url():
    cfg = lv.LiveTurnConfig(base_url='https://voice.example.com')
    with pytest.raises(lv.LiveVoiceUnavailable) as e:
        cfg.validate()
    assert e.value.code == 'offhost_base_url'


def test_validate_refuses_bad_sample_rate():
    with pytest.raises(lv.LiveVoiceUnavailable) as e:
        lv.LiveTurnConfig(stt_sample_rate=999999).validate()
    assert e.value.code == 'bad_sample_rate'


def test_from_env_is_independent_of_settings(monkeypatch):
    monkeypatch.setenv('HARNESS_LIVE_PROVIDER', 'voicestudio-local')
    monkeypatch.setenv('HARNESS_LIVE_TTS_ENGINE', 'mlx-audio')
    monkeypatch.setenv('HARNESS_LIVE_AEC', '0')
    cfg = lv.LiveTurnConfig.from_env()
    assert cfg.tts_engine == 'mlx-audio' and cfg.aec is False
    cfg.validate()


def test_from_env_rejects_non_numeric(monkeypatch):
    monkeypatch.setenv('HARNESS_LIVE_STT_SAMPLE_RATE', 'not-a-number')
    with pytest.raises(lv.LiveVoiceUnavailable) as e:
        lv.LiveTurnConfig.from_env()
    assert e.value.code == 'bad_config'


# ---------------------------------------------------------------------------
# Discovery: endpoints are data, never hard-coded
# ---------------------------------------------------------------------------

def test_discovery_derives_both_streams_from_documents():
    ep = endpoints()
    assert ep.stt_stream_path == '/v1/audio/transcriptions/stream'
    assert ep.tts_stream_path == '/ws/tts'
    assert ep.protocol == 'voicestudio.speech.v1'
    assert ep.service_version == '0.5.6'
    assert ep.source_url.endswith('/.well-known/voicestudio-speech')
    assert ep.features['acoustic_echo_cancellation'] is True


def test_discovery_fails_closed_when_streaming_stt_missing():
    bad = dict(CAP_DOC, endpoints={'capabilities': {}})
    with pytest.raises(lv.LiveVoiceUnavailable) as e:
        lv.discover_endpoints('http://127.0.0.1:3900',
                              opener=opener(cap=bad))
    assert e.value.code == 'no_streaming_stt'


def test_discovery_fails_closed_when_streaming_tts_missing():
    with pytest.raises(lv.LiveVoiceUnavailable) as e:
        lv.discover_endpoints('http://127.0.0.1:3900',
                              opener=opener(spec={'paths': {}}))
    assert e.value.code == 'no_streaming_tts'


def test_discovery_fails_closed_on_unreachable_provider():
    def boom(url):
        raise OSError('connection refused')
    with pytest.raises(lv.LiveVoiceUnavailable) as e:
        lv.discover_endpoints('http://127.0.0.1:3900', opener=boom)
    assert e.value.code == 'discovery_failed'


def test_discovery_moved_stt_path_is_honoured():
    moved = json.loads(json.dumps(CAP_DOC))
    moved['endpoints']['streaming_transcription']['path'] = '/v2/live/asr'
    ep = lv.discover_endpoints('http://127.0.0.1:3900', opener=opener(cap=moved))
    assert ep.stt_stream_path == '/v2/live/asr'


def test_discovery_uses_handshake_probe_when_no_document_lists_ws():
    # VoiceStudio 0.5.6 reality: capability doc lists only STT, and FastAPI
    # keeps WebSocketRoute out of openapi.json paths. Only a live handshake can
    # confirm the TTS path -- and that confirmation is recorded as provenance.
    probed = []

    def probe(url):
        probed.append(url)
        return url.endswith('/ws/tts')

    ep = lv.discover_endpoints('http://127.0.0.1:3900',
                               opener=opener(spec={'paths': {}}),
                               tts_probe=probe)
    assert ep.tts_stream_path == '/ws/tts'
    assert ep.tts_discovery == 'handshake_verified'
    assert probed and all(u.startswith('ws://127.0.0.1') for u in probed)


def test_discovery_fails_closed_when_probe_finds_nothing():
    def probe(url):
        return False
    with pytest.raises(lv.LiveVoiceUnavailable) as e:
        lv.discover_endpoints('http://127.0.0.1:3900',
                              opener=opener(spec={'paths': {}}),
                              tts_probe=probe)
    assert e.value.code == 'no_streaming_tts'


def test_discovery_prefers_capability_document_over_a_probe():
    cap = json.loads(json.dumps(CAP_DOC))
    cap['endpoints']['streaming_synthesis'] = {'path': '/v3/tts/ws',
                                               'transport': 'websocket'}
    called = []

    def probe(url):
        called.append(url)
        return True

    ep = lv.discover_endpoints('http://127.0.0.1:3900',
                               opener=opener(cap=cap, spec={'paths': {}}),
                               tts_probe=probe)
    assert ep.tts_stream_path == '/v3/tts/ws'
    assert ep.tts_discovery == 'capability_document:streaming_synthesis'
    assert called == []                                # document wins, no probe


# ---------------------------------------------------------------------------
# Frame classification (pure)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('msg,expected_kind,expected_text', [
    (json.dumps({'type': 'partial', 'text': '你好'}), 'partial', '你好'),
    (json.dumps({'type': 'final', 'text': '顶点坐标', 'final_kind': 'utterance'}),
     'utterance', '顶点坐标'),
    (json.dumps({'type': 'final', 'text': '全句', 'final_kind': 'summary'}),
     'summary', '全句'),
    (json.dumps({'type': 'status', 'stage': 'ready'}), 'status', 'ready'),
    (json.dumps({'type': 'error', 'message': 'no model'}), 'error', 'no model'),
    (json.dumps({'type': 'done'}), 'meta', ''),
])
def test_classify_frame_kinds(msg, expected_kind, expected_text):
    ev = lv.classify_frame(msg)
    assert ev and ev.kind == expected_kind and ev.text == expected_text


def test_classify_binary_frame_is_audio_not_a_turn_boundary():
    ev = lv.classify_frame(b'\x01\x02\x03\x04')
    assert ev and ev.kind == 'audio' and ev.raw['_bytes'] == 4


def test_classify_garbage_returns_none():
    assert lv.classify_frame('not json') is None
    assert lv.classify_frame(12345) is None
    assert lv.classify_frame(json.dumps({'type': 'heartbeat'})) is None


# ---------------------------------------------------------------------------
# One full turn, driven by fakes
# ---------------------------------------------------------------------------

def stt_frames():
    return [
        json.dumps({'type': 'session.started'}),
        json.dumps({'type': 'status', 'stage': 'ready'}),
        json.dumps({'type': 'partial', 'text': '你'}),
        json.dumps({'type': 'partial', 'text': '你好'}),
        json.dumps({'type': 'final', 'text': '你好，讲讲二次函数。',
                    'final_kind': 'utterance'}),
    ]


def tts_frames():
    return [
        json.dumps({'type': 'start', 'sample_rate': 24000}),
        b'\x00\x01' * 100,
        b'\x00\x01' * 100,
        json.dumps({'type': 'done', 'ttfa_ms': 4800.0}),
    ]


def test_one_turn_streams_partials_then_reply_audio():
    tr = FakeTransport(stt_frames(), tts_frames())
    cfg = lv.LiveTurnConfig()
    session = lv.LiveTurnSession(cfg, endpoints(), tr, tutor)
    result = asyncio.run(session.run_turn([b'\x00\x00' * 320] * 3))
    assert result.transcript == '你好，讲讲二次函数。'
    assert result.partials == ['你', '你好']
    assert result.reply.startswith('好，我们来看：')
    assert result.audio_chunks == 2
    assert result.barge_in is True
    assert result.stt_ms > 0 and result.tts_first_audio_ms is not None
    assert result.latency_note == lv.LATENCY_NOTE      # no hidden downgrade
    assert tr.stt.closed and tr.tts_called is True


def test_multiple_vad_utterances_in_one_turn_are_all_collected():
    # Regression for a measured live failure: a natural pause mid-sentence made
    # the recogniser commit "你好。" then keep talking. Breaking on the first
    # endpoint truncated the learner's question. One turn = all utterances up to
    # the provider going idle, not the first one.
    frames = [
        json.dumps({'type': 'session.started'}),
        json.dumps({'type': 'partial', 'text': '你好'}),
        json.dumps({'type': 'final', 'text': '你好。', 'final_kind': 'utterance'}),
        json.dumps({'type': 'partial', 'text': '请讲讲'}),
        json.dumps({'type': 'partial', 'text': '请讲讲二次函数'}),
        json.dumps({'type': 'final', 'text': '请讲讲二次函数的顶点坐标。',
                    'final_kind': 'utterance'}),
    ]
    tr = FakeTransport(frames, tts_frames())
    session = lv.LiveTurnSession(lv.LiveTurnConfig(), endpoints(), tr, tutor)
    result = asyncio.run(session.run_turn([b'\x00\x00']))
    assert result.utterances == ['你好。', '请讲讲二次函数的顶点坐标。']
    assert '顶点坐标' in result.transcript
    assert result.partials == ['你好', '请讲讲', '请讲讲二次函数']
    assert result.reply.startswith('好，我们来看：')
    assert result.audio_chunks == 2


def test_no_utterance_before_idle_fails_closed():
    tr = FakeTransport([json.dumps({'type': 'status', 'stage': 'ready'})],
                       tts_frames())
    session = lv.LiveTurnSession(lv.LiveTurnConfig(), endpoints(), tr, tutor)
    with pytest.raises(lv.LiveVoiceUnavailable) as e:
        asyncio.run(session.run_turn([b'\x00\x00']))
    assert e.value.code == 'no_utterance'
    assert tr.tts_called is False


def test_aec_mode_prefixes_every_mic_frame():
    tr = FakeTransport(stt_frames(), tts_frames())
    session = lv.LiveTurnSession(lv.LiveTurnConfig(aec=True), endpoints(), tr, tutor)
    asyncio.run(session.run_turn([b'\x11\x22' * 4]))
    assert 'aec=1' in tr.stt_url
    for frame in tr.stt.sent_bytes:
        assert frame[0] == 0x00                        # near/mic prefix
    assert any(f[1:] == b'\x11\x22' * 4 for f in tr.stt.sent_bytes)


def test_plain_mode_sends_unprefixed_pcm():
    tr = FakeTransport(stt_frames(), tts_frames())
    session = lv.LiveTurnSession(lv.LiveTurnConfig(aec=False), endpoints(), tr, tutor)
    asyncio.run(session.run_turn([b'\x11\x22' * 4]))
    assert 'aec=1' not in tr.stt_url
    assert b'\x11\x22' * 4 in tr.stt.sent_bytes         # not eaten by demux


def test_endpoint_silence_is_long_enough_to_fire_the_vad_in_both_modes():
    # 0.6 s trailing silence at 20 ms/frame => >= 30 quiet frames, in AEC and
    # plain mode alike. A 3-frame (60 ms) tail would never commit an utterance.
    for aec in (True, False):
        tr = FakeTransport(stt_frames(), tts_frames())
        cfg = lv.LiveTurnConfig(aec=aec, endpoint_silence_s=0.6)
        session = lv.LiveTurnSession(cfg, endpoints(), tr, tutor)
        asyncio.run(session.run_turn([b'\x11\x22' * 4]))
        quiet = [f for f in tr.stt.sent_bytes
                 if f == b'\x00' * 640 or f == b'\x00' + b'\x00' * 640]
        assert len(quiet) >= 30, (aec, len(quiet))


def test_empty_utterance_fails_closed_no_fabricated_reply():
    frames = [json.dumps({'type': 'final', 'text': '   ',
                          'final_kind': 'utterance'})]
    tr = FakeTransport(frames, tts_frames())
    session = lv.LiveTurnSession(lv.LiveTurnConfig(), endpoints(), tr, tutor)
    with pytest.raises(lv.LiveVoiceUnavailable) as e:
        asyncio.run(session.run_turn([b'\x00\x00']))
    assert e.value.code == 'empty_transcript'
    assert tr.tts_called is False                     # tutor never called


def test_stt_error_frame_fails_closed_and_never_speaks():
    frames = [json.dumps({'type': 'error', 'message': 'asr_model_missing'})]
    tr = FakeTransport(frames, tts_frames())
    session = lv.LiveTurnSession(lv.LiveTurnConfig(), endpoints(), tr, tutor)
    with pytest.raises(lv.LiveVoiceUnavailable) as e:
        asyncio.run(session.run_turn([b'\x00\x00']))
    assert e.value.code == 'stt_error'
    assert tr.tts_called is False


def test_empty_tutor_reply_fails_closed_no_audio():
    async def blank(text):
        return '   '
    tr = FakeTransport(stt_frames(), tts_frames())
    session = lv.LiveTurnSession(lv.LiveTurnConfig(), endpoints(), tr, blank)
    with pytest.raises(lv.LiveVoiceUnavailable) as e:
        asyncio.run(session.run_turn([b'\x00\x00']))
    assert e.value.code == 'empty_reply'
    assert tr.tts_called is False


def test_tts_error_fails_closed():
    tr = FailingTtsTransport(stt_frames(), tts_frames())
    session = lv.LiveTurnSession(lv.LiveTurnConfig(), endpoints(), tr, tutor)
    with pytest.raises(lv.LiveVoiceUnavailable) as e:
        asyncio.run(session.run_turn([b'\x00\x00']))
    assert e.value.code == 'tts_error'


def test_reply_is_capped_without_truncating_the_transcript():
    async def long_tutor(text):
        return '很长的讲解' * 200
    tr = FakeTransport(stt_frames(), tts_frames())
    cfg = lv.LiveTurnConfig(max_reply_chars=40)
    session = lv.LiveTurnSession(cfg, endpoints(), tr, long_tutor)
    result = asyncio.run(session.run_turn([b'\x00\x00']))
    assert len(result.reply) == 40


def test_barge_in_is_false_without_aec_or_partials():
    cap = json.loads(json.dumps(CAP_DOC))
    cap['features']['acoustic_echo_cancellation'] = False
    ep = lv.discover_endpoints('http://127.0.0.1:3900', opener=opener(cap=cap))
    tr = FakeTransport(stt_frames(), tts_frames())
    session = lv.LiveTurnSession(lv.LiveTurnConfig(), ep, tr, tutor)
    result = asyncio.run(session.run_turn([b'\x00\x00']))
    assert result.barge_in is False


def test_asr_model_override_is_passed_as_query():
    tr = FakeTransport(stt_frames(), tts_frames())
    cfg = lv.LiveTurnConfig(asr_model='sherpa-zipformer-zh-14m')
    session = lv.LiveTurnSession(cfg, endpoints(), tr, tutor)
    asyncio.run(session.run_turn([b'\x00\x00']))
    assert 'model=sherpa-zipformer-zh-14m' in tr.stt_url


def test_discovery_prefers_http_streaming_tts_path():
    ep = endpoints()
    # The legacy /ws/tts WS route may still be discovered, but the HTTP
    # streaming endpoint is what the session uses for sub-second first audio.
    assert ep.tts_http_path == '/v1/audio/speech'
    assert ep.tts_discovery in ('openapi_paths', 'handshake_verified')


def test_tts_num_step_is_passed_to_streaming_transport():
    tr = FakeTransport(stt_frames(), tts_frames())
    cfg = lv.LiveTurnConfig(tts_num_step=2)
    session = lv.LiveTurnSession(cfg, endpoints(), tr, tutor)
    asyncio.run(session.run_turn([b'\x00\x00']))
    assert tr.tts_called is True
    assert tr.tts_num_step == 2
    assert tr.tts_url.endswith('/v1/audio/speech')


def test_bad_tts_num_step_fails_validation():
    with pytest.raises(lv.LiveVoiceUnavailable) as e:
        lv.LiveTurnConfig(tts_num_step=0).validate()
    assert e.value.code == 'bad_tts_num_step'
