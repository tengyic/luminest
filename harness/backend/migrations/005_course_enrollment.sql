-- ============================================================================
--  Luminfest Learning Harness — schema v4 -> v5
--  Course enrolment: the subject a learner is studying.
--
--  The course registry itself lives in code (``app/courses.py``) because a course is
--  authored content, not user data. This migration only records *which* registry id a
--  learner is enrolled in, so every course-scoped view (map, figures, practice) can be
--  filtered without mixing one subject's graph into another's.
--
--  Additive and idempotent, same contract as 004.
-- ============================================================================

BEGIN;

ALTER TABLE users ADD COLUMN IF NOT EXISTS course_id text;

-- Existing learners are placed on the integrated mathematics course, which is the only
-- course a v4 database can have been serving.
UPDATE users SET course_id = 'integrated_math_1' WHERE course_id IS NULL;

ALTER TABLE users ALTER COLUMN course_id SET DEFAULT 'integrated_math_1';
ALTER TABLE users ALTER COLUMN course_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS users_course_idx ON users (course_id);

UPDATE schema_version SET version = 5 WHERE id = 1;

COMMIT;
