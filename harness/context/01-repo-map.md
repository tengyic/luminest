# 01 — Repository map

Every source file, its stated purpose, and its public surface. Read this to
decide *which* file to open; do not open a file to learn what it is for.

Generated from the tree. Regenerate with `python3 scripts/context_pack.py`.

# Backend (`backend/app/`)

## application root — 48 files

**`accounts.py`** — 378 ln — Account lifecycle, demand capture and metering for a hosted Beta.
    normalize_email(), valid_email(), Mailer, waitlist_position(), waitlist_json(), join_waitlist(), confirm_waitlist(), find_invite(), invite_is_redeemable(), redeem_invite(), +9 more
**`adaptation.py`** — 126 ln — Explicit domain gate: EdNet research inference is never a trained math model.
    predict(), train_on_opt_in_csv()
**`capabilities.py`** — 801 ln — The capability matrix: every multimodal thing Luminfest can offer, and who gets it.
    Capability, by_id(), all_capabilities(), provider_ready(), entitlements_of(), active_entitlement(), operator_grants(), operator_granted(), paid_plan(), ensure_paid_quota(), +7 more
**`config.py`** — 373 ln — (no docstring)
    legal_dir(), load_dotenv(), Settings
**`course_builder.py`** — 1923 ln — Build a course from the learner's own material, and make it studyable.
    refusal_rules(), Refusal, IntakeRefused, BuildRefused, Intake, word_count(), paragraph_count(), intake_text(), intake_bytes(), intake_url(), +19 more
**`courses.py`** — 371 ln — Course registry: many subjects, one harness.
    Course, UnknownCourse, course(), enrolled_for(), graph_for(), stats_for(), catalogue(), total_concepts(), course_for_node(), graph_for_node(), +1 more
**`curriculum.py`** — 711 ln — Original worked examples and questions; source books are credited, not copied.
    parameter(), add(), validate_curriculum(), graph_states_in(), graph_states(), simulation_node(), graph_summary(), validate_graph(), course_concepts(), course_questions(), +1 more
**`curriculum_route.py`** — 239 ln — One routing layer for every course's curriculum.
    CourseRoute, concept_payload(), references_for(), route(), route_for_user()
**`db.py`** — 903 ln — (no docstring)
    now_ts(), uid(), iso(), Base, User, SchemaVersion, TrainingConsent, Token, RefreshToken, AuthToken, +32 more
**`deck.py`** — 1512 ln — The deck document and the real .pptx engine behind the slide editor.
    DeckError, DeckUnavailable, normalise_color(), new_deck(), new_slide(), new_text_element(), normalise_document(), validate_element(), validate_document(), require_valid(), +26 more
**`exam_guard.py`** — 45 ln — Whether an account is mid-exam, and what that forbids.
    active(), block()
**`experiments.py`** — 192 ln — A/B experiment wiring for the learning-science features.
    bucket(), ensure_experiment(), snapshot(), log_exposure()
**`feature_routers.py`** — 44 ln — The feature-router modules ``main.create_app`` mounts, named in exactly one place.
**`figures.py`** — 181 ln — Subject-aware figures.
    concept_map(), figure_for()
**`flashcards.py`** — 618 ln — Flashcard decks: grounded auto-generation, FSRS-6 scheduling, interleaved study.
    resolve_concept(), block_source(), question_source(), source_exists(), normalise(), front_key(), generate_candidates(), generate_for_user(), preview_for_user(), apply_grade(), +7 more
**`generated_curriculum.py`** — 507 ln — Generated lesson and question layer for courses with no authored content.
    question_id(), materialise(), structural_items(), materialise_graph(), register()
**`knowledge_graph.py`** — 598 ln — Scalable concept graph: nodes, prerequisite edges, taxonomy, validation and analytics.
    slug(), ConceptNode, Issue, Taxonomy, KnowledgeGraph, load_pack(), combine()
**`kst.py`** — 307 ln — Knowledge Space Theory (KST) as the assessment layer.
    TooManyStates, KnowledgeSpace, from_knowledge_graph(), default_space()
**`learning.py`** — 307 ln — (no docstring)
    adapter(), predict(), update(), propagate_implicit_credit(), logit(), item_probability(), diagnose(), recommend(), model_status()
**`learning_science.py`** — 293 ln — Learning-science scheduling and measurement.
    concept_family(), build_practice_group(), brier_decomposition(), next_transfer()
**`legal_guard.py`** — 65 ln — Legal shippability guard (audit finding L-1).
    unfilled_placeholders(), assert_shippable()
