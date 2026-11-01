"""Speaking the tutor's own words, off the request path.

The tutor already has a voice: ``text_to_speech`` in :mod:`app.harness.tools_creation`
lets the *model* choose to speak a passage mid-turn. This module is the other half -
the turn's **reply itself** is spoken, so a learner who asked to be taught out loud
hears the whole answer while they look at the whiteboard. One turn, one utterance,
the reply text and nothing else.

Why it is a separate module rather than a call into the tool:

* **The tool returns a** :class:`~app.harness.toolbox.ToolResult`, which is the model's
  contract. A route needs a URL and a state.
* **The cache key and the cache directory are shared, not duplicated.** ``audio_root``
  and the digest formula below are deliberately the same ones the tool uses, so a
  passage the model spoke mid-turn and the same passage spoken as a reply resolve to
  one file. Two spellings of the same cache is how a cache starts lying.

**Synthesis is slow and the learner is not.** Rendering a paragraph on this hardware
costs 20-40 seconds. Doing that inside the request would mean a tutor that answers in
forty seconds, which is a worse tutor. So :func:`request` returns immediately with a
descriptor whose state is ``pending``, a daemon thread does the rendering, and the
client polls ``GET /media/audio/{digest}`` (404 while it renders, 200 with the bytes
when it lands). A digest that is already cached is ``ready`` on the first call, which
is the common case in a lesson: the same explanation is replayed, re-rendered, or
given to another learner.

**The cache is keyed by content, never by learner.** The digest covers the text, the
voice, the speed and the instruction - everything that changes the bytes. It does not
cover who asked. That is what makes a shared explanation free on the second learner
and makes the cache a pure function of its inputs.

**Every failure is named.** ``voice_enabled`` off, a reply too long to speak, a
VoiceStudio that is not running - each returns a descriptor that says which, and none
of them produces silence that looks like success. A learner whose voice did not render
must be able to see that, not wonder why the speaker button does nothing.

**The learner's text stays on the machine.** The call is loopback to a local
VoiceStudio, which is why this module is gated on ``voice_enabled`` and not on
``media_enabled``. ``media_enabled`` is the operator's "this instance may reach
third-party image and video APIs" switch, and the shipped desktop bundle turns it off
so the privacy policy's "no outbound media" line stays true. Conflating the two made
that same bundle mute: the tutor's replies were refused before synthesis was even
attempted. A loopback call to an engine the learner is already running is not an
outbound media fetch, and the two switches are now separate.
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
from pathlib import Path
from typing import Any

from . import media, voice as voice_backend

log = logging.getLogger('luminfest.speech')

#: States a descriptor can carry. ``ready`` means the bytes exist; ``pending`` means a
#: thread is rendering them; ``failed`` means it will not (the reason travels with it);
#: ``unavailable`` means this instance will not try (voice output is switched off).
READY = 'ready'
PENDING = 'pending'
FAILED = 'failed'
UNAVAILABLE = 'unavailable'

#: One utterance, one file. The engine's own request schema caps ``input`` at 4096
#: characters (``voice.MAX_INPUT_CHARS``); a reply longer than that is cut at the last
#: sentence boundary that fits and the descriptor says so. Cutting mid-word would
#: produce audio that is wrong in a way nobody can see.
MAX_UTTERANCE_CHARS = voice_backend.MAX_INPUT_CHARS

#: Threads rendering right now, keyed by digest, so two learners asking for the same
#: sentence do not both pay for it.
_in_flight: dict[str, threading.Thread] = {}
#: How the last few renders ended, keyed by digest. A failed render writes no file, so
#: without this the byte route's 404 is indistinguishable from "still rendering" and the
#: client polls a URL that will never fill. Bounded because it is a diagnostic, not a
#: cache: the audio itself is the cache.
_outcomes: dict[str, dict[str, Any]] = {}
OUTCOME_MEMORY = 64
_guard = threading.Lock()


def _remember(digest: str, descriptor: dict[str, Any]) -> None:
    """Record a finished render so ``state`` can explain a missing file."""
    with _guard:
        _outcomes[digest] = {key: descriptor.get(key) for key in
                             ('state', 'reason', 'code', 'bytes', 'voice', 'tone')}
        while len(_outcomes) > OUTCOME_MEMORY:
            _outcomes.pop(next(iter(_outcomes)), None)


def audio_root(settings) -> Path:
    """Where spoken clips live: beside the media image cache, under the data dir.

    The same directory ``tools_creation.text_to_speech`` writes to, on purpose - see
    the module docstring. ``media.cache_root`` already resolves the operator's
    ``media_cache_dir`` override, so an instance that relocated its media relocated
    its audio with it.
    """
    return Path(media.cache_root(settings)).parent / 'audio'


def spoken_text(text: str) -> str:
    """The text that will actually be spoken, and therefore the text that is cached.

    Markdown is for the eye. A reply that reaches a speaker as ``**friction**`` or
    ``### Step 2`` is heard as punctuation, so the markers are stripped here - once,
    in one place, so what the learner reads and what the learner hears are the same
    words. Nothing else is rewritten: no symbol table, no "x" to "times". A mapping
    invented here would be a second, drifting opinion about how a subject is
    pronounced, and it would be wrong in the subjects nobody tested.
    """
    collapsed = ' '.join(str(text or '').split())
    if not collapsed:
        return ''
    cleaned = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', collapsed)  # link -> its label
    cleaned = re.sub(r'[*_`>#]+', '', cleaned)
    return ' '.join(cleaned.split()).strip()


def _clip(text: str) -> tuple[str, bool]:
    """The utterance and whether it was shortened. Cuts at a sentence end, never mid-word."""
    if len(text) <= MAX_UTTERANCE_CHARS:
        return text, False
    window = text[:MAX_UTTERANCE_CHARS]
    cut = max(window.rfind('. '), window.rfind('! '), window.rfind('? '))
    if cut < MAX_UTTERANCE_CHARS // 2:      # no usable boundary: take the window whole
        return window.strip(), True
    return window[:cut + 1].strip(), True


#: How much text one clip may carry. Not a provider limit -- a latency budget. This engine
#: runs at roughly eight characters a second on this machine, so a 1,800-character reply is
#: a four-minute render: one request, one silence, one timeout, and the learner hears
#: nothing at all. A few sentences per clip turns that into a first clip in about half a
#: minute and a continuous stream after it, and it makes an interruption cheap because only
#: the current clip is lost.
CHUNK_CHARS = 220


def utterances(text: str) -> list[str]:
    """Split a reply into speakable clips at sentence boundaries.

    Sentences are grouped up to ``CHUNK_CHARS`` rather than one clip each: a clip per
    sentence would put a queue of tiny requests through a single-worker engine and pay the
    per-request overhead every time. A sentence longer than the budget is cut at a comma
    or a space, never mid-word, because a clip that starts mid-word is heard as a glitch.
    """
    spoken = spoken_text(text)
    if not spoken:
        return []
    sentences = re.split(r'(?<=[.!?])\s+', spoken)
    clips: list[str] = []
    current = ''
    for sentence in sentences:
        if not sentence:
            continue
        if len(sentence) > CHUNK_CHARS:
            if current:
                clips.append(current)
                current = ''
            # Long sentence: break on a comma if there is one past halfway, else a space.
            while len(sentence) > CHUNK_CHARS:
                window = sentence[:CHUNK_CHARS]
                cut = max(window.rfind(', '), window.rfind('; '), window.rfind(' '))
                if cut < CHUNK_CHARS // 2:
                    cut = CHUNK_CHARS
                clips.append(sentence[:cut + 1].strip())
                sentence = sentence[cut + 1:].strip()
            current = sentence
            continue
        candidate = f'{current} {sentence}'.strip()
        if len(candidate) > CHUNK_CHARS:
            clips.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        clips.append(current)
    return [clip for clip in clips if clip]


def _digest(model: str, chosen_voice: str, speed: float, instruct: str, text: str) -> str:
    """The same formula the tool uses, so one passage is one file across both paths."""
    return hashlib.sha256(
        f'{model}\x00{chosen_voice}\x00{speed}\x00{instruct}\x00{text}'.encode()
    ).hexdigest()[:16]


def _descriptor(settings, digest: str, state: str, **extra) -> dict[str, Any]:
    payload: dict[str, Any] = {
        'digest': digest,
        'state': state,
        'url': f'/api/v1/media/audio/{digest}',
        'format': 'mp3',
        'provider': 'voicestudio',
        'voice': voice_backend.default_voice(settings),
        'model': voice_backend.model(settings),
    }
    payload.update(extra)
    return payload


def state(settings, digest: str) -> dict[str, Any]:
    """What this instance knows about one clip, without rendering anything."""
    if not digest or not digest.isalnum() or len(digest) > 32:
        return {'digest': digest, 'state': 'unknown', 'url': ''}
    target = audio_root(settings) / f'{digest}.mp3'
    if target.exists() and target.stat().st_size > 0:
        return {'digest': digest, 'state': READY,
                'url': f'/api/v1/media/audio/{digest}',
                'bytes': target.stat().st_size, 'format': 'mp3'}
    with _guard:
        running = digest in _in_flight
        outcome = _outcomes.get(digest)
    if running:
        return {'digest': digest, 'state': PENDING,
                'url': f'/api/v1/media/audio/{digest}', 'format': 'mp3'}
    if outcome:
        # A render that ended without bytes. Saying so is the whole point: the client
        # can stop polling and the operator gets the engine's own sentence instead of
        # a silent teacher.
        return {'digest': digest, 'url': f'/api/v1/media/audio/{digest}',
                'format': 'mp3', **outcome}
    return {'digest': digest, 'state': 'unknown',
            'url': f'/api/v1/media/audio/{digest}', 'format': 'mp3'}


def file_for(settings, digest: str) -> Path | None:
    """The bytes for a digest, or ``None``. The route's only way to reach the disk."""
    if not digest or not digest.isalnum() or len(digest) > 32:
        return None
    target = audio_root(settings) / f'{digest}.mp3'
    if target.exists() and target.stat().st_size > 0:
        return target
    return None


