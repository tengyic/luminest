#!/usr/bin/env python3
"""Export the authoritative visual catalog to the Web host's generated JSON.

``app.harness.visual_specs`` owns the catalog. This script is called by build.mjs so the
JS host can never drift from the backend: there is exactly one definition, and a pytest
compares the generated file against it on every backend run.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from app.harness.visual_specs import catalog_document  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print('usage: export_visual_catalog.py <output.json>', file=sys.stderr)
        return 2
    target = Path(sys.argv[1])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(catalog_document(), indent=2, sort_keys=True, ensure_ascii=False) + '\n',
        encoding='utf-8',
    )
    print(f'wrote {target} ({target.stat().st_size} bytes)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
