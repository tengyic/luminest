# 03 — Behavioural spec (test names)

1518 test functions. The names are the specification: they state what the
system promises, in the same words the promises were written in. Read the
relevant block before changing a module; a change that contradicts a name
here is either a bug or a deliberate re-specification.

**`test_accounts.py`** (16)
    test_waitlist_is_idempotent_and_holds_position
    test_waitlist_confirmation_requires_the_emailed_token
    test_invite_gate_admits_only_the_addressed_email
    test_invite_required_when_configured
    test_invite_carries_a_cohort
    test_admin_surface_rejects_a_learner
    test_refresh_rotates_and_reuse_is_treated_as_theft
    test_sessions_can_be_listed_and_revoked_per_device
    test_a_revoked_access_token_stops_working_immediately
    test_email_verification_flow
    test_password_reset_is_single_use_and_ends_other_sessions
    test_forgot_password_does_not_reveal_whether_an_account_exists
    test_usage_reports_observation_not_enforcement
    test_preferences_round_trip
    test_feedback_works_signed_out_and_is_idempotent_when_signed_in
    test_legal_documents_are_served

**`test_agent_loop.py`** (27)
    test_chat_tools_parses_calls_usage_and_reasoning
    test_chat_tools_keeps_unparseable_arguments_as_raw_text
    test_chat_tools_returns_none_when_offline
    test_chat_tools_never_raises_on_http_error
    test_chat_tools_reasoning_is_none_when_blank_or_absent
    test_loop_executes_tools_and_feeds_results_back
    test_loop_refuses_unknown_tools_instead_of_guessing
    test_loop_stops_at_the_step_cap
    test_loop_hard_cap_bounds_a_runaway_step_argument
    test_loop_reasoning_is_suppressed_by_default
    test_loop_offline_returns_a_clean_not_configured_event
    test_loop_cancellation_stops_between_steps
    test_loop_survives_a_crashing_tool
    test_tools_payload_matches_the_openai_wire_format
    test_agent_chat_delimits_learner_text_in_the_untrusted_block
    test_agent_chat_injects_only_reviewed_teacher_style_and_teaching_method
    test_legacy_teacher_chat_delimits_learner_text_in_the_untrusted_block
    test_agent_stream_cancels_server_side_when_the_client_disconnects
    test_offline_turn_is_ledgered_as_fallback_not_ok
    test_agent_chat_offline_returns_a_clean_event
    test_agent_chat_requires_authentication
    test_a_concept_scoped_offline_turn_is_answered_by_the_grounded_tutor
    test_an_offline_turn_without_a_concept_in_scope_stays_honestly_empty
    test_a_concept_the_course_does_not_own_is_not_answered
    test_agent_stream_emits_the_sse_contract
    test_agent_chat_rejects_an_empty_message
    test_register_with_accept_terms_writes_the_consent_ledger

**`test_api.py`** (28)
    test_auth_session_and_profile
    test_expired_token
    test_receipts_hiding_idempotence_and_variants
    test_cross_user_isolation
    test_invalid_attempt
    test_expired_receipt
    test_diagnostic_and_exam
    test_reviews_and_analytics
    test_consent_heartbeat_bounds_and_replays
    test_project_formative_export_and_deletion
    test_persistence_restart
    test_provider_failure_falls_back_to_the_curriculum
    test_dag_questions_health
    test_concurrent_idempotence
    test_production_fail_closed
    test_contract_and_invalid_event_boundaries
    test_password_whitespace_preserved
    test_persisted_rate_limit
    test_option_specific_tentative_diagnosis_and_targeted_variant
    test_exam_no_leak_from_history_export_or_state
    test_training_consent_ledger_and_minimized_export
    test_all_simulation_parameters_and_integer_trials
    test_empirical_calibration_uses_authoritative_actual_attempts
    test_exam_default_abandon_body
    test_explicit_schema_migration_preserves_existing_users
    test_generated_simulation_covers_every_course_concept
    test_generated_simulation_accepts_lesson_ids_and_overrides
    test_scene_figure_is_not_drawn_as_a_curve

**`test_assets.py`** (16)
    test_a_figure_about_a_different_idea_is_off_topic
    test_the_review_names_what_it_looked_for
    test_the_topic_alone_is_not_evidence
    test_the_generic_probe_is_never_treated_as_a_figure
    test_a_concept_map_is_a_fallback_not_a_success
    test_a_figure_with_no_controls_and_no_curve_is_broken
    test_permutations_get_a_counting_figure_not_a_distribution
    test_every_mathematics_concept_gets_a_figure_about_itself
    test_the_only_mathematics_concepts_without_a_simulation_are_the_matrices
    test_a_verified_video_is_an_embed_and_an_unverified_one_is_a_link
    test_an_image_without_a_licence_is_not_usable
    test_repair_substitutes_before_it_fixes
    test_a_broken_interactive_hands_off_to_a_curated_video_when_there_is_one
    test_an_offline_instance_is_not_given_a_video_search_job
    test_a_clean_sweep_says_nothing
    test_a_sweep_separates_what_blocks_from_what_can_be_improved

**`test_authoring.py`** (58)
    test_blueprint_resolves_prerequisites_by_title
    test_blueprint_refuses_a_dangling_prerequisite
    test_blueprint_refuses_a_forward_prerequisite
    test_blueprint_refuses_a_cycle
    test_blueprint_refuses_a_concept_with_too_many_prerequisites
    test_thin_prose_is_advisory_at_parse_and_blocking_at_audit
    test_unknown_profile_is_refused_rather_than_defaulted
    test_override_cannot_invent_a_field
    test_synthesis_matches_the_shipped_concept_shape
    test_every_concept_gets_at_least_four_valid_items
    test_the_foundry_adds_discrimination_and_transfer_items
    test_the_lesson_carries_the_depth_the_generated_layer_cannot
    test_a_step_list_the_model_already_numbered_is_not_numbered_again
    test_the_worked_example_fades_in_the_final_unit
    test_every_lesson_states_where_it_came_from
    test_difficulty_ramps_across_the_course
    test_synthesis_is_deterministic
    test_audit_refuses_an_item_whose_answer_is_not_in_the_lesson
    test_audit_refuses_a_lesson_with_no_worked_example
    test_audit_refuses_a_course_that_only_asks_for_recall
    test_audit_reports_a_flat_difficulty_ramp
    test_audit_accepts_the_course_it_is_given
    test_a_published_course_is_resolvable_and_survives_a_restart
    test_deleting_a_course_withdraws_it_from_every_registry
    test_a_course_may_not_shadow_a_shipped_one
    test_store_refuses_an_unaudited_course
    test_republishing_requires_an_explicit_replace
    test_draft_refuses_without_a_model
    test_draft_retries_with_the_validators_complaint
    test_a_refused_lesson_is_rewritten_from_the_complaint
    test_draft_gives_up_honestly
    test_an_answer_that_puts_a_summary_in_the_title_still_lands
    test_a_half_answered_batch_is_asked_again_for_the_rest
    test_authoring_tools_are_teacher_gated
    test_authoring_tool_builds_and_publishes
    test_authoring_tool_reports_audit_findings_rather_than_storing
    test_extend_course_adds_a_unit_under_the_same_audit
    test_tools_are_registered_for_the_agent_loop
    test_http_preview_stores_nothing
    test_http_create_then_read_then_delete
    test_http_requires_a_teacher
    test_http_refuses_an_unreadable_blueprint
    test_http_refuses_a_thin_course_with_audit_findings
    test_http_draft_without_a_model_is_503
    test_http_methodology_is_readable
    test_an_authored_course_is_studyable_through_the_existing_endpoints
    test_the_review_page_shows_the_lessons_the_items_and_the_answer_key
    test_the_review_page_escapes_a_lesson_and_reports_a_refusal
    test_an_authored_textbook_carries_a_real_photograph
    test_an_unverified_image_cannot_enter_a_textbook
    test_illustrating_an_offline_instance_is_reported_and_changes_nothing
    test_a_concept_that_finds_nothing_is_reported_rather_than_filled
    test_deleting_a_course_forgets_its_photographs
    test_the_tutor_can_create_an_illustrated_textbook_in_one_call
    test_the_tutor_can_attach_one_chosen_photograph
    test_the_illustration_tools_are_teacher_gated
    test_http_illustration_reports_what_it_did
    test_a_concept_with_no_search_hits_is_not_reported_as_a_filter_refusal

**`test_authoring_overlay.py`** (9)
    test_framing_preserves_the_courses_own_structure
    test_overlay_keeps_pack_fields_and_adds_depth
    test_a_framed_course_survives_the_round_trip_through_its_own_document
    test_the_diagram_follows_the_concept_rather_than_the_template
    test_publishing_an_overlay_deepens_the_shipped_course
    test_withdrawing_an_overlay_restores_the_shipped_course
    test_an_overlay_restores_the_structural_items_it_displaces
    test_a_lesson_written_alone_gets_no_under_optioned_items
    test_a_concept_the_course_does_not_own_is_reported_not_invented

**`test_board.py`** (23)
    test_between_orders_and_is_strict
    test_between_refuses_impossible_interval
    test_top_z_places_new_nodes_above_existing
    test_create_and_load_roundtrip
    test_add_move_update_delete_batch
    test_stale_base_version_is_a_conflict_not_a_stomp
    test_non_owner_cannot_mutate
    test_unknown_kind_and_fabricated_media_are_refused
    test_video_node_rejects_off_allowlist_embeds
    test_update_cannot_touch_media_status
    test_licence_rollup_share_alike_wins
    test_svg_export_embeds_and_stamps
    test_lesson_bundle_roundtrip
    test_import_rejects_non_bundle
    test_share_create_resolve_revoke
    test_share_requires_ownership_and_expires
    test_image_file_resolves_only_real_cache_entries
    test_board_http_crud_and_conflict
    test_board_is_per_account
    test_share_endpoint_serves_without_auth_and_revokes
    test_image_bytes_endpoint
    test_agent_chat_rejects_bad_image_payloads
    test_export_endpoint_formats

**`test_calculus_figures.py`** (10)
    test_no_mathematics_concept_falls_back_to_the_generic_probe
    test_only_declared_concepts_are_left_without_a_figure
    test_the_authored_course_keeps_its_own_figures
    test_a_factorial_is_not_a_factor
    test_no_mathematics_concept_is_served_a_quadratic_figure
    test_each_calculus_family_gets_its_own_figure
    test_every_generated_figure_explains_itself_and_reads_out
    test_every_generated_figure_builds_at_every_parameter_extreme
    test_a_negative_power_base_is_bracketed_in_both_renderings
    test_a_series_figure_plots_totals_not_terms

**`test_capabilities.py`** (23)
    test_anonymous_caller_fails_closed_to_the_free_tier
    test_matrix_shape_is_stable
    test_tier_resolution_for_a_signed_in_learner
    test_expired_entitlement_stops_resolving
    test_granted_capability_is_visible_and_writes_real_rows
    test_grant_persists_the_entitlement_row
    test_ungranted_capability_is_refused_with_a_reason
    test_receipt_cannot_be_replayed_across_capabilities
    test_tampered_and_expired_receipts_are_refused
    test_operator_comp_grants_without_any_receipt
    test_revoke_removes_the_entitlement
    test_ungranted_beats_degraded_in_the_reason
    test_entitled_capability_degrades_when_the_provider_is_off
    test_absent_package_degrades_the_speech_capability
    test_local_capabilities_never_degrade
    test_resolver_never_raises_on_a_probe_failure
    test_http_surface_shape
    test_grant_requires_authentication
    test_broken_token_on_a_read_is_not_silently_anonymous
    test_free_capability_grant_is_an_idempotent_noop
    test_missing_capability_cannot_be_granted
    test_the_adoption_seam_other_routes_will_use
    test_require_capability_refuses_a_degraded_provider

