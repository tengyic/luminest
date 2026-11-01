"""Where the app's top-level resource directories live, frozen or not.

Three modules read a directory that sits *outside* the ``app`` package - the static web
assets (``web/``), the trained-adapter package (``model/``) and, through
:func:`app.config.legal_dir`, the legal documents. In the source tree those directories
are siblings of ``backend/``, so each module reached them with
``Path(__file__).resolve().parents[2]``. That arithmetic is right for exactly one layout,
and it is why the frozen app looked one level too deep for ``web`` and ``model``.

The two layouts::

    source                 frozen (PyInstaller onedir, --contents-directory _internal)
    harness/               LuminfestBackend/
      backend/               _internal/
        app/web_routes.py      app/web_routes.pyc
      web/                     web/
      model/                   model/
      legal/                   legal/

PyInstaller mirrors the *package* tree under the bundle's ``_internal`` contents
directory, but the frozen layout has no ``backend/`` level to consume the extra
``parents`` step, so ``parents[2]`` lands on ``LuminfestBackend`` - a directory with no
``web`` in it. The visible result was a shipped app whose gallery page (``/playground``)
and workbench shell (``/``) answered 404 while ``/api/v1/health`` looked perfectly
healthy.

So the depth is computed once, here, and every caller asks this module instead:

* source tree - ``parents[2]`` of this file is ``harness/``, where ``web/`` and ``model/``
  live;
* frozen bundle - ``sys._MEIPASS``, which PyInstaller sets to the ``_internal`` directory
  that ``--add-data`` writes those same directories into.

``app/harness/playground/catalogue.py`` deliberately does not use this. Its packs live
*inside* the package (``app/harness/playground/``), so its own ``parents[2]`` already
lands on the right directory in both layouts - the two extra package levels cancel the
missing ``backend/``. Adding an indirection there would only be a new way to get it wrong.
"""

from __future__ import annotations

import sys
from pathlib import Path

#: How many ``parents`` steps from this file reach the source tree's root of top-level
#: resources (``harness/``). Named rather than inlined so the number is explained at the
#: one place it is used.
_SOURCE_ROOT_DEPTH = 2


def resource_root() -> Path:
    """The directory that holds ``web/``, ``model/`` and ``legal/``.

    Frozen builds answer ``sys._MEIPASS``; everything else answers the source tree's
    ``harness/``. ``sys.frozen``/``sys._MEIPASS`` are read at *call* time, not import
    time, so a test can stage a bundle and assert this resolves inside it.
    """
    if getattr(sys, 'frozen', False) and getattr(sys, '_MEIPASS', None):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[_SOURCE_ROOT_DEPTH]


def resource_dir(name: str) -> Path:
    """``resource_root() / name``.

    One spelling for every caller, so no module repeats - and no module can get wrong -
    the arithmetic that produced the 404s.
    """
    return resource_root() / name
