# Where do I change this?

A capability → entry point → files → tests map for the Luminest learning harness.
Every path below is relative to `harness/`, and every `path:line` was verified against the
working tree on 2026-11-08 with the checks described in
[How this table was verified](#how-this-table-was-verified). The guard
`backend/tests/test_architecture_guards.py` re-checks the file references on every run,
so a moved or deleted file fails the suite rather than leaving a plausible-looking lie.

Read this with [`../../ARCHITECTURE.md`](../../ARCHITECTURE.md) for the shape of the system
and the ADRs for the rules: [ADR-0001](ADR-0001-architecture-principles.md),
[ADR-0003](ADR-0003-native-boundaries.md), [ADR-0004](ADR-0004-api-contract-discipline.md),
[ADR-0005](ADR-0005-database-migration-policy.md),
[ADR-0006](ADR-0006-no-duplicated-business-logic.md).

**A note on a moving tree.** During this documentation pass two relocations were in
flight: the account family moved from `backend/app/main.py` into
`backend/app/api/v1/account.py`, and the native app's `Core.swift` / `BoardEditor.swift`
were split into `native/Sources/LearningHarness/Shared/` and
`native/Sources/LearningHarness/Features/Board/`. The table cites the post-move
locations. Where a symbol is more stable than its file, the symbol is named
(`AppStore`, `BoardEditor`, `BoardStore`) so a further move does not invalidate the row.

---

## The table

| Capability | Entry point (HTTP route · native screen) | Files to read | Tests that cover it |
| --- | --- | --- | --- |
| **Sign-in, registration, email verification, password reset** | `POST /api/v1/auth/register` at `backend/app/main.py:941`; `POST /api/v1/auth/login` at `backend/app/main.py:1003`; `POST /api/v1/auth/refresh` at `backend/app/main.py:1026`; `POST /api/v1/auth/verify-email` at `backend/app/main.py:1044`; `POST /api/v1/auth/reset-password` at `backend/app/main.py:1094` · `OnboardingView` at `native/Sources/LearningHarness/LuminfestApp.swift:203`, reached from `RootView` at `native/Sources/LearningHarness/LuminfestApp.swift:98`; the request itself is built in `AppStore.signIn` at `native/Sources/LearningHarness/Shared/State/AppStore.swift:293` | `backend/app/main.py` (routes), `backend/app/security.py` (hashing, sessions, rate limits), `backend/app/accounts.py` (mail + waitlist), `backend/app/schemas.py` (request shapes) | `backend/tests/test_accounts.py`, `backend/tests/test_account_auth_single_source.py`, `backend/tests/test_security_contract.py` |
| **Session list, revoke, logout everywhere** | `GET /api/v1/auth/sessions` at `backend/app/main.py:1115`; `DELETE /api/v1/auth/sessions/{session_id}` at `backend/app/main.py:1127`; `POST /api/v1/auth/logout-all` at `backend/app/main.py:1137` · `SettingsPage` at `native/Sources/LearningHarness/ProjectsInsightsSettings.swift:108` | `backend/app/security.py` (`issue_session`, `rotate_refresh`, `revoke_all_sessions`), `backend/app/main.py` | `backend/tests/test_accounts.py`, `backend/tests/test_account_auth_single_source.py` |
| **Profile and preferences** | `GET /api/v1/me` at `backend/app/main.py:1151`; `PATCH /api/v1/me` at `backend/app/main.py:1155`; `GET /api/v1/preferences` at `backend/app/api/v1/account.py:62`; `PATCH /api/v1/preferences` at `backend/app/api/v1/account.py:69` · `SettingsPage` at `native/Sources/LearningHarness/ProjectsInsightsSettings.swift:108`, store method in `native/Sources/LearningHarness/Shared/State/AppStore+Account.swift` | `backend/app/api/v1/account.py`, `backend/app/accounts.py` (`preferences_for`, `preferences_json`), `backend/app/schemas.py` (`Profile`, `PreferencePatch`) | `backend/tests/test_accounts.py`, `backend/tests/test_final_contract.py` |
| **Account deletion and the erasure ledger** | `DELETE /api/v1/me` at `backend/app/main.py:4144` · the delete button and its confirmation phrase are in `SettingsPage` at `native/Sources/LearningHarness/ProjectsInsightsSettings.swift:482`; the call is `AppStore.deleteAccount()` at `native/Sources/LearningHarness/Shared/State/AppStore+Account.swift:83` | `backend/app/account_erasure.py` (policy, cascade, `erased_accounts.jsonl`, `reconcile`), `backend/app/main.py` (the route and the boot-time re-purge), `backend/legal/privacy.md` section 7 | `backend/tests/test_account_deletion.py` (cascade table-by-table, artefacts, restore-then-token, policy numbers bound to `legal/privacy.md`) |
| **Tutor chat (history + one turn)** | `GET /api/v1/chat` at `backend/app/main.py:2040`; `POST /api/v1/chat` at `backend/app/main.py:2185` · `TutorPanel` at `native/Sources/LearningHarness/Studio.swift:707`; `AppStore.loadChat()` / `sendMessage` at `native/Sources/LearningHarness/Shared/State/AppStore+Tutor.swift:4` | `backend/app/tutor.py`, `backend/app/harness/loop.py` (the agent loop), `backend/app/content_locale.py` (generated-content language), `backend/app/db.py` (`Message`) | `backend/tests/test_api.py`, `backend/tests/test_agent_loop.py`, `backend/tests/test_tutoring_coverage.py` |
| **Streaming agent turn** | `POST /api/v1/agent/chat` at `backend/app/main.py:3639`; `POST /api/v1/agent/stream` at `backend/app/main.py:3686` · consumed by `APIClient.serverEvents` at `native/Sources/LearningHarness/Shared/Networking/APIClient.swift:118` and rendered in `TutorPanel` at `native/Sources/LearningHarness/Studio.swift:707` | `backend/app/main.py` (both routes), `backend/app/harness/loop.py`, `backend/app/harness/agent_loop.py`, `native/Sources/LearningHarness/Shared/Networking/ServerEvent.swift` | `backend/tests/test_agent_loop.py`, `backend/tests/test_stream.py` |
| **Questions, attempts, grading** | `GET /api/v1/questions/next` at `backend/app/main.py:1525`; `POST /api/v1/attempts` at `backend/app/main.py:1669` · `QuestionView` at `native/Sources/LearningHarness/QuestionView.swift:3`; `AppStore.submitAnswer()` at `native/Sources/LearningHarness/Shared/State/AppStore.swift:411` | `backend/app/learning.py` (mastery update), `backend/app/curriculum.py` (`QUESTIONS`, `authored_share`), `backend/app/learning_science.py` (calibration, transfer), `backend/app/schemas.py` (`AttemptInput`) | `backend/tests/test_learning.py`, `backend/tests/test_learning_science.py`, `backend/tests/test_psychometrics.py` |
| **Flashcards and spaced review** | `GET /api/v1/flashcards/session` at `backend/app/routes_flash.py:143`; `POST /api/v1/flashcards/{card_id}/review` at `backend/app/routes_flash.py:245`; `POST /api/v1/flashcards/generate` at `backend/app/routes_flash.py:259` · `FlashcardsView` at `native/Sources/LearningHarness/Flashcards.swift:241`; `ReviewView` at `native/Sources/LearningHarness/TodayKnowledge.swift:745` | `backend/app/routes_flash.py` (HTTP only), `backend/app/flashcards.py` (FSRS-6 scheduling, de-duplication), `backend/app/memory.py` (the scheduler switch), `backend/app/db.py` (`Flashcard`) | `backend/tests/test_flashcards.py`, `backend/tests/test_memory.py` |
| **Knowledge map and curriculum** | `GET /api/v1/curriculum` at `backend/app/main.py:1275`; `GET /api/v1/knowledge-graph` at `backend/app/main.py:1300`; `GET /api/v1/knowledge-graph/{concept_id}` at `backend/app/main.py:1382`; `GET /api/v1/knowledge-graph/coverage/me` at `backend/app/main.py:1411` · `KnowledgeView` at `native/Sources/LearningHarness/TodayKnowledge.swift:234`, `GraphOverview` at `native/Sources/LearningHarness/TodayKnowledge.swift:418` | `backend/app/curriculum.py`, `backend/app/knowledge_graph.py`, `backend/app/courses.py` (course registry and enrolment), `backend/app/curriculum_packs/` | `backend/tests/test_knowledge_graph.py`, `backend/tests/test_multisubject.py`, `backend/tests/test_curriculum_route.py` |
| **Board / canvas (whiteboard)** | `GET /api/v1/boards` at `backend/app/main.py:2894`; `POST /api/v1/boards` at `backend/app/main.py:2899`; `POST /api/v1/boards/{board_id}/diagram` at `backend/app/main.py:2931`; `PATCH /api/v1/boards/{board_id}` at `backend/app/main.py:3078`; `GET /api/v1/boards/{board_id}/export` at `backend/app/main.py:3102`; live classroom ink: `POST /api/v1/whiteboards/{board_id}/ink` at `backend/app/main.py:3798` · `BoardEditor` at `native/Sources/LearningHarness/Features/Board/BoardEditor.swift:34`, document model `BoardStore` at `native/Sources/LearningHarness/Board.swift:65`, legacy `CanvasView` at `native/Sources/LearningHarness/CanvasView.swift:39` | `backend/app/harness/board.py` (storage), `backend/app/harness/whiteboard.py` (classroom ink), `backend/app/harness/diagram.py` (AI line diagrams), `native/Sources/LearningHarness/BoardKit.swift` (geometry, snap, undo) | `backend/tests/test_board.py`, `backend/tests/test_whiteboard_unification.py`, `backend/tests/test_diagram.py` |
| **Decks (slide editor and .pptx)** | `GET /api/v1/deck` at `backend/app/routes_deck.py:111`; `POST /api/v1/deck/{deck_id}/slides` at `backend/app/routes_deck.py:211`; `GET /api/v1/deck/{deck_id}/export.pptx` at `backend/app/routes_deck.py:323`; `POST /api/v1/deck/import` at `backend/app/routes_deck.py:342` · `DeckEditorView` at `native/Sources/LearningHarness/DeckEditor.swift:726`; `NarratedDeckView` at `native/Sources/LearningHarness/MediaTools.swift:236` | `backend/app/routes_deck.py` (HTTP + ownership only), `backend/app/deck.py` (document validation and mutation rules), `native/Sources/LearningHarness/DeckEditor.swift` | `backend/tests/test_deck.py`, `backend/tests/test_feature_routers.py` |
| **Simulations** | `GET /api/v1/simulations/{concept_id}` at `backend/app/main.py:1417`; `GET /api/v1/simulations` at `backend/app/main.py:2506`; `GET /api/v1/simulations/{concept_id}/external` at `backend/app/main.py:2517` · `SimulationView` at `native/Sources/LearningHarness/Studio.swift:387`; `SimulationDetail` at `native/Sources/LearningHarness/SimulationDetail.swift` | `backend/app/mathkit/` (symbolic build, whitelisted kinds), `backend/app/simulation_map.py`, `backend/app/harness/guided_sim.py` (the predict/explain gate) | `backend/tests/test_mathkit.py`, `backend/tests/test_guided_sim.py`, `backend/tests/test_sims_check.py` |
| **Lectures (auto-generated, with media)** | `GET /api/v1/lecture/{concept_id}` at `backend/app/main.py:2455`; `POST /api/v1/lecture/{concept_id}/start` at `backend/app/main.py:2465`; `POST /api/v1/lecture/{concept_id}/segment/{index}` at `backend/app/main.py:2480` · `LectureTheater` at `native/Sources/LearningHarness/LectureMode.swift:162`; `LectureStore` at `native/Sources/LearningHarness/LectureMode.swift:46` | `backend/app/lecture.py` (segment plan, cache under `data_dir/lectures/`), `backend/app/harness/media.py` (segment imagery), `backend/app/harness/speech.py` (narration) | `backend/tests/test_lecture.py` |
| **Media, image search and speech output** | `GET /api/v1/media/sources` at `backend/app/main.py:2382`; `GET /api/v1/media/images` at `backend/app/main.py:2394`; `GET /api/v1/media/images/{sha}/bytes` at `backend/app/main.py:3164`; `POST /api/v1/voice/speak` at `backend/app/main.py:3188`; `POST /api/v1/images/fetch` at `backend/app/routes_media.py:130` · `NativeMediaView` at `native/Sources/LearningHarness/Studio.swift:528`; image insertion sheet at `native/Sources/LearningHarness/Features/Board/BoardSheets.swift:47` | `backend/app/harness/media.py` (licence gate, cache, attribution), `backend/app/routes_media.py`, `backend/app/harness/speech.py`, `backend/app/capabilities.py` | `backend/tests/test_media_pipeline.py`, `backend/tests/test_image_fetch.py`, `backend/tests/test_image_mime_normalisation.py` |
| **Course builder (a course from the learner's own material)** | `POST /api/v1/create/preview` at `backend/app/routes_create.py:164`; `POST /api/v1/create/course` at `backend/app/routes_create.py:175`; `POST /api/v1/create/upload` at `backend/app/routes_create.py:253`; `POST /api/v1/create/auto` at `backend/app/routes_source.py:124`; `GET /api/v1/my-courses` at `backend/app/routes_create.py:311` · `CourseSetupView` at `native/Sources/LearningHarness/CourseSetup.swift:8`, `CourseSwitcher` at `native/Sources/LearningHarness/CourseSetup.swift:606` | `backend/app/routes_create.py`, `backend/app/routes_source.py`, `backend/app/course_builder.py` (intake, planning, persistence), `backend/app/generated_curriculum.py` | `backend/tests/test_course_builder.py`, `backend/tests/test_creation_tools.py`, `backend/tests/test_source_extension.py` |
| **Authored courses (the foundry)** | `POST /api/v1/author/draft` at `backend/app/routes_authoring.py:214`; `POST /api/v1/author/courses` at `backend/app/routes_authoring.py:181`; `POST /api/v1/author/courses/{course_id}/rebuild` at `backend/app/routes_authoring.py:299` · `TeacherPage` at `native/Sources/LearningHarness/Studio.swift:648` | `backend/app/harness/authoring/`, `backend/app/routes_authoring.py`, `backend/app/ingest/policy.py` | `backend/tests/test_authoring.py`, `backend/tests/test_authoring_overlay.py` |
| **Usage limits and quotas** | `GET /api/v1/usage` at `backend/app/api/v1/account.py:57`. **There is no native screen for this and none in the browser UI today** — `grep -rn '"/usage"' native/Sources harness/web` returns nothing, so the route is the only entry point | `backend/app/api/v1/account.py`, `backend/app/accounts.py` (`effective_policies`, `usage_summary`), `backend/app/db.py` (`QuotaPolicy`, `QuotaCounter`, `UsageLedger`) | `backend/tests/test_metering.py`, `backend/tests/test_accounts.py` |
| **Backup and restore** | No HTTP route and no UI. Operator surface: `backend/scripts/backup_drill.py`; the library is `create_sqlite_backup` at `backend/app/database_backup.py:788`, `restore_sqlite_backup` at `backend/app/database_backup.py:1503`, `prune_sqlite_backups` at `backend/app/database_backup.py:1218` | `backend/app/database_backup.py` (manifest + sidecar, verify, retention, maintenance lock), `backend/app/account_erasure.py` (the ledger that survives a restore) | `backend/tests/test_database_backup.py`, `backend/tests/test_backup_resilience.py`, `backend/tests/test_account_deletion.py` |
| **Schema upgrade** | No route. Entry point is the explicit CLI: `initialize()` at `backend/scripts/init_db.py:267`, run as `python backend/scripts/init_db.py`. The app refuses to start on a mismatch at `backend/app/main.py:721` and `backend/app/main.py:725` | `backend/app/db.py` (`SCHEMA_VERSION` at `backend/app/db.py:75`), `backend/scripts/init_db.py` (`ADDED_COLUMNS`, `SCHEMA_LANDMARKS`), `backend/migrations/`, `backend/scripts/schema_parity.py` | `backend/tests/test_schema_equivalence.py`, `backend/tests/test_database_engines.py`, `backend/tests/test_backup_resilience.py` |
| **Localisation (interface language and generated content)** | `PATCH /api/v1/preferences` at `backend/app/api/v1/account.py:69` (stores `locale`); the request's `Accept-Language` is turned into generated-content language at `backend/app/main.py:773` · `AppLanguage` at `native/Sources/LearningHarness/Localization.swift:12`, lookup at `native/Sources/LearningHarness/Localization.swift:58`; strings in `native/Sources/LearningHarness/Resources/en.lproj/Localizable.strings` and `native/Sources/LearningHarness/Resources/zh-Hans.lproj/Localizable.strings` | `backend/app/content_locale.py`, `native/Sources/LearningHarness/Localization.swift`, `native/Sources/LearningHarness/Shared/Networking/APIClient.swift` (`acceptLanguage` at `native/Sources/LearningHarness/Shared/Networking/APIClient.swift:68`) | `backend/tests/test_content_locale.py`, `native/Tests/LearningHarnessTests/LocalizationTests.swift`, `native/Tests/LearningHarnessTests/ContentLanguageTests.swift` |
| **Theming and appearance** | No route — the preference is local. `AppearancePreference` at `native/Sources/LearningHarness/Theme.swift:130`, `TextScale` at `native/Sources/LearningHarness/Theme.swift:105`; the control is in `SettingsPage` at `native/Sources/LearningHarness/ProjectsInsightsSettings.swift:108` | `native/Sources/LearningHarness/Theme.swift`, `native/Sources/LearningHarness/Design.swift` (`Palette`, `Accent`, button styles) | No dedicated test today; the palette is exercised indirectly by `native/Tests/LearningHarnessTests/SidebarBreakpointTests.swift` and the UI tests under `ui-tests/` |
| **Diagnostics and support report** | `GET /api/v1/diagnostics` at `backend/app/main.py:4072`; `GET /api/v1/health` at `backend/app/main.py:4161` · `DiagnosticsPanel` at `native/Sources/LearningHarness/StateViews.swift:640`; `AppStore.loadDiagnostics()` at `native/Sources/LearningHarness/Shared/State/AppStore+Account.swift:64` | `backend/app/main.py` (the narrow report), `backend/app/learning.py` (`model_status`), `native/Sources/LearningHarness/StateViews.swift` | `backend/tests/test_release_surface.py`, `backend/tests/test_final_contract.py` |
| **Data export** | `GET /api/v1/export` at `backend/app/main.py:4119` · `AppStore.exportAccount()` at `native/Sources/LearningHarness/Shared/State/AppStore+Account.swift:51` | `backend/app/main.py` (`export`), `backend/app/db.py` (the tables it serialises), `native/Sources/LearningHarness/Shared/State/AppStore+Account.swift` | `backend/tests/test_api.py`, `backend/tests/test_account_deletion.py` |
| **Desktop launcher and server discovery** | No route of its own; it probes `GET /api/v1/health` and refuses a server whose `schema_version` differs. `expectedSchemaVersion` at `native/Sources/LearningHarness/BackendLauncher.swift:100`, verdict logic at `native/Sources/LearningHarness/BackendLauncher.swift:216` | `native/Sources/LearningHarness/BackendLauncher.swift`, `backend/desktop_entry.py`, `backend/app/config.py` | `native/Tests/LearningHarnessTests/BackendLauncherTests.swift` |
| **Browser workbench** | `GET /` at `backend/app/web_routes.py:249`; `GET /api/v1/role` at `backend/app/web_routes.py:323`; `GET /api/v1/sims` at `backend/app/web_routes.py:271`; `GET /web/{asset_path}` at `backend/app/web_routes.py:257` | `backend/app/web_routes.py`, `web/app.js`, `web/index.html`, `web/cards.js`, `web/telemetry.js` | `backend/tests/test_web_routes_contract.py`, `backend/tests/test_web_cards_helper.py`, `backend/tests/test_web_telemetry_helper.py` |
| **Simulator playground** | `GET /api/v1/playground` at `backend/app/playground_routes.py:186`; `POST /api/v1/playground/games/{slug}/outcome` at `backend/app/playground_routes.py:301`; the page itself is `GET /playground` at `backend/app/playground_routes.py:80` | `backend/app/playground_routes.py`, `backend/app/harness/playground/` (catalogue, pipeline, archetypes, evidence), `harness/web/playground.html` | `backend/tests/test_playground.py`, `backend/tests/test_playground_correctness.py`, `backend/tests/test_playground_guided.py` |

---

## Route modules

Every module that defines HTTP routes, and what it owns. The guard test asserts this list
is complete: a new `routes_*` module that is not named here fails the suite.

| Module | Routes | Owns |
| --- | --- | --- |
| `backend/app/main.py` | 125 | Application composition, auth, account, curriculum, questions, boards, chat, agent, lecture, media, TA, admin, legal, health |
| `backend/app/api/v1/account.py` | 3 | `usage`, `preferences` — the first family relocated out of `main.py` |
| `backend/app/routes_deck.py` | 19 | Slide decks and `.pptx` bridge |
| `backend/app/routes_authoring.py` | 12 | The authored-course foundry |
| `backend/app/routes_flash.py` | 10 | Flashcards |
| `backend/app/routes_procedure.py` | 8 | Compiled lesson procedures |
| `backend/app/routes_create.py` | 7 | Courses built from learner material |
| `backend/app/routes_stream.py` | 6 | Desktop window streaming |
| `backend/app/routes_media.py` | 6 | Image search, paste, attribution |
| `backend/app/routes_multimodal.py` | 4 | Capability grants |
| `backend/app/web_routes.py` | 10 | Browser workbench + saved sims |
| `backend/app/routes_ta.py` | 2 | Teaching-assistant jobs |
| `backend/app/routes_supervision.py` | 2 | Classroom supervision |
| `backend/app/routes_source.py` | 2 | Course-from-search |
| `backend/app/routes_rewards.py` | 1 | Reward events |
| `backend/app/playground_routes.py` | 12 | Playground page + gallery/API |

`scripts/api_surface.py` is the authoritative count and description of the surface; run it
rather than counting decorators by hand:

```
cd harness/backend
.venv/bin/python scripts/api_surface.py --out /tmp/surface.json
```

At the time of writing it reports **226 route registrations** (225 handler functions;
`/api/v1/health` and `/health` are two registrations of one handler).

---

## How this table was verified

1. **Routes and line numbers.** An AST pass over the 16 route-bearing modules resolved
   `API + '/…'` constants and printed `path | method | file:line | function` for all 226
   registrations. The runtime surface was cross-checked with
   `backend/scripts/api_surface.py` (reports `route_count: 226`), which flattens this
   FastAPI build's lazy `_IncludedRouter` objects.
2. **Swift views and line numbers.** `grep -nE '^(struct|final class) …'` over
   `native/Sources/LearningHarness/**/*.swift` after the `Shared/` + `Features/Board/`
   split completed. Symbols, not just files, are named in each row because the native tree
   was moving during this pass.
3. **Tests.** Every named test file was checked with `test -f`; the capability mapping was
   produced by grepping the route literal in `backend/tests/*.py` and reading the file
   docstring, not by guessing from file names.
4. **Every `path:line` in this document** is re-parsed by
   `backend/tests/test_architecture_guards.py::test_every_index_path_exists`, which fails
   if the file is gone or the line number is past the end of the file.
