"""Compose the 2.7 deck from the assets a person chose, through named templates.

Every slide is a template plus content. No slide positions anything itself, which is what
made the first version wrong in a way that was invisible until it was rendered: a full-bleed
`cover` crop put the picture over the title and cut the diagram's own labels off. A template
states where the title is and where the picture may stand, and the renderer refuses a layout
whose slots would overlap.

    backend/.venv/bin/python -u scripts/build_27_deck.py --out outputs/2.7-forgetting.pptx
"""
from __future__ import annotations

import argparse
import glob
import re
from pathlib import Path

import pymupdf
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Pt

PDF = Path.home() / 'Downloads' / '2.7 Forgetting and Memory Errors.pdf'
CLIP = Path.home() / '.workbuddy-ai' / 'clipboard-images'

INK = RGBColor(0x07, 0x30, 0x46)
BODY = RGBColor(0x11, 0x11, 0x11)
MUTED = RGBColor(0x6B, 0x72, 0x80)
PAPER = RGBColor(0xFF, 0xFF, 0xFF)
RULE = RGBColor(0xDE, 0xD9, 0xD0)

#: Measured from the fourteen reference decks: 720x405pt pages (= 960x540 at 96dpi), title
#: 32pt at (63, 44), body 22pt from y=130, captions and kickers 9pt.
CANVAS = (960, 540)
MARGIN = 63
KICKER = 'AP PSYCHOLOGY  ·  UNIT 2.7  ·  FORGETTING AND MEMORY ERRORS'

#: Slots are (x, y, w, h, kind). A kind of ``contain`` or ``cover`` is an image slot and
#: carries its fit mode: ``contain`` shows the picture whole, which any diagram requires,
#: ``cover`` crops it to the slot, which only a photograph with no words in it can survive.
TEMPLATES: dict[str, dict] = {
    'cover': {
        'kicker': (MARGIN, 20, 500, 16, 'kicker'),
        'title': (MARGIN, 150, 470, 130, 'display'),
        'subtitle': (MARGIN, 300, 470, 60, 'lead'),
        'image': (560, 0, 400, 540, 'cover'),
    },
    'text': {
        'kicker': (MARGIN, 20, 834, 16, 'kicker'),
        'title': (MARGIN, 40, 700, 46, 'title'),
        'rule': (MARGIN, 92, 834, 0, 'rule'),
        'body': (MARGIN, 130, 834, 350, 'body'),
    },
    'split-right': {
        'kicker': (MARGIN, 20, 834, 16, 'kicker'),
        'title': (MARGIN, 40, 700, 46, 'title'),
        'rule': (MARGIN, 92, 834, 0, 'rule'),
        'body': (MARGIN, 130, 400, 320, 'body'),
        'image': (500, 108, 400, 330, 'contain'),
        'caption': (500, 448, 400, 42, 'caption'),
    },
    'split-left': {
        'kicker': (MARGIN, 20, 834, 16, 'kicker'),
        'title': (MARGIN, 40, 700, 46, 'title'),
        'rule': (MARGIN, 92, 834, 0, 'rule'),
        'image': (MARGIN, 108, 400, 330, 'contain'),
        'caption': (MARGIN, 448, 400, 42, 'caption'),
        'body': (520, 130, 377, 320, 'body'),
    },
    # The picture gets its own band under the rule: it never touches the title, and a
    # diagram is shown whole even when that leaves white on either side.
    'figure': {
        'kicker': (MARGIN, 20, 834, 16, 'kicker'),
        'title': (MARGIN, 40, 700, 46, 'title'),
        'rule': (MARGIN, 92, 834, 0, 'rule'),
        'image': (MARGIN, 100, 834, 392, 'contain'),
        'caption': (MARGIN, 498, 834, 30, 'caption'),
    },
    'list': {
        'kicker': (MARGIN, 20, 834, 16, 'kicker'),
        'title': (MARGIN, 40, 700, 46, 'title'),
        'rule': (MARGIN, 92, 834, 0, 'rule'),
        'lead': (MARGIN, 120, 834, 40, 'lead'),
        'items': (MARGIN, 186, 834, 300, 'items'),
    },
}

