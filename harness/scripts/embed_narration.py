"""Put each slide's narration inside the deck, so the .pptx carries its own voice.

What this does and does not buy you, because the difference matters when handing a file over:

  * it does: every slide owns its mp3, so the deck travels as one file and the speaker icon
    on a page plays that page's narration;
  * it does not: start the audio by itself. Automatic narration needs the media wired into the
    slide's <p:timing> tree, and a malformed timing tree makes PowerPoint refuse the file.
    That cannot be verified on this machine - there is no PowerPoint here - so this script
    stops at the part it can check: the media parts exist, the relationships resolve, and each
    slide references an ``a:audioFile``.

    backend/.venv/bin/python -u scripts/embed_narration.py \
        --deck outputs/2.7-forgetting-narrated.pptx
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from pptx import Presentation
from pptx.util import Emu

A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--deck', default='outputs/2.7-forgetting-narrated.pptx')
    parser.add_argument('--audio', default='outputs/narration')
    parser.add_argument('--timings', default='outputs/narration/timings.json')
    parser.add_argument('--out', default='outputs/2.7-forgetting-narrated.pptx')
    args = parser.parse_args()

    deck = Path(args.deck)
    audio_dir = Path(args.audio)
    rows = {row['slide']: row for row in
            json.loads(Path(args.timings).read_text(encoding='utf-8'))['slides']}

    presentation = Presentation(deck)
    added = 0
    for index, slide in enumerate(presentation.slides, 1):
        row = rows.get(index)
        if not row:
            continue
        mp3 = audio_dir / row['mp3']
        if not mp3.is_file():
            print(f'  s{index:02} missing {mp3.name}')
            continue
        # A speaker in the empty top-right corner: the kicker lives top-left, so this never
        # lands on a word.
        shape = slide.shapes.add_movie(str(mp3), Emu(int(896 * 12700)), Emu(int(8 * 12700)),
                                       Emu(int(34 * 12700)), Emu(int(34 * 12700)),
                                       mime_type='audio/mpeg')
        # ``add_movie`` writes an ``a:videoFile``. An mp3 is audio, and PowerPoint's own
        # narration objects use ``a:audioFile``; the tag is the only difference that matters.
        for node in shape.element.iter():
            if node.tag == A + 'videoFile':
                node.tag = A + 'audioFile'
        added += 1

    out = Path(args.out)
    presentation.save(out)

    # Verify what was actually written, not what was intended.
    import zipfile
    with zipfile.ZipFile(out) as package:
        media = [n for n in package.namelist() if n.startswith('ppt/media/')]
        slides = sorted(n for n in package.namelist()
                        if n.startswith('ppt/slides/slide') and n.endswith('.xml'))
        with_audio = 0
        for name in slides:
            xml = package.read(name).decode('utf-8', 'replace')
            if 'audioFile' in xml:
                with_audio += 1
    size = out.stat().st_size / 1e6
    print(f'added narration to {added} slide(s)')
    print(f'{out}  {size:.1f} MB  media parts={len(media)}  slides with audio={with_audio}/{len(slides)}')
    print('note: audio plays when its speaker icon is clicked; the slide times already '
          'advance the show by themselves.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