**`test_classroom.py`** (34)
    test_a_learner_on_a_break_is_never_disturbed
    test_another_application_pauses_the_timer_and_docks_participation
    test_very_suspicious_triggers_a_cheat_check_with_every_item
    test_a_quiz_tick_with_a_conclusive_signal_runs_the_cheat_check
    test_plain_suspicion_without_conclusive_evidence_only_asks
    test_away_with_rest_quota_left_reminds_without_penalty
    test_away_with_the_rest_quota_spent_marks_the_timeout
    test_a_still_unanswered_learner_gets_a_staying_quiz
    test_a_frame_that_shows_work_reads_as_reading_not_absence
    test_a_low_confidence_frame_does_not_override_the_away_reading
    test_drifting_between_the_two_idle_thresholds_asks_one_question
    test_lagging_but_still_browsing_is_allowed_to_continue
    test_lagging_and_stopped_gets_help_and_lowers_difficulty
    test_progress_is_measured_against_the_sessions_own_plan
    test_ahead_of_the_plan_is_not_lagging
    test_staying_far_too_long_on_a_node_suggests_and_notes
    test_an_error_streak_reads_as_struggling_and_asks_for_help
    test_a_learner_who_asks_for_help_gets_a_hint_and_a_skip
    test_an_active_on_track_learner_is_left_alone
    test_low_node_memory_explains_instead_of_advancing
    test_strong_node_memory_asks_the_learner_to_reason_aloud
    test_low_node_memory_on_a_quiz_allows_a_skip
    test_an_unknown_belief_is_not_a_weak_one
    test_the_memory_layer_never_overrides_a_pause_or_cheat_check
    test_an_interruption_inside_the_cooldown_is_marked_quiet
    test_an_interruption_after_the_cooldown_is_not_quiet
    test_the_cooldown_never_silences_a_cheat_check
    test_the_decision_carries_a_participation_reading
    test_from_mapping_tolerates_missing_and_junk_fields
    test_the_same_snapshot_always_yields_the_same_decision
    test_describe_exposes_the_reviewable_thresholds
    test_classroom_and_supervision_agree_on_shared_states
    test_the_tick_route_returns_a_decision
    test_the_tick_route_needs_a_session

**`test_container_image.py`** (3)
    test_every_resource_directory_is_copied_into_the_image
    test_the_build_context_can_see_those_directories
    test_the_ignore_file_does_not_exclude_what_the_image_needs

**`test_counting_figures.py`** (9)
    test_factorial_is_defined_on_the_whole_numbers_only
    test_choose_and_permute_agree_with_the_stdlib
    test_choosing_more_than_available_is_zero_not_an_error
    test_the_template_claims_the_concept
    test_the_curve_is_the_binomial_coefficients
    test_the_curve_has_one_point_per_integer
    test_the_two_counts_differ_by_exactly_r_factorial
    test_an_impossible_selection_is_explained_rather_than_crashing
    test_the_figure_is_stable_across_calls

**`test_course_builder.py`** (39)
    test_every_concept_carries_a_verbatim_span_of_the_source
    test_extraction_is_deterministic
    test_generated_graph_is_a_dag_and_every_edge_names_a_real_concept
    test_prerequisites_come_from_the_source_not_from_position_alone
    test_a_too_thin_source_is_refused_with_a_reason_and_a_minimum
    test_a_single_paragraph_is_refused_even_when_it_is_long
    test_a_source_with_too_few_concepts_is_refused
    test_the_refusal_contract_is_data_and_is_served
    test_every_question_has_four_options_one_correct_and_a_diagnosis_per_distractor
    test_every_concept_has_more_than_one_variant
    test_a_created_course_is_studyable_through_the_existing_endpoints
    test_a_created_course_survives_a_restart_of_the_process
    test_deleting_a_course_removes_it_and_resets_the_active_course
    test_a_course_belongs_to_one_account_only
    test_an_anonymous_request_is_refused
    test_a_preview_persists_nothing
    test_a_textbook_pdf_yields_its_terms_not_its_furniture
    test_a_wrapped_bold_heading_is_one_term
    test_the_term_markers_never_reach_the_learner
    test_a_textbook_course_plans_end_to_end
    test_upload_can_save_and_enrol_the_course
    test_upload_preview_still_persists_nothing
    test_upload_reads_a_multipart_body
    test_upload_reads_a_raw_body_with_a_filename
    test_upload_detects_docx_by_content_not_by_extension
    test_upload_reads_a_pdf
    test_upload_refuses_a_file_it_cannot_parse
    test_upload_refuses_an_empty_file
    test_upload_without_a_file_part_is_a_structured_refusal
    test_a_non_https_url_is_refused_without_fetching
    test_an_oversized_page_is_refused_and_does_not_raise
    test_a_login_walled_page_is_refused
    test_a_non_text_content_type_is_refused
    test_a_fetch_failure_is_a_structured_refusal_not_a_500
    test_a_redirect_to_http_is_refused
    test_an_https_page_is_ingested
    test_a_missing_source_is_refused
    test_my_courses_lists_the_account_own_courses_with_their_graph
    test_creating_a_course_does_not_leak_it_into_the_shared_catalogue

**`test_creation_tools.py`** (65)
    test_gate_student_create_is_refused_with_reason
    test_gate_student_change_requests_are_approved_as_requirements
    test_gate_teacher_can_create_and_restructure
    test_gate_unknown_role_fails_closed_to_student
    test_gate_teacher_grant_requires_exact_canonical_string
    test_gate_teacher_grant_still_works_and_canonical_student_passes_categories
    test_gate_student_empty_note_is_refused
    test_gate_student_create_proceeds_only_on_an_approved_record
    test_gate_unknown_category_is_refused
    test_approval_records_persist_to_disk
    test_validation_accepts_a_good_sim_and_rejects_the_bad_ones
    test_validator_catches_the_measured_bypasses
    test_validator_still_allows_ordinary_named_functions
    test_validator_allows_the_lowercase_function_keyword
    test_validator_catches_the_residual_bypasses
    test_validator_still_allows_the_clean_forms
    test_deck_kind_does_not_require_data_series
    test_extract_html_tolerates_fences_and_prose
    test_store_versions_are_append_only
    test_store_diff_summary_counts_lines
    test_store_read_api_is_the_web_layers_path
    test_write_simulation_requires_a_provider
    test_write_simulation_gate_refuses_students
    test_write_simulation_stores_a_validated_artifact
    test_write_simulation_refuses_invalid_html
    test_a_truncated_document_is_never_stored
    test_a_near_miss_is_retried_with_the_validators_reasons
    test_a_repeated_failure_reports_the_problems_and_stops
    test_tool_specs_do_not_expose_a_role_argument
    test_role_tool_argument_is_rejected
    test_unauthenticated_context_is_a_student
    test_edit_simulation_scoped_bug_request_bumps_version
    test_edit_simulation_student_cannot_restructure
    test_edit_simulation_teacher_restructure_is_allowed
    test_edit_simulation_invalid_update_leaves_previous_version_serving
    test_edit_simulation_unknown_artifact_is_an_error
    test_generate_slides_writes_a_real_deck_and_pptx
    test_generate_slides_from_authored_curriculum
    test_generate_slides_without_input_refuses_honestly
    test_tts_refuses_honestly_when_voice_output_is_off
    test_tts_names_the_missing_service_and_how_to_start_it
    test_tts_produces_audio_when_the_service_answers
    test_tts_rejects_a_200_that_is_not_audio
    test_tts_maps_a_licence_refusal_to_an_actionable_message
    test_tts_translates_edge_rate_syntax_into_a_speed_multiplier
    test_tts_clamps_a_rate_the_provider_would_reject
    test_tts_does_not_silently_accept_an_edge_voice_name
    test_tts_refuses_text_beyond_the_provider_limit
    test_tts_sends_a_tone_to_a_freeform_instruction_engine
    test_tts_reduces_a_tone_to_omnivoice_speaker_design_tags
    test_tts_does_not_claim_a_tone_omnivoice_cannot_express
    test_tts_passes_a_pure_tag_tone_through_without_a_lecture
    test_tts_keeps_different_tones_out_of_each_others_cache
    test_tts_replays_a_cached_recording_without_synthesising_again
    test_tts_applies_the_configured_default_tone
    test_image_search_delegates_to_media_and_reports_honest_disabled_state
    test_image_search_returns_cleared_candidates_with_citations
    test_web_search_refuses_when_disabled
    test_web_search_refuses_when_package_missing
    test_web_search_withholds_snippets_from_unclear_domains
    test_image_generate_refuses_when_disabled
    test_image_generate_reports_provider_and_writes_file
    test_image_generate_reports_honest_failure_when_all_providers_fail
    test_creation_tools_are_registered_with_the_right_postures
    test_scoped_edit_reaches_the_model_as_a_requirement

**`test_curation_tools.py`** (19)
    test_every_pack_row_is_registered_and_https
    test_game_sources_are_all_link_only
    test_wikipedia_policy_is_ingestible
    test_find_game_refuses_learner_role
    test_find_game_refuses_missing_user
    test_find_game_returns_registered_cards
    test_find_game_names_the_gap
    test_find_game_withholds_under_commercial_use
    test_fetch_page_text_refuses_when_media_disabled
    test_fetch_page_text_refuses_uncleared_domain_without_network
    test_fetch_page_text_refuses_non_http_scheme
    test_fetch_page_text_reads_cleared_domain
    test_fetch_page_text_re_gates_redirects
    test_wikipedia_summary_refuses_when_media_disabled
    test_wikipedia_summary_refuses_bad_lang
    test_browser_snapshot_refuses_learner
    test_browser_snapshot_refuses_when_disabled
    test_search_videos_refuses_learner
    test_search_videos_refuses_when_media_disabled

**`test_curriculum_route.py`** (9)
    test_the_layer_resolves_a_real_course_for_every_course_the_harness_ships
    test_every_concept_in_every_course_names_the_course_it_belongs_to
    test_only_mathematics_routes_through_the_symbolic_engine
    test_every_reference_card_carries_a_rights_position_and_both_spellings
    test_a_course_the_learner_built_routes_through_the_same_layer
    test_an_unknown_course_raises_at_the_edge_rather_than_looking_empty
    test_route_for_user_falls_back_when_the_account_names_a_course_that_is_gone
    test_the_curriculum_surface_stamps_every_concept_and_offers_the_sources
    test_a_lesson_surface_stamps_the_course_that_owns_the_concept

**`test_deck.py`** (13)
    test_export_roundtrip_reopens_with_real_runs_and_picture
    test_import_roundtrip_survives_text_and_geometry
    test_import_refuses_bytes_that_are_not_a_pptx
    test_slide_svg_contains_real_text_and_font_size
    test_malformed_element_is_rejected_with_422
    test_replace_with_malformed_document_is_422
    test_export_route_returns_a_real_zip
    test_decks_are_per_account
    test_slide_add_move_duplicate_delete
    test_element_patch_moves_and_restyles
    test_deck_images_reports_attribution
    test_upload_image_then_embed_in_pptx
    test_deck_from_concept_builds_an_editable_deck

**`test_desktop_environment.py`** (6)
    test_desktop_is_strict_about_consent_and_quiet_about_telemetry
    test_desktop_boots_with_sqlite_and_no_secret
    test_production_still_refuses_sqlite
    test_development_keeps_its_convenient_defaults
    test_desktop_registration_is_refused_without_the_attestation
    test_desktop_first_account_can_teach_and_consent_is_recorded

