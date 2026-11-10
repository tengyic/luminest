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

import logging
import re
import threading
import time
from typing import Any

import httpx

from .media import USER_AGENT

log = logging.getLogger('luminfest.voice')

#: Where a stock VoiceStudio install listens. Override with HARNESS_VOICE_BASE_URL.
DEFAULT_BASE_URL = 'http://127.0.0.1:3900'
#: Cheap capability document the backend serves; used as the liveness probe.
DISCOVERY_PATH = '/.well-known/voicestudio-speech'
MODELS_PATH = '/v1/models'
SPEECH_PATH = '/v1/audio/speech'
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