**`main.py`** — 4064 ln — (no docstring)
    user_json(), enrolled_course(), course_graph(), my_concepts(), my_questions(), my_graph_states(), my_concepts_by_node(), resolve_course_node(), concept_meta(), concept_title(), +21 more
**`memory.py`** — 375 ln — The DSR memory model: Difficulty, Stability, Retrievability, per FSRS-6.
    enabled(), retrievability(), recall_probability(), next_interval_days(), due_time(), new_state(), review(), apply_implicit_credit()
**`planner.py`** — 336 ln — Goal-driven study planning.
    pacing(), is_secure(), classify(), coverage_gaps(), order_concepts(), milestones(), plan()
**`playground_routes.py`** — 429 ln — HTTP surface for the simulator playground.
    playground_page(), GuidedCycle, Outcome, ComposeRequest, DraftRequest, gallery(), archetypes(), posture(), summary(), runs(), +6 more
**`procedure_service.py`** — 839 ln — Resolve the real assets a lesson can use, compile the procedure, and persist the run.
    UnknownConcept, assets_for(), recent_kinds(), compile_for(), current_run(), deck_section_count(), deck_cursor(), set_deck_cursor(), start_run(), advance_run(), +4 more
**`resources.py`** — 70 ln — Where the app's top-level resource directories live, frozen or not.
    resource_root(), resource_dir()
**`routes_authoring.py`** — 428 ln — HTTP surface for the content foundry.
    BlueprintBody, DraftBody, UnitBody, IllustrateBody, methodology_route(), list_courses(), preview(), create_course(), draft_course(), get_course(), +6 more
**`routes_create.py`** — 384 ln — HTTP surface for building a course out of the learner's own material.
    SourceInput, UploadInput, CreateInput, account(), create_preview(), create_course(), create_upload(), my_courses(), my_course(), delete_my_course(), +1 more
**`routes_deck.py`** — 439 ln — HTTP surface for the slide editor: an editable deck document and a real .pptx bridge.
    list_decks(), create_deck(), deck_from_concept(), get_deck(), replace_deck(), delete_deck(), add_slide(), patch_slide(), delete_slide(), move_slide(), +9 more
**`routes_flash.py`** — 348 ln — HTTP surface for flashcard decks: ``/api/v1/flashcards``.
    authenticated(), CardInput, CardPatch, GenerateInput, ReviewInput, ImportInput, list_cards(), session(), stats(), create_card(), +6 more
**`routes_media.py`** — 235 ln — HTTP surface for image *acquisition*: fetch, library, lesson batch, attribution, delete.
    FetchInput, LessonInput, PasteImageInput, paste_image(), fetch_images(), image_library(), images_for_lesson(), image_attribution(), delete_image()
**`routes_multimodal.py`** — 214 ln — HTTP surface for the capability matrix: what this instance offers, and what you get.
    GrantInput, capability_matrix(), capability_detail(), grant_capability(), revoke_capability()
**`routes_procedure.py`** — 338 ln — HTTP surface for the compiled lesson procedure: ``/api/v1/procedure``.
    authenticated(), AdvanceInput, running(), read_run(), advance(), abandon(), DeckCursorInput, read_deck_cursor(), write_deck_cursor(), plan(), +1 more
**`routes_rewards.py`** — 111 ln — HTTP surface for the positive record: ``/api/v1/rewards``.
    reward_events()
**`routes_source.py`** — 201 ln — HTTP surface for *finding* a source and turning it into a course in one motion.
    SearchInput, AutoInput, create_search(), create_auto()
**`routes_stream.py`** — 187 ln — HTTP surface for presenting the app's own window in a browser: ``/api/v1/stream``.
    app_page(), WindowReport, InputEvent, StreamSwitch, set_stream(), stream_status(), report_window(), stream_frame(), stream_input()
**`routes_supervision.py`** — 195 ln — HTTP surface for the session supervisor: ``/api/v1/supervision``.
    authenticated(), AssessInput, describe_supervision(), assess()
**`routes_ta.py`** — 235 ln — HTTP surface for the TA's interval check: ``/api/v1/ta/sweep``.
    SweepInput, sweep(), PrepareInput, prepare()
**`schemas.py`** — 338 ln — (no docstring)
    Input, Login, Register, WaitlistJoin, TokenOnly, ForgotPassword, ResetPassword, RefreshRequest, InviteRedeem, InviteCreate, +24 more
