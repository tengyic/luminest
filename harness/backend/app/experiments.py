"""A/B experiment wiring for the learning-science features.

``experiments`` and ``experiment_assignments`` shipped in v4 and had zero writers:
infrastructure without instrumentation, which cannot produce evidence. This module
is the writer half.

Three properties are load-bearing:

1. **Assignment is deterministic and sticky.** A learner's variant is a hash of
   ``(experiment key, user id)`` into the variant list, persisted on first read.
   The same user always lands in the same bucket - on this server, on any replica,
   forever - so re-assignment cannot contaminate an analysis.
2. **Nothing changes until an operator creates the experiment.** With no
   ``experiments`` row, every feature uses its default. Creating an experiment with
   status ``running`` is the switch; deleting or pausing it returns everyone to the
   default. A "controlled comparison" no one started is not one.
3. **Assignment is not exposure.** ``log_exposure`` records that a learner actually
   met the treatment on a surface; an analysis that counts the assigned-but-never-
   exposed as participants inflates N with people who never saw the change.
"""

from __future__ import annotations

import hashlib

from sqlalchemy import select

from .db import Experiment, ExperimentAssignment, ExperimentExposure, now_ts

#: The experiment keys the harness knows how to interpret, the variants each may
#: carry, and the behaviour each overrides when running. Feature defaults live here
#: too, so the default arm of every experiment is legible in one place.
EXPERIMENT_CATALOGUE: dict[str, dict] = {
    'p1_interleaved_practice': {
        'description': 'P-1: /questions/next group requests use the interleaved '
                       'scheduler (on) versus the blocked legacy order (off).',
        'variants': ['on', 'off'],
        'default': 'on',
    },
    'p2_confidence_capture': {
        'description': 'P-2: attempts record learner confidence (on) versus the '
                       'control arm where confidence is dropped before storage (off), '
                       'so calibration feedback can be compared against no capture.',
        'variants': ['on', 'off'],
        'default': 'on',
    },
    'p3_self_explanation_gate': {
        'description': 'P-3: submitting a graded attempt requires a short structured '
                       'self-explanation, enforced with 422 (on) versus no gate (off).',
        'variants': ['on', 'off'],
        'default': 'off',
    },
    'm4_target_correctness': {
        'description': 'M-4: the practice target P(correct) the scheduler aims at. '
                       '0.7 is a product assumption, not an evidence-based optimum '
                       '(Wilson et al. 2019 concerns classifier training, not human '
                       'practice), so it is tuned by experiment rather than fixed.',
        'variants': ['0.6', '0.7', '0.8'],
        'default': '0.7',
    },
}

DEFAULT_FLAGS: dict = {
    'interleaved_practice': True,
    'confidence_capture': True,
    'self_explanation_gate': False,
    'target_correctness': 0.7,
}

FLAG_OF_KEY: dict[str, str] = {
    'p1_interleaved_practice': 'interleaved_practice',
    'p2_confidence_capture': 'confidence_capture',
    'p3_self_explanation_gate': 'self_explanation_gate',
    'm4_target_correctness': 'target_correctness',
}


def bucket(user_id: str, key: str, buckets: int = 100) -> int:
    """Stable bucket in ``[0, buckets)`` for a user in an experiment.

    blake2b over ``key:user_id`` - not Python's ``hash``, which is salted per
    process, and not a plain sha of the user id, which would correlate buckets
    across experiments. Pure and deterministic: the same pair always maps to the
    same bucket on every machine.
    """
    digest = hashlib.blake2b(f'{key}:{user_id}'.encode('utf-8'), digest_size=8).digest()
    return int.from_bytes(digest, 'big') % buckets


def ensure_experiment(db, key: str, description: str | None = None,
                      variants: list[str] | None = None,
                      status: str = 'running') -> Experiment:
    """Idempotently create an experiment row from the catalogue. Never mutates one."""
    spec = EXPERIMENT_CATALOGUE.get(key)
    row = db.scalar(select(Experiment).where(Experiment.key == key))
    if row:
        return row
    row = Experiment(key=key,
                     description=description or (spec or {}).get('description', ''),
                     variants=variants or (spec or {}).get('variants', ['on', 'off']),
                     status=status if status in {'draft', 'running', 'paused', 'completed'} else 'draft')
    db.add(row)
    db.flush()
    return row


