"""The creation boundary: who may change a teaching artifact, and how.

This is the server-side gate for the "not a vibe-coding harness" boundary. It exists
because the same model that fixes a bug in a supply-and-demand simulation can, with one
careless prompt, rewrite the lesson into something nobody filed a request for. The gate
makes that impossible by construction rather than by asking the model to behave.

The rules.

**Teachers create and modify freely.** A teacher may create a new simulation and may
restructure an existing one; that is the job.

**Students file change requests, never code instructions.** A student request must fall
in one of four categories -- ``bug`` (something broken), ``wrong_info`` (incorrect
content), ``ugly`` (visual quality), ``ux`` (usability) -- and is auto-approved *as a
requirement*: the model is told to fix that bug, correct that fact, improve that
visual, improve that interaction. It is never told "rewrite it however you like".

**Arbitrary creation is teacher-only.** ``create`` and ``restructure`` from a student
require a pending-teacher-approval record that has actually been approved. A refusal
says so plainly, and says what the student can do instead.

Three properties worth naming. First, the grant is **exact string equality** with the
canonical ``'teacher'`` -- no case-folding, no whitespace stripping toward a grant.
``'TEACHER'``, ``' Teacher'``, ``'admin'``, ``None`` and ``''`` are all students; the
privileged path must be granted by an exact canonical value, never *normalised* into.
(Case-folding exists only to make a refused role readable in the recorded note.) Second,
an unknown or missing role is a student (fail closed). Third, a student request with an
empty note cannot be approved, because a requirement nobody wrote down is not a
requirement -- it is an invitation for the model to invent scope.

Note on the approval flow: ``save_approval`` / ``load_approvals`` are implemented and
tested, but there is no production call site yet -- an approval UI is pending. Until it
ships, a student ``create`` / ``restructure`` request can be approved only by an
operator writing the record directly; the gate itself never implies approval.
"""

from __future__ import annotations

import json
import time
from typing import Any, Mapping

#: Categories a student may file, auto-approved and passed to the model as requirements.
STUDENT_CATEGORIES = ('bug', 'wrong_info', 'ugly', 'ux')

#: Categories that change what the artifact *is*. Teacher role, or an approved record.
TEACHER_CATEGORIES = ('create', 'restructure')

ALL_CATEGORIES = STUDENT_CATEGORIES + TEACHER_CATEGORIES

#: The requirement text each category turns into. This is the mechanism: the model
#: receives a *specific filed requirement*, scoped in advance, never an open invitation.
REQUIREMENT_TEXT = {
    'bug': 'Fix the reported defect: {note}. Change the minimum needed to make the '
           'described behaviour work correctly. Do not restructure the file and do not '
           'change anything the report does not cover.',
    'wrong_info': 'Correct the reported factual error: {note}. Fix the stated content so '
                  'it is factually right. Do not change the design, the interactions, or '
                  'any other content.',
    'ugly': 'Improve the reported visual quality problem: {note}. Presentation changes '
            'only -- layout, colour, spacing, clarity. Do not change behaviour or '
            'teaching content.',
    'ux': 'Improve the reported usability problem: {note}. Interaction changes only -- '
          'controls, labels, feedback, affordances. Do not change the teaching content '
          'or the underlying model.',
    'create': 'Create the artifact described: {note}. Follow the supplied spec.',
    'restructure': 'Restructure the artifact as requested: {note}. This is a '
                   'teacher-directed change and may alter scope.',
}

#: The system prompt for the sim-authoring persona. The boundary lives here as well as
#: in the gate: the model is told it is editing a teaching artifact in response to
#: specific filed requirements, must keep changes minimal, must not add scope, and must
#: preserve working behaviour.
SIM_AUTHORING_SYSTEM_PROMPT = (
    'You are editing a teaching artifact -- a self-contained HTML simulation used in a '
    'lesson -- in response to specific filed requirements. You are not free-styling.\n'
    'Rules:\n'
    '1. Address the filed requirement and nothing else. Keep changes minimal and '
    'scoped to it.\n'
    '2. Preserve working behaviour. Do not rewrite, reorganise or "improve" code the '
    'requirement does not cover.\n'
    '3. Never add new scope: no new features, no new sections, no new interactions that '
    'were not asked for.\n'
    '4. The artifact must stay self-contained: no external scripts, stylesheets, fonts, '
    'images or network fetches; no form posts to outside hosts; no eval or new Function.\n'
    '5. Tag every interactive series with data-series="..." so the lesson UI can '
    'highlight it on hover.\n'
    '6. Return the complete updated HTML file and nothing else. No prose, no markdown '
    'fence, no explanation.'
)

#: The system prompt for *building* a simulation from a spec, as opposed to editing one.
#: The edit prompt above is the wrong frame for a creation: "keep changes minimal, never
#: add new scope" tells a model with an empty page to write as little as possible, and it
#: says nothing about the two things that actually break a first draft -- the document
#: must be closed, and it must fit a token budget. Measured 2026-11-01: with this prompt
#: and ``reasoning='off'``, three unrelated specs produced complete, validating documents
#: in 4.5k-6.5k completion tokens.
SIM_CREATION_SYSTEM_PROMPT = (
    'You are building a teaching artifact: one self-contained HTML simulation that a '
    'tutor will show during a live lesson. You are writing the whole file, not editing '
    'one.\n'
    'Rules:\n'
    '1. Build exactly what the spec describes, and make it interactive: every control '
    'must be wired to real state and the current values must be visible on screen.\n'
    '2. Self-contained: inline all CSS and JavaScript; no external scripts, stylesheets, '
    'fonts or images; no fetch, XMLHttpRequest or WebSocket; no form posts to outside '
    'hosts; no eval or new Function.\n'
    '3. Tag every interactive data series with data-series="..." so the lesson UI can '
    'highlight it on hover.\n'
    '4. Be compact. No code comments, no unused CSS, no duplicated blocks, no framework '
    'boilerplate. Every line must earn its place: a learner reads the result, not the '
    'source.\n'
    '5. Start with <!DOCTYPE html> and end with </html>. The file must be complete; a '
    'truncated document is a broken lesson and cannot be repaired later.\n'
    '6. Return the file and nothing else. No prose, no markdown fence, no explanation, '
    'no "here is" preamble.'
)


