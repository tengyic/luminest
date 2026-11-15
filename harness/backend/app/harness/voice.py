"""Text to speech through a local VoiceStudio backend.

VoiceStudio (https://github.com/debpalash/VoiceStudio) is a self-hosted voice
workbench. Its Python backend exposes an OpenAI-compatible
``POST /v1/audio/speech`` on loopback (default port 3900), so this module is the
only place that knows its contract.

**Why this replaced edge-tts.** The previous provider was the ``edge-tts``
library calling Microsoft's public speech endpoint: every utterance left the
machine and carried the learner's text to a third party, and it needed the
network to be up for a lesson to speak. VoiceStudio runs on the operator's own
machine, so the audio path is now local.

**What that changes about the gate.** ``media_enabled`` used to mean "this
instance may make outbound calls". The call here is loopback, so that reading
would now be false -- yet the flag went on deciding whether an instance produces
audio at all. That conflation muted the shipped desktop bundle: it turns
``media_enabled`` off to keep the privacy policy true, and the tutor's voice went
off with it, with the refusal only visible to a learner who went looking. The
gate is now ``voice_enabled``, its own switch with its own default, and the
refusal text names that switch rather than the network one.

**Failure is reported, never faked.** A local service can be missing, still
loading a model, waiting for a licence to be accepted, or busy on a GPU. Each of
those has a different fix, so each gets its own code and its own sentence. A 200
whose body is not audio (a proxy error page, a JSON error) is rejected rather
than written to disk as a corrupt ``.mp3`` -- that is the failure mode that
produces a file which exists, is non-empty, and will not play.
"""
from __future__ import annotations

import array
import io
import json
import logging
import os
import re
import shutil
import subprocess
import threading
import time
import wave
from typing import Any

import httpx

from . import voice_ws
from .media import USER_AGENT

log = logging.getLogger('luminfest.voice')

#: Where a stock VoiceStudio install listens. Override with HARNESS_VOICE_BASE_URL.
DEFAULT_BASE_URL = 'http://127.0.0.1:3900'
#: Cheap capability document the backend serves; used as the liveness probe.
DISCOVERY_PATH = '/.well-known/voicestudio-speech'
MODELS_PATH = '/v1/models'
SPEECH_PATH = '/v1/audio/speech'
#: The same backend's batch transcription endpoint. A live course needs ASR as well
#: as TTS: the learner speaks a barge-in question, and the tutor answers the words
#: that were actually said rather than a canned interruption.
TRANSCRIPTION_PATH = '/v1/audio/transcriptions'
TRANSCRIPTION_MODEL = 'whisper-1'
#: The batch endpoint above is correct but slow on this host (measured ~20 s for
#: a one-second utterance, because it re-loads the recogniser per request). A
#: barge-in question cannot wait 20 seconds, so the live course uses the same
#: service's streaming WebSocket with raw s16le mono 16 kHz PCM, which measured
#: ~1.8 s end to end. The batch path stays as the declared fallback for audio we
#: cannot decode here, and for a provider that refuses the upgrade.
TRANSCRIPTION_STREAM_PATH = '/v1/audio/transcriptions/stream'
STREAM_SAMPLE_RATE = 16000
STREAM_FRAME_BYTES = 640          # 20 ms of s16le mono at 16 kHz
STREAM_MIN_DECODE_BYTES = 256     # below this it is a test fixture, not audio
MAX_STREAM_SECONDS = 30.0
#: A microphone chunk must never be able to pin the server. Eight MB is several
#: minutes of browser-recorded opus/webm, well past one utterance.
MAX_ASR_BYTES = 8 * 1024 * 1024
#: The request schema caps ``input`` at 4096 characters (SpeechRequest.max_length).
MAX_INPUT_CHARS = 4096
#: VoiceStudio clamps ``speed`` to this range; outside it the request is a 400.
MIN_SPEED, MAX_SPEED = 0.25, 4.0
#: A probe must never hold a page render. Connection-refused is instant; this cap
#: only matters for a service that accepts the socket and then stalls.
PROBE_TIMEOUT = 1.5

#: ``en-US-AriaNeural`` and friends are edge-tts voice names. They mean nothing to
#: VoiceStudio, and silently passing one through would either 400 or -- worse --
#: produce the default voice while the caller believes it asked for Aria.
_EDGE_VOICE_RE = re.compile(r'^[a-z]{2,3}-[A-Z]{2}-[A-Za-z0-9]+Neural$')
_RATE_RE = re.compile(r'^\s*([+-]?)(\d+(?:\.\d+)?)\s*(%?)\s*$')

#: A style instruction longer than this is not a tone, it is a paragraph.
MAX_INSTRUCT_CHARS = 1000

