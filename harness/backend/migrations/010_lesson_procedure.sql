-- 010_lesson_procedure.sql -- v10 -> v11
-- PostgreSQL reference DDL for the persisted lesson procedure. ``scripts/init_db.py`` is
-- the authoritative SQLite path and creates the same table via ``create_all``; this file
-- documents and applies the change for upgraded PostgreSQL databases.
--
-- Why a table and not a recompute on read: the procedure is a *plan*, and a plan that
-- changes shape underneath a learner mid-session is not a lesson. Storing the compiled
-- blocks keeps the session the learner started, even after new evidence moves the policy
-- to a different plan for the next session.
--
-- Why it is not an ``attempts`` row: advancing a block says the learner did the activity,
-- not that they did it well. Mastery still moves only through the question route and the
-- playground's own outcome route. Mixing the two would let "opened the deck" be read as
-- "learned the concept".

CREATE TABLE procedure_runs (
    id varchar(36) PRIMARY KEY,
    user_id varchar(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    concept_id varchar(64) NOT NULL,
    course_id varchar(40) NOT NULL DEFAULT '',
    procedure_hash varchar(64) NOT NULL,
    profile_name varchar(40) NOT NULL DEFAULT 'default',
    budget_minutes integer NOT NULL DEFAULT 0,
    total_minutes integer NOT NULL DEFAULT 0,
    blocks json NOT NULL DEFAULT '[]',
    completed json NOT NULL DEFAULT '[]',
    skipped json NOT NULL DEFAULT '[]',
    rationale varchar(1000) NOT NULL DEFAULT '',
    status varchar(20) NOT NULL DEFAULT 'active',
    created_at double precision NOT NULL DEFAULT (EXTRACT(epoch FROM now())),
    updated_at double precision NOT NULL DEFAULT (EXTRACT(epoch FROM now())),
    CONSTRAINT procedure_runs_user_concept_hash_uq UNIQUE (user_id, concept_id, procedure_hash),
    CONSTRAINT procedure_runs_status_ck CHECK (status IN ('active','completed','abandoned'))
);

CREATE INDEX procedure_runs_user_id_idx ON procedure_runs (user_id);
CREATE INDEX procedure_runs_concept_id_idx ON procedure_runs (concept_id);
CREATE INDEX procedure_runs_hash_idx ON procedure_runs (procedure_hash);
CREATE INDEX procedure_runs_status_idx ON procedure_runs (status);
CREATE INDEX procedure_runs_active_idx ON procedure_runs (user_id, concept_id, status);