TYPE = {
    'kicker': {'size': 9, 'colour': MUTED},
    'display': {'size': 44, 'bold': True, 'colour': INK},
    'title': {'size': 32, 'bold': True, 'colour': INK},
    'lead': {'size': 20, 'colour': BODY},
    'body': {'size': 22, 'colour': BODY, 'spacing': 1.25},
    'items': {'size': 18, 'colour': INK, 'spacing': 1.7},
    'caption': {'size': 9, 'colour': MUTED},
}

#: page in the PDF -> (asset prefix, template, caption). The template follows from what the
#: asset is: a diagram goes where it can be seen whole, a photograph may fill its slot.
PLAN = [
    ('4e0326d3', 'split-right', 'Memory keeps what attention selects.', 3),
    ('83d3344d', 'figure', 'Ebbinghaus, 1885: retention falls fastest in the first hour.', 4),
    ('deb82eac', 'split-right', 'Encoding failure: unattended detail never enters memory.', 5),
    ('ec71b709', 'split-right', 'Tip of the tongue: stored, but the route to it is blocked.', 5),
    ('b88c9551', 'figure', 'Interference: old learning blocks new, and new blocks old.', 5),
    ('8439564e', 'split-right', 'Repression: motivation, not decay, keeps it out of reach.', 6),
    ('80a46af2', 'figure', 'Leading questions reshape what a witness remembers seeing.', 7),
    ('0c4089fc', 'figure', 'Misattribution: a confident identification is not a correct one.', 7),
    ('9e630740', 'split-right', 'Source amnesia: the fact survives, its origin does not.', 8),
    ('9295c14f', 'figure', 'Spaced review flattens the curve; one reading does not.', 9),
    ('bc315474', 'split-right', 'Mnemonics: giving structure a place to hang.', 9),
]

#: Labelled by position, not by topic: nobody here has watched them, and a title invented for
#: a clip is a claim about its content that this script cannot make.
VIDEOS = [
    ('Clip 1 (link supplied for this unit)', 'https://www.youtube.com/watch?v=2CbVt-KVyiQ'),
    ('Clip 2 (link supplied for this unit)', 'https://www.youtube.com/watch?v=NfPLTtlo2oY'),
    ('Clip 3 (link supplied for this unit)', 'https://www.youtube.com/watch?v=qQ-96BLaKYQ'),
]


def asset(prefix: str) -> Path:
    matches = sorted(glob.glob(str(CLIP / f'*{prefix}*')))
    return Path(matches[-1]) if matches else Path('/nonexistent') / prefix


def overlaps(a, b) -> bool:
    return not (a[0] + a[2] <= b[0] or b[0] + b[2] <= a[0]
                or a[1] + a[3] <= b[1] or b[1] + b[3] <= a[1])


def check_template(name: str) -> None:
    """Refuse a template whose picture can land on its words.

    This is the check the first version of this script needed and did not have. A full-bleed
    image is right on a cover and wrong on a figure page, and the difference between them is
    nothing but whether the slots intersect.
    """
    template = TEMPLATES[name]
    if 'image' not in template or 'title' not in template:
        return
    if overlaps(template['image'][:4], template['title'][:4]):
        raise SystemExit(f'template {name!r}: the image slot covers the title')