#: The OmniVoice family does not accept freeform style prose. Its ``instruct`` is a
#: closed vocabulary of speaker-design tags, one value per category, and
#: ``omnivoice.utils.voice_design.sanitize_instruct`` **drops everything else
#: without an error** -- a request for "a warm, encouraging teacher" comes back as
#: the engine's default voice and a 200. Mirrored here so the tool can say that
#: out loud instead of reporting a tone it never applied. Keep in step with the
#: engine's ``_INSTRUCT_CATEGORIES``.
_OMNIVOICE_CATEGORIES: tuple[frozenset[str], ...] = (
    frozenset({'male', 'female'}),
    frozenset({'child', 'teenager', 'young adult', 'middle-aged', 'elderly'}),
    frozenset({'very low pitch', 'low pitch', 'moderate pitch', 'high pitch',
               'very high pitch'}),
    frozenset({'whisper'}),
    frozenset({'american accent', 'british accent', 'australian accent',
               'chinese accent', 'canadian accent', 'indian accent',
               'korean accent', 'portuguese accent', 'russian accent',
               'japanese accent'}),
    frozenset({'河南话', '陕西话', '四川话', '贵州话', '云南话', '桂林话',
               '济南话', '石家庄话', '甘肃话', '宁夏话', '青岛话', '东北话'}),
)


#: Voices the Settings picker offers. Each is a **(profile, tone)** pair the client sends
#: as the ``voice`` and ``tone`` of every speech request. They are not backend state: the
#: selection lives on the Mac (it follows the operator's machine, not their account) and
#: rides in on each request, so adding or renaming a preset here changes nothing the server
#: must remember.
#:
#: ``default`` uses the instance's configured voice and tone (``HARNESS_VOICE_NAME`` /
#: ``HARNESS_VOICE_INSTRUCT``) -- the safe choice when VoiceStudio has no matching profile.
#: The instruct-based presets work with the stock OmniVoice engine **without** a named
#: profile, because OmniVoice honours the tags directly; a non-OmniVoice engine simply
#: passes the same string through as its own ``instructions``. ``custom`` is a sentinel the
#: client replaces with a freeform profile name the operator typed in the picker.
VOICE_PRESETS: tuple[dict, ...] = (
    {'id': 'default', 'label': 'Default voice', 'voice': '', 'tone': '',
     'note': 'The instance-configured voice and tone (HARNESS_VOICE_NAME / '
             'HARNESS_VOICE_INSTRUCT).'},
    {'id': 'warm_teacher', 'label': 'Warm teacher · female, British', 'voice': '',
     'tone': 'female, young adult, moderate pitch, british accent', 'note': ''},
    {'id': 'clear_narrator', 'label': 'Clear narrator · male, American', 'voice': '',
     'tone': 'male, middle-aged, moderate pitch, american accent', 'note': ''},
    {'id': 'friendly_tutor', 'label': 'Friendly tutor · female, American', 'voice': '',
     'tone': 'female, young adult, moderate pitch, american accent', 'note': ''},
    {'id': 'calm_explainer', 'label': 'Calm explainer · male, Australian', 'voice': '',
     'tone': 'male, young adult, moderate pitch, australian accent', 'note': ''},
    {'id': 'energetic_coach', 'label': 'Energetic coach · female, high pitch', 'voice': '',
     'tone': 'female, young adult, high pitch, american accent', 'note': ''},
    {'id': 'mandarin_teacher', 'label': 'Mandarin teacher · female, Chinese', 'voice': '',
     'tone': 'female, young adult, moderate pitch, chinese accent', 'note': ''},
    {'id': 'custom', 'label': 'Custom profile name…', 'voice': '', 'tone': '',
     'note': 'Send a specific VoiceStudio profile name as the voice.'},
)


def list_voices(settings) -> dict:
    """What the Settings picker offers, and whether voice output is on.

    Single source of truth for the client's voice list: the picker renders
    ``presets``, ``default`` is what an empty selection resolves to, and ``enabled`` tells
    the UI whether the switch in Settings will do anything. ``served_models`` lets the UI
    warn when the configured engine is not what VoiceStudio is actually serving.
    """
    return {
        'enabled': bool(getattr(settings, 'voice_enabled', False)),
        'model': model(settings),
        'served_models': list(served_models(settings)),
        'current_voice': default_voice(settings),
        'presets': list(VOICE_PRESETS),
    }


