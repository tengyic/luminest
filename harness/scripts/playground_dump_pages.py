"""Write each rendered page from a pages.json bundle to its own .html file.

    python scripts/playground_dump_pages.py <pages.json> <out_dir>

Used by the real-browser verifier, which needs each page as a file it can serve over
http:// inside an iframe. Kept separate from playground_render_pages.py so the render
step stays a pure "catalogue -> json" transform.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    src = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    pages = json.loads(src.read_text(encoding='utf-8'))
    written = 0
    for page in pages:
        html = page.get('html') or ''
        if not html:
            continue
        (out_dir / f"{page['slug']}.html").write_text(html, encoding='utf-8')
        written += 1
    print(f'wrote {written} html files -> {out_dir}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