**`security.py`** — 183 ln — (no docstring)
    digest(), password_ok(), issue_token(), new_secret(), issue_session(), rotate_refresh(), revoke_session(), revoke_all_sessions(), issue_auth_token(), consume_auth_token(), +4 more
**`simulation_map.py`** — 427 ln — Concept to simulation mapping, with the rights position and the evidentiary limit.
    pack(), providers(), mappings(), uncovered(), verify_slug(), verify_all(), match(), for_concept(), for_course(), coverage(), +1 more
**`source_extension.py`** — 792 ln — Find a source, take one the learner supplied, and turn it into a course.
    SourceRefused, Candidate, SearchResult, find(), forget(), search_enabled(), search(), normalise_wiki_text(), policy_for(), intake_for(), +5 more
**`teacher_clone.py`** — 129 ln — Consent-gated teacher transcript analysis for a personalized tutor.
    normalize_profile(), offline_profile(), tutor_style(), analyze()
**`training.py`** — 117 ln — Trusted server-side consent ledger and minimized offline worker export.
    set_consent(), current_grant(), eligible_attempts(), training_status(), pseudonym(), canonical(), export_training(), verify_export()
**`tutor.py`** — 411 ln — (no docstring)
    respond()
**`user_scope.py`** — 218 ln — User-scope isolation guard: the multi-tenant safety baseline.
    UnsafeQueryError, unscoped, unscoped_events(), clear_unscoped_events(), install(), installed()
**`web_routes.py`** — 483 ln — Static web workbench + serving layer for the simulation artifact store.
    inject_agent_script(), principal(), server_role(), issue_frame_token(), verify_frame_token(), seed_sims(), title_from_html(), workbench_index(), workbench_asset(), list_sims(), +7 more

## harness — 43 files

**`__init__.py`** — 102 ln — The harness: memory, toolbox, sandbox, generation and the agentic loop.
    HarnessContext, context_for(), status(), plan_for(), run_move()
**`agent_loop.py`** — 319 ln — The tool-driving agent loop: the "coding harness" behaviour.
    tool_label(), tools_payload(), run_agent()
**`attention.py`** — 312 ln — Whether the learner is working on the task: an evidence reading, not surveillance.
    available(), status(), telemetry(), assess(), describe()
**`board.py`** — 914 ln — Board: the interactive canvas the teacher, the learner and the tutor share.
    between(), top_z(), create(), load(), load_owned(), latest_version(), delete(), list_for_owner(), apply_mutations(), update_meta(), +8 more
**`browser.py`** — 110 ln — Headless-browser snapshot for the tutor's tool loop (teacher-only, gated).
    snapshots_dir(), purge_expired(), snapshot()
**`classroom.py`** — 675 ln — The classroom decision engine: one polling tick in, one teaching decision out.
    Config, Snapshot, Decision, evaluate(), describe()
**`conduct.py`** — 162 ln — The teaching-conduct rules, as one citable block of prose.
    lesson_format()
**`creation_gate.py`** — 250 ln — The creation boundary: who may change a teaching artifact, and how.
    evaluate(), load_approvals(), save_approval(), new_approval_id()
**`ddg_provider.py`** — 46 ln — Resolve a DuckDuckGo search provider, preferring the maintained package.
    load(), installed()
**`diagram.py`** — 765 ln — Safe, line-only whiteboard diagram generation from the configured DeepSeek VLM.
    DiagramError, fourier_smooth(), nodes_from_proposal(), sample_curve(), list_templates(), template_preview(), vectorize_image(), generate()
**`econ_figures.py`** — 1058 ln — Deterministic diagrams for economics concepts.
    classify(), render(), for_concept(), caption_with_parameters()
**`game_search.py`** — 65 ln — Curated math-game / interactive-activity search over an audited, operator-edited pack.
    pack_games(), for_query()
**`generate.py`** — 924 ln — Grounded generation of multimodal teaching content.
    redact_textbook_quotes(), Artifact, Context, retrieve(), asset_block(), compose(), catalogue()
**`guided_sim.py`** — 273 ln — The guided-simulation cycle: predict, manipulate, explain - and the contract for it.
    cycle(), evaluate_prediction(), validate_outcome(), outcome_payload(), explanation_substance(), credit(), describe()
**`leveling.py`** — 163 ln — Map the internal IRT ability theta (logits) onto labels a learner can read.
    is_language_subject(), cefr_from_theta(), grade_from_theta(), level_summary(), learner_level(), describe()
**`loop.py`** — 683 ln — The agentic loop: what the harness does next, and why.
    Candidate, Decision, gather(), recent_decisions(), effectiveness(), score_moves(), choose(), plan(), record_outcome(), explain(), +2 more
