"""The shipped image pack: curation travels as data, so the offline deck still has pictures.

The desktop build runs with ``media_enabled`` off, which is a promise in ``privacy.md`` and not
a bug. The consequence was that ``media.acquire`` could only answer ``network_disabled``, so
every deck fell back to a decorative pattern drawn by ``LuminfestArt`` — a shape captioned
"FIGURE 1 · DETERMINISTIC" that reads as an illustration and is not one. These tests pin the
replacement: a picture curated at build time is installed into the instance's own cache on
first ask, and from then on the bytes route, the manifest and the export bundle treat it
exactly like a downloaded one.

The tests write their own pack. ``conftest.no_shipped_image_pack`` detaches the real one, so a
half-finished curation run on a developer's machine cannot decide whether these pass.
"""
from __future__ import annotations

import hashlib
import json
import struct
import zlib
from dataclasses import replace
from pathlib import Path

from app import procedure_service
from app.harness import media

from test_api import settings  # noqa: F401 - fixture


def _png(width: int = 4, height: int = 3) -> bytes:
    """A real, decodable PNG, built with the stdlib only.

    Not a hardcoded blob: a fixture that is actually a valid image is what makes
    ``store_bytes``-style MIME sniffing meaningful, and ``zlib``/``struct`` are already
    dependencies of the interpreter.
    """
    raw = b''.join(b'\x00' + b'\x80\x80\x80' * width for _ in range(height))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack('>I', len(data)) + tag + data
                + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff))

    header = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header)
            + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))


def _row(body: bytes, *, title: str = 'Air masses over the Pacific') -> dict:
    sha = hashlib.sha256(body).hexdigest()
    return {
        'sha256': sha, 'file': f'{sha}.png', 'source': 'wikimedia',
        'source_id': 'File:Air masses.png', 'query': 'Air masses and fronts',
        'title': title, 'creator': 'A photographer', 'licence_code': 'Public domain',
        'licence_class': 'public_domain', 'licence_url': '',
        'attribution_text': 'Air masses over the Pacific, public domain',
        'landing_page_url': 'https://commons.wikimedia.org/wiki/File:Air_masses.png',
        'file_url': 'https://upload.wikimedia.org/air-masses.png',
        'bytes': len(body), 'width': 4, 'height': 3, 'mime': 'image/png',
        'description': 'A front where two air masses meet.',
        'fetched_at': 1_700_000_000.0,
        'alt_text': 'Photograph illustrating Air masses and fronts',
    }


def _write_pack(tmp_path: Path, monkeypatch, rows: dict[str, dict], *, bodies: bool = True):
    """Point ``media`` at a pack this test built, optionally without the bytes."""
    pack_dir = tmp_path / 'media_packs'
    images = pack_dir / 'images'
    images.mkdir(parents=True, exist_ok=True)
    if bodies:
        for row in rows.values():
            (images / str(row['file'])).write_bytes(_png())
    index = pack_dir / 'image_seed.json'
    index.write_text(json.dumps(rows, indent=2), encoding='utf-8')
    monkeypatch.setattr(media, 'SEED_PACK', index)
    monkeypatch.setattr(media, 'SEED_DIR', images)
    return index, images


def test_an_absent_pack_is_empty_rather_than_an_error(tmp_path, monkeypatch):
    """A source checkout that has never run the curator must still boot."""
    monkeypatch.setattr(media, 'SEED_PACK', tmp_path / 'never-written.json')
    monkeypatch.setattr(media, 'SEED_DIR', tmp_path / 'no-images')

    assert media.shipped_pack() == {}
    assert media.shipped_for(settings, 'air_masses_and_fronts') is None


def test_the_shipped_picture_is_installed_into_the_instance_cache(tmp_path, monkeypatch, settings):
    body = _png()
    row = _row(body)
    _write_pack(tmp_path, monkeypatch, {'air_masses_and_fronts': row})

    installed = media.shipped_for(settings, 'air_masses_and_fronts')

    assert installed is not None
    assert installed['sha256'] == row['sha256']
    # The attribution travels with the picture: it is a condition of the licence, so a
    # shipped image that lost its credit would be worse than no image.
    assert installed['attribution_text'] == row['attribution_text']
    assert installed['licence_code'] == 'Public domain'
    # Installed into *this instance's* data directory, addressed by content, so the bytes
    # route and the export bundle need no special case for "shipped".
    target = Path(settings.data_dir) / installed['cache_path']
    assert target.is_file()
    assert target.read_bytes() == body
    assert target.name == f"{row['sha256']}.png"


def test_installing_the_same_picture_twice_adds_one_manifest_line(tmp_path, monkeypatch, settings):
    """Idempotent, because the deck asks on every plan build, not once per install."""
    _write_pack(tmp_path, monkeypatch, {'air_masses_and_fronts': _row(_png())})

    first = media.shipped_for(settings, 'air_masses_and_fronts')
    second = media.shipped_for(settings, 'air_masses_and_fronts')

    assert first is not None and second is not None
    assert first['sha256'] == second['sha256']
    lines = media.manifest_path(settings).read_text(encoding='utf-8').splitlines()
    assert len([line for line in lines if line.strip()]) == 1


