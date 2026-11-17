"""Production control for Bayesian Knowledge Tracing parameters.

The offline fitter in ``ml/bkt.py`` is research code: it answers "can these parameters
be estimated?" It does not answer "which parameters may affect a learner right now?".
This module is that boundary. A candidate is registered with metrics and a digest, moved
to shadow where it makes non-serving predictions, and only then promoted behind a
machine-checkable gate. Promotion records the previous active model so rollback restores
a reviewed state rather than falling back to an undocumented default.

No model file is executed or loaded from a path supplied by a client. Parameters come
from the registry row's metrics and are bounded to (0, 1) before use.
"""
from __future__ import annotations

import math
import re
import time
from typing import Any, Mapping

from ml.bkt import BKT, EPS

VERSION = re.compile(r'^[a-z0-9][a-z0-9_.-]{1,39}$')
STAGES = ('candidate', 'shadow', 'active', 'rolled_back')
DEFAULT_MODEL_VERSION = 'builtin-default-v1'
DEFAULT_PARAMS = BKT()
MIN_HELD_OUT_SEQUENCES = 20
MIN_HELD_OUT_STUDENTS = 10
MAX_CALIBRATION_ERROR = 0.10


class RegistryRefused(ValueError):
    """A registry transition was refused by policy."""


def _finite(value: Any, default: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def params_from_metrics(metrics: Mapping[str, Any]) -> BKT:
    raw = (metrics or {}).get('parameters') or {}
    return BKT(prior=_finite(raw.get('prior', DEFAULT_PARAMS.prior), DEFAULT_PARAMS.prior),
               learn=_finite(raw.get('learn', DEFAULT_PARAMS.learn), DEFAULT_PARAMS.learn),
               guess=_finite(raw.get('guess', DEFAULT_PARAMS.guess), DEFAULT_PARAMS.guess),
               slip=_finite(raw.get('slip', DEFAULT_PARAMS.slip), DEFAULT_PARAMS.slip)).clamped()


def promotion_gate(metrics: Mapping[str, Any]) -> dict[str, Any]:
    """The decision, with every check visible rather than a bare boolean."""
    metrics = metrics or {}
    evaluation = metrics.get('evaluation') or {}
    privacy = metrics.get('privacy') or {}
    baseline = metrics.get('baseline') or {}
    licence = metrics.get('licence') or {}
    logloss = _finite(evaluation.get('logloss'), math.inf)
    baseline_logloss = _finite(baseline.get('logloss'), math.inf)
    calibration = _finite(evaluation.get('calibration_error'), math.inf)
    checks = {
        'heldout_sequences': int(evaluation.get('heldout_sequences') or 0) >= MIN_HELD_OUT_SEQUENCES,
        'heldout_students': int(evaluation.get('heldout_students') or 0) >= MIN_HELD_OUT_STUDENTS,
        'logloss_no_worse_than_baseline': logloss <= baseline_logloss,
        'calibration_within_tolerance': calibration <= MAX_CALIBRATION_ERROR,
        'training_consent_only': bool(privacy.get('training_consent_only')),
        'licence_note_present': bool(str(licence.get('note') or '').strip()),
        'parameters_present': bool((metrics.get('parameters') or {}).keys()
                                  >= {'prior', 'learn', 'guess', 'slip'}),
    }
    return {'passed': all(checks.values()), 'checks': checks,
            'thresholds': {'min_heldout_sequences': MIN_HELD_OUT_SEQUENCES,
                           'min_heldout_students': MIN_HELD_OUT_STUDENTS,
                           'max_calibration_error': MAX_CALIBRATION_ERROR}}


def _event(db, model_id: str, event: str, reason: str, actor: str) -> None:
    from .db import BktModelEvent
    db.add(BktModelEvent(model_id=model_id, event=event, reason=reason.strip() or event,
                         actor=actor or 'system'))


def _row(db, version: str):
    from sqlalchemy import select

    from .db import BktModel
    return db.scalar(select(BktModel).where(BktModel.version == version))


def register_candidate(db, *, version: str, artifact_path: str, digest: str,
                       metrics: Mapping[str, Any], licence_note: str = '',
                       actor: str = 'system') -> dict[str, Any]:
    from .db import BktModel

    if not VERSION.fullmatch(str(version or '')):
        raise RegistryRefused('version must be a short lowercase identifier')
    if not re.fullmatch(r'[0-9a-f]{64}', str(digest or '')):
        raise RegistryRefused('digest must be a 64-character lowercase SHA-256 hex string')
    if not str(artifact_path or '').strip():
        raise RegistryRefused('artifact_path is required')
    if not isinstance(metrics, Mapping):
        raise RegistryRefused('metrics must be an object')
    if _row(db, version) is not None:
        raise RegistryRefused(f'model version {version!r} already exists')
    row = BktModel(version=version, artifact_path=str(artifact_path),
                   digest=str(digest), metrics=dict(metrics), stage='candidate',
                   licence_note=str(licence_note or ''))
    db.add(row)
    db.flush()
    _event(db, row.id, 'registered', f'Registered candidate {version}.', actor)
    return row_payload(row)


def row_payload(row) -> dict[str, Any]:
    return {
        'id': row.id, 'version': row.version, 'stage': row.stage,
        'digest': row.digest, 'artifact_path': row.artifact_path,
        'metrics': row.metrics, 'licence_note': row.licence_note,
        'created_at': row.created_at, 'promoted_at': row.promoted_at,
        'previous_version': row.previous_version,
        'promotion_gate': promotion_gate(row.metrics),
    }


def snapshot(db) -> dict[str, Any]:
    from sqlalchemy import select

    from .db import BktModel, BktModelEvent
    rows = list(db.scalars(select(BktModel).order_by(BktModel.created_at.desc())))
    events = list(db.scalars(select(BktModelEvent).order_by(
        BktModelEvent.created_at.desc()).limit(50)))
    return {
        'models': [row_payload(row) for row in rows],
        'events': [{'model_id': event.model_id, 'event': event.event,
                    'reason': event.reason, 'actor': event.actor,
                    'created_at': event.created_at} for event in events],
        'serving': (next((row_payload(row) for row in rows if row.stage == 'active'), None)),
        'builtin_fallback': {
            'version': DEFAULT_MODEL_VERSION,
            'parameters': {'prior': DEFAULT_PARAMS.prior, 'learn': DEFAULT_PARAMS.learn,
                           'guess': DEFAULT_PARAMS.guess, 'slip': DEFAULT_PARAMS.slip},
            'note': 'Unversioned teaching prior used when no reviewed model is active.'},
        'note': ('Shadow models record predictions but never affect teaching state. '
                 'Promotion requires a passing gate; rollback restores the previous active version.'),
    }


def promote_to_shadow(db, version: str, *, reason: str, actor: str) -> dict[str, Any]:
    row = _row(db, version)
    if row is None:
        raise RegistryRefused(f'No such model version {version!r}')
    if row.stage != 'candidate':
        raise RegistryRefused(f'Only a candidate can enter shadow; stage is {row.stage!r}')
    row.stage = 'shadow'
    _event(db, row.id, 'shadow', reason, actor)
    return row_payload(row)


def promote_to_active(db, version: str, *, reason: str, actor: str) -> dict[str, Any]:
    from .db import BktModel
    from sqlalchemy import select

    row = _row(db, version)
    if row is None:
        raise RegistryRefused(f'No such model version {version!r}')
    if row.stage != 'shadow':
        raise RegistryRefused(f'Only a shadow model can be promoted; stage is {row.stage!r}')
    gate = promotion_gate(row.metrics)
    if not gate['passed']:
        raise RegistryRefused('Promotion gate failed: ' + ', '.join(
            name for name, passed in gate['checks'].items() if not passed))
    current = db.scalar(select(BktModel).where(BktModel.stage == 'active'))
    if current is not None and current.id != row.id:
        current.stage = 'rolled_back'
        _event(db, current.id, 'superseded',
               f'Replaced by {row.version}: {reason}', actor)
        row.previous_version = current.version
    row.stage = 'active'
    row.promoted_at = time.time()
    _event(db, row.id, 'promoted', reason, actor)
    return row_payload(row)


def rollback_active(db, version: str, *, reason: str, actor: str) -> dict[str, Any]:
    row = _row(db, version)
    if row is None:
        raise RegistryRefused(f'No such model version {version!r}')
    if row.stage != 'active':
        raise RegistryRefused(f'Only an active model can be rolled back; stage is {row.stage!r}')
    row.stage = 'rolled_back'
    _event(db, row.id, 'rolled_back', reason, actor)
    restored = None
    if row.previous_version:
        previous = _row(db, row.previous_version)
        if previous is not None and previous.stage == 'rolled_back':
            previous.stage = 'active'
            previous.promoted_at = __import__('time').time()
            _event(db, previous.id, 'reactivated',
                   f'Restored after rollback of {row.version}: {reason}', actor)
            restored = previous.version
    return {'rolled_back': row.version, 'restored': restored,
            'serving': restored or DEFAULT_MODEL_VERSION,
            'reason': reason, 'actor': actor}


def serving_models(db) -> tuple[BKT, str, BKT | None, str]:
    """(active params, active version, shadow params, shadow version)."""
    from sqlalchemy import select

    from .db import BktModel
    rows = list(db.scalars(select(BktModel)))
    active = next((row for row in rows if row.stage == 'active'), None)
    shadow = next((row for row in rows if row.stage == 'shadow'), None)
    return (
        params_from_metrics(active.metrics) if active else DEFAULT_PARAMS,
        active.version if active else DEFAULT_MODEL_VERSION,
        params_from_metrics(shadow.metrics) if shadow else None,
        shadow.version if shadow else '',
    )


def _p_correct(p_l: float, params: BKT) -> float:
    value = p_l * (1 - params.slip) + (1 - p_l) * params.guess
    return min(1 - EPS, max(EPS, value))


def _update_belief(p_l: float, correct: bool, params: BKT) -> tuple[float, float]:
    p_obs = p_l * ((1 - params.slip) if correct else params.slip) \
        + (1 - p_l) * (params.guess if correct else 1 - params.guess)
    p_obs = min(1 - EPS, max(EPS, p_obs))
    posterior = p_l * ((1 - params.slip) if correct else params.slip) / p_obs
    return posterior, posterior + (1 - posterior) * params.learn


def update_state(state: dict[str, Any], correct: bool, *, active: BKT,
                 active_version: str, shadow: BKT | None = None,
                 shadow_version: str = '') -> dict[str, Any]:
    """Advance the production BKT belief for one answer; shadow never writes mastery.

    The result travels in ``learning_states.data`` beside the existing DSR/mastery
    fields. It is an additional, versioned estimate — not a replacement for the
    receipt-bound answer path.
    """
    # Always return a new mapping. SQLAlchemy does not track in-place edits to a JSON
    # column, so mutating the caller's dict and returning the same object would leave
    # the BKT estimate in the response but never in the database.
    state = dict(state)
    p_l = _finite(state.get('bkt_p_l', active.prior), active.prior)
    p_l = min(1 - EPS, max(EPS, p_l))
    posterior, updated = _update_belief(p_l, bool(correct), active)
    state['bkt_p_l'] = round(updated, 6)
    state['bkt_model_version'] = active_version
    state['bkt'] = {
        'p_known_before': round(p_l, 6),
        'p_known_after_response': round(posterior, 6),
        'p_known_after_learning': round(updated, 6),
        'p_next_correct': round(_p_correct(updated, active), 6),
        'model_version': active_version,
        'method': 'bkt-forward-update-v1',
        'note': 'Versioned teaching estimate, not a certified mastery score.',
    }
    if shadow is not None:
        s_l = _finite(state.get('bkt_shadow_p_l', shadow.prior), shadow.prior)
        s_l = min(1 - EPS, max(EPS, s_l))
        _, s_updated = _update_belief(s_l, bool(correct), shadow)
        state['bkt_shadow_p_l'] = round(s_updated, 6)
        state['bkt_shadow'] = {
            'model_version': shadow_version,
            'p_known': round(s_updated, 6),
            'p_next_correct': round(_p_correct(s_updated, shadow), 6),
            'serving': False,
            'note': 'Shadow prediction recorded for comparison; it did not affect teaching.',
        }
    return state
