# 02 — Interfaces

The contract surface. These are what a change must not break; the bodies
behind them are what a retriever should fetch.

## HTTP endpoints

**`playground_routes.py`** (12)
    GET /playground  →  playground_page
    GET /api/v1/playground  →  gallery
    GET /api/v1/playground/archetypes  →  archetypes
    GET /api/v1/playground/posture  →  posture
    GET /api/v1/playground/summary  →  summary
    GET /api/v1/playground/runs  →  runs
    GET /api/v1/playground/games/{slug}  →  one_game
    GET /api/v1/playground/games/{slug}/html  →  game_html
    POST /api/v1/playground/games/{slug}/instantiate  →  instantiate
    POST /api/v1/playground/games/{slug}/outcome  →  record_outcome
    POST /api/v1/playground/compose  →  compose
    POST /api/v1/playground/draft  →  draft

**`routes_authoring.py`** (12)
    GET /api/v1/author/methodology  →  methodology_route
    GET /api/v1/author/courses  →  list_courses
    POST /api/v1/author/preview  →  preview
    POST /api/v1/author/courses  →  create_course
    POST /api/v1/author/draft  →  draft_course
    GET /api/v1/author/courses/{course_id}  →  get_course
    GET /api/v1/author/courses/{course_id}/blueprint  →  get_blueprint
    POST /api/v1/author/courses/{course_id}/units  →  add_unit
    POST /api/v1/author/courses/{course_id}/rebuild  →  rebuild
    POST /api/v1/author/courses/{course_id}/illustrate  →  illustrate_course
    GET /api/v1/author/courses/{course_id}/images  →  course_images
    DELETE /api/v1/author/courses/{course_id}  →  delete_course

**`routes_create.py`** (7)
    POST /api/v1/create/preview  →  create_preview
    POST /api/v1/create/course  →  create_course
    POST /api/v1/create/upload  →  create_upload
    GET /api/v1/my-courses  →  my_courses
    GET /api/v1/my-courses/{course_id}  →  my_course
    DELETE /api/v1/my-courses/{course_id}  →  delete_my_course
    POST /api/v1/my-courses/{course_id}/enrol  →  enrol_my_course

**`routes_deck.py`** (19)
    GET /api/v1/deck  →  list_decks
    POST /api/v1/deck  →  create_deck
    GET /api/v1/deck/from-concept/{concept_id}  →  deck_from_concept
    GET /api/v1/deck/{deck_id}  →  get_deck
    PUT /api/v1/deck/{deck_id}  →  replace_deck
    DELETE /api/v1/deck/{deck_id}  →  delete_deck
    POST /api/v1/deck/{deck_id}/slides  →  add_slide
    PATCH /api/v1/deck/{deck_id}/slides/{slide_id}  →  patch_slide
    DELETE /api/v1/deck/{deck_id}/slides/{slide_id}  →  delete_slide
    POST /api/v1/deck/{deck_id}/slides/{slide_id}/move  →  move_slide
    POST /api/v1/deck/{deck_id}/slides/{slide_id}/duplicate  →  duplicate_slide
    POST /api/v1/deck/{deck_id}/elements  →  add_element
    PATCH /api/v1/deck/{deck_id}/elements/{element_id}  →  patch_element
    DELETE /api/v1/deck/{deck_id}/elements/{element_id}  →  delete_element
    GET /api/v1/deck/{deck_id}/export.pptx  →  export_pptx
    POST /api/v1/deck/import  →  import_pptx
    GET /api/v1/deck/{deck_id}/slide/{slide_id}.svg  →  slide_svg
    GET /api/v1/deck/{deck_id}/images  →  deck_images
    POST /api/v1/deck/{deck_id}/images  →  upload_deck_image

**`routes_flash.py`** (10)
    GET /api/v1/flashcards  →  list_cards
    GET /api/v1/flashcards/session  →  session
    GET /api/v1/flashcards/stats  →  stats
    POST /api/v1/flashcards  →  create_card
    PATCH /api/v1/flashcards/{card_id}  →  update_card
    DELETE /api/v1/flashcards/{card_id}  →  delete_card
    POST /api/v1/flashcards/{card_id}/review  →  review_card
    POST /api/v1/flashcards/generate  →  generate
    GET /api/v1/flashcards/export  →  export
    POST /api/v1/flashcards/import  →  import_cards

**`routes_media.py`** (6)
    POST /api/v1/images/paste  →  paste_image
    POST /api/v1/images/fetch  →  fetch_images
    GET /api/v1/images/library  →  image_library
    POST /api/v1/images/for-lesson  →  images_for_lesson
    GET /api/v1/images/{sha}/attribution  →  image_attribution
    DELETE /api/v1/images/{sha}  →  delete_image

