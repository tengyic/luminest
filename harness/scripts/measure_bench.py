#!/usr/bin/env python3
"""Run the learning-efficiency estimator benchmark and print the verdict.

Why this is a script and not only a test
----------------------------------------
A test answers "did this change break it". An operator also needs to answer "is the instrument
currently trustworthy", on a build they did not write, without reading the test file. The
suite in :mod:`app.measurement.bench` is seeded, so its output is deterministic: a change in
these numbers is a change in the instrument, which is exactly when someone should look.

Usage
-----
    python scripts/measure_bench.py                  # default cohort, human-readable
    python scripts/measure_bench.py --learners 400   # tighter estimate
    python scripts/measure_bench.py --json           # machine-readable, for CI

Exit status is 0 only when every check passes, so this can gate a release the same way
``verify_feature_register.py --check`` does.

What it does not do
-------------------
It does not read learner data and it cannot tell you whether a real learner's measured rate
predicts their exam result. Synthetic learners have a known generating process; real learners
do not. See ``docs/MEASUREMENT.md`` for the field design that would answer the second question.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ``app`` is a package under ``backend/``, not at the repository root, so the import path is
# the backend directory rather than the scripts' parent. The benchmark itself needs nothing
# beyond the standard library - which is deliberate: a validation tool that requires the
# application's dependency tree is one that runs less often than the code it validates.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))

from app.measurement import bench  # noqa: E402


def render(suite: dict) -> str:
    lines = [
        'Learning-efficiency estimator benchmark',
        '=' * 78,
        f"cohort: {suite['learners']} synthetic learners per check "
        f"(known learning rate, known support boost)",
        '',
    ]
    for check in suite['checks']:
        mark = 'PASS' if check['passes'] else 'FAIL'
        lines.append(f"[{mark}] {check['check']}")
        lines.append(f"       {check['question']}")
        for key, value in check.items():
            if key in {'check', 'question', 'passes', 'criterion', 'note'}:
                continue
            lines.append(f"       {key:<34} {value}")
        lines.append(f"       criterion: {check['criterion']}")
        lines.append('')
    lines += [
        '-' * 78,
        f"{suite['passed']}/{suite['total']} checks passed "
        f"-> {'OK' if suite['ok'] else 'INSTRUMENT NOT TRUSTWORTHY'}",
        '',
        f"validates: {suite['validates']}",
        suite['scope'],
    ]
    return '\n'.join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--learners', type=int, default=bench.DEFAULT_LEARNERS,
                        help='synthetic learners per check (default %(default)s)')
    parser.add_argument('--seed', type=int, default=0, help='seed for the cohort')
    parser.add_argument('--json', action='store_true', help='emit JSON instead of text')
    args = parser.parse_args()

    if args.learners < 40:
        parser.error('--learners below 40 cannot estimate coverage or a false-positive rate')

    suite = bench.run_suite(learners=args.learners, seed=args.seed)
    if args.json:
        print(json.dumps(suite, indent=2))
    else:
        print(render(suite))
    return 0 if suite['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