def _normalise_role(role: Any) -> str:
    """Readable form of a role for *logging only*. Never used for the grant decision."""
    return str(role or '').strip().casefold()


def evaluate(request: Mapping[str, Any], *,
             approvals: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Decide whether a change request may proceed.

    ``request`` carries ``{role, category, note, selection, approval_id}``; ``approvals``
    maps approval-record ids to their status (``approved`` / anything else). Returns a
    dict, never an exception::

        {'approved': bool, 'role': str, 'category': str, 'reason': str,
         'requirement': str, 'requirement_prompt': str, 'notes': [str]}

    The grant is exact string equality with the canonical ``'teacher'``. No case-folding
    or whitespace handling moves a role toward the teacher path: ``'TEACHER'``,
    ``'teacher '``, ``' Teacher'``, ``'admin'``, ``None`` and ``''`` are all students.
    Case-folding happens only afterwards, to make a refused role readable in the note.
    """
    raw_role = request.get('role')
    role = raw_role if isinstance(raw_role, str) else ''
    category = str(request.get('category') or '').strip().casefold()
    note = ' '.join(str(request.get('note') or '').split())
    selection = str(request.get('selection') or '').strip()
    notes: list[str] = []
    # The grant: exact equality with the canonical 'teacher'. Everything else --
    # including a padded, cased or renamed variant -- decides as a student.
    effective_role = 'teacher' if role == 'teacher' else 'student'
    if role and role != 'teacher':
        notes.append(f'Role {_normalise_role(role)!r} is not the canonical teacher role; '
                     'treated as student.')

    if not category:
        return _decision(False, effective_role, category, note,
                         'No change category was supplied. Choose one of: '
                         f'{", ".join(ALL_CATEGORIES)}.', notes)
    if category not in ALL_CATEGORIES:
        return _decision(False, effective_role, category, note,
                         f'{category!r} is not a change category. A change request must be '
                         f'one of: {", ".join(ALL_CATEGORIES)}.', notes)

    if effective_role == 'teacher':
        return _decision(True, effective_role, category, note,
                         '', notes, selection=selection)

    # Student path (and every unrecognised role, per the fail-closed rule above).
    if category in TEACHER_CATEGORIES:
        approval_id = str(request.get('approval_id') or '').strip()
        if not approval_id:
            return _decision(False, effective_role, category, note,
                             f'{category.capitalize()} requires the teacher role. As a '
                             'student you can file a change request in one of: '
                             f'{", ".join(STUDENT_CATEGORIES)}; or ask a teacher to '
                             'approve this creation request.', notes, selection=selection)
        record = (approvals or {}).get(approval_id, '')
        status = str(record.get('status', '') if isinstance(record, Mapping) else record).casefold()
        if status != 'approved':
            return _decision(False, effective_role, category, note,
                             f'Approval record {approval_id!r} is not approved '
                             f'(status: {status or "not found"}). The request stays '
                             'blocked until a teacher approves it.', notes,
                             selection=selection)
        notes.append('Proceeding on an approved teacher-approval record.')
        return _decision(True, effective_role, category, note, '', notes, selection=selection)

    if not note:
        return _decision(False, effective_role, category, note,
                         'A change request must describe what is broken, wrong, ugly or '
                         'hard to use. An empty note gives the authoring model nothing '
                         'to be scoped to.', notes, selection=selection)
    return _decision(True, effective_role, category, note, '', notes, selection=selection)


def _decision(approved: bool, role: str, category: str, note: str, reason: str,
              notes: list[str], *, selection: str = '') -> dict[str, Any]:
    requirement = REQUIREMENT_TEXT.get(category, '').format(note=note) if note else ''
    if selection:
        requirement += f' The request points at this element/selection: {selection}.'
    return {'approved': approved, 'role': role or 'student', 'category': category,
            'note': note, 'selection': selection, 'reason': reason,
            'requirement': requirement, 'requirement_prompt': requirement,
            'notes': notes}


# ------------------------------------------------------- teacher approval records


def load_approvals(settings) -> dict[str, dict[str, Any]]:
    """Approval records from ``<sims>/approvals.json``. Missing file means empty."""
    from . import sims_store
    path = sims_store.pending_approvals_path(settings)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (ValueError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def save_approval(settings, approval_id: str, *, status: str, by: str = '',
                  category: str = '', note: str = '') -> dict[str, Any]:
    """Record one approval decision, as data rather than an in-memory set.

    A pending-teacher-approval record is the second way a student's ``create`` /
    ``restructure`` request can proceed, so it must survive a restart and be auditable,
    which an in-process set is not.
    """
    from . import sims_store
    records = load_approvals(settings)
    now = time.time()
    existing = records.get(approval_id) or {}
    record = {**existing, 'id': approval_id, 'status': status, 'category': category,
              'note': note, 'updated_at': now,
              **({'decided_by': by, 'decided_at': now} if status == 'approved' else {})}
    records[approval_id] = record
    path = sims_store.pending_approvals_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding='utf-8')
    return record


def new_approval_id() -> str:
    import hashlib
    return 'appr-' + hashlib.sha256(str(time.time_ns()).encode()).hexdigest()[:10]
