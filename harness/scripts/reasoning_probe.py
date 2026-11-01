#!/usr/bin/env python3
"""Which request field, if any, bounds the reasoning budget on this endpoint?

Artifact generation does not need an 84k-character chain of thought: it needs a document.
If the provider accepts a switch that suppresses or caps reasoning, the token ceiling
becomes predictable and the 140 s latency collapses. This tries the plausible spellings
against a small prompt and reports reasoning_tokens for each, so the choice is measured
rather than assumed.
"""
import json
import sys
from pathlib import Path

import httpx

BACKEND = Path(__file__).resolve().parents[1] / 'backend'
sys.path.insert(0, str(BACKEND))

from app.config import Settings   # noqa: E402

PROMPT = ('A shelf holds 5 distinct books. In how many orders can 3 of them be arranged? '
          'Answer with the number only.')

VARIANTS = {
    'baseline': {},
    'reasoning_effort=none': {'reasoning_effort': 'none'},
    'reasoning_effort=minimal': {'reasoning_effort': 'minimal'},
    'reasoning_effort=low': {'reasoning_effort': 'low'},
    'thinking=disabled': {'thinking': {'type': 'disabled'}},
    'enable_thinking=false': {'chat_template_kwargs': {'enable_thinking': False}},
    'thinking_budget=0': {'thinking_budget': 0},
}


def main():
    settings = Settings.from_env()
    headers = {'Authorization': f'Bearer {settings.provider_key}'} if settings.provider_key else {}
    url = settings.provider_url.rstrip('/') + '/chat/completions'
    for name, extra in VARIANTS.items():
        payload = {'model': settings.provider_model,
                   'messages': [{'role': 'user', 'content': PROMPT}],
                   'max_tokens': 4000, 'temperature': 0.2}
        payload.update(extra)
        try:
            with httpx.Client(timeout=settings.provider_timeout, trust_env=False) as client:
                r = client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            print(f'{name:26s} transport error {exc!r}')
            continue
        if r.status_code != 200:
            print(f'{name:26s} HTTP {r.status_code}  {r.text[:140]}')
            continue
        body = r.json()
        choice = (body.get('choices') or [{}])[0]
        usage = body.get('usage') or {}
        details = usage.get('completion_tokens_details') or {}
        content = ((choice.get('message') or {}).get('content') or '').strip()
        print(f'{name:26s} reasoning={details.get("reasoning_tokens")!s:>6}  '
              f'completion={usage.get("completion_tokens")!s:>6}  '
              f'finish={choice.get("finish_reason")!r}  answer={content[:40]!r}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