**`media.py`** — 2007 ln — Internet images, licence-gated, downloaded, cached and attributed.
    user_agent(), contact_configured(), normalise_mime(), Candidate, ImageAsset, enabled(), cache_root(), manifest_path(), shipped_pack(), shipped_for(), +32 more
**`memory.py`** — 200 ln — Learner memory: what the harness knows, how it decays, and how it is cited.
    Note, remember(), recall(), digest(), forget(), wipe(), summarise(), age_factor(), half_life_days()
**`modality.py`** — 179 ln — Modality routing: which representation to show this learner, and why.
    route(), describe()
**`presentation.py`** — 622 ln — Narrated slide decks, assembled the way a slide-video product assembles them.
    Segment, estimate_seconds(), build_segments(), timeline(), vtt(), render_html(), compose()
**`prompt.py`** — 243 ln — The harness system prompt, assembled rather than hard-coded.
    role_for(), build(), payload()
**`provider.py`** — 267 ln — A single, small adapter to the configured language model.
    meter_usage(), available(), label(), chat(), chat_tools(), chat_json(), learner_block()
**`psychometrics.py`** — 422 ln — Item Response Theory and computerised adaptive testing, kept deliberately small.
    probability(), information(), standard_error(), ability_posterior(), estimate_ability(), theta_to_success(), select_item(), rasch_item(), calibrate_bank(), describe()
**`render.py`** — 270 ln — Vector rendering for generated figures.
    Frame, figure_svg(), deck_svg()
**`rewards.py`** — 189 ln — Milestones as *things the client can animate*.
    events(), describe()
**`sandbox.py`** — 504 ln — A workspace and a sandbox for generated content and learner code.
    SandboxRefused, StaticGuardError, guard(), Workspace, workspace_for(), describe()
**`screen.py`** — 422 ln — Put the running app's own window in a browser tab.
    StreamRefused, region_path(), save_region(), load_region(), console_state(), capture(), send_input(), status()
**`sims_check.py`** — 125 ln — Does a stored simulation actually run, or does it merely parse?
    available(), check()
**`sims_store.py`** — 352 ln — Storage and validation for self-contained teaching artifacts (simulations, decks).
    store_root(), manifest_path(), raw_url(), load(), list_artifacts(), validate_html(), diff_summary(), create_artifact(), save_version(), read_version(), +2 more
**`socratic.py`** — 149 ln — The Socratic dialogue ladder: which move the tutor makes on the next turn.
    step(), may_reveal_answer(), state_from_evidence(), describe()
**`speech.py`** — 513 ln — Speaking the tutor's own words, off the request path.
    audio_root(), spoken_text(), utterances(), state(), file_for(), enabled(), plan(), request(), request_sequence(), render(), +3 more
**`ta.py`** — 126 ln — TA — teacher's assistant subagent.
    DispatchFull, configure(), dispatch(), status(), results()
**`telemetry.py`** — 159 ln — What an interaction may say.
    validate(), summarise(), describe()
**`toolbox.py`** — 1411 ln — The harness toolbox: the complete set of actions the agentic loop may take.
    ToolSpec, ToolResult, ToolRefused, ToolContext, graph_for(), learner_states(), search_concepts(), read_concept(), inspect_prerequisites(), recall_learner_memory(), +24 more
**`tools_board.py`** — 232 ln — Board tools: the tutor's hands on the interactive canvas.
    board_read(), board_apply(), board_write(), board_place_media()
**`tools_creation.py`** — 1174 ln — Creation and multimodal generation tools, behind the creation boundary.
    extract_html(), looks_truncated(), write_simulation(), edit_simulation(), check_simulation(), generate_slides(), text_to_speech(), image_search(), web_search(), fetch_page_text(), +4 more
**`tools_vision.py`** — 103 ln — The two vision tools: looking at a picture, and reading whether work is on task.
    look_at_image(), check_on_task()
**`tools_whiteboard.py`** — 225 ln — Whiteboard tools: the tutor's hands on the shared Stage surface.
    whiteboard_read(), whiteboard_apply(), whiteboard_write(), whiteboard_place_image()
**`video.py`** — 560 ln — Video lessons: curated, verified, embedded, never copied.
    ExtractionRefused, assert_extraction_allowed(), allowlist_path(), revocation_path(), load_allowlist(), save_allowlist(), curate(), load_revocations(), revoke(), VideoRef, +5 more
