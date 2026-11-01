import os

import pytest


@pytest.fixture(autouse=True)
def hermetic_harness_environment(monkeypatch):
    """Scrub every ``HARNESS_*`` variable before a test builds its own settings.

    ``Settings.from_env()`` reads the process environment, so without this a test suite inherits
    whatever the developer's shell happens to export and the same commit passes or fails depending
    on the machine. That is not hypothetical. With ``HARNESS_ACCESS_TOKEN_TTL_SECONDS=3600`` in the
    environment the access token expires inside the clock shifts that the receipt-expiry test and
    the UTC-day-accounting test perform, and both start reporting ``401`` instead of exercising the
    rule they are actually about -- a failure that looks like a security regression and is really
    an ambient variable.

    The fixture is autouse so it cannot be forgotten, and it runs before the per-file ``settings``
    fixtures, which then set exactly the variables they intend to test against.
    """
    for name in [key for key in os.environ if key.startswith('HARNESS_')]:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def no_shipped_video_curation(monkeypatch, tmp_path_factory):
    """Detach the packaged video seed from every test.

    ``video.load_allowlist`` falls back to ``media_packs/video_allowlist_seed.json``, which is
    build output: it changes whenever curation runs, so a test asserting "this concept has no
    video" would pass or fail depending on when the seed was last regenerated. Detaching it here
    makes the unit tests depend on their own fixtures only. The precedence order itself is
    covered by a test that points the pack at a file it wrote.
    """
    from app.harness import video

    monkeypatch.setattr(video, 'SEED_PACK',
                        tmp_path_factory.mktemp('no-seed') / 'absent.json')


@pytest.fixture(autouse=True)
def no_shipped_image_pack(monkeypatch, tmp_path_factory):
    """Detach the packaged image seed from every test.

    Same hazard as the video seed, with a sharper edge: ``_deck_image`` asks the shipped pack
    *first*, so a stale or half-curated ``media_packs/image_seed.json`` would silently change
    which deck tests see a picture at all. A test asserting "this deck has no image, and here
    is the reason" would pass before curation and fail after it, on a machine rather than on a
    code change. Both the index and the bytes directory are detached, because an index that
    names files it cannot find refuses the picture and reports a different reason.
    """
    from app.harness import media

    absent = tmp_path_factory.mktemp('no-image-seed')
    monkeypatch.setattr(media, 'SEED_PACK', absent / 'absent.json')
    monkeypatch.setattr(media, 'SEED_DIR', absent / 'images')
