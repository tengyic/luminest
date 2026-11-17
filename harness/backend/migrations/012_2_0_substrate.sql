-- 012_2_0_substrate.sql -- v12 -> v13
-- PostgreSQL reference DDL. ``scripts/init_db.py`` applies the same additive change to
-- SQLite through ``Base.metadata.create_all``. No existing row is rewritten or dropped.
--
-- Why these tables:
--   * interactive_artifacts / interactive_evidence close the generative interactive
--     runtime path. A model-emitted spec becomes a persisted artifact; learner state
--     frames and the evidence derived from them are append-only and never an Attempt.
--   * learner_concept_facets / learner_concept_edges / concept_evidence_ledger hold a
--     learner-owned multi-dimensional concept graph. Every facet estimate has provenance;
--     the ledger is the history, so a correction never erases the earlier observation.
--   * bkt_model_registry / bkt_model_events make BKT fitting a production-controlled
--     model rather than an offline experiment. Promotion and rollback are registry
--     transitions and every transition has an append-only event with an actor and reason.
--
-- Tenant rule: every learner-owned table has a NOT NULL user_id with ON DELETE CASCADE,
-- and is listed in ``app.user_scope.USER_SCOPED_TABLES`` in the same change.

CREATE TABLE IF NOT EXISTS interactive_artifacts (
    id varchar(36) PRIMARY KEY,
    user_id varchar(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    concept_id varchar(80) NOT NULL DEFAULT '',
    title varchar(160) NOT NULL,
    spec jsonb NOT NULL,
    schema_version integer NOT NULL DEFAULT 1,
    source varchar(30) NOT NULL DEFAULT 'model',
    created_at double precision NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_interactive_artifacts_user_id
    ON interactive_artifacts (user_id);
CREATE INDEX IF NOT EXISTS ix_interactive_artifacts_concept_id
    ON interactive_artifacts (concept_id);
CREATE INDEX IF NOT EXISTS interactive_artifacts_user_created_idx
    ON interactive_artifacts (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS interactive_evidence (
    id bigserial PRIMARY KEY,
    user_id varchar(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    artifact_id varchar(36) NOT NULL,
    concept_id varchar(80) NOT NULL DEFAULT '',
    state jsonb NOT NULL,
    evidence jsonb NOT NULL,
    created_at double precision NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_interactive_evidence_user_id
    ON interactive_evidence (user_id);
CREATE INDEX IF NOT EXISTS ix_interactive_evidence_artifact_id
    ON interactive_evidence (artifact_id);
CREATE INDEX IF NOT EXISTS ix_interactive_evidence_concept_id
    ON interactive_evidence (concept_id);
CREATE INDEX IF NOT EXISTS interactive_evidence_artifact_idx
    ON interactive_evidence (user_id, artifact_id, created_at);

CREATE TABLE IF NOT EXISTS learner_concept_facets (
    id bigserial PRIMARY KEY,
    user_id varchar(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    concept_id varchar(80) NOT NULL,
    facet varchar(24) NOT NULL,
    mastery double precision NOT NULL DEFAULT 0.15,
    attempts integer NOT NULL DEFAULT 0,
    evidence jsonb NOT NULL DEFAULT '{}',
    updated_at double precision NOT NULL,
    CONSTRAINT learner_concept_facets_facet_ck
        CHECK (facet IN ('conceptual', 'procedural', 'calculation', 'retrieval')),
    CONSTRAINT learner_concept_facets_uq UNIQUE (user_id, concept_id, facet)
);

CREATE INDEX IF NOT EXISTS ix_learner_concept_facets_user_id
    ON learner_concept_facets (user_id);
CREATE INDEX IF NOT EXISTS ix_learner_concept_facets_concept_id
    ON learner_concept_facets (concept_id);
CREATE INDEX IF NOT EXISTS learner_concept_facets_user_concept_idx
    ON learner_concept_facets (user_id, concept_id);

CREATE TABLE IF NOT EXISTS learner_concept_edges (
    id bigserial PRIMARY KEY,
    user_id varchar(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_id varchar(80) NOT NULL,
    target_id varchar(80) NOT NULL,
    relation varchar(32) NOT NULL,
    weight double precision NOT NULL DEFAULT 0,
    evidence jsonb NOT NULL DEFAULT '{}',
    updated_at double precision NOT NULL,
    CONSTRAINT learner_concept_edges_uq UNIQUE (user_id, source_id, target_id, relation)
);

CREATE INDEX IF NOT EXISTS ix_learner_concept_edges_user_id
    ON learner_concept_edges (user_id);
CREATE INDEX IF NOT EXISTS ix_learner_concept_edges_source_id
    ON learner_concept_edges (source_id);
CREATE INDEX IF NOT EXISTS ix_learner_concept_edges_target_id
    ON learner_concept_edges (target_id);
CREATE INDEX IF NOT EXISTS learner_concept_edges_user_source_idx
    ON learner_concept_edges (user_id, source_id);

CREATE TABLE IF NOT EXISTS concept_evidence_ledger (
    id bigserial PRIMARY KEY,
    user_id varchar(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    concept_id varchar(80) NOT NULL,
    facet varchar(24) NOT NULL,
    source_type varchar(30) NOT NULL,
    source_id varchar(80) NOT NULL DEFAULT '',
    weight double precision NOT NULL DEFAULT 1,
    payload jsonb NOT NULL DEFAULT '{}',
    created_at double precision NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_concept_evidence_ledger_user_id
    ON concept_evidence_ledger (user_id);
CREATE INDEX IF NOT EXISTS ix_concept_evidence_ledger_concept_id
    ON concept_evidence_ledger (concept_id);
CREATE INDEX IF NOT EXISTS concept_evidence_ledger_provenance_idx
    ON concept_evidence_ledger (user_id, concept_id, created_at);

CREATE TABLE IF NOT EXISTS bkt_model_registry (
    id varchar(36) PRIMARY KEY,
    version varchar(40) NOT NULL UNIQUE,
    artifact_path text NOT NULL,
    digest varchar(64) NOT NULL,
    metrics jsonb NOT NULL DEFAULT '{}',
    stage varchar(20) NOT NULL DEFAULT 'candidate',
    licence_note text NOT NULL DEFAULT '',
    created_at double precision NOT NULL,
    promoted_at double precision,
    previous_version varchar(40),
    CONSTRAINT bkt_registry_stage_ck
        CHECK (stage IN ('candidate', 'shadow', 'active', 'rolled_back'))
);

CREATE TABLE IF NOT EXISTS bkt_model_events (
    id bigserial PRIMARY KEY,
    model_id varchar(36) NOT NULL,
    event varchar(30) NOT NULL,
    reason text NOT NULL,
    actor varchar(80) NOT NULL DEFAULT 'system',
    created_at double precision NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_bkt_model_events_model_id
    ON bkt_model_events (model_id);
CREATE INDEX IF NOT EXISTS bkt_model_events_model_idx
    ON bkt_model_events (model_id, created_at);