**`video_search.py`** — 512 ln — Video search for teachers: find candidates, verify embeddability, never auto-trust.
    search_videos(), relevance(), trusted_channel(), closer_to_another(), curate_for_concept()
**`vla.py`** — 396 ln — Vision-language-action: the tutor can look, then act, then look again.
    ModelCard, model_card(), card_for(), vision_status(), vision_ready(), actions_ready(), describe(), ImageRefused, sniff_mime(), to_data_url(), +8 more
**`voice.py`** — 523 ln — Text to speech through a local VoiceStudio backend.
    VoiceError, base_url(), model(), served_models(), resolve_model(), default_voice(), timeout(), speed_from_rate(), resolve_voice(), default_instruct(), +3 more
**`whiteboard.py`** — 496 ln — Legacy Stage whiteboard — DEPRECATED. This module is now a *view* over board.py.
    concept_node_id(), clean_op(), op_to_node(), node_to_op(), legacy_view(), digest(), load(), load_or_create(), apply_ops(), raise_interrupt(), +4 more

## harness/authoring — 9 files

**`__init__.py`** — 97 ln — The content foundry: the harness authors its own courses.
**`audit.py`** — 476 ln — The audit: the reason a generated course is allowed to exist.
    Finding, Audit, audit(), require(), CourseRefused
**`blueprint.py`** — 732 ln — A course blueprint: the document a course is designed as, before it is materialised.
    BlueprintError, Problem, ConceptPlan, UnitPlan, CoursePlan, course_id(), concept_id(), parse(), frame_from_entries(), is_fatal(), +1 more
**`draft.py`** — 737 ln — Drafting a blueprint with the harness's own model provider.
    skeleton_tokens(), unit_tokens(), DraftUnavailable, DraftRefused, Draft, title_key(), expand(), refused_prose(), repair(), draft()
**`illustrate.py`** — 301 ln — Real photographs in an authored textbook.
    Illustration, illustrate(), attach(), coverage()
**`methodology.py`** — 341 ln — The authoring methodology: how this harness designs a course, as inspectable data.
    BlockSpec, Shape, Load, Assessment, AuthoringProfile, default_profile(), compact_profile(), seminar_profile(), profile(), apply_overrides(), +1 more
**`registry.py`** — 559 ln — Making an authored course real, and keeping it real across a restart.
    Record, root(), store(), store_overlay(), delete(), load_all(), get(), listing(), withheld(), publish(), +3 more
**`synthesize.py`** — 770 ln — Materialise a blueprint into a course the rest of the harness already understands.
    AuthoredCourse, build_graph(), build_course(), build_blocks(), build_questions(), build(), build_overlay(), build_from_document()
**`tools.py`** — 341 ln — Foundry tools: authoring reachable from inside a teaching turn.
    author_course(), draft_course(), illustrate_course(), attach_lesson_image(), course_images(), list_authored_courses(), read_course_blueprint(), extend_course(), describe_methodology()

## harness/playground — 13 files

**`__init__.py`** — 60 ln — The simulator playground: a template system for interactive learning games.
**`archetypes.py`** — 346 ln — The archetype contract: what a game template *is*, and how content is checked.
    Field, Archetype, register(), register_all(), all_archetypes(), get(), by_subject(), validate_spec(), render(), problems_for_page()
**`archetypes_core.py`** — 340 ln — ``curve_shift`` - the reference archetype, and the shape every other one copies.
**`archetypes_economics.py`** — 1512 ln — Economics archetypes for the simulator playground.
**`archetypes_general.py`** — 1295 ln — ``order_sequence``, ``matching_pairs`` and ``label_diagram`` - the general-purpose interactions.
**`archetypes_math_a.py`** — 1505 ln — Mathematics archetypes, set A: the linear-functions and equation family.
**`archetypes_math_b.py`** — 1353 ln — Mathematics and computer-science archetypes: area models, probability, patterns, and stepping through an algorithm.
**`archetypes_science_a.py`** — 1603 ln — ``archetypes_science_a`` - physics and chemistry simulators for the playground.
**`archetypes_science_b.py`** — 1740 ln — Physics, biology and earth-science archetypes for the simulator playground.
**`catalogue.py`** — 235 ln — The bundled game catalogue: which games exist, and which had to be withheld.
    refresh(), all_games(), withheld(), get_game(), by_subject(), by_course(), by_archetype(), subjects(), courses(), catalogue(), +1 more
**`evidence.py`** — 256 ln — Turning a completed game into an observation the harness can actually use.
    resolve_concept(), record(), recent(), summary(), describe()
