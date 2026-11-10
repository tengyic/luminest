"""Algebra 1 outline, in the shape ``scripts/course_pipeline.py`` expects.

The data lives in ``scripts/build_algebra_1.py`` (the provenance module written first);
this module is the registry entry the generic pipeline reads, so the course can be rebuilt
and re-verified with the same command as every other course.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from build_algebra_1 import DESCRIPTION, UNITS  # noqa: E402,F401

ID = 'algebra_1'
TITLE = 'Algebra 1'
SUBJECT = 'Mathematics'
SUBJECT_KIND = 'mathematics'
EXPECTED_WEEKS = 36
COURSE_LINE = 'Algebra 1 - Expressions, Linear and Quadratic Relationships'

TEXTBOOK = {
    'spine': 'OpenStax Elementary Algebra (1e, CC BY 4.0)',
    'supplements': [
        'OpenStax Algebra and Trigonometry (1e, CC BY 4.0)',
        'OpenStax Introductory Statistics (1e, CC BY 4.0)',
    ],
    'link_only_note': ('OpenStax Algebra 1 reports CC BY-NC-SA 4.0 and is carried as a '
                       'link-only study reference: never stored or quoted.'),
}