**`test_diagram.py`** (14)
    test_fourier_smoothing_preserves_line_segments_and_curve_endpoints
    test_proposal_becomes_only_board_paths_and_text
    test_formula_sampler_handles_functions_parametrics_and_fourier_series
    test_formula_sampler_refuses_python_execution_and_bad_bounds
    test_catalog_has_original_editable_economics_and_biology_templates
    test_image_vectorizer_extracts_line_only_nodes_from_raster
    test_image_vectorizer_refuses_blank_or_unsupported_bytes
    test_vlm_route_sends_snapshot_and_returns_nonmutating_path_preview
    test_curve_template_and_catalog_routes_are_preview_only
    test_vectorization_route_checks_image_and_returns_path_nodes
    test_diagram_route_refuses_non_owner_and_invalid_snapshot
    test_clipboard_paste_caches_image_and_board_can_reload_it
    test_clipboard_paste_rejects_invalid_or_unsupported_image
    test_live_deepseek_v41_flash_reads_board_snapshot_and_commits_line_paths

**`test_econ_figures.py`** (22)
    test_every_rule_names_a_template_that_exists
    test_no_template_emits_a_broken_coordinate
    test_a_tax_wedge_splits_the_burden_by_elasticity
    test_a_subsidy_is_the_tax_wedge_mirrored
    test_the_isoquant_is_tangent_to_the_isocost
    test_a_price_maker_sets_marginal_revenue_equal_to_marginal_cost
    test_a_price_taker_has_no_markup
    test_marginal_utility_buys_while_the_next_unit_is_worth_its_price
    test_the_lorenz_curve_ends_at_perfect_equality_and_bends_below_it
    test_average_product_peaks_where_it_crosses_marginal_product
    test_economic_profit_charges_for_the_owners_own_inputs
    test_present_value_discounts_each_receipt_by_its_own_year
    test_the_payoff_matrix_marks_a_mutual_best_response
    test_a_public_good_is_under_provided_because_private_demand_is_too_low
    test_the_specific_shape_wins_over_the_generic_one
    test_a_concept_with_nothing_to_draw_gets_no_figure
    test_the_caption_states_the_parameters_the_figure_was_drawn_with
    test_a_template_with_no_axes_still_renders_a_full_canvas
    test_the_paper_is_painted_before_the_title_it_sits_behind
    test_adverse_selection_draws_a_missing_market_rather_than_a_cheap_one
    test_a_concept_with_no_honest_shape_gets_no_figure
    test_the_pack_id_decides_the_figure_before_any_paraphrase_does

**`test_feature_routers.py`** (7)
    test_every_named_feature_router_is_a_real_module_with_a_router
    test_the_application_mounts_every_feature_router
    test_the_mounted_routes_actually_answer
    test_every_feature_router_has_a_frozen_artifact_probe
    test_each_probe_names_a_route_its_module_really_declares
    test_packaging_reads_the_same_router_list_as_the_application
    test_the_archive_check_actually_rejects_a_router_that_did_not_land

**`test_final_contract.py`** (6)
    test_final_assessment_completion_and_progress
    test_final_diagnostic_status_uses_completed_assessment
    test_final_practice_is_not_an_assessment
    test_final_daily_active_minutes_are_utc_day_isolated
    test_final_chat_history_preserves_exact_provider_after_restart
    test_final_invalid_payload_has_field_level_422_details

**`test_flashcards.py`** (12)
    test_generation_is_grounded_in_real_curriculum_blocks_and_questions
    test_a_diagnosed_distractor_becomes_a_misconception_card
    test_generation_is_idempotent
    test_generation_preview_does_not_persist
    test_a_card_without_provenance_cannot_be_created
    test_good_schedules_further_out_than_again
    test_review_rejects_an_out_of_range_grade
    test_session_interleaves_two_concepts
    test_stats_and_schedule_move_after_a_review
    test_a_card_is_private_to_its_account
    test_editing_and_deleting_a_card
    test_export_import_round_trip

**`test_guided_sim.py`** (9)
    test_a_complete_guided_run_is_acceptable_evidence
    test_the_cycle_prompts_cover_all_three_phases
    test_a_run_without_a_prediction_or_explanation_is_refused
    test_a_short_explanation_does_not_count
    test_missing_required_fields_are_named
    test_an_out_of_range_or_non_boolean_field_is_refused
    test_the_prediction_is_scored_by_the_payload_builder_not_asserted_by_the_caller
    test_a_wrong_prediction_is_not_scolded
    test_status_reports_the_simulation_cycle

**`test_harness.py`** (68)
    test_memory_reinforcement_and_decay_are_separate_signals
    test_memory_confidence_is_bounded_and_never_reaches_certainty
    test_memory_relevance_prefers_this_concept_over_a_distant_one
    test_memory_digest_is_citable_and_hedged
    test_memory_forget_and_wipe_are_exact
    test_memory_rejects_an_unknown_kind_and_empty_text
    test_tool_catalogue_is_internally_consistent
    test_a_tool_whose_optional_package_is_absent_is_registered_but_not_offered
    test_unknown_tool_and_bad_arguments_are_refusals_not_exceptions
    test_material_search_returns_links_only_for_restricted_sources
    test_fetch_material_text_refuses_restricted_sources_and_allows_cleared_ones
    test_no_generated_artifact_puts_restricted_text_in_front_of_the_learner
    test_every_tool_returns_a_typed_result
    test_build_figure_is_real_executable_content_for_a_curve_and_a_scene
    test_case_study_is_grounded_in_the_authored_lesson
    test_workspace_tools_are_confined
    test_sandbox_runs_ordinary_python_and_writes_inside_the_workspace
    test_sandbox_refuses_network_process_and_import_capabilities
    test_sandbox_runtime_hook_catches_what_static_analysis_cannot
    test_sandbox_refuses_writes_outside_and_reads_of_the_home_tree
    test_sandbox_bounds_time_output_and_language
    test_sandbox_path_resolution_refuses_escapes_and_reports_boundaries
    test_sandbox_denies_data_directory_reads_but_not_the_learner_workspace
    test_every_artifact_kind_composes_for_a_curve_and_a_scene_concept
    test_generated_quiz_items_name_the_error_process_behind_each_distractor
    test_generated_numeric_items_are_mathematically_correct
    test_quiz_falls_back_to_a_concept_item_when_no_numeric_item_applies
    test_slide_deck_carries_speaker_notes_and_a_real_figure
    test_deck_renders_to_a_self_contained_svg_for_print_and_export
    test_svg_renderer_escapes_text_so_a_concept_title_cannot_inject_markup
    test_figure_svg_is_valid_and_draws_a_scene_as_bars_not_a_line
    test_image_brief_always_ships_a_deterministic_fallback
    test_flashcards_include_cards_built_from_the_learner_record
    test_generation_rejects_an_unknown_kind_and_concept
    test_a_failing_model_degrades_to_the_deterministic_artifact
    test_scoring_covers_every_move_and_is_deterministic
    test_an_unattempted_concept_is_taught_or_oriented_not_drilled
    test_a_due_concept_is_retrieved
    test_a_conceptual_error_prefers_a_change_of_representation
    test_fast_wrong_attempts_are_treated_as_overload_not_as_a_reason_to_drill
    test_strong_mastery_opens_applied_work
    test_repetition_is_itself_a_reason_to_change_format
    test_a_concept_with_no_figure_cannot_be_simulated
    test_measured_progress_shifts_the_next_decision
    test_evidence_counts_only_incorrect_responses_as_errors
    test_plan_records_the_decision_and_the_outcome_feeds_back
    test_an_active_exam_suppresses_teaching_moves
    test_gather_reads_real_learner_state
    test_explain_decision_is_reviewable
    test_system_prompt_carries_the_contract_and_the_live_tool_list
    test_harness_status_is_self_describing
    test_harness_endpoints_require_authentication
    test_harness_status_and_tools_endpoints
    test_harness_prompt_endpoint_exposes_what_the_model_is_told
    test_harness_plan_endpoint_accepts_a_lesson_id_and_can_execute
    test_attempts_write_memory_that_the_api_then_reports
    test_memory_can_be_deleted_by_note_and_wholesale
    test_outcome_endpoint_closes_the_learning_loop
    test_generate_endpoint_returns_a_grounded_artifact
    test_workspace_endpoints_write_read_list_and_delete
    test_workspace_run_endpoint_executes_and_refuses
    test_export_and_delete_cover_the_harness_records
    test_health_reports_the_harness_posture
    test_harness_help_is_withheld_during_an_active_exam
    test_schema_v2_migrates_to_v3_without_losing_data
    test_a_database_from_the_future_is_refused
    test_the_dialogue_ladder_is_attached_to_every_decision
    test_two_failed_cycles_escalate_the_ladder_without_revealing_the_answer

**`test_image_fetch.py`** (35)
    test_fetch_reports_a_refusal_when_the_network_is_unavailable
    test_fetch_never_raises_even_when_the_transport_raises_something_unexpected
    test_fetch_downloads_nothing_when_media_is_disabled
    test_an_unknown_licence_is_dropped_and_the_reason_is_present
    test_a_non_commercial_licence_is_dropped_with_its_reason
    test_normalise_mime_is_applied_at_the_provider_boundary
    test_fetch_caches_a_cleared_image_and_carries_its_attribution
    test_fetch_route_requires_a_token_and_accepts_one
    test_fetch_route_rejects_an_empty_query
    test_library_returns_only_the_calling_accounts_images
    test_library_can_be_filtered_by_query
    test_library_requires_a_token
    test_attribution_route_returns_the_credit_and_404s_an_unknown_sha
    test_delete_removes_an_image_from_the_library
    test_for_lesson_attaches_a_photograph_block_to_the_lesson
    test_a_lesson_with_no_fetch_gains_no_photograph_block
    test_for_lesson_rejects_an_unknown_concept_and_needs_a_token
    test_lesson_image_needs_is_capped_and_skips_thin_blocks
    test_a_concept_query_is_the_title_because_a_phrase_returns_nothing
    test_support_ranks_candidates_without_rejecting_any
    test_the_fetch_stops_at_the_attempt_cap_instead_of_taking_a_lower_ranked_image
    test_a_rate_limited_host_stops_the_fetch_immediately
    test_a_successful_fetch_reports_the_candidates_it_skipped
    test_the_user_agent_carries_a_contact_route
    test_the_client_sends_the_configured_contact
    test_an_agent_policy_refusal_is_named_rather_than_reported_as_a_transport_fault
    test_an_unset_contact_is_reported_rather_than_hidden
    test_a_block_slot_searches_the_concept_title_not_a_ten_word_phrase
    test_one_coincidental_word_is_not_enough_to_illustrate_a_concept
    test_a_rejected_shared_word_says_which_term_is_missing
    test_the_head_term_survives_inflection
    test_a_withdrawn_photograph_stops_being_served
    test_the_other_half_of_the_concept_is_a_wrong_answer_not_a_near_miss
    test_infographics_is_not_information
    test_a_two_word_query_needs_both_words

**`test_image_mime_normalisation.py`** (5)
    test_normalise_mime_accepts_extensions_and_mime_types
    test_normalise_mime_preserves_an_unknown_value_for_the_reason_string
    test_a_bare_extension_is_not_a_rejection_reason
    test_a_genuinely_undisplayable_type_is_still_rejected
    test_extension_map_covers_every_displayable_mime

