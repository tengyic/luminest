"""Pins the *formal* Lumi art set.

Lumi has exactly one approved look: the painterly, soft-lit cream creature with an
asterisk crest and a glowing amber ember in the belly, rendered from
``outputs/luminfest-avatar/lumi-master.png`` (brand page: ``Lumi-Avatar-Spec.html``).
A flat vector illustration of the same character circulates as a reference sketch and is
**not** a Lumi asset - it was rejected for the app. Only the painterly render ships.

A test cannot judge "painterly", so this file does not pretend to. What it can pin is the
signature the formal renders leave behind, which a flat vector cut-out cannot fake:

* exactly seven files, named after ``LumiSprite``'s raw values - no extras, no gaps;
* 256x256, 8-bit, colour type 6 (RGBA) - the format ``normalise.py`` + ``make_alpha.py``
  emit, not a JPEG or a downscaled vector export;
* a **matted** alpha channel: 2-8% of pixels are partially transparent because the
  distance matte feathers the edge. A vector cut-out is ~0.5% partial, so a swap to the
  flat style fails here;
* the figure occupies ~60% of the canvas height, the constant ``LumiArt.fill`` divides by.
  Art that ignored the pipeline's normalise step would break every call site's sizing.

If someone legitimately regenerates the seven renders from the master, all of the above
still holds and this file stays green - which is the point. It fails on a *different*
kind of art, not on new art.
"""
import re
import struct
import zlib
from functools import lru_cache
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
LUMI = ROOT / "harness" / "native" / "Sources" / "LearningHarness" / "Resources" / "Lumi"
SWIFT = ROOT / "harness" / "native" / "Sources" / "LearningHarness" / "LumiCompanion.swift"

# The seven formal sprites: six moods plus the blink frame.
FORMAL = {
    "idle",
    "blink",
    "greeting",
    "listening",
    "thinking",
    "celebrating",
    "resting",
}


def _paeth(left: int, up: int, upleft: int) -> int:
    p = left + up - upleft
    pa, pb, pc = abs(p - left), abs(p - up), abs(p - upleft)
    if pa <= pb and pa <= pc:
        return left
    return up if pb <= pc else upleft


def _unfilter(kind: int, line: bytearray, prev: bytes, bpp: int) -> None:
    if kind == 0:
        return
    if kind == 1:
        for i in range(bpp, len(line)):
            line[i] = (line[i] + line[i - bpp]) & 0xFF
    elif kind == 2:
        for i in range(len(line)):
            line[i] = (line[i] + prev[i]) & 0xFF
    elif kind == 3:
        for i in range(len(line)):
            left = line[i - bpp] if i >= bpp else 0
            line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
    elif kind == 4:
        for i in range(len(line)):
            left = line[i - bpp] if i >= bpp else 0
            upleft = prev[i - bpp] if i >= bpp else 0
            line[i] = (line[i] + _paeth(left, prev[i], upleft)) & 0xFF
    else:  # pragma: no cover - malformed file
        raise AssertionError(f'unknown PNG filter type {kind}')


@lru_cache(maxsize=None)
def _decode(path: str):
    """Return (width, height, depth, colour_type, alpha) for a PNG, stdlib only.

    Pillow is deliberately not used: it is not a declared backend requirement, and a test
    that quietly needs an undeclared dependency is the thing
    ``test_packaging_manifest`` exists to prevent.
    """
    data = Path(path).read_bytes()
    assert data[:8] == b'\x89PNG\r\n\x1a\n', f'{path} is not a PNG'

    header = None
    payload = bytearray()
    pos = 8
    while pos + 8 <= len(data):
        length = int.from_bytes(data[pos:pos + 4], 'big')
        kind = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        if kind == b'IHDR':
            header = struct.unpack('>IIBBBBB', chunk)
        elif kind == b'IDAT':
            payload += chunk
        elif kind == b'IEND':
            break
        pos += 12 + length

    assert header is not None, f'{path} has no IHDR'
    width, height, depth, colour, _compression, _filter, interlace = header
    if (depth, colour, interlace) != (8, 6, 0):
        # Not decodable by the simple path below; the caller asserts the format first.
        return width, height, depth, colour, None

    stride = width * 4
    raw = zlib.decompress(bytes(payload))
    prev = bytes(stride)
    alpha = bytearray()
    offset = 0
    for _ in range(height):
        kind = raw[offset]
        offset += 1
        line = bytearray(raw[offset:offset + stride])
        offset += stride
        _unfilter(kind, line, prev, 4)
        alpha += line[3::4]
        prev = bytes(line)
    return width, height, depth, colour, bytes(alpha)


def _sprites():
    return sorted(LUMI.glob('*.png'))


def test_the_resource_set_is_exactly_the_seven_formal_sprites():
    names = {path.stem.removeprefix('lumi-') for path in _sprites()}
    assert names == FORMAL, (
        'the Lumi resource folder must hold exactly the formal set; '
        f'missing={sorted(FORMAL - names)} unexpected={sorted(names - FORMAL)}'
    )


def test_the_shipped_files_match_the_swift_sprite_enum():
    # A renamed PNG renders a sage dot instead of a face, silently. LumiArt resolves
    # `lumi-<rawValue>.png`, so the enum and the folder have to agree by name.
    source = SWIFT.read_text('utf-8')
    match = re.search(r'enum LumiSprite: String, CaseIterable, Equatable \{\s*case ([^\n}]+)', source)
    assert match, 'LumiSprite declaration moved; update this test rather than deleting it'
    cases = {token.strip() for token in match.group(1).split(',') if token.strip()}
    assert cases == FORMAL, f'LumiSprite cases {sorted(cases)} do not match the formal set'


def test_every_sprite_is_a_256_square_rgba_render():
    for path in _sprites():
        width, height, depth, colour, alpha = _decode(str(path))
        assert (width, height) == (256, 256), f'{path.name} is {width}x{height}, not 256x256'
        assert (depth, colour) == (8, 6), f'{path.name} is not 8-bit RGBA (depth={depth}, colour={colour})'
        assert alpha is not None, f'{path.name} is interlaced; the render pipeline emits non-interlaced PNGs'


def test_every_sprite_is_a_matted_render_not_a_flat_cutout():
    for path in _sprites():
        alpha = _decode(str(path))[4]
        total = len(alpha)
        partial = sum(1 for value in alpha if 0 < value < 255) / total
        assert 0.02 <= partial <= 0.08, (
            f'{path.name} has {partial:.2%} feathered edge pixels; the formal renders sit near 3.5% '
            'and a flat vector cut-out near 0.5% - this is the wrong Lumi art'
        )
        assert alpha[0] == 0, f'{path.name} is not matted: the corner pixel is opaque'


def test_the_figure_fills_the_canvas_the_way_lumiart_expects():
    # LumiArt.fill = 0.60 and LumiSpriteView divides by it, so a figure authored at another
    # scale makes the companion wrong by the same factor everywhere it appears.
    for path in _sprites():
        width, height, alpha = _decode(str(path))[0], _decode(str(path))[1], _decode(str(path))[4]
        xs = [i % width for i, value in enumerate(alpha) if value > 8]
        ys = [i // width for i, value in enumerate(alpha) if value > 8]
        assert xs and ys, f'{path.name} is empty'
        tall = (max(ys) - min(ys) + 1) / height
        wide = (max(xs) - min(xs) + 1) / width
        assert 0.58 <= tall <= 0.68, f'{path.name} fills {tall:.2%} of the canvas height, expected ~60%'
        assert 0.35 <= wide <= 0.60, f'{path.name} fills {wide:.2%} of the canvas width'
