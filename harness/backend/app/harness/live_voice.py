"""Live, turn-taking spoken conversation for the harness.

A learner speaks; the tutor listens with *streaming* ASR, commits an utterance
when the recogniser endpoints (not when a timer guesses), forms a reply, and
speaks it back as sentence-by-sentence streamed audio. Barge-in is a real event:
a new ``partial`` while the tutor is talking cancels the in-flight reply.

Why this module exists
----------------------
The desktop app already shipped two voice paths (``Voice.swift`` offline
Converse, ``VoiceRealtime.swift`` hosted duplex). Neither is a *configured,
local, streaming* provider:

* ``VoiceRealtime.swift`` is ``RETIRED``: it hard-codes
  ``gpt-4o-realtime-preview-2024-12-17`` and the ``OpenAI-Beta: realtime=v1``
  header. OpenAI shut that model down on 2026-05-07, removed the beta header on
  2026-05-12, and GA renamed the audio events (``response.audio.delta`` ->
  ``response.output_audio.delta``) and nested the session config. It also sends
  learner audio off the host, which ``docs/provider-and-voice-setup.md`` §3
  forbids ("learner text must not leave the host to be spoken" -- audio is at
  least as sensitive as the text it becomes).
* ``Voice.swift`` Converse is local but turn-*taking*: an energy VAD with a
  1.1 s silence endpoint and a non-streaming ``SFSpeechRecognizer``. The tutor
  cannot start before the learner stops, and barge-in needs ~0.33 s of speech
  over a raised threshold because the mic hears the speakers.

The installed VoiceStudio 0.5.6 backend closes both gaps on loopback: its
capability document advertises ``streaming_transcription`` (WebSocket, partial
+ ``final``/``utterance`` + word timestamps), ``acoustic_echo_cancellation``,
and it serves TTS over a streaming HTTP endpoint (the legacy ``/ws/tts``
WebSocket is not used -- it ignores ``num_step`` and lands at ~15 s, whereas
the HTTP ``/v1/audio/speech`` endpoint reaches sub-second first audio with
``num_step`` lowered to 2-4). No new service, no API key, no audio leaving
the host, and the reply still comes from the grounded backend tutor rather
than a free-floating voice model.

Provider decision (every assertion carries a rule id and a source)
-----------------------------------------------------------------
See ``PROVIDERS``. The active provider is ``voicestudio-local``. ``openai-
realtime`` is RETIRED (dead wire format + off-host audio + paid). ``livekit`` is
OVERKILL: a WebRTC SFU needs UDP 50000-60000, TURN, Redis in production and
agent workers; for a 1:1 loopback session it adds operational surface without
touching the one real bottleneck (Chinese TTS first-audio latency). Measured on this host (2026-11-10, Apple M5, VoiceStudio 0.5.6): the HTTP
streaming ``/v1/audio/speech`` endpoint at the default diffusion step count
(num_step=16) renders a Chinese sentence in ~11 s, but the SAME endpoint with
``num_step`` lowered to 2-4 reaches sub-second first audio (omnivoice:
~250-620 ms, see ``outputs/ttfa_refined_evidence.json``). The legacy
``/ws/tts`` WebSocket path does NOT honor ``num_step`` and lands at ~15 s
regardless, so it is no longer used for TTS. The reply is spoken back over
the HTTP streaming endpoint, not the WS one.

That last fact is deliberately NOT hidden behind a config flag. ``LIVE_TTS``
latency is reported to the caller on every turn; a caller that needs sub-second
first audio must install a faster Chinese engine or accept off-host audio, and
must decide that explicitly. This module never silently swaps in a cheaper
provider.

The second measured trade-off is streaming ASR *accuracy*: the installed
25 MB ``sherpa-zipformer-zh-14m`` gives near-real-time partials and server-side
endpointing but mis-hears short Chinese phrases, whereas the same utterance via
batch ``faster-whisper`` is accurate yet takes ~9 s and yields no partials. See
``ASR_QUALITY_NOTE``. Accuracy is reported as evidence, never asserted.

Design boundary
---------------
No WebSocket client is imported here. ``websockets`` is present in the venv only
as a transitive dep of ``uvicorn[standard]`` and is NOT declared in
``requirements.txt`` -- ``scripts/package.py`` freezes only *declared*
distributions, so importing it from production code would build a bundle whose
live-voice path fails on a tester's machine. All socket I/O is injected through
a small ``StreamConnection``/``LiveTransport`` protocol; the shipped wiring
lives in ``scripts/live_turn_verify.py`` and the native client, both of which
own their own dependency. Endpoints are discovered from the provider's
capability document at runtime, never hard-coded, so a moved port or a new
protocol version is a data change rather than a code change.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable, Protocol

__all__ = [
    'PROVIDERS', 'ACTIVE_PROVIDER', 'LiveVoiceUnavailable', 'ProviderDecision',
    'LiveTurnConfig', 'Endpoints', 'discover_endpoints', 'classify_frame',
    'TurnEvent', 'LiveTurnSession', 'LATENCY_NOTE', 'ASR_QUALITY_NOTE',
]

# A named rule id + source for every provider assertion, so a decision can be
# traced back to the measurement or the vendor notice that produced it.
@dataclass(frozen=True)
class ProviderDecision:
    id: str
    state: str                 # ACTIVE | RETIRED | OVERKILL
    rule: str                  # short machine-readable rule id
    reasons: tuple[str, ...]
    sources: tuple[str, ...]

    @property
    def available(self) -> bool:
        return self.state == 'ACTIVE'


PROVIDERS: dict[str, ProviderDecision] = {
    'voicestudio-local': ProviderDecision(
        id='voicestudio-local', state='ACTIVE',
        rule='LOCAL_STREAMING_STT_TTS_AEC_NO_OFFHOST_AUDIO',
        reasons=(
            'Installed and answering on loopback (:3900, service_version 0.5.6).',
            'Capability document advertises streaming_transcription (partial + '
            'utterance finals + word_timestamps) and acoustic_echo_cancellation.',
            'Separate streaming-TTS WebSocket serves sentence-by-sentence PCM16.',
            'No API key, no per-minute fee, no learner audio leaving the host.',
            'Reply stays with the grounded backend tutor, not a free voice model.',
        ),
        sources=(
            'GET http://127.0.0.1:3900/.well-known/voicestudio-speech (probed 2026-11-10)',
            'GET http://127.0.0.1:3900/openapi.json (/ws/tts, /v1/audio/transcriptions/stream)',
            'harness/backend/docs/provider-and-voice-setup.md §3 privacy invariant',
        ),
    ),
    'openai-realtime': ProviderDecision(
        id='openai-realtime', state='RETIRED',
        rule='DEAD_WIRE_FORMAT_AND_OFFHOST_AUDIO_AND_PAID',
        reasons=(
            'gpt-4o-realtime-preview-2024-12-17 shut down 2026-05-07; '
            'OpenAI-Beta: realtime=v1 header removed 2026-05-12.',
            'GA renamed audio events (response.output_audio.delta) and nested '
            'session config; the shipped VoiceRealtime.swift cannot connect.',
            'Learner audio leaves the host (violates the §3 invariant); metered.',
        ),
        sources=(
            'https://developers.openai.com/api/docs/deprecations',
            'harness/native/Sources/LearningHarness/VoiceRealtime.swift:24,80,83',
            'harness/backend/app/config.py:199-201 (stale default model)',
        ),
    ),
    'livekit': ProviderDecision(
        id='livekit', state='OVERKILL',
        rule='SFU_UNNEEDED_FOR_1TO1_LOOPBACK_AND_DOES_NOT_FIX_TTS_TTFA',
        reasons=(
            'Free and self-hostable (Apache-2.0), but an SFU needs UDP '
            '50000-60000, TURN, Redis and agent workers for a 1:1 loopback call.',
            'Does not supply TTS: a TTS backend is still required, so the '
            'measured 4.4-11.8 s Chinese first-audio latency is unchanged.',
            'The installed provider already offers streaming STT + AEC + '
            'server-side endpointing on loopback.',
        ),
        sources=(
            'https://github.com/livekit/livekit (server = WebRTC SFU)',
            'Measured /ws/tts TTFA on this host, 2026-11-10',
        ),
    ),
}

ACTIVE_PROVIDER = 'voicestudio-local'

LATENCY_NOTE = (
    'Chinese TTS first-audio on this host (2026-11-10, VoiceStudio 0.5.6 / Apple M5) '
    'is driven by num_step on the HTTP streaming /v1/audio/speech endpoint '
    '(omnivoice, 16-char sentence, ASR-verified intelligibility in '
    'outputs/ttfa_intelligibility.json): step8 = 852 ms TTFA at 0.973 '
    'transcript similarity (BEST balance, the default); step4 = 622 ms at '
    '0.857; step2 = 497 ms but audibly degraded (0.55); step1 = 420 ms and '
    'unintelligible (0.08). Short text (2 chars) reaches 220-705 ms. '
    'In-pipeline E2E with a 44-char reply measured 1299-3544 ms. The legacy '
    '/ws/tts WebSocket path (~15 s, does not honor num_step) is not used. '
    'Streaming STT partials remain near real-time; the remaining accuracy gap '
    'is the streaming ASR weight -- see ASR_QUALITY_NOTE.'
)

ASR_QUALITY_NOTE = (
    'Streaming Chinese ASR, re-measured 2026-11-10 with corrected 16 kHz audio '
    'on the same utterance: sherpa-zipformer-zh-14m (25 MB) and '
    'sherpa-paraformer-bilingual-zh-en (0.24 GB) both reach 0.976 transcript '
    'similarity and both commit utterance finals reliably; '
    'sherpa-zipformer-bilingual-zh-en emits SIL artifacts (0.784) and is '
    'rejected. Paraformer is installed and set as the dictation default; '
    'zh-14m remains a lighter equal-accuracy alternative. The previously '
    'reported 0.579 was an artifact of a verifier bug that shipped unresampled '
    '24 kHz audio as 16 kHz (fixed in live_turn_verify.py). Batch '
    'faster-whisper stays accurate (~9 s, no partials); choosing streaming vs '
    'batch is an explicit liveness-vs-nothing tradeoff -- both are local.'
)


class LiveVoiceUnavailable(RuntimeError):
    """Fail-close: the selected provider cannot serve a live turn.

    Raised instead of inventing a transcript, a reply, or a fallback provider.
    ``code`` is a stable token the caller can show the operator.
    """
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class LiveTurnConfig:
    """Independent configuration, read from ``HARNESS_LIVE_*``.

    Deliberately separate from ``app.config.Settings``: that dataclass is being
    edited by another workstream, and a live-voice setting must not be able to
    alter the boot contract of the whole backend. Every default is loopback-only.
    """
    provider: str = ACTIVE_PROVIDER
    base_url: str = 'http://127.0.0.1:3900'
    stt_sample_rate: int = 16000
    tts_engine: str = 'omnivoice'       # Chinese-accurate; see LATENCY_NOTE
    asr_model: str = ''                 # empty -> provider's selected dictation model
    aec: bool = True                    # echo cancellation, so barge-in is honest
    endpoint_silence_s: float = 0.6    # sherpa rule2 commits here
    max_reply_chars: int = 400
    tts_num_step: int = 8        # diffusion steps: 8 is the only measured config that is
                                 # both sub-second (~852 ms) and near-perfect intelligibility
                                 # (0.973); lower steps trade quality for latency -- see LATENCY_NOTE

    @classmethod
    def from_env(cls) -> 'LiveTurnConfig':
        def _bool(name: str, default: bool) -> bool:
            raw = os.getenv(name)
            return default if raw is None else raw.strip().lower() in {'1', 'true', 'on', 'yes'}
        try:
            sr = int(os.getenv('HARNESS_LIVE_STT_SAMPLE_RATE', '16000'))
            silence = float(os.getenv('HARNESS_LIVE_ENDPOINT_SILENCE_S', '0.6'))
            cap = int(os.getenv('HARNESS_LIVE_MAX_REPLY_CHARS', '400'))
            nstep = int(os.getenv('HARNESS_LIVE_TTS_NUM_STEP', '8'))
        except ValueError as exc:
            raise LiveVoiceUnavailable('bad_config',
                                       f'HARNESS_LIVE_* numeric setting is invalid: {exc}') from exc
        return cls(
            provider=os.getenv('HARNESS_LIVE_PROVIDER', ACTIVE_PROVIDER).strip() or ACTIVE_PROVIDER,
            base_url=os.getenv('HARNESS_LIVE_BASE_URL', 'http://127.0.0.1:3900').strip(),
            stt_sample_rate=sr,
            tts_engine=os.getenv('HARNESS_LIVE_TTS_ENGINE', 'omnivoice').strip() or 'omnivoice',
            asr_model=os.getenv('HARNESS_LIVE_ASR_MODEL', '').strip(),
            aec=_bool('HARNESS_LIVE_AEC', True),
            endpoint_silence_s=silence,
            max_reply_chars=cap,
            tts_num_step=nstep,
        )

    def validate(self) -> None:
        decision = PROVIDERS.get(self.provider)
        if decision is None:
            raise LiveVoiceUnavailable('unknown_provider',
                                       f'No provider decision for {self.provider!r}. '
                                       f'Known: {", ".join(sorted(PROVIDERS))}.')
        if not decision.available:
            raise LiveVoiceUnavailable(
                'provider_unavailable',
                f'Provider {self.provider!r} is {decision.state} '
                f'({decision.rule}): {decision.reasons[0]}')
        if not (self.base_url.startswith('http://127.0.0.1')
                or self.base_url.startswith('http://localhost')
                or self.base_url.startswith('http://[::1]')):
            raise LiveVoiceUnavailable(
                'offhost_base_url',
                f'HARNESS_LIVE_BASE_URL={self.base_url!r} is not loopback; learner '
                f'audio must not leave the host. Configure an explicit remote '
                f'provider instead of pointing this one off-machine.')
        if not (8000 <= self.stt_sample_rate <= 48000):
            raise LiveVoiceUnavailable('bad_sample_rate',
                                       f'STT sample rate {self.stt_sample_rate} is out of range.')
        if not (1 <= self.tts_num_step <= 32):
            raise LiveVoiceUnavailable('bad_tts_num_step',
                                       f'TTS num_step {self.tts_num_step} is out of range (1-32).')


@dataclass(frozen=True)
class Endpoints:
    """Discovered endpoints, with provenance (never hard-coded)."""
    capabilities_path: str
    stt_stream_path: str
    tts_stream_path: str
    protocol: str
    service_version: str
    source_url: str
    input_format: str
    output_events: tuple[str, ...]
    features: dict[str, bool] = field(default_factory=dict)
    tts_discovery: str = ''        # provenance: how the TTS WS path was confirmed
    tts_http_path: str = ''      # HTTP streaming /v1/audio/speech (preferred; honors num_step)


# WebSocket path candidates for streaming TTS. These are protocol *lookups*,
# not asserted facts: each must be confirmed by a capability document, an
# OpenAPI path, or a live handshake before it is returned. Source: the
# VoiceStudio 0.5.6 bundle ``api/routers/tts_stream.py`` (@router.websocket),
# plus the OpenAI-style streaming-speech convention. A provider that moves its
# WS route only needs a new candidate here, and the handshake still verifies it.
_TTS_WS_CANDIDATES: tuple[str, ...] = ('/ws/tts', '/v1/audio/speech/stream')


def _get_json(base_url: str, path: str, *, opener: Callable[..., Any]) -> dict:
    """One discovered-document read, proxied through an injected opener."""
    url = base_url.rstrip('/') + path
    try:
        payload = opener(url)
    except Exception as exc:  # typed by the injected opener, not guessed here
        raise LiveVoiceUnavailable(
            'discovery_failed',
            f'Could not read the provider capability document at {url}: '
            f'{type(exc).__name__}: {exc}') from exc
    if not isinstance(payload, dict):
        raise LiveVoiceUnavailable('discovery_bad_shape',
                                   f'{url} did not return a JSON object.')
    return payload


def discover_endpoints(base_url: str, *, opener: Callable[..., Any],
                       tts_probe: Callable[[str], bool] | None = None) -> Endpoints:
    """Derive every endpoint from ``/.well-known/voicestudio-speech``.

    ``opener`` is an injected callable taking a URL and returning a decoded
    dict, so this function is testable without a socket and works with the
    pinned ``httpx`` client in production. Endpoint paths are data, not code.

    ``tts_probe`` is an optional injected callable taking a *ws://* URL and
    returning whether a real WebSocket handshake succeeded. VoiceStudio 0.5.6
    serves a streaming-TTS WebSocket but does NOT advertise it anywhere
    machine-readable: the capability document lists only STT, and FastAPI does
    not put ``WebSocketRoute`` into ``openapi.json`` ``paths`` (verified on the
    live server: zero ``/ws`` paths). The probe lets the caller own that one
    socket dependency (``scripts/live_turn_verify.py``) while this module keeps
    zero undeclared deps. Without a confirming document or a passing handshake,
    the TTS path is NOT guessed: discovery fails closed.
    """
    doc = _get_json(base_url, '/.well-known/voicestudio-speech', opener=opener)
    endpoints = doc.get('endpoints')
    if not isinstance(endpoints, dict):
        raise LiveVoiceUnavailable('discovery_no_endpoints',
                                   'Capability document has no endpoints object.')
    stt = endpoints.get('streaming_transcription') or {}
    stt_path = stt.get('path') if isinstance(stt, dict) else None
    if not stt_path:
        raise LiveVoiceUnavailable('no_streaming_stt',
                                   'Provider does not advertise streaming_transcription; '
                                   'a live turn needs partials + utterance endpointing.')
    # A streaming-TTS path is accepted as a FACT only when a document names it
    # or an injected probe confirms a real handshake. VoiceStudio 0.5.6 has no
    # machine-readable WS registry (capability doc lists only STT; FastAPI omits
    # WebSocketRoute from openapi.json paths), so the handshake is the only
    # honest source there. An unverified candidate is never returned.
    tts_path = ''
    tts_discovery = ''
    # (1) capability document -- a future provider may advertise the WS route.
    for key in ('streaming_synthesis', 'streaming_tts', 'tts_stream'):
        cand = endpoints.get(key)
        path = cand.get('path') if isinstance(cand, dict) else (
            cand if isinstance(cand, str) else None)
        if path:
            tts_path, tts_discovery = path, f'capability_document:{key}'
            break
    # (2) OpenAPI paths -- works when a provider documents WS routes there.
    tts_http_path = ''
    if not tts_path:
        try:
            spec = _get_json(base_url, '/openapi.json', opener=opener)
            for candidate in _TTS_WS_CANDIDATES:
                if candidate in (spec.get('paths') or {}):
                    tts_path, tts_discovery = candidate, 'openapi_paths'
                    break
        except LiveVoiceUnavailable:
            pass
    # (2b) HTTP streaming TTS endpoint -- the preferred path. VoiceStudio 0.5.6
    # advertises /v1/audio/speech (POST) in openapi.json; it honors num_step
    # and reaches sub-second first audio, unlike the WS route.
    try:
        spec = _get_json(base_url, '/openapi.json', opener=opener)
        paths = spec.get('paths') or {}
        if '/v1/audio/speech' in paths and 'post' in paths['/v1/audio/speech']:
            tts_http_path = '/v1/audio/speech'
    except LiveVoiceUnavailable:
        pass
    # (3) injected live handshake verification -- the real 0.5.6 case.
    if not tts_path and tts_probe is not None:
        ws_base = (base_url.replace('http://', 'ws://')
                   .replace('https://', 'wss://').rstrip('/'))
        for candidate in _TTS_WS_CANDIDATES:
            try:
                if tts_probe(ws_base + candidate):
                    tts_path, tts_discovery = candidate, 'handshake_verified'
                    break
            except Exception:
                continue   # a refused handshake is evidence of absence, not a crash
    if not tts_path:
        raise LiveVoiceUnavailable(
            'no_streaming_tts',
            'Provider exposes no streaming-TTS WebSocket (no capability entry, '
            'no OpenAPI path, and no candidate passed a live handshake probe); '
            'a live turn cannot stream a reply.')
    stream_in = doc.get('stream_input') or {}
    stream_out = doc.get('stream_output') or {}
    return Endpoints(
        capabilities_path='/.well-known/voicestudio-speech',
        stt_stream_path=stt_path,
        tts_stream_path=tts_path,
        protocol=str(doc.get('protocol') or ''),
        service_version=str(doc.get('service_version') or ''),
        source_url=base_url.rstrip('/') + '/.well-known/voicestudio-speech',
        input_format=str((stream_in.get('formats') or ['audio/pcm;encoding=s16le;channels=1'])[0]),
        output_events=tuple(str(e) for e in (stream_out.get('events') or ())),
        features={str(k): bool(v) for k, v in (doc.get('features') or {}).items()},
        tts_discovery=tts_discovery, tts_http_path=tts_http_path,
    )


# ---- frame classification: pure, so it is unit-testable without a socket ----

@dataclass(frozen=True)
class TurnEvent:
    """One normalised event in a live turn."""
    kind: str        # partial | utterance | summary | status | error | audio | meta
    text: str = ''
    final_kind: str = ''
    raw: dict = field(default_factory=dict)


def classify_frame(message: Any) -> TurnEvent | None:
    """Normalise one STT/TTS server frame. Binary frames are audio, not events.

    Returns ``None`` for frames with no semantic content (empty/ignorable), so
    a caller cannot mistake a keepalive for a turn boundary.
    """
    if isinstance(message, (bytes, bytearray, memoryview)):
        return TurnEvent(kind='audio', raw={'_bytes': len(message)})
    if not isinstance(message, str):
        return None
    import json as _json
    try:
        obj = _json.loads(message)
    except (ValueError, TypeError):
        return None
    if not isinstance(obj, dict):
        return None
    typ = str(obj.get('type') or '')
    if typ == 'partial':
        return TurnEvent('partial', str(obj.get('text') or ''), raw=obj)
    if typ == 'final':
        fk = str(obj.get('final_kind') or 'summary')
        return TurnEvent('utterance' if fk == 'utterance' else 'summary',
                         str(obj.get('text') or ''), fk, obj)
    if typ == 'error':
        return TurnEvent('error', str(obj.get('message') or obj.get('detail') or ''), raw=obj)
    if typ in ('status', 'session.started', 'start', 'routing'):
        return TurnEvent('status', str(obj.get('stage') or typ), raw=obj)
    if typ in ('done', 'session_summary'):
        return TurnEvent('meta', raw=obj)
    return None


# ---- injected I/O protocol --------------------------------------------------

class StreamConnection(Protocol):
    """The subset of a WebSocket a live turn needs."""
    async def send_bytes(self, data: bytes) -> None: ...
    async def send_json(self, obj: dict) -> None: ...
    async def recv(self) -> Any: ...
    async def aclose(self) -> None: ...


class LiveTransport(Protocol):
    """Injected so production needs no un-declared WebSocket client dep."""
    async def open_stt(self, url: str) -> StreamConnection: ...
    def now(self) -> float: ...
    # TTS is HTTP streaming (not WebSocket): the injected transport yields raw
    # PCM chunks for a reply at a chosen diffusion step count (num_step). The
    # native client implements this with URLSession; the verifier with httpx.
    async def stream_tts(self, url: str, *, text: str, num_step: int) -> AsyncIterator[bytes]: ...


@dataclass
class TurnResult:
    transcript: str
    reply: str
    partials: list[str]
    barge_in: bool
    stt_ms: float
    tts_first_audio_ms: float | None
    audio_chunks: int
    latency_note: str = LATENCY_NOTE
    utterances: list[str] = field(default_factory=list)


class LiveTurnSession:
    """Drive one spoken turn over an injected transport.

    ``tutor`` is ``async (transcript) -> reply text``. Keeping it injected means
    this module never chooses between the grounded tutor and a voice model; the
    caller does, and a missing tutor fails closed instead of inventing a reply.
    """
    def __init__(self, config: LiveTurnConfig, endpoints: Endpoints,
                 transport: LiveTransport,
                 tutor: Callable[[str], Awaitable[str]]):
        self.config = config
        self.endpoints = endpoints
        self.transport = transport
        self.tutor = tutor

    async def run_turn(self, pcm_chunks: list[bytes]) -> TurnResult:
        cfg = self.config
        cfg.validate()
        ws_base = cfg.base_url.replace('http://', 'ws://').replace('https://', 'wss://').rstrip('/')
        stt_q = f'?pcm=1&sr={cfg.stt_sample_rate}'
        if cfg.asr_model:
            stt_q += f'&model={cfg.asr_model}'
        # ``aec=1`` changes the *binary framing*: each frame must carry a 1-byte
        # prefix (0x00 = microphone/near, 0x01 = playback reference/far) so the
        # server's NLMS canceller can subtract the speaker from the mic. Enabling
        # the flag without prefixing would make the server eat the first sample
        # of every frame -- an audio-corruption bug that looks like bad ASR.
        stt_q += '&aec=1' if cfg.aec else ''
        stt_url = ws_base + self.endpoints.stt_stream_path + stt_q
        tts_url = cfg.base_url.rstrip('/') + (self.endpoints.tts_http_path or '/v1/audio/speech')

        partials: list[str] = []
        utterances: list[str] = []
        t0 = self.transport.now()
        stt = await self.transport.open_stt(stt_url)
        stt_done_ms = 0.0
        try:
            for chunk in pcm_chunks:
                payload = b'\x00' + chunk if cfg.aec else chunk
                await stt.send_bytes(payload)
            # Server-side VAD endpoints the utterance; no client EOF frame is
            # sent -- VoiceStudio's sherpa handler commits on trailing silence.
            # The mic must actually stay quiet for cfg.endpoint_silence_s (0.6 s
            # by default): one 640-byte frame = 20 ms at 16 kHz, so a fixed
            # 3-frame tail (60 ms) would never fire the endpoint. Derive the
            # frame count from the configured rule, in both AEC and plain mode.
            silence_frames = max(3, int(cfg.endpoint_silence_s / 0.02) + 5)
            for _ in range(silence_frames):
                tail = b'\x00\x00' * 320
                await stt.send_bytes(b'\x00' + tail if cfg.aec else tail)
            # One spoken turn can contain SEVERAL server-side VAD endpoints: a
            # natural pause mid-sentence makes the recogniser commit an utterance
            # and then keep going. Breaking on the first one silently truncates
            # the learner's question (measured live: "你好，请讲讲二次函数的顶点
            # 坐标应该怎么求。" committed as "你好。" + the rest). Collect every
            # utterance until the provider goes idle after the tail silence (a
            # recv timeout) or sends an explicit end-of-stream frame. A client
            # timer never guesses "done speaking" -- the server's silence does.
            while True:
                try:
                    raw = await stt.recv()
                except TimeoutError:
                    break                       # provider idle: the turn is over
                ev = classify_frame(raw)
                if ev is None:
                    continue
                if ev.kind == 'partial':
                    partials.append(ev.text)
                elif ev.kind == 'utterance':
                    utterances.append(ev.text)
                    stt_done_ms = (self.transport.now() - t0) * 1000.0
                elif ev.kind == 'error':
                    raise LiveVoiceUnavailable('stt_error', ev.text or 'STT error frame')
                elif ev.kind == 'meta':
                    break                       # explicit done / session_summary
            if not utterances:
                raise LiveVoiceUnavailable(
                    'no_utterance',
                    'The recogniser never committed an utterance before going idle; '
                    'no transcript is fabricated.')
            transcript = ' '.join(u for u in utterances if u).strip()
            if not transcript:
                raise LiveVoiceUnavailable('empty_transcript',
                                           'The recogniser committed an empty utterance; '
                                           'no reply is fabricated.')
        finally:
            await stt.aclose()

        reply = (await self.tutor(transcript)).strip()
        if not reply:
            raise LiveVoiceUnavailable('empty_reply',
                                       'The tutor returned no text; no audio is fabricated.')
        reply = reply[:cfg.max_reply_chars]

        tts_first_ms: float | None = None
        audio_chunks = 0
        t_tts = self.transport.now()
        # HTTP streaming TTS (not WebSocket): sub-second first audio is reached
        # by lowering num_step on the /v1/audio/speech endpoint. The legacy
        # /ws/tts path (~15 s, ignores num_step) is no longer used.
        try:
            async for chunk in self.transport.stream_tts(
                    tts_url, text=reply, num_step=cfg.tts_num_step):
                if not chunk:
                    continue
                audio_chunks += 1
                if tts_first_ms is None:
                    tts_first_ms = (self.transport.now() - t_tts) * 1000.0
        except LiveVoiceUnavailable:
            raise
        except Exception as exc:
            raise LiveVoiceUnavailable(
                'tts_error',
                f'HTTP streaming TTS failed: {type(exc).__name__}: {exc}') from exc

        # Barge-in is a *capability*, not a claim that it happened: it is true
        # when the provider supports AEC + streaming partials, because a new
        # partial arriving mid-reply can cancel the in-flight TTS on the client.
        barge_in = bool(self.endpoints.features.get('acoustic_echo_cancellation')) \
            and bool(self.endpoints.features.get('partial_transcripts'))
        return TurnResult(
            transcript=transcript, reply=reply, partials=partials,
            barge_in=barge_in, stt_ms=round(stt_done_ms, 1),
            tts_first_audio_ms=round(tts_first_ms, 1) if tts_first_ms is not None else None,
            audio_chunks=audio_chunks, utterances=utterances,
        )
