#!/usr/bin/env python3
"""Selective mutation testing for the calculations a learner's progress depends on.

A green test suite proves tests ran, not that they *detect* anything. This script applies
a small, curated set of defects to the scheduling and grading code and checks that a test
fails. A mutant that survives means the suite would not have noticed that bug in
production, which is exactly what a release gate needs to know.

Deliberately selective, not exhaustive:

* only pure functions with a narrow test surface (so each run is seconds, not hours);
* every mutant is a *plausible* mistake (an off-by-one, a dropped floor, a missing
  increment), not a random type substitution;
* the original file is restored in a ``finally`` block and verified by hash, and a
  leftover backup from a killed run is repaired before anything else happens.

Usage::

    python3 scripts/mutation_check.py            # human summary, exit 1 if any survives
    python3 scripts/mutation_check.py --json out.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
BACKEND = HARNESS / 'backend'


@dataclass(frozen=True)
class Mutant:
    name: str
    path: str
    find: str
    replace: str
    tests: tuple[str, ...]
    why: str


MUTANTS: tuple[Mutant, ...] = (
    Mutant(
        name='forgetting-curve-flat',
        path='app/memory.py',
        find='return (1.0 + factor * t / stability) ** decay',
        replace='return 1.0',
        tests=('tests/test_memory_properties.py',),
        why='A retrieval probability that never decays would schedule every card forever; '
            'the property test asserts R(S) = 0.9 and monotone decay.',
    ),
    Mutant(
        name='due-time-floor-dropped',
        path='app/memory.py',
        find='interval = max(MIN_DUE_SECONDS, min(MAX_INTERVAL_DAYS, next_interval_days(stability, desired_retention)) * 86400.0)',
        replace='interval = min(MAX_INTERVAL_DAYS, next_interval_days(stability, desired_retention)) * 86400.0',
        tests=('tests/test_memory_properties.py',),
        why='Dropping the five-minute floor makes a lapsed card due immediately, which turns '
            'spaced repetition into a loop.',
    ),
    Mutant(
        name='lapse-counter-ignored',
        path='app/memory.py',
        find="'lapses': int(rating == RATING_AGAIN),",
        replace="'lapses': 0,",
        tests=('tests/test_memory_properties.py',),
        why='Retention is reported as 1 - lapses/reviews; a lapse counter that never moves '
            'reports perfect retention forever.',
    ),
    Mutant(
        name='learn-floor-removed',
        path='app/learning.py',
        find='return min(0.995, posterior + (1-posterior)*LEARN)',
        replace='return min(0.995, posterior)',
        tests=('tests/test_learning_properties.py',),
        why='Without the LEARN floor a single wrong answer can drive mastery to zero, which '
            'is the "never punish" invariant this product promises.',
    ),
    Mutant(
        name='mastery-cap-raised',
        path='app/learning.py',
        find='return min(0.995, posterior + (1-posterior)*LEARN)',
        replace='return min(1.5, posterior + (1-posterior)*LEARN)',
        tests=('tests/test_learning_properties.py',),
        why='Mastery is a probability; a cap that allows 1.5 breaks every downstream '
            'comparison against MASTERY_THRESHOLD.',
    ),
    Mutant(
        name='grade-inversion',
        path='app/learning.py',
        find="numerator = prior * ((1-SLIP) if correct else SLIP)",
        replace="numerator = prior * (SLIP if correct else (1-SLIP))",
        tests=('tests/test_learning_properties.py',),
        why='Swapping the evidence terms makes a correct answer lower the belief than a '
            'wrong one — the single worst failure this app could ship.',
    ),
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def restore(path: Path, backup: Path, expected: str) -> None:
    if backup.is_file():
        path.write_bytes(backup.read_bytes())
        backup.unlink()
    if path.is_file() and digest(path) != expected:
        raise SystemExit(f'Refusing to continue: {path} is not the file that was read')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--python', default=None)
    parser.add_argument('--json', type=Path, default=None)
    parser.add_argument('--timeout', type=int, default=300, help='Per-mutant test timeout')
    args = parser.parse_args()

    python = args.python
    if not python:
        candidates = sorted(BACKEND.glob('.venv*/bin/python'))
        if not candidates:
            raise SystemExit('No backend virtualenv found; pass --python')
        python = str(candidates[-1])

    results = []
    killed = 0
    for mutant in MUTANTS:
        target = BACKEND / mutant.path
        backup = target.with_name(target.name + '.mutation-backup')
        # Repair a backup left behind by a killed run BEFORE reading the file: the file on
        # disk may be a mutant, and running the next mutant on top of it would compound.
        if backup.is_file():
            target.write_bytes(backup.read_bytes())
            backup.unlink()
        original = digest(target)
        try:
            source = target.read_text()
            # Keep an on-disk backup for the whole mutation window: if this process is
            # killed mid-run, the next invocation can restore from it instead of leaving
            # a mutant in the tree.
            backup.write_text(source)
            if mutant.find not in source:
                results.append({'mutant': mutant.name, 'outcome': 'invalid',
                                'why': 'anchor text not found; the source changed', 'why_it_matters': mutant.why})
                continue
            target.write_text(source.replace(mutant.find, mutant.replace, 1))
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
            env.pop('HARNESS_DATABASE_URL', None)
            completed = subprocess.run(
                [python, '-m', 'pytest', '-q', '-x', *mutant.tests],
                cwd=BACKEND, env=env, capture_output=True, text=True, timeout=args.timeout)
            survived = completed.returncode == 0
            outcome = 'survived' if survived else 'killed'
            killed += 0 if survived else 1
            results.append({'mutant': mutant.name, 'outcome': outcome,
                            'why_it_matters': mutant.why,
                            'test_output': (completed.stdout or '')[-1500:] if survived else ''})
        finally:
            restore(target, backup, original)

    total = len(results)
    score = round(killed / total, 3) if total else 0.0
    document = {'mutants': results, 'killed': killed, 'total': total, 'score': score,
                'policy': 'A surviving mutant means the suite would not have caught that defect.'}
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(document, indent=2) + '\n')

    for row in results:
        mark = {'killed': 'KILLED  ', 'survived': 'SURVIVED', 'invalid': 'INVALID '}[row['outcome']]
        print(f"{mark} {row['mutant']}")
        if row['outcome'] == 'survived':
            print(f"         {row['why_it_matters']}")
    print(f'\nMutation score: {killed}/{total} ({score:.0%})')
    return 0 if killed == total else 1


if __name__ == '__main__':
    sys.exit(main())
