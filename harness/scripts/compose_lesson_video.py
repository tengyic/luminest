"""Turn a narrated deck into a lesson someone can just watch.

Two outputs, from the same timing table:

  * ``.mp4`` - each slide held for exactly as long as its own narration, so the page turns
    when the sentence ends. This is the "uninteractive course": press play, stop thinking
    about the controls;
  * the deck with ``advTm`` written into every slide's transition, so PowerPoint's own
    Slide Show advances by itself if the learner opens the file instead of the video.

Durations come from ``narration/timings.json``, which was measured from the audio files, not
estimated from word counts.

    backend/.venv/bin/python -u scripts/compose_lesson_video.py \
        --deck outputs/2.7-forgetting.pptx --timings outputs/narration/timings.json
"""
from __future__ import annotations

import argparse
import base64
import html
import json
import re
import subprocess
from copy import deepcopy
from pathlib import Path

from lxml import etree
from playwright.sync_api import sync_playwright
from pptx import Presentation

P = 12700.0
NS = {'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
      'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'}


def slide_html(slide) -> str:
    """The slide as absolutely positioned HTML, so Chromium can photograph it."""
    items = []
    for shape in slide.shapes:
        x, y = (shape.left or 0) / P, (shape.top or 0) / P
        w, h = (shape.width or 0) / P, (shape.height or 0) / P
        if shape.shape_type == 13:
            uri = 'data:%s;base64,%s' % (shape.image.content_type,
                                         base64.b64encode(shape.image.blob).decode())
            cropped = any((shape.crop_left, shape.crop_right, shape.crop_top, shape.crop_bottom))
            fit = 'cover' if cropped else 'contain'
            items.append(f'<div style="position:absolute;left:{x}px;top:{y}px;width:{w}px;'
                         f'height:{h}px;overflow:hidden"><img src="{uri}" '
                         f'style="width:100%;height:100%;object-fit:{fit}"></div>')
        elif shape.has_text_frame and shape.text_frame.text.strip():
            paragraphs = []
            for paragraph in shape.text_frame.paragraphs:
                runs = []
                for run in paragraph.runs:
                    size = run.font.size.pt if run.font.size else 16
                    bold = 600 if run.font.bold else 400
                    colour = (f'#{run.font.color.rgb}'
                              if run.font.color and run.font.color.type is not None else '#111')
                    runs.append(f'<span style="font-size:{size}px;font-weight:{bold};'
                                f'color:{colour}">{html.escape(run.text)}</span>')
                if runs:
                    paragraphs.append(f'<div style="line-height:1.3">{"".join(runs)}</div>')
            if paragraphs:
                items.append(f'<div style="position:absolute;left:{x}px;top:{y}px;width:{w}px;'
                             f'height:{h}px">{"".join(paragraphs)}</div>')
    return ''.join(items)


def render_slides(deck: Path, out_dir: Path) -> list[Path]:
    presentation = Presentation(deck)
    out_dir.mkdir(parents=True, exist_ok=True)
    bodies = [f'<div class="s">{slide_html(slide)}</div>' for slide in presentation.slides]
    page = ('<html><meta charset="utf-8"><style>body{margin:0;background:#fff;'
            'font-family:Arial,Helvetica,sans-serif}.s{position:relative;width:960px;'
            'height:540px;background:#fff;overflow:hidden}</style>' + ''.join(bodies) + '</html>')
    document = out_dir / 'slides.html'
    document.write_text(page, encoding='utf-8')

    shots = []
    with sync_playwright() as driver:
        browser = driver.chromium.launch()
        view = browser.new_page(viewport={'width': 960, 'height': 540}, device_scale_factor=2)
        view.goto('file://' + str(document.resolve()))
        view.wait_for_timeout(600)
        tiles = view.locator('.s')
        for index in range(tiles.count()):
            target = out_dir / f'slide-{index + 1:02}.png'
            tiles.nth(index).screenshot(path=str(target))
            shots.append(target)
        browser.close()
    return shots


def write_advance_times(deck: Path, out_deck: Path, timings: dict) -> None:
    """Give every slide an automatic advance, in milliseconds."""
    presentation = Presentation(deck)
    by_slide = {row['slide']: row for row in timings['slides']}
    for index, slide in enumerate(presentation.slides, 1):
        row = by_slide.get(index)
        if not row:
            continue
        element = slide.element
        trans = element.find('p:transition', NS)
        if trans is None:
            trans = etree.SubElement(element, '{%s}transition' % NS['p'])
        # advTm is in milliseconds; PowerPoint shows the slide for that long, then advances.
        trans.set('advTm', str(int(round(row['advance'] * 1000))))
        trans.set('spd', 'med')
    presentation.save(out_deck)