def _resolved_variant(db, user_id: str, experiment: Experiment,
                      persist: bool) -> str:
    """Sticky variant for one user: stored assignment wins, else compute and store."""
    row = db.scalar(select(ExperimentAssignment).where(
        ExperimentAssignment.experiment_id == experiment.id,
        ExperimentAssignment.user_id == user_id))
    if row:
        return row.variant
    variants = list(experiment.variants or [])
    if not variants:
        variants = EXPERIMENT_CATALOGUE.get(experiment.key, {}).get('variants', ['on'])
    variant = variants[bucket(user_id, experiment.key, len(variants))]
    if persist:
        exists = db.scalar(select(ExperimentAssignment.id).where(
            ExperimentAssignment.experiment_id == experiment.id,
            ExperimentAssignment.user_id == user_id))
        if not exists:
            db.add(ExperimentAssignment(experiment_id=experiment.id, user_id=user_id,
                                        variant=variant, assigned_at=now_ts()))
            db.flush()
    return variant


def snapshot(db, user_id: str) -> dict:
    """The learner's effective flags and their assignments, in one read pass.

    Flags resolve in order: a stored assignment for a *running* experiment wins;
    otherwise a running experiment contributes its hash-computed variant; otherwise
    the feature default. Non-running experiments contribute nothing, which is what
    makes pausing an experiment a true rollback to default.
    """
    rows = list(db.scalars(select(Experiment).where(
        Experiment.key.in_(set(EXPERIMENT_CATALOGUE)))))
    running = {row.key: row for row in rows if row.status == 'running'}
    assignments: dict[str, str] = {}
    listed: list[dict] = []
    if running:
        id_to_key = {row.id: key for key, row in running.items()}
        stored = db.scalars(select(ExperimentAssignment).where(
            ExperimentAssignment.user_id == user_id,
            ExperimentAssignment.experiment_id.in_(list(id_to_key))))
        for row in stored:
            key = id_to_key.get(row.experiment_id)
            if key:
                assignments[key] = row.variant
    flags = dict(DEFAULT_FLAGS)
    for key, spec in EXPERIMENT_CATALOGUE.items():
        experiment = running.get(key)
        if experiment is None:
            listed.append({'key': key, 'variant': None, 'status': 'not_created'})
            continue
        variant = assignments.get(key) or _resolved_variant(db, user_id, experiment, persist=True)
        assignments[key] = variant
        listed.append({'key': key, 'variant': variant, 'status': experiment.status})
        flag = FLAG_OF_KEY[key]
        if flag == 'target_correctness':
            try:
                flags[flag] = float(variant)
            except (TypeError, ValueError):
                flags[flag] = float(spec['default'])
        else:
            flags[flag] = variant == 'on'
    return {'flags': flags, 'experiments': listed}


def log_exposure(db, user_id: str, key: str, surface: str) -> dict:
    """Record that this user met the experiment on this surface. Idempotent."""
    experiment = db.scalar(select(Experiment).where(Experiment.key == key))
    if experiment is None:
        return {'logged': False, 'reason': 'no_such_experiment'}
    if experiment.status != 'running':
        return {'logged': False, 'reason': 'experiment_not_running'}
    variant = _resolved_variant(db, user_id, experiment, persist=True)
    existing = db.scalar(select(ExperimentExposure).where(
        ExperimentExposure.experiment_id == experiment.id,
        ExperimentExposure.user_id == user_id,
        ExperimentExposure.surface == surface))
    if existing:
        return {'logged': False, 'reason': 'already_logged', 'variant': variant,
                'exposed_at': existing.exposed_at}
    exposed_at = now_ts()
    db.add(ExperimentExposure(experiment_id=experiment.id, user_id=user_id,
                              surface=surface[:40], exposed_at=exposed_at))
    db.flush()
    return {'logged': True, 'variant': variant, 'exposed_at': exposed_at}
