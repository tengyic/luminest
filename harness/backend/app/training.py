"""Trusted server-side consent ledger and minimized offline worker export."""
import csv
import hashlib
import hmac
import json
from pathlib import Path

from sqlalchemy import select

from .db import Attempt, TrainingConsent, User, now_ts

POLICY = 'training-v1'
MIN_ROWS = 20
MIN_USERS = 30


def set_consent(db, user, enabled):
    latest = db.scalar(select(TrainingConsent).where(TrainingConsent.user_id == user.id).order_by(TrainingConsent.created_at.desc(), TrainingConsent.id.desc()))
    if latest is None or user.training_consent != enabled:
        db.add(TrainingConsent(user_id=user.id, enabled=enabled, policy_version=POLICY, created_at=now_ts()))
    user.training_consent = enabled
    db.flush()


def current_grant(db, user):
    latest = db.scalar(select(TrainingConsent).where(TrainingConsent.user_id == user.id).order_by(TrainingConsent.created_at.desc(), TrainingConsent.id.desc()))
    return latest if user.training_consent and latest and latest.enabled and latest.policy_version == POLICY else None


def eligible_attempts(db, user, grant):
    if not grant:
        return []
    # Score only real submitted, nonblank responses. Do not export reasoning, telemetry or identity.
    rows = db.scalars(select(Attempt).where(Attempt.user_id == user.id, Attempt.created_at >= grant.created_at).order_by(Attempt.created_at, Attempt.id))
    return [a for a in rows if a.payload.get('option_id') or a.payload.get('answer_text')]


def training_status(db, user):
    grant = current_grant(db, user)
    samples = len(eligible_attempts(db, user, grant))
    return {'training_consent': bool(grant), 'policy_version': POLICY, 'consented_samples': samples,
            'qualified_samples': samples if samples >= MIN_ROWS else 0,
            'minimum_samples_per_user': MIN_ROWS, 'minimum_qualified_users': MIN_USERS,
            'worker_eligible': samples >= MIN_ROWS, 'automatic_promotion': False,
            'status': 'eligible_for_offline_worker' if samples >= MIN_ROWS else 'insufficient_consented_data',
            'scope': 'Only responses after the current opt-in are eligible. Telemetry consent is separate. Opt-out excludes existing rows from future exports; it cannot undo an already trained artifact. No model promotion or efficacy certification.'}


def pseudonym(secret, user_id):
    return hmac.new(secret.encode(), ('training-user:' + user_id).encode(), hashlib.sha256).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def export_training(db, secret, output_dir):
    output_dir = Path(output_dir)
    if not output_dir.is_dir():
        raise ValueError('Output directory must already exist')
    data, manifest_path = output_dir / 'training.csv', output_dir / 'consent_manifest.json'
    if data.exists() or manifest_path.exists():
        raise ValueError('Refusing to overwrite an existing training export')
    records, ledger, allowed = [], [], []
    for user in db.scalars(select(User).where(User.training_consent.is_(True)).with_for_update()):
        grant = current_grant(db, user)
        if not grant:
            continue
        rows = eligible_attempts(db, user, grant)
        if not rows:
            continue
        student = pseudonym(secret, user.id)
        allowed.append(student)
        ledger.append({'student_id': student, 'grant_sha256': hashlib.sha256(grant.id.encode()).hexdigest(),
                       'granted_at': grant.created_at, 'policy_version': grant.policy_version,
                       'rows': len(rows)})
        records.extend({'student_id': student, 'question_id': a.question_id, 'concept_id': a.concept_id,
                        'is_correct': int(a.correct), 'timestamp': a.created_at} for a in rows)
    if not records:
        raise ValueError('No eligible currently consented responses; no training export created')
    with data.open('x', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=['student_id', 'question_id', 'concept_id', 'is_correct', 'timestamp'])
        writer.writeheader()
        writer.writerows(records)
    data.chmod(0o600)
    manifest = {'schema_version': 2, 'domain': 'math', 'consent_verified': True, 'ownership_verified': True,
                'data_sha256': hashlib.sha256(data.read_bytes()).hexdigest(), 'timestamp_unit': 'seconds',
                'source_license': 'Owner-controlled original response logs; explicit training opt-in only, no third-party content or commercial-rights claim',
                'opt_in_student_ids': sorted(allowed), 'consent_ledger': ledger, 'policy_version': POLICY,
                'verified_at': now_ts(), 'verification': 'server HMAC plus fresh database consent-ledger cross-check',
                'automatic_promotion': False}
    manifest['ledger_signature'] = hmac.new(secret.encode(), canonical(manifest), hashlib.sha256).hexdigest()
    with manifest_path.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(manifest, indent=2) + '\n')
    manifest_path.chmod(0o600)
    return data, manifest_path


def verify_export(db, secret, data, manifest_path):
    manifest = json.loads(Path(manifest_path).read_text(encoding='utf-8'))
    signature = manifest.pop('ledger_signature', '')
    expected = hmac.new(secret.encode(), canonical(manifest), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected) or manifest.get('data_sha256') != hashlib.sha256(Path(data).read_bytes()).hexdigest():
        raise ValueError('Training export or consent ledger signature is invalid')
    active = {}
    for user in db.scalars(select(User).where(User.training_consent.is_(True)).with_for_update()):
        grant = current_grant(db, user)
        if grant:
            active[pseudonym(secret, user.id)] = grant
    for entry in manifest.get('consent_ledger', []):
        grant = active.get(entry['student_id'])
        if not grant or entry['grant_sha256'] != hashlib.sha256(grant.id.encode()).hexdigest():
            raise ValueError('Consent was revoked or changed since export; regenerate the export')
    if set(manifest.get('opt_in_student_ids', [])) != {e['student_id'] for e in manifest.get('consent_ledger', [])}:
        raise ValueError('Consent ledger does not cover every exported student')
    return manifest
