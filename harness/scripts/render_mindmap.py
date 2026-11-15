"""CLI for the concept mind map. The layout lives in ``app/mindmap.py``.

    backend/.venv/bin/python -u scripts/render_mindmap.py --payload outputs/mindmap.json
    backend/.venv/bin/python -u scripts/render_mindmap.py --tree my-tree.json --out out.svg
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
    parser.add_argument('--payload', default='outputs/mindmap.json')
    parser.add_argument('--tree', default='')
    parser.add_argument('--out', default='outputs/mindmap.svg')
    args = parser.parse_args()
    if args.tree:
        root = mindmap.from_dict(json.loads(Path(args.tree).read_text(encoding='utf-8')))
    else:
        root = mindmap.from_payload(json.loads(Path(args.payload).read_text(encoding='utf-8')))
    out = Path(args.out)
    out.write_text(mindmap.svg(root), encoding='utf-8')
    nodes = len(list(mindmap.walk(root)))
    print(f'wrote {out}  nodes={nodes}  tiers={mindmap.depth_of(root) + 1}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