def enabled(settings) -> bool:
    """Whether this instance may synthesise speech.

    ``voice_enabled``, not ``media_enabled``. The two answer different questions: media is
    "may this instance fetch pictures from third-party APIs", voice is "may it call the
    VoiceStudio on this machine". Gating voice on media made the shipped desktop bundle mute
    -- it turns media off to keep the privacy policy true, and the tutor's voice went with it.
    """
    return bool(settings and getattr(settings, 'voice_enabled', False))


def plan(settings, text: str, *, voice: str = '', rate: str = '', tone: str = '') -> dict:
    """Everything about speaking ``text`` except the rendering: digest, state, why not.

    Pure and synchronous, so a route can ask "would this be spoken?" without paying
    for a synthesis. This is also the function a test calls: every refusal reason is
    reachable without a VoiceStudio on the machine.
    """
    spoken = spoken_text(text)
    if not spoken:
        return {'state': FAILED, 'reason': 'There is nothing to speak.',
                'url': '', 'digest': ''}
    if not enabled(settings):
        return {'state': UNAVAILABLE,
                'reason': 'Voice output is switched off for this instance '
                          '(HARNESS_VOICE_ENABLED=0).',
                'url': '', 'digest': ''}
    if len(spoken) > MAX_UTTERANCE_CHARS * 4:
        # Not a cap on speech - a cap on what one utterance may carry. A reply four
        # times the engine's limit is a document, and a document read aloud is not
        # teaching.
        return {'state': FAILED,
                'reason': f'The reply is {len(spoken)} characters; one utterance '
                          f'carries at most {MAX_UTTERANCE_CHARS}.',
                'url': '', 'digest': ''}
    utterance, truncated = _clip(spoken)
    try:
        speed, _ = voice_backend.speed_from_rate(rate)
        chosen_voice, _ = voice_backend.resolve_voice(voice, settings)
        requested_tone = (tone or '').strip() or voice_backend.default_instruct(settings)
        # The engine that will actually speak, not the one that was configured. When a
        # name is not served the request is rerouted to an alias, and the instruction
        # vocabulary belongs to the engine that renders: OmniVoice tags sent to
        # ``tts-1`` are rejected outright. It also keeps the cache honest -- a
        # substitution is different audio, so it must not reuse the old digest.
        speaking_model, _ = voice_backend.resolve_model(settings)
        instruct, _ = voice_backend.resolve_instruct(speaking_model, requested_tone)
    except voice_backend.VoiceError as exc:
        return {'state': FAILED, 'reason': str(exc), 'url': '', 'digest': ''}
    digest = _digest(speaking_model, chosen_voice, speed, instruct, utterance)
    descriptor = _descriptor(settings, digest, PENDING, voice=chosen_voice, speed=speed,
                             tone=instruct, truncated=truncated,
                             spoken_chars=len(utterance))
    if file_for(settings, digest) is not None:
        descriptor['state'] = READY
        descriptor['cached'] = True
        return descriptor
    return descriptor


