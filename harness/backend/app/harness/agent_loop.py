"""The tool-driving agent loop: the "coding harness" behaviour.

The deterministic loop in :mod:`app.harness.loop` decides *which kind of interaction* a
learner needs. This module is the layer beneath a model that can ask for tools natively:
it calls the provider with the tool catalogue, **executes** whatever the model asked for,
hands the results back as ``role: 'tool'`` messages, and repeats until the model answers
in plain prose, the step cap is reached, or the caller cancels.

Design rules, in the same spirit as the rest of the package:

* **The model is an enhancement, never a dependency.** Every failure path - offline
  provider, timeout, malformed tool arguments - comes back as an ``error`` or
  ``turn_end`` event, never an exception, and never a crash in a route.
* **Tools are dispatched by name, from a registry.** An unknown tool name is *refused*,
  not guessed: the refusal is fed back to the model so it can recover, and the refusal is
  visible in the event trace.
* **Nothing is persisted here.** The loop mutates the caller's message list and yields
  events; what to store is the caller's decision, exactly as ``provider`` never touches
  the database.
* **Reasoning is invisible by default.** The provider may return a chain of thought; it
  only appears in events when the caller passes ``developer_mode=True``.
* **Every tool call carries a learner-facing label.** ``tool_call`` and ``tool_result``
  both include ``label`` - what the tutor is doing in plain words ("Drawing on the
  whiteboard"), so a chat can narrate the work as it happens. See :data:`TOOL_LABELS`.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Iterable, Mapping, Sequence

from . import provider, vla
from .toolbox import ToolResult

#: A tool registry: name -> callable(arguments: dict, ctx) -> ToolResult.
Registry = Mapping[str, Callable[[dict, Any], ToolResult]]

#: Upper bound on loop turns, so a model stuck in a tool-calling rhythm cannot spin
#: forever and burn tokens. Generous enough for real multi-step work, hard enough to bound.
DEFAULT_MAX_STEPS = 8
HARD_MAX_STEPS = 24

#: The event contract. Exactly these types are yielded, and exactly these travel over
#: the SSE wire in ``/api/v1/agent/stream``. ``observation`` appears only when a tool
#: returned an image that was re-injected into the conversation - the point at which the
#: loop becomes vision-language-*action* rather than a chain of text calls.
EVENT_TYPES = ('turn_start', 'message_delta', 'tool_call', 'tool_result', 'observation',
               'turn_end', 'error')

#: What the tutor is doing, in the learner's language, for the chat's activity chips.
#:
#: A tool name is an implementation fact ("whiteboard_apply"); a chip that says
#: "whiteboard_apply" teaches the learner the API instead of the concept. The map is
#: therefore written as a *present continuous action* - the same sentence the tutor
#: would say out loud while it works, so the chip reads as narration, not logging.
#: Every entry names the learner-visible effect, never the mechanism.
#:
#: An unlisted tool falls back to :func:`tool_label`, which title-cases the name. A
#: missing label is therefore still readable - never blank, never "unknown tool".
TOOL_LABELS: dict[str, str] = {
    # the classroom: drawing while teaching
    'whiteboard_read': 'Looking at the whiteboard',
    'whiteboard_apply': 'Drawing on the whiteboard',
    'whiteboard_write': 'Writing on the whiteboard',
    'whiteboard_place_image': 'Pinning a picture on the whiteboard',
    'board_read': 'Looking at the board',
    'board_apply': 'Drawing on the board',
    'board_place_media': 'Pinning media on the board',
    'deck_control': 'Moving the slides',
    # orienting in the course
    'search_concepts': 'Searching the course',
    'read_concept': 'Reading the concept',
    'inspect_prerequisites': 'Checking what you have already got',
    'recall_learner_memory': 'Remembering what we have done',
    'read_learner_evidence': 'Reviewing your recent answers',
    # sources
    'search_material': 'Searching the material',
    'fetch_material_text': 'Reading a source',
    'web_search': 'Searching the web',
    'fetch_page_text': 'Reading a page',
    'wikipedia_summary': 'Reading an encyclopedia entry',
    'image_search': 'Looking for a picture',
    'find_image': 'Finding a picture',
    'image_generate': 'Drawing a picture',
    'find_video': 'Finding a video',
    'search_videos': 'Finding a video',
    'find_simulation': 'Finding something to play with',
    'look_at_image': 'Looking at the image',
    'browser_snapshot': 'Opening a page',
    # teaching acts
    'check_understanding': 'Preparing a question for you',
    'prepare_case_study': 'Building a case study',
    'compose_content': 'Preparing something to show you',
    'build_figure': 'Building the figure',
    'build_presentation': 'Building a narrated deck',
    'generate_slides': 'Building a slide deck',
    'write_simulation': 'Building a simulation',
    'edit_simulation': 'Adjusting the simulation',
    'find_game': 'Finding a game',
    # speaking
    'text_to_speech': 'Speaking',
    # workspace
    'run_in_workspace': 'Running some code',
    'list_workspace': 'Listing the workspace',
    'write_workspace_file': 'Saving a file',
    'read_workspace_file': 'Reading a file',
    # monitoring
    'check_on_task': 'Checking you are still with me',
    # authoring
    'author_course': 'Authoring a course',
    'draft_course': 'Drafting a course',
    'list_authored_courses': 'Listing authored courses',
    'read_course_blueprint': 'Reading the blueprint',
    'extend_course': 'Extending a course',
    'describe_methodology': 'Reading the methodology',
    'illustrate_course': 'Illustrating the textbook',
    'attach_lesson_image': 'Attaching a photograph',
    'course_images': 'Checking the textbook images',
}

#: Fallback for a tool that is not in :data:`TOOL_LABELS`.
_LABEL_FALLBACK = 'Working on it'


def tool_label(name: str) -> str:
    """The learner-facing label for one tool call.

    A chip is shown *while the tutor works*, before any result is known, so the label
    describes the action, not the outcome: "Drawing on the whiteboard", whether or not
    the drawing lands. Results carry their own status through ``ok``.
    """
    label = TOOL_LABELS.get(name, '').strip()
    if label:
        return label
    readable = str(name or '').replace('_', ' ').strip()
    return readable[:1].upper() + readable[1:] if readable else _LABEL_FALLBACK


def tools_payload(specs: Iterable[Any]) -> list[dict[str, Any]]:
    """Turn tool specs into the OpenAI ``tools`` wire format.

    The catalogue's ``arguments`` and ``returns`` strings are prose for the model, not a
    JSON Schema, so the declared schema stays permissive (``additionalProperties``) and
    the prose carries the real contract. A schema invented here would be a second,
    drifting copy of the truth.
    """
    wire = []
    for spec in specs:
        description = ' '.join(part for part in (spec.summary, spec.arguments, spec.returns) if part)
        wire.append({'type': 'function', 'function': {
            'name': spec.name, 'description': description,
            'parameters': {'type': 'object', 'properties': {}, 'additionalProperties': True}}})
    return wire


def run_agent(settings, messages: list[dict[str, Any]], registry: Registry, ctx: Any,
              *, tools: Sequence[dict[str, Any]] | None = None, max_steps: int = DEFAULT_MAX_STEPS,
              developer_mode: bool = False, cancelled: Callable[[], bool] | None = None,
              usage_out: dict | None = None, max_tokens: int = 8000,
              temperature: float = 0.2) -> Iterable[dict[str, Any]]:
    """Drive ``chat_tools`` and tool execution until the model stops or a bound is hit.

    ``max_tokens`` defaults high (8000) because the creation tools ask the model to emit
    a complete self-contained HTML document in one assistant message; a chat-sized cap
    truncates the artifact and the tool correctly refuses to store a partial file.

    Yields the event dicts of :data:`EVENT_TYPES` as they happen. ``messages`` is the
    caller's own list and is extended in place with every assistant and tool message, so
    the caller owns the transcript and decides what to persist. ``cancelled`` is checked
    between steps; when it turns true the loop stops cleanly with a ``turn_end`` whose
    reason is ``'cancelled'``.

    The final assistant text travels on the ``turn_end`` event, because a generator has no
    return channel: callers who only want the answer read it there.
    """
    steps = max(1, min(int(max_steps), HARD_MAX_STEPS))
    if not provider.available(settings):
        yield {'type': 'error', 'message': 'Model not configured. The harness falls back to '
                                           'deterministic, grounded-offline content when no '
                                           'provider is set.'}
        yield {'type': 'turn_end', 'reason': 'unavailable', 'content': None}
        return
    yield {'type': 'turn_start'}
    reason = 'completed'
    content = None
    for _ in range(steps):
        if cancelled is not None and cancelled():
            reason = 'cancelled'
            break
        _release(ctx)
        result = provider.chat_tools(settings, messages, tools=tools if tools is not None
                                     else _registry_tools(registry), max_tokens=max_tokens,
                                     temperature=temperature, usage_out=usage_out)
        if result is None:
            yield {'type': 'error', 'message': 'The model call failed; no tool results were '
                                               'changed by this turn.'}
            reason = 'provider_error'
            break
        if developer_mode and result.get('reasoning'):
            yield {'type': 'message_delta', 'text': result['reasoning'], 'channel': 'reasoning'}
        content = result.get('content')
        calls = result.get('tool_calls') or []
        if not calls:
            if content:
                yield {'type': 'message_delta', 'text': content}
            reason = 'completed'
            break
        messages.append({'role': 'assistant', 'content': content, 'tool_calls': [
            {'id': call['id'], 'type': 'function',
             'function': {'name': call['name'],
                          'arguments': json.dumps(call['arguments'])
                          if isinstance(call['arguments'], dict) else call['arguments']}}
            for call in calls]})
        seen: list[str] = []
        seen_from: list[str] = []
        for call in calls:
            # The label travels on both events: `tool_call` fires while the tool runs
            # (so the chat can show activity before there is any result) and
            # `tool_result` fires when it lands (so the chip can settle without a
            # second lookup of the name).
            yield {'type': 'tool_call', 'id': call['id'], 'name': call['name'],
                   'label': tool_label(call['name']), 'arguments': call['arguments']}
            outcome = _execute(registry, call, ctx)
            yield {'type': 'tool_result', 'id': call['id'], 'name': call['name'],
                   'label': tool_label(call['name']),
                   'ok': outcome.ok, 'summary': _summary(outcome), 'data': outcome.to_dict()}
            messages.append({'role': 'tool', 'tool_call_id': call['id'],
                             'content': _tool_message(outcome)})
            seen.extend(outcome.images)
            if outcome.images:
                seen_from.append(call['name'])
        if seen:
            # A tool message is text-only in the OpenAI protocol, so an image a tool
            # produced is re-injected as a user turn. Without this the model would be
            # told "the screenshot shows a mistake" and could not check it.
            images = seen[:vla.MAX_IMAGES]
            messages.append({'role': 'user', 'content':
                             [{'type': 'text', 'text': vla.observation_note(seen_from, len(images))}]
                             + [vla.part(image) for image in images]})
            yield {'type': 'observation', 'images': len(images), 'tools': sorted(set(seen_from))}
        # Tools are independently durable actions: committed here, not held open across
        # the next provider call. A reasoning-model call can run for minutes, and an
        # uncommitted write keeps SQLite's write lock for that whole window - every other
        # request in the process then times out with "database is locked", and this very
        # session is poisoned by the fallout.
        _release(ctx)
        if developer_mode:
            yield {'type': 'message_delta', 'text': '', 'channel': 'tool_step'}
    else:
        reason = 'max_steps'
    yield {'type': 'turn_end', 'reason': reason, 'content': content}


# ------------------------------------------------------------------ internals

def _release(ctx: Any) -> None:
    """Commit the turn's session so no write transaction outlives a tool step.

    The turn's tools mutate the database through ``ctx.db`` and then the loop calls the
    model again - a call that can run for minutes against a reasoning provider. SQLite
    holds the write lock from the first uncommitted write until commit, so leaving the
    transaction open across the model call starves every other request in the process
    ("database is locked") and poisons this session with a PendingRollbackError on the
    way out. Committing before each model call releases the lock for the call's whole
    window; a failed commit rolls back so the loop keeps a usable session.
    """
    db = getattr(ctx, 'db', None)
    if db is None:
        return
    try:
        db.commit()
    except Exception:   # noqa: BLE001 - a poisoned session must not kill the turn
        try:
            db.rollback()
        except Exception:   # noqa: BLE001
            pass


def _registry_tools(registry: Registry) -> list[dict[str, Any]]:
    """The wire tools for a bare registry, for callers that skipped ``tools_payload``."""
    return [{'type': 'function', 'function': {
        'name': name, 'description': f'Tool {name}.',
        'parameters': {'type': 'object', 'properties': {}, 'additionalProperties': True}}}
        for name in registry]


def _execute(registry: Registry, call: Mapping[str, Any], ctx: Any) -> ToolResult:
    """Dispatch one tool call by name. Unknown names and bad arguments are refusals."""
    name = call.get('name', '')
    entry = registry.get(name)
    if entry is None:
        return ToolResult(name, False, refused=f'Unknown tool {name!r}',
                          error=f'Unknown tool {name!r}')
    arguments = call.get('arguments')
    if not isinstance(arguments, dict):
        return ToolResult(name, False, refused=f'Unparseable arguments for {name!r}',
                          error='Arguments must be a JSON object')
    try:
        return entry(dict(arguments), ctx)
    except Exception as exc:  # a tool crashing must not take the loop down
        return ToolResult(name, False, error=f'{type(exc).__name__}: {exc}')


def _summary(result: ToolResult) -> str:
    if result.refused:
        return result.refused
    if not result.ok:
        return result.error or 'Tool failed'
    return 'ok'


def _tool_message(result: ToolResult) -> str:
    """The evidence, serialized for the model. Kept bounded like every other reply."""
    try:
        payload = json.dumps(result.to_dict(), default=str)
    except (ValueError, TypeError):
        payload = json.dumps({'tool': result.tool, 'ok': result.ok, 'error': 'unserializable'})
    return payload[:provider.MAX_REPLY_CHARS]
