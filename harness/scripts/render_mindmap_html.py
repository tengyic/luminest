"""CLI for the interactive mind map. The page lives in ``app/mindmap.py``.

    backend/.venv/bin/python -u scripts/render_mindmap_html.py --tree outputs/mindmap-course.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app import mindmap  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--payload', default='')
    parser.add_argument('--tree', default='')
    parser.add_argument('--out', default='outputs/mindmap.html')
    parser.add_argument('--open-depth', type=int, default=1)
    args = parser.parse_args()
    if args.tree:
        root = mindmap.from_dict(json.loads(Path(args.tree).read_text(encoding='utf-8')))
    else:
        source = Path(args.payload or 'outputs/mindmap.json')
        root = mindmap.from_payload(json.loads(source.read_text(encoding='utf-8')))
    out = Path(args.out)
    out.write_text(mindmap.interactive_page(root, open_depth=args.open_depth), encoding='utf-8')
    print(f'wrote {out}  ({out.stat().st_size/1024:.0f} KB)  tiers={mindmap.depth_of(root) + 1}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
