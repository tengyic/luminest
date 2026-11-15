"""Narrate a deck: one mp3 per slide, a timing table, and one stitched transcript track.

The lesson stops being interactive here. Each slide's own words - its title, its bullets, its
caption - are spoken by VoiceStudio through the harness route that the app's read-aloud button
already uses, so the voice a learner hears in the video is the voice the tutor speaks in.

Durations are measured from the files, never estimated from word counts: the point of the
exercise is that the slide changes when the sentence ends.

    backend/.venv/bin/python -u scripts/narrate_deck.py --deck outputs/2.7-forgetting.pptx
"""
from __future__ import annotations

import argparse
import json
import secrets
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from pptx import Presentation

API = '/api/v1'


def call(base: str, path: str, payload=None, token: str = '', raw: bool = False):
    data = json.dumps(payload).encode() if payload is not None else None
    method = 'POST' if data else 'GET'
    request = urllib.request.Request(base + path, data=data, method=method)
    request.add_header('content-type', 'application/json')
    if token:
        request.add_header('authorization', 'Bearer ' + token)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=900) as response:
        body = response.read()
        return response.status, (body if raw else json.loads(body or b'{}'))


def register(base: str) -> str:
    email = f'narrator-{secrets.token_hex(4)}@course.test'
    status, body = call(base, f'{API}/auth/register',
                        {'name': 'narrator', 'email': email,
                         'password': secrets.token_urlsafe(12)})
    if status not in (200, 201) or 'token' not in body:
        raise SystemExit(f'register failed: {status} {str(body)[:200]}')
    return body['token']


def slide_script(slide) -> tuple[str, str]:
    """The spoken text and the on-slide title, taken from the shapes themselves."""
    title, bullets, caption = '', [], ''
    for shape in slide.shapes:
        if not shape.has_text_frame or not shape.text_frame.text.strip():
            continue
        runs = [run for paragraph in shape.text_frame.paragraphs for run in paragraph.runs]
        size = runs[0].font.size.pt if runs and runs[0].font.size else 0
        bold = bool(runs[0].font.bold) if runs else False
        text = ' '.join(shape.text_frame.text.split())
        if text.upper().startswith('AP PSYCHOLOGY'):
            # The running header is furniture, not narration. Reading it aloud at the top of
            # every slide is what made the audio sound like it belonged to another page.
            continue
        if bold and size >= 28 and not title:
            title = text
        elif size <= 10:
            caption = text
        else:
            bullets.extend(line.strip(' ▪') for line in shape.text_frame.text.split('\n')
                           if line.strip())
    spoken = '. '.join(part for part in [title] + bullets + [caption] if part)
    spoken = spoken.replace('  ·  ', ' ').replace('·', ',')
    return spoken, title


def duration_of(path: Path) -> float:
    out = subprocess.run(['/usr/bin/afinfo', str(path)], capture_output=True, text=True).stdout
    for line in out.splitlines():
        if 'estimated duration' in line:
            return round(float(line.split(':')[1].strip().split(' ')[0]), 3)
    return 0.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--deck', default='outputs/2.7-forgetting.pptx')
    parser.add_argument('--base', default='http://127.0.0.1:8877')
    parser.add_argument('--out', default='outputs/narration')
    parser.add_argument('--voice', default='')
    parser.add_argument('--limit', type=int, default=0, help='stop after N slides')
    parser.add_argument('--pause', type=float, default=0.8,
                        help='seconds of silence after a slide before the next one')
    args = parser.parse_args()

    deck = Path(args.deck)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    token = register(args.base)
    print(f'registered narrator, token {token[:8]}…')

    presentation = Presentation(deck)
    timings = []
    for index, slide in enumerate(presentation.slides, 1):
        if args.limit and index > args.limit:
            break
        spoken, title = slide_script(slide)
        if not spoken:
            continue
        target = out_dir / f'slide-{index:02}.mp3'
        if not target.exists() or target.stat().st_size < 2000:
            status, audio = call(args.base, f'{API}/voice/speak',
                                 {'text': spoken, 'voice': args.voice, 'wait': True}, token, raw=True)
            if status != 200 or not isinstance(audio, bytes) or len(audio) < 2000:
                print(f'  s{index:02} SPEAK FAILED {status}')
                continue
            target.write_bytes(audio)
        seconds = duration_of(target)
        timings.append({'slide': index, 'title': title, 'mp3': target.name,
                        'seconds': seconds, 'advance': round(seconds + args.pause, 2),
                        'text': spoken})
        print(f'  s{index:02} {seconds:6.2f}s  {title[:52]}')

    total = sum(row['seconds'] for row in timings)
    (out_dir / 'timings.json').write_text(json.dumps(
        {'deck': str(deck), 'total_seconds': round(total, 2), 'slides': timings},
        indent=1, ensure_ascii=False), encoding='utf-8')

    # One continuous track: mp3 streams concatenate, and the result is what a learner opens
    # when they want to listen without the slides.
    stitch = out_dir / 'lesson.mp3'
    with stitch.open('wb') as handle:
        for row in timings:
            handle.write((out_dir / row['mp3']).read_bytes())
    print(f'\n{len(timings)} slide(s), {total/60:.1f} min total')
    print(f'wrote {stitch}  ({stitch.stat().st_size/1e6:.1f} MB)')
    print(f'wrote {out_dir / "timings.json"}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