**`pipeline.py`** — 336 ln — The generation pipeline: content spec -> validated, stored, playable game.
    slugify(), spec_hash(), render_game(), page_args(), instantiate(), compose(), draft(), describe()
**`runtime.py`** — 630 ln — The shared runtime every playground game is built on.
    eyebrow_for(), render_page()

## harness/teaching — 12 files

**`__init__.py`** — 86 ln — The teaching core: a configuration-driven teacher for one learner.
**`assets.py`** — 309 ln — Asset review: is this artefact actually about the concept it is attached to?
    concept_terms(), review_simulation(), review_video(), review_image(), sweep(), plan_repair(), describe()
**`config.py`** — 540 ln — The teacher profile: the whole pedagogy, as inspectable data.
    MoveSpec, RetrievalConfig, DifficultyConfig, WrapConfig, CompletionConfig, SequencingConfig, PersonaConfig, ModalityConfig, ProcedureConfig, LearnedPreferenceConfig, +2 more
**`evidence.py`** — 297 ln — What the teacher knows about the learner and the concept, as one record.
    ConceptFacts, concept_type_for(), concept_facts(), LearnerEvidence, fsrs_recall(), parent_states_for(), prerequisite_debt(), build_evidence()
**`modalities.py`** — 410 ln — Multimodal move selection: *how* a concept is taught, grounded in evidence.
    ToolCall, ModalityChoice, choose_modality()
**`motivation.py`** — 166 ln — The positive half of the loop: streaks, milestones, badges, the certificate.
    streak(), quiz_streak(), node_milestone(), badges(), certificate()
**`policy.py`** — 416 ln — The move policy: which teaching move, chosen from evidence and configuration.
    MoveScore, score_moves(), select_move()
**`procedure.py`** — 1042 ln — The lesson procedure: the run of show, compiled from evidence and available assets.
    ProcedureAssets, ProcedureBlock, CourseProcedure, compile_procedure(), procedure_hash(), render_procedure_block()
**`render.py`** — 219 ln — The prompt sections, *rendered from* the teacher profile.
    render_move_section(), render_persona_section(), render_retrieval_section(), render_modalities_section(), render_profile_sections(), render_plan_block()
**`retrieval.py`** — 163 ln — The retrieval schedule: which concepts are due, in which order.
    ReviewItem, RetrievalPlan, is_due(), due_concepts(), plan_retrieval()
**`session.py`** — 284 ln — The session plan: the teaching loop, assembled and executable.
    TeachingStep, TeachingPlan, plan_session()
**`supervision.py`** — 361 ln — Whether to interrupt at all: the session supervisor.
    progress_reading(), participation(), difficulty(), provenance(), assess(), describe()

## ingest — 4 files

**`__init__.py`** — 16 ln — Concept ingestion: fetch, classify and validate curriculum structure.
**`classify.py`** — 475 ln — Classification engine: raw source records -> a validated concept graph.
    tokens(), stem(), ClassificationRules, ClassificationReport, Classifier, classify()
**`pipeline.py`** — 275 ln — Command-line orchestration for curriculum ingestion.
    cmd_policy(), cmd_build(), cmd_enrich(), cmd_verify(), cmd_textbook(), main()
**`policy.py`** — 1111 ln — Licence policy for curriculum ingestion.
    LicenceClass, SourcePolicy, IngestionRefused, assert_ingestible(), AssetRefused, classify_code(), classify_licence(), reset_override_cache(), load_overrides(), override_for(), +12 more

## ingest/sources — 6 files

**`__init__.py`** — 10 ln — Ingestion adapters. Every adapter declares a licence policy and is gated on it.
**`base.py`** — 75 ln — Shared vocabulary for ingestion sources.
    SourceError, RawNode, Source, StaticSource
**`bundled.py`** — 32 ln — Bundled course outlines that ship with the harness.
    available(), bundled_outline()
**`openstax.py`** — 425 ln — Grounded OpenStax textbook sections: fetched from the publisher, licence-gated, stored with provenance, quoted with attribution.
    store_path(), book_policy(), fetch_book_meta(), fetch_toc(), fetch_section(), load_sections(), ingest_section(), grounding(), describe()
**`scope_sequence.py`** — 136 ln — Ingest an operator-supplied course outline.
    ScopeSequenceSource, course_metadata()
**`wikidata.py`** — 218 ln — Wikidata ingestion source (CC0).
    WikidataRoot, WikidataSource

## mathkit — 6 files

