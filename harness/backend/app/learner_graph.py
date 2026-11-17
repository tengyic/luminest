"""The per-learner, multi-dimensional concept graph.

The authored curriculum graph says what concepts exist and how they relate. This module
keeps a *different* graph: one learner's estimates for conceptual, procedural,
calculation and retrieval facets, the typed relations that their evidence supports, and
an append-only ledger explaining every estimate. It is deliberately not a second mastery
score. ``learning_states`` remains the receipt-bound answer state; a facet is a bounded,
provenance-bearing estimate that can disagree with it and say why.

The update rule here is a transparent heuristic, not a calibrated psychometric model.
That is stated in the payload rather than hidden: BKT parameters are versioned and
served by :mod:`app.bkt_registry`, and a learner-facing estimate must never imply a
certified model it did not come from.
"""
from __future__ import annotations

from typing import Any, Mapping

FACETS = ('conceptual', 'procedural', 'calculation', 'retrieval')
PRIOR = 0.15
MAX_LEDGER = 200


def facet_for(question: Mapping[str, Any], diagnosis: Mapping[str, Any] | None) -> str:
    """Choose the facet an answer actually bears on, with no invented taxonomy."""
    for candidate in ((question or {}).get('category'),
                      (diagnosis or {}).get('category'),
                      (diagnosis or {}).get('facet')):
        if candidate in FACETS:
            return candidate
    return 'conceptual'


def _bounded(value: float) -> float:
    return round(min(0.99, max(0.01, value)), 6)


def estimate_after(prior: float, correct: bool, confidence: float | None) -> float:
    """One transparent evidence step. Stronger confidence means a stronger update.

    A wrong answer with high confidence is more informative than a hesitant wrong
    answer; a correct answer with low confidence moves the estimate less. This is a
    teaching prior, not a claim about the learner's ability.
    """
    base = 0.22 if confidence is None else 0.14 + 0.20 * min(1.0, max(0.0, confidence))
    current = min(0.99, max(0.01, float(prior)))
    if correct:
        return _bounded(current + (1.0 - current) * base)
    return _bounded(current * (1.0 - base))


def _graph_neighbours(concept_id: str) -> list[tuple[str, str]]:
    """(predecessor, typed relation) pairs from the authored course graph."""
    from .curriculum import KNOWLEDGE_GRAPH

    node = KNOWLEDGE_GRAPH.nodes.get(concept_id)
    if node is None:
        return []
    pairs: list[tuple[str, str]] = [
        (source, 'hard_prerequisite') for source in node.prerequisites]
    pairs.extend((source, 'recommended_predecessor')
                 for source in node.sequence_predecessors)
    pairs.extend((str(edge.get('concept_id') or ''), str(edge.get('kind') or ''))
                 for edge in node.relationships
                 if edge.get('concept_id') and edge.get('kind'))
    return [(source, relation) for source, relation in pairs if source and relation]


