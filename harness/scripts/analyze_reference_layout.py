"""Second pass: what each page *is*, geometrically.

The first pass counted fonts and images. This one answers the questions a template needs:
where does the title sit, where does the picture sit, is there a caption, and which of a few
page archetypes does this page belong to. Every number is normalised to the page, so it can
be pasted into 960x540 without conversion.

    backend/.venv/bin/python -u scripts/analyze_reference_layout.py \
        --glob "/Users/tengyi/Downloads/[0-2].*.pdf" --out outputs/reference-layout.json
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import statistics
from pathlib import Path

import pymupdf


def norm(value: float, total: float) -> float:
    return round(value / total, 3) if total else 0.0


def analyse(path: Path, pages: int) -> dict:
    doc = pymupdf.open(path)
    archetypes: collections.Counter = collections.Counter()
    rows = []
    captions = []
    for index in range(min(doc.page_count, pages)):
        page = doc[index]
        width, height = page.rect.width, page.rect.height
        spans = []
        for block in page.get_text('dict').get('blocks', []):
            for line in block.get('lines', []):
                text = ''.join(s.get('text', '') for s in line.get('spans', [])).strip()
                if not text:
                    continue
                biggest = max(s['size'] for s in line['spans'])
                spans.append({'text': ' '.join(text.split())[:160], 'bbox': line['bbox'],
                              'size': round(biggest, 1)})
        if not spans:
            continue
        median = statistics.median(s['size'] for s in spans)
        title = max(spans, key=lambda s: s['size'])

        pictures = []
        for info in page.get_image_info():
            x0, y0, x1, y1 = info['bbox']
            frac = ((x1 - x0) * (y1 - y0)) / (width * height)
            if frac >= 0.12:
                pictures.append({'bbox': (x0, y0, x1, y1), 'frac': frac})
        pictures.sort(key=lambda p: -p['frac'])
        hero = pictures[0] if pictures else None

        if hero is None:
            archetype = 'text-only'
        elif hero['frac'] >= 0.55:
            archetype = 'image-full'
        else:
            cx = (hero['bbox'][0] + hero['bbox'][2]) / 2 / width
            h = hero['bbox'][3] - hero['bbox'][1]
            w = hero['bbox'][2] - hero['bbox'][0]
            if h / height <= 0.45 and w / width >= 0.45:
                archetype = 'image-band'
            elif cx >= 0.55:
                archetype = 'image-right'
            elif cx <= 0.45:
                archetype = 'image-left'
            else:
                archetype = 'image-centred'
        archetypes[archetype] += 1

        page_caption = ''
        if hero:
            for span in spans:
                if span['size'] > median * 0.85:
                    continue
                bbox = span['bbox']
                if (hero['bbox'][1] - 40 <= bbox[1] <= hero['bbox'][3] + 40
                        and bbox[2] > hero['bbox'][0] - 20 and bbox[0] < hero['bbox'][2] + 20):
                    page_caption = span['text']
                    break
            if page_caption:
                captions.append({'page': index + 1, 'caption': page_caption})

        body = [s for s in spans if s is not title and s['size'] >= median * 0.85]
        body_box = None
        if body:
            body_box = (min(s['bbox'][0] for s in body), min(s['bbox'][1] for s in body),
                        max(s['bbox'][2] for s in body), max(s['bbox'][3] for s in body))

        rows.append({
            'page': index + 1, 'archetype': archetype,
            'title_pt': title['size'],
            'title_at': (norm(title['bbox'][0], width), norm(title['bbox'][1], height)),
            'body_box': None if not body_box else tuple(norm(v, width if i % 2 == 0 else height)
                                                        for i, v in enumerate(body_box)),
            'hero': None if not hero else {
                'x': norm(hero['bbox'][0], width), 'y': norm(hero['bbox'][1], height),
                'w': norm(hero['bbox'][2] - hero['bbox'][0], width),
                'h': norm(hero['bbox'][3] - hero['bbox'][1], height),
                'area': round(hero['frac'], 3)},
            'caption': page_caption,
            'lines': len(spans),
        })
    return {'file': path.name, 'archetypes': archetypes.most_common(), 'pages': rows,
            'captions': captions[:10]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--glob', action='append', default=[])
    parser.add_argument('--pages', type=int, default=12)
    parser.add_argument('--out', default='outputs/reference-layout.json')
    args = parser.parse_args()

    patterns = args.glob or ['~/Downloads/*.pdf']
    paths: list[Path] = []
    for pattern in patterns:
        paths.extend(Path(p).expanduser() for p in glob.glob(os.path.expanduser(pattern)))
    paths = sorted({p.resolve() for p in paths if p.suffix.lower() == '.pdf'})

    grand: collections.Counter = collections.Counter()
    all_rows, all_captions, reports = [], [], []
    for path in paths:
        try:
            report = analyse(path, args.pages)
        except Exception as error:  # noqa: BLE001
            print(f'!! {path.name}: {type(error).__name__}: {error}')
            continue
        reports.append(report)
        grand.update(dict(report['archetypes']))
        all_rows.extend(report['pages'])
        all_captions.extend(report['captions'])
        top = dict(report['archetypes'])
        print(f"{report['file'][:52]:54} {top}")

    print('\npage archetypes across every analysed page:')
    for name, count in grand.most_common():
        print(f'   {name:16} {count:4}  {count / max(1, sum(grand.values())):.0%}')

    heroes = [r['hero'] for r in all_rows if r['hero']]
    if heroes:
        print(f'\nhero geometry (n={len(heroes)}): '
              f"x {round(statistics.median(h['x'] for h in heroes), 2)} "
              f"y {round(statistics.median(h['y'] for h in heroes), 2)} "
              f"w {round(statistics.median(h['w'] for h in heroes), 2)} "
              f"h {round(statistics.median(h['h'] for h in heroes), 2)} "
              f"area {round(statistics.median(h['area'] for h in heroes), 2)}")
    titles = [r['title_at'] for r in all_rows]
    if titles:
        print(f"title anchor: x {round(statistics.median(t[0] for t in titles), 2)} "
              f"y {round(statistics.median(t[1] for t in titles), 2)}")
    print(f'captions found: {len(all_captions)}')
    for row in all_captions[:6]:
        print(f"   p{row['page']:02} {row['caption'][:90]}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({'totals': grand.most_common(), 'files': reports},
                              indent=1, ensure_ascii=False), encoding='utf-8')
    print(f'\nwrote {out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