def request(settings, text: str, *, voice: str = '', rate: str = '',
            tone: str = '') -> dict:
    """Speak ``text``: render it now if it is cached, otherwise start a thread.

    The returned descriptor is what a route puts on the turn. ``state`` is ``ready``
    (bytes on disk, play immediately), ``pending`` (a thread is rendering; poll the
    url), ``failed`` or ``unavailable`` (never will be, with the reason).
    """
    descriptor = plan(settings, text, voice=voice, rate=rate, tone=tone)
    if descriptor.get('state') != PENDING:
        return descriptor
    digest = descriptor.get('digest') or ''
    if not digest:
        return descriptor
    with _guard:
        if digest in _in_flight:
            return descriptor
        thread = threading.Thread(target=_render, args=(settings, digest, text),
                                  daemon=True, name=f'speech-{digest}')
        _in_flight[digest] = thread
    thread.start()
    return descriptor


def request_sequence(settings, text: str, *, voice: str = '', rate: str = '',
                     tone: str = '') -> dict:
    """Speak a whole reply as an ordered series of clips.

    One clip for a paragraph is one long silence: the engine is slower than real time, so a
    reply is only "spoken" if the first clip arrives while the learner is still listening to
    the first sentence. The clips are planned up front (so the client knows how many to
    expect) and rendered in order by one worker, because the engine takes one request at a
    time regardless.

    The returned descriptor keeps the single-clip fields at the top level -- ``url``,
    ``digest``, ``state`` -- so a client written against :func:`request` still plays the
    first clip and still works. ``clips`` is the whole sequence.
    """
    parts = utterances(text)
    if not parts:
        return {'state': FAILED, 'reason': 'There is nothing to speak.',
                'url': '', 'digest': '', 'clips': []}
    descriptors = [plan(settings, part, voice=voice, rate=rate, tone=tone)
                   for part in parts]
    if descriptors[0].get('state') == UNAVAILABLE:
        return {**descriptors[0], 'clips': descriptors}

    pending = [(index, part) for index, part in enumerate(parts)
               if descriptors[index].get('state') == PENDING]
    if pending:
        with _guard:
            thread = threading.Thread(
                target=_render_sequence,
                args=(settings, pending, voice, rate, tone),
                daemon=True, name=f'speech-seq-{descriptors[0]["digest"]}')
            for index, part in pending:
                digest = descriptors[index]['digest']
                if digest not in _in_flight:
                    _in_flight[digest] = thread
        thread.start()

    first = descriptors[0]
    return {**first, 'clips': descriptors,
            'state': first.get('state', PENDING) if pending else READY,
            'total': len(descriptors)}


