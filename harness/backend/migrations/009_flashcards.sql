-- 009_flashcards.sql -- v8 -> v9
-- PostgreSQL reference DDL for the persisted flashcard deck. ``scripts/init_db.py`` is the
-- authoritative SQLite path and creates the same table via ``create_all``; this file
-- documents and applies the change for upgraded PostgreSQL databases.
--
-- Why a table and not the existing generator: ``harness.generate`` produced flashcards as
-- an in-memory artifact for a single request. A card that is never stored can be read but
-- never reviewed, and review is the only event the FSRS-6 model in ``app.memory`` learns
-- from. ``due_at`` / ``stability`` / ``difficulty`` are that model's state, so a reviewed
-- card feeds the same memory curve as concept-level practice.

CREATE TABLE flashcards (
    id varchar(36) PRIMARY KEY,
    user_id varchar(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    concept_id varchar(64) NOT NULL,
    front text NOT NULL,
    back text NOT NULL,
    hint text,
    tags json NOT NULL DEFAULT '[]',
    source json NOT NULL DEFAULT '{}',
    kind varchar(20) NOT NULL DEFAULT 'basic',
    front_key varchar(64) NOT NULL,
    due_at double precision NOT NULL DEFAULT (EXTRACT(epoch FROM now())),
    stability double precision,
    difficulty double precision,
    reps integer NOT NULL DEFAULT 0,
    lapses integer NOT NULL DEFAULT 0,
    last_review_at double precision,
    last_grade smallint,
    state varchar(20) NOT NULL DEFAULT 'new',
    created_at double precision NOT NULL DEFAULT (EXTRACT(epoch FROM now())),
    updated_at double precision NOT NULL DEFAULT (EXTRACT(epoch FROM now())),
    CONSTRAINT flashcards_kind_ck CHECK (kind IN ('basic','cloze','definition','formula','misconception')),
    CONSTRAINT flashcards_state_ck CHECK (state IN ('new','learning','review','relearning')),
    CONSTRAINT flashcards_user_concept_front_key UNIQUE (user_id, concept_id, front_key)
);

CREATE INDEX flashcards_user_due_idx ON flashcards (user_id, due_at);
CREATE INDEX flashcards_user_concept_idx ON flashcards (user_id, concept_id);
