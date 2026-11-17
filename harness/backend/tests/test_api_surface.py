"""The recorded HTTP surface must match the application this tree builds.

``scripts/api_surface.py`` has always described its ``--expect`` output as "the route
count the guard test asserts". That guard did not exist, and the fixture had drifted from
244 routes to 274 without anything noticing. This is the guard.

It asserts the whole sorted ``METHOD path`` list rather than the count alone: a refactor
that removes one route and adds another keeps the count and changes the surface, which is
exactly the change this instrument exists to catch.
"""

import json
from pathlib import Path

FIXTURE = Path(__file__).resolve().parent / 'fixtures' / 'api_surface.json'


def _surface(monkeypatch, tmp_path):
    """Build the app the way ``api_surface.build_app`` does, under pytest's control.

    ``build_app`` mutates ``os.environ`` and never restores it; calling it from a test
    would leak a throwaway data directory into every later test in the session. The
    monkeypatch fixture restores the environment instead.
    """
    from app.config import Settings
    from app.main import create_app
    from scripts import api_surface

    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path / 'api-surface'))
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    return api_surface.build_surface(create_app(Settings.from_env()))


def test_the_recorded_surface_matches_the_built_app(monkeypatch, tmp_path):
    recorded = json.loads(FIXTURE.read_text(encoding='utf-8'))
    surface = _surface(monkeypatch, tmp_path)

    live = sorted(f'{entry["method"]} {entry["path"]}' for entry in surface['routes'])
    assert surface['route_count'] == recorded['route_count'], (
        f'recorded: {recorded["route_count"]} routes, this tree: '
        f'{surface["route_count"]}. Regenerate with `python scripts/api_surface.py '
        '--expect tests/fixtures/api_surface.json` and say in the commit why the '
        'surface changed.')

    added = sorted(set(live) - set(recorded['routes']))
    removed = sorted(set(recorded['routes']) - set(live))
    assert live == recorded['routes'], {'added': added, 'removed': removed}
