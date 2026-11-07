"""A single, small adapter to the configured language model.

The harness is designed so that the model is an *enhancement*, never a dependency. Every
call returns ``None`` on any failure - missing configuration, timeout, malformed JSON,
oversized reply - and every caller has a deterministic path that does not need it. That
way the offline build produces real content instead of a degraded placeholder, and a
misconfigured key degrades quality rather than availability.

Learner text is always passed as data inside a delimited block, never as instructions,
and the model is told so explicitly.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Mapping, Sequence

from .. import content_locale

import httpx

MAX_REPLY_CHARS = 40000
_JSON_BLOCK = re.compile(r'\{.*\}', re.S)


def meter_usage(usage_out, *, started=None, body=None, outcome='ok') -> None:
    """Fill in the caller's usage dict. A no-op when no dict was passed.

    This module deliberately knows nothing about the database: it reports what the provider
    said and lets the caller decide what to write. An unmetered call is the one that breaks
    the budget, so the error and fallback paths are reported too, with zero tokens.
    """
    if usage_out is None:
        return
    prompt = completion = total = 0
    if isinstance(body, dict):
        usage = body.get('usage')
        if isinstance(usage, dict):                       # OpenAI-compatible
            prompt = int(usage.get('prompt_tokens') or 0)
            completion = int(usage.get('completion_tokens') or 0)
            total = int(usage.get('total_tokens') or (prompt + completion))
        else:                                             # Ollama
            prompt = int(body.get('prompt_eval_count') or 0)
            completion = int(body.get('eval_count') or 0)
            total = prompt + completion
    usage_out.update({'prompt_tokens': prompt, 'completion_tokens': completion,
                      'total_tokens': total, 'outcome': outcome,
                      'latency_ms': None if started is None
                      else int((time.monotonic() - started) * 1000)})


def available(settings) -> bool:
    return bool(settings and getattr(settings, 'provider', 'offline') != 'offline'
                and getattr(settings, 'provider_url', ''))


def label(settings) -> str:
    if not available(settings):
        return 'grounded-offline'
    return f"{settings.provider}:{settings.provider_model}"


def chat(settings, messages: Sequence[dict[str, Any]], *, max_tokens: int = 900,
         temperature: float = 0.2, usage_out: dict | None = None,
         reasoning: str = 'auto', max_reply_chars: int | None = None) -> str | None:
    """One completion, or ``None``. Never raises: the caller always has a fallback.

    ``usage_out``, when supplied, receives the provider's own token accounting plus
    ``latency_ms``, ``outcome`` and -- the part that matters for diagnosis -- the
    provider's ``finish_reason``. It is an ordinary dict, so a caller can meter a call
    without this module ever importing the database.

    ``reasoning`` is ``'auto'`` (send nothing, let the model decide) or ``'off'``. It
    exists because this endpoint is a *reasoning* model whose hidden trace is billed
    against ``max_tokens``: measured on 2026-11-01, one wave-interference simulation
    spent 26,421 of a 32,000-token budget on ``reasoning_tokens`` and was still cut off
    mid-document, while ``reasoning_effort: 'none'`` answered the same arithmetic
    question in 1 completion token with the same result. A caller generating an
    *artifact* -- HTML, a deck, a lesson body -- wants the document, not the trace, so
    it opts out and gets a ceiling that means what it says.

    ``max_reply_chars`` overrides the ``MAX_REPLY_CHARS`` discard for one call. The
    default guard is sized for a chat turn; a self-contained HTML document is
    legitimately larger, and discarding it as if the model had failed would hide a
    complete artefact.
    """
    if not available(settings):
        meter_usage(usage_out, outcome='fallback')
        return None
    ceiling = MAX_REPLY_CHARS if max_reply_chars is None else int(max_reply_chars)
    started = time.monotonic()
    headers = {'Authorization': f'Bearer {settings.provider_key}'} if settings.provider_key else {}
    finish_reason = ''
    try:
        with httpx.Client(timeout=settings.provider_timeout, follow_redirects=False,
                          trust_env=False) as client:
            if settings.provider == 'ollama':
                response = client.post(settings.provider_url.rstrip('/') + '/api/chat', json={
                    'model': settings.provider_model, 'messages': content_locale.apply(messages), 'stream': False,
                    'options': {'num_predict': max_tokens, 'temperature': temperature}}, headers=headers)
                response.raise_for_status()
                if len(response.content) > ceiling * 4:
                    meter_usage(usage_out, started=started, outcome='error')
                    return None
                body = response.json()
                text = body.get('message', {}).get('content')
                finish_reason = str(body.get('done_reason') or '')
                meter_usage(usage_out, started=started, body=body)
            else:
                payload = {'model': settings.provider_model, 'messages': content_locale.apply(messages),
                           'max_tokens': max_tokens, 'temperature': temperature}
                if reasoning == 'off':
                    payload['reasoning_effort'] = 'none'
                response = client.post(settings.provider_url.rstrip('/') + '/chat/completions',
                                       json=payload, headers=headers)
                response.raise_for_status()
                if len(response.content) > ceiling * 4:
                    meter_usage(usage_out, started=started, outcome='error')
                    return None
                body = response.json()
                choice = (body.get('choices') or [{}])[0]
                text = (choice.get('message') or {}).get('content')
                finish_reason = str(choice.get('finish_reason') or '')
                meter_usage(usage_out, started=started, body=body)
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
        meter_usage(usage_out, started=started, outcome='error')
        return None
    if usage_out is not None and finish_reason:
        # Recorded before the emptiness check: "ran out of room" and "said nothing" are
        # the same return value here but they are not the same failure, and the caller
        # is the only place that can tell the learner which one happened.
        usage_out['finish_reason'] = finish_reason
    if not isinstance(text, str) or not text.strip() or len(text) > ceiling:
        # The tokens were still spent, so keep the counts and only mark the outcome.
        if usage_out is not None:
            usage_out['outcome'] = 'error'
        return None
    return text.strip()


def chat_tools(settings, messages: Sequence[dict[str, Any]], *, tools: Sequence[dict[str, Any]],
               tool_choice: str | dict = 'auto', max_tokens: int = 1200,
               temperature: float = 0.2, usage_out: dict | None = None) -> dict[str, Any] | None:
    """One completion with native OpenAI function calling, or ``None`` on any failure.

    Same never-raise contract as :func:`chat`: a missing configuration, a timeout or a
    malformed reply yields ``None`` and the caller keeps a deterministic path. The result,
    when there is one, is a dict::

        {'content': str | None,
         'tool_calls': [{'id': str, 'name': str, 'arguments': dict | str}],
         'finish_reason': str,
         'usage': {'prompt_tokens', 'completion_tokens', 'total_tokens'},
         'reasoning': str | None}

    ``arguments`` is the parsed JSON object, or the raw string when it does not parse -
    the caller decides how to refuse a malformed call, this layer only refuses to guess.
    DeepSeek (and other reasoning models) may return a ``reasoning_content`` field
    alongside ``content``; it is captured under ``reasoning`` and never merged into the
    answer text, because surfacing a chain of thought is a product decision, not a
    provider accident.

    Only the OpenAI-compatible endpoint is wired: that is the protocol DeepSeek and every
    other hosted provider speak. The Ollama path keeps returning ``None`` rather than
    pretending tool support it may not have.
    """
    if not available(settings):
        meter_usage(usage_out, outcome='fallback')
        return None
    if settings.provider == 'ollama':
        meter_usage(usage_out, outcome='fallback')
        return None
    started = time.monotonic()
    headers = {'Authorization': f'Bearer {settings.provider_key}'} if settings.provider_key else {}

    def _spec(tool: Mapping[str, Any]) -> Mapping[str, Any]:
        """Accept either a raw tool spec ``{'name', 'description', 'parameters'}`` or an
        already-wrapped OpenAI wire entry ``{'type': 'function', 'function': {...}}``.

        ``agent_loop.tools_payload`` and ``agent_loop._registry_tools`` both hand over
        wire-format entries, while older callers pass raw specs — normalising here means
        one drift point instead of three. A dict with neither shape is refused with a
        metered error, never guessed at.
        """
        function = tool.get('function')
        if isinstance(function, Mapping) and function.get('name'):
            return function
        if tool.get('name'):
            return tool
        raise ValueError(f'tool spec has neither "function" nor "name": {sorted(tool)}')

    try:
        wire_tools = [{'type': 'function',
                       'function': {'name': spec['name'], 'description': spec.get('description', ''),
                                    'parameters': spec.get('parameters') or {'type': 'object', 'properties': {}}}}
                      for spec in (_spec(tool) for tool in tools)]
    except (ValueError, AttributeError, TypeError):
        meter_usage(usage_out, started=started, outcome='error')
        return None
    try:
        with httpx.Client(timeout=settings.provider_timeout, follow_redirects=False,
                          trust_env=False) as client:
            response = client.post(settings.provider_url.rstrip('/') + '/chat/completions', json={
                'model': settings.provider_model, 'messages': content_locale.apply(messages),
                'tools': wire_tools, 'tool_choice': tool_choice,
                'max_tokens': max_tokens, 'temperature': temperature}, headers=headers)
            response.raise_for_status()
            if len(response.content) > MAX_REPLY_CHARS * 4:
                meter_usage(usage_out, started=started, outcome='error')
                return None
            body = response.json()
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
        meter_usage(usage_out, started=started, outcome='error')
        return None
    choice = body.get('choices', [{}])[0]
    message = choice.get('message') or {}
    calls = []
    for raw in message.get('tool_calls') or []:
        function = raw.get('function') or {}
        name = function.get('name', '')
        if not name:
            continue
        arguments = function.get('arguments', '{}')
        try:
            parsed = json.loads(arguments) if isinstance(arguments, str) else arguments
            if not isinstance(parsed, dict):
                parsed = arguments
        except (ValueError, TypeError):
            parsed = arguments
        calls.append({'id': raw.get('id', ''), 'name': name, 'arguments': parsed})
    meter_usage(usage_out, started=started, body=body)
    usage = {key: usage_out.get(key, 0) for key in ('prompt_tokens', 'completion_tokens', 'total_tokens')} \
        if usage_out is not None else {}
    reasoning = message.get('reasoning_content')
    if not isinstance(reasoning, str) or not reasoning.strip():
        reasoning = None
    return {'content': (message.get('content').strip() if isinstance(message.get('content'), str)
                        and message.get('content').strip() else None),
            'tool_calls': calls, 'finish_reason': choice.get('finish_reason') or 'stop',
            'usage': usage, 'reasoning': reasoning}


def chat_json(settings, messages: Sequence[dict[str, Any]], *, max_tokens: int = 1200,
              usage_out: dict | None = None) -> Any | None:
    """A completion parsed as JSON. Fenced or wrapped output is tolerated; junk is not."""
    text = chat(settings, messages, max_tokens=max_tokens, temperature=0.1, usage_out=usage_out)
    if text is None:
        return None
    candidate = text
    if candidate.startswith('```'):
        candidate = candidate.strip('`')
        if candidate.lower().startswith('json'):
            candidate = candidate[4:]
    match = _JSON_BLOCK.search(candidate)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except (ValueError, TypeError):
        return None


def learner_block(text: str, limit: int = 4000) -> str:
    """Wrap untrusted learner text so it cannot be mistaken for instructions."""
    cleaned = (text or '').replace('```', "'''")[:limit]
    return ('<learner_message untrusted="true">\n' + cleaned + '\n</learner_message>')
