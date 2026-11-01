"""Pins the container image against the directories the app actually reads.

The desktop bundle has had this guard for a while - ``package.py`` probes every declared
router and refuses to build when one did not land. The container had none, and it drifted
exactly as you would expect: ``app/resources.py`` resolves ``web/`` and ``model/`` by
walking two parents up from ``app/``, which is ``/srv`` inside the image, while the
Dockerfile built from a ``backend/``-only context and copied neither. The container
answered 404 at ``/`` and ``/playground``; the desktop bundle served both.

Two things are asserted here, and both are cheap:

* every name passed to ``resource_dir(...)`` has a matching ``COPY ... /srv/<name>``;
* the compose build context is wide enough for those directories to be copyable at all.

Neither needs Docker. That matters: an image that cannot be built in this environment is
still an image whose paths can be checked, and a check that only runs where Docker exists
would never run here.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HARNESS = ROOT / "harness"
BACKEND = HARNESS / "backend"
DOCKERFILE = BACKEND / "Dockerfile"
COMPOSE = HARNESS / "deploy" / "compose.yaml"

#: ``resource_dir('web')`` / ``resource_dir("model")`` - the two spellings used in the app.
RESOURCE_CALL = re.compile(r"resource_dir\(\s*['\"]([A-Za-z0-9_]+)['\"]\s*\)")
#: ``COPY <source...> /srv/<name>`` - absolute destination, which is what the image needs.
COPY_TO_SRV = re.compile(r"^\s*COPY\s+(?P<sources>.+?)\s+/srv/(?P<name>[A-Za-z0-9_]+)\s*$",
                         re.MULTILINE)


def _declared_resource_dirs() -> set[str]:
    names = set()
    for path in (BACKEND / "app").rglob("*.py"):
        names.update(RESOURCE_CALL.findall(path.read_text(encoding="utf-8")))
    return names


def test_every_resource_directory_is_copied_into_the_image():
    """The 404s, as an assertion.

    ``resource_root()`` is ``/srv`` in the image, so a name the app asks for is a
    directory the Dockerfile has to place at ``/srv/<name>``. Copying it anywhere else -
    under ``/srv/backend``, say - looks right in the Dockerfile and 404s at runtime.
    """
    declared = _declared_resource_dirs()
    assert declared, "no resource_dir() calls found; this test would silently pass forever"
    copied = {match.group("name") for match in COPY_TO_SRV.finditer(
        DOCKERFILE.read_text(encoding="utf-8"))}
    missing = sorted(declared - copied)
    assert not missing, (
        f"the app reads {', '.join(missing)} through resource_dir(), which resolves to "
        f"/srv/<name> in the image, but the Dockerfile never copies them there. "
        f"Copied: {sorted(copied) or 'nothing'}.")


def test_the_build_context_can_see_those_directories():
    """``COPY web /srv/web`` is only possible if ``web/`` is inside the context.

    The context used to be ``../backend``, which made the line above impossible to write -
    the failure was in the compose file, not the Dockerfile, which is why fixing one
    without the other changes nothing.
    """
    contexts = re.findall(r"^\s*context:\s*(\S+)\s*$", COMPOSE.read_text(encoding="utf-8"),
                          re.MULTILINE)
    assert contexts, "compose no longer declares an explicit build context"
    for context in contexts:
        resolved = (COMPOSE.parent / context).resolve()
        assert resolved == HARNESS.resolve(), (
            f"build context {context!r} resolves to {resolved}, not {HARNESS}. "
            "resource_dir() reaches /srv via the harness root, so a narrower context "
            "cannot supply web/ or model/.")
        for name in _declared_resource_dirs():
            assert (resolved / name).is_dir(), f"{name}/ is not in the build context"


def test_the_ignore_file_does_not_exclude_what_the_image_needs():
    """Widening the context made ``.dockerignore`` load-bearing; keep it honest.

    A pattern here that matches ``web``, ``model`` or ``backend`` would drop the very
    directories the two tests above just proved are required - and the build would still
    succeed, which is the worst kind of regression.
    """
    patterns = [line.strip() for line in
                (HARNESS / ".dockerignore").read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.startswith("#")]
    required = {"web", "model", "backend"}
    for pattern in patterns:
        bare = pattern.strip("/").removeprefix("**/")
        assert bare not in required, f".dockerignore excludes {bare!r}, which the image needs"
