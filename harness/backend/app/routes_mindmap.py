"""HTTP surface for the concept mind map: ``/api/v1/mindmap``.

Mounted by convention - ``main.create_app`` imports this module and calls ``include_router`` -
so the capability can be removed by deleting the file and one line in ``feature_routers``.

Serving contract:

    GET /api/v1/mindmap/course               -> the enrolled course: units and their concepts
    GET /api/v1/mindmap/{concept_id}         -> one concept's tree, as data
    GET /api/v1/mindmap/{concept_id}/html    -> the same tree as one interactive page

Two boundaries, and no others:

* **The tree is the graph's own words.** Every label comes from the curriculum's prerequisite,
  teaching-order and unit edges through :func:`app.figures.concept_map`; nothing is invented
  to make the picture look fuller.
* **A concept that is not in the caller's course is a 404**, never a 403, exactly as the deck
  and flashcard routers do: a 403 would confirm that the concept exists.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from . import courses, figures, mindmap
from .security import require_principal

router = APIRouter(dependencies=[Depends(require_principal('api', 120))])

API = '/api/v1/mindmap'


def current_user(request: Request):
    """The caller, through the one shared account resolver rather than a local copy.

    A router that re-implemented token lookup is how a deleted account kept working, so this
    defers to ``main.resolve_account`` and writes through the same request-scoped session.
    """
    from .main import resolve_account, start_write

    factory = request.app.state.factory
    with factory() as db:
        user = resolve_account(request, db, rate_key='api', limit=120)
        start_write(db)
        db.commit()
        return user


def _graph_and_node(user, concept_id: str):
    from .main import LESSON_TARGETS, course_graph

    graph = course_graph(user)
    node = graph.nodes.get(concept_id)
    if node is None:
        # A lesson id and a graph id name the same idea; both are accepted, as elsewhere.
        target = LESSON_TARGETS.get(concept_id)
        node = graph.nodes.get(target) if target else None
    if node is None:
        raise HTTPException(404, f'Unknown concept {concept_id!r}')
    return graph, node


def _tree(graph, node) -> mindmap.Node:
    payload = figures.concept_map({'id': node.id, 'title': node.title}, graph, {})
    return mindmap.from_payload(payload)


@router.get(API + '/course')
def course_map(user=Depends(current_user)):
    """The whole course as a tree: course, units, and up to five concepts in each."""
    from .main import course_graph

    graph = course_graph(user)
    root = mindmap.course_tree(graph)
    spec = courses.enrolled_for(user)
    root.label = str(getattr(spec, 'title', '') or root.label)
    course_id = str(getattr(spec, 'id', '') or '')
    return JSONResponse({'course_id': course_id, 'tree': mindmap.to_dict(root),
                         'tiers': mindmap.depth_of(root) + 1,
                         'nodes': len(list(mindmap.walk(root)))})


@router.get(API + '/{concept_id}')
def concept_map(concept_id: str, open_depth: int = Query(default=1, ge=0, le=6),
                user=Depends(current_user)):
    """The concept's map as data, for a client that draws it itself."""
    graph, node = _graph_and_node(user, concept_id)
    root = _tree(graph, node)
    return JSONResponse({'concept_id': node.id, 'title': node.title,
                         'tree': mindmap.to_dict(root), 'tiers': mindmap.depth_of(root) + 1,
                         'nodes': len(list(mindmap.walk(root))), 'open_depth': open_depth})


@router.get(API + '/{concept_id}/html', response_class=HTMLResponse)
def concept_map_page(concept_id: str, open_depth: int = Query(default=1, ge=0, le=6),
                     user=Depends(current_user)):
    """One self-contained page: no network, no build step, click a bar to open its branch."""
    graph, node = _graph_and_node(user, concept_id)
    page = mindmap.interactive_page(_tree(graph, node), open_depth=open_depth, title=node.title)
    return HTMLResponse(page, headers={'Cache-Control': 'no-store'})
