"""Cross-cutting concerns that are not features.

``errors``   one error hierarchy and the handler that renders it.
``config``   does not exist on purpose - see the note below.

What belongs here
-----------------
Only things every layer needs and no layer may own: the error contract, the settings
object (today still ``app/config.py``), and - in later waves - the session dependency and
the clock. If a module here imports from ``app.api`` or ``app.services``, the dependency
rule has been broken.

Why there is no ``app/core/config.py``
-------------------------------------
``app/config.py`` is already the single place that reads the environment and validates it
at boot. A second module named ``config`` under this package would be a second answer to
"where do settings come from", and the two would drift. When settings move, ``app/config.py``
moves *here* (one file, one history) rather than being copied; until then this package does
not contain a config module at all, and the absence is deliberate.
"""
