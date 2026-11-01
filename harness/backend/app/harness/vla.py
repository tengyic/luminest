"""Vision-language-action: the tutor can look, then act, then look again.

The harness already had three of the four pieces of a VLA and was honest about the
fourth. ``provider.chat`` posts whatever ``messages`` it is given, so a message whose
``content`` is a list of parts reaches an image-capable model unchanged; ``main`` already
builds that shape for a lasso capture from the board; ``agent_loop`` already executes
tool calls. What was missing is the part that makes the loop *vision-language-action*
rather than vision-language-description:

* **The model could not acquire an image mid-turn.** Images only arrived with the
  learner's message. A tool that found a figure, or a screenshot of the learner's own
  work, had no way to reach the model's eyes, because OpenAI's ``role: 'tool'`` message
  is text-only.
* **Nothing could answer a question about a picture the model did not already hold.**
  A path on disk or a cached media file was invisible.
* **No model card existed**, so "does this endpoint accept an image?" was a guess made
  from a document rather than a fact read from the configured model.

This module supplies those three, and nothing else. It deliberately does **not** wrap the
agent loop: ``agent_loop.run_agent`` remains the only driver, and it now re-injects an
image a tool returned as a ``user`` message with image parts between steps. That is the
whole mechanism - *see, act, see* - and it is a property of the loop rather than a second
loop beside it.

Three invariants, in the same spirit as the rest of the package:

* **Never raise.** :func:`observe` returns ``None`` on any failure and every caller has a
  deterministic path. A missing vision model is a refusal with a reason, not a crash.
* **No image leaves for a URL the model supplied.** Only a validated ``data:`` URL, or
  bytes read from this learner's own workspace, is ever sent. A model cannot ask the
  server to fetch an arbitrary address.
* **Identity is not an output.** The observer prompt forbids naming or identifying a
  person, guessing age or emotion as fact, and describing anything outside the frame's
  task-relevant content. That rule exists because the same primitive powers the on-task
  check, where the subject is a learner.
"""

from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from . import provider

# --------------------------------------------------------------------- model cards

#: Per-image ceiling, matching the route that already accepts lasso captures. A larger
#: image is refused before any request is built, so a 12 MB phone photo fails fast with a
#: sentence instead of a provider timeout.
MAX_IMAGE_BYTES = 2_000_000

#: How many images one observation may carry. A model asked about six pictures at once
#: answers none of them well, and the token cost is quadratic in practice.
MAX_IMAGES = 4

#: The three formats the rest of the pipeline already produces and serves.
MIME_BY_FORMAT = {'png': 'image/png', 'jpeg': 'image/jpeg', 'webp': 'image/webp'}

#: Floor for one observation's completion budget. Measured against the live endpoint on
#: 2026-10-22: a one-word answer about a 1x1 image cost **171** completion tokens, because
#: V4.1-Flash spends most of the budget on reasoning before it writes anything. At
#: ``max_tokens=40`` the reply was 200 OK with empty content and ``finish_reason: stop`` -
#: a silent "the model said nothing" that reads like a provider fault. 1500 leaves room
#: for the reasoning plus a paragraph, and is still a rounding error against the context
#: window.
OBSERVE_MAX_TOKENS = 1500

_DATA_URL = re.compile(r'^data:(image/(?:png|jpeg|webp));base64,([A-Za-z0-9+/=]+)$')


@dataclass(frozen=True)
class ModelCard:
    """What a configured model can actually do, as opposed to what its name suggests.

    The distinction matters here: on this account ``deepseek-flash`` declares
    ``input_modalities: ["text","image"]`` while ``deepseek-v4-pro`` declares text only.
    A harness that assumed "V4" meant vision would send an image to a text model and get
    a confident description of nothing.
    """

    id: str
    display_name: str
    context_window: int
    max_output_tokens: int
    input_modalities: tuple[str, ...]
    actions: tuple[str, ...]
    aliases: tuple[str, ...] = ()
    note: str = ''

    @property
    def sees(self) -> bool:
        return 'image' in self.input_modalities

    @property
    def acts(self) -> bool:
        """Whether the model can emit native tool calls, which is the 'A' in VLA."""
        return 'tools' in self.actions

    @property
    def vla(self) -> bool:
        return self.sees and self.acts

    def to_dict(self) -> dict[str, Any]:
        return {'id': self.id, 'display_name': self.display_name,
                'context_window': self.context_window,
                'max_output_tokens': self.max_output_tokens,
                'input_modalities': list(self.input_modalities),
                'actions': list(self.actions), 'aliases': list(self.aliases),
                'vision': self.sees, 'action': self.acts, 'vla': self.vla,
                'note': self.note}


