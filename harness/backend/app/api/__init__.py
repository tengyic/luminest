"""The HTTP boundary of the application, split into versioned router packages.

Everything under this package is a *transport* module: it declares paths, validates input
against :mod:`app.schemas`, scopes the call to the authenticated account, and serialises a
result. It is not allowed to hold a domain rule - the rule lives in the domain module, and
a rule that lives in a route is a rule the next route will disagree with.

The package exists so that ``app/main.py`` can go back to being what its name says: the
composition root. ``main.create_app`` builds the settings, the engine and the auth
dependency, then mounts routers. It should not be 4 000 lines of endpoint bodies.

Current contents
----------------
``app.api.v1.account`` - the caller's own consumption and settings
(``GET /api/v1/usage``, ``GET|PATCH /api/v1/preferences``). The first family relocated out
of ``main.py``; the remaining inline families are listed in
``docs/architecture/ADR-0002-backend-boundaries.md`` with the wave that moves each one.
"""
