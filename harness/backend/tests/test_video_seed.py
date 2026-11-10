"""The shipped video seed: the file that lets a lesson play with no network.

The desktop build runs with outbound media off, so the video a learner sees comes from
``media_packs/video_allowlist_seed.json`` — curated once, at build time, by
``scripts/curate_videos.py``, and read at runtime without a request. That makes the file a
contract rather than a cache, and these are its terms:

1. **It parses, and every row is complete.** A truncated write is not a loud failure:
   ``load_allowlist`` reads unparsable JSON as "no seed", so every lesson would lose its
   video while every other check in the suite stayed green.
2. **Its keys are lesson ids.** The first curation pass keyed rows by graph *node* id. Every
   row was written, the file looked full, and no lesson ever found one, because a lesson asks
   for its own id. Only the curriculum can catch that, so it is asked here.
3. **A curated lesson resolves.** "The file contains a row" and "a lesson can play it" are
   different claims, and the second one is the only one that matters.

The file is build output, so a checkout that has never curated skips instead of failing.
A file that is present and wrong always fails.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import curriculum
from app.config import Settings
from app.harness import video

#: Where the seed lives in the source tree. ``video.SEED_PACK`` is detached by an autouse
#: fixture so that unrelated tests never depend on when curation last ran; this file is the
#: one place that deliberately looks at the real thing.
SEED = Path(video.__file__).resolve().parents[1] / 'media_packs' / 'video_allowlist_seed.json'


@pytest.fixture
def seed(monkeypatch, tmp_path):
    if not SEED.is_file():
        pytest.skip('no video seed has been curated in this checkout')
    monkeypatch.setattr(video, 'SEED_PACK', SEED)
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('HARNESS_MEDIA_ENABLED', '0')      # the shipped default
    monkeypatch.delenv('HARNESS_TUTOR_PROVIDER', raising=False)
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    monkeypatch.delenv('HARNESS_SECRET', raising=False)
    return Settings.from_env(), json.loads(SEED.read_text(encoding='utf-8'))


def test_the_seed_parses_and_every_row_is_complete(seed):
    _settings, table = seed
    assert isinstance(table, dict) and table, 'the seed has no courses in it'
    for course_id, rows in table.items():
        assert isinstance(rows, list) and rows, f'{course_id} maps to no rows'
        for row in rows:
            for key in ('concept_id', 'provider', 'video_id', 'title'):
                assert str(row.get(key) or '').strip(), \
                    f'{course_id}: a row is missing {key}: {row}'
            # A row with no stated reason is a row nobody can review later.
            assert str(row.get('why') or '').strip(), f'{course_id}: {row.get("concept_id")} ' \
                                                       'has no recorded reason'


def test_every_row_is_keyed_by_a_lesson_that_exists(seed):
    """The node-id bug: a full file that no lesson could ever read from."""
    _settings, table = seed
    for course_id, rows in table.items():
        lessons = set(curriculum.course_concepts(course_id))
        assert lessons, f'{course_id} is not a course the curriculum knows'
        unknown = sorted({str(row.get('concept_id')) for row in rows} - lessons)
        assert not unknown, (f'{course_id}: rows keyed by something no lesson asks for: '
                             f'{unknown}')


def test_a_curated_lesson_resolves_with_the_network_off(seed):
    settings, table = seed
    assert settings.media_enabled is False, 'the point is that this works with media off'
    course_id = sorted(table)[0]
    row = table[course_id][0]
    concept_id = str(row['concept_id'])

    cards = video.resolve(settings, course_id, concept_id, verify_remote=False)

    assert cards, f'{course_id}/{concept_id} is in the seed but resolves to nothing'
    assert cards[0]['video_id'] == row['video_id']
    assert cards[0]['watch_url'], 'a curated video with no address is not a video'
    assert cards[0]['status'] != 'withheld', 'a freshly curated row cannot be withdrawn'


def test_the_operator_file_still_wins_over_the_shipped_seed(seed, tmp_path):
    """A curated seed must not override what an operator curated by hand."""
    settings, table = seed
    course_id = sorted(table)[0]
    video.save_allowlist(settings, {course_id: [{'concept_id': 'operator_choice',
                                                 'provider': 'youtube',
                                                 'video_id': 'dQw4w9WgXcQ',
                                                 'title': 'Chosen by hand'}]})
    loaded = video.load_allowlist(settings)
    assert [str(row['concept_id']) for row in loaded[course_id]] == ['operator_choice']
