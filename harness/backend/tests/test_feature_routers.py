"""The feature routers must be mounted in the app *and* declared to the freezer.

Every capability that lives in its own ``routes_*`` module is reached by
``main.create_app`` through ``importlib.import_module``. That dynamic import is invisible
to PyInstaller, so the frozen desktop build shipped with ``app.main`` present and **none**
of the routers it mounts: ``/api/v1/deck``, ``/api/v1/flashcards``, ``/api/v1/my-courses``
and ``/api/v1/images/library`` all answered 404 in the app a tester installs, while the
source tree served them and the whole suite stayed green.

Nothing here can catch a freezer mistake by itself - that is ``scripts/package.py``'s
archive check and the frozen-artifact smoke test. This file is the source-tree half: it
pins that the router list is defined once, that every name in it really is a router
module, that every one of them carries a smoke probe, and that the application mounts
them. Together the two halves mean a router cannot go missing without a test or a build
failing first.
"""
import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.feature_routers import FEATURE_ROUTERS
from app.main import create_app

PACKAGE_SCRIPT = Path(__file__).resolve().parents[3] / "harness" / "scripts" / "package.py"


@pytest.fixture(scope="module")
def package_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("luminfest_package_routers", PACKAGE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("HARNESS_ENV", "test")
    monkeypatch.setenv("HARNESS_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("HARNESS_DATABASE_URL", raising=False)
    monkeypatch.delenv("HARNESS_SECRET", raising=False)
    monkeypatch.setenv("HARNESS_TUTOR_PROVIDER", "offline")
    return Settings.from_env()


def test_every_named_feature_router_is_a_real_module_with_a_router():
    """A name in the tuple is a promise that the module ships, so it must resolve."""
    for name in FEATURE_ROUTERS:
        module = importlib.import_module(f"app.{name}")
        assert hasattr(module, "router"), f"app.{name} defines no APIRouter named 'router'"
        assert module.router.routes, f"app.{name}.router declares no routes"


def test_the_application_mounts_every_feature_router(settings):
    """The source-tree equivalent of the four 404s a release review found.

    Reading the app's own OpenAPI schema is the closest thing to the question a tester
    asks - "does this path exist" - without starting a server.
    """
    paths = set(create_app(settings).openapi()["paths"])
    expected = {
        "routes_deck": "/api/v1/deck",
        "routes_flash": "/api/v1/flashcards",
        "routes_create": "/api/v1/my-courses",
        "routes_media": "/api/v1/images/library",
    }
    missing = [path for path in expected.values() if path not in paths]
    assert not missing, f"create_app did not mount these routes: {missing}"


def test_the_mounted_routes_actually_answer(settings):
    """Mounted is not the same as serving: drive the four endpoints a learner opens.

    A router can be included and still 404 if the path it declares is not the path the
    client asks for, which is the failure mode this test exists for. Authentication is
    required, so 200 is not the assertion - only that the route is reachable and does not
    answer "no such path".
    """
    with TestClient(create_app(settings)) as client:
        registered = client.post("/api/v1/auth/register", json={
            "name": "Router probe", "email": "routers@example.com",
            "password": "Correct-Horse-9", "age_confirmed": True}).json()
        headers = {"Authorization": "Bearer " + registered["token"]}
        for route in ("/api/v1/deck", "/api/v1/flashcards", "/api/v1/my-courses",
                      "/api/v1/images/library"):
            assert client.get(route, headers=headers).status_code != 404, route


def test_every_feature_router_has_a_frozen_artifact_probe(package_module):
    """The probe map is what the packaged smoke test walks, so it must stay complete."""
    probes = dict(package_module.FEATURE_ROUTE_PROBES)
    assert set(probes) == set(FEATURE_ROUTERS), (
        "every feature router needs a smoke probe: "
        f"missing {sorted(set(FEATURE_ROUTERS) - set(probes))}, "
        f"unknown {sorted(set(probes) - set(FEATURE_ROUTERS))}")


def _declared_paths(router) -> set[str]:
    """Every path a router declares, including routers FastAPI nested into it.

    FastAPI 0.143 represents ``include_router`` with an ``_IncludedRouter`` wrapper that
    has no ``.path``; the real routes live on ``original_router.routes``. Walking only the
    top level would report a real, served probe as undeclared - the same class of false
    negative this test exists to prevent, but in the other direction.
    """
    found: set[str] = set()
    for route in router.routes:
        nested = getattr(getattr(route, 'original_router', None), 'routes', None)
        if nested:
            found |= _declared_paths(route.original_router)
            continue
        path = getattr(route, 'path', None)
        if path:
            found.add(path)
    return found


def test_each_probe_names_a_route_its_module_really_declares(package_module):
    """A probe pointing at the wrong path would pass the build and prove nothing."""
    for name, route in package_module.FEATURE_ROUTE_PROBES:
        module = importlib.import_module(f"app.{name}")
        declared = _declared_paths(module.router)
        assert f"/api/v1{route}" in declared, (
            f"app.{name} does not declare /api/v1{route}; it declares {sorted(declared)}")


def test_packaging_reads_the_same_router_list_as_the_application(package_module):
    """One tuple with two readers - the whole point, and the drift that shipped a hole."""
    assert package_module.feature_router_modules() == tuple(FEATURE_ROUTERS)


def test_the_archive_check_actually_rejects_a_router_that_did_not_land(package_module):
    """Negative control for the build gate.

    The shipped defect was precisely a router absent from the frozen module table, so the
    gate has to be shown rejecting that case - not just passing when everything is fine.
    The stand-in has to be a name that genuinely is not a module: ``routes_multimodal``
    used to serve, until it became a real router, which quietly turned this negative
    control into a tautology.
    """
    present = [f"app.{name}" for name in FEATURE_ROUTERS]
    assert package_module.missing_router_modules(FEATURE_ROUTERS, present) == []
    assert package_module.missing_router_modules(
        FEATURE_ROUTERS + ("routes_never_written",), present) == ["routes_never_written"]
    assert package_module.missing_router_modules(FEATURE_ROUTERS, []) == list(FEATURE_ROUTERS)
