"""Find candidate pictures on the open web with a real browser, then verify the licence.

Why this exists: Openverse and Wikimedia are *tag* indexes. "overconfidence meme" returns
nothing there while "dunning kruger effect" returns the right diagram, because a tag index
answers with what a librarian labelled, not with what a web page shows. A browser-driven
image search answers the second question - and returns mostly copyrighted pictures, which is
exactly why this script does not hand anything to the deck.

What it does:

  1. opens Bing Images with the "free to share and use" filter on;
  2. collects the result tiles (image URL, landing page, title);
  3. downloads the ones large enough to project;
  4. follows each landing page and looks for a licence it can actually name.

Anything whose licence cannot be read out of the page is reported as unverified and left
alone. A picture that is right for the slide and wrong for the licence is not usable.

    backend/.venv/bin/python -u scripts/web_image_search.py --query "overconfidence cartoon" --limit 6
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

BING = 'https://www.bing.com/images/search'

#: L2/L3/L4 is Bing's "free to share and use" family of filters. It narrows the result set;
#: it is not a licence grant, which is why every hit is still verified below.
LICENCE_FILTER = '+filterui:license-L2_L3_L4'
#: Another "+filterui:imagesize-large" keeps phone-thumbnails out of a projected slide.
SIZE_FILTER = '+filterui:imagesize-large'

#: A plain headless Chromium is served a degraded, unrelated result set by Bing. The user
#: agent and the automation flag are what make the search answer the question asked.
USER_AGENT = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')

CC = re.compile(r'creativecommons\.org/(?:licenses|publicdomain)/(zero|mark|by(?:-sa|-nc|-nd)?'
                r'|by-sa|by-nc|by-nd|by-nc-sa|by-nc-nd)', re.I)
PD = re.compile(r'public domain|cc0', re.I)


def harvest(page, query: str, limit: int) -> list[dict]:
    # ``qft`` is a separate parameter. Appending the filter to ``q`` makes Bing search for a
    # query that contains the filter text, which returns nothing.
    qft = urllib.request.quote(LICENCE_FILTER + SIZE_FILTER)
    url = f'{BING}?q={urllib.request.quote(query)}&qft={qft}'
    page.goto(url, wait_until='domcontentloaded', timeout=45000)
    page.wait_for_timeout(1500)
    for _ in range(4):
        page.mouse.wheel(0, 2400)
        page.wait_for_timeout(700)
    rows = page.evaluate("""() => Array.from(document.querySelectorAll('a.iusc'))
        .map(a => { try { const m = JSON.parse(a.getAttribute('m')); return m; } catch (e) { return null; } })
        .filter(Boolean)
        .map(m => ({ image: m.murl, page: m.purl, title: m.t || '', width: m.mw || 0, height: m.mh || 0 }))
    """)
    seen, out = set(), []
    for row in rows:
        image = (row.get('image') or '').split('?')[0]
        if not image or image in seen:
            continue
        # Bing no longer fills mw/mh in this layout (every tile reports 0x0), so the size
        # floor is applied after the bytes arrive, not to metadata that is not there.
        seen.add(image)
        out.append(row)
        if len(out) >= limit:
            break
    return out


def fetch(url: str, *, limit: int = 900_000) -> tuple[bytes, str]:
    # A Wikimedia file URL carries an en-dash; urllib refuses a non-ASCII URL outright.
    url = urllib.parse.quote(url, safe=':/?&=%#~+,;@!$()*[]')
    request = urllib.request.Request(url, headers={'user-agent': 'Mozilla/5.0 (compatible; Luminest media audit)'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read(limit), response.headers.get('content-type', '')


def licence_of(page_url: str) -> tuple[str, str]:
    """The licence this landing page states, as (code, evidence). Empty code = unverified."""
    if not page_url:
        return '', 'no landing page'
    try:
        html, _ = fetch(page_url)
    except (urllib.error.URLError, OSError, ValueError) as error:
        return '', f'page unreadable: {type(error).__name__}'
    text = html.decode('utf-8', 'replace')
    match = CC.search(text)
    if match:
        slug = match.group(1).lower()
        return ('cc0' if slug in ('zero', 'mark') else 'cc_' + slug.replace('-', '_')), f'found cc link: {slug}'
    if PD.search(text):
        return 'cc0', 'page says public domain'
    return '', 'no licence stated on the page'


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--query', required=True)
    parser.add_argument('--limit', type=int, default=6)
    parser.add_argument('--out', default='outputs/web-found')
    args = parser.parse_args()

    out_dir = Path(args.out) / re.sub(r'[^a-z0-9]+', '-', args.query.lower()).strip('-')
    out_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as driver:
        browser = driver.chromium.launch(args=['--disable-blink-features=AutomationControlled'])
        page = browser.new_context(user_agent=USER_AGENT, locale='en-US',
                                   viewport={'width': 1440, 'height': 1000}).new_page()
        rows = harvest(page, args.query, args.limit)
        browser.close()

    print(f'{len(rows)} result(s) over the size floor for {args.query!r}\n')
    manifest = []
    for row in rows:
        code, evidence = licence_of(row['page'])
        name = hashlib.sha256(row['image'].encode()).hexdigest()[:12]
        saved = ''
        try:
            blob, kind = fetch(row['image'])
            if len(blob) > 8000 and kind.startswith('image/'):
                suffix = {'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp',
                          'image/gif': 'gif'}.get(kind.split(';')[0], 'bin')
                (out_dir / f'{name}.{suffix}').write_bytes(blob)
                saved = f'{name}.{suffix}'
        except (urllib.error.URLError, OSError, ValueError) as error:
            evidence += f'; download failed: {type(error).__name__}'
        manifest.append({'query': args.query, 'title': row['title'][:120],
                         'image': row['image'], 'page': row['page'],
                         'width': row.get('width'), 'height': row.get('height'),
                         'licence': code or 'UNVERIFIED', 'evidence': evidence, 'file': saved})
        print(f"  {(code or 'UNVERIFIED'):10} {row['title'][:58]:60} {row.get('width')}x{row.get('height')}")
        print(f"             {evidence[:100]}")
        print(f"             {row['page'][:110]}")

    (out_dir / 'manifest.json').write_text(json.dumps(manifest, indent=1, ensure_ascii=False),
                                           encoding='utf-8')
    verified = [row for row in manifest if row['file'] and row['licence'] != 'UNVERIFIED']
    print(f'\nverified + saved: {len(verified)}   unverified: {len(manifest) - len(verified)}')
    print(f'wrote {out_dir}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
