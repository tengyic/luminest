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
def no_dotenv_loading(monkeypatch):
    """Make ``Settings.from_env()`` ignore ``backend/.env`` for every test.

    Scrubbing the environment above is not enough on its own. ``Settings.from_env()`` calls
    ``config.load_dotenv()``, which *re-reads* ``backend/.env`` and re-injects
    ``HARNESS_TUTOR_PROVIDER``/``_MODEL``/``_URL`` — precisely the variables a fixture just
    deleted. A developer following the documented setup keeps a real provider in that file,
    so every test asserting the *unconfigured* model state fails on their machine while
    passing on CI, which checks out a clean tree. Sixteen tests were red on a developer
    checkout and green in CI for this reason.

    Worse than red: those tests reached the provider that the file names and made a real
    outbound request, so "assert the refusal" could pass while a live model answered.

    Neutralising the loader rather than the file keeps a test's own ``setenv`` working (the
    fixture sets variables and ``from_env`` still reads them) while making the suite's result
    independent of what a developer has on disk.
    """
    from app import config as config_module

    monkeypatch.setattr(config_module, 'load_dotenv', lambda *args, **kwargs: {})


@pytest.fixture(scope='session')
def absent_video_seed(tmp_path_factory):
    """A path that does not exist, computed **once per session**.

    ``tmp_path_factory.mktemp(name)`` deletes any directory already sitting at that name,
    so calling it from an autouse function-scoped fixture performs a filesystem delete
    before every single test. Fifty of those trip the environment's bulk-delete guard
    (``[safe-delete][SAFE_DELETE_BULK_CONFIRM_REQUIRED]``, threshold 50 per turn), which
    raises ``SystemExit(1)`` from inside fixture setup -- and pytest reports the remaining
    ~1700 tests as errors. The failure looks like a collapsed test suite, not a delete
    quota, and it is intermittent because it depends on how many deletes have already
    happened in the session. The value never changes, so compute it at session scope.
    """
    return tmp_path_factory.mktemp('no-seed') / 'absent.json'


@pytest.fixture(scope='session')
def absent_image_seed(tmp_path_factory):
    """Same hazard, same fix: one directory for the whole session."""
    return tmp_path_factory.mktemp('no-image-seed')


@pytest.fixture(autouse=True)
def no_shipped_video_curation(monkeypatch, absent_video_seed):
    """Detach the packaged video seed from every test.

    ``video.load_allowlist`` falls back to ``media_packs/video_allowlist_seed.json``, which is
    build output: it changes whenever curation runs, so a test asserting "this concept has no
    video" would pass or fail depending on when the seed was last regenerated. Detaching it here
    makes the unit tests depend on their own fixtures only. The precedence order itself is
    covered by a test that points the pack at a file it wrote.
    """
    from app.harness import video

    monkeypatch.setattr(video, 'SEED_PACK', absent_video_seed)


@pytest.fixture(autouse=True)
def no_shipped_image_pack(monkeypatch, absent_image_seed):
    """Detach the packaged image seed from every test.

    Same hazard as the video seed, with a sharper edge: ``_deck_image`` asks the shipped pack
    *first*, so a stale or half-curated ``media_packs/image_seed.json`` would silently change
    which deck tests see a picture at all. A test asserting "this deck has no image, and here
    is the reason" would pass before curation and fail after it, on a machine rather than on a
    code change. Both the index and the bytes directory are detached, because an index that
    names files it cannot find refuses the picture and reports a different reason.
    """
    from app.harness import media

    monkeypatch.setattr(media, 'SEED_PACK', absent_image_seed / 'absent.json')
    monkeypatch.setattr(media, 'SEED_DIR', absent_image_seed / 'images')