#: The cards this build knows. Read from the endpoint's own ``GET /models`` on
#: 2026-10-14 and recorded here so a readiness check needs no network call: a probe that
#: costs a request is a probe nobody runs on a health endpoint.
MODELS: tuple[ModelCard, ...] = (
    ModelCard(id='deepseek-flash', display_name='DeepSeek-V4.1-Flash',
              context_window=1_048_576, max_output_tokens=393_216,
              input_modalities=('text', 'image'), actions=('tools',),
              # 'deepseek-v4.1-flash-1047' is the build label operators use in
              # conversation; the wire id is deepseek-flash and the legacy
              # deepseek-v4-flash is still accepted and routed to the same model.
              aliases=('deepseek-v4.1-flash', 'deepseek-v4.1-flash-1047',
                       'deepseek-flash-1047', 'deepseek-v4-flash'),
              note='The default VLA: image input and native tool calls on one endpoint.'),
    ModelCard(id='deepseek-v4-pro', display_name='DeepSeek-V4-Pro',
              context_window=1_048_576, max_output_tokens=393_216,
              input_modalities=('text',), actions=('tools',),
              note='Text-only input. Usable for actions, not for looking.'),
)

#: ``HARNESS_TUTOR_VISION=1`` lets an operator vouch for a model that is not in
#: :data:`MODELS`. It is an explicit claim, never a default: an unknown model is treated
#: as blind, because sending an image to a text endpoint produces a plausible lie.
VISION_OVERRIDE_ENV = 'HARNESS_TUTOR_VISION'


def model_card(model_id: str | None) -> ModelCard | None:
    """The card for a wire model id or any of its aliases, or ``None`` if unknown."""
    needle = (model_id or '').strip().casefold()
    if not needle:
        return None
    # A provider prefix ('deepseek/deepseek-flash') is a routing detail, not part of the id.
    needle = needle.rsplit('/', 1)[-1]
    for card in MODELS:
        if needle == card.id or needle in {alias.casefold() for alias in card.aliases}:
            return card
    return None


def card_for(settings) -> ModelCard | None:
    return model_card(getattr(settings, 'provider_model', '') or '')


def vision_status(settings) -> tuple[bool, str]:
    """(ready, sentence) for image input. Never raises, never touches the network."""
    if not provider.available(settings):
        return False, ('No language model is configured (HARNESS_TUTOR_PROVIDER is '
                       'offline), so no image can be read.')
    if getattr(settings, 'provider', '') == 'ollama':
        return False, ('The Ollama path is not wired for image content parts; point '
                       'HARNESS_TUTOR_PROVIDER at an OpenAI-compatible vision endpoint.')
    card = card_for(settings)
    if card is not None:
        if card.sees:
            return True, f'{card.display_name} accepts image input.'
        return False, (f'{card.display_name} declares text-only input; configure a vision '
                       'model or set HARNESS_TUTOR_VISION=1 if the endpoint does accept images.')
    import os
    if os.getenv(VISION_OVERRIDE_ENV, '') == '1':
        return True, ('The configured model is not in this build\'s card table; image input '
                      f'is assumed because {VISION_OVERRIDE_ENV}=1.')
    return False, (f'The model {getattr(settings, "provider_model", "")!r} is not in this '
                   'build\'s card table, so image input is not assumed. Set '
                   f'{VISION_OVERRIDE_ENV}=1 to vouch for it.')


def vision_ready(settings) -> bool:
    return vision_status(settings)[0]


def actions_ready(settings) -> bool:
    """Whether native tool calls are wired for this provider (the 'A' in VLA)."""
    return provider.available(settings) and getattr(settings, 'provider', '') != 'ollama'


