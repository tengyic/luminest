"""A lesson whose concept has a curated photograph must be illustrated offline.

``fetch_for_lesson`` used to go straight to a web search for every image slot, so
``/api/v1/images/for-lesson`` reported ``no_images`` for
``physics_acceleration_as_the_rate_of_change_of_velocity`` even though the bundle
ships a licence-cleared ``acceleration`` photograph. The pack is keyed by short
slugs; ``_concept_keys`` performs the join, but nothing in this path called it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings
from app.harness import media


@pytest.fixture(autouse=True)
def real_shipped_pack(monkeypatch, no_shipped_image_pack):
    """Restore the committed pack for this module only.

    ``conftest.no_shipped_image_pack`` deliberately points the seed at a missing file
    so no test can accidentally depend on a developer's curation state. These two tests
    are *about* the shipped pack, so they opt back in explicitly - and by depending on
    that fixture they are guaranteed to run after it.
    """
    root = Path(media.__file__).resolve().parents[1] / 'media_packs'
    monkeypatch.setattr(media, 'SEED_PACK', root / 'image_seed.json')
    monkeypatch.setattr(media, 'SEED_DIR', root / 'images')


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    monkeypatch.delenv('HARNESS_SECRET', raising=False)
    monkeypatch.delenv('HARNESS_TUTOR_PROVIDER', raising=False)
    return Settings.from_env()


def _install(monkeypatch, needs):
    monkeypatch.setattr(media, 'lesson_image_needs', lambda **kw: needs)
    searched = []

    def fake_fetch(*args, **kwargs):
        searched.append(args[1] if len(args) > 1 else '')
        return {'outcome': 'no_cleared_candidate', 'assets': [], 'seen': 0,
                'accepted': 0, 'rejections': [], 'notes': []}

    monkeypatch.setattr(media, 'fetch', fake_fetch)
    return searched


def test_shipped_photo_fills_the_concept_slot_with_no_network(settings, monkeypatch):
    cid = 'physics_acceleration_as_the_rate_of_change_of_velocity'
    needs = [{'slot': 'concept', 'block_index': 1, 'query': 'Acceleration',
              'support': '', 'alt_text': 'a'},
             {'slot': 'block', 'block_index': 2, 'query': 'velocity graph',
              'support': '', 'alt_text': 'b'}]
    searched = _install(monkeypatch, needs)
    result = media.fetch_for_lesson(settings, concept_id=cid, title='Acceleration',
                                    summary='The rate of change of velocity')
    assert result['outcome'] == 'ok'
    assert result['assigned'] == 1
    first = result['images'][0]
    assert first['outcome'] == 'shipped' and first['via'] == 'shipped'
    assert first['asset']['sha256']
    assert first['asset']['credit'], 'a shipped picture must still carry its credit line'
    # Only the slot the pack could not fill is allowed to reach the network.
    assert searched == ['velocity graph']
    blocks = media.lesson_photograph_blocks(settings, cid)
    assert blocks and blocks[0]['block_index'] == 1


def test_a_concept_with_no_shipped_photo_still_reports_a_named_absence(settings, monkeypatch):
    cid = 'ap_psychology_acquisition_extinction_and_spontaneous_recovery'
    needs = [{'slot': 'concept', 'block_index': 1, 'query': 'conditioning',
              'support': '', 'alt_text': 'a'}]
    searched = _install(monkeypatch, needs)
    result = media.fetch_for_lesson(settings, concept_id=cid, title='Conditioning')
    assert result['outcome'] == 'no_images'
    assert result['images'][0]['outcome'] == 'no_cleared_candidate'
    assert searched == ['conditioning']
