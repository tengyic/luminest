"""Third pass: pull the assets and the two content patterns out of a reference deck.

  * image assets, de-duplicated by content hash, saved with a manifest entry (page, size,
    the caption found near it, and the fraction of the page it covered);
  * definition units - a bold or larger run naming a term, and the sentence that explains it;
  * question units - a stem ending in a question mark plus the option lines that follow it.

These three are what a template actually needs: the geometry says where things go, this says
what the things are.

    backend/.venv/bin/python -u scripts/extract_reference_assets.py \
        --glob "/Users/tengyi/Downloads/[0-2].*.pdf" --out outputs/reference-assets
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import statistics
from pathlib import Path

import pymupdf

QUESTION = re.compile(r'\?\s*$')
OPTION = re.compile(r'^\s*(?:[A-Da-d][).]|\d[).]|[•▪◦❏])\s*(?P<body>\S.{0,220})$')


def near_caption(spans, hero) -> str:
    """The smallest text immediately under or beside a picture - the photographer's line."""
    if not hero:
        return ''
    hx0, hy0, hx1, hy1 = hero
    best = ''
    for span in spans:
        bbox = span['bbox']
        inside_x = bbox[2] > hx0 - 24 and bbox[0] < hx1 + 24
        below = hy1 - 6 <= bbox[1] <= hy1 + 48
        beside = bbox[0] >= hx1 - 6 and hy0 - 12 <= bbox[1] <= hy1
        if inside_x and (below or beside) and span['size'] <= span['median'] * 0.9:
            text = span['text'].strip()
            if len(text) > len(best):
                best = text
    return best[:180]


def analyse(path: Path, out_dir: Path, pages: int, seen: dict) -> dict:
    doc = pymupdf.open(path)
    stem = path.stem.replace(' ', '_')[:40]
    target = out_dir / stem
    definitions, questions, assets = [], [], []

    for index in range(min(doc.page_count, pages)):
        page = doc[index]
        width, height = page.rect.width, page.rect.height
        spans = []
        for block in page.get_text('dict').get('blocks', []):
            for line in block.get('lines', []):
                for span in line.get('spans', []):
                    text = span.get('text', '').strip()
                    if not text:
                        continue
                    spans.append({'text': ''.join(text.split()), 'bbox': span['bbox'],
                                  'size': round(span['size'], 1),
                                  'bold': bool(span.get('flags', 0) & 2 ** 4)})
        if not spans:
            continue
        median = statistics.median(s['size'] for s in spans)
        for span in spans:
            span['median'] = median

        # --- definitions: a short emphasise run, then a sentence that explains it
        for i, span in enumerate(spans[:-1]):
            emphasise = span['bold'] or span['size'] >= median * 1.15
            if not emphasise or not (2 <= len(span['text'].split()) <= 7):
                continue
            follower = spans[i + 1]
            if follower['size'] > median * 1.3:
                continue
            body = follower['text']
            if len(body) < 25 or body.lower().startswith(('module', 'unit', 'ap®')):
                continue
            definitions.append({'file': path.name, 'page': index + 1,
                                'term': span['text'][:70], 'definition': body[:220]})
            break  # one per page keeps the sample readable

        # --- questions: a stem, then option-shaped lines
        for i, span in enumerate(spans):
            if not QUESTION.search(span['text']) or len(span['text']) < 25:
                continue
            options = []
            for follower in spans[i + 1:i + 6]:
                match = OPTION.match(follower['text'])
                if match:
                    options.append(match.group('body')[:120])
                elif options:
                    break
            questions.append({'file': path.name, 'page': index + 1,
                              'stem': span['text'][:240], 'options': options[:5]})
            break

        # --- assets
        infos = [i for i in page.get_image_info(xrefs=True)]
        hero = None
        for info in infos:
            x0, y0, x1, y1 = info['bbox']
            frac = ((x1 - x0) * (y1 - y0)) / (width * height)
            if frac >= 0.25 and (hero is None or frac > hero[4]):
                hero = (x0, y0, x1, y1, frac)
        caption = near_caption(spans, hero[:4] if hero else None)
        for info in infos:
            x0, y0, x1, y1 = info['bbox']
            frac = ((x1 - x0) * (y1 - y0)) / (width * height)
            if frac < 0.05:
                continue
            xref = info.get('xref') or 0
            if not xref:
                continue
            try:
                raw = doc.extract_image(xref)
            except Exception:  # noqa: BLE001 - a broken xref is one missing picture
                continue
            blob = raw.get('image') or b''
            if len(blob) < 4000:
                continue
            sha = hashlib.sha256(blob).hexdigest()
            if sha in seen:
                continue
            target.mkdir(parents=True, exist_ok=True)
            name = f'{sha[:16]}.{raw.get("ext", "png")}'
            (target / name).write_bytes(blob)
            seen[sha] = {'file': name, 'source': path.name, 'page': index + 1,
                         'width': raw.get('width'), 'height': raw.get('height'),
                         'page_fraction': round(frac, 3), 'caption': caption}
            assets.append(seen[sha])
    return {'file': path.name, 'assets': assets, 'definitions': definitions,
            'questions': questions}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--glob', action='append', default=[])
    parser.add_argument('--pages', type=int, default=14)
    parser.add_argument('--out', default='outputs/reference-assets')
    args = parser.parse_args()

    patterns = args.glob or ['~/Downloads/*.pdf']
    paths: list[Path] = []
    for pattern in patterns:
        paths.extend(Path(p).expanduser() for p in glob.glob(os.path.expanduser(pattern)))
    paths = sorted({p.resolve() for p in paths if p.suffix.lower() == '.pdf'})

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    seen: dict = {}
    reports = [analyse(path, out_dir, args.pages, seen) for path in paths]

    (out_dir / 'manifest.json').write_text(
        json.dumps({'assets': list(seen.values()), 'files': reports},
                   indent=1, ensure_ascii=False), encoding='utf-8')

    files = list(out_dir.rglob('*.png')) + list(out_dir.rglob('*.jpeg')) + \
        list(out_dir.rglob('*.jpg'))
    print(f'assets written: {len(files)} files, '
          f'{sum(f.stat().st_size for f in files) / 1e6:.1f} MB')
    for report in reports:
        print(f"  {report['file'][:50]:52} assets={len(report['assets']):3} "
              f"definitions={len(report['definitions']):2} questions={len(report['questions'])}")
    print('\nfirst definitions:')
    for row in [d for r in reports for d in r['definitions']][:5]:
        print(f"  [{row['term']}] → {row['definition'][:90]}")
    print('\nquestions with options:')
    for row in [q for r in reports for q in r['questions'] if q['options']][:4]:
        print(f"  {row['stem'][:80]}")
        for option in row['options'][:3]:
            print(f'     - {option[:70]}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