**`routes_multimodal.py`** (4)
    GET /api/v1/capabilities  →  capability_matrix
    GET /api/v1/capabilities/{capability_id}  →  capability_detail
    POST /api/v1/capabilities/{capability_id}/grant  →  grant_capability
    DELETE /api/v1/capabilities/{capability_id}/grant  →  revoke_capability

**`routes_procedure.py`** (8)
    GET /api/v1/procedure  →  running
    GET /api/v1/procedure/runs/{run_id}  →  read_run
    POST /api/v1/procedure/runs/{run_id}/advance  →  advance
    POST /api/v1/procedure/runs/{run_id}/abandon  →  abandon
    GET /api/v1/procedure/{concept_id}/deck-cursor  →  read_deck_cursor
    PUT /api/v1/procedure/{concept_id}/deck-cursor  →  write_deck_cursor
    GET /api/v1/procedure/{concept_id}  →  plan
    POST /api/v1/procedure/{concept_id}/start  →  start

**`routes_rewards.py`** (1)
    GET /api/v1/rewards/events  →  reward_events

**`routes_source.py`** (2)
    POST /api/v1/create/search  →  create_search
    POST /api/v1/create/auto  →  create_auto

**`routes_stream.py`** (6)
    GET /app  →  app_page
    POST /api/v1/stream/enable  →  set_stream
    GET /api/v1/stream/status  →  stream_status
    POST /api/v1/stream/window  →  report_window
    GET /api/v1/stream/frame  →  stream_frame
    POST /api/v1/stream/input  →  stream_input

**`routes_supervision.py`** (2)
    GET /api/v1/supervision  →  describe_supervision
    POST /api/v1/supervision/assess  →  assess

**`routes_ta.py`** (2)
    POST /api/v1/ta/sweep  →  sweep
    POST /api/v1/ta/prepare  →  prepare

**`web_routes.py`** (10)
    GET /  →  workbench_index
    GET /web/{asset_path:path}  →  workbench_asset
    GET /api/v1/sims  →  list_sims
    POST /api/v1/sims  →  save_sim
    GET /api/v1/sims/{sim_id}  →  sim_meta
    GET /api/v1/role  →  acting_role
    POST /api/v1/sims/{sim_id}/frame-token  →  sim_frame_token
    GET /api/v1/sims/{sim_id}/raw  →  sim_raw
    GET /api/v1/sims/{sim_id}/download/{name}  →  sim_download
    POST /api/v1/sims/{sim_id}/requests  →  file_change_request

_101 endpoints across 14 modules._

## Agent tools (the teacher's toolbox)

  attach_lesson_image, author_course, board_apply, board_place_media, board_read, browser_snapshot, build_figure, build_presentation, check_on_task, check_simulation, check_understanding, compose_content, course_images, deck_control, describe_methodology, draft_course, edit_simulation, extend_course, fetch_material_text, fetch_page_text, find_game, find_image, find_simulation, find_video, generate_slides, illustrate_course, image_generate, image_search, inspect_prerequisites, list_authored_courses, list_workspace, look_at_image, prepare_case_study, read_concept, read_course_blueprint, read_learner_evidence, read_workspace_file, recall_learner_memory, run_in_workspace, search_concepts, search_material, search_videos, text_to_speech, web_search, whiteboard_apply, whiteboard_place_image, whiteboard_read, whiteboard_write, wikipedia_summary, write_simulation, write_workspace_file

_51 tools._

## Database tables

  users, schema_version, training_consent_ledger, tokens, refresh_tokens, auth_tokens, rate_buckets, server_secrets, learning_states, assessments, receipts, attempts, messages, projects, telemetry_events, memory_notes, harness_runs, flashcards, cohorts, waitlist_signups, beta_invites, invite_redemptions, feedback, feedback_events, experiments, experiment_assignments, experiment_exposures, usage_ledger, usage_daily_rollup, quota_policies, quota_counters, user_preferences, teacher_style_profiles, consent_ledger, admin_audit_log, playground_runs, procedure_runs

_37 tables. `db.py` is the schema; migrations live beside it._

## Capability matrix

  images, video, audio_tts, web_search, browser_snapshot, course_creation, vision_understanding, vla_actions, on_task_monitoring, simulations, whiteboard_rich, flashcards_auto, pptx_export

_Every capability degrades to a declared fallback with a reason. Never let one raise._