def test_a_row_whose_bytes_are_missing_is_not_a_picture(tmp_path, monkeypatch, settings):
    """The index naming a file the pack does not carry is a broken pack, not an image.

    Claiming it would serve a 404 through the bytes route under a real attribution line,
    which is the failure mode this whole path exists to remove.
    """
    _write_pack(tmp_path, monkeypatch, {'air_masses_and_fronts': _row(_png())},
                bodies=False)

    assert media.shipped_for(settings, 'air_masses_and_fronts') is None


def test_the_installed_picture_is_served_like_a_downloaded_one(tmp_path, monkeypatch, settings):
    """One manifest row shape, so every reader of the manifest sees a normal image."""
    row = _row(_png())
    _write_pack(tmp_path, monkeypatch, {'air_masses_and_fronts': row})

    media.shipped_for(settings, 'air_masses_and_fronts')

    manifest = media._load_manifest(settings)
    assert row['sha256'] in manifest
    assert manifest[row['sha256']]['shipped'] is True
    assert not str(manifest[row['sha256']]['cache_path']).startswith('/')


def test_the_deck_uses_the_shipped_picture_with_the_network_off(tmp_path, monkeypatch, settings):
    """The actual defect: offline policy used to mean "no picture, ever".

    ``desktop`` sets ``media_enabled`` off. That must now cost the live search, not the
    picture the build already curated.
    """
    _write_pack(tmp_path, monkeypatch, {'air_masses_and_fronts': _row(_png())})
    offline = replace(settings, media_enabled=False)

    image, reason = procedure_service._deck_image(
        offline, 'Air masses and fronts', 'air_masses_and_fronts')

    assert reason == ''
    assert image is not None
    assert image['url'] == f"/api/v1/media/images/{image['sha256']}/bytes"
    assert image['credit'] == 'Air masses over the Pacific, public domain'
    assert image['licence_class'] == 'public_domain'


def test_a_lesson_the_pack_does_not_cover_still_reports_why(tmp_path, monkeypatch, settings):
    """Coverage is not the same as honesty: an uncurated lesson says so, and says why."""
    _write_pack(tmp_path, monkeypatch, {'air_masses_and_fronts': _row(_png())})
    offline = replace(settings, media_enabled=False)

    image, reason = procedure_service._deck_image(
        offline, 'Climate versus weather', 'climate_versus_weather')

    assert image is None
    assert 'network_disabled' in reason


def test_the_narrated_deck_carries_the_shipped_photograph(tmp_path, monkeypatch, settings):
    """The deck half of the defect: a picture on the wire that the slide never showed.

    ``presentation.compose`` attaches a photograph to the slide it illustrates, and the deck
    used to be built with ``include_image`` unset by every caller, so no picture was ever
    attached and the client drew a bundled pattern instead. It also only ever asked the live
    search, which on the desktop build can only answer ``network_disabled``.
    """
    from app.harness import presentation
    from test_media_pipeline import harness_context

    lesson = 'quadratic_expressions_and_their_graphs'
    _write_pack(tmp_path, monkeypatch, {lesson: _row(_png())})

    deck = presentation.compose(harness_context(replace(settings, media_enabled=False)),
                                lesson, {})

    photos = [slide for slide in deck['slides']
              if (slide.get('visual') or {}).get('type') == 'photograph']
    assert photos, 'the deck dropped the curated photograph'
    visual = photos[0]['visual']
    assert visual['url'] == f"/api/v1/media/images/{visual['sha256']}/bytes"
    # The attribution is a condition of the licence, so it must travel with the picture to
    # the slide, not live only in the manifest.
    assert visual['attribution']
    assert visual['attribution'] == visual['credit']


def test_the_shared_payload_names_the_attribution_under_both_keys():
    """``deck.from_presentation`` reads ``attribution``; the native deck reads ``credit``.

    They are the same sentence, built once, so neither consumer can ship a picture with a
    blank credit because it happened to read the other key.
    """
    payload = media.asset_payload({
        'sha256': 'a' * 64, 'attribution_text': 'Photograph by someone, CC BY 4.0',
        'title': 'A front', 'alt_text': 'Two air masses meeting', 'licence_code': 'CC BY 4.0',
        'licence_class': 'cc_by', 'landing_page_url': 'https://example.test/x',
        'width': 1200, 'height': 800,
    })

    assert payload['credit'] == payload['attribution'] == 'Photograph by someone, CC BY 4.0'
    assert payload['url'] == '/api/v1/media/images/' + 'a' * 64 + '/bytes'
    assert payload['licence_class'] == 'cc_by'


def test_the_pack_is_keyed_by_lesson_id_so_the_deck_can_find_it(tmp_path, monkeypatch, settings):
    """``assets_for`` resolves the authored lesson id and passes that through.

    Curating by graph node id would write rows nothing ever reads, which is exactly how a
    pack can be full and every deck still be empty.
    """
    _write_pack(tmp_path, monkeypatch, {'air_masses_and_fronts': _row(_png())})
    offline = replace(settings, media_enabled=False)

    image, _ = procedure_service._deck_image(offline, 'Air masses and fronts',
                                             'air_masses_and_fronts')
    # Same lesson asked for by its graph node id: not in the pack, so no picture.
    other, reason = procedure_service._deck_image(offline, 'Air masses and fronts',
                                                  'ess.2.3')

    assert image is not None
    assert other is None and reason