**`test_image_query_widening.py`** (6)
    test_the_head_of_a_lesson_title_is_the_part_a_photograph_can_show
    test_a_one_word_head_is_left_alone
    test_a_title_without_a_conjunction_is_not_widened
    test_the_whole_title_is_tried_first_and_the_subject_second
    test_a_title_that_works_is_never_searched_twice
    test_a_network_refusal_is_not_retried

**`test_interruption.py`** (11)
    test_an_interruption_is_named_to_the_model
    test_an_ordinary_message_does_not_claim_to_be_an_interruption
    test_an_answer_may_replace_what_is_playing
    test_an_explanation_queues_behind_what_is_playing
    test_a_notice_never_cuts_across_the_teacher
    test_an_unknown_kind_falls_back_to_an_explanation
    test_the_interval_check_stays_silent_when_the_learner_is_working
    test_a_nudge_is_offered_as_an_idle_only_notification
    test_a_notice_inside_its_cooldown_is_withheld
    test_a_spoken_notice_carries_a_clip_the_client_can_play
    test_a_withheld_notice_never_spends_a_synthesis

**`test_knowledge_graph.py`** (20)
    test_prerequisite_and_sequence_edges_are_tracked_separately
    test_duplicate_ids_are_rejected_unless_replaced
    test_validate_catches_self_loop_unknown_prerequisite_and_bad_metadata
    test_cycles_are_detected_with_a_concrete_path
    test_sequence_contradicting_prerequisites_is_reported
    test_raise_if_invalid_raises_on_errors_only
    test_topological_order_is_deterministic_and_respects_edges
    test_topological_order_refuses_a_cyclic_graph
    test_depths_roots_leaves_and_subgraph
    test_search_scores_exact_id_above_title_above_keywords
    test_search_is_bounded_and_empty_safe
    test_from_pack_restores_the_same_graph
    test_combine_merges_packs_with_later_wins
    test_from_dict_normalises_malformed_records
    test_slug_is_stable_ascii_and_lowercase
    test_coverage_reports_mastery_ready_and_units
    test_payload_carries_both_edge_kinds_and_stats
    test_every_shipped_pack_is_structurally_valid
    test_shipped_packs_carry_provenance_and_unique_ids
    test_shipped_packs_declared_metadata_names_the_pipeline

**`test_kst.py`** (11)
    test_states_are_exactly_the_down_sets
    test_cycles_are_rejected
    test_closure_requires_prerequisites
    test_contradictory_observations_are_refused_not_fudged
    test_observations_filter_the_version_space_exactly
    test_probe_selection_maximises_entropy_and_probes_disambiguate
    test_gaps_report_names_surely_known_and_missing
    test_real_math_graph_uses_sampled_mode_and_is_deterministic
    test_sampled_mode_honours_observations
    test_min_probes_estimate_is_reported_honestly
    test_space_builds_from_the_knowledge_graph_helper

**`test_learning.py`** (13)
    test_fallback_evidence_and_recall
    test_domain_gate_rejects_toeic
    test_numeric_answers_independently_recomputed
    test_symbolic_variants_by_substitution
    test_dag_cycle_rejected
    test_item_calibration_monotonic_and_smoothed
    test_diagnostic_order_depends_on_uncertainty_and_prerequisites
    test_every_distractor_has_specific_tentative_crosscheck
    test_native_parameter_contracts_and_independent_crosschecks
    test_practice_skips_a_concept_the_learner_has_already_mastered
    test_practice_falls_back_to_a_mastered_concept_when_nothing_else_remains
    test_practice_prefers_a_concept_whose_prerequisites_are_met
    test_mastery_threshold_is_shared_by_gating_and_the_skip_rule

**`test_learning_science.py`** (14)
    test_interleaved_group_spans_two_families_and_reports_the_mix
    test_interleaved_group_mixes_due_reviews_with_new_items
    test_group_requests_are_rejected_outside_practice_and_when_disabled
    test_calibration_decomposition_sums_and_speaks_plainly
    test_calibration_uses_only_completed_graded_attempts
    test_self_explanation_gate_is_a_422_not_a_warning
    test_self_explanation_gate_is_switchable_by_experiment
    test_transfer_item_family_never_appeared_in_practice
    test_transfer_requires_practice_history
    test_bucket_is_stable_and_assignment_is_sticky
    test_assignment_persists_and_flag_overrides
    test_exposure_logging_is_idempotent
    test_admin_experiments_lifecycle
    test_migration_008_upgrades_a_v7_database

**`test_legal_guard.py`** (12)
    test_regex_catches_every_placeholder_class_from_the_audit
    test_regex_tolerates_markdown_links_and_prose_brackets
    test_scan_reports_each_file_and_line
    test_clean_bundle_passes
    test_missing_legal_directory_is_not_shippable
    test_assert_shippable_raises_with_guidance
    test_production_startup_refuses_unfilled_legal_bundle
    test_production_startup_passes_clean_bundle
    test_template_opt_out_is_explicit
    test_current_repository_bundle_is_reported_honestly
    test_cli_allow_template_reports_without_failing
    test_cli_fails_loudly_on_unfilled_bundle

**`test_lesson_format.py`** (9)
    test_the_format_forbids_the_five_failures_that_matter
    test_the_format_puts_contrast_before_the_formula
    test_a_guided_solution_asks_for_one_computation_and_stops
    test_wrong_options_must_name_a_real_mistake
    test_the_simulation_clause_appears_only_when_the_tool_exists
    test_the_agent_prompt_carries_the_format
    test_the_agent_prompt_names_the_simulation_tool_only_when_it_is_available
    test_the_transparency_payload_exposes_the_shape_rules
    test_the_chat_tutor_wires_the_same_block_into_its_prompt

**`test_lesson_procedure.py`** (64)
    test_exactly_one_input_block_is_ever_emitted
    test_a_capable_learner_is_not_shown_an_input_at_all
    test_a_procedural_error_prefers_the_worked_example_over_the_deck
    test_first_exposure_to_a_science_concept_opens_with_the_curated_video
    test_first_exposure_opens_with_the_video_whatever_the_subject
    test_a_video_is_never_invented_when_none_is_curated
    test_the_same_deck_is_not_served_twice_in_a_day
    test_a_concept_with_no_assets_still_teaches_by_explanation
    test_the_interactive_is_gated_by_a_mastery_band
    test_a_first_lesson_may_open_with_the_interactive_because_the_diagnostic_measures
    test_an_interactive_already_used_this_session_is_not_repeated
    test_an_absent_interactive_is_a_reason_not_an_empty_block
    test_the_plan_never_exceeds_its_budget
    test_a_short_session_is_a_smaller_lesson_not_a_truncated_one
    test_practice_survives_every_budget_because_it_is_the_only_evidence
    test_an_unobservable_interactive_earns_an_extra_question
    test_practice_size_follows_mastery_and_the_bank
    test_overload_ends_the_session_instead_of_shrinking_it
    test_every_refusal_carries_a_sentence_and_appears_once
    test_every_block_names_a_purpose_and_a_reason
    test_the_practice_block_promises_the_items_the_bank_actually_holds
    test_the_same_evidence_compiles_the_same_lesson
    test_the_hash_moves_when_the_lesson_moves_and_not_otherwise
    test_the_procedure_can_be_switched_off_from_configuration
    test_the_rendered_block_names_the_current_activity_and_forbids_substitution
    test_the_rendered_block_marks_completed_activities
    test_the_rendered_block_publishes_the_refusals_as_prohibitions
    test_the_rendered_block_binds_the_artifact_rather_than_describing_it
    test_an_empty_procedure_renders_nothing_rather_than_a_placeholder
    test_the_procedure_reaches_the_system_prompt_the_provider_receives
    test_the_agent_loop_carries_the_procedure_to_its_tool_registry
    test_progress_shapes_the_next_turn
    test_the_sequence_is_frozen_once_the_lesson_begins
    test_starting_the_same_lesson_twice_returns_the_same_run
    test_advancing_every_block_completes_the_run
    test_a_double_tap_is_refused_rather_than_recorded_twice
    test_an_unknown_block_is_refused
    test_abandoning_frees_the_concept_for_a_new_lesson
    test_another_learners_run_is_a_404_not_a_403
    test_a_concept_outside_the_learners_course_is_a_404
    test_advancing_writes_no_evidence
    test_the_exam_guard_covers_the_whole_lesson
    test_the_deck_is_materialised_and_its_twin_is_downloadable
    test_a_pptx_download_cannot_escape_the_artifact_directory
    test_the_deck_block_carries_the_slides_a_client_can_present
    test_the_video_block_carries_a_url_a_player_can_actually_use
    test_the_simulation_block_carries_what_the_app_needs_to_open_it
    test_the_started_run_still_carries_what_the_preview_promised
    test_the_plan_preview_persists_nothing
    test_the_plan_is_reproducible_from_the_endpoint
    test_the_run_payload_carries_the_authored_concept_title
    test_a_shorter_budget_from_the_client_produces_a_shorter_lesson
    test_the_resolver_refuses_a_symbolic_figure_for_a_non_mathematics_subject
    test_the_resolver_never_promises_a_video_that_is_not_curated
    test_the_game_matcher_prefers_containment_over_overlap
    test_the_deck_opening_slide_carries_a_licence_cleared_image
    test_a_deck_without_a_cleared_picture_ships_without_one
    test_the_concept_board_can_be_created_at_the_id_the_client_addresses
    test_the_deck_cursor_starts_on_the_opening_slide
    test_the_tutor_can_advance_the_deck_the_learner_is_watching
    test_the_learner_moving_the_deck_reaches_the_tutor
    test_the_prompt_tells_the_tutor_it_can_move_an_open_deck
    test_the_cursor_is_clamped_to_the_deck_that_exists
    test_a_board_id_owned_by_somebody_else_is_not_silently_reused

**`test_leveling.py`** (13)
    test_no_evidence_means_no_level
    test_one_item_short_of_the_minimum_is_still_no_level
    test_an_unstated_count_is_treated_as_not_enough
    test_enough_evidence_produces_a_level
    test_cefr_is_withheld_for_a_non_language_subject
    test_cefr_is_reported_for_a_language_subject
    test_language_subject_matching_is_not_fooled_by_a_substring_of_a_non_language
    test_the_band_rises_with_ability
    test_grade_labels_read_as_english
    test_the_readable_success_matches_the_psychometric_function
    test_nothing_claims_certification
    test_a_fresh_account_is_not_given_a_level
    test_the_route_reports_a_grade_for_a_measured_learner

**`test_license_override.py`** (10)
    test_no_file_means_no_overrides
    test_default_position_unchanged_without_file
    test_valid_override_flips_only_the_named_policy
    test_unknown_policy_name_is_dropped
    test_prohibited_source_can_never_be_overridden
    test_unknown_target_class_dropped
    test_missing_approval_fields_dropped
    test_unreadable_file_fails_closed
    test_wrong_schema_fails_closed
    test_registry_reports_effective_position_and_override

**`test_live_smoke.py`** (1)
    test_live_provider_returns_a_typed_tool_call

**`test_lumi_art.py`** (5)
    test_the_resource_set_is_exactly_the_seven_formal_sprites
    test_the_shipped_files_match_the_swift_sprite_enum
    test_every_sprite_is_a_256_square_rgba_render
    test_every_sprite_is_a_matted_render_not_a_flat_cutout
    test_the_figure_fills_the_canvas_the_way_lumiart_expects