def update_from_attempt(db, user, *, attempt_id: str, concept_id: str,
                        question: Mapping[str, Any], diagnosis: Mapping[str, Any] | None,
                        correct: bool, confidence: float | None, mode: str,
                        now: float) -> dict[str, Any]:
    """Append provenance and update one learner facet plus its typed edges."""
    from sqlalchemy import select

    from .db import ConceptEvidenceLedger, LearnerConceptEdge, LearnerConceptFacet

    facet = facet_for(question, diagnosis)
    row = db.scalar(select(LearnerConceptFacet).where(
        LearnerConceptFacet.user_id == user.id,
        LearnerConceptFacet.concept_id == concept_id,
        LearnerConceptFacet.facet == facet))
    if row is None:
        row = LearnerConceptFacet(user_id=user.id, concept_id=concept_id, facet=facet,
                                  mastery=PRIOR, attempts=0, evidence={})
        db.add(row)
    prior = float(row.mastery or PRIOR)
    new_mastery = estimate_after(prior, correct, confidence)
    row.mastery = new_mastery
    row.attempts = int(row.attempts or 0) + 1
    row.evidence = {
        'method': 'bounded-heuristic-v1',
        'last_source_type': 'attempt',
        'last_source_id': attempt_id,
        'last_correct': bool(correct),
        'last_confidence': confidence,
        'last_mode': mode,
        'prior': prior,
        'updated_at': now,
    }
    row.updated_at = now

    db.add(ConceptEvidenceLedger(
        user_id=user.id, concept_id=concept_id, facet=facet,
        source_type='attempt', source_id=attempt_id,
        weight=1.0 if confidence is None else 0.5 + 0.5 * float(confidence),
        payload={'correct': bool(correct), 'question_id': question.get('id', ''),
                 'diagnosis_category': (diagnosis or {}).get('category', ''),
                 'mode': mode, 'prior': prior, 'estimate': new_mastery},
        created_at=now))

    touched: list[dict[str, Any]] = []
    for source, relation in _graph_neighbours(concept_id):
        edge = db.scalar(select(LearnerConceptEdge).where(
            LearnerConceptEdge.user_id == user.id,
            LearnerConceptEdge.source_id == source,
            LearnerConceptEdge.target_id == concept_id,
            LearnerConceptEdge.relation == relation))
        if edge is None:
            edge = LearnerConceptEdge(user_id=user.id, source_id=source,
                                      target_id=concept_id, relation=relation,
                                      weight=0.0, evidence={})
            db.add(edge)
        delta = 0.08 if correct else -0.05
        edge.weight = round(min(1.0, max(-1.0, float(edge.weight or 0.0) + delta)), 6)
        edge.evidence = {
            'source_type': 'attempt', 'source_id': attempt_id,
            'facet': facet, 'last_correct': bool(correct), 'updated_at': now}
        edge.updated_at = now
        touched.append(edge_payload(edge))
    return {'facet': facet, 'prior': prior, 'estimate': new_mastery,
            'edges': touched}


def edge_payload(row) -> dict[str, Any]:
    return {'source_id': row.source_id, 'target_id': row.target_id,
            'relation': row.relation, 'weight': row.weight, 'evidence': row.evidence}


def snapshot(db, user, concept_id: str = '') -> dict[str, Any]:
    """A learner's graph, with missing facets present as *unknown*, never zero."""
    from sqlalchemy import select

    from .db import ConceptEvidenceLedger, LearnerConceptEdge, LearnerConceptFacet

    facet_query = select(LearnerConceptFacet).where(
        LearnerConceptFacet.user_id == user.id)
    edge_query = select(LearnerConceptEdge).where(
        LearnerConceptEdge.user_id == user.id)
    ledger_query = select(ConceptEvidenceLedger).where(
        ConceptEvidenceLedger.user_id == user.id)
    if concept_id:
        facet_query = facet_query.where(LearnerConceptFacet.concept_id == concept_id)
        edge_query = edge_query.where(
            (LearnerConceptEdge.source_id == concept_id)
            | (LearnerConceptEdge.target_id == concept_id))
        ledger_query = ledger_query.where(
            ConceptEvidenceLedger.concept_id == concept_id)

    rows = list(db.scalars(facet_query))
    by_key = {(row.concept_id, row.facet): row for row in rows}
    concepts = sorted({row.concept_id for row in rows}
                      | ({concept_id} if concept_id else set()))
    facets: list[dict[str, Any]] = []
    for cid in concepts:
        for facet in FACETS:
            row = by_key.get((cid, facet))
            facets.append({
                'concept_id': cid, 'facet': facet,
                'estimate': row.mastery if row is not None else PRIOR,
                'attempts': row.attempts if row is not None else 0,
                'mastery_known': row is not None and int(row.attempts or 0) > 0,
                'provenance': row.evidence if row is not None else {},
                'updated_at': row.updated_at if row is not None else None,
            })
    edges = [edge_payload(row) for row in db.scalars(edge_query.order_by(
        LearnerConceptEdge.updated_at.desc()))]
    ledger = [{
        'concept_id': row.concept_id, 'facet': row.facet,
        'source_type': row.source_type, 'source_id': row.source_id,
        'weight': row.weight, 'payload': row.payload, 'created_at': row.created_at,
    } for row in db.scalars(ledger_query.order_by(
        ConceptEvidenceLedger.created_at.desc()).limit(MAX_LEDGER))]
    return {
        'facets': facets, 'edges': edges, 'evidence_ledger': ledger,
        'facet_vocabulary': list(FACETS),
        'scope': concept_id or 'all concepts in this learner\'s graph',
        'note': ('Estimates from recorded evidence, not a certified mastery score. '
                 'A facet with no attempts has no estimate and is shown at the prior.'),
        'method': 'bounded-heuristic-v1',
    }