def page_text(doc, index: int) -> tuple[str, list[str]]:
    """The page's title, and its body as whole sentences, taken per text block."""
    page = doc[index]
    blocks = []
    for block in page.get_text('dict')['blocks']:
        parts, biggest = [], 0.0
        for line in block.get('lines', []):
            for span in line.get('spans', []):
                if span.get('text', '').strip():
                    parts.append(span['text'])
                    biggest = max(biggest, round(span['size'], 1))
        text = ' '.join(''.join(parts).split())
        if text:
            blocks.append({'y': round(block['bbox'][1]), 'size': biggest, 'text': text})
    if not blocks:
        return '', []
    blocks.sort(key=lambda b: b['y'])
    title_block = max(blocks, key=lambda b: b['size'])
    body = ' '.join(b['text'] for b in blocks if b is not title_block)
    body = body.replace('●', ' ').replace('❏', ' ')
    body = re.sub(r'(?<=[.!?])(?=[A-Z])', ' ', body)
    skip = ('AP Psychology Reminders', 'Vocabulary', 'Remember:', 'Homework:')
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', ' '.join(body.split()))
                 if len(s.strip()) > 24 and not s.strip().startswith(skip)]
    return title_block['text'], sentences[:2]


def split_label(bullet: str) -> tuple[str, str]:
    """Split "Encoding failure: information never stored" into its label and its text.

    The reference decks bold exactly this label - "Encoding failure:", "Proactive interference:"
    - and leave the explanation plain. That is the only emphasis they use, so it is the only
    one worth reproducing.
    """
    match = re.match(r'^([^:]{3,44}):\s*(.+)$', bullet.strip())
    if not match:
        return '', bullet.strip()
    return match.group(1).strip() + ':', ' ' + match.group(2).strip()


def page_terms(doc, index: int) -> list[str]:
    """The vocabulary list on a page, as terms.

    Every term here is shorter than the 24-character floor ``page_text`` uses to reject
    fragments, so a vocabulary page came out empty and the lesson's second slide had nothing
    on it. The terms are marked with a box glyph in this deck, which is what identifies them.
    """
    page = doc[index]
    terms = []
    for block in page.get_text('dict')['blocks']:
        for line in block.get('lines', []):
            # The vocabulary block is set smaller than the objectives above it; without this
            # the list started with "Explain potential causes of / memory failure and".
            if max(round(s['size'], 1) for s in line['spans']) > 13:
                continue
            text = ' '.join(''.join(s.get('text', '') for s in line['spans']).split())
            text = text.lstrip('❏○●•▪ ').strip()
            if not text or text.startswith(('2.7 ', 'AP Psychology')):
                continue
            if 3 <= len(text) <= 48 and text not in terms and text != 'Vocabulary':
                terms.append(text)
    return terms[:14]

def text_box(slide, rect, text: str, kind: str):
    style = TYPE[kind]
    box = slide.shapes.add_textbox(Emu(int(rect[0] * 12700)), Emu(int(rect[1] * 12700)),
                                   Emu(int(rect[2] * 12700)), Emu(int(rect[3] * 12700)))
    frame = box.text_frame
    frame.word_wrap = True
    frame.vertical_anchor = MSO_ANCHOR.TOP
    frame.margin_left = frame.margin_right = frame.margin_top = frame.margin_bottom = 0
    bullets = [line for line in text.split('\n') if line.strip()] or ['']
    for i, bullet in enumerate(bullets):
        paragraph = frame.paragraphs[0] if i == 0 else frame.add_paragraph()
        paragraph.alignment = PP_ALIGN.LEFT
        paragraph.line_spacing = style.get('spacing', 1.15)
        if kind == 'body' and len(bullets) > 1:
            marker = paragraph.add_run()
            marker.text = '▪  '
            marker.font.size = Pt(style['size'])
            marker.font.color.rgb = MUTED
            marker.font.name = 'Arial'
        label, rest = split_label(bullet) if kind in ('body', 'items') else ('', bullet)
        if label:
            lead = paragraph.add_run()
            lead.text = label
            lead.font.size = Pt(style['size'])
            lead.font.bold = True
            lead.font.color.rgb = INK
            lead.font.name = 'Arial'
        run = paragraph.add_run()
        run.text = rest
        run.font.size = Pt(style['size'])
        run.font.bold = style.get('bold', False)
        run.font.color.rgb = style['colour']
        run.font.name = 'Arial'
    return box


