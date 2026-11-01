"""Put the running app's own window in a browser tab.

The client is SwiftUI — 36 files, no HTML frontend — so "serve the app's frontend to the
web" has no file to serve. The only way to present the *same* app, against the *same*
backend, with the *same* state, in a browser is to present the window itself: capture its
pixels, send them, and deliver the pointer and the keyboard back. Everything else is
reused unchanged, which is the point — there is no second frontend to drift.

That makes this module a remote-desktop bridge, and it is treated as one:

* **Off by default** (``HARNESS_STREAM_ENABLED``), like every other capability that reaches
  outside the process. A route that is off refuses with a named reason rather than 404.
* **The window, not the desktop.** The app reports its own frame; the capture is cropped to
  it. A browser therefore sees the app and nothing else — no mail window behind it.
* **Teacher-gated.** This is the host's screen. A learner account cannot open it, on any
  deployment, because on a shared server "the host's screen" is everybody's screen.
* **Every missing macOS permission is a named refusal, never a black rectangle.** Screen
  Recording and Accessibility are granted per binary, by a human, in System Settings; the
  status route reports which one is missing and the page shows it.

What this module does not do: record, store, or transmit a frame anywhere except to the
browser that asked for it. Frames are captured on demand, held in memory for the length of
one response, and never written to disk.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from collections import deque
from pathlib import Path
from typing import Any, Mapping

#: The system capture tool. Absolute, because a bundled app inherits a PATH that does not
#: necessarily contain ``/usr/sbin``.
SCREENCAPTURE = '/usr/sbin/screencapture'

#: ``osascript`` is how input reaches the app: System Events posts the events, so the
#: permission that has to be granted is the one macOS already knows how to ask for.
OSASCRIPT = '/usr/bin/osascript'

#: ``ioreg`` is how the console's lock state is read, and only on a capture that already
#: failed: a locked screen and a missing Screen Recording grant produce the *same* tool
#: error (``could not create image from rect``), so without asking this the refusal would
#: tell the operator to grant a permission they already granted.
IOREG = '/usr/sbin/ioreg'

#: ``sips`` re-encodes the capture. ``screencapture -t jpg`` writes at close to lossless:
#: measured 764 KiB for one 1470x956 window in 147 ms. Re-encoding is the difference between
#: a stream that works over Wi-Fi and one that does not, and the lever is the *resize*, not
#: the quality — the page scales the frame to its own viewport anyway. Measured on the same
#: window: 1600 px at 60% = 218 KiB in 232 ms, 1280 px at 55% = 142 KiB in 202 ms, 1100 px at
#: 50% = 98 KiB in 201 ms. The middle one is the default: it is the smallest frame that keeps
#: body text crisp when the pane is a laptop screen.
SIPS = '/usr/bin/sips'

#: The long edge a frame is resized to. Chosen against the thing it is shown in: a browser
#: pane on a laptop, not a 4K display, and a Retina capture is twice the size of the window.
MAX_FRAME_EDGE = 1280

#: JPEG quality for the re-encode. See the measurements above.
FRAME_QUALITY = 55

#: A click, a keystroke and a scroll each start a process, so input is bounded rather than
#: unbounded: a held key on a stalled link must not become a process per repeat.
MAX_EVENTS_PER_SECOND = 25

#: Timestamps of the events accepted in the last second. Process-local, which is the right
#: scope: the limit exists to protect the host from one browser tab, and the desktop bundle
#: runs one backend process.
_recent_events: deque[float] = deque(maxlen=MAX_EVENTS_PER_SECOND * 4)


def _too_fast() -> bool:
    now = time.monotonic()
    while _recent_events and now - _recent_events[0] > 1.0:
        _recent_events.popleft()
    if len(_recent_events) >= MAX_EVENTS_PER_SECOND:
        return True
    _recent_events.append(now)
    return False

#: The smallest region worth streaming. Below this the page is unusable and the region is
#: almost certainly a bad report rather than a small window.
MIN_SIDE = 120


#: The result of the last capture attempt. ``status`` reads it instead of capturing again:
#: the page polls the status every 15 seconds, and a status call that also captured would
#: double the work of a stream that is already the most expensive thing on the host.
_last_capture: dict[str, Any] = {'at': 0.0, 'ok': False, 'detail': '', 'bytes': 0}

#: How long a recorded outcome still answers "is capture permitted?". The frame loop runs
#: several times a second, so a live stream always has a fresh answer here; an old one means
#: nobody has asked for a frame, and guessing on the page's behalf would be a claim the
#: server cannot back. Long enough to survive a paused tab, short enough that a permission
#: granted in System Settings shows up on the next poll rather than the one after.
_CAPTURE_FRESH_SECONDS = 30.0


def _note_capture(ok: bool, detail: str = '', size: int = 0) -> None:
    """Record one capture outcome for ``status`` to report. Never raises."""
    _last_capture.update({'at': time.monotonic(), 'ok': ok, 'detail': detail, 'bytes': size})


class StreamRefused(RuntimeError):
    """A named reason the stream cannot serve this request."""


def region_path(settings) -> Path:
    return Path(settings.data_dir) / 'stream' / 'window.json'


def save_region(settings, region: Mapping[str, Any]) -> dict[str, Any]:
    """Record the frame the app reported. Clamped, because a stale report is a bad region."""
    x = int(region.get('x') or 0)
    y = int(region.get('y') or 0)
    width = max(MIN_SIDE, int(region.get('width') or 0))
    height = max(MIN_SIDE, int(region.get('height') or 0))
    frame = {'x': max(0, x), 'y': max(0, y), 'width': width, 'height': height,
             'scale': float(region.get('scale') or 2.0)}
    path = region_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(frame), encoding='utf-8')
    return frame


def load_region(settings) -> dict[str, Any] | None:
    path = region_path(settings)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding='utf-8'))
    except (ValueError, OSError):
        return None
    if not isinstance(raw, Mapping):
        return None
    return {'x': int(raw.get('x') or 0), 'y': int(raw.get('y') or 0),
            'width': max(MIN_SIDE, int(raw.get('width') or 0)),
            'height': max(MIN_SIDE, int(raw.get('height') or 0)),
            'scale': float(raw.get('scale') or 2.0)}


def _run(command: list[str], timeout: float = 10.0) -> tuple[int, str]:
    """Run a tool and return (returncode, combined output). Never raises for a refusal."""
    try:
        completed = subprocess.run(command, capture_output=True, timeout=timeout,
                                   check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, f'{type(exc).__name__}: {exc}'
    output = (completed.stdout or b'') + (completed.stderr or b'')
    return completed.returncode, output.decode('utf-8', 'replace').strip()


def _display_asleep() -> bool:
    """Whether the main display is asleep, asked of CoreGraphics directly.

    This is the commonest reason a stream stops on a Mac nobody is touching, and it is
    invisible from the tool: ``screencapture -R`` fails exactly as it does without Screen
    Recording, while a whole-screen capture still *succeeds* — returning a blank frame.
    Measured here: 773 KiB while the display was awake, 93 KiB while it was asleep, and the
    region call failed in both the asleep and the locked case. ``CGDisplayIsAsleep`` is a
    public API, so no permission and no subprocess is involved.
    """
    try:
        import ctypes
        library = ctypes.CDLL('/System/Library/Frameworks/CoreGraphics.framework/'
                              'CoreGraphics')
        library.CGMainDisplayID.restype = ctypes.c_uint32
        library.CGDisplayIsAsleep.argtypes = [ctypes.c_uint32]
        library.CGDisplayIsAsleep.restype = ctypes.c_bool
        return bool(library.CGDisplayIsAsleep(library.CGMainDisplayID()))
    except Exception:                                   # noqa: BLE001 - never fatal
        return False


def _console_locked() -> bool:
    """Whether the console session is locked. Asked only when a capture has already failed."""
    code, output = _run([IOREG, '-n', 'Root', '-d1'], timeout=5.0)
    return code == 0 and 'CGSSessionScreenIsLocked" = Yes' in output


def console_state() -> str:
    """``'asleep'``, ``'locked'`` or ``'awake'`` — why a capture would fail, before it does.

    A sleeping display and a locked screen fail the capture tool with the *same* message as a
    missing Screen Recording grant, and only one of the three is the operator's System
    Settings. Reporting the wrong one sends someone to grant a permission they already have,
    which is worse than saying nothing.
    """
    if _display_asleep():
        return 'asleep'
    if _console_locked():
        return 'locked'
    return 'awake'


def capture(settings, *, quality: int = FRAME_QUALITY) -> bytes:
    """One JPEG of the app's window. Raises :class:`StreamRefused` with the reason.

    A thin wrapper on purpose: it records the outcome so :func:`status` can report it, and
    doing that here means none of the refusal paths below has to remember to say so.
    """
    try:
        data = _capture(settings, quality=quality)
    except StreamRefused as refused:
        _note_capture(False, str(refused))
        raise
    _note_capture(True, size=len(data))
    return data


def _capture(settings, *, quality: int = FRAME_QUALITY) -> bytes:
    """The capture itself: crop to the reported window, then re-encode small enough to send."""
    if not getattr(settings, 'stream_enabled', False):
        raise StreamRefused(
            'Streaming the app window is switched off on this instance '
            '(HARNESS_STREAM_ENABLED). Nothing was captured.')
    if not os.path.exists(SCREENCAPTURE):
        raise StreamRefused(f'{SCREENCAPTURE} is not present on this system.')
    region = load_region(settings)
    if region is None:
        raise StreamRefused(
            'The app has not reported its window yet. Streaming presents the app\'s own '
            'window, so the app has to be running; it reports its frame on launch.')
    with tempfile.TemporaryDirectory(prefix='frame-') as directory:
        target = Path(directory) / 'frame.jpg'
        code, output = _run([SCREENCAPTURE, '-x', '-o', '-t', 'jpg',
                             '-R', f"{region['x']},{region['y']},"
                                   f"{region['width']},{region['height']}",
                             str(target)])
        if code != 0 or not target.is_file():
            state = console_state()
            if state == 'asleep':
                raise StreamRefused(
                    'The display is asleep, and macOS does not hand a sleeping display to a '
                    'region capture. Wake it and the stream resumes on the next frame — the '
                    'app keeps running behind a sleeping display. Nothing was captured. '
                    f'({output[:120]})')
            if state == 'locked':
                raise StreamRefused(
                    'The screen is locked, and macOS does not hand a locked console to a '
                    'region capture. Unlock the Mac and the stream resumes on the next '
                    f'frame; the app keeps running behind the lock screen. ({output[:120]})')
            raise StreamRefused(
                'The screen could not be captured. macOS gives this same error when this app '
                'has not been granted Screen Recording (System Settings > Privacy & Security '
                '> Screen Recording), and it also gives it while the display is between '
                'sleep states — so check the grant, and try again with the Mac awake and '
                f'unlocked. ({output[:200]})')
        # Re-encode to a second file: ``sips`` treats "re-encode to the format it already is"
        # as a no-op when the output path is the input path, which silently kept the 700 KiB
        # frame. A failure here is not fatal — the original capture is a valid JPEG, just a
        # large one, and a large frame beats a blank one.
        #
        # Whether to resize is arithmetic on what the app reported, not a second ``sips``
        # call to measure the file: the window is ``width`` points wide at ``scale``, and
        # ``-Z`` upscales, so a small window must not be sent through it.
        scale = float(region.get('scale') or 2.0)
        resample = max(region['width'] * scale, region['height'] * scale) > MAX_FRAME_EDGE
        smaller = Path(directory) / 'small.jpg'
        command = [SIPS, '-s', 'formatOptions', str(int(quality)), '-s', 'format', 'jpeg']
        if resample:
            command += ['-Z', str(MAX_FRAME_EDGE)]
        command += [str(target), '--out', str(smaller)]
        code, _ = _run(command)
        data = smaller.read_bytes() if code == 0 and smaller.is_file() else target.read_bytes()
    if len(data) < 512:
        raise StreamRefused(
            'The capture came back empty. On macOS that is what a missing Screen '
            'Recording permission looks like from the outside, so it is reported as a '
            'permission problem rather than as an empty window.')
    return data


# ------------------------------------------------------------------------------- input


def _input_permitted() -> tuple[bool, str]:
    """Whether System Events will accept events, asked without sending any."""
    code, output = _run([OSASCRIPT, '-e',
                         'tell application "System Events" to get name of first process'])
    if code == 0:
        return True, ''
    lowered = output.casefold()
    if '-10004' in output or 'not allowed assistive access' in lowered or \
            'assistive' in lowered or '权限' in output:
        return False, (
            'Input cannot be delivered: macOS has not granted this app Accessibility, '
            'which is what System Events needs in order to click and type. System '
            'Settings > Privacy & Security > Accessibility, then add this app.')
    return False, f'Input is unavailable: {output[:200] or "osascript failed"}'


def _click(region: Mapping[str, Any], x: int, y: int) -> None:
    screen_x = int(region['x']) + int(x)
    screen_y = int(region['y']) + int(y)
    code, output = _run([OSASCRIPT, '-e',
                         f'tell application "System Events" to click at '
                         f'{{{screen_x}, {screen_y}}}'])
    if code != 0:
        raise StreamRefused(output[:300] or 'the click was refused')


def _key(code_number: int, *, down: bool = True) -> None:
    # System Events has no key-up/down pair; ``key code`` is a complete press. A held key
    # therefore repeats, which is what a browser sends when a key repeats anyway.
    code, output = _run([OSASCRIPT, '-e',
                         f'tell application "System Events" to key code {int(code_number)}'])
    if code != 0:
        raise StreamRefused(output[:300] or 'the key was refused')


def _type(text: str) -> None:
    escaped = text.replace('\\', '\\\\').replace('"', '\\"')
    code, output = _run([OSASCRIPT, '-e',
                         f'tell application "System Events" to keystroke "{escaped}"'])
    if code != 0:
        raise StreamRefused(output[:300] or 'the text was refused')


def send_input(settings, event: Mapping[str, Any]) -> dict[str, Any]:
    """Deliver one pointer or keyboard event to the app. Returns what happened."""
    if not getattr(settings, 'stream_enabled', False):
        return {'ok': False, 'reason': 'Streaming is switched off on this instance.'}
    region = load_region(settings)
    if region is None:
        return {'ok': False, 'reason': 'The app has not reported its window yet.'}
    permitted, why = _input_permitted()
    if not permitted:
        return {'ok': False, 'reason': why}
    if _too_fast():
        return {'ok': False,
                'reason': f'More than {MAX_EVENTS_PER_SECOND} events in a second; the rest '
                          'of this burst was dropped rather than turned into processes.'}

    kind = str(event.get('kind') or '')
    try:
        if kind == 'click':
            _click(region, int(event.get('x') or 0), int(event.get('y') or 0))
        elif kind == 'key':
            _key(int(event.get('code') or 0))
        elif kind == 'type':
            text = str(event.get('text') or '')[:200]
            if not text:
                return {'ok': False, 'reason': 'No text was supplied.'}
            _type(text)
        elif kind == 'scroll':
            # System Events cannot scroll a point, so a wheel becomes page keys. It is an
            # approximation and it is named as one rather than silently ignored.
            _key(121 if int(event.get('dy') or 0) > 0 else 116)
        else:
            return {'ok': False, 'reason': f'Unknown event kind: {kind!r}'}
    except StreamRefused as refused:
        return {'ok': False, 'reason': str(refused)}
    except (TypeError, ValueError):
        return {'ok': False, 'reason': 'The event was malformed.'}
    return {'ok': True, 'kind': kind}


# ------------------------------------------------------------------------------ status


def status(settings) -> dict[str, Any]:
    """What the page needs in order to say what is wrong instead of showing a blank box."""
    enabled = bool(getattr(settings, 'stream_enabled', False))
    region = load_region(settings) if enabled else None
    report: dict[str, Any] = {
        'enabled': enabled,
        'window': region,
        'capture_tool': os.path.exists(SCREENCAPTURE),
        'input': 'unknown',
        'permissions': [],
        'guarantees': [
            'The stream is the app\'s own window, cropped to the frame the app reports.',
            'Frames are captured on demand and never written to disk or kept.',
            'Nothing is sent anywhere except to the browser session that asked for it.',
        ],
    }
    if not enabled:
        report['reason'] = ('Streaming is switched off on this instance '
                            '(HARNESS_STREAM_ENABLED). Nothing is captured.')
        return report
    if region is None:
        report['reason'] = ('The app has not reported its window yet; open the app on the '
                            'host machine and its frame will be registered.')
    permitted, why = _input_permitted()
    report['input'] = 'permitted' if permitted else 'refused'
    if not permitted:
        report['permissions'].append(why)
    # Why a capture would fail *before* it does. A sleeping display and a locked screen
    # produce the same tool error as a missing grant, so the page can say which of the three
    # it is instead of pointing at System Settings for a Mac that is simply asleep.
    report['console'] = console_state()
    # Capture is *reported*, not repeated. The page asks for this every 15 seconds and the
    # frame loop already captures several times a second; capturing here as well would make
    # the cheapest route on the page cost the same as the most expensive one, on a host that
    # is simultaneously rendering the app. So the answer is the last real attempt.
    age = time.monotonic() - float(_last_capture['at'] or 0.0)
    if region is not None and _last_capture['at'] and age <= _CAPTURE_FRESH_SECONDS:
        report['capture'] = 'permitted' if _last_capture['ok'] else 'refused'
        report['capture_checked_ago'] = round(age, 1)
        if _last_capture['ok']:
            report['last_frame_bytes'] = int(_last_capture['bytes'])
        else:
            # The reason is kept, but it only belongs under "permissions" when a permission
            # is what is missing — a console that is asleep is not a permission problem.
            report['capture_reason'] = str(_last_capture['detail'])
            if report['console'] == 'awake':
                report['permissions'].append(str(_last_capture['detail']))
    else:
        report['capture'] = 'unknown'
        report.setdefault(
            'reason',
            f'No frame has been requested in the last {int(_CAPTURE_FRESH_SECONDS)} seconds, '
            'so whether capture is permitted is not yet known. The page asks for a frame as '
            'soon as it is open; nothing is captured in order to answer this question.')
    return report
