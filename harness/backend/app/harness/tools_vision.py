"""The two vision tools: looking at a picture, and reading whether work is on task.

They are separate tools rather than one because they answer different questions and carry
different obligations. ``look_at_image`` is perception: it puts a picture in front of the
model, or asks one question about it. ``check_on_task`` is a *judgement about a learner*,
and everything about it - the opt-in gate, the evidence, the privacy block, the ban on a
punitive move - is in :mod:`app.harness.attention`, not here.

Why ``look_at_image`` has two modes
-----------------------------------
* ``look_at_image(source)`` with no question **attaches** the image to the conversation.
  The tool returns the validated ``data:`` URL in ``ToolResult.images`` and
  ``agent_loop`` re-injects it as a user message with image parts, so the model looks at
  the real pixels and decides what to do next. This is the see-act-see path.
* ``look_at_image(source, question="…")`` **asks** the model about it in a side call and
  returns the answer as text. Use it when the answer is what matters and the picture does
  not need to stay in context - it costs one extra call and no context.

Both accept only a ``data:`` URL or a path inside *this learner's* workspace. A remote URL
is refused: otherwise a model could make the server fetch an address of its choosing.
"""

from __future__ import annotations

from typing import Any, Mapping

from .. import model_config
from . import attention, vla
from .toolbox import ToolContext, ToolResult

#: Where the observation goes. Said in every result so a caller cannot mistake a
#: description for a measurement.
OBSERVATION_NOTE = ('This is a description of pixels, not a measurement of understanding. '
                    'Anything the model inferred rather than saw is labelled as inference '
                    'in the text.')


def _settings(ctx: ToolContext):
    return getattr(ctx, 'settings', None)


def look_at_image(ctx: ToolContext, source: str, question: str = '') -> ToolResult:
    """See an image: attach it, or ask one question about it."""
    settings = _settings(ctx)
    if settings is None:
        return ToolResult('look_at_image', False, error='No settings are bound to this call')
    ready, note = vla.vision_status(settings)
    if not ready:
        return ToolResult('look_at_image', False,
                          refused=('No vision model is available, so this image cannot be '
                                   f'read. {note}'),
                          notes=[note])
    try:
        data_url, raw, origin = vla.resolve_image(getattr(ctx, 'workspace', None), source)
    except vla.ImageRefused as exc:
        return ToolResult('look_at_image', False, refused=str(exc), error=str(exc))

    digest = vla.digest(raw)
    provenance = {'sha256': digest, 'bytes': len(raw), 'origin': origin,
                  'model': (vla.card_for(settings).display_name if vla.card_for(settings)
                            else model_config.effective(settings).provider_model or '')}
    question = (question or '').strip()
    if not question:
        # Attach, do not describe: the loop injects the picture and the model looks itself.
        return ToolResult('look_at_image', True,
                          {'attached': True, 'image': provenance,
                           'next': ('The image is attached to the conversation; read it '
                                    'before the next step.')},
                          citations=[{'kind': 'image', 'id': digest,
                                      'source': 'this call', 'licence_class': 'personal'}],
                          notes=[OBSERVATION_NOTE], images=[data_url])

    result = vla.observe(settings, [data_url], question)
    if result is None:
        return ToolResult('look_at_image', False,
                          error=('The vision call returned nothing; the provider is '
                                 'unreachable, refused the image, or is not billed. No '
                                 'description is invented in its place.'),
                          notes=['The image was not stored.'])
    return ToolResult('look_at_image', True,
                      {'attached': False, 'question': question,
                       'description': result['text'], 'image': provenance,
                       'usage': result['usage']},
                      citations=[{'kind': 'image', 'id': digest, 'source': 'this call',
                                  'licence_class': 'personal'}],
                      notes=[OBSERVATION_NOTE])


def check_on_task(ctx: ToolContext, task: str, snapshot: str = '',
                  signals: Mapping[str, Any] | None = None) -> ToolResult:
    """Read whether the learner's work is on the task, with evidence and a teaching move."""
    settings = _settings(ctx)
    if settings is None:
        return ToolResult('check_on_task', False, error='No settings are bound to this call')
    reading = attention.assess(settings, task=task, signals=signals or {}, snapshot=snapshot)
    if not reading.get('ok'):
        return ToolResult('check_on_task', False, refused=reading.get('refused', 'Refused'),
                          data=reading, notes=[reading.get('refused', '')])
    return ToolResult('check_on_task', True, reading,
                      citations=[{'kind': 'attention_reading', 'source': 'this learner only',
                                  'licence_class': 'personal'}],
                      notes=[reading['suggested_action'],
                             'Frames are not stored; only this reading is returned.'])
