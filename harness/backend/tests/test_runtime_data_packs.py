"""Every route that reads a runtime JSON pack must actually serve content.

The curriculum and media packs are loaded through ``Path(__file__).resolve().parent``
rather than by import. That makes them invisible to a bundler and to anyone reading the
import graph, and it means a missing pack is not an error at startup: the knowledge graph
comes back empty and the media and simulation routes raise 500 the first time a learner
opens them. The frozen-artifact check lives in ``scripts/package.py``; this file is the
source-tree half, so the packs cannot be dropped or emptied before packaging either.

Thresholds are deliberately below the current counts. This asserts that the packs are
present and wired up, not that they never grow.
"""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

APP_DIR = Path(__file__).resolve().parents[1] / "app"

#: Directories read at runtime as data. Kept in sync with package.py's PACK_DATA_DIRS.
PACK_DIRS = ("curriculum_packs", "media_packs")


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("HARNESS_ENV", "test")
    monkeypatch.setenv("HARNESS_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("HARNESS_DATABASE_URL", raising=False)
    monkeypatch.delenv("HARNESS_SECRET", raising=False)
    monkeypatch.delenv('HARNESS_TUTOR_PROVIDER', raising=False)
    return Settings.from_env()


@pytest.fixture
def learner(settings):
    with TestClient(create_app(settings)) as client:
        body = client.post("/api/v1/auth/register", json={
            "name": "Pack probe", "email": "packs@example.com",
            "password": "Correct-Horse-9", "age_confirmed": True}).json()
        headers = {"Authorization": "Bearer " + body["token"]}
        client.patch("/api/v1/me", json={"course_id": "integrated_math_1"}, headers=headers)
        yield client, headers


def test_every_pack_directory_exists_and_holds_json():
    for name in PACK_DIRS:
        directory = APP_DIR / name
        assert directory.is_dir(), f"{directory} is missing; packaging will ship without it"
        assert list(directory.glob("*.json")), f"{directory} holds no JSON packs"


def test_the_packaging_script_lists_every_runtime_pack_directory():
    """Guards against adding a pack directory the bundler does not know about."""
    import importlib.util

    script = Path(__file__).resolve().parents[2] / "scripts" / "package.py"
    spec = importlib.util.spec_from_file_location("luminfest_package_packs", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert set(module.PACK_DATA_DIRS) == set(PACK_DIRS)


def test_knowledge_graph_is_populated_for_the_default_course(learner):
    client, headers = learner
    graph = client.get("/api/v1/knowledge-graph", headers=headers).json()
    nodes, edges = graph.get("nodes") or [], graph.get("edges") or []
    assert len(nodes) >= 100, f"knowledge graph has {len(nodes)} nodes; curriculum_packs did not load"
    assert len(edges) >= 100, f"knowledge graph has {len(edges)} edges; prerequisites are missing"
    # A graph with nodes but no edges is not a graph: it cannot order study.
    assert all("id" in node for node in nodes)


def test_media_and_simulation_routes_serve_pack_content(learner):
    client, headers = learner
    sources = client.get("/api/v1/media/sources", headers=headers)
    assert sources.status_code == 200, sources.text[:200]
    assert len(sources.json().get("sources") or []) >= 5

    simulations = client.get("/api/v1/simulations", headers=headers)
    assert simulations.status_code == 200, simulations.text[:200]
    assert simulations.json().get("units"), "no simulation units; media_packs did not load"


def test_every_pack_file_parses_as_json():
    """A truncated pack fails at request time, in front of a learner, not at import."""
    for name in PACK_DIRS:
        for path in sorted((APP_DIR / name).glob("*.json")):
            with path.open("rb") as stream:
                json.load(stream)
