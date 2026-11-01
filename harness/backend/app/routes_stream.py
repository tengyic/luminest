"""HTTP surface for presenting the app's own window in a browser: ``/api/v1/stream``.

The client is SwiftUI, so there is no HTML frontend to serve and no second frontend to
build: the page at ``/app`` shows the app itself, one JPEG at a time, and posts the pointer
and keyboard back. Same backend, same database, same lesson in progress — the browser is a
window onto the running app, not a copy of it.

Four routes, each one thin:

* ``GET  /api/v1/stream/status``   - what is and is not permitted, in words
* ``GET  /api/v1/stream/frame``    - one JPEG of the app's window
* ``POST /api/v1/stream/window``   - the app reporting its own frame
* ``POST /api/v1/stream/input``    - one click, keystroke or typed string
* ``POST /api/v1/stream/enable``   - the switch itself, on a single-user instance

**Teacher-only, and that is not a formality.** This is the host's screen. On a shared
deployment "the host's screen" is every learner's data, so the role is read from the
authenticated account and a learner token is refused with 403 — the same gate the other
operator tools use, for the same reason.

**Off by default.** ``HARNESS_STREAM_ENABLED`` is the switch. When it is off, ``/status``
says so and ``/frame`` refuses with 503 and the reason; nothing is captured.

**Who may throw the switch.** On a *hosted* instance it belongs to the operator, so a
teacher cannot flip it: the environment check in :func:`set_stream` refuses anything that
is not a local single-user instance. On the desktop bundle the person at the Mac *is* the
operator, and they have already said yes by turning on a switch in Settings — demanding
that they also quit and relaunch the app was the reason that switch looked broken. A
runtime flip is still the person choosing, which is the property the flag exists to keep.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from .harness import screen
from .resources import resource_dir

#: The same bearer dependency every other feature router uses. Imported, not copied: a
#: second auth implementation is a second place for it to drift.
from .routes_supervision import authenticated

router = APIRouter()

API = '/api/v1/stream'

#: The page itself, served from ``web/`` alongside the workbench and the playground so the
#: frozen bundle finds it in the one directory ``--add-data`` writes.
WEB_DIR = resource_dir('web')


@router.get('/app', include_in_schema=False)
def app_page():
    """The viewer page. Unauthenticated like the other shells: it holds no data, and every
    request it makes carries the operator's own token."""
    page = WEB_DIR / 'app.html'
    if not page.exists():
        raise HTTPException(404, 'Viewer page not built; expected harness/web/app.html')
    return FileResponse(page, media_type='text/html; charset=utf-8')

#: A frame is the app's window at screen resolution. Above this the JPEG is bigger than the
#: screen it came from, which means the region is wrong rather than the window large.
MAX_FRAME_SIDE = 6000


class WindowReport(BaseModel):
    """What the app reports about its own window, in points, origin top-left."""

    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    scale: float = 2.0


class InputEvent(BaseModel):
    """One pointer or keyboard event, in window-local coordinates."""

    kind: str
    x: int = 0
    y: int = 0
    code: int = 0
    text: str = ''
    dy: int = 0


def _operator(user) -> None:
    if getattr(user, 'role', 'learner') != 'teacher':
        raise HTTPException(403, 'Streaming the host window is a teacher action. This '
                                 'account is not a teacher.')


#: Environments where the person at the Mac and the operator are the same person, so the
#: switch in Settings is theirs to throw. Everywhere else ``HARNESS_STREAM_ENABLED`` is an
#: operator policy and a teacher may not overrule it from the app.
LOCAL_ENVIRONMENTS = frozenset({'desktop', 'development', 'test'})


class StreamSwitch(BaseModel):
    """The switch, as Settings sends it."""

    enabled: bool


@router.post(API + '/enable')
def set_stream(body: StreamSwitch, request: Request,
               session=Depends(authenticated)) -> dict[str, Any]:
    """Turn the switch on or off on the *running* instance.

    ``HARNESS_STREAM_ENABLED`` is read once, when the process starts, which meant a person
    who turned the switch on in Settings got a page that said "switched off" until they quit
    and relaunched the whole app. That is not a consent story, it is a broken button.

    The setting is replaced on ``app.state`` rather than mutated, because ``Settings`` is
    frozen. Every streaming route reads ``request.app.state.settings`` per request — none of
    them closed over the object at import — so the new value is what the next ``/frame``
    sees.
    """
    _db, user = session
    _operator(user)
    settings = request.app.state.settings
    if getattr(settings, 'environment', '') not in LOCAL_ENVIRONMENTS:
        raise HTTPException(
            403, 'On this deployment the streaming switch belongs to the operator '
                 '(HARNESS_STREAM_ENABLED), not to an account in the app.')
    request.app.state.settings = dataclasses.replace(
        settings, stream_enabled=bool(body.enabled))
    return screen.status(request.app.state.settings)


@router.get(API + '/status')
def stream_status(request: Request, session=Depends(authenticated)) -> dict[str, Any]:
    """Everything the page needs in order to explain itself instead of showing a blank box."""
    _db, user = session
    _operator(user)
    return screen.status(request.app.state.settings)


@router.post(API + '/window')
def report_window(body: WindowReport, request: Request,
                  session=Depends(authenticated)) -> dict[str, Any]:
    """The app reports its own frame, because only the app knows it.

    The alternative is asking the window server, which needs Accessibility before it will
    answer — the same permission input needs, and one the capture path deliberately does
    not depend on. The app already knows its frame; asking it is cheaper and needs nothing.
    """
    _db, user = session
    _operator(user)
    settings = request.app.state.settings
    if not getattr(settings, 'stream_enabled', False):
        raise HTTPException(503, 'Streaming is switched off on this instance '
                                 '(HARNESS_STREAM_ENABLED).')
    if not (0 < body.width <= MAX_FRAME_SIDE and 0 < body.height <= MAX_FRAME_SIDE):
        raise HTTPException(422, 'The reported window has no usable size.')
    return {'ok': True, 'window': screen.save_region(settings, body.model_dump())}


@router.get(API + '/frame')
def stream_frame(request: Request, session=Depends(authenticated)) -> Response:
    """One JPEG. Captured on demand, held in memory for the length of this response only."""
    _db, user = session
    _operator(user)
    settings = request.app.state.settings
    try:
        data = screen.capture(settings)
    except screen.StreamRefused as refused:
        raise HTTPException(503, str(refused)) from refused
    return Response(content=data, media_type='image/jpeg',
                    headers={'Cache-Control': 'no-store, no-cache, must-revalidate',
                             'Pragma': 'no-cache'})


@router.post(API + '/input')
def stream_input(body: InputEvent, request: Request,
                 session=Depends(authenticated)) -> dict[str, Any]:
    """Deliver one event. A refusal is a 200 with ``ok: false`` and the reason, because a
    missing permission is a state the page displays, not an error it retries."""
    _db, user = session
    _operator(user)
    return screen.send_input(request.app.state.settings, body.model_dump())
