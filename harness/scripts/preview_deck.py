"""Render a compiled deck as one HTML page, so the design can be looked at.

Every change to the layout table so far has been made without seeing the result. A .pptx
needs PowerPoint; a slide SVG needs a build. This needs neither: it reads the deck document,
fetches the picture bytes, and lays the elements out with the same coordinates the exporter
uses, so what you see here is what the file contains.

    backend/.venv/bin/python -u scripts/preview_deck.py
    backend/.venv/bin/python -u scripts/preview_deck.py --concept biology_active_transport_against_a_gradient --course biology
    open outputs/deck-preview.html

The picture is embedded as a data: URI on purpose - the page has to keep working after the
server is stopped, and a report that breaks when you close a terminal is not evidence.
"""
from __future__ import annotations

import argparse
import base64
import html
import json
import secrets
import sys
import urllib.error
import urllib.request
from pathlib import Path

CANVAS = (960, 540)
SCALE = 0.62


def call(base: str, path: str, payload=None, token: str | None = None,
         method: str | None = None, timeout: float = 180.0, raw: bool = False):
    url = base.rstrip('/') + path
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method or ('POST' if data else 'GET'))
    request.add_header('content-type', 'application/json')
    if token:
        request.add_header('authorization', 'Bearer ' + token)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            body = response.read()
            if raw:
                return response.status, body
            return response.status, json.loads(body or b'{}')
    except urllib.error.HTTPError as error:
        body = error.read()
        if raw:
            return error.code, b''
        try:
            return error.code, json.loads(body or b'{}')
        except ValueError:
            return error.code, {'detail': body.decode('utf-8', 'replace')[:300]}
    except (urllib.error.URLError, ConnectionError, TimeoutError) as error:
        return 0, (b'' if raw else {'detail': f'not reachable: {error}'})


def mime_from(sha: str, blob: bytes) -> str:
    if blob[:3] == b'\xff\xd8\xff':
        return 'image/jpeg'
    if blob[:8] == b'\x89PNG\r\n\x1a\n':
        return 'image/png'
    if blob[:4] == b'RIFF':
        return 'image/webp'
    return 'image/jpeg'


def style_of(element: dict) -> str:
    style = element.get('style') or {}
    size = float(style.get('size') or 18)
    parts = [f'font-size:{size:.0f}px', f'line-height:1.28']
    if style.get('bold'):
        parts.append('font-weight:600')
    if style.get('italic'):
        parts.append('font-style:italic')
    colour = str(style.get('color') or '')
    if colour.startswith('#') and len(colour) in (4, 7):
        parts.append(f'color:{colour}')
    if str(style.get('role') or '') == 'footnote':
        parts.append('opacity:.72')
    anchor = str(style.get('anchor') or '')
    if anchor == 'middle':
        parts.append('display:flex;align-items:center')
    elif anchor == 'top':
        # An explicit top anchor must not be centred: body copy starts under the rule, and
        # centring it in a tall box opens a gap that is not in the document.
        parts.append('display:block')
    else:
        # Short content in a tall box reads as a mistake when it clings to the top. Body
        # text is centred in its own box, like the exporter's vertical anchor does.
        parts.append('display:flex;flex-direction:column;justify-content:center')
    return ';'.join(parts)


def element_html(element: dict, images: dict[str, str]) -> str:
    kind = str(element.get('kind') or '')
    box = (f"left:{float(element.get('x') or 0):.0f}px;top:{float(element.get('y') or 0):.0f}px;"
           f"width:{float(element.get('w') or 0):.0f}px;height:{float(element.get('h') or 0):.0f}px")
    rotation = float(element.get('rotation') or 0)
    if rotation:
        box += f';transform:rotate({rotation}deg)'
    if kind == 'image':
        image = element.get('image') or {}
        sha = str(image.get('sha256') or '')
        uri = images.get(sha, '')
        alt = html.escape(str(image.get('alt') or ''))
        credit = html.escape(str(image.get('attribution') or ''))
        if not uri:
            return (f'<div class="el image missing" style="{box}">image {sha[:10]}… '
                    f'<span>{credit}</span></div>')
        fit = str(image.get('fit') or 'contain')
        return (f'<div class="el image" style="{box}">'
                f'<img src="{uri}" alt="{alt}" style="object-fit:{fit}">'
                f'<span class="credit">{credit}</span></div>')
    if kind == 'shape':
        shape = str(element.get('shape') or 'rect')
        style = element.get('style') or {}
        stroke = str(style.get('stroke') or '#d8d4cc')
        if shape == 'line':
            # A rule is one pixel of hairline, not a zero-height box with a border.
            return (f'<div class="el" style="left:{float(element.get("x") or 0):.0f}px;'
                    f'top:{float(element.get("y") or 0):.0f}px;'
                    f'width:{float(element.get("w") or 0):.0f}px;height:0;'
                    f'border-top:1px solid {stroke}"></div>')
        fill = str(style.get('fill') or 'transparent')
        return (f'<div class="el" style="{box};border:1px solid {stroke};'
                f'background:{fill}"></div>')
    if kind == 'text':
        paragraphs = ((element.get('text') or {}).get('paragraphs') or [])
        blocks = []
        for paragraph in paragraphs:
            text = ''.join(str(run.get('text') or '') for run in (paragraph.get('runs') or []))
            blocks.append(f'<p>{html.escape(text)}</p>')
        return f'<div class="el text" style="{box};{style_of(element)}">{"".join(blocks)}</div>'
    return f'<div class="el other" style="{box}">{html.escape(kind)}</div>'