**`__init__.py`** — 25 ln — A symbolic mathematics engine for generated interactive content.
**`calculus.py`** — 1687 ln — Figures for calculus and the later Algebra 2 topics.
    conic_figure(), hyperbola_figure(), rational_figure(), polynomial_figure(), radical_figure(), no_figure()
**`expression.py`** — 646 ln — A small, safe symbolic expression engine.
    MathSyntaxError, tokenize(), parse(), depth(), evaluate(), simplify(), derivative(), substitute(), to_string(), to_latex(), +1 more
**`polynomial.py`** — 288 ln — Polynomial normalisation, exact roots and factoring.
    constant(), variable(), from_ast(), add(), sub(), multiply(), scale(), derivative(), degree(), leading(), +13 more
**`simulate.py`** — 466 ln — Turn a simulation spec into a complete, renderable payload.
    Parameter, Part, Mark, SimulationSpec, sample(), build()
**`templates.py`** — 1273 ln — Generate a simulation spec for any concept, from its own classification.
    template_for(), available_templates()

_141 files._

# Native SwiftUI (`native/Sources/`)

## LearningHarness — 39 files

**`AppResources.swift`** — 51 ln — Where the bundled artwork actually lives.
    enum:AppResources
**`BackendLauncher.swift`** — 270 ln — (no header comment)
**`Board.swift`** — 989 ln — (no header comment)
    struct:BoardNode, enum:BoardKind, struct:BoardSnapshot, enum:BoardRenderer, extension:CGRect, extension:Color
**`BoardEditor.swift`** — 2387 ln — (no header comment)
    enum:BoardEraserMode, struct:BoardViewport, extension:Comparable, struct:BoardEventBridge, struct:BoardEditor, extension:BoardEditor, extension:BoardEditor, extension:BoardEditor, extension:BoardEditor, struct:TextSheet, +2 more
**`BoardKit.swift`** — 789 ln — (no header comment)
    enum:BoardTool, struct:BoardSelection, enum:ResizeHandle, struct:SnapGuide, struct:SnapOutcome, enum:SnapEngine, enum:AlignCommand, enum:DistributeCommand, struct:BoardState, struct:BoardHistory, +2 more
**`BoardMenu.swift`** — 144 ln — (no header comment)
    struct:BoardSheet
**`CanvasView.swift`** — 729 ln — (no header comment)
    enum:CanvasTool, struct:CanvasView, struct:EventBridge, extension:BoardNode, struct:NodeView, struct:ArrowShape, enum:CryptoSHA256
**`CelebrationOverlay.swift`** — 266 ln — The reward surface: one event at a time, at the weight of ceremony the backend asked for.
    struct:RewardOverlay, struct:CelebrationParticles, struct:SeededGenerator
**`ClickTelemetry.swift`** — 194 ln — App-wide interaction telemetry: what was touched, in batches, with no content.
**`Core.swift`** — 1385 ln — (no header comment)
    struct:AppFailure, struct:ServerEvent, struct:ChatActivity, enum:SecureSession, enum:Page
**`CourseSetup.swift`** — 663 ln — First-run setup: choose a subject, say what you are aiming for, choose a daily pace.
    struct:CourseSetupView, struct:CourseOptionRow, struct:FlowRow, struct:PlanCard, struct:CourseSwitcher
**`DeckEditor.swift`** — 1468 ln — (no header comment)
    struct:DeckStyle, struct:DeckRun, struct:DeckParagraph, struct:DeckTextBody, struct:DeckCrop, struct:DeckImageRef, struct:DeckTableBody, struct:DeckElement, struct:DeckSlide, struct:DeckTheme, +2 more
**`Design.swift`** — 962 ln — A Morandi accent pair: a soft surface tint used for fills and a deep ink tone used
    extension:Color, struct:Accent, enum:Palette, struct:LuminfestButtonStyle, struct:LuminfestButtonBody, struct:Card, struct:Eyebrow, struct:SectionHeading, struct:Tag, struct:EmptyState, +2 more
**`Flashcards.swift`** — 675 ln — (no header comment)
    struct:Flashcard, enum:FlashTab, struct:FlashcardsView, struct:FlashcardEditor, struct:GenerateSheet
**`GeneratedSimulation.swift`** — 438 ln — A live figure generated by the backend's symbolic engine.
    struct:SimulationLab, struct:GeneratedFigure, struct:FigureBounds, extension:JSON
**`HarnessPlan.swift`** — 120 ln — Mirror of `Decision.to_dict()` (loop.py). Built from the app's dynamic JSON value,
    struct:HarnessDecision, struct:HarnessPlanState, struct:HarnessPlanCard