def describe(settings) -> dict[str, Any]:
    """The posture, for ``/api/v1/harness/status`` and the transparency panel."""
    card = card_for(settings)
    vision, vision_note = vision_status(settings)
    acts = actions_ready(settings)
    return {
        'model': card.to_dict() if card else {'id': getattr(settings, 'provider_model', '') or '',
                                              'known': False},
        'vision': {'ready': vision, 'note': vision_note},
        'action': {'ready': acts,
                   'note': ('Native tool calls are wired for the OpenAI-compatible path.'
                            if acts else 'Tool calls need HARNESS_TUTOR_PROVIDER=openai.')},
        'vla': bool(vision and acts),
        'max_images': MAX_IMAGES,
        'max_image_bytes': MAX_IMAGE_BYTES,
        'observation_loop': ('A tool that returns an image gets it re-injected as a user '
                             'message with image parts before the next step, so the model '
                             'can act on what it just saw.'),
        'identity_rule': ('The observer never names or identifies a person and never states '
                          'age, identity or emotion as fact.'),
    }


# --------------------------------------------------------------------- image plumbing


class ImageRefused(ValueError):
    """A caller-supplied image that cannot be sent. Always carries a sentence."""


def sniff_mime(raw: bytes) -> str | None:
    """The format from magic bytes. The extension is not evidence."""
    if raw[:8] == b'\x89PNG\r\n\x1a\n':
        return 'image/png'
    if raw[:3] == b'\xff\xd8\xff':
        return 'image/jpeg'
    if raw[:4] == b'RIFF' and raw[8:12] == b'WEBP':
        return 'image/webp'
    return None


def to_data_url(raw: bytes, mime: str | None = None) -> str:
    """Bytes to a validated ``data:`` URL, or a refusal that says why."""
    if not isinstance(raw, (bytes, bytearray)) or not raw:
        raise ImageRefused('The image is empty.')
    raw = bytes(raw)
    if len(raw) > MAX_IMAGE_BYTES:
        raise ImageRefused(f'The image is {len(raw)} bytes; the limit is '
                           f'{MAX_IMAGE_BYTES} bytes ({MAX_IMAGE_BYTES // 1_000_000} MB).')
    detected = sniff_mime(raw)
    if detected is None:
        raise ImageRefused('The bytes are not a PNG, JPEG or WebP image.')
    if mime and mime not in MIME_BY_FORMAT.values():
        raise ImageRefused(f'{mime} is not one of the formats this pipeline sends.')
    # The sniffed type wins: a .jpg that is really a PNG would otherwise be labelled wrong
    # and rejected by the provider with a less useful message.
    return f'data:{detected};base64,' + base64.b64encode(raw).decode('ascii')


def check_data_url(value: Any) -> tuple[str, bytes]:
    """(mime, bytes) for a ``data:`` URL, or :class:`ImageRefused`."""
    if not isinstance(value, str) or not value:
        raise ImageRefused('An image must be a data: URL or a workspace path.')
    match = _DATA_URL.match(value)
    if not match:
        raise ImageRefused('Only a data:image/(png|jpeg|webp);base64,… URL is accepted; '
                           'a remote URL would make the server fetch an address the model chose.')
    try:
        raw = base64.b64decode(match.group(2), validate=True)
    except (ValueError, TypeError) as exc:
        raise ImageRefused('The data: URL is not valid base64.') from exc
    if not raw:
        raise ImageRefused('The data: URL decodes to nothing.')
    if len(raw) > MAX_IMAGE_BYTES:
        raise ImageRefused(f'The image decodes to {len(raw)} bytes; the limit is '
                           f'{MAX_IMAGE_BYTES}.')
    return match.group(1), raw


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def part(data_url: str) -> dict[str, Any]:
    """The OpenAI content part for one image."""
    return {'type': 'image_url', 'image_url': {'url': data_url}}


def from_workspace(workspace, path: str) -> tuple[str, bytes]:
    """Read an image out of *this learner's* workspace, or refuse.

    Containment is the workspace's own job (:meth:`sandbox.Workspace.resolve`), which is
    the single place that decides what a path may reach. This function adds only the
    format and size rules.
    """
    if workspace is None:
        raise ImageRefused('No workspace is bound to this call, so a path cannot be read.')
    try:
        target = workspace.resolve(path)
    except Exception as exc:  # SandboxRefused and friends, without importing them here
        raise ImageRefused(str(exc) or 'That path is not readable.') from exc
    if not target.is_file():
        raise ImageRefused(f'No such workspace file: {path}')
    raw = target.read_bytes()
    return to_data_url(raw), raw


