"""The architecture docs have to be checkable, or they are plausible-looking lies.

``docs/architecture/INDEX.md`` states that every ``path:line`` it names is re-parsed by
``test_every_index_path_exists`` and that a moved or deleted file fails the suite. That
test did not exist — and without it the document had accumulated a reference to this very
file, a double-prefixed path (``harness/web/playground.html``), two links to ADRs that were
never written, and a route count 48 out of date.

The same class of drift applies to the documents written beside it, so this guard covers
the whole set rather than one file.

Two limits are stated rather than hidden:

* Only paths anchored on a known top-level directory are resolved. A bare basename
  (``main.py``, ``Core.swift``) appears in prose about how the tree moved; resolving it
  would be guesswork, and guessing is what this file is defending against.
* Only existence and "the line number is not past the end of the file" are asserted. The
  *meaning* of a line number drifts as code grows above it, and no regex can see that.
  This is a guard against deletion and wholesale moves, not against a one-line slip.
"""

import re
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[2]
DOCS = HARNESS / 'docs'
ARCHITECTURE = DOCS / 'architecture'

#: Documents whose ``path:line`` references are machine-checked.
CHECKED = (
    ARCHITECTURE / 'INDEX.md',
    ARCHITECTURE / 'ARCHITECTURE_DEEP_DIVE.md',
    DOCS / 'API.md',
    DOCS / 'AGENT_TOOLS.md',
    DOCS / 'DB_SCHEMA.md',
    DOCS / 'SECURITY.md',
    DOCS / 'MODEL_TRAINING.md',
    DOCS / 'VERSION_TRUTH.md',
    DOCS / 'LUMINEST_2_REPOSITORY_POLICY.md',
)

_ANCHORED = ('backend/', 'native/', 'web/', 'docs/', 'scripts/', 'ui-tests/',
             'context/', 'deploy/', 'legal/')

_LINK = re.compile(r'\]\(([^)\s]+)\)')
_REF = re.compile(
    r'`([A-Za-z0-9_./-]+\.(?:py|swift|sql|md|json|html|js|css))(?::(\d+)(?:-(\d+))?)?`')


def test_the_guarded_document_set_is_present():
    missing = [str(path.relative_to(HARNESS)) for path in CHECKED if not path.is_file()]
    assert not missing, missing


def test_every_document_link_resolves():
    missing = []
    for document in CHECKED:
        for target in _LINK.findall(document.read_text(encoding='utf-8')):
            if target.startswith(('http://', 'https://', '#', 'mailto:')):
                continue
            if not (document.parent / target.split('#')[0]).resolve().exists():
                missing.append((document.name, target))
    assert not missing, missing


def test_every_index_path_exists():
    """Kept under this name because INDEX.md names it in prose."""
    broken_files, broken_lines = [], []
    for document in CHECKED:
        text = document.read_text(encoding='utf-8')
        for name, start, end in sorted({tuple(match) for match in _REF.findall(text)}):
            if not name.startswith(_ANCHORED):
                continue
            path = HARNESS / name
            if not path.exists():
                broken_files.append((document.name, name))
                continue
            wanted = int(end or start or 0)
            if not wanted:
                continue
            line_count = sum(1 for _ in path.open(encoding='utf-8', errors='replace'))
            if wanted > line_count:
                broken_lines.append((document.name, name, wanted, line_count))
    assert not broken_files, broken_files
    assert not broken_lines, broken_lines