**`test_mathkit.py`** (29)
    test_expression_evaluation
    test_expression_rejects_unknown_names_and_code
    test_rendered_expression_reparses_to_the_same_function
    test_rendered_output_can_be_read_back_in
    test_typographic_operators_are_accepted
    test_denominator_of_a_product_is_bracketed
    test_latex_uses_braces_for_radicals
    test_derivative_of_a_product_is_normalised
    test_polynomial_collects_like_terms_and_solves_exactly
    test_non_polynomial_is_reported_as_such
    test_fraction_bar_is_a_bar_model_not_a_flattened_line
    test_fraction_bars_recompute_when_the_numerator_moves
    test_system_second_line_is_normalised_too
    test_scene_kinds_supply_a_scene_and_curve_kinds_supply_a_series
    test_every_concept_produces_a_well_formed_figure
    test_every_parameter_extreme_still_builds
    test_no_concept_falls_back_to_the_generic_probe
    test_template_selection_uses_whole_words
    test_template_choice_is_deterministic
    test_unmatched_concept_still_gets_an_honest_generic_figure
    test_number_line_explains_direction_without_malformed_signs
    test_domain_figure_reports_the_excluded_region
    test_vertical_line_test_marks_both_branches
    test_every_declared_parameter_actually_moves_the_figure
    test_folding_parameters_keeps_the_exact_analysis
    test_signed_second_terms_render_as_subtraction
    test_domain_figure_renders_signed_shifts
    test_simulation_sampling_is_bounded
    test_quadratic_readouts_agree_with_the_curve

**`test_media_pipeline.py`** (42)
    test_licence_codes_classify_correctly
    test_an_unknown_licence_is_refused_rather_than_assumed_permissive
    test_non_commercial_and_no_derivatives_cannot_be_stored_locally
    test_redistributable_licences_are_storable
    test_nc_and_nd_classes_are_excluded_from_local_storage
    test_non_commercial_sources_are_withheld_on_a_paid_instance
    test_the_commercial_gate_is_enforced_not_merely_documented
    test_stored_cards_are_re_evaluated_against_the_live_rights_position
    test_a_card_whose_policy_does_not_resolve_is_withheld_not_cleared
    test_filter_rejects_each_bad_candidate_with_a_stated_reason
    test_an_unclassified_licence_is_rejected_before_any_size_check
    test_lexical_overlap_is_a_recall_measure
    test_image_search_reports_a_refusal_when_media_is_disabled
    test_acquire_downloads_nothing_when_media_is_disabled
    test_attribution_is_built_when_the_provider_supplies_only_pieces
    test_openverse_attribution_string_is_preserved_verbatim
    test_video_embedding_fails_closed_when_it_cannot_be_verified
    test_video_embedding_is_used_only_after_a_positive_verification
    test_no_video_is_ever_downloadable_or_transcribable
    test_extraction_is_a_named_refusal_not_a_missing_feature
    test_a_revocation_wins_over_every_other_branch
    test_video_search_quota_is_stated_as_a_decision_input
    test_khan_required_notice_is_carried_as_data
    test_an_invented_slug_is_withheld_not_embedded
    test_a_verified_slug_produces_a_real_embed_url
    test_every_simulation_card_is_marked_unobservable
    test_gizmos_is_never_embedded
    test_the_declared_provider_order_is_reconciled_against_the_pack
    test_phet_is_withheld_on_a_paid_instance
    test_an_uncovered_concept_returns_a_gap_not_the_least_bad_match
    test_the_pack_publishes_its_own_gaps
    test_presentation_uses_one_narrator_and_audio_led_timing
    test_presentation_timeline_is_monotonic
    test_presentation_emits_an_editable_script_and_a_subtitle_track
    test_the_exported_deck_is_self_contained
    test_presentation_blocks_carry_a_printed_slide_per_slide
    test_presentation_visuals_are_never_model_generated
    test_the_new_tools_are_registered_with_the_right_posture
    test_find_image_reports_a_refusal_rather_than_raising
    test_find_simulation_is_unobservable_through_the_tool
    test_generated_kinds_include_every_new_capability
    test_media_pipeline_describe_states_its_guarantees

**`test_memory.py`** (17)
    test_retrievability_is_one_now_and_decreases_with_time
    test_retrievability_matches_fsrs_semantics_r_at_stability_is_point_nine
    test_recall_probability_none_for_unseen_item
    test_published_default_weights_are_used_verbatim
    test_stability_increases_on_success_and_decreases_on_lapse
    test_desirable_difficulty_lower_retrievability_larger_gain
    test_difficulty_moves_with_performance_and_mean_reverts
    test_due_time_schedules_at_desired_retention
    test_legacy_state_is_adopted_not_discarded
    test_invalid_rating_rejected
    test_learning_update_uses_fsrs_by_default_and_keeps_mastery_contract
    test_learning_fallback_leitner_path_still_works
    test_deterministic_seed_property_same_inputs_same_outputs
    test_implicit_credit_bumps_stability_without_touching_the_review_clock
    test_propagate_implicit_credit_walks_prerequisites_with_distance_decay
    test_propagate_implicit_credit_skips_lapses_and_disabled_model
    test_implicit_credit_fires_through_the_api

**`test_metering.py`** (2)
    test_offline_turn_is_recorded_as_a_fallback_with_no_tokens
    test_provider_token_counts_reach_the_ledger

**`test_ml_training.py`** (10)
    test_split_by_students_is_disjoint_and_total
    test_split_is_seed_deterministic
    test_auc_recovers_perfect_and_random_rankings
    test_bkt_em_improves_the_likelihood_on_its_own_data
    test_trained_model_beats_chance_on_synthetic_data_with_real_learning_curves
    test_evaluation_predictions_use_earlier_responses_only
    test_bkt_model_cold_start_uses_fitted_prior
    test_csv_loader_roundtrip_and_drops_bad_rows
    test_dataset_license_table_is_complete_and_non_commercial
    test_run_result_carries_the_research_only_banner

**`test_modality.py`** (14)
    test_every_channel_is_reachable_and_the_choice_is_deterministic
    test_a_novice_on_short_material_gets_narration_when_no_interactive_exists
    test_a_novice_with_a_figure_available_gets_the_guided_interactive
    test_an_expert_gets_static_text_with_a_problem_first
    test_long_material_forces_text_even_for_a_novice
    test_frustration_changes_the_frame_to_a_diagram
    test_a_long_session_prefers_a_short_static_segment
    test_the_router_says_a_learning_style_is_not_an_input
    test_transience_and_interactive_availability_are_explicit_inputs
    test_decision_modality_defaults_to_none
    test_plan_attaches_a_routed_representation_and_stores_the_channel
    test_status_reports_the_router_and_the_conduct_rules
    test_the_tutor_and_the_harness_share_one_conduct_source
    test_the_system_prompt_carries_the_conduct_block_and_stays_transparent

**`test_multisubject.py`** (25)
    test_every_declared_course_is_real
    test_subject_kind_decides_the_symbolic_engine
    test_concept_ids_do_not_collide_across_courses
    test_course_for_node_resolves_every_concept
    test_non_mathematics_figure_is_a_concept_map_not_a_quadratic
    test_mathematics_figure_is_still_symbolic
    test_curriculum_is_scoped_to_the_enrolled_course
    test_lesson_and_question_are_served_for_a_generated_course
    test_generated_items_are_gradeable_through_the_real_attempt_path
    test_a_concept_from_another_course_is_refused
    test_projects_materialise_only_for_the_enrolled_course
    test_recommendation_never_crosses_courses
    test_graph_endpoints_report_the_enrolled_course
    test_switching_course_switches_the_whole_view
    test_unknown_course_is_rejected_and_does_not_take_the_server_down
    test_course_catalogue_lists_every_course_with_its_size
    test_tutor_answers_for_every_course
    test_harness_plan_and_generate_work_for_every_course
    test_harness_memory_is_scoped_to_the_learner
    test_every_course_has_four_questions_per_concept
    test_generated_items_ask_about_concepts_not_the_course
    test_authored_mathematics_content_is_unchanged_by_the_generated_layer
    test_every_course_offers_a_citable_reference
    test_reference_links_are_subject_appropriate
    test_tutor_cites_a_real_reference_for_every_course

**`test_openstax_textbook.py`** (18)
    test_openstax_licence_strings_classify_fail_closed
    test_audited_policy_is_cc_by_and_registered
    test_book_policy_from_live_api_meta_cc_by
    test_book_policy_for_nc_2e_is_link_only_and_refused_at_gate
    test_book_policy_refuses_unaudited_slug
    test_book_policy_refuses_licence_drift
    test_toc_comes_from_real_index_fixture
    test_section_fetch_extracts_real_text_and_provenance
    test_ingest_stores_text_with_full_provenance_for_cc_by_book
    test_ingest_refuses_nc_book_and_never_requests_section_text
    test_ingest_refuses_unaudited_book
    test_ingest_unavailable_on_network_failure
    test_grounding_ready_card_carries_quote_and_citation
    test_grounding_withholds_without_inventing_text
    test_grounding_returns_empty_for_unmapped_concept_or_empty_store
    test_describe_reports_store_state
    test_tool_result_redacts_verbatim_quote_but_lesson_keeps_it
    test_redaction_is_lossless_outside_marked_blocks

**`test_operator_role.py`** (4)
    test_a_local_instance_promotes_its_only_learner_to_teacher
    test_production_never_promotes_anybody
    test_a_local_instance_leaves_an_existing_teacher_alone
    test_the_first_account_on_a_local_instance_registers_as_teacher

**`test_packaging_manifest.py`** (19)
    test_info_plist_declares_every_permission_the_app_requests
    test_info_plist_keeps_the_keys_macos_and_gatekeeper_expect
    test_usage_descriptions_are_specific_rather_than_placeholders
    test_distribution_notice_never_claims_a_signature_it_does_not_have
    test_every_declared_runtime_requirement_is_installed_here
    test_the_comparison_reports_missing_and_mismatched_separately
    test_an_exclusion_that_no_longer_matches_a_declaration_is_refused
    test_a_missing_required_package_stops_the_build
    test_the_legal_documents_are_declared_as_bundle_data
    test_the_pack_data_directories_are_still_declared
    test_every_bundle_exclusion_is_declared_and_explained
    test_the_resource_bundle_name_follows_the_package_manifest
    test_a_build_without_the_resource_bundle_is_refused
    test_artwork_is_never_loaded_through_swiftpms_generated_accessor
    test_the_search_provider_the_app_resolves_is_declared_and_installed
    test_a_build_environment_without_a_search_provider_is_refused
    test_the_archive_check_covers_a_provider_that_never_landed
    test_a_backend_frozen_from_different_sources_is_refused
    test_matching_sources_and_a_missing_record_both_pass

**`test_planner.py`** (24)
    test_pace_is_arithmetic_from_the_stated_budget
    test_pace_has_a_floor_and_never_divides_by_zero
    test_textbook_pace_slows_or_advances_from_course_performance_without_changing_budget
    test_textbook_pace_does_not_react_to_insufficient_or_middle_band_evidence
    test_live_study_plan_uses_performance_adjusted_textbook_pace
    test_a_fresh_learner_is_never_told_they_have_a_gap
    test_an_unmeasured_prerequisite_does_not_block_its_dependants
    test_a_measured_weak_prerequisite_does_block_its_dependants
    test_a_weak_leaf_is_a_diagnostic_gap_not_a_blocker
    test_secure_requires_evidence_not_only_a_high_estimate
    test_due_review_outranks_everything_else
    test_the_queue_is_never_empty_for_a_course_with_content
    test_the_queue_is_deterministic
    test_the_queue_opens_on_a_load_bearing_concept
    test_a_prerequisite_is_never_scheduled_after_its_dependant
    test_progress_counts_what_the_course_offers
    test_today_fits_the_stated_budget
    test_mastered_concepts_leave_the_queue_and_move_progress
    test_weeks_remaining_is_a_projection_with_its_basis_stated
    test_the_plan_states_what_it_is_not
    test_the_plan_names_an_empty_goal_rather_than_inventing_one
    test_milestones_cover_every_unit_that_has_content
    test_coverage_gaps_are_reported_not_scheduled
    test_a_lesson_id_resolves_to_the_node_it_teaches

