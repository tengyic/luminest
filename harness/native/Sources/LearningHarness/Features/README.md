# Features/

One directory per surface the learner can be on. A feature directory holds the views,
the view-local state, and the request shapes that exist *only* for that surface. It may
read from `Shared/`; `Shared/` may never read from here. See ADR-0003 for what that rule
is worth today (nothing is enforced by the compiler — this is one SwiftPM target).

Directories appear here when they receive code, not before. The target layout also names
`Authentication`, `Dashboard`, `Courses`, `Lessons`, `Practice`, `Reviews`, `Projects`,
`Tutor`, `Insights` and `Settings`; those directories do not exist yet because their code
is still in the flat tree (see ADR-0003, "What is still flat and why").

## Board/

The Stage whiteboard: the drawing surface opened from a lesson, and everything that only
exists to serve it.

Belongs here: the editor view and its tool/gesture/diagram state; the AppKit event bridge
that reports pressure and first-responder keys (things SwiftUI on macOS still cannot do);
canvas primitives (eraser mode, viewport transform, clamp helper); the board's own modal
sheets (write-on-board, image insert).

Does not belong here: the board *document* model, its mutation/reconcile/undo engine and
its serialisation — that is `BoardStore` in `Board.swift`, which the tutor, the exporter
and the QA driver also use, and which is therefore not a board-editor concern. Nor the
export compositor (`BoardRenderer`). Nor `BoardTool` / `BoardSelection` / `SnapGuide` /
`BoardGeometry` — those are in `BoardKit.swift` and are shared by the editor and the
renderer.
