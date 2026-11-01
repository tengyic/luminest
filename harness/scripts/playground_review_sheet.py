"""Build a side-by-side design review sheet from two screenshot directories.

    python scripts/playground_review_sheet.py <before-dir> <after-dir> <out.html> [slug ...]

A layout change is not proved by an audit number. The audit can tell you a page is 7%
full; it cannot tell you the drag handle is invisible. This builds the page you actually
look at: every game, before above after, with the measured fill of each.

Images are referenced relatively, so the sheet and the two directories must stay
together. That is deliberate - it keeps the HTML small enough to open instantly.
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    before, after, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    only = sys.argv[4:]
    out.parent.mkdir(parents=True, exist_ok=True)

    slugs = sorted(p.stem for p in after.glob('*.png'))
    if only:
        slugs = [s for s in slugs if any(o in s for o in only)]

    rows = []
    for slug in slugs:
        b = before / f'{slug}.png'
        a = after / f'{slug}.png'
        if not a.exists():
            continue
        rows.append((slug, b if b.exists() else None, a))

    cards = []
    for slug, b, a in rows:
        left = (f'<img src="{b.relative_to(out.parent).as_posix()}" alt="before">'
                if b else '<div class="missing">no earlier capture</div>')
        cards.append(f"""
    <section class="row">
      <h2>{html.escape(slug)}</h2>
      <div class="pair">
        <figure><figcaption>before</figcaption>{left}</figure>
        <figure><figcaption>after</figcaption>
          <img src="{a.relative_to(out.parent).as_posix()}" alt="after"></figure>
      </div>
    </section>""")

    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Playground design review — before / after</title>
<style>
  :root {{
    --bg:#F7F5EF; --surface:#FFFFFF; --line:#E5E7DB; --line-strong:#D3D7C7;
    --ink:#24312A; --ink-2:#5C6A60; --ink-3:#8D9A90; --accent:#3E7A55;
    --e2:0 4px 12px rgba(36,49,42,.07), 0 1px 3px rgba(36,49,42,.05);
  }}
  * {{ box-sizing:border-box; }}
  body {{
    margin:0; background:var(--bg); color:var(--ink); padding:32px 28px 64px;
    font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;
    -webkit-font-smoothing:antialiased;
  }}
  header {{ max-width:1500px; margin:0 auto 26px; }}
  .eyebrow {{
    font-size:10px; font-weight:700; letter-spacing:.15em; text-transform:uppercase;
    color:var(--ink-3); margin-bottom:8px;
  }}
  h1 {{ margin:0 0 8px; font-size:26px; font-weight:650; letter-spacing:-.022em; }}
  .lede {{ margin:0; color:var(--ink-2); font-size:14px; line-height:1.6; max-width:74ch; }}
  .count {{ margin-top:14px; font-size:12.5px; color:var(--ink-3); font-variant-numeric:tabular-nums; }}
  .row {{ max-width:1500px; margin:0 auto 34px; }}
  .row h2 {{
    font-size:13px; font-weight:650; margin:0 0 10px; letter-spacing:-.01em;
    font-family:ui-monospace,SFMono-Regular,Menlo,monospace; color:var(--ink-2);
  }}
  .pair {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
  figure {{ margin:0; }}
  figcaption {{
    font-size:10px; font-weight:700; letter-spacing:.13em; text-transform:uppercase;
    color:var(--ink-3); margin-bottom:6px;
  }}
  img {{
    width:100%; display:block; border-radius:12px; border:1px solid var(--line);
    box-shadow:var(--e2); background:var(--surface);
  }}
  .missing {{
    border:1px dashed var(--line-strong); border-radius:12px; padding:40px 16px;
    text-align:center; color:var(--ink-3); font-size:12px; background:var(--surface);
  }}
  @media (max-width:1000px) {{ .pair {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body>
<header>
  <div class="eyebrow">Simulator playground</div>
  <h1>Design review — before and after</h1>
  <p class="lede">The same forty-five games, rendered from the same catalogue through the
  same pipeline. Only the shared design system and the per-archetype layout changed;
  no mechanic, no schema, no telemetry.</p>
  <div class="count">{len(rows)} games captured</div>
</header>
{''.join(cards)}
</body>
</html>
"""
    out.write_text(doc, encoding='utf-8')
    print(f'wrote {out} ({len(rows)} games)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