**`test_playground.py`** (43)
    test_the_playground_ships_at_least_twenty_games
    test_the_bundled_games_span_several_subjects
    test_no_bundled_game_is_withheld
    test_every_game_names_a_registered_archetype
    test_every_game_declares_an_objective_and_a_prompt
    test_archetype_ids_are_unique_and_registration_is_guarded
    test_every_bundled_game_renders_a_page_the_store_accepts
    test_a_page_is_deterministic_for_one_spec
    test_no_page_can_load_anything_from_the_network
    test_no_page_uses_dynamic_code_evaluation
    test_every_page_carries_the_series_convention_and_the_bridge
    test_a_scored_game_offers_a_way_to_commit_an_answer
    test_no_page_calls_a_runtime_helper_that_does_not_exist
    test_every_game_survives_a_headless_click_and_drag
    test_validation_names_the_field_and_the_bound
    test_validation_refuses_a_value_outside_a_declared_vocabulary
    test_validation_refuses_a_field_the_schema_does_not_declare
    test_an_invalid_game_is_withheld_with_its_reason
    test_an_unknown_archetype_is_withheld_rather_than_dropped
    test_compose_stores_a_game_and_reuses_it_for_the_same_revision
    test_compose_refuses_a_spec_that_does_not_match_the_schema
    test_instantiate_is_idempotent_and_serves_the_same_revision
    test_draft_without_a_model_stores_nothing_and_says_so
    test_draft_refuses_an_unknown_archetype_before_asking_a_model
    test_attribution_prefers_an_explicit_concept_id
    test_attribution_refuses_a_game_whose_concept_is_not_in_the_course
    test_attribution_matches_an_exact_title
    test_a_run_moves_mastery_and_records_the_before_and_after
    test_an_unattributed_run_is_recorded_but_does_not_move_mastery
    test_the_playground_router_is_declared_to_the_packager
    test_the_gallery_route_serves_the_catalogue
    test_the_archetype_route_publishes_the_schemas
    test_a_game_page_is_served_as_html
    test_the_playground_needs_a_token
    test_an_unknown_game_is_a_404
    test_an_active_exam_blocks_every_play_surface
    test_a_refused_outcome_writes_no_run
    test_an_active_exam_leaves_listing_and_reading_alone
    test_an_exam_that_is_over_does_not_block
    test_every_archetype_declares_a_known_commit_state
    test_the_commit_state_is_published_to_the_api
    test_registration_refuses_an_unknown_commit_state
    test_registration_refuses_completion_commit_on_an_unscored_sandbox

**`test_playground_attribution.py`** (9)
    test_the_specs_this_file_uses_are_valid
    test_the_two_specs_really_do_differ
    test_recomposing_an_unchanged_spec_reuses_the_stored_artifact
    test_the_hash_ignores_key_order
    test_changing_the_spec_forces_a_new_revision
    test_a_page_from_spec_a_is_never_served_for_spec_b
    test_the_stored_metadata_records_the_spec_that_produced_it
    test_the_same_spec_under_a_different_slug_is_a_different_artifact
    test_a_mutation_of_a_stored_spec_is_detected

**`test_playground_correctness.py`** (2)
    test_every_case_scores_a_correct_answer_correct_and_a_wrong_answer_wrong
    test_the_gate_is_not_vacuous

**`test_playground_gallery.py`** (23)
    test_the_gallery_page_exists_where_the_tests_look_for_it
    test_the_source_check_gates_every_message_before_anything_else
    test_the_readout_branch_exits_before_the_outcome_post
    test_the_outcome_post_is_gated_on_the_exact_message_type
    test_the_outcome_payload_is_validated_before_it_is_forwarded
    test_the_sequence_watermark_is_checked_before_the_post
    test_the_gallery_chooses_the_game_itself_not_the_frame
    test_the_watermark_is_reset_when_a_new_page_is_injected
    test_a_readout_never_reaches_the_server
    test_a_malformed_readout_is_still_silent
    test_one_outcome_posts_exactly_one_run
    test_a_redelivered_outcome_posts_exactly_one_run
    test_a_second_commit_in_the_same_game_is_still_recorded
    test_a_late_duplicate_after_a_second_commit_is_ignored
    test_the_watermark_resets_when_a_new_page_loads
    test_an_outcome_from_another_source_is_ignored
    test_a_malformed_outcome_is_dropped_not_forwarded
    test_an_outcome_without_a_sequence_number_is_still_recorded
    test_a_readout_shaped_payload_is_refused_and_writes_no_run
    test_an_outcome_records_exactly_one_run
    test_the_route_records_every_commit_it_is_given
    test_the_route_refuses_a_malformed_outcome
    test_the_route_coerces_a_truthy_string_for_correct

**`test_playground_guided.py`** (6)
    test_a_complete_guided_run_is_recorded_and_moves_mastery
    test_a_run_that_skipped_the_explanation_is_refused_before_anything_is_written
    test_a_two_word_explanation_does_not_count_as_explaining
    test_the_guided_credit_overrides_a_self_reported_correct_flag
    test_a_run_without_the_guided_block_still_records_as_before
    test_the_stored_detail_carries_the_scored_cycle_for_audit

**`test_playground_pipeline.py`** (13)
    test_the_spec_this_file_tests_against_is_actually_valid
    test_draft_stores_a_valid_spec_the_model_returns
    test_draft_feeds_the_validators_complaint_back_to_the_model
    test_the_retry_conversation_grows_instead_of_being_replaced
    test_draft_stores_nothing_when_the_model_never_produces_a_valid_spec
    test_a_rejected_spec_does_not_store_then_a_valid_one_does
    test_draft_reports_a_non_object_return_instead_of_crashing
    test_a_non_object_return_is_retried_before_giving_up
    test_the_model_is_asked_once_when_the_first_answer_is_valid
    test_the_model_is_asked_exactly_the_budget_when_it_always_fails
    test_the_budget_constant_is_two_and_is_what_the_code_uses
    test_a_model_authored_spec_cannot_break_out_of_the_script_block
    test_the_injected_page_script_still_parses

**`test_provider.py`** (5)
    test_reasoning_off_tells_the_endpoint_not_to_spend_the_budget_on_its_trace
    test_the_default_leaves_the_reasoning_budget_to_the_model
    test_truncation_is_visible_on_a_reply_that_still_has_text
    test_a_reply_that_spent_its_whole_budget_on_reasoning_still_reports_the_reason
    test_a_large_artefact_can_raise_the_reply_guard_for_one_call

**`test_psychometrics.py`** (27)
    test_probability_is_monotonic_in_ability_and_half_at_difficulty
    test_discrimination_changes_steepness_not_the_midpoint
    test_a_guessing_floor_raises_the_low_ability_asymptote
    test_extreme_values_do_not_produce_nan
    test_information_peaks_at_the_difficulty
    test_a_harder_item_carries_its_information_higher_up_the_scale
    test_no_responses_returns_the_prior_and_says_so
    test_correct_responses_raise_the_estimate_and_shrink_its_error
    test_wrong_responses_lower_the_estimate
    test_an_all_correct_run_flags_the_boundary_rather_than_claiming_precision
    test_uncalibrated_rows_are_skipped_rather_than_defaulted_to_zero
    test_theta_renders_as_a_readable_success_rate
    test_measurement_picks_maximum_information
    test_practice_picks_a_high_success_item_not_the_most_informative_one
    test_the_two_purposes_disagree_and_that_is_the_point
    test_exposure_control_skips_an_over_exposed_item
    test_when_every_item_is_over_the_cap_the_least_exposed_is_returned_and_flagged
    test_excluded_items_are_never_selected
    test_an_uncalibrated_candidate_is_reported_not_assumed
    test_an_empty_bank_returns_no_item_rather_than_a_default
    test_an_unknown_purpose_is_refused
    test_the_selection_says_why_and_reports_an_expected_error
    test_a_thin_item_is_cold_start_and_its_difficulty_is_the_prior
    test_a_well_observed_item_is_calibrated_and_its_difficulty_orders_correctly
    test_a_fifty_percent_item_sits_at_zero_difficulty
    test_calibration_counts_are_reported_with_their_denominator
    test_status_reports_the_model_and_what_it_does_not_do

**`test_release_surface.py`** (12)
    test_diagnostics_requires_a_token
    test_diagnostics_reports_configuration_not_the_learner
    test_diagnostics_redacts_secret_shaped_log_lines
    test_release_kit_refuses_a_template_legal_build
    test_release_kit_refuses_a_relabelled_build
    test_release_kit_refuses_a_failed_smoke
    test_release_kit_refuses_an_artifact_changed_after_packaging
    test_release_kit_accepts_a_clean_record
    test_install_script_is_valid_posix_sh
    test_install_script_refuses_a_path_it_did_not_install
    test_cask_points_at_the_versioned_dmg
    test_release_directory_explains_itself

**`test_resource_paths.py`** (11)
    test_the_resolver_finds_each_directory_inside_a_frozen_bundle
    test_a_frozen_marker_without_meipass_falls_back_to_the_source_tree
    test_a_false_frozen_flag_is_not_treated_as_frozen
    test_the_resolver_still_finds_the_source_tree
    test_every_module_resolves_its_directory_through_the_resolver
    test_the_directories_the_modules_read_are_populated
    test_the_web_directory_is_declared_as_bundle_data
    test_the_owned_model_package_loads_from_bytecode_only
    test_the_loader_still_prefers_the_source_file_when_both_are_present
    test_the_loader_names_both_initialiser_spellings
    test_the_loader_refuses_an_empty_model_directory_with_a_clear_message

**`test_rewards.py`** (21)
    test_a_learner_with_no_history_is_not_told_anything
    test_one_day_counts_quietly
    test_five_days_is_a_milestone_and_not_also_a_daily_notice
    test_a_run_that_ended_yesterday_is_still_current
    test_the_same_achievement_always_produces_the_same_id
    test_five_correct_practice_answers_are_a_banner_and_ten_are_a_moment
    test_an_assessment_cannot_earn_a_question_strike
    test_a_wrong_answer_ends_the_run
    test_crossing_into_full_mastery_announces_once_not_twice
    test_mastery_below_the_first_threshold_says_nothing
    test_junk_in_a_concept_row_does_not_raise
    test_badges_come_from_the_rule_module
    test_the_heaviest_ceremony_is_shown_first
    test_there_is_no_negative_event_kind
    test_every_kind_has_a_complete_presentation
    test_the_route_requires_a_token
    test_a_new_learner_gets_an_empty_list_rather_than_an_error
    test_five_stored_days_produce_the_milestone_through_the_route
    test_a_review_item_counts_as_practice_but_an_exam_does_not
    test_one_learner_never_sees_another_learners_events
    test_the_route_cannot_be_talked_into_an_event

**`test_runtime_data_packs.py`** (5)
    test_every_pack_directory_exists_and_holds_json
    test_the_packaging_script_lists_every_runtime_pack_directory
    test_knowledge_graph_is_populated_for_the_default_course
    test_media_and_simulation_routes_serve_pack_content
    test_every_pack_file_parses_as_json

