# First-person acceptance evidence — 2026-11-08

Durable, token-redacted copy of `.tmp/first-person-evidence-1108/`. The raw unsanitised run stays in the gitignored `.tmp/` directory.

**Result: 29 / 29 steps passed** against a fresh database, a brand-new learner account, an unseen topic, and no configured tutor provider. Steps 16–19 exercise the unit grade book and written perspective evidence over real HTTP.

The unseen-topic step passes as a *declared fallback* (a structured, non-fabricating notice), not as a generated lesson. That is an honest limit, not a claim that offline unseen-topic teaching works.

# First-person acceptance run

- backend: `http://127.0.0.1:53170` · database: `/Users/tengyi/WorkBuddy AI/2026-10-10-18-14-50/harness/.tmp/fp-verify-1108-20tq14hl/h.sqlite3`
- unseen topic: **creep deformation of titanium aluminide turbine blades**
- result: **29/29 steps passed**

| # | Step | Pass | Evidence |
|---|---|---|---|
| 1 | 01 health | PASS | `{"status": 200, "body": {"ready": true, "service": "luminfest-learning-harness", "schema_version": 11, "model_status": {"name": "FSRS-6 DSR memory model (upstream defaults v6.3.2) + heuristic BKT mastery", "trained": false, "domain": "mathematics; memory model is principled, mastery prior is not calibrated", "commercia …[672 chars]` |
| 2 | 02 register fresh learner | PASS | `{"status": 201, "body": {"token": "[REDACTED]", "refresh_token": "[REDACTED]", "token_type": "Bearer", "expires_in": 3600, "user": {"id": "b46a9628-8fd8-4d0e-971b-73042342fcf8", "name": "First Person Learner", "email": "fi …[619 chars]` |
| 3 | 02b no operator promotion | PASS | `{"role": "learner"}` |
| 4 | 03 topic is unseen | PASS | `{"status": 200, "body": {"query": "creep deformation of titanium aluminide turbine blades", "results": []}}` |
| 5 | 04 ask to be taught the unseen topic (answer or declared fallback) | PASS | `{"status": 200, "body": {"message": null, "finish_reason": "unavailable", "events": [{"type": "error", "message": "Model not configured. The harness falls back to deterministic, grounded-offline content when no provider is set."}, {"type": "turn_end", "reason": "unavailable", "content": null, "notice": {"kind": "unavai …[1414 chars]` |
| 6 | 04b agent chat scoped to a concept | PASS | `{"status": 200, "body": {"message": "Grounded offline tutor — curriculum retrieval, not an LLM.\n\nA fraction describes equal parts of a whole. Equivalent fractions multiply numerator and denominator by the same nonzero number.\n\nChoose a common unit before adding numerators.\nFrom your own recorded work: No prior obs …[4382 chars]` |
| 7 | 05 generate a course from the topic name | PASS | `{"status": 200, "body": {"course_id": "mine_c81d281af9", "title": "Gas-turbine engine", "subject": "Blades, Creep, Turbine", "level": "project_led", "concepts": 42, "questions": 168, "graph_stats": {"concepts": 42, "edges": 5, "sequence_edges": 41, "strands": 1, "units": 1, "topics": 26, "roots": 37, "leaves": 38, "max …[2297 chars]` |
| 8 | 05b save and enrol the generated course | PASS | `{"status": 201, "body": {"course_id": "mine_a68aabd665", "title": "Gas-turbine engine", "subject": "Blades, Creep, Turbine", "level": "project_led", "concepts": 42, "questions": 168, "graph_stats": {"concepts": 42, "edges": 5, "sequence_edges": 41, "strands": 1, "units": 1, "topics": 26, "roots": 37, "leaves": 38, "max …[3239 chars]` |
| 9 | 05c generated lesson has independent worked example | PASS | `{"lesson": {"id": "mine_a68aabd665_a_gas_turbine", "title": "A gas turbine", "unit": "Gas-turbine engine", "strand": "Blades, Creep, Turbine", "topic": "General", "tier": "foundation", "difficulty": 1, "blocks": [{"kind": "concept", "title": "Core idea", "body": "A gas turbine is a complete continuous-flow internal com …[3419 chars]` |
| 10 | 06 available courses | PASS | `{"status": 200, "body": {"courses": [{"id": "integrated_math_1", "title": "Integrated Mathematics I", "subject": "Mathematics", "subject_kind": "mathematics", "description": "A full-year integrated mathematics course: number and quantity, algebra, functions, geometry and measurement, statistics and probability.", "expe …[17114 chars]` |
| 11 | 07 chat on an unknown topic is refused | PASS | `{"status": 404, "body": {"detail": "Unknown concept for this course"}}` |
| 12 | 08 start a lesson | PASS | `{"status": 200, "body": {"run_id": "6454d07c-a5ef-45f7-9497-e8b9c4da39fc", "concept_id": "mine_a68aabd665_a_gas_turbine", "concept_title": "A gas turbine", "course_id": "mine_a68aabd665", "hash": "087404fa852925e57653c1d559ac7bd2", "status": "active", "budget_minutes": 20, "total_minutes": 11, "blocks": [{"order": 1, " …[8319 chars]` |
| 13 | 09 lesson plan binds answerable questions | PASS | `{"order": 1, "total": 2, "block_kinds": ["diagnostic", "deck", "practice"]}` |
| 14 | 09a done is refused before the answers exist | PASS | `{"refusal": {"status": 409, "body": {"detail": "Block 1 promised 2 scored question(s) and 0 have an answer recorded. Answer the rest before marking it done, or skip the block."}}, "counts_before": {"attempts": 0}, "counts_after": {"attempts": 0}}` |
| 15 | 09b the lesson serves its bound signed question | PASS | `{"status": 200, "body": {"run_id": "6454d07c-a5ef-45f7-9497-e8b9c4da39fc", "block_order": 1, "question": {"id": "mine_a68aabd665-mine_a68aabd665_a_gas_turbine-0", "concept_id": "mine_a68aabd665_a_gas_turbine", "concept_title": "A gas turbine", "prompt": "Which statement best describes A gas turbine?", "options": [{"id" …[1711 chars]` |
| 16 | 09c answers are scored and recorded | PASS | `{"answered": [{"question_id": "mine_a68aabd665-mine_a68aabd665_a_gas_turbine-0", "status": 200, "diagnosis": {"category": "conceptual", "reason": "Tentative: This belongs to \"A turboprop engine\", not to \"A gas turbine\". Naming which idea a wrong option belongs to turns a wrong answer into a diagnosis. This option i …[9861 chars]` |
| 17 | 09d done is accepted after the answers | PASS | `{"status": 200, "body": {"run_id": "6454d07c-a5ef-45f7-9497-e8b9c4da39fc", "concept_id": "mine_a68aabd665_a_gas_turbine", "concept_title": "A gas turbine", "course_id": "mine_a68aabd665", "hash": "087404fa852925e57653c1d559ac7bd2", "status": "active", "budget_minutes": 20, "total_minutes": 11, "blocks": [{"order": 1, " …[11267 chars]` |
| 18 | 10 serve a real question | PASS | `{"status": 200, "body": {"id": "mine_a68aabd665-mine_a68aabd665_a_gas_turbine-2", "concept_id": "mine_a68aabd665_a_gas_turbine", "concept_title": "A gas turbine", "prompt": "Which of these does your source present later than A gas turbine?", "options": [{"id": "a", "text": "A turbocharger"}, {"id": "b", "text": "Advant …[989 chars]` |
| 19 | 11 answer the question | PASS | `{"status": 200, "body": {"id": "26381caa-d5ff-4b9f-83e3-a8f6b06ec93c", "correct": false, "correct_answer": "Concept cars", "explanation": "Concept cars depends on A gas turbine in your course graph, so the source meets it later.", "diagnosis": {"category": "conceptual", "reason": "Tentative: This belongs to \"A turboch …[1053 chars]` |
| 20 | 12 learning state moved and next review scheduled | PASS | `{"states": [{"concept_id": "mine_a68aabd665_a_gas_turbine", "data": {"stability": 0.1506138490725352, "difficulty": 9.134384137540838, "last_review": 1794149583.863092, "reps": 3, "lapses": 2, "memory_model": "fsrs-6", "memory_model_note": "stability seeded from legacy half_life_days (Leitner heuristic); FSRS updates t …[1550 chars]` |
| 21 | 13 recompile plan after the answer | PASS | `{"status": 200, "body": {"plan": {"concept_id": "mine_a68aabd665_a_gas_turbine", "concept_title": "A gas turbine", "course_id": "mine_a68aabd665", "profile": "default", "version": "1", "hash": "6de801e2352c8f20ca24c06cefd85380", "enabled": true, "budget_minutes": 20, "total_minutes": 11, "blocks": [{"order": 1, "kind": …[18259 chars]` |
| 22 | 14 voice behaviour is honest | PASS | `{"status": 200, "body": {"raw_bytes": 41132, "preview": "ID3\u0004\u0000\u0000\u0000\u0000\u0000\"TSSE\u0000\u0000\u0000\u000e\u0000\u0000\u0003Lavf61.7.100\u0000\u0000\u0000\u0000\u0000\u0000\u0000\u0000\u0000\u0000\u0000����\u0000DL)�\u0016ɓ�\u0001�r\u001f��\u0013\u000b\"[p(�I&Y�YfY&�F \u0005�`�\u0017�\u0018 P3����0� …[506 chars]` |
| 23 | 14b tutor actually speaks | PASS | `{"status": 200, "body": {"raw_bytes": 41132, "preview": "ID3\u0004\u0000\u0000\u0000\u0000\u0000\"TSSE\u0000\u0000\u0000\u000e\u0000\u0000\u0003Lavf61.7.100\u0000\u0000\u0000\u0000\u0000\u0000\u0000\u0000\u0000\u0000\u0000����\u0000DL)�\u0016ɓ�\u0001�r\u001f��\u0013\u000b\"[p(�I&Y�YfY&�F \u0005�`�\u0017�\u0018 P3����0� …[506 chars]` |
| 24 | 15 lesson ends with a summary | PASS | `{"status": 200, "body": {"run_id": "6454d07c-a5ef-45f7-9497-e8b9c4da39fc", "concept_id": "mine_a68aabd665_a_gas_turbine", "concept_title": "A gas turbine", "course_id": "mine_a68aabd665", "hash": "087404fa852925e57653c1d559ac7bd2", "status": "completed", "budget_minutes": 20, "total_minutes": 11, "blocks": [{"order": 1 …[7893 chars]` |
| 25 | 16 gradebook declares standards and no invented grade | PASS | `{"status": 200, "body": {"course_id": "mine_a68aabd665", "units": [{"key": "blades-creep-turbine-gas-turbine-engine-f21bef74", "strand": "Blades, Creep, Turbine", "unit": "Gas-turbine engine", "course_id": "mine_a68aabd665", "concept_count": 42, "standards": [{"code": "gas-turbine-engine-5c8b5123.advantages-and-disadva …[9341 chars]` |
| 26 | 16b an unevidenced unit grade is refused with reasons | PASS | `{"status": 409, "body": {"detail": {"reason": "This unit has no defensible grade yet.", "missing_standards": ["Advantages and disadvantages", "Aeroderivative gas turbines (industrial turboshafts)", "Applications", "Compressed-air energy storage", "Concept cars", "External links", "Industrial gas turbines for power gene …[815 chars]` |
| 27 | 17 empty perspectives are absent, not zero | PASS | `{"status": 200, "body": {"dimensions": [{"name": "Participation", "code": "participation", "value": null, "evidence": "No written rubric observation has been recorded for this dimension. A count of active minutes is not a participation score. Only written observations count here.", "status": "insufficient_evidence", "m …[2665 chars]` |
| 28 | 18 a written observation is scored only on a real artifact | PASS | `{"short_note": 422, "invented_artifact": 422, "created": 200, "analytics_value": 0.75, "attention_last": "Cognitive attention", "attention_value": null, "withdrawn": 200}` |
| 29 | 19 export covers grade book and perspective records | PASS | `{"status": 200, "body": {"exported_at": "2026-11-08T14:53:18.722716+00:00", "schema_version": 11, "user": {"id": "b46a9628-8fd8-4d0e-971b-73042342fcf8", "name": "First Person Learner", "email": "first-person-9664a36b0364@example.test", "goal": "Build real understanding", "daily_minutes": 20, "telemetry_consent": false, …[26299 chars]` |

## Health / provider declaration

```json
{"ready": true, "service": "luminfest-learning-harness", "schema_version": 11, "model_status": {"name": "FSRS-6 DSR memory model (upstream defaults v6.3.2) + heuristic BKT mastery", "trained": false, "domain": "mathematics; memory model is principled, mastery prior is not calibrated", "commercial_ready": false}, "tutor": {"provider": "offline", "availability": "local"}, "harness": {"moves": 9, "tools": 51, "artefacts": 11, "memory_kinds": ["episodic", "semantic", "procedural"], "memory_half_life_days": 21.0, "sandbox_boundaries": ["path-confinement", "static-guard", "runtime-audit-hook", "seatbelt"], "generation_mode": "grounded-offline"}}
```

## Agent turn on the unseen topic

```json
{"answered_by": "grounded-offline", "provider": "grounded-offline", "grounded_offline": false, "finish_reason": "unavailable", "tool_calls": [], "message": "null", "notice": "{\"kind\": \"unavailable\", \"reason\": \"No tutor model is configured on this instance, and this question is not scoped to a concept in your course, so there is no grounded material to teach from.\", \"next_action\": \"Open a concept from your course and ask again, or build a course from your own notes so the offline tutor has a source to ground its answer in. Teaching a topic that is not in your course yet requires a configured tutor provider.\"}"}
```

## Database row counts

```json
{"after_generation": {"users": 1, "attempts": 0, "learning_states": 0, "procedure_runs": 1, "created_courses": 0, "messages": 2, "flashcards": 0, "assessments": 0, "unit_grades": 0, "perspective_reviews": 0}, "after_answer": {"users": 1, "attempts": 3, "learning_states": 1, "procedure_runs": 2, "created_courses": 1, "messages": 2, "flashcards": 0, "assessments": 0, "unit_grades": 0, "perspective_reviews": 0}, "final": {"users": 1, "attempts": 3, "learning_states": 1, "procedure_runs": 2, "created_courses": 1, "messages": 2, "flashcards": 0, "assessments": 0, "unit_grades": 0, "perspective_reviews": 0}}
```

Full machine-readable evidence: `first-person-run.json`.