def build_video(shots: list[Path], timings: dict, audio_dir: Path, out: Path, work: Path) -> None:
    """Picture and sound built separately, then muxed once.

    The first version cut one mp4 per slide and concatenated the files with ``-c copy``. That
    is where the screech at the end came from: ``-shortest`` stops coding an mp3 mid-frame,
    and joining those partial frames leaves the decoder reading noise. Here each clip is
    decoded to PCM first, given a short tail of real silence, and the whole soundtrack is
    encoded once, with a fade at the very end.
    """
    work.mkdir(parents=True, exist_ok=True)
    rows = {row['slide']: row for row in timings['slides']}

    audio_parts, image_lines, silence = [], [], 0.45
    for index, shot in enumerate(shots, 1):
        row = rows.get(index)
        if not row:
            continue
        wav = work / f'part-{index:02}.wav'
        if not wav.exists():
            subprocess.run([
                'ffmpeg', '-y', '-loglevel', 'error', '-i', str(audio_dir / row['mp3']),
                '-af', f'apad=pad_dur={silence}', '-ar', '44100', '-ac', '2',
                '-c:a', 'pcm_s16le', str(wav),
            ], check=True)
        seconds = float(subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', str(wav)],
            capture_output=True, text=True).stdout.strip() or 0)
        audio_parts.append(wav)
        image_lines.append(f"file '{shot.resolve()}'\nduration {seconds:.3f}\n")

    # The last image has to be listed twice: the concat demuxer needs an explicit final entry
    # or ffmpeg drops the tail of the last slide.
    if image_lines:
        image_lines.append(image_lines[-1])

    slides_txt = work / 'images.txt'
    slides_txt.write_text(''.join(image_lines), encoding='utf-8')
    video = work / 'video-only.mp4'
    subprocess.run([
        'ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0',
        '-i', str(slides_txt), '-fps_mode', 'cfr', '-pix_fmt', 'yuv420p',
        '-vf', 'scale=1920:1080:flags=lanczos', '-r', '30', str(video),
    ], check=True)

    audio_txt = work / 'audio.txt'
    audio_txt.write_text(''.join(f"file '{part.resolve()}'\n" for part in audio_parts),
                         encoding='utf-8')
    soundtrack = work / 'soundtrack.wav'
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0',
                    '-i', str(audio_txt), '-c', 'copy', str(soundtrack)], check=True)

    total = float(subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
         '-of', 'default=noprint_wrappers=1:nokey=1', str(soundtrack)],
        capture_output=True, text=True).stdout.strip() or 0)
    fade_start = max(0.0, total - 0.6)
    subprocess.run([
        'ffmpeg', '-y', '-loglevel', 'error', '-i', str(video), '-i', str(soundtrack),
        '-map', '0:v', '-map', '1:a', '-c:v', 'copy',
        '-af', f'afade=t=out:st={fade_start:.2f}:d=0.6,highpass=f=60',
        '-c:a', 'aac', '-b:a', '160k', '-shortest', str(out),
    ], check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--deck', default='outputs/2.7-forgetting.pptx')
    parser.add_argument('--timings', default='outputs/narration/timings.json')
    parser.add_argument('--audio', default='outputs/narration')
    parser.add_argument('--out', default='outputs/2.7-forgetting-lesson.mp4')
    parser.add_argument('--narrated-deck', default='outputs/2.7-forgetting-narrated.pptx')
    args = parser.parse_args()

    deck = Path(args.deck)
    timings = json.loads(Path(args.timings).read_text(encoding='utf-8'))
    shots = render_slides(deck, Path('outputs/narration/frames'))
    print(f'rendered {len(shots)} slide image(s)')

    write_advance_times(deck, Path(args.narrated_deck), timings)
    print(f'wrote {args.narrated_deck} with automatic advance times')

    build_video(shots, timings, Path(args.audio), Path(args.out), Path('outputs/narration/parts'))
    size = Path(args.out).stat().st_size / 1e6
    print(f'wrote {args.out}  ({size:.1f} MB)  {timings["total_seconds"]/60:.1f} min')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