**`test_schema_equivalence.py`** (2)
    test_upgrading_the_previous_version_matches_a_fresh_schema
    test_upgrading_is_idempotent

**`test_security_contract.py`** (4)
    test_default_access_ttl_sites_agree
    test_from_env_default_matches_the_dataclass_default
    test_issued_access_token_expires_at_the_configured_ttl
    test_refresh_token_is_the_long_half

**`test_shipped_image_pack.py`** (10)
    test_an_absent_pack_is_empty_rather_than_an_error
    test_the_shipped_picture_is_installed_into_the_instance_cache
    test_installing_the_same_picture_twice_adds_one_manifest_line
    test_a_row_whose_bytes_are_missing_is_not_a_picture
    test_the_installed_picture_is_served_like_a_downloaded_one
    test_the_deck_uses_the_shipped_picture_with_the_network_off
    test_a_lesson_the_pack_does_not_cover_still_reports_why
    test_the_narrated_deck_carries_the_shipped_photograph
    test_the_shared_payload_names_the_attribution_under_both_keys
    test_the_pack_is_keyed_by_lesson_id_so_the_deck_can_find_it

**`test_sims_check.py`** (8)
    test_an_empty_artifact_is_not_checked
    test_a_missing_browser_reports_unverified_never_a_pass
    test_a_working_artifact_passes
    test_a_non_finite_value_is_caught_after_the_page_is_driven
    test_a_throwing_script_is_caught
    test_check_simulation_is_registered_and_offered_to_the_ta
    test_the_tool_says_unverified_rather_than_broken_without_a_browser
    test_the_tool_reports_an_unknown_artifact

**`test_socratic.py`** (8)
    test_the_ladder_escalates_one_rung_per_failed_cycle
    test_the_answer_is_not_revealed_before_two_failed_cycles
    test_every_rung_is_on_the_ladder_and_states_its_position
    test_an_explicit_request_for_a_worked_explanation_is_honoured_at_once
    test_a_learner_who_has_explained_is_asked_to_go_deeper_not_corrected
    test_a_climbing_latency_trend_narrows_the_space
    test_the_step_is_deterministic_and_the_guard_agrees_with_the_policy
    test_status_reports_the_dialogue_ladder

**`test_source_extension.py`** (21)
    test_a_search_returns_licence_cleared_candidates_with_what_may_be_done
    test_a_link_only_reference_is_offered_and_never_buildable
    test_building_from_a_candidate_that_is_not_wikipedia_is_refused
    test_a_provider_failure_degrades_to_a_note_and_not_a_fabrication
    test_search_holds_slots_for_the_learners_own_material
    test_a_query_with_no_buildable_source_is_refused_with_what_was_offered
    test_supplying_nothing_is_refused_with_the_ways_to_supply_one
    test_an_expired_candidate_is_a_refusal_rather_than_a_crash
    test_a_course_built_from_wikipedia_is_stamped_with_its_real_rights
    test_a_course_from_pasted_text_is_stamped_the_learners_own
    test_wiki_headings_are_reconciled_with_the_extractors_dialect
    test_an_unreadable_article_is_a_refusal_not_a_crash
    test_the_level_comes_from_the_learners_own_goal
    test_the_estimate_uses_the_planners_own_arithmetic
    test_the_level_the_goal_implies_is_on_the_plan_too
    test_a_goal_that_names_concepts_matches_them
    test_search_route_returns_candidates_with_their_rights
    test_auto_route_builds_personalises_enrols_and_teaches
    test_auto_route_can_build_a_plan_without_saving_it
    test_auto_route_refuses_a_link_only_candidate_with_a_reason
    test_auto_route_refuses_a_source_too_thin_for_a_course

**`test_speech_outcomes.py`** (12)
    test_a_render_that_fails_says_so_instead_of_staying_pending
    test_a_render_that_lands_is_ready_and_state_agrees
    test_an_unknown_digest_is_not_reported_as_a_failure
    test_a_failure_is_never_cached_as_a_clip
    test_warm_up_is_skipped_when_voice_output_is_off
    test_warm_up_touches_the_engine_before_a_learner_does
    test_the_digest_follows_the_engine_that_will_speak
    test_a_reply_is_split_into_clips_short_enough_to_be_heard_soon
    test_a_split_never_lands_mid_word
    test_an_empty_reply_has_nothing_to_speak
    test_the_sequence_renders_every_clip_and_names_the_first
    test_a_sequence_with_voice_output_off_says_so_once

**`test_stage_whiteboard.py`** (10)
    test_board_creates_on_first_use
    test_clean_op_rejects_bad_shapes
    test_student_ink_layer_is_forced
    test_board_layer_ops_round_trip
    test_interrupts_raise_and_clear
    test_whiteboard_tools_refuse_learners
    test_whiteboard_write_and_read
    test_place_image_refused_when_pipeline_returns_nothing
    test_ta_dispatch_requires_runner
    test_ta_pool_cap_and_results

**`test_stream.py`** (17)
    test_off_means_off_and_says_which_switch
    test_the_window_is_the_frame_the_app_reported
    test_a_region_that_was_never_reported_is_not_the_whole_screen
    test_a_missing_screen_recording_permission_is_a_sentence
    test_a_sleeping_display_is_not_blamed_on_screen_recording
    test_a_locked_screen_is_not_blamed_on_screen_recording
    test_status_reports_the_last_capture_instead_of_taking_another
    test_status_carries_the_reason_a_capture_failed
    test_input_is_refused_for_a_learner_and_reports_a_missing_grant
    test_an_unknown_event_kind_is_refused_by_name
    test_a_reported_window_with_no_size_is_refused
    test_the_region_is_clamped_rather_than_trusted
    test_the_event_budget_bounds_a_held_key
    test_the_switch_can_be_thrown_without_relaunching_the_app
    test_the_switch_can_be_turned_off_again
    test_a_hosted_instance_keeps_the_switch_with_its_operator
    test_a_learner_cannot_throw_the_switch

**`test_supervision.py`** (32)
    test_a_concept_with_no_attempts_is_not_treated_as_a_weak_one
    test_a_learner_who_is_present_and_on_pace_is_left_alone
    test_an_empty_chair_gets_a_break_offer_while_breaks_remain
    test_with_breaks_used_up_the_move_is_a_question_not_a_nag
    test_a_break_the_learner_asked_for_is_not_an_absence
    test_ninety_seconds_of_silence_is_a_nudge_not_an_accusation
    test_being_behind_the_plan_while_still_scrolling_is_not_an_emergency
    test_being_behind_and_still_earns_the_next_step_only
    test_thin_mastery_is_taught_rather_than_quizzed
    test_secure_mastery_earns_a_why_question
    test_progress_is_not_judged_before_the_session_has_any_shape
    test_an_impossibly_fast_right_answer_asks_for_a_variant
    test_a_right_answer_without_reasoning_asks_for_the_reasoning
    test_solving_the_original_but_not_the_variant_is_fragile_knowledge
    test_no_check_is_run_during_an_assessment
    test_a_normal_answer_raises_nothing
    test_secure_mastery_and_a_holding_record_move_the_item_up
    test_thin_mastery_moves_the_item_down
    test_fast_and_wrong_together_moves_down_even_at_middling_mastery
    test_no_record_means_hold
    test_the_supervisor_never_deducts_flags_or_watches
    test_participation_is_reported_as_a_reading_not_a_score
    test_the_same_interruption_is_not_repeated_inside_the_cooldown
    test_a_streak_that_ends_yesterday_is_still_current
    test_a_streak_that_ends_two_days_ago_is_over
    test_the_longest_run_survives_a_break
    test_five_days_in_a_row_is_announced_once
    test_a_question_streak_counts_practice_and_ignores_assessments
    test_five_practice_answers_in_a_row_is_announced
    test_a_milestone_announces_on_the_crossing_not_on_every_attempt
    test_badges_name_the_condition_that_earned_them
    test_the_certificate_needs_the_tests_and_the_assignments

**`test_ta_media_feed.py`** (18)
    test_a_search_result_keeps_its_url_and_licence
    test_a_search_result_without_a_url_is_not_a_card
    test_a_downloaded_asset_prefers_its_local_copy
    test_a_generated_illustration_says_so_instead_of_borrowing_a_licence
    test_a_generated_path_without_a_provider_is_not_claimed
    test_a_failed_tool_result_never_becomes_a_card
    test_the_same_image_twice_is_one_card
    test_the_feed_is_capped_at_eight_images
    test_the_three_shapes_together_keep_their_call_order
    test_generated_bytes_are_indexed_with_a_generated_licence
    test_a_generated_image_gets_a_card_not_just_a_media_row
    test_a_downloaded_image_card_links_its_source_page
    test_a_search_card_carries_the_sha_when_the_instance_has_the_bytes
    test_a_deck_is_an_artifact_card
    test_the_card_list_ignores_failed_turns
    test_a_deck_revised_in_the_same_turn_is_one_card
    test_two_different_decks_stay_two_cards
    test_the_same_picture_twice_is_one_card

**`test_ta_sweep.py`** (8)
    test_a_teacher_gets_an_asset_review_for_the_concept
    test_the_figure_returned_is_the_one_that_was_reviewed
    test_a_learner_cannot_run_the_sweep
    test_an_unknown_concept_is_not_fabricated
    test_a_client_cannot_state_its_own_mastery
    test_signals_turn_the_sweep_into_a_decision
    test_a_working_learner_is_left_alone
    test_the_sweep_does_not_write

**`test_teacher_clone.py`** (6)
    test_normalize_profile_requires_verbatim_evidence
    test_invalid_model_output_uses_bounded_offline_signals
    test_profile_limits_and_consent_gate
    test_generated_course_map_lesson_is_taught_with_its_limits_named
    test_concept_with_no_lesson_gets_orientation_only
    test_transcript_length_is_checked

