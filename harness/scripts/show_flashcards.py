"""Render a generated flashcard deck as a flip-card page, exactly as the API returns it.

This exists to look at the output rather than at a JSON dump: a card that reads badly is
obvious the moment it is laid out, and invisible inside a list of dicts.

    backend/.venv/bin/python -u scripts/show_flashcards.py --concept fractions --count 12
"""
from __future__ import annotations

import argparse
import html
import json
import secrets
import urllib.error
import urllib.request
from pathlib import Path


def call(base: str, path: str, payload=None, token: str = ''):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(base + path, data=data, method='POST' if data else 'GET')
    request.add_header('content-type', 'application/json')
    if token:
        request.add_header('authorization', 'Bearer ' + token)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=180) as response:
            return response.status, json.loads(response.read() or b'{}')
    except urllib.error.HTTPError as error:
        body = error.read()
        try:
            return error.code, json.loads(body or b'{}')
        except ValueError:
            return error.code, {'detail': body.decode('utf-8', 'replace')[:200]}


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{title}</title>
<style>
  :root {{ --ink: #111214; --muted: #6b7078; --line: #e3e2de; }}
  html, body {{ margin: 0; background: #f6f6f4; color: var(--ink);
    font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif; }}
  #wrap {{ max-width: 620px; margin: 0 auto; padding: 26px 22px 40px; }}
  h1 {{ font-size: 26px; font-weight: 600; margin: 0 0 6px; letter-spacing: -.2px; }}
  .meta {{ font-size: 12px; color: var(--muted); margin-bottom: 18px; }}
  .hint {{ text-align: center; font-size: 12.5px; color: #8b8f97; margin: 0 0 14px; }}
  .card {{ position: relative; border-radius: 26px; padding: 34px 30px 44px;
    min-height: 380px; display: flex; flex-direction: column; justify-content: center;
    transition: background .18s ease, color .18s ease, border .18s ease; }}
  .card.front {{ background: #2c2c2e; color: #f5f5f3; border: 1px solid #2c2c2e; }}
  .card.back {{ background: #fff; color: #1a1a1c; border: 1px solid var(--line); }}
  .count {{ position: absolute; top: 22px; left: 26px; font-size: 13px; opacity: .55; }}
  .kind {{ position: absolute; top: 20px; right: 24px; font-size: 11px; letter-spacing: .6px;
    text-transform: uppercase; opacity: .45; }}
  .q {{ font-size: 30px; line-height: 1.32; font-weight: 500; letter-spacing: -.3px; }}
  .card.back .q {{ font-size: 25px; line-height: 1.45; font-weight: 400; }}
  .reveal {{ position: absolute; bottom: 22px; left: 0; right: 0; text-align: center;
    font-size: 13px; opacity: .5; }}
  .flag {{ position: absolute; bottom: 20px; left: 26px; font-size: 11.5px; color: #b3261e;
    background: #fdecea; border: 1px solid #f5c6c1; border-radius: 999px; padding: 4px 10px; }}
  .bar {{ display: flex; align-items: center; justify-content: space-between; margin-top: 20px; }}
  .nav {{ width: 58px; height: 58px; border-radius: 50%; border: 1px solid var(--line);
    background: #fff; color: #1a1a1c; font-size: 20px; display: flex; align-items: center;
    justify-content: center; cursor: pointer; }}
  .score {{ display: flex; gap: 14px; }}
  .score div {{ border: 1px solid var(--line); background: #fff; border-radius: 999px;
    padding: 12px 20px; font-size: 15px; }}
  .neg {{ color: #d1493f; }} .pos {{ color: #3f8a5b; }}
</style></head><body>
<div id="wrap">
  <h1>{title}</h1>
  <div class="meta">{count} generated cards · {concept}</div>
  <p class="hint">Space flips the card &nbsp;·&nbsp; ← / → moves between cards</p>
  <div id="card" class="card front">
    <div class="count" id="count">1/{count}</div>
    <div class="kind" id="kind"></div>
    <div class="q" id="q"></div>
    <div class="reveal" id="reveal">Reveal answer</div>
    <div class="flag" id="flag" hidden></div>
  </div>
  <div class="bar">
    <div class="nav" onclick="step(-1)">←</div>
    <div class="score"><div class="neg">✕ 0</div><div class="pos">0 ✓</div></div>
    <div class="nav" onclick="step(1)">→</div>
  </div>
</div>
<script>
const CARDS = {cards};
let at = 0, flipped = false;
const el = id => document.getElementById(id);
function paint() {{
  const card = CARDS[at];
  el('q').textContent = flipped ? card.back : card.front;
  el('count').textContent = (at + 1) + '/' + CARDS.length;
  el('kind').textContent = card.kind || '';
  el('reveal').style.visibility = flipped ? 'hidden' : 'visible';
  el('flag').hidden = !card.flag;
  el('flag').textContent = card.flag || '';
  document.getElementById('card').className = 'card ' + (flipped ? 'back' : 'front');
}}
function step(delta) {{
  at = (at + delta + CARDS.length) % CARDS.length;
  flipped = false;
  paint();
}}
document.addEventListener('keydown', event => {{
  if (event.key === ' ') {{ event.preventDefault(); flipped = !flipped; paint(); }}
  if (event.key === 'ArrowRight') step(1);
  if (event.key === 'ArrowLeft') step(-1);
}});
document.getElementById('card').addEventListener('click', () => {{ flipped = !flipped; paint(); }});
paint();
</script></body></html>
"""


def looks_broken(card: dict) -> str:
    """Why a card cannot be answered, if it cannot.

    A card is unusable when its front asks about a statement it never shows, or when the
    answer is about a different concept than the question. Both are measured, not judged.
    """
    front = str(card.get('front') or '')
    back = str(card.get('back') or '')
    if 'statement' in front.lower() and 'statement' not in back.lower()[:40] \
            and 'this is the statement for' in back.lower():
        return 'front asks about a statement it never states'
    if 'not for' in back.lower() or 'belongs to' in back.lower():
        return 'answer is about a different concept'
    return ''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='http://127.0.0.1:8877')
    parser.add_argument('--concept', default='fractions')
    parser.add_argument('--count', type=int, default=12)
    parser.add_argument('--out', default='outputs/flashcards.html')
    parser.add_argument('--title', default='')
    args = parser.parse_args()

    status, body = call(args.base, '/api/v1/auth/register',
                        {'name': 'cards', 'email': f'cards-{secrets.token_hex(3)}@x.test',
                         'password': 'long-secret-password'})
    token = body['token']
    status, preview = call(args.base, '/api/v1/flashcards/generate',
                           {'concept_id': args.concept, 'dry_run': True}, token)
    cards = (preview.get('cards') or [])[:args.count]
    print(f'generate {status}: {len(cards)} candidate(s) for {args.concept}')

    broken = 0
    view = []
    for card in cards:
        flag = looks_broken(card)
        broken += bool(flag)
        view.append({'front': card.get('front', ''), 'back': card.get('back', ''),
                     'kind': card.get('kind', ''), 'flag': flag})
        print(f"  [{card.get('kind','?'):13}] {'BROKEN ' if flag else '       '}"
              f"{str(card.get('front'))[:64]}")

    title = args.title or f"{args.concept.replace('_', ' ').title()} Flashcards"
    page = PAGE.format(title=html.escape(title), count=len(view),
                       concept=html.escape(args.concept),
                       cards=json.dumps(view, ensure_ascii=False))
    out = Path(args.out)
    out.write_text(page, encoding='utf-8')
    print(f'\n{broken}/{len(view)} card(s) cannot be answered as written')
    print(f'wrote {out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
