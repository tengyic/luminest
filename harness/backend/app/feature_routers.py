"""The feature-router modules ``main.create_app`` mounts, named in exactly one place.

Every capability that lives in its own ``routes_*`` module is reached at runtime through
``importlib.import_module('.' + name)``. That indirection is deliberate: a capability can
be added or removed without editing the application module, and a module that cannot be
imported degrades to "that capability is absent" instead of taking the whole API down.

It is also invisible to PyInstaller, which only follows imports it can see statically. The
consequence was a frozen desktop bundle that contained ``app.main`` and **not one** of the
routers it mounts: ``/api/v1/deck``, ``/api/v1/flashcards``, ``/api/v1/my-courses`` and
``/api/v1/images/library`` all answered 404 in the shipped app while the source tree served
them, and the graceful degradation meant nothing failed loudly enough to be noticed.

The list therefore lives here, as plain data, so that three readers share one tuple and
cannot disagree:

* ``main.create_app`` mounts it;
* ``scripts/package.py`` turns it into ``--hidden-import`` arguments, because a dynamic
  import has to be declared to the freezer rather than inferred by it;
* the packaging gate refuses to ship a bundle in which any of them failed to land.

Adding a router means adding one line here - and that line is what puts it in the app.
A module listed here is expected to exist and to ship; a name that does not resolve is a
packaging defect, not a capability that happens to be switched off.
"""

FEATURE_ROUTERS = (
    'routes_deck',
    'routes_flash',
    'routes_create',
    'routes_authoring',
    'routes_media',
    'routes_multimodal',
    'routes_source',
    'playground_routes',
    'routes_procedure',
    'routes_supervision',
    'routes_rewards',
    'routes_ta',
    'routes_stream',
    # Dedicated scratch-board drawing agent. It is intentionally a separate router:
    # the tutor's teacher-gated whiteboard_* tools keep the lesson canvas, while this
    # one owns region=scratch. See app/harness/whiteboard_agent.py.
    'routes_whiteboard_agent',
    # Runtime model configuration. The product requires a language model; this is the
    # surface that lets an operator supply one without editing the environment and
    # restarting. See app/model_config.py and app/routes_model_config.py.
    'routes_model_config',
)

__all__ = ['FEATURE_ROUTERS']
