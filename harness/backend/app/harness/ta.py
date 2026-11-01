"""TA — teacher's assistant subagent.

The teacher is mid-lesson and must never "wait a minute": a dispatch runs an
agentic turn in a background thread with a restricted toolset (research +
asset generation only) and delivers the result to the teacher's feed. TA output
NEVER auto-presents on the Stage; the teacher pulls it when they choose to.

Constraints:
- At most ``HARNESS_TA_MAX_JOBS`` concurrent jobs (default 5); the UI normally
  dispatches one. Over-limit dispatches are refused with 429 by the endpoint.
- Each job runs one agent turn with ``developer_mode=False``: the event trace
  stays server-side, so no chain-of-thought ever reaches the client in
  production (the Alpha/development flag is the only way to see traces).
- Jobs own their DB session (created here, disposed here) because they outlive
  the request that spawned them.
- Nothing here writes learner memory or the messages table: TA results are
  ephemeral working notes for the teacher, not part of the learner transcript.
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any

# The TA's toolset: research + asset generation. Deliberately narrower than the
# tutor's registry — no memory writes, no workspace file tools, no quiz authoring.
# This is the *desired* set: the runner intersects it with ``toolbox.available_specs()``,
# so a tool whose optional package this build does not carry (browser_snapshot needs
# playwright, which the desktop bundle excludes) is simply not offered rather than being
# offered and guaranteed to refuse.
TA_TOOLS = ('search_concepts', 'read_concept', 'web_search', 'wikipedia_summary',
            'fetch_page_text', 'image_search', 'image_generate', 'find_image',
            'build_figure', 'find_game', 'search_videos', 'browser_snapshot',
            'generate_slides', 'write_simulation', 'whiteboard_apply',
            'whiteboard_write', 'whiteboard_place_image')

MAX_JOBS = 5
_state_lock = threading.Lock()
_jobs: dict[str, dict[str, Any]] = {}
# Populated at app startup so the runner can reuse the app's agent machinery.
_runner = None


class DispatchFull(Exception):
    pass


def configure(runner) -> None:
    """Bind the job runner (injected from main.create_app so the TA reuses
    exactly the same agent loop, settings and gates as the live tutor)."""
    global _runner
    _runner = runner


def _prune() -> None:
    horizon = time.time() - 6 * 3600
    for job_id in [j for j, job in _jobs.items() if job['created_at'] < horizon]:
        _jobs.pop(job_id, None)


def dispatch(message: str, *, concept_id: str = '', teacher_id: str = '',
             role: str = 'teacher') -> dict:
    """Register one TA job and start it. Raises DispatchFull when the pool is saturated."""
    if _runner is None:
        raise RuntimeError('TA runner is not configured')
    with _lock_guard():
        _prune()
        running = sum(1 for job in _jobs.values() if job['status'] in ('queued', 'running'))
        if running >= MAX_JOBS:
            raise DispatchFull(f'{running} TA jobs are already in flight (limit {MAX_JOBS})')
        job_id = 'ta-' + uuid.uuid4().hex[:12]
        _jobs[job_id] = {'id': job_id, 'status': 'queued', 'message': message[:2000],
                         'concept_id': concept_id[:80], 'created_at': time.time(),
                         'result': None, 'summary': '', 'error': ''}
    thread = threading.Thread(target=_run, args=(job_id, message, concept_id, teacher_id),
                              daemon=True, name=f'ta-{job_id}')
    thread.start()
    return dict(_jobs[job_id])


def _lock_guard():
    return _state_lock


def _run(job_id: str, message: str, concept_id: str, teacher_id: str) -> None:
    with _state_lock:
        _jobs[job_id]['status'] = 'running'
    try:
        result = _runner(message, concept_id, teacher_id)
        with _state_lock:
            _jobs[job_id].update(status='done', result=result.get('payload'),
                                 summary=result.get('summary', ''), error='')
    except Exception as exc:  # a TA failure is data, never a crash of the teacher's UI
        with _state_lock:
            _jobs[job_id].update(status='failed', summary='', error=f'{type(exc).__name__}: {exc}')


def status() -> list[dict]:
    with _state_lock:
        jobs = sorted(_jobs.values(), key=lambda job: job['created_at'], reverse=True)
        return [{key: job.get(key) for key in
                 ('id', 'status', 'created_at', 'summary', 'error', 'concept_id')}
                for job in jobs]


def results(since_version: int = 0) -> list[dict]:
    """Completed job results newer than the caller's last seen version."""
    with _state_lock:
        out = []
        for job in sorted(_jobs.values(), key=lambda job: job['created_at']):
            if job['status'] != 'done' or not job.get('result'):
                continue
            if job['created_at'] <= since_version:
                continue
            out.append({'id': job['id'], 'created_at': job['created_at'],
                        'concept_id': job.get('concept_id', ''),
                        'summary': job.get('summary', ''), 'result': job['result']})
        return out