def resolve_image(workspace, source: str) -> tuple[str, bytes, str]:
    """(data_url, bytes, origin) for a data: URL or a workspace path."""
    if not isinstance(source, str) or not source.strip():
        raise ImageRefused('An image source is required: a data: URL or a workspace path.')
    source = source.strip()
    if source.startswith('data:'):
        mime, raw = check_data_url(source)
        # Re-encode so the digest and the wire bytes agree even if the caller's base64
        # was padded oddly.
        return to_data_url(raw, mime), raw, 'inline'
    data_url, raw = from_workspace(workspace, source)
    return data_url, raw, 'workspace'


# --------------------------------------------------------------------- observing

OBSERVER_SYSTEM = (
    'You are looking at an image for a tutoring system. Report only what is visibly in '
    'the frame, at the level a careful person would agree on.\n'
    'Rules, in order of importance:\n'
    '1. Never name, identify or guess the identity of a person. Never state age, gender, '
    'ethnicity, emotion or intent as fact; if it matters, say "not determinable".\n'
    '2. Do not describe anything outside the task you were given, even if it is legible. '
    'Ignore other windows, names, messages and personal content.\n'
    '3. Separate observation from inference: "the third line reads 3/4 + 1/2" is an '
    'observation; "the learner added the denominators" is an inference - label it.\n'
    '4. If the image is too small, blurry or cropped to answer, say exactly that instead '
    'of guessing.\n'
    '5. No praise, no teaching, no next step. You are the eyes, not the tutor.'
)


def observation_note(tools: Sequence[str], count: int) -> str:
    """The text that accompanies a re-injected image, so the model knows its provenance."""
    names = ', '.join(sorted({name for name in tools if name})) or 'a tool'
    return (f'{count} image(s) returned by {names} are attached. They were produced during '
            'this turn, not supplied by the learner. Read them before deciding the next step.')


def observe(settings, images: Sequence[str], question: str, *,
            max_tokens: int = OBSERVE_MAX_TOKENS, usage_out: dict | None = None) -> dict[str, Any] | None:
    """One VLM call about one or more images, or ``None``.

    Same never-raise contract as :func:`provider.chat`. The return value carries the text
    and the provenance a caller needs to report honestly: which model read it, how many
    images, and the digest of each, so a later claim can be traced to the picture it came
    from without storing the picture.
    """
    if not vision_ready(settings):
        return None
    if not images:
        return None
    parts: list[dict[str, Any]] = [{'type': 'text', 'text': question or 'Describe this image.'}]
    digests: list[str] = []
    for value in list(images)[:MAX_IMAGES]:
        try:
            mime, raw = check_data_url(value)
        except ImageRefused:
            continue
        # Re-encode from the bytes rather than forwarding the caller's string: the digest
        # and the bytes on the wire then describe the same image, whatever padding or
        # labelling the caller used.
        parts.append(part(to_data_url(raw, mime)))
        digests.append(digest(raw))
    if not parts[1:]:
        return None
    text = provider.chat(settings,
                         [{'role': 'system', 'content': OBSERVER_SYSTEM},
                          {'role': 'user', 'content': parts}],
                         max_tokens=max_tokens, temperature=0.0, usage_out=usage_out)
    if text is None:
        return None
    card = card_for(settings)
    return {'text': text, 'images': len(digests), 'digests': digests,
            'model': (card.display_name if card else getattr(settings, 'provider_model', '')),
            'usage': {key: (usage_out or {}).get(key, 0)
                      for key in ('prompt_tokens', 'completion_tokens', 'total_tokens')}}


def read_json(settings, images: Sequence[str], instruction: str, *,
              max_tokens: int = OBSERVE_MAX_TOKENS, usage_out: dict | None = None) -> Any | None:
    """An observation parsed as JSON, for callers that need fields rather than prose."""
    import json
    result = observe(settings, images, instruction, max_tokens=max_tokens, usage_out=usage_out)
    if result is None:
        return None
    text = result['text'].strip()
    if text.startswith('```'):
        text = text.strip('`')
        if text.lower().startswith('json'):
            text = text[4:]
    start, end = text.find('{'), text.rfind('}')
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(text[start:end + 1])
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, Mapping) else None
