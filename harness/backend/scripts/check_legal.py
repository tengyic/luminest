#!/usr/bin/env python3
"""Exit nonzero while the legal bundle still contains unfilled placeholders.

The documents in ``backend/legal/`` are templates, not legal advice; this is the
loud, boring check that keeps them from being published by accident. The decisions
each placeholder represents belong to named owners in
``backend/legal/FILL_IN_SHEET.md`` -- filling them is counsel's and the founders'
job, never an engineer's convenience.

Usage::

    python scripts/check_legal.py                 # ship gate: exit 1 while unfilled
    python scripts/check_legal.py --allow-template  # report only (local development)
    python scripts/check_legal.py --legal-dir DIR
"""
import argparse
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.legal_guard import unfilled_placeholders  # noqa: E402

DEFAULT_LEGAL_DIR = BACKEND / 'legal'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--legal-dir', type=Path, default=DEFAULT_LEGAL_DIR)
    parser.add_argument('--allow-template', action='store_true',
                        help='report placeholders without failing; never use for a release')
    args = parser.parse_args(argv)
    found = unfilled_placeholders(args.legal_dir)
    total = sum(len(tokens) for tokens in found.values())
    if not found:
        print(f'LEGAL OK: no placeholders under {args.legal_dir}')
        print('Reminder: the documents are still not legal advice until counsel has '
              'signed off on the filled values (see FILL_IN_SHEET.md).')
        return 0
    print(f'LEGAL NOT SHIPPABLE: {total} unfilled placeholder(s) under {args.legal_dir}:')
    for name, tokens in found.items():
        for token in tokens:
            print(f'  {name}: {token}')
    print('Fill each one from backend/legal/FILL_IN_SHEET.md. Do not guess: a wrong '
          'jurisdiction or entity name in a shipped ToS is worse than a missing one.')
    if args.allow_template:
        print('--allow-template: reporting only; this bundle must not be released.')
        return 0
    return 1


if __name__ == '__main__':
    sys.exit(main())
