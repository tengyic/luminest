"""Regression tests for the image MIME normalisation bug.

The defect these lock down: ``_search_openverse`` set ``Candidate.mime`` from Openverse's
``filetype`` field, which is a bare extension (``"jpg"``), while ``filter_candidates``
compared that value against ``IMAGE_MIMES`` (``"image/jpeg"``). Every Openverse hit was
therefore rejected with the reason "Not a displayable image type (jpg)" -- a
correct-looking rejection attached to the most common image format on the web, which is
exactly why it survived: the reason read as a judgement about the asset rather than a
vocabulary mismatch in the provider mapping.

The tests are written against ``normalise_mime`` and the filter rather than against the
Openverse HTTP call, because the invariant is "a bare extension is never, by itself, a
reason to drop an image", and that must hold for a provider that does not exist yet.
"""

from __future__ import annotations

import pytest

from app.harness import media


@pytest.mark.parametrize('given,expected', [
    ('jpg', 'image/jpeg'),
    ('JPEG', 'image/jpeg'),
    ('.png', 'image/png'),
    ('webp', 'image/webp'),
    ('gif', 'image/gif'),
    ('image/jpeg', 'image/jpeg'),
    ('IMAGE/PNG', 'image/png'),
    ('image/svg+xml', 'image/svg+xml'),
])
def test_normalise_mime_accepts_extensions_and_mime_types(given, expected):
    assert media.normalise_mime(given) == expected


def test_normalise_mime_preserves_an_unknown_value_for_the_reason_string():
    """An unrecognised value is kept, lowercased, so the rejection can name it.

    Emptying it would turn a specific rejection reason into a vague one, and the whole
    point of the filter is that every rejection is checkable by a reviewer.
    """
    assert media.normalise_mime('application/x-weird') == 'application/x-weird'
    assert media.normalise_mime('  jxl  ') == 'jxl'
    assert media.normalise_mime('') == ''


def test_a_bare_extension_is_not_a_rejection_reason():
    """The exact defect: a 1200x900 JPEG described as ``filetype='jpg'`` must be accepted.

    Before the fix this candidate was dropped on the MIME branch. The size and overlap
    are chosen to pass every other rule so that the MIME check is the only thing under
    test.
    """
    candidate = media.Candidate(
        source='openverse', source_id='1', title='Mitosis in an onion root tip',
        licence_code='cc0 1.0', licence_class='cc0',
        file_url='https://example.invalid/a.jpg', width=1200, height=900, mime='jpg')
    accepted, rejected = media.filter_candidates([candidate], 'mitosis onion root tip')
    assert [c.source_id for c in accepted] == ['1'], [c.rejected for c in rejected]


def test_a_genuinely_undisplayable_type_is_still_rejected():
    """The fix must not turn the filter off: a PDF is not an image and must still drop."""
    candidate = media.Candidate(
        source='openverse', source_id='2', title='Mitosis in an onion root tip',
        licence_code='cc0 1.0', licence_class='cc0',
        file_url='https://example.invalid/a.pdf', width=1200, height=900,
        mime='application/pdf')
    accepted, rejected = media.filter_candidates([candidate], 'mitosis onion root tip')
    assert accepted == []
    assert 'Not a displayable image type' in rejected[0].rejected


def test_extension_map_covers_every_displayable_mime():
    """Every MIME the filter accepts has at least one extension that maps onto it.

    Otherwise a provider answering in extensions could never produce an acceptable asset,
    which is the class of bug this module exists to prevent.
    """
    mapped = set(media.EXTENSION_MIMES.values())
    assert media.IMAGE_MIMES <= mapped, media.IMAGE_MIMES - mapped
