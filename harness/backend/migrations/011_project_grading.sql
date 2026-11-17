-- 011_project_grading.sql -- v11 -> v12
-- PostgreSQL reference DDL. ``scripts/init_db.py`` applies the same additive change
-- to SQLite through ``Base.metadata.create_all`` and ``ADDED_COLUMNS``.
--
-- Why a new table: a human review corrects an earlier review but must not erase it.
-- Each score is a row with a ``supersedes`` pointer, so the history is the evidence.
-- Why the level column: assistance disclosure is a fact about the submission, not
-- an inference about AI use; a default of 'none' on an old row means 'not recorded'.

ALTER TABLE projects ADD COLUMN assistance_level text NOT NULL DEFAULT 'none';

CREATE TABLE IF NOT EXISTS project_grades (
    id varchar(36) PRIMARY KEY,
    user_id varchar(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id varchar(36) NOT NULL,
    criteria json NOT NULL DEFAULT '[]',
    total double precision NOT NULL,
    max_total double precision NOT NULL,
    status varchar(30) NOT NULL,
    rationale text NOT NULL,
    reviewer_email varchar(254) NOT NULL,
    supersedes varchar(36),
    created_at double precision NOT NULL
);

CREATE INDEX IF NOT EXISTS project_grades_user_project_idx
    ON project_grades (user_id, project_id, created_at);