**`test_teacher_core.py`** (58)
    test_the_move_vocabulary_matches_the_loop
    test_a_concept_with_no_evidence_is_oriented_before_it_is_taught
    test_a_concept_that_satisfies_the_completion_gate_stops_being_taught
    test_recognition_alone_does_not_close_the_gate
    test_prerequisite_debt_stops_forward_teaching_and_repairs_instead
    test_overload_chooses_rest_over_another_explanation
    test_a_session_past_its_budget_stops_adding_material
    test_a_procedural_error_reaches_the_move_that_corrects_a_process
    test_every_candidate_carries_a_reason_and_is_clamped
    test_selection_is_deterministic_and_independent_of_declaration_order
    test_a_move_the_profile_does_not_declare_can_never_win
    test_a_learner_specific_bias_is_bounded_and_cannot_outvote_the_evidence
    test_a_review_is_due_at_the_desired_retention_point
    test_a_concept_never_reviewed_is_not_due_but_enters_as_new_material
    test_a_scheduler_written_due_at_is_honoured
    test_due_concepts_are_served_weakest_memory_first
    test_the_schedule_interleaves_new_material_rather_than_front_loading_it
    test_the_schedule_states_its_own_reasoning
    test_planning_retrieval_never_asks_for_more_than_the_session_allows
    test_the_rendered_moves_are_exactly_the_profile_moves
    test_editing_the_profile_edits_the_prompt
    test_the_retrieval_section_states_the_configured_retention
    test_the_retrieval_section_reports_the_actual_calendar_when_given_one
    test_the_modalities_section_names_the_ceiling_not_only_the_defaults
    test_the_persona_section_is_visibly_subordinate_to_the_evidence
    test_an_unknown_profile_section_is_rejected_rather_than_ignored
    test_a_probability_typo_is_clamped_rather_than_disabling_a_rule
    test_an_impossible_profile_is_refused
    test_a_profile_round_trips_through_plain_data
    test_non_mathematics_routes_to_a_concept_map_not_a_function_plot
    test_a_procedural_error_routes_to_a_simulation
    test_a_conceptual_error_draws_on_the_board_when_the_caller_has_one
    test_a_conceptual_error_without_a_board_falls_back_to_the_figure
    test_an_overloaded_learner_is_not_given_a_new_representation
    test_modality_changes_as_performance_moves_from_fast_wrong_to_steady_progress
    test_a_spatial_concept_at_consolidation_asks_the_learner_to_draw
    test_spoken_output_adds_audio_and_keeps_the_text
    test_a_channel_switched_off_on_this_instance_is_never_chosen
    test_an_image_channel_without_a_pipeline_degrades_to_text
    test_an_exact_repeat_of_the_previous_channel_is_varied_once
    test_the_router_only_names_channels_the_profile_catalogue_knows
    test_every_tool_the_teaching_core_calls_actually_exists
    test_a_placeholder_resolves_at_the_call_site_and_stays_visible_when_it_cannot
    test_the_loop_completes_elicit_teach_practice_consolidate
    test_the_loop_can_draw_on_the_board
    test_the_loop_can_run_a_simulation
    test_the_loop_gives_practice_and_checks_understanding
    test_a_learner_who_cannot_retrieve_yet_is_not_asked_to
    test_the_wrap_can_be_switched_off_in_configuration
    test_the_transfer_task_appears_only_when_the_gate_still_wants_it
    test_rest_is_terminal_and_appends_nothing_after_it
    test_a_session_over_budget_gets_the_move_and_an_exit_not_a_full_loop
    test_the_loop_phases_are_drawn_from_one_declared_order
    test_the_plan_is_serialisable_for_the_transparency_panel
    test_a_plan_carries_the_retrieval_calendar_when_one_was_built
    test_the_router_never_reads_a_learning_style
    test_every_channel_the_profile_allows_is_reachable_by_some_rule
    test_the_ceiling_is_enforced_on_every_rule_not_only_the_default_route

**`test_teacher_wiring.py`** (7)
    test_the_policy_decision_is_in_the_prompt_the_provider_receives
    test_the_decision_follows_the_learners_stored_state
    test_a_mastered_learner_is_not_sent_back_to_the_introduction
    test_the_plan_block_lists_the_phases_in_order
    test_no_plan_renders_nothing_rather_than_a_placeholder
    test_the_agent_loop_carries_the_decision_to_the_tool_registry
    test_a_failing_plan_does_not_fail_the_turn

**`test_telemetry.py`** (20)
    test_a_click_with_a_control_id_is_accepted
    test_a_blur_needs_no_target
    test_a_click_without_a_target_is_refused
    test_an_unknown_kind_is_refused_by_name
    test_a_target_that_is_prose_is_refused
    test_a_window_title_is_refused
    test_a_text_field_is_refused
    test_a_key_event_names_a_target_and_never_a_key
    test_a_tap_is_not_evidence
    test_the_route_requires_consent
    test_the_route_accepts_a_tap_and_replays_it_once
    test_the_route_refuses_a_window_title
    test_a_tap_cannot_move_mastery
    test_an_external_simulation_open_is_accepted
    test_an_external_simulation_open_cannot_carry_parameters
    test_the_summary_counts_and_does_not_score
    test_one_learner_never_sees_anothers_taps
    test_the_summary_skips_kinds_the_vocabulary_does_not_contain
    test_the_summary_ignores_rows_outside_the_window
    test_other_event_types_are_not_counted

**`test_tutor_voice.py`** (23)
    test_a_label_names_the_action_not_the_tool
    test_every_registered_tool_has_a_readable_label
    test_the_fallback_title_cases_an_unlisted_tool
    test_loop_events_carry_a_label_while_the_tool_runs
    test_the_draw_aloud_protocol_arrives_only_when_a_board_is_in_scope
    test_an_invalid_board_id_gets_no_board_framing
    test_the_protocol_asks_for_drawing_discipline_not_impersonation
    test_a_spoken_turn_asks_the_model_to_write_for_the_ear
    test_a_spoken_turn_carries_a_speech_descriptor_and_renders_it
    test_a_repeated_answer_is_spoken_from_the_cache
    test_a_turn_nobody_asked_to_speak_carries_no_speech
    test_a_turn_with_no_reply_says_nothing
    test_voice_output_switched_off_is_reported_not_faked
    test_the_audio_route_needs_authentication
    test_a_recording_that_does_not_exist_is_a_404
    test_plan_names_every_refusal_reason
    test_media_off_does_not_take_the_tutors_voice_with_it
    test_spoken_text_strips_markdown_for_the_ear
    test_a_long_reply_is_cut_at_a_sentence_boundary_never_mid_word
    test_the_digest_covers_everything_that_changes_the_bytes
    test_the_cache_serves_a_clip_once_and_forgets_it
    test_a_digest_never_reaches_the_filesystem
    test_a_render_failure_is_reported_with_the_engines_own_reason

**`test_tutoring_coverage.py`** (5)
    test_every_requested_course_is_registered
    test_every_requested_course_has_practice_in_every_unit
    test_every_requested_course_concept_has_four_distinct_options
    test_every_requested_course_concept_is_teachable
    test_a_generated_lesson_names_the_thing_it_lacks

**`test_user_scope.py`** (9)
    test_guard_is_installed
    test_unscoped_select_on_user_scoped_table_raises
    test_unscoped_select_without_any_where_raises
    test_user_scoped_predicate_still_works_and_isolates
    test_primary_key_lookup_is_allowed
    test_escape_hatch_runs_and_is_audited
    test_escape_hatch_requires_a_reason
    test_guard_covers_the_whole_user_scoped_surface
    test_live_api_traffic_runs_under_the_guard

**`test_video_curation.py`** (16)
    test_an_on_topic_verified_video_is_curated_and_then_resolves
    test_a_video_about_something_else_is_refused
    test_a_candidate_that_cannot_be_embedded_is_not_curated
    test_a_link_is_accepted_only_when_the_caller_asks_for_one
    test_the_closest_title_wins
    test_curating_twice_writes_one_entry
    test_a_withdrawn_source_cannot_be_curated_back_in
    test_relevance_ignores_the_words_every_lesson_title_has
    test_a_video_that_belongs_to_the_neighbouring_lesson_is_refused
    test_the_neighbour_test_only_refuses_and_never_chooses
    test_a_thin_match_from_an_unfamiliar_source_is_not_shipped
    test_a_trusted_video_that_was_off_topic_does_not_suppress_the_retry
    test_an_equally_on_topic_video_from_a_preferred_source_wins
    test_the_shipped_seed_is_read_when_the_operator_has_not_written_one
    test_an_operator_file_replaces_the_seed_without_losing_it
    test_with_no_seed_and_no_operator_file_the_hand_verified_rows_still_answer

**`test_video_search.py`** (11)
    test_a_verified_candidate_becomes_an_embed_card
    test_an_unverifiable_candidate_keeps_its_link_and_loses_its_embed
    test_the_probes_title_wins_over_the_scraped_one
    test_the_scraped_title_survives_when_the_probe_has_none
    test_media_off_refuses_before_searching
    test_the_results_page_yields_its_rows
    test_a_lecture_a_short_and_a_live_row_are_not_candidates
    test_a_page_without_the_state_blob_is_empty_rather_than_an_error
    test_the_chain_prefers_the_provider_and_falls_back_to_the_serp
    test_both_keyless_paths_failing_is_reported_not_swallowed
    test_inflection_does_not_hide_the_right_video

**`test_video_seed.py`** (4)
    test_the_seed_parses_and_every_row_is_complete
    test_every_row_is_keyed_by_a_lesson_that_exists
    test_a_curated_lesson_resolves_with_the_network_off
    test_the_operator_file_still_wins_over_the_shipped_seed

**`test_vla.py`** (28)
    test_build_label_resolves_to_the_wire_id
    test_a_text_only_model_is_not_treated_as_a_vlm
    test_an_unknown_model_is_blind_by_default
    test_vision_status_refuses_a_text_only_model_with_a_reason
    test_vision_status_names_the_missing_switch_when_offline
    test_a_remote_url_is_refused_because_the_server_would_fetch_it
    test_the_magic_bytes_decide_the_mime_not_the_caller
    test_oversize_and_non_image_bytes_are_refused_by_name
    test_workspace_paths_are_resolved_inside_the_learner_workspace
    test_observe_sends_image_parts_and_reports_a_digest
    test_observe_returns_none_when_the_provider_refuses
    test_observe_never_sends_more_than_the_image_cap
    test_a_tool_that_returns_an_image_gets_it_reinjected_before_the_next_step
    test_a_turn_with_no_images_emits_no_observation_event
    test_look_at_image_attaches_the_picture_when_no_question_is_asked
    test_look_at_image_answers_a_question_in_a_side_call
    test_look_at_image_refuses_without_a_vision_model
    test_monitoring_off_is_a_refusal_that_names_the_switch
    test_idle_time_reads_as_off_task_with_its_evidence
    test_no_attempt_and_little_activity_is_unclear_not_off_task
    test_telemetry_alone_can_call_it_on_task
    test_a_picture_that_contradicts_the_telemetry_is_reported_as_unclear
    test_the_tool_returns_a_move_and_a_privacy_block
    test_the_pptx_twin_is_a_sixteen_by_nine_deck_with_notes_and_a_title_slide
    test_deck_quality_notes_name_the_slide_to_fix
    test_the_capability_matrix_reports_vision_as_implemented
    test_the_vision_probe_reads_the_model_card_not_the_provider_name
    test_harness_status_exposes_the_vla_and_attention_posture

**`test_voice_busy.py`** (3)
    test_two_sentences_never_reach_the_engine_at_once
    test_a_busy_engine_is_retried_after_the_interval_it_names
    test_a_second_refusal_is_reported_rather_than_retried_forever

**`test_voice_model.py`** (5)
    test_a_served_model_is_used_as_configured
    test_an_unserved_model_falls_back_to_an_alias
    test_the_alias_preference_is_stable
    test_an_unreadable_model_list_trusts_the_configuration
    test_the_substitution_is_reported_by_the_probe

**`test_web_routes_contract.py`** (7)
    test_tool_created_artifact_served_with_version_history
    test_post_sims_refused_by_validator_and_stores_nothing
    test_student_cannot_declare_teacher_role_on_change_requests
    test_static_asset_route_never_escapes_the_web_root
    test_sandbox_never_grants_same_origin_and_bridge_is_serve_time_only
    test_luminfest_ready_handshake_exists_in_served_artifacts
    test_parent_checks_event_source_before_handling_luminfest_ready

**`test_whiteboard_unification.py`** (10)
    test_wb_and_board_ids_resolve_to_one_document
    test_tutor_node_is_visible_on_the_learner_canvas_path
    test_move_survives_and_read_reflects_the_new_geometry
    test_non_teacher_is_refused_by_all_four_tools
    test_student_ink_refuses_text_and_accepts_path
    test_place_image_withheld_places_nothing
    test_place_image_places_a_resolvable_cached_node
    test_legacy_shim_presents_the_node_board_and_survives_an_empty_one
    test_read_digest_names_what_is_on_the_board
    test_malformed_id_is_refused_not_created

**`test_whole_use.py`** (1)
    test_a_learner_can_go_from_a_document_to_a_taught_course

_1518 tests across 91 files. Run: `cd backend && python -m pytest -q`._
