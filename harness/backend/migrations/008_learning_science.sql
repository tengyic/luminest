-- 008_learning_science.sql -- v7 -> v8
-- PostgreSQL reference DDL for the learning-science unit. ``scripts/init_db.py`` is the
-- authoritative SQLite path and applies the same change via ``ADDED_COLUMNS`` and
-- ``create_all``; this file documents and applies it for upgraded PostgreSQL databases.
--
-- 1. ``assessments.delay_days`` - the delay (7 or 28 days) at which a ``mode='transfer'``
--    assessment was taken. Nullable: every diagnostic/final row stays NULL and no
--    existing row is rewritten. The delay is the measurement (Karpicke & Roediger 2008
--    test learning at a delay), so it is stored, not inferred.
-- 2. ``experiment_exposures`` - the writer half of the A/B layer. ``experiments`` and
--    ``experiment_assignments`` shipped in v4 with zero writers; exposure logging is
--    what makes an assigned-but-never-shown user distinguishable from a participant.

ALTER TABLE assessments ADD COLUMN delay_days integer;

CREATE TABLE experiment_exposures (
    id varchar(36) PRIMARY KEY,
    experiment_id varchar(36) NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
    user_id varchar(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    surface varchar(40) NOT NULL,
    exposed_at double precision NOT NULL DEFAULT (EXTRACT(epoch FROM now())),
    CONSTRAINT experiment_exposures_unique_per_surface UNIQUE (experiment_id, user_id, surface)
);

CREATE INDEX ix_experiment_exposures_user_id ON experiment_exposures (user_id);
