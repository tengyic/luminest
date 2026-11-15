"""Measure a set of reference lesson decks so a template can be derived from facts.

Nothing here is a matter of taste: fonts, sizes, weights, colours, rules, block geometry,
definition sentence shapes and question stems are all read out of the files. The output is a
JSON file plus a short report, so a template spec can cite numbers rather than impressions.

    backend/.venv/bin/python -u scripts/analyze_deck_references.py \
        --glob "~/Downloads/[12].*.pdf" --out outputs/reference-analysis.json
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import re
import statistics
from pathlib import Path

import pymupdf

DEFINITION = re.compile(r'^(?P<term>[A-Z][^.:;]{2,58}?)\s+(?:is|are|refers to|means)\s+(?P<body>.{15,})$')
QUESTION = re.compile(r'\?\s*$')
CHOICE = re.compile(r'^(?:[A-D][).]|[a-d][).])\s+\S')
NUMBERED = re.compile(r'^\s*(?:\d+[.)]|[•▪◦])\s+\S')


def colour_of(span: dict) -> str:
    value = int(span.get('color') or 0)
    return '#%06x' % (value & 0xFFFFFF)


def underline_like(page, spans) -> int:
    """How many text lines have a drawn rule within 3pt under them.

    PyMuPDF does not expose underline as a text flag consistently across producers, so the
    rule is measured from the page's own vector line segments instead: a line whose y sits
    just below a text baseline and whose x range overlaps the text.
    """
    lines = []
    for drawing in page.get_drawings():
        for item in drawing.get('items', []):
            if item[0] == 'l':
                lines.append((item[1], item[2]))
            elif item[0] == 're':
                rect = item[1]
                if rect.height <= 3:
                    lines.append(((rect.x0, rect.y0), (rect.x1, rect.y0)))
    count = 0
    for block in spans:
        bbox = block['bbox']
        for (x0, y0), (x1, y1) in lines:
            if abs(y0 - y1) > 1.5:
                continue
            if bbox[1] + 1 <= y0 <= bbox[3] + 4 and x0 <= bbox[0] + 4 and x1 >= bbox[2] - 4:
                count += 1
                break
    return count


def analyse(path: Path, pages: int) -> dict:
    doc = pymupdf.open(path)
    fonts: collections.Counter = collections.Counter()
    sizes: collections.Counter = collections.Counter()
    colours: collections.Counter = collections.Counter()
    page_reports = []
    definitions, questions, choices, images = [], [], 0, []

    for index in range(min(doc.page_count, pages)):
        page = doc[index]
        page_area = page.rect.width * page.rect.height
        raw = page.get_text('dict')
        spans, lines = [], []
        for block in raw.get('blocks', []):
            for line in block.get('lines', []):
                text = ''.join(s.get('text', '') for s in line.get('spans', []))
                if not text.strip():
                    continue
                lines.append({'bbox': line['bbox'], 'text': text})
                for span in line.get('spans', []):
                    if not span.get('text', '').strip():
                        continue
                    spans.append({'bbox': span['bbox'], 'size': round(span['size'], 1),
                                  'font': span.get('font', ''), 'flags': span.get('flags', 0),
                                  'colour': colour_of(span)})
                    fonts[span.get('font', '')] += len(span.get('text', ''))
                    sizes[round(span['size'], 1)] += len(span.get('text', ''))
                    colours[colour_of(span)] += len(span.get('text', ''))
        if not spans:
            continue
        median = statistics.median([s['size'] for s in spans])
        headings = [s for s in spans if s['size'] >= median * 1.25]
        title = max(spans, key=lambda s: s['size'])
        underlined = underline_like(page, lines)

        pictures = []
        for info in page.get_image_info():
            x0, y0, x1, y1 = info['bbox']
            area = (x1 - x0) * (y1 - y0)
            pictures.append({'frac': round(area / page_area, 3),
                             'aspect': round((x1 - x0) / max(1, (y1 - y0)), 2)})

        # Content box: the bbox of every text line, which is what a template's margins mean.
        left = min(l['bbox'][0] for l in lines)
        right = max(l['bbox'][2] for l in lines)
        top = min(l['bbox'][1] for l in lines)
        bottom = max(l['bbox'][3] for l in lines)

        for line in lines:
            text = ' '.join(line['text'].split())
            if DEFINITION.match(text) and len(text) < 260:
                definitions.append({'page': index + 1, 'text': text[:200]})
            if QUESTION.search(text):
                questions.append({'page': index + 1, 'text': text[:200]})
            if CHOICE.match(text) or NUMBERED.match(text):
                choices += 1

        page_reports.append({
            'page': index + 1, 'lines': len(lines), 'median_pt': round(median, 1),
            'title_pt': round(title['size'], 1), 'title_font': title['font'],
            'headings_pt': sorted({round(h['size'], 1) for h in headings})[:6],
            'underlined_lines': underlined,
            'pictures': pictures,
            'margins': {'left': round(left), 'right': round(page.rect.width - right),
                        'top': round(top), 'bottom': round(page.rect.height - bottom)},
            'body_colours': collections.Counter(s['colour'] for s in spans).most_common(4),
        })
        images.extend(pictures)

    return {
        'file': path.name, 'pages': doc.page_count,
        'analysed_pages': len(page_reports),
        'page_size': (round(doc[0].rect.width), round(doc[0].rect.height)) if doc.page_count else (0, 0),
        'fonts': fonts.most_common(6),
        'sizes': sizes.most_common(8),
        'colours': colours.most_common(6),
        'definitions': definitions[:8],
        'definition_count': len(definitions),
        'questions': questions[:6],
        'question_count': len(questions),
        'choice_lines': choices,
        'images': {'count': len(images),
                   'big': sum(1 for i in images if i['frac'] >= 0.12),
                   'aspects': collections.Counter(i['aspect'] for i in images).most_common(5)},
        'pages_detail': page_reports,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--glob', action='append', default=[])
    parser.add_argument('--pages', type=int, default=10)
    parser.add_argument('--out', default='outputs/reference-analysis.json')
    args = parser.parse_args()

    patterns = args.glob or ['~/Downloads/*.pdf']
    paths: list[Path] = []
    for pattern in patterns:
        paths.extend(Path(p).expanduser() for p in glob.glob(os.path.expanduser(pattern)))
    paths = sorted({p.resolve() for p in paths if p.suffix.lower() == '.pdf'})
    print(f'{len(paths)} file(s)')

    reports = []
    for path in paths:
        try:
            reports.append(analyse(path, args.pages))
        except Exception as error:  # noqa: BLE001 - a broken file must not stop the survey
            print(f'  !! {path.name}: {type(error).__name__}: {error}')

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(reports, indent=1, ensure_ascii=False), encoding='utf-8')

    for report in reports:
        pages = report['pages_detail']
        if not pages:
            continue
        lefts = [p['margins']['left'] for p in pages]
        tops = [p['margins']['top'] for p in pages]
        print('=' * 74)
        print(f"{report['file']}  {report['pages']}p  {report['page_size'][0]}x{report['page_size'][1]}")
        print(f"  fonts      : {', '.join(f'{f} ({n})' for f, n in report['fonts'][:3])}")
        print(f"  sizes(pt)  : {', '.join(f'{s}pt×{n}' for s, n in report['sizes'][:5])}")
        print(f"  colours    : {', '.join(f'{c}×{n}' for c, n in report['colours'][:3])}")
        print(f"  margins    : left {min(lefts)}-{max(lefts)}  top {min(tops)}-{max(tops)}")
        print(f"  underlined : {sum(p['underlined_lines'] for p in pages)} line(s) "
              f"over {len(pages)} page(s)")
        print(f"  images     : {report['images']['count']} total, "
              f"{report['images']['big']} covering >=12% of a page")
        print(f"  definitions: {report['definition_count']}  questions: {report['question_count']}"
              f"  option lines: {report['choice_lines']}")
    print(f'\nwrote {out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
