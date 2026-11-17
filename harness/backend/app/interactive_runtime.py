"""The persistence half of the generative interactive runtime.

``declarative_ui`` validates an untrusted spec and evaluates one state frame without
executing it. This module is the boundary between that pure machinery and the database:

* a model-emitted spec becomes an :class:`~app.db.InteractiveArtifact` before it is shown;
* a learner interaction becomes an append-only :class:`~app.db.InteractiveEvidence` row,
  evaluated against the stored artifact rather than a client-supplied spec;
* neither is an ``Attempt`` and neither is a grade. They are teaching evidence with a
  named source and a bounded vocabulary.

Keeping persistence here (rather than in ``toolbox`` or a route) means the same rules
apply whether the spec came from the agent loop, an API probe or a future authoring tool.
"""
from __future__ import annotations

import re
from typing import Any, Mapping

from . import declarative_ui

CONCEPT_ID = re.compile(r'^[a-z0-9_.-]{1,80}$')
MAX_EVIDENCE_KEYS = 64
MAX_EVIDENCE_STRING = 400


class InteractiveRefused(ValueError):
    """A client asked the runtime to do something outside its declared contract."""


def artifact_payload(row) -> dict[str, Any]:
    """The client-facing handle for a stored artifact."""
    return {
        'artifact_id': row.id,
        'spec': row.spec,
        'schema_version': row.schema_version,
        'source': row.source,
        'concept_id': row.concept_id,
        'title': row.title,
        'created_at': row.created_at,
    }


def persist_artifact(db, user, spec: Any, *, concept_id: str = '',
                     source: str = 'model') -> dict[str, Any]:
    """Validate and store a model-emitted spec. Caller owns the transaction.

    ``flush`` makes the generated id available to the tool result immediately; the
    agent loop commits between provider calls, so no write lock survives a model call.
    """
    from .db import InteractiveArtifact

    validated = declarative_ui.validate(spec)
    cid = str(concept_id or validated.get('concept_id') or '').strip()
    if cid and not CONCEPT_ID.fullmatch(cid):
        raise InteractiveRefused('concept_id must be a short lowercase identifier')
    if source not in ('model', 'authored', 'example'):
        raise InteractiveRefused('unsupported artifact source')

    row = InteractiveArtifact(
        user_id=user.id, concept_id=cid, title=validated['title'],
        spec=validated, schema_version=validated['schema_version'], source=source)
    db.add(row)
    db.flush()
    return artifact_payload(row)


def _clean_state(state: Any, inputs: list[str]) -> dict[str, Any]:
    if state is None:
        return {}
    if not isinstance(state, Mapping):
        raise InteractiveRefused('state must be an object')
    if len(state) > MAX_EVIDENCE_KEYS:
        raise InteractiveRefused(f'state has more than {MAX_EVIDENCE_KEYS} entries')
    allowed = set(inputs)
    clean: dict[str, Any] = {}
    for key, value in state.items():
        if key not in allowed:
            raise InteractiveRefused(f'state names unknown input {key!r}')
        if isinstance(value, bool) or isinstance(value, (int, float)):
            clean[key] = value
        elif isinstance(value, str):
            if len(value) > MAX_EVIDENCE_STRING:
                raise InteractiveRefused(f'state value for {key!r} is too long')
            clean[key] = value
        else:
            raise InteractiveRefused(f'state value for {key!r} must be a number or choice')
    return clean


def record_evidence(db, user, artifact_id: str, state: Any) -> dict[str, Any]:
    """Evaluate one frame against a stored artifact and append the evidence.

    The client never supplies the spec: doing so would let a forged frame claim that a
    different interaction happened. It supplies only input values, which are checked
    against the artifact's declared inputs before evaluation.
    """
    from sqlalchemy import select

    from .db import InteractiveEvidence

    if not artifact_id or len(artifact_id) > 36:
        raise InteractiveRefused('artifact_id is required')
    artifact = db.scalar(select(_artifact_model()).where(
        _artifact_model().id == artifact_id,
        _artifact_model().user_id == user.id))
    if artifact is None:
        raise InteractiveRefused('No such interactive artifact')
    clean = _clean_state(state, list(artifact.spec.get('inputs') or []))
    frame = declarative_ui.evaluate(artifact.spec, clean)

    row = InteractiveEvidence(
        user_id=user.id, artifact_id=artifact.id, concept_id=artifact.concept_id,
        state=frame['inputs'], evidence=frame['evidence'])
    db.add(row)
    db.flush()
    return {
        'artifact_id': artifact.id,
        'concept_id': artifact.concept_id,
        'readouts': frame['readouts'],
        'feedback': frame['feedback'],
        'evidence': frame['evidence'],
        'recorded': True,
    }


def _artifact_model():
    """Late import keeps this module importable from toolbox during app bootstrap."""
    from .db import InteractiveArtifact
    return InteractiveArtifact