def render(doc: dict, images: dict[str, str], meta: list[str]) -> str:
    width, height = CANVAS
    slides_html = []
    for index, slide in enumerate(doc.get('slides') or [], start=1):
        elements = sorted(slide.get('elements') or [], key=lambda e: float(e.get('z') or 0))
        body = ''.join(element_html(element, images) for element in elements)
        notes = html.escape(str(slide.get('notes') or ''))[:600]
        slides_html.append(f"""
<section class="wrap">
  <div class="label">{index:02d} · {html.escape(str(slide.get('layout') or ''))}</div>
  <div class="slide" style="width:{width}px;height:{height}px;transform:scale({SCALE})">
    {body}
  </div>
  {f'<div class="notes">{notes}</div>' if notes else ''}
</section>""")
    meta_html = ''.join(f'<li>{html.escape(line)}</li>' for line in meta)
    return f"""<!doctype html>
<html lang="zh"><meta charset="utf-8">
<title>deck preview · {html.escape(str(doc.get('title') or ''))}</title>
<style>
 body{{margin:0;padding:32px;background:#eeece7;color:#1c1c1e;
      font:14px/1.6 -apple-system,BlinkMacSystemFont,"Helvetica Neue",sans-serif}}
 h1{{font-size:18px;font-weight:600;margin:0 0 6px}}
 ul.meta{{font-size:12px;color:#5f5e5a;margin:0 0 24px;padding-left:18px}}
 .wrap{{margin:0 0 28px}}
 .label{{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:#8a877f;
         margin:0 0 6px}}
 .slide{{position:relative;background:#fff;border:1px solid #dcd8d0;border-radius:6px;
        transform-origin:top left;overflow:hidden}}
 .el{{position:absolute;box-sizing:border-box;overflow:hidden}}
 .text p{{margin:0 0 .5em}}
 .el.image img{{width:100%;height:100%;object-fit:contain}}
 .credit{{position:absolute;left:0;bottom:0;font-size:9px;color:#5f5e5a;
          background:rgba(255,255,255,.9);padding:1px 4px;max-width:100%;
          white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
 .el.missing{{background:#f7eded;border:1px dashed #c98a8a;color:#8a3b3b;font-size:11px;
              padding:6px}}
 .el.other{{background:#f2f0ea;color:#6b6b70;font-size:11px}}
 .notes{{font-size:12px;color:#5f5e5a;max-width:{int(CANVAS[0] * SCALE)}px;
         margin-top:-4px;padding:10px 12px;border-left:2px solid #d8d4cc}}
</style>
<h1>{html.escape(str(doc.get('title') or 'deck'))}</h1>
<ul class="meta">{meta_html}</ul>
{''.join(slides_html)}
</html>"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='http://127.0.0.1:8877')
    parser.add_argument('--concept', default='biology_active_transport_against_a_gradient')
    parser.add_argument('--course', default='biology')
    parser.add_argument('--out', default='')
    parser.add_argument('--token', default='')
    args = parser.parse_args()

    status, health = call(args.base, '/health')
    if status != 200:
        print(f'the backend is not answering on {args.base}: {health}')
        return 2

    if args.token:
        token = args.token
        who = 'your token'
    else:
        email = f'preview-{secrets.token_hex(4)}@deck.test'
        status, body = call(args.base, '/api/v1/auth/register',
                            {'name': 'preview', 'email': email,
                             'password': 'long-secret-password'})
        if status != 201:
            print(f'registration failed: {status} {body}')
            return 2
        token = body['token']
        who = f'a fresh {(body.get("user") or {}).get("role")} account'
    call(args.base, '/api/v1/me', {'course_id': args.course}, token, method='PATCH')

    status, doc = call(args.base, '/api/v1/deck/from-concept/' + args.concept, token=token)
    if status != 200:
        print(f'deck: {status} {json.dumps(doc, ensure_ascii=False)[:300]}')
        return 2

    images: dict[str, str] = {}
    for slide in doc.get('slides') or []:
        for element in slide.get('elements') or []:
            image = element.get('image') or {}
            sha = str(image.get('sha256') or '')
            if not sha or sha in images:
                continue
            status, blob = call(args.base, f'/api/v1/media/images/{sha}/bytes',
                                token=token, raw=True)
            if status == 200 and blob:
                images[sha] = (f'data:{mime_from(sha, blob)};base64,'
                               + base64.b64encode(blob).decode())

    status, lint = call(args.base, f'/api/v1/deck/{doc.get("id")}/lint', token=token)
    violations = (lint.get('violations') if isinstance(lint, dict) else None) or []
    meta = [f'读取者：{who}',
            f'概念：{args.concept}',
            f'{len(doc.get("slides") or [])} 页 · {len(images)} 张图已内嵌',
            f'规范检查：{len(violations)} 项违规'
            + (f'（{", ".join(str(v.get("rule")) for v in violations[:4])}）' if violations else '')]
    if status != 200:
        meta.append(f'lint 未取到：{status}')

    out = Path(args.out) if args.out else Path('outputs') / 'deck-preview.html'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(doc, images, meta), encoding='utf-8')
    print(f'preview: {out.resolve()}')
    print(f'slides: {len(doc.get("slides") or [])} · images embedded: {len(images)} '
          f'· lint violations: {len(violations)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