**`LessonProcedure.swift`** — 934 ln — (no header comment)
    struct:ProcedureStep, struct:DeckSection, struct:DeckImage, enum:BlockPresentation, struct:LessonProcedureState, struct:LessonProcedureCard, struct:LessonBlockSheet, struct:DeckImageView
**`LumiCompanion.swift`** — 419 ln — (no header comment)
    enum:LumiMood, enum:LumiSprite, enum:LumiArt, struct:LumiStep, enum:LumiAction, struct:LumiSpriteView, struct:LumiCompanionView, struct:LumiSidebarSlot, struct:LumiSetupGuide
**`LuminfestApp.swift`** — 680 ln — Opt-in presentation mode for screenshots meant for people outside the harness.
    enum:CapturePresentation, struct:RootView, struct:OnboardingView, struct:FormFieldContainer, struct:AppShell, struct:SidebarItemButton, struct:SidebarSettingsButton, struct:HeaderRefreshButton
**`MarkdownBlocks.swift`** — 209 ln — One rendered unit of a tutor reply.
    enum:MarkdownBlock, enum:MarkdownBlocks
**`MarkdownText.swift`** — 154 ln — A tutor reply, drawn as blocks instead of as one run of characters.
    struct:MarkdownText, struct:MarkdownBlockView
**`MediaTools.swift`** — 491 ln — (no header comment)
    struct:SafeLessonLink, extension:LessonSpeech, struct:LocalPDFView, struct:LocalMediaChooser, struct:LessonPresentation, enum:MediaEmbed, struct:EmbeddedLessonWebView, struct:NarratedDeckView, struct:TinyDotLabelStyle, struct:DeckPhotograph, +2 more
**`NativeQA.swift`** — 705 ln — In-process QA: every workflow change goes through the application's real accessibility
**`PerfectFreehand.swift`** — 239 ln — (no header comment)
    enum:PerfectFreehand, enum:RDP
**`Playground.swift`** — 286 ln — (no header comment)
    struct:PlaygroundWebView, struct:PlaygroundSheet, struct:PlaygroundCard
**`ProjectsInsightsSettings.swift`** — 305 ln — (no header comment)
    struct:ProjectsView, struct:ProjectEditor, struct:InsightsView, struct:SettingsPage
**`QuestionView.swift`** — 120 ln — (no header comment)
    struct:QuestionView
**`RealtimeKey.swift`** — 57 ln — The OpenAI Realtime API key, held in the macOS Keychain so it never lives in
    enum:RealtimeKey
**`RewardCenter.swift`** — 119 ln — One reward event, exactly as the backend sent it.
    struct:RewardEvent
**`SessionVault.swift`** — 112 ln — Keychain-backed storage for *both* halves of a session (audit finding E-1).
    enum:SessionVault
**`SimulationDetail.swift`** — 189 ln — (no header comment)
    enum:SimulationMath, struct:SimulationDetail
**`SoundBank.swift`** — 245 ln — The five sounds a celebration can make.
    enum:SoundVoice, enum:SoundSynth
**`Stage.swift`** — 779 ln — State for the big central Stage. One stage per concept.
    struct:SpeakerButton, struct:StageView, struct:BoardPane, extension:StageStore, struct:DeckPane, struct:WebPane, struct:StageWebView, struct:AssetsPane, struct:TAFeed
**`Studio.swift`** — 922 ln — (no header comment)
    struct:SimulationParameter, enum:PlotMath, struct:StudioView, struct:LevelCard, struct:ConceptPicker, struct:LessonBlock, struct:CachedPhotograph, struct:SimulationView, struct:NativePlot, struct:NativeMediaView, +2 more
**`TeacherProfile.swift`** — 192 ln — Transcript-based teacher style analysis. The transcript stays in this view's local
    struct:TeacherProfileSheet
**`TodayKnowledge.swift`** — 774 ln — (no header comment)
    struct:TodayView, struct:MetricCard, struct:KnowledgeView, struct:GraphOverview, struct:UnitBrowser, struct:ConceptInspector, struct:ReviewView
**`Voice.swift`** — 458 ln — Device voice I/O for the Stage: on-device ASR (SFSpeechRecognizer) and TTS
    extension:VoiceIO, struct:VoiceActivityDetector, extension:ClipPlayer
**`VoiceRealtime.swift`** — 331 ln — Real-time, duplex voice with the OpenAI Realtime API (`/v1/realtime`).
**`WindowStream.swift`** — 102 ln — Tells the backend where this app's window is, so `/app` can present it in a browser tab.

_39 files._
