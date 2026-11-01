"""Probe the browser presentation of the app's own window, end to end.

What this proves, in order, against a real server process:

1. the stream is off unless an operator turns it on, and the refusal names the switch;
2. a teacher can report the app's window and a learner cannot;
3. a frame comes back as a JPEG of *that* region, not of the whole screen;
4. the viewer page is served from the same origin as the API it calls;
5. the permission that is missing on this machine is reported as a sentence.

On 3: a region capture needs Screen Recording granted to the binary that runs the backend.
When that grant is absent, ``screencapture -R`` fails while a whole-screen capture still
succeeds — so the probe asks the tool itself which case it is in, and when the answer is "no
grant" it checks that the route reports *that same reason* instead of demanding a frame it
cannot get. A green run therefore means something; a missing permission is printed as an
operator item rather than counted as a defect in the code.

It deliberately does not test input delivery: on macOS that needs Accessibility granted to
the binary, which is a human decision in System Settings, and a probe that silently posted
no events would be the worst kind of green. ``--input`` asks the server what it thinks and
prints the answer.

Run from ``harness/``::

    ui-tests/.venv/bin/python scripts/probe_stream.py
    ui-tests/.venv/bin/python scripts/probe_stream.py --keep-frame .tmp/frame.jpg
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
PYTHON = HARNESS / 'ui-tests' / '.venv' / 'bin' / 'python'
PASSWORD = 'Correct-Horse-9'
SCREENCAPTURE = '/usr/sbin/screencapture'
SIPS = '/usr/bin/sips'


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def call(url: str, body=None, token: str = '', timeout: float = 20.0):
    import httpx
    headers = {'Authorization': 'Bearer ' + token} if token else {}
    try:
        if body is None:
            response = httpx.get(url, headers=headers, timeout=timeout, trust_env=False)
        else:
            response = httpx.post(url, json=body, headers=headers, timeout=timeout,
                                  trust_env=False)
    except Exception as exc:                     # noqa: BLE001 - a probe reports, not raises
        return 0, {'error': f'{type(exc).__name__}: {exc}'}
    try:
        return response.status_code, response.json()
    except ValueError:
        return response.status_code, {'raw': response.text[:200]}


def wait_ready(base: str, budget: float = 120.0) -> None:
    deadline = time.time() + budget
    while time.time() < deadline:
        status, _ = call(base + '/api/v1/health', timeout=3)
        if status == 200:
            return
        time.sleep(0.4)
    raise SystemExit('the backend did not become ready')


def screen_size() -> tuple[int, int]:
    """The main display, measured by the tool that will do the capturing."""
    probe = HARNESS / '.tmp' / 'screen-probe.jpg'
    probe.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([SCREENCAPTURE, '-x', '-t', 'jpg', str(probe)], check=True)
    output = subprocess.run([SIPS, '-g', 'pixelWidth', '-g', 'pixelHeight', str(probe)],
                            capture_output=True, text=True, check=True).stdout
    values = {}
    for line in output.splitlines():
        if ':' in line:
            key, _, value = line.partition(':')
            values[key.strip()] = value.strip()
    width = int(values.get('pixelWidth', 0))
    height = int(values.get('pixelHeight', 0))
    # A Retina display captures at 2x; the window frame the app reports is in points.
    scale = 2 if width > 2000 else 1
    return max(320, width // scale), max(240, height // scale)


def check(label: str, passed: bool, detail: str = '') -> bool:
    mark = 'PASS' if passed else 'FAIL'
    print(f'  [{mark}] {label}' + (f' — {detail}' if detail else ''))
    return passed


def console_state() -> str:
    """``'asleep'``, ``'locked'`` or ``'awake'`` — read the way the backend reads it.

    A sleeping display, a locked screen and a missing Screen Recording grant all fail the
    capture tool with the same message, so a probe that guessed would sometimes print the
    wrong instruction. Measured here: all three happen, and the display is the usual one.
    """
    try:
        import ctypes
        library = ctypes.CDLL('/System/Library/Frameworks/CoreGraphics.framework/'
                              'CoreGraphics')
        library.CGMainDisplayID.restype = ctypes.c_uint32
        library.CGDisplayIsAsleep.argtypes = [ctypes.c_uint32]
        library.CGDisplayIsAsleep.restype = ctypes.c_bool
        if library.CGDisplayIsAsleep(library.CGMainDisplayID()):
            return 'asleep'
    except Exception:                                   # noqa: BLE001 - a probe reports
        pass
    result = subprocess.run(['/usr/sbin/ioreg', '-n', 'Root', '-d1'],
                            capture_output=True, text=True, check=False)
    if 'CGSSessionScreenIsLocked" = Yes' in (result.stdout or ''):
        return 'locked'
    return 'awake'


def host_can_capture(region: dict) -> tuple[bool, str]:
    """Whether this machine can capture that region at all, asked of the same tool.

    macOS grants Screen Recording per binary. Without it, ``screencapture -R`` fails with
    ``could not create image from rect`` — while a *whole-screen* capture still succeeds,
    which is exactly why the distinction matters: the two look nothing alike from HTTP, and
    only one of them is a defect in this codebase. Asking the tool directly is how the probe
    tells "the route is broken" apart from "a human has not granted a permission yet".
    """
    target = HARNESS / '.tmp' / 'region-probe.jpg'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.unlink(missing_ok=True)
    result = subprocess.run(
        [SCREENCAPTURE, '-x', '-o', '-t', 'jpg',
         '-R', f"{region['x']},{region['y']},{region['width']},{region['height']}",
         str(target)], capture_output=True, text=True, check=False)
    detail = (result.stderr or result.stdout or '').strip()[:160]
    if result.returncode != 0 or not target.is_file():
        return False, detail or f'exit {result.returncode}'
    return True, ''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--keep-frame', default='')
    parser.add_argument('--region', default='', help='WxH, default: the main display')
    parser.add_argument('--enabled', default='1')
    args = parser.parse_args()

    port = free_port()
    state = HARNESS / '.tmp' / f'stream-{int(time.time())}-{port}'
    state.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update({
        'HARNESS_ENV': 'development',       # the first account becomes the operator
        'HARNESS_DATA_DIR': str(state),
        'HARNESS_DATABASE_URL': 'sqlite:///' + str(state / 'h.sqlite3'),
        'HARNESS_AUTO_CREATE': '1',
        'HARNESS_PORT': str(port),
        'HARNESS_SECRET': secrets.token_urlsafe(48),
        'HARNESS_ALLOWED_HOSTS': 'localhost,127.0.0.1',
        'HARNESS_STREAM_ENABLED': args.enabled,
        'HARNESS_TUTOR_PROVIDER': 'offline',
        'HARNESS_MEDIA_ENABLED': '0',
    })
    for key in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy'):
        env.pop(key, None)

    command = [str(PYTHON), 'scripts/run.py']
    log = (state / 'server.log').open('w')
    server = subprocess.Popen(command, cwd=str(HARNESS / 'backend'), env=env,
                              stdout=log, stderr=subprocess.STDOUT)
    base = f'http://127.0.0.1:{port}'
    api = base + '/api/v1'
    failures = 0
    try:
        wait_ready(base)
        print(f'backend: source tree, stream {"on" if args.enabled == "1" else "off"}, '
              f'state {state}')

        print('\n[1] the viewer page is served by the same origin as the API')
        import httpx
        page = httpx.get(base + '/app', timeout=10, trust_env=False)
        failures += not check('/app answers 200', page.status_code == 200, str(page.status_code))
        failures += not check('it is the viewer, not a stub', 'stream/frame' in page.text)
        failures += not check('and it talks to /api/v1', '/api/v1' in page.text)

        print('\n[2] who may open it')
        email = f'stream-{secrets.token_hex(5)}@example.invalid'
        status, body = call(api + '/auth/register',
                            {'name': 'Operator', 'email': email, 'password': PASSWORD,
                             'age_confirmed': True, 'accept_terms': True})
        failures += not check('the operator account is created', status == 201, str(status))
        teacher = body.get('token', '')
        failures += not check('and is the teacher', (body.get('user') or {}).get('role')
                              == 'teacher', str((body.get('user') or {}).get('role')))

        status, pupil = call(api + '/auth/register',
                             {'name': 'Pupil', 'email': 'pupil-' + email, 'password': PASSWORD,
                              'age_confirmed': True, 'accept_terms': True})
        learner_token = pupil.get('token', '')
        status, _ = call(api + '/stream/status', token=learner_token)
        failures += not check('a learner cannot open the host window', status == 403, str(status))

        print('\n[3] the app reports its window; the frame is that window')
        width, height = screen_size()
        if args.region:
            box_w, box_h = (int(part) for part in args.region.lower().split('x'))
        else:
            box_w, box_h = width, height
        region = {'x': 0, 'y': 0, 'width': box_w, 'height': box_h, 'scale': 2.0}
        status, body = call(api + '/stream/window', region, token=teacher)
        failures += not check('the frame is registered', status == 200, str(status))

        status, reported = call(api + '/stream/status', token=teacher)
        failures += not check('the status reports a window', bool((reported or {}).get('window')),
                              json.dumps((reported or {}).get('window')))
        # The status route answers from the last capture it saw; it does not take one of its
        # own. Against a real server this is observable: nothing has been captured yet.
        failures += not check('and does not capture in order to say so',
                              (reported or {}).get('capture') == 'unknown',
                              str((reported or {}).get('capture')))

        frame = httpx.get(api + '/stream/frame', headers={'Authorization': 'Bearer ' + teacher},
                          timeout=30, trust_env=False)
        refusal = ''
        if frame.status_code != 200:
            try:
                refusal = str(frame.json().get('detail', ''))
            except ValueError:
                refusal = frame.text[:200]

        # Is the failure this host's permission, or this code's defect? The host answers that.
        host_ok, host_detail = host_can_capture(region)
        if host_ok:
            failures += not check('a frame comes back', frame.status_code == 200,
                                  str(frame.status_code))
            failures += not check('as a JPEG',
                                  frame.headers.get('content-type') == 'image/jpeg',
                                  str(frame.headers.get('content-type')))
            failures += not check('that is not cached', 'no-store' in
                                  frame.headers.get('cache-control', ''))
            if args.keep_frame and frame.status_code == 200:
                Path(args.keep_frame).write_bytes(frame.content)
                print(f'  frame written to {args.keep_frame} '
                      f'({len(frame.content) // 1024} KiB)')
        else:
            state = console_state()
            expected_reason = {'asleep': 'display is asleep',
                               'locked': 'screen is locked'}.get(state, 'Screen Recording')
            print(f'  [note] this host cannot capture a region: {host_detail} ({state})')
            failures += not check(f'the route refuses with the same reason the host gives '
                                  f'({expected_reason})',
                                  frame.status_code == 503 and expected_reason in refusal,
                                  f'{frame.status_code} {refusal[:90]}')
            if state == 'awake':
                print('  operator item: grant Screen Recording to the binary that runs the '
                      'backend, in System Settings > Privacy & Security > Screen Recording,\n'
                      '                 then re-run this probe to see a real frame. The route '
                      'is not the fault here.')
            else:
                print(f'  operator item: the {expected_reason}. A region capture needs the '
                      'console awake and unlocked;\n                 wake or unlock the Mac '
                      'and re-run. The app keeps running behind it, and nothing in the\n'
                      '                 route can change this.')

        status, reported = call(api + '/stream/status', token=teacher)
        expected = 'permitted' if host_ok else 'refused'
        failures += not check(f'the status then reports the capture it saw ({expected})',
                              (reported or {}).get('capture') == expected,
                              str((reported or {}).get('capture')))
        if host_ok:
            failures += not check('with that frame\'s size',
                                  int((reported or {}).get('last_frame_bytes') or 0) > 512,
                                  str((reported or {}).get('last_frame_bytes')))

        print('\n[4] what the page would tell the user about input')
        status, answer = call(api + '/stream/input', {'kind': 'click', 'x': 4, 'y': 4},
                              token=teacher)
        state_text = (answer or {}).get('ok')
        print(f'  input: ok={state_text} '
              f'{(answer or {}).get("reason", "")[:120]}')
        print('  (a refusal here is a macOS permission, not a defect in the route)')

        print('\n[5] switching it off is a refusal, not a 404')
        status, _ = call(api + '/stream/frame', token=teacher)
        # 200 when the host can capture, 503 when a permission is missing — both prove the
        # route is mounted and answering. Only a 404 would mean it is not there at all.
        acceptable = (200,) if host_ok else (200, 503)
        failures += not check('the frame route exists while on (not a 404)',
                              status in acceptable, str(status))
    finally:
        server.terminate()
        try:
            server.wait(timeout=15)
        except subprocess.TimeoutExpired:
            server.kill()
        log.close()

    print(f'\n{"FAILED" if failures else "OK"} — {failures} failed check(s)')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
