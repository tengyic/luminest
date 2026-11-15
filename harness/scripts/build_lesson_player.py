"""One HTML file that plays the narrated lesson: click once, it runs to the end.

Why a player and not only a deck: a PowerPoint only auto-plays its narration when the media
objects are wired into the slide's timing tree, which cannot be verified on a machine without
PowerPoint. A browser is on every machine and can be driven here, so this is the artifact that
is actually checked before it is handed over.

The audio is the clock. When a clip ends the next slide appears - no timers, no drift, and a
slow machine simply takes longer rather than showing the wrong picture.

    backend/.venv/bin/python -u scripts/build_lesson_player.py \
        --deck outputs/2.7-forgetting.pptx --out outputs/2.7-forgetting-lesson.html
"""
from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path


def embed(path: Path, mime: str) -> str:
    return f'data:{mime};base64,' + base64.b64encode(path.read_bytes()).decode()


TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{title}</title>
<style>
  html, body {{ margin: 0; height: 100%; background: #12141a; color: #e8e6e1;
    font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif; }}
  #wrap {{ display: flex; flex-direction: column; align-items: center;
    justify-content: center; min-height: 100%; gap: 14px; }}
  #stage {{ position: relative; width: min(96vw, 1280px); aspect-ratio: 16 / 9;
    background: #fff; box-shadow: 0 18px 50px rgba(0,0,0,.45); overflow: hidden; }}
  #stage img {{ position: absolute; inset: 0; width: 100%; height: 100%; object-fit: contain;
    display: none; }}
  #stage img.on {{ display: block; }}
  #play {{ position: absolute; inset: 0; display: flex; align-items: center;
    justify-content: center; cursor: pointer; background: rgba(12,14,18,.55);
    transition: opacity .25s ease; }}
  #play.hidden {{ opacity: 0; pointer-events: none; }}
  #play span {{ padding: 18px 34px; border-radius: 999px; background: #fff; color: #073046;
    font-size: 20px; font-weight: 700; letter-spacing: .2px; }}
  #bar {{ display: flex; align-items: center; gap: 16px; width: min(96vw, 1280px);
    font-size: 13px; color: #9aa0aa; }}
  #bar b {{ color: #e8e6e1; font-weight: 600; }}
  #track {{ flex: 1; height: 3px; background: #2b2f38; border-radius: 2px; overflow: hidden; }}
  #fill {{ height: 100%; width: 0%; background: #fa5041; transition: width .2s linear; }}
  #caption {{ width: min(96vw, 1280px); font-size: 14px; color: #9aa0aa; min-height: 20px; }}
</style></head>
<body>
<div id="wrap">
  <div id="stage">
    {images}
    <div id="play"><span>&#9654; Play lesson</span></div>
  </div>
  <div id="bar"><b id="counter">1 / {count}</b><div id="track"><div id="fill"></div></div>
    <span id="total"></span></div>
  <div id="caption"></div>
</div>
<audio id="voice" preload="auto"></audio>
<script>
const clips = {clips};
const titles = {titles};
const images = Array.from(document.querySelectorAll('#stage img'));
const voice = document.getElementById('voice');
const play = document.getElementById('play');
const counter = document.getElementById('counter');
const fill = document.getElementById('fill');
const caption = document.getElementById('caption');
const total = document.getElementById('total');
let index = -1;

const clock = (s) => Math.floor(s / 60) + ':' + String(Math.round(s % 60)).padStart(2, '0');
total.textContent = clock({total_seconds});

function show(i) {{
  images.forEach((img, k) => img.classList.toggle('on', k === i));
  counter.textContent = (i + 1) + ' / ' + images.length;
  caption.textContent = titles[i] || '';
}}

function start(i) {{
  index = i;
  show(i);
  voice.src = clips[i];
  // The clip is the clock: the page turns when the sentence ends, not on a timer that drifts.
  voice.onended = () => (i + 1 < clips.length ? start(i + 1) : finish());
  voice.onerror = () => (i + 1 < clips.length ? start(i + 1) : finish());
  voice.play().catch(() => {{}});
}}

function finish() {{
  fill.style.width = '100%';
  play.querySelector('span').textContent = '&#8635; Play again';
  play.classList.remove('hidden');
  index = -1;
}}

voice.ontimeupdate = () => {{
  if (!voice.duration) return;
  const done = clips.slice(0, Math.max(index, 0)).reduce((a, c) => a, 0);
  const before = {starts}[Math.max(index, 0)] || 0;
  fill.style.width = Math.min(100, ((before + voice.currentTime) / {total_seconds}) * 100) + '%';
}};

play.onclick = () => {{ play.classList.add('hidden'); start(0); }};
document.addEventListener('keydown', (e) => {{
  if (e.key === ' ' && index < 0) {{ e.preventDefault(); play.click(); }}
}});
show(0);
</script>
</body></html>
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--frames', default='outputs/narration/frames')
    parser.add_argument('--audio', default='outputs/narration')
    parser.add_argument('--timings', default='outputs/narration/timings.json')
    parser.add_argument('--out', default='outputs/2.7-forgetting-lesson.html')
    parser.add_argument('--title', default='Understanding Forgetting — 2.7')
    args = parser.parse_args()

    timings = json.loads(Path(args.timings).read_text(encoding='utf-8'))
    rows = timings['slides']
    frames = Path(args.frames)
    audio_dir = Path(args.audio)

    images, clips, titles, starts = [], [], [], []
    elapsed = 0.0
    for row in rows:
        frame = frames / f"slide-{row['slide']:02}.png"
        clip = audio_dir / row['mp3']
        images.append(f'<img src="{embed(frame, "image/png")}" alt="">')
        clips.append(embed(clip, 'audio/mpeg'))
        titles.append(row.get('title') or '')
        starts.append(round(elapsed, 2))
        elapsed += row['seconds']

    document = TEMPLATE.format(
        title=args.title, count=len(rows), images=''.join(images),
        clips=json.dumps(clips), titles=json.dumps(titles), starts=json.dumps(starts),
        total_seconds=round(elapsed, 2))

    out = Path(args.out)
    out.write_text(document, encoding='utf-8')
    print(f'wrote {out}  ({out.stat().st_size/1e6:.1f} MB)  slides={len(rows)}'
          f'  {elapsed/60:.1f} min  self-contained (no external files)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