def _render_sequence(settings, parts: list[tuple[int, str]], voice: str, rate: str,
                     tone: str) -> None:
    """Render the remaining clips in order. One worker, so the engine is never raced."""
    for _index, part in parts:
        try:
            # The voice, rate and tone must travel with the text: the digest the client
            # was given was keyed on them, and rendering with the defaults would write a
            # different file than the one the descriptor points at.
            render(settings, part, voice=voice, rate=rate, tone=tone)
        except Exception as exc:   # noqa: BLE001 - one bad clip must not stop the rest
            log.warning('clip render failed: %s: %s', type(exc).__name__, exc)


def render(settings, text: str, *, voice: str = '', rate: str = '',
           tone: str = '') -> dict:
    """Synthesise ``text`` synchronously and return the descriptor. Used by the worker
    thread and by tests that want to watch a real render happen."""
    descriptor = plan(settings, text, voice=voice, rate=rate, tone=tone)
    if descriptor.get('state') != PENDING:
        return descriptor
    return _render(settings, descriptor['digest'], text, voice=voice, rate=rate, tone=tone)


def _render(settings, digest: str, text: str, *, voice: str = '', rate: str = '',
            tone: str = '') -> dict:
    """The worker body. Writes through a sibling ``.part`` file, exactly as the tool
    does, so a crash mid-write cannot leave a truncated clip that looks like a cache
    hit on the next call.

    Whatever happens, the outcome is remembered before the in-flight mark is cleared:
    a render that fails writes no bytes, and an unexplained 404 is a teacher who is
    silently mute.
    """
    outcome: dict[str, Any]
    try:
        spoken = spoken_text(text)
        utterance, truncated = _clip(spoken)
        speed, _ = voice_backend.speed_from_rate(rate)
        chosen_voice, _ = voice_backend.resolve_voice(voice, settings)
        requested_tone = (tone or '').strip() or voice_backend.default_instruct(settings)
        # Must match ``plan``: the digest was keyed on this instruct, so computing it
        # from a different model here would render different audio under that digest.
        speaking_model, _ = voice_backend.resolve_model(settings)
        instruct, _ = voice_backend.resolve_instruct(speaking_model, requested_tone)
        payload = voice_backend.synthesize(settings, utterance, voice=chosen_voice,
                                           speed=speed, response_format='mp3',
                                           instructions=instruct)
        if not payload:
            outcome = _descriptor(settings, digest, FAILED,
                                  reason='VoiceStudio returned an empty body.',
                                  voice=chosen_voice)
        else:
            root = audio_root(settings)
            root.mkdir(parents=True, exist_ok=True)
            target = root / f'{digest}.mp3'
            staging = target.with_suffix('.mp3.part')
            staging.write_bytes(payload)
            staging.replace(target)
            outcome = _descriptor(settings, digest, READY, voice=chosen_voice, speed=speed,
                                  tone=instruct, truncated=truncated, bytes=len(payload),
                                  spoken_chars=len(utterance))
    except voice_backend.VoiceError as exc:
        # ``not_running`` and friends are states an operator fixes; they are reported
        # with the engine's own sentence so the fix is one search away.
        outcome = _descriptor(settings, digest, FAILED, reason=str(exc),
                              code=getattr(exc, 'code', ''))
    except Exception as exc:   # noqa: BLE001 - a worker thread must never die loudly
        outcome = _descriptor(settings, digest, FAILED,
                              reason=f'{type(exc).__name__}: {exc}')
    finally:
        with _guard:
            _in_flight.pop(digest, None)
    _remember(digest, outcome)
    return outcome


