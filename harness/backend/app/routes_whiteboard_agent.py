"""HTTP surface for the dedicated whiteboard drawing agent.

The tutor's ``whiteboard_*`` tools stay exactly where they are: teacher-gated, driven
by ``agent_loop``, writing ``board-<concept>`` lesson canvases. This router is a
separate capability. It is deliberately NOT teacher-gated - a scratch diagram is a
learner-side action - and it never touches the lesson canvas. That separation is the
point of the request: structured "draw this" objects are handled by a specialised
agent so they cannot conflict with the teacher.

Three endpoints, all cheap to keep in a frozen bundle:

* ``GET  /api/v1/whiteboard-agent/catalog`` - protocol + renderer catalog (also the
  packaging probe: a route that exists proves the module was collected). Public:
  it holds no account data and must answer for a signed-out visitor and for the
  frozen-bundle probe, which sends no bearer token.
* ``GET  /api/v1/whiteboard-agent/boards`` - the caller's scratch boards only.
* ``POST /api/v1/whiteboard-agent/draw``   - one content object -> one board node.

The POST always answers 200 with a status in the body. ``UNRESOLVED`` / ``REFUSED``
are product states, not transport failures: the caller needs the blocking features,
and a 4xx would make a faithful refusal look like a broken connection.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Request

from .harness import board as node_boards
from .harness import whiteboard_agent
from .routes_supervision import authenticated
from .security import require_principal

API = '/api/v1/whiteboard-agent'

#: No router-level auth dependency: it would also cover ``catalog``, which must stay
#: public. The two protected routes therefore declare the resolver *on the route*.
#: ``require_principal`` puts a marked resolver into the dependency graph (the
#: ``test_account_auth_single_source`` gate reads that graph, not the function body),
#: and it runs before ``authenticated``, which is what leaves ``request.state.token``
#: set for the session heartbeat. ``authenticated`` alone is invisible to the graph
#: walk; an optional router-level resolver would instead cache an anonymous principal
#: and break that heartbeat.
_require_principal = require_principal('api', 180)
router = APIRouter()


@router.get(API + '/catalog')
def catalog():
    return whiteboard_agent.catalog_document()


@router.get(API + '/boards', dependencies=[Depends(_require_principal)])
def list_boards(request: Request, auth=Depends(authenticated)):
    """The owner's scratch boards only - never the teacher's ``board-*`` lesson canvases."""
    _db, user = auth
    settings = request.app.state.settings
    boards = node_boards.list_for_owner_prefix(
        settings, str(user.id), prefix=whiteboard_agent.SCRATCH_BOARD_PREFIX)
    return {'boards': boards}


@router.post(API + '/draw', dependencies=[Depends(_require_principal)])
def draw(request: Request, payload: dict = Body(...), auth=Depends(authenticated)):
    _db, user = auth
    settings = request.app.state.settings
    agent = whiteboard_agent.WhiteboardDrawAgent(settings, owner_id=str(user.id))
    return agent.draw(payload)

