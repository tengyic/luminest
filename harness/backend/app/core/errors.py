"""One error contract for the whole API.

The shape
---------
A failure the caller is allowed to know about is an :class:`ApplicationError`. It carries
three things and nothing else:

``code``         a stable machine-readable string. Clients branch on this, never on prose.
``http_status``  the status the transport uses. Kept on the class so the mapping from
                 failure to status is one table, not one ``raise HTTPException`` per route.
``message``      a *safe* user-facing sentence. It is rendered to the caller as-is, so an
                 error subclass must never be constructed with an internal detail - that is
                 what the log is for.

Every error body is ``{"detail": <message>, "code": <code>}``. That is the shape the API
already used (``{"detail": ...}`` from ``HTTPException``) with one field added, so a client
that reads ``detail`` keeps working and a client that wants to branch has something to
branch on.

The two handlers
----------------
``ApplicationError``  rendered from its own fields. Nothing is logged: these are expected
                      outcomes, and logging them would drown the real failures.
``Exception``         rendered as a generic 500 with a fixed message and logged *with* the
                      traceback server-side. The traceback must never be in the response.

``install`` is called once, from ``create_app``.

Why a handler for bare ``Exception`` at all
-------------------------------------------
Without one, Starlette's ``ServerErrorMiddleware`` answers an unhandled exception with
``500 text/plain "Internal Server Error"``. That is not a leak - the traceback stays on the
server - but it does contradict the boundary in ``main.boundaries`` that states "the API
sends JSON and only JSON": the one response a client is least able to parse was the only
one that was not JSON. Registering ``Exception`` moves that path inside the application, so
it is JSON and the log line is written deliberately rather than by the ASGI server's
default handler.

Precisely where each branch runs, because it decides which headers the caller sees:
``ApplicationError`` is resolved by Starlette's ``ExceptionMiddleware``, *inside*
``main.boundaries``, so the response comes back through the middleware and carries
``Cache-Control: no-store`` and ``X-Content-Type-Options: nosniff``. A bare ``Exception``
is resolved by ``ServerErrorMiddleware``, which sits *outside* every user middleware - the
response is JSON now, but it still does not carry those two headers, exactly as before.
Making it carry them would mean catching ``Exception`` inside ``boundaries``, which is a
different, larger change; this wave deliberately does not make it.

Note that Starlette's ``ExceptionMiddleware`` resolves the handler by walking the MRO, so
the more specific registrations keep winning: ``HTTPException`` and
``RequestValidationError`` (FastAPI) and ``SQLAlchemyError`` (``main.create_app``) are all
matched before ``Exception``. Registering the base class changes only the paths that had no
handler.

Existing exception classes that should subclass the base
--------------------------------------------------------
Not done in this wave: each lives in a module this change does not own, and a relocation
commit must not also re-parent somebody else's exception. The intended adopters, in the
order they are worth doing:

===============================  ==========================  =====================
class                            module                      suggested base
===============================  ==========================  =====================
``BackupError``                  ``database_backup``          ``UnavailableError``
``BackupVerificationError``      ``database_backup``          ``UnavailableError``
``BackupBusyError``              ``database_backup``          ``ConflictError``
``BackupEncryptionError``        ``database_backup``          ``InternalError``
``BackupSourceError``            ``database_backup``          ``UnavailableError``
``ErasureLedgerUnreadable``      ``account_erasure``          ``InternalError``
``IntakeRefused``/``BuildRefused`` ``course_builder``         ``InvalidInputError``
``SourceRefused``                ``source_extension``         ``InvalidInputError``
``ToolRefused``/``SandboxRefused`` ``harness.toolbox``/``.sandbox`` ``ForbiddenError``
``DispatchFull``                 ``harness.ta``               ``RateLimitedError``
``VoiceError``                   ``harness.voice``            ``UnavailableError``
``StreamRefused``                ``harness.screen``           ``ForbiddenError``
``UnknownCourse``/``UnknownConcept`` ``courses``/``procedure_service`` ``NotFoundError``
``DeckError``/``DiagramError``   ``deck``/``harness.diagram`` ``InvalidInputError``
===============================  ==========================  =====================

The mapping is a suggestion, not a contract: what matters is that a *route* that catches
one of these raises the base class instead of inventing a status code.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from starlette.requests import Request
from starlette.responses import JSONResponse

log = logging.getLogger('luminfest.errors')


class ApplicationError(Exception):
    """A failure that is part of the API contract, not an incident."""

    code = 'internal_error'
    http_status = 500
    default_message = 'The request could not be completed.'

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.default_message
        super().__init__(self.message)

    def body(self) -> dict:
        return {'detail': self.message, 'code': self.code}


class InvalidInputError(ApplicationError):
    """The request is well-formed but cannot be acted on as sent."""

    code = 'invalid_input'
    http_status = 422
    default_message = 'The request could not be understood.'


class NotFoundError(ApplicationError):
    """The thing does not exist, or does not exist *for this account*.

    The two are the same answer on purpose: a 403 on someone else's record confirms that
    the record exists.
    """

    code = 'not_found'
    http_status = 404
    default_message = 'No such resource.'


class ForbiddenError(ApplicationError):
    """The caller is known and is not allowed to do this."""

    code = 'forbidden'
    http_status = 403
    default_message = 'This account may not perform that action.'


class ConflictError(ApplicationError):
    """The request collides with the current state - busy, already exists, stale."""

    code = 'conflict'
    http_status = 409
    default_message = 'The request conflicts with the current state.'


class RateLimitedError(ApplicationError):
    """A quota or a concurrency ceiling was reached; retrying later can succeed."""

    code = 'rate_limited'
    http_status = 429
    default_message = 'Too many requests. Try again shortly.'


class UnavailableError(ApplicationError):
    """A dependency the request needs is not usable right now."""

    code = 'unavailable'
    http_status = 503
    default_message = 'A required service is unavailable; no successful write is reported.'


class InternalError(ApplicationError):
    """A failure we know about but must not describe to the caller."""

    code = 'internal_error'
    http_status = 500
    default_message = 'The request could not be completed.'


async def _application_error(request: Request, exc: ApplicationError) -> JSONResponse:
    return JSONResponse(exc.body(), status_code=exc.http_status)


async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
    log.exception('unhandled %s on %s %s', type(exc).__name__, request.method, request.url.path)
    return JSONResponse(
        {'detail': 'The request could not be completed.', 'code': 'internal_error'},
        status_code=500,
    )


def install(app: FastAPI) -> None:
    """Register the error contract on ``app``.

    Two registrations, one call site, so ``create_app`` gains a single line. Order does not
    matter - Starlette resolves by exception MRO - but specificity does, which is why the
    base ``Exception`` handler is listed last here for the reader.
    """
    app.add_exception_handler(ApplicationError, _application_error)
    app.add_exception_handler(Exception, _unexpected)