def picture(slide, path: Path, rect, mode: str) -> bool:
    """Place a picture in a slot without distorting it."""
    if not path.is_file():
        return False
    x, y, w, h = rect
    shape = slide.shapes.add_picture(str(path), Emu(int(x * 12700)), Emu(int(y * 12700)))
    image_w, image_h = shape.image.size
    if not image_w or not image_h:
        return False
    box_ratio, image_ratio = w / h, image_w / image_h
    if mode == 'cover':
        shape.width, shape.height = Emu(int(w * 12700)), Emu(int(h * 12700))
        if image_ratio > box_ratio:
            excess = (1 - box_ratio / image_ratio) / 2
            shape.crop_left = shape.crop_right = excess
        elif image_ratio < box_ratio:
            excess = (1 - image_ratio / box_ratio) / 2
            shape.crop_top = shape.crop_bottom = excess
        return True
    if image_ratio > box_ratio:
        new_w, new_h = w, w / image_ratio
    else:
        new_h, new_w = h, h * image_ratio
    shape.width, shape.height = Emu(int(new_w * 12700)), Emu(int(new_h * 12700))
    shape.left = Emu(int((x + (w - new_w) / 2) * 12700))
    shape.top = Emu(int((y + (h - new_h) / 2) * 12700))
    return True


def render(slide, template_name: str, *, image: Path | None = None, **content):
    """Fill a template's slots. Anything the template does not declare is ignored."""
    template = TEMPLATES[template_name]
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = PAPER
    for slot, spec in template.items():
        x, y, w, h, kind = spec
        if kind == 'rule':
            line = slide.shapes.add_connector(1, Emu(int(x * 12700)), Emu(int(y * 12700)),
                                              Emu(int((x + w) * 12700)), Emu(int(y * 12700)))
            line.line.color.rgb = RULE
            line.line.width = Pt(0.75)
            continue
        if kind in ('cover', 'contain'):
            if image is not None:
                picture(slide, image, (x, y, w, h), kind)
            continue
        text = content.get(slot, '')
        if text:
            text_box(slide, (x, y, w, h), text, kind)
    return slide


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', default='outputs/2.7-forgetting.pptx')
    args = parser.parse_args()

    for name in TEMPLATES:
        check_template(name)

    doc = pymupdf.open(PDF)
    presentation = Presentation()
    presentation.slide_width = Emu(CANVAS[0] * 12700)
    presentation.slide_height = Emu(CANVAS[1] * 12700)
    blank = presentation.slide_layouts[6]

    render(presentation.slides.add_slide(blank), 'cover', image=asset('4e0326d3'),
           kicker=KICKER, title='Understanding\nForgetting',
           subtitle='Why memory fails, and what a confident memory is worth')

    terms = page_terms(doc, 1)
    render(presentation.slides.add_slide(blank), 'text', kicker=KICKER, title='Vocabulary',
           body='\n'.join(terms) or 'Encoding · storage · retrieval')

    for prefix, template, caption, page_index in PLAN:
        title, sentences = page_text(doc, page_index)
        render(presentation.slides.add_slide(blank), template, image=asset(prefix),
               kicker=KICKER, title=title or 'Memory error',
               body='\n'.join(sentences) or caption, caption=caption)

    render(presentation.slides.add_slide(blank), 'list', kicker=KICKER, title='Watch',
           lead='Three clips, each for one idea on these pages.',
           items='\n'.join(f'{label}  —  {url}' for label, url in VIDEOS))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    presentation.save(out)
    print(f'wrote {out}  slides={len(presentation.slides)}  templates={len(TEMPLATES)}')
    for index, slide in enumerate(presentation.slides, 1):
        pictures = sum(1 for shape in slide.shapes if shape.shape_type == 13)
        print(f'  s{index:02} shapes={len(slide.shapes):2} pictures={pictures}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
