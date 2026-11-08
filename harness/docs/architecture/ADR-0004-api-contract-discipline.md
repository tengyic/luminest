# ADR-0004 — API contract discipline

- **Status:** accepted; migration incomplete (see "What is true today")
- **Date:** 2026-11-08
- **Scope:** the FastAPI application in `backend/app/`
- **Deciders:** architecture governance pass
- **Instrument:** `backend/scripts/api_surface.py` (exists; see "Enforcement")

## What "explicit contract" means in this application

A route has an explicit contract when all four of these are true:

1. **The request body is a declared model.** A pydantic class names every field, its type
   and its bounds; FastAPI rejects the request before the handler runs. Reading
   `await request.json()` and validating by hand is not a contract.
2. **The response is a declared model.** `response_model=` on the decorator (or a return
   annotation FastAPI can infer) names the shape. A bare `dict` is not a shape; it is a
   promise that the handler will remember every key on every path.
3. **The URL is under the version prefix.** `API = '/api/v1'` at
   `backend/app/main.py:69`, and new route modules declare the same prefix once (for
   example `PREFIX = '/api/v1'` at `backend/app/api/v1/account.py:49`).
4. **Errors use the one envelope** described in
   [ADR-0001](ADR-0001-architecture-principles.md#3-errors-have-one-shape):
   `{"detail": <string>}`.

The application does not publish an OpenAPI document: `docs_url=None`, `redoc_url=None`,
`openapi_url=None` at `backend/app/main.py:763`. So the contract cannot be discovered from a
running server. That is precisely why the declaration has to be in the code, and why
`scripts/api_surface.py` exists: it is the only machine-readable description of the surface.

## What is true today

Measured 2026-11-08 on the tree as it stood after the account family moved to
`backend/app/api/v1/account.py`.

| Property | Value | How measured |
| --- | --- | --- |
| Route registrations | **226** | `backend/scripts/api_surface.py` (`route_count`); cross-checked by `grep -rE '@(app\|router\|api)\.(get\|post\|put\|patch\|delete)\('` over the 16 route modules |
| Routes declaring a response model | **4 / 226** | `api_surface.py`; all four are `builtins.dict`, inferred from `-> dict[str, Any]` on the stream routes |
| `response_model=` written by hand | **0** | `grep -rE 'response_model' backend/app/` |
| Handler functions returning a dict literal | **134** statements | `grep -rE '^[[:space:]]+return \{'` over the route modules |
| Routes declaring at least one body model | **85 / 226** | `api_surface.py` (`body_models` non-empty) |
| Routes declaring at least one dependency | **212 / 226** | `api_surface.py` (`dependencies` non-empty) |
| Handler functions taking `Request` | **88** | AST pass over the route modules |
| Pydantic classes in the shared schema module | **34** | `grep -cE '^class ' backend/app/schemas.py` |
| Pydantic classes declared inside route modules | **29** | `grep -rE 'class .*\((BaseModel\|Input)\)'` over `routes_*.py`, `playground_routes.py`, `web_routes.py` |
| Error sites | 236 `HTTPException`; 7 `JSONResponse({'detail': ...})` | `grep -rc 'HTTPException('`; `grep -rn "JSONResponse({'detail'"` |

Two facts follow, and they are the reason this ADR exists:

- **The response side is almost entirely undeclared.** 222 of 226 routes answer with a
  shape only the handler knows. The four that declare one declare `dict` — which tells a
  reader nothing.
- **The request side is half declared and split in two.** 85 routes have a model; the
  models live in two places: the shared `backend/app/schemas.py` (used by `main.py` and
  `api/v1/account.py`) and 29 classes declared inside the feature-router modules
  (`routes_flash.py:51` `CardInput`, `routes_deck.py`, `playground_routes.py:126`
  `GuidedCycle`, and so on). A client cannot import one schema module because there isn't
  one.

The stream routes are the one place the declaration is actively misleading:
`backend/app/routes_stream.py:113`, `:139`, `:147`, `:182` annotate `-> dict[str, Any]`,
so FastAPI records `builtins.dict` as the response model. That is worse than no annotation:
a generated client would see "object with no properties" and a reviewer would see "modelled".

## The rule going forward

1. **New route → request model and response model.** Request bodies are a pydantic class,
   defined in `backend/app/schemas.py` if shared or beside the route if it is genuinely
   private to that family. Responses declare `response_model=<Model>`; if the handler builds
   a dict, the model is the contract and the dict is an implementation detail.
2. **No new `Response`, `JSONResponse` or bare-dict returns.** The existing 134 dict
   returns and 35 `Response`/`JSONResponse` sites are legacy. A new one is a review
   rejection. Where the response is not JSON (a `.pptx`, an SVG, a streamed frame), use the
   declared media type and say so in the decorator, as `routes_deck.py` and
   `web_routes.py:366` already do.
3. **Versioned prefix, one constant.** A new module declares `PREFIX = '/api/v1'` once and
   builds every path from it. Changing the version is then one edit per module, and the
   surface instrument makes the change visible.
4. **One schema owner per family.** Do not add a fifth place for request models. Moving the
   29 route-local classes into `schemas.py` (or into a per-family `schemas` module) is the
   intended direction, but it is a behaviour-neutral refactor and must be proved with
   `api_surface.py --compare`, not done as a side effect of a feature change.

## Enforcement

`backend/scripts/api_surface.py` is the instrument. It builds the app with a throwaway data
directory, flattens this FastAPI build's lazy `_IncludedRouter` objects, and writes a sorted
description of every route: method, served path, endpoint name, `response_model`,
`body_models`, `dependencies`, `status_codes`, plus `route_count` and
`registration_order`. Two runs on the same tree are byte-identical, so `--compare` is an
equality test rather than a diff of formatting noise.

A baseline is checked in at `backend/tests/fixtures/api_surface.json` (`route_count: 226`).
The guard added in this pass asserts that the number quoted in this ADR is the number the
application actually serves
(`backend/tests/test_architecture_guards.py::test_adr_route_count_matches_the_running_app`).
If a route is added or removed, that test fails until this ADR is updated — which is the
point: the number is a promise, not a snapshot.

What the instrument cannot enforce is the *quality* of a contract. It can see that
`response_model` is `builtins.dict`; it cannot see that a model has one field named `data`.
The 4/226 number is the honest starting point, and the direction of travel is that it rises.

## Consequences

- Adding a route without a response model is now a documented violation, not an oversight.
  It is not a test failure, because 222 existing routes would fail the same test; the rule
  is enforced on new code by review and made visible by `api_surface.py`.
- Relocating routes (as happened to the account family in this pass) is safe and provable:
  `api_surface.py --compare baseline.json current.json` must report no differences. The
  account move was checked that way; the fixture still reports 226.
- The shared schema module is smaller than it looks. A client that wants typed access has to
  read 29 route-local classes as well as `schemas.py`. That is a known cost of the current
  layout, stated rather than hidden.
