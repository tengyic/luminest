#!/usr/bin/env python3
"""Refuse to call a tree releasable when the product depends on files git does not carry.

The failure this exists for: a feature branch had 110 modified tracked files and 28
untracked ones, five of which were *runtime modules* -- `app/model_config.py`,
`app/routes_model_config.py`, `app/harness/live_voice.py`,
`app/harness/teaching/items.py`, `app/harness/teaching/generate_problems.py` -- already
imported by those modified files. Committing with `git add -u` (the common move) staged
every edit except the new modules, and the resulting tree died at import:

    ImportError: cannot import name 'model_config' from 'app'

The same shape of failure applies to the native resource root: SwiftPM's `.copy("Visuals")`
means the WKWebView's document root is whatever git carried, so a missing `vendor/` still
launches and then renders `RENDERER_ASSETS_NOT_INSTALLED` on every inserted visual.

Both are invisible to a test suite that runs in the developer's working tree, because the
files are right there on disk. This check asks git instead of the filesystem.

Two directories are load-bearing enough to be checked by name:

* ``backend/app``        -- the Python package the process imports at boot.
* ``.../Visuals``        -- the WKWebView document root declared in ``Package.swift``.

An untracked file anywhere else is a judgement call. An untracked file in either of these
two is a broken artifact.

Usage:
    python scripts/verify_releasable_tree.py
    python scripts/verify_releasable_tree.py --repo /path/to/checkout

Exit codes: 0 releasable, 1 files missing from git, 2 could not determine (not a git
checkout), which is reported as a skip rather than a pass because "I could not look" is
not "everything is fine".
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]

#: Directories whose contents are imported or copied whole. A file present on disk and
#: absent from git does not degrade the artifact, it breaks it.
GUARDED = (
    'backend/app',
    'native/Sources/LearningHarness/Visuals',
)

#: The resource root is declared as `.copy("Visuals")`; these two files are the entry
#: points the WebView loads, and a bundle missing either renders nothing at all.
VISUAL_ENTRY_POINTS = ('index.html', 'catalog.json')


def _git(repo: Path, *args: str) -> tuple[int, str]:
    result = subprocess.run(['git', *args], cwd=repo, capture_output=True, text=True)
    return result.returncode, (result.stdout if result.returncode == 0 else result.stderr)


def untracked_in(repo: Path, relative: str) -> list[str]:
    code, out = _git(repo, 'ls-files', '--others', '--exclude-standard', '--', relative)
    if code != 0:
        raise RuntimeError(f'git ls-files failed for {relative}: {out.strip()}')
    return [line for line in out.splitlines() if line.strip()]


#: A directory listed as one line once it has this many untracked files. The Visuals
#: resource root carries ~170 TeX font files; printing each one buries the five Python
#: modules that actually matter.
COLLAPSE_AT = 3


def summarise(paths: list[str]) -> list[str]:
    """Group long per-directory runs into a single line, keep short ones explicit."""
    by_dir: dict[str, list[str]] = {}
    for path in paths:
        by_dir.setdefault(str(Path(path).parent), []).append(path)

    lines: list[str] = []
    for directory, members in sorted(by_dir.items()):
        if len(members) < COLLAPSE_AT:
            lines.extend(members)
            continue
        sample = ', '.join(Path(m).name for m in sorted(members)[:3])
        lines.append(f'{directory}/ — {len(members)} untracked files (e.g. {sample})')
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', default=str(HARNESS), help='harness/ checkout to inspect')
    args = parser.parse_args(argv)
    repo = Path(args.repo).resolve()

    code, _ = _git(repo, 'rev-parse', '--is-inside-work-tree')
    if code != 0:
        print(f'SKIP: {repo} is not a git working tree; nothing to compare against.',
              file=sys.stderr)
        return 2

    problems: list[str] = []

    for guarded in GUARDED:
        problems.extend(f'untracked but load-bearing: {line}'
                        for line in summarise(untracked_in(repo, guarded)))

    visuals = repo / 'native' / 'Sources' / 'LearningHarness' / 'Visuals'
    for name in VISUAL_ENTRY_POINTS:
        candidate = visuals / name
        relative = candidate.relative_to(repo)
        if not candidate.exists():
            problems.append(f'missing resource entry point: {relative}')
            continue
        code, _ = _git(repo, 'ls-files', '--error-unmatch', str(relative))
        if code != 0:
            problems.append(f'entry point not tracked: {relative}')

    if not problems:
        checked = ', '.join(GUARDED)
        print(f'OK: every file under [{checked}] and both Visuals entry points are tracked.')
        return 0

    print('REFUSING: this tree would produce an artifact that does not run.', file=sys.stderr)
    for problem in problems:
        print(f'  - {problem}', file=sys.stderr)
    print(
        '\nStage these together with the tracked edits that import or copy them. A commit of\n'
        'tracked files only (`git add -u`) is what produces the ImportError above. If a path\n'
        'here belongs to another workstream, that workstream has to land it before this one\n'
        'ships — dropping it is not an option, because the artifact is broken without it.',
        file=sys.stderr,
    )
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
