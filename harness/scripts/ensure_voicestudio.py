#!/usr/bin/env python3
"""Make sure the learner's own VoiceStudio backend is answering on loopback.

``/api/v1/voice/speak`` is a loopback call to ``POST {base}/v1/audio/speech``.
The desktop VoiceStudio app starts its own uvicorn on 127.0.0.1:3900 when the
app is launched, but nothing starts the app: after a reboot (or after quitting
it) every read-aloud button answered 503 even though the code was correct.

This script is the missing half. It probes, launches the app only when needed,
waits for the API, and reports what it did. It never installs anything, never
touches user data, and never starts a second copy if the API is already up.

    python3 scripts/ensure_voicestudio.py
    python3 scripts/ensure_voicestudio.py --wait 90 --json
    python3 scripts/ensure_voicestudio.py --url http://127.0.0.1:3900 --no-launch

Probes go through a proxy-free opener on purpose: sandboxed environments export
HTTP_PROXY, and a proxy answers a loopback request with a 502 that looks exactly
like "VoiceStudio is down" when it is not.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from urllib.request import ProxyHandler, Request, build_opener
from urllib.error import URLError

DEFAULT_URL = 'http://127.0.0.1:3900'
MAC_APP = '/Applications/VoiceStudio.app'
OPEN_URL = build_opener(ProxyHandler({}))


def probe(base: str, timeout: float = 3.0) -> tuple[bool, list[str]]:
    """Ask ``/v1/models``; a 200 with a model list is the readiness contract."""
    request = Request(base.rstrip('/') + '/v1/models',
                      headers={'Accept': 'application/json'})
    try:
        with OPEN_URL.open(request, timeout=timeout) as response:
            if response.status != 200:
                return False, []
            payload = json.loads(response.read().decode('utf-8', 'replace'))
        models = [str(row.get('id')) for row in (payload.get('data') or [])
                  if isinstance(row, dict) and row.get('id')]
        return bool(models), models[:20]
    except (URLError, OSError, ValueError, json.JSONDecodeError):
        return False, []


def launch_app() -> tuple[bool, str]:
    """Start the installed desktop app via LaunchServices, macOS only."""
    if platform.system() != 'Darwin':
        return False, 'Auto-launch is macOS-only; start VoiceStudio yourself.'
    if not os.path.isdir(MAC_APP):
        return False, f'{MAC_APP} is not installed.'
    try:
        result = subprocess.run(['open', '-a', 'VoiceStudio'],
                                capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f'open failed: {type(exc).__name__}: {exc}'
    if result.returncode != 0:
        return False, (result.stderr or 'open returned non-zero').strip()[:200]
    return True, 'Launched VoiceStudio.app with `open -a`.'


def ensure(base: str = DEFAULT_URL, wait: float = 60.0,
           allow_launch: bool = True) -> dict:
    started = time.monotonic()
    ready, models = probe(base)
    action = 'already running'
    detail = 'VoiceStudio was already answering on loopback.'
    if not ready and allow_launch:
        launched, detail = launch_app()
        action = 'launched' if launched else 'launch failed'
        if launched:
            deadline = started + max(0.0, wait)
            while time.monotonic() < deadline:
                time.sleep(2.0)
                ready, models = probe(base)
                if ready:
                    break
    elif not ready:
        action = 'probe only (launch disabled)'
        detail = ('The API did not answer and --no-launch was requested; start '
                  'VoiceStudio yourself.')
    return {
        'ready': ready,
        'url': base,
        'action': action,
        'detail': detail,
        'models': models,
        'elapsed_seconds': round(time.monotonic() - started, 1),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default=os.getenv('HARNESS_VOICE_BASE_URL', DEFAULT_URL))
    parser.add_argument('--wait', type=float, default=60.0,
                        help='seconds to wait for the API after launching')
    parser.add_argument('--no-launch', action='store_true',
                        help='probe only; never start the app')
    parser.add_argument('--json', action='store_true', help='machine-readable output')
    args = parser.parse_args(argv)

    outcome = ensure(args.url, args.wait, allow_launch=not args.no_launch)
    if args.json:
        print(json.dumps(outcome, indent=2))
    else:
        state = 'READY' if outcome['ready'] else 'NOT READY'
        print(f"VoiceStudio {state} at {outcome['url']} "
              f"({outcome['action']}, {outcome['elapsed_seconds']}s)")
        if outcome['models']:
            print('models: ' + ', '.join(outcome['models']))
        if not outcome['ready']:
            print('detail: ' + outcome['detail'])
    return 0 if outcome['ready'] else 1


if __name__ == '__main__':
    sys.exit(main())
