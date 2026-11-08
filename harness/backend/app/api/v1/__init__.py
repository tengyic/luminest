"""Version 1 of the HTTP surface (``/api/v1``).

One module per cohesive family, one ``APIRouter`` per module. The prefix is declared on
the router rather than spelled into every decorator, so the version segment exists in one
place per module and a future ``v2`` can mount alongside this one.

``app/api/v1/account.py`` is the only family here today. It is deliberately a small one:
the first wave had to prove the instrument and the pattern, not demonstrate throughput.
"""