class VoiceError(Exception):
    """A synthesis attempt that produced no audio, with an actionable reason.

    ``code`` is stable and testable; ``message`` is written for the operator who
    has to fix it, not for the learner who is waiting.
    """

    def __init__(self, code: str, message: str, *, retryable: bool = False,
                 status: int | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.status = status

    def __str__(self) -> str:
        return self.message


# --------------------------------------------------------------------- settings

def base_url(settings) -> str:
    raw = str(getattr(settings, 'voice_base_url', '') or DEFAULT_BASE_URL).strip()
    return raw.rstrip('/')


def model(settings) -> str:
    return str(getattr(settings, 'voice_model', '') or 'omnivoice').strip()


#: Models VoiceStudio advertises that are aliases for whichever engine is active. Any of
#: them is a safe substitute when the configured name is not served, because the alias is
#: by definition the engine the operator is actually running.
ALIAS_MODELS = ('tts-1', 'tts-1-hd', 'gpt-4o-mini-tts')

#: How long an advertised-models reading is trusted. Long enough that a render loop does
#: not probe on every sentence, short enough that restarting VoiceStudio with a different
#: engine is picked up without restarting the harness.
SERVED_TTL_SECONDS = 60.0
_served: dict[str, tuple[float, tuple[str, ...]]] = {}


def served_models(settings) -> tuple[str, ...]:
    """Model ids the backend advertises, or ``()`` when it cannot be asked.

    This is what makes a wrong ``HARNESS_VOICE_MODEL`` visible instead of silent. A name
    the backend does not serve does not produce a clean 4xx — VoiceStudio 0.5.6 accepts the
    request and then never answers, so the synthesis thread hangs until its timeout and the
    teacher is mute with no error to read. Checking the advertised list first turns that
    into a substitution the operator can see.
    """
    root = base_url(settings)
    cached = _served.get(root)
    now = time.time()
    if cached and now - cached[0] < SERVED_TTL_SECONDS:
        return cached[1]
    try:
        with _client(settings, read_timeout=PROBE_TIMEOUT) as client:
            response = client.get(f'{root}{MODELS_PATH}')
            if response.status_code != 200:
                return ()
            payload = response.json()
    except (httpx.HTTPError, ValueError):
        return ()
    entries = payload.get('data') if isinstance(payload, dict) else None
    ids = tuple(str(entry.get('id')) for entry in (entries or [])
                if isinstance(entry, dict) and entry.get('id'))
    _served[root] = (now, ids)
    return ids


def resolve_model(settings) -> tuple[str, str]:
    """``(model_to_use, note)``. The note is empty when the configured name is served.

    A configured model that the backend does not advertise is replaced by the first
    advertised alias, and the substitution is reported rather than hidden: a voice that
    quietly changes is less bad than a teacher who never speaks, but it is still a change
    the operator should see in the log.
    """
    configured = model(settings)
    advertised = served_models(settings)
    if not advertised or configured in advertised:
        return configured, ''
    substitute = next((name for name in ALIAS_MODELS if name in advertised),
                      advertised[0])
    note = (f'VoiceStudio does not serve model {configured!r} '
            f'(it advertises {", ".join(advertised[:6])}); used {substitute!r} instead. '
            f'Set HARNESS_VOICE_MODEL={substitute} to make this explicit.')
    log.warning(note)
    return substitute, note


def default_voice(settings) -> str:
    return str(getattr(settings, 'voice_name', '') or 'default').strip()


#: Voice design is *sampled*. Two unseeded takes of one sentence come back as two
#: different people (measured 2026-11-15: zero-crossing rate 3152 vs 2733, different
#: durations); two seeded takes are byte-identical. Without a seed the tutor changes
#: speaker every sentence, which is worse than an imperfect voice -- it breaks the one
#: thing a teacher's voice is for, being the same person across a lesson.
DEFAULT_SEED = 1234


def voice_seed(settings) -> int | None:
    """The voice-design seed, or ``None`` to let the engine draw a new speaker.

    Settings win over the environment so a caller can pass a modified settings object
    in a test without touching process state. ``0`` is VoiceStudio's own "no seed",
    and is treated as an explicit opt-out rather than silently replaced.
    """
    raw = getattr(settings, 'voice_seed', None)
    if raw is None or raw == '':
        raw = os.getenv('HARNESS_VOICE_SEED', DEFAULT_SEED)
    try:
        seed = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_SEED
    return seed or None


def voice_language(settings) -> str:
    """Pin phonemisation for short text, or ``''`` to let the engine guess.

    Measured: an unseeded six-character Chinese phrase is occasionally voiced with
    English prosody and transcribes as nonsense; ``zh`` makes the same phrase stable.
    Default is empty because the harness also teaches in English, and forcing Chinese
    phonemes on an English sentence would be the same defect in the other direction.
    """
    raw = getattr(settings, 'voice_language', None)
    if raw is None or raw == '':
        raw = os.getenv('HARNESS_VOICE_LANGUAGE', '')
    return str(raw).strip()


def voice_num_step(settings) -> int | None:
    """Diffusion steps for the streaming endpoint, or ``None`` for the engine default.

    The streaming ``/v1/audio/speech`` path reaches sub-second first audio at 8 steps
    while lower counts trade intelligibility for latency. Off by default: this path
    is not streaming, so the step count changes quality without buying any TTFA.
    """
    raw = getattr(settings, 'voice_num_step', None)
    if raw is None or raw == '':
        raw = os.getenv('HARNESS_VOICE_NUM_STEP', '')
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def timeout(settings) -> float:
    value = float(getattr(settings, 'voice_timeout', 120.0) or 120.0)
    # A local model on CPU is slow; a 12 s network timeout here would abort a
    # perfectly healthy synthesis. Bounded so a typo cannot hang a worker forever.
    return min(max(value, 5.0), 600.0)


def _client(settings, *, read_timeout: float) -> httpx.Client:
    headers = {'User-Agent': USER_AGENT, 'Accept': 'audio/*, application/json'}
    key = str(getattr(settings, 'voice_api_key', '') or '').strip()
    if key:
        # VoiceStudio does not check this itself, but a reverse proxy in front of it
        # might, and sending it costs nothing when nothing is checking.
        headers['Authorization'] = f'Bearer {key}'
    return httpx.Client(timeout=httpx.Timeout(read_timeout, connect=5.0),
                        follow_redirects=False, trust_env=False, headers=headers)


# ------------------------------------------------------------------ arg mapping

def speed_from_rate(rate: Any) -> tuple[float, str]:
    """Translate edge-tts rate syntax into VoiceStudio's multiplier.

    edge-tts took ``'+25%'`` / ``'-10%'``; VoiceStudio takes ``0.25``-``4.0``.
    Callers that still pass the old syntax keep working, and a value the provider
    would reject is clamped with a note instead of becoming a 400.
    """
    if rate is None or rate == '':
        return 1.0, ''
    if isinstance(rate, (int, float)):
        raw = float(rate)
    else:
        match = _RATE_RE.match(str(rate))
        if not match:
            raise VoiceError(
                'bad_rate',
                f'rate {rate!r} is neither a percentage ("+10%") nor a multiplier ("1.1").',
            )
        sign, number, percent = match.groups()
        raw = float(number)
        if percent:
            raw = raw / 100.0
        if sign == '-':
            raw = -raw
        if percent:
            raw = 1.0 + raw
    clamped = min(max(raw, MIN_SPEED), MAX_SPEED)
    if clamped != raw:
        return clamped, (f'Speed {raw:g}x is outside the provider range '
                         f'{MIN_SPEED}-{MAX_SPEED:g}; used {clamped:g}x.')
    return clamped, ''


def resolve_voice(voice: str, settings) -> tuple[str, str]:
    """Map a requested voice onto something VoiceStudio understands.

    Returns ``(voice, note)``. An edge-tts voice name is not an error worth
    failing a lesson over, but substituting it silently would misreport which
    voice the learner heard, so the substitution is stated in the note.
    """
    requested = str(voice or '').strip()
    if not requested:
        return default_voice(settings), ''
    if _EDGE_VOICE_RE.match(requested):
        return default_voice(settings), (
            f'Voice {requested!r} is an edge-tts voice name and does not exist in '
            f'VoiceStudio; used the configured default voice '
            f'{default_voice(settings)!r} instead.'
        )
    return requested, ''


# ------------------------------------------------------------------------ tone

def default_instruct(settings) -> str:
    """The configured style instruction, or ``''`` for none."""
    return str(getattr(settings, 'voice_instruct', '') or '').strip()


def _omnivoice_tags(text: str) -> list[str]:
    """Speaker-design tags present in ``text``, one per category, in first-seen order."""
    lowered = text.lower()
    found: list[tuple[int, str]] = []
    for category in _OMNIVOICE_CATEGORIES:
        hits = [(lowered.find(tag), tag) for tag in category if tag in lowered]
        hits = [(pos, tag) for pos, tag in hits if pos >= 0]
        if hits:
            found.append(min(hits))
    return [tag for _, tag in sorted(found)]


def resolve_instruct(model_id: str, text: str) -> tuple[str, str]:
    """Reduce a style instruction to what ``model_id`` can actually honour.

    Returns ``(instruct, note)``. The note is empty when nothing was lost. A tone
    the engine cannot express is not an error -- the lesson still speaks -- but
    reporting it as applied when it was dropped would misdescribe the audio the
    learner hears, so the reduction is always stated.
    """
    text = (text or '').strip()
    if not text:
        return '', ''
    if len(text) > MAX_INSTRUCT_CHARS:
        text = text[:MAX_INSTRUCT_CHARS].rstrip()
        truncated = (f'Style instruction was longer than {MAX_INSTRUCT_CHARS} '
                     f'characters and was truncated.')
    else:
        truncated = ''

    if not str(model_id).startswith('omnivoice'):
        return text, truncated

    tags = _omnivoice_tags(text)
    if not tags:
        return '', (
            f'OmniVoice cannot express {text!r} as a style: its instruction is a '
            f'closed set of speaker-design tags (e.g. "female, young adult, '
            f'moderate pitch, british accent"), so this text was dropped and the '
            f'engine default was used. Choose a freeform-instruction engine '
            f'(e.g. cosyvoice) if the tone matters.'
        )
    kept = ', '.join(tags)
    # Already a pure tag list: nothing was lost, so there is nothing to explain.
    parts = [part.strip().lower() for part in text.split(',') if part.strip()]
    already_tags = bool(parts) and all(
        any(part in category for category in _OMNIVOICE_CATEGORIES) for part in parts)
    if already_tags and len(parts) == len(tags):
        return kept, truncated
    note = (f'OmniVoice accepts only speaker-design tags; used {kept!r} from the '
            f'style instruction and dropped the rest.')
    return kept, (note + ' ' + truncated).strip()



# ---------------------------------------------------------------------- probing

def probe(settings) -> tuple[bool, str]:
    """Whether a VoiceStudio backend is answering, with a sentence either way.

    Two paths are tried because the discovery document is newer than the speech
    endpoint: an older build 404s the former and still serves ``/v1/models``.

    Answering is not the same as *able to speak*. A configured model the backend does not
    advertise is called out here, because the symptom is a synthesis request that is
    accepted and then never answered — a mute teacher with nothing in the log.
    """
    root = base_url(settings)
    last = ''
    try:
        with _client(settings, read_timeout=PROBE_TIMEOUT) as client:
            for path in (DISCOVERY_PATH, MODELS_PATH):
                response = client.get(f'{root}{path}')
                if response.status_code == 200:
                    _chosen, note = resolve_model(settings)
                    return True, note or f'VoiceStudio is answering at {root}.'
                last = f'HTTP {response.status_code} from {path}'
    except httpx.ConnectError:
        return False, (f'No VoiceStudio backend is listening at {root}. Start the '
                       f'desktop app (or its API) and set HARNESS_VOICE_BASE_URL if '
                       f'it listens somewhere else.')
    except httpx.HTTPError as exc:
        return False, f'VoiceStudio at {root} did not answer: {type(exc).__name__}.'
    return False, (f'Something is listening at {root} but it does not look like '
                   f'VoiceStudio ({last}).')


# ------------------------------------------------------------------- synthesis

def _error_from_response(response: httpx.Response) -> VoiceError:
    """Turn VoiceStudio's OpenAI-shaped error body into a fixable sentence."""
    detail = ''
    code_hint = ''
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        error = body.get('error')
        if isinstance(error, dict):
            detail = str(error.get('message') or '')
            code_hint = str(error.get('code') or '')
        if not detail:
            detail = str(body.get('detail') or '')

    status = response.status_code
    suffix = f' ({detail})' if detail else ''

    if status == 403:
        return VoiceError(
            'licence_not_accepted',
            'VoiceStudio refused the model because its licence has not been accepted '
            f'in the app. Open VoiceStudio, accept the model licence, then retry.{suffix}',
            status=status)
    if status == 429:
        return VoiceError(
            'busy',
            'VoiceStudio is saturated (GPU pool full). Retry after the interval it '
            f'returned.{suffix}', retryable=True, status=status)
    if status in (500, 502, 503, 504):
        return VoiceError(
            'engine_failed',
            f'VoiceStudio could not synthesise speech (HTTP {status}). A model may '
            f'still be loading, or the engine crashed.{suffix}',
            retryable=True, status=status)
    if status == 400 and ('model' in code_hint or 'model' in detail.lower()):
        return VoiceError(
            'model_missing',
            f'VoiceStudio does not have that model available. Install it in the app '
            f'or set HARNESS_VOICE_MODEL to one that is.{suffix}', status=status)
    if status == 409:
        return VoiceError(
            'ambiguous_voice',
            f'The voice name matches more than one profile in VoiceStudio; use the '
            f'profile id instead.{suffix}', status=status)
    return VoiceError(
        'rejected',
        f'VoiceStudio rejected the request (HTTP {status}).{suffix}', status=status)


def synthesize(settings, text: str, *, voice: str = '', speed: float = 1.0,
               response_format: str = 'mp3', instructions: str = '') -> bytes:
    """Return encoded audio bytes, or raise :class:`VoiceError`.

    Never returns a partial or empty payload: callers write the return value
    straight to disk, so an error page must not survive this function.

    Requests are **serialised per engine**, because the engine is: a stock VoiceStudio
    runs one GPU worker and refuses the second concurrent request with a 429 rather than
    queueing it ("1 running, 1 already queued on 1 worker(s)"). A harness that fires
    two sentences at once therefore does not go twice as fast, it gets one clip and one
    refusal -- and the refused one is the sentence the learner was waiting for. Waiting
    our turn here costs nothing and turns a race into a queue.
    """
    if not text.strip():
        raise VoiceError('empty_text', 'There is no text to speak.')
    if len(text) > MAX_INPUT_CHARS:
        raise VoiceError(
            'too_long',
            f'Text is {len(text)} characters; the provider accepts at most '
            f'{MAX_INPUT_CHARS} per request. Split the passage.')

    root = base_url(settings)
    chosen_model, _note = resolve_model(settings)
    payload = {
        'model': chosen_model,
        'input': text,
        'voice': voice or default_voice(settings),
        'response_format': response_format,
        'speed': float(speed),
    }
    if instructions:
        # OpenAI's field name. The route maps it onto the engine's own `instruct`,
        # which is the only portable spelling across engines -- sending the
        # native name would be VoiceStudio-specific.
        payload['instructions'] = instructions
    # The voice lock. ``seed`` keeps the sampled speaker fixed; without it every
    # sentence is a new person. ``language`` pins phonemisation where the caller
    # knows it (short Chinese text otherwise drifts into English prosody).
    seed = voice_seed(settings)
    if seed is not None:
        payload['seed'] = seed
    language = voice_language(settings)
    if language:
        payload['language'] = language
    steps = voice_num_step(settings)
    if steps:
        payload['num_step'] = steps
    with _engine_lock(root):
        response = _post_speech(settings, root, payload)

    if response.status_code != 200:
        raise _error_from_response(response)

    media_type = (response.headers.get('content-type') or '').split(';')[0].strip()
    if not media_type.startswith('audio/'):
        # The exact failure this check exists for: a 200 that is actually an error
        # page. Writing it to ``.mp3`` yields a file that exists and will not play.
        raise VoiceError(
            'bad_response',
            f'VoiceStudio answered 200 with {media_type or "no content type"} instead '
            f'of audio, so nothing was written.')
    if not response.content:
        raise VoiceError('bad_response', 'VoiceStudio answered 200 with an empty body.')

    return response.content


#: One lock per engine address. A second engine on another port has its own worker pool,
#: so a single global lock would serialise two machines that never needed to wait.
_engine_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()

#: How long a 429 asks us to wait when it does not say. The engine's own message quotes
#: the real interval ("about 31s"); this is the fallback when the text is unrecognised.
DEFAULT_RETRY_WAIT = 30.0
#: A retry is worth one attempt, not a loop: the second refusal means something else is
#: wrong and the learner is better served by an honest failure than by a longer silence.
MAX_RETRY_WAIT = 75.0


def _engine_lock(root: str) -> threading.Lock:
    with _locks_guard:
        lock = _engine_locks.get(root)
        if lock is None:
            lock = _engine_locks[root] = threading.Lock()
        return lock


def _retry_wait(response: httpx.Response) -> float:
    """The interval the engine asked for, in seconds, bounded."""
    header = (response.headers.get('retry-after') or '').strip()
    if header:
        try:
            return min(max(float(header), 1.0), MAX_RETRY_WAIT)
        except ValueError:
            pass
    match = re.search(r'about (\d+(?:\.\d+)?)\s*s', response.text or '')
    if match:
        return min(max(float(match.group(1)), 1.0), MAX_RETRY_WAIT)
    return DEFAULT_RETRY_WAIT


def _post_speech(settings, root: str, payload: dict) -> httpx.Response:
    """POST once, and once more if the engine says it was merely busy.

    A 429 from this engine is explicit that nothing was started ("safe to retry as-is"),
    so retrying is not a guess about whether the first attempt took effect. Anything
    else is returned to the caller to interpret.
    """
    try:
        with _client(settings, read_timeout=timeout(settings)) as client:
            response = client.post(f'{root}{SPEECH_PATH}', json=payload)
            if response.status_code != 429:
                return response
            wait = _retry_wait(response)
            log.warning('VoiceStudio is busy; retrying in %.0fs', wait)
            time.sleep(wait)
            return client.post(f'{root}{SPEECH_PATH}', json=payload)
    except httpx.ConnectError:
        raise VoiceError(
            'not_running',
            f'No VoiceStudio backend is listening at {root}, so no audio was '
            f'generated. Install it (curl -fsSL https://voicestudio.sh/install | sh) '
            f'or set HARNESS_VOICE_BASE_URL to the port it is on.')
    except httpx.TimeoutException:
        raise VoiceError(
            'timeout',
            f'VoiceStudio did not finish within {timeout(settings):g}s. A cold model '
            f'on CPU can be slower than that; raise HARNESS_VOICE_TIMEOUT_SECONDS or '
            f'warm the model in the app.', retryable=True)


# ------------------------------------------------------------------- transcription


class _StreamFailure(RuntimeError):
    """The streaming recogniser could not serve this utterance.

    Transport-level only. A recording the recogniser heard as silence is not a
    failure -- it is an answer -- and must not trigger the slow batch retry.
    """

    def __init__(self, reason: str, detail: str = ''):
        super().__init__(detail or reason)
        self.reason = reason
        self.detail = detail


def _resample_pcm16(frames: bytes, channels: int, width: int,
                    source_rate: int) -> bytes | None:
    """Mono, 16 kHz, s16le. Pure stdlib: ``audioop`` is gone in Python 3.13."""
    if width != 2 or channels < 1 or not frames:
        return None
    samples = array.array('h')
    try:
        samples.frombytes(frames)
    except ValueError:
        return None
    if channels > 1:
        samples = array.array('h', [
            sum(samples[i:i + channels]) // channels
            for i in range(0, len(samples) - channels + 1, channels)])
    if source_rate != STREAM_SAMPLE_RATE and len(samples) > 1:
        ratio = source_rate / float(STREAM_SAMPLE_RATE)
        resampled = array.array('h')
        position, last = 0.0, len(samples) - 1
        while position < last:
            left = int(position)
            fraction = position - left
            value = samples[left] * (1.0 - fraction) + samples[left + 1] * fraction
            resampled.append(max(-32768, min(32767, int(value))))
            position += ratio
        samples = resampled
    return samples.tobytes()


def decode_pcm(audio: bytes, content_type: str = 'audio/webm') -> bytes | None:
    """Decode a recorded utterance to s16le mono 16 kHz, or ``None``.

    WAV is read with the stdlib. Browser recordings (webm, mp4, ogg, mpeg) go
    through ``ffmpeg`` when it is on PATH. VoiceStudio itself uses ffmpeg for
    exactly this conversion on its own WebM path, so this is not a new
    prerequisite for a machine that can already run the service; when it is
    absent we return ``None`` and the caller uses the batch endpoint instead of
    failing the turn.
    """
    if len(audio) < STREAM_MIN_DECODE_BYTES:
        return None
    kind = str(content_type or '').split(';')[0].strip().lower()
    pcm: bytes | None = None
    if kind in ('audio/wav', 'audio/x-wav', 'audio/wave', 'audio/pcm'):
        try:
            with wave.open(io.BytesIO(audio), 'rb') as handle:
                pcm = _resample_pcm16(handle.readframes(handle.getnframes()),
                                      handle.getnchannels(), handle.getsampwidth(),
                                      handle.getframerate())
        except Exception:                          # noqa: BLE001 - not a WAV after all
            pcm = None
    if pcm is None:
        ffmpeg = shutil.which('ffmpeg')
        if not ffmpeg:
            return None
        try:
            done = subprocess.run(
                [ffmpeg, '-nostdin', '-loglevel', 'error', '-i', 'pipe:0',
                 '-f', 's16le', '-ar', str(STREAM_SAMPLE_RATE), '-ac', '1', 'pipe:1'],
                input=audio, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                timeout=20, check=False)
        except (OSError, subprocess.SubprocessError):
            return None
        pcm = done.stdout if done.returncode == 0 else None
    if not pcm:
        return None
    ceiling = int(MAX_STREAM_SECONDS * STREAM_SAMPLE_RATE * 2)
    return pcm if len(pcm) <= ceiling else pcm[:ceiling]


def _stream_transcribe(settings, pcm: bytes) -> dict[str, Any]:
    """One utterance over the streaming WebSocket. Raises :class:`_StreamFailure`.

    The order of operations is measured, not decorative:

    1. Wait for the recogniser's ``ready`` status. A cold model takes ~1.5 s;
       sending the end control into that window tears the session down before
       anything is committed, which looks exactly like "no speech".
    2. Feed 20 ms PCM frames. Only ``pcm`` and ``sr`` are sent: an unknown query
       parameter makes the server stop honouring ``pcm=1`` and try to decode the
       bytes as WebM, which also looks like silence.
    3. Trailing silence lets server-side VAD commit the utterance. The end
       control is sent *only* as a flush if nothing has committed after 1.2 s --
       sent immediately it produces a summary with no utterance event.
    4. Accept a ``summary`` final as the transcript. It carries the same text and
       is what the provider emits when the end control wins the race.
    """
    root = base_url(settings)
    ws_root = root.replace('https://', 'wss://').replace('http://', 'ws://').rstrip('/')
    url = f'{ws_root}{TRANSCRIPTION_STREAM_PATH}?pcm=1&sr={STREAM_SAMPLE_RATE}'
    headers: dict[str, str] = {}
    key = str(getattr(settings, 'voice_api_key', '') or '').strip()
    if key:
        headers['Authorization'] = f'Bearer {key}'
    try:
        sock = voice_ws.connect(url, timeout=6.0, extra_headers=headers or None)
    except Exception as exc:                      # noqa: BLE001
        raise _StreamFailure('voice-stream-unreachable', f'{type(exc).__name__}: {exc}') from exc

    utterances: list[str] = []
    partials: list[str] = []
    summary = ''
    finished = False

    def consume(raw) -> None:
        nonlocal summary, finished
        if raw is None or isinstance(raw, bytes):
            return
        try:
            event = json.loads(raw)
        except (ValueError, TypeError):
            return
        kind = str(event.get('type') or '')
        text = str(event.get('text') or '').strip()
        if kind == 'partial':
            if text:
                partials.append(text)
        elif kind == 'final':
            if str(event.get('final_kind') or 'utterance') == 'utterance':
                if text:
                    utterances.append(text)
            else:
                summary = text or summary
                finished = True
        elif kind == 'error':
            raise _StreamFailure(
                'voice-stream-error',
                str(event.get('message') or event.get('detail') or 'recogniser error'))
        elif kind in ('done', 'session_summary'):
            finished = True

    audio_started = time.monotonic()
    try:
        # 1. Ready. ``session.started`` is accepted too: some builds emit it
        #    without a separate ready status, and waiting forever for a frame
        #    that will never come is worse than starting the audio slightly early.
        ready_by = time.monotonic() + 12.0
        while time.monotonic() < ready_by:
            raw = sock.recv(timeout=0.35)
            if raw is None:
                continue
            if isinstance(raw, str) and ('"ready"' in raw or '"session.started"' in raw):
                break
            consume(raw)
        audio_started = time.monotonic()

        # 2 + 3. Frames, then trailing silence.
        for offset in range(0, len(pcm), STREAM_FRAME_BYTES):
            sock.send_bytes(pcm[offset:offset + STREAM_FRAME_BYTES])
        for _ in range(35):
            sock.send_bytes(b'\x00\x00' * 320)

        # 4. Collect. A natural pause can produce several VAD commits, so keep
        #    reading until the provider is quiet or ends the session.
        deadline = time.monotonic() + min(max(len(pcm) / 32000.0 * 2.0 + 12.0, 6.0), 45.0)
        end_sent = False
        last_event = time.monotonic()
        while time.monotonic() < deadline and not finished:
            now = time.monotonic()
            if not utterances and not end_sent and now - last_event > 1.2:
                try:
                    sock.send_text(json.dumps({'type': 'input_audio.end'}))
                except Exception:                  # noqa: BLE001
                    pass
                end_sent = True
                continue
            if utterances and now - last_event > 0.35:
                break
            raw = sock.recv(timeout=0.2)
            if raw is None:
                continue
            last_event = time.monotonic()
            consume(raw)
            if sock.closed:
                break
    except _StreamFailure:
        raise
    except Exception as exc:                      # noqa: BLE001
        raise _StreamFailure('voice-stream-failed', f'{type(exc).__name__}: {exc}') from exc
    finally:
        sock.close()

    transcript = ' '.join(t for t in utterances if t).strip() or summary.strip()
    return {'text': transcript, 'partials': partials[-12:],
            'stt_ms': round((time.monotonic() - audio_started) * 1000, 1)}


def transcribe(settings, audio: bytes, *, content_type: str = 'audio/webm',
               model: str = TRANSCRIPTION_MODEL) -> dict[str, Any]:
    """Turn one recorded utterance into text, or report why it could not be heard.

    This is the ASR half of a live course; :func:`synthesize` is the TTS half. Both
    go to the same local backend, so a learner's voice never leaves the machine.

    The streaming WebSocket is tried first because a barge-in is a *turn*, not a
    batch job. When the recording cannot be decoded here, or the provider refuses
    the upgrade, the batch endpoint remains a declared fallback: slower, but the
    same words. Neither path ever raises and neither ever fakes a transcript.

    ``transport`` and ``latency_ms`` travel back with the result so the live
    surface can report which path actually answered.
    """
    fallback = {'ok': False, 'text': '', 'reason': '', 'next_action': '',
                'fallback': 'declared', 'provider': 'voicestudio'}
    started = time.monotonic()

    def elapsed() -> int:
        return int((time.monotonic() - started) * 1000)

    if not bool(getattr(settings, 'voice_enabled', False)):
        return {**fallback, 'reason': 'voice-disabled',
                'next_action': 'Turn on voice output in Settings, or type the '
                               'question instead.'}
    if not audio:
        return {**fallback, 'reason': 'empty-audio',
                'next_action': 'Record again, or type the question instead.'}
    if len(audio) > MAX_ASR_BYTES:
        return {**fallback, 'reason': 'audio-too-large',
                'next_action': 'Record a shorter question (under eight MB), or type it.'}

    pcm = decode_pcm(audio, content_type)
    if pcm:
        try:
            streamed = _stream_transcribe(settings, pcm)
        except _StreamFailure as exc:
            log.info('streaming ASR unavailable (%s: %s); using batch', exc.reason, exc.detail)
        else:
            text = str(streamed.get('text') or '').strip()
            if not text:
                return {**fallback, 'reason': 'no-speech', 'transport': 'stream',
                        'latency_ms': elapsed(),
                        'next_action': 'No speech was heard. Check the microphone, or type '
                                       'the question instead.'}
            return {'ok': True, 'text': text[:4000], 'reason': '', 'next_action': '',
                    'fallback': '', 'provider': 'voicestudio', 'transport': 'stream',
                    'model': 'streaming-asr', 'stt_ms': streamed.get('stt_ms'),
                    'latency_ms': elapsed()}

    suffix = {'audio/webm': '.webm', 'audio/mpeg': '.mp3', 'audio/mp4': '.m4a',
              'audio/wav': '.wav', 'audio/ogg': '.ogg'}.get(
                  str(content_type or '').split(';')[0].strip().lower(), '.webm')
    root = base_url(settings)
    try:
        with _client(settings, read_timeout=timeout(settings)) as client:
            response = client.post(
                f'{root}{TRANSCRIPTION_PATH}',
                files={'file': (f'utterance{suffix}', audio, str(content_type or 'audio/webm'))},
                data={'model': model})
    except httpx.ConnectError:
        return {**fallback, 'reason': 'voice-unavailable', 'transport': 'batch',
                'latency_ms': elapsed(),
                'next_action': f'No voice backend is listening at {root}. Start it, '
                               'or type the question instead.'}
    except httpx.TimeoutException:
        return {**fallback, 'reason': 'voice-timeout', 'transport': 'batch',
                'latency_ms': elapsed(),
                'next_action': 'The recogniser did not finish in time. Try a shorter '
                               'recording, or type the question instead.'}
    except Exception as exc:  # noqa: BLE001 - a voice failure must never break a turn
        log.warning('VoiceStudio transcription failed', exc_info=True)
        return {**fallback, 'reason': f'voice-error: {type(exc).__name__}',
                'transport': 'batch', 'latency_ms': elapsed(),
                'next_action': 'Type the question instead; the lesson continues.'}
    if response.status_code != 200:
        return {**fallback, 'reason': f'voice-http-{response.status_code}',
                'transport': 'batch', 'latency_ms': elapsed(),
                'next_action': 'The recogniser refused this recording. Try again or '
                               'type the question instead.'}
    try:
        body = response.json()
    except ValueError:
        return {**fallback, 'reason': 'voice-bad-response', 'transport': 'batch',
                'latency_ms': elapsed(),
                'next_action': 'The recogniser returned a non-JSON response. Type '
                               'the question instead.'}
    text = str(body.get('text') or '').strip() if isinstance(body, dict) else ''
    if not text:
        return {**fallback, 'reason': 'no-speech', 'transport': 'batch',
                'latency_ms': elapsed(),
                'next_action': 'No speech was heard. Check the microphone, or type '
                               'the question instead.'}
    return {'ok': True, 'text': text[:4000], 'reason': '', 'next_action': '',
            'fallback': '', 'provider': 'voicestudio', 'transport': 'batch',
            'latency_ms': elapsed(), 'model': model}
