#!/usr/bin/env python3
"""Look at the raw provider response for a simulation request.

The tool only ever sees a string, so a reply that spent its whole budget on hidden
reasoning and a reply that the model refused look identical. This prints the fields the
tool cannot see: finish_reason, whether reasoning content was emitted, and the split
between reasoning and document characters.
"""
import json
import sys
import time
from pathlib import Path

import httpx

BACKEND = Path(__file__).resolve().parents[1] / 'backend'
sys.path.insert(0, str(BACKEND))

from app.config import Settings                          # noqa: E402
from app.harness import creation_gate                    # noqa: E402
from app.harness.tools_creation import _SIM_CAPABILITY_RULES   # noqa: E402

TITLE = 'Wave Interference Bench'
SPEC = ('Two draggable point sources on a grid. Render the interference pattern with '
        'adjustable wavelength, amplitude and source separation; show a vertical '
        'intensity cross-section, mark nodes and antinodes, and let the learner toggle '
        'path-difference readout for a movable probe.')


def main():
    budget = int(sys.argv[1]) if len(sys.argv) > 1 else 16000
    settings = Settings.from_env()
    decision = creation_gate.evaluate({'role': 'teacher', 'category': 'create',
                                       'note': f'{TITLE}. {SPEC}'})
    user = (f'Create a new interactive teaching simulation.\n'
            f'Title: {TITLE}\nSpec: {SPEC}\nHard requirements:\n' +
            '\n'.join(f'- {rule}' for rule in _SIM_CAPABILITY_RULES) +
            f'\n\nFiled requirement (binding): {decision["requirement"]}')
    headers = {'Authorization': f'Bearer {settings.provider_key}'} if settings.provider_key else {}
    started = time.monotonic()
    with httpx.Client(timeout=settings.provider_timeout, trust_env=False) as client:
        r = client.post(settings.provider_url.rstrip('/') + '/chat/completions', json={
            'model': settings.provider_model,
            'messages': [{'role': 'system',
                          'content': creation_gate.SIM_AUTHORING_SYSTEM_PROMPT},
                         {'role': 'user', 'content': user}],
            'max_tokens': budget, 'temperature': 0.2}, headers=headers)
    print(f'elapsed : {time.monotonic() - started:.1f}s   http {r.status_code}')
    body = r.json()
    choice = (body.get('choices') or [{}])[0]
    msg = choice.get('message') or {}
    content = msg.get('content') or ''
    reasoning = msg.get('reasoning_content') or msg.get('reasoning') or ''
    print(f'finish_reason : {choice.get("finish_reason")!r}')
    print(f'usage         : {json.dumps(body.get("usage"), sort_keys=True)}')
    print(f'message keys  : {sorted(msg.keys())}')
    print(f'reasoning     : {len(reasoning)} chars')
    print(f'content       : {len(content)} chars')
    print(f'content head  : {content[:200]!r}')
    print(f'content tail  : {content[-160:]!r}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