def forget(settings, digest: str) -> bool:
    """Drop one cached clip. The cache is content-addressed, so this is the only
    deletion that makes sense: there is no per-learner set of recordings to remove."""
    target = file_for(settings, digest)
    if target is None:
        return False
    try:
        target.unlink()
    except OSError:
        return False
    return True


#: Spoken once at startup so the engine's first real sentence is not also its first
#: load. Short on purpose: it exists to touch the model, not to say anything.
WARM_PHRASE = 'Ready when you are.'


#: What an utterance is *for*. The words are not enough to decide whether it may cut
#: across another one: "hold on, why is it divided by r factorial?" spoken by a learner
#: must stop the teacher, and the same sentence spoken as a nudge from the TA must wait
#: its turn. So the caller names the kind and the descriptor carries the consequence.
KINDS = ('explanation', 'answer', 'notification')

#: How a clip should meet whatever is already playing.
#: ``replace`` -- stop the current clip and play this one (the learner just spoke).
#: ``append``  -- queue it; the teacher is mid-explanation and this continues it.
#: ``idle_only`` -- never interrupt; speak it only when the channel is free.
DELIVERY = {'answer': 'replace', 'explanation': 'append', 'notification': 'idle_only'}


def classify(clip: dict[str, Any], kind: str) -> dict[str, Any]:
    """Tag a descriptor with what it is for, and how it should meet a clip already playing.

    Not part of the digest: the same words can be an explanation in one place and an
    answer in another, and they are byte-identical audio. The tag is about delivery, not
    about synthesis, so it must not fork the cache.
    """
    chosen = kind if kind in KINDS else 'explanation'
    return {**clip, 'kind': chosen, 'delivery': DELIVERY[chosen]}


def warm(settings) -> None:
    """Move the engine's cold-start cost to launch time.

    The first synthesis after VoiceStudio has been idle pays for loading the model --
    a minute or more on CPU here, well past the render timeout, which is how a teacher
    ends up silent for the first sentence of a class and fine afterwards. Nobody is
    waiting at startup, so the cost belongs there. A failure is logged and otherwise
    ignored: a mute engine must never stop the app from starting.
    """
    if not enabled(settings):
        return
    threading.Thread(target=_warm, args=(settings,), daemon=True,
                     name='speech-warm').start()


def _warm(settings) -> None:
    try:
        ready, why = voice_backend.probe(settings)
        if not ready:
            log.info('speech warm-up skipped: %s', why)
            return
        descriptor = request(settings, WARM_PHRASE)
        log.info('speech warm-up: %s%s', descriptor.get('state'),
                 ' (' + str(descriptor.get('reason')) + ')' if descriptor.get('reason') else '')
    except Exception as exc:   # noqa: BLE001 - startup must survive a broken engine
        log.info('speech warm-up failed: %s: %s', type(exc).__name__, exc)
