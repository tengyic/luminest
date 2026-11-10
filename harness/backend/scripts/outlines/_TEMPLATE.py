"""TEMPLATE — copy to scripts/outlines/<course_id>.py and fill in.

An outline module is data only. The generic pipeline (scripts/course_pipeline.py) derives
ids, prerequisite wiring and the textbook_alignment metadata from it, so two courses built
through this file cannot drift apart.

Rules that are enforced rather than suggested:

* ``sections`` slugs must come from ``scripts/probe_sections.py`` (the publisher's own table
  of contents) or from a fetch that returned HTTP 200. A guessed slug is a citation that
  404s on a learner's screen and ``verify`` will fail it.
* Only CC BY first editions may be anchors. ``chemistry-2e``, ``biology-2e``,
  ``college-physics-2e``, ``astronomy-2e``, ``calculus-volume-*``, ``organic-chemistry``
  and ``writing-guide`` are CC BY-NC-SA: link-only, never anchors.
* If the subject has no CC BY book at all, delete ``sections``, add the unit anyway, and set
  ``TEXTBOOK = {'no_cc_by_anchor': True, 'reason': '...'}``. An honest SKIP is required;
  an unrelated book used as a stand-in is a fabricated citation.
* Concept titles must be unique inside the course, and a title is what prerequisites name.
* Two or three concepts per topic is the intended grain: a topic is a lesson, a concept is
  a teachable idea inside it.
"""

from __future__ import annotations

ID = 'example_course'
TITLE = 'Example Course'
SUBJECT = 'Chemistry'
SUBJECT_KIND = 'science'          # 'science' | 'mathematics' | 'computing' | 'social_science'
EXPECTED_WEEKS = 36
COURSE_LINE = 'Example Course - Scope and Sequence'
DESCRIPTION = 'One paragraph a learner reads in the course picker.'

TEXTBOOK = {
    'spine': 'OpenStax X (1e, CC BY 4.0)',
    'supplements': [],
    'link_only_note': '',
}

UNITS = [
    {
        'unit': 'Unit Name',
        'about': 'One sentence: what this unit is for, in the course arc.',
        'sections': [
            ('book-slug', '1-1-verified-page-slug'),
        ],
        'topics': [
            ('Topic Name', [
                ('Concept Title',
                 'One accurate sentence: the claim, with its condition.',
                 ['keyword', 'keyword']),
                ('Second Concept',
                 'One accurate sentence that depends on the first.',
                 ['keyword']),
            ]),
        ],
    },
]
