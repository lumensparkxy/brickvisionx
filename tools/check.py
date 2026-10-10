"""Explicit check scopes; absent tools never count as successful checks."""
import argparse
import subprocess
import sys
from _paths import ROOT


# Representative routine checks; the no-flag CI/release command still runs every test.
# Keep source/schema, both reconstruction modes, immutable history, cache fences and leases.
QUICK_TESTS = [
    "tests/backend/test_api.py",
    "tests/backend/test_contracts.py",
    "tests/backend/test_source.py",
    "tests/backend/test_engine_delta.py",
    "tests/backend/test_engine_store.py",
    "tests/backend/test_engine_scheduling.py",
    "tests/backend/test_engine_checkpoint_artifacts.py::test_small_sql_checkpoint_preserves_exact_public_json_and_old_revisions",
    "tests/backend/test_engine_checkpoint_artifacts.py::test_inline_legacy_rows_are_read_without_migration",
    "tests/backend/test_engine_checkpoint_artifacts.py::test_reference_and_file_corruption_fail_closed",
    "tests/backend/test_engine_checkpoint_artifacts.py::test_artifact_is_published_before_final_lease_fence_without_replacing_prior_state",
    "tests/backend/test_engine_concurrent_claims.py::test_simultaneous_independent_store_claims_cannot_exceed_two",
    "tests/backend/test_engine_corrections.py::test_mapping_fork_is_immutable_assisted_and_has_frozen_budget",
    "tests/backend/test_engine_corrections.py::test_group_replay_carries_future_members_through_six_dof_attachment",
    "tests/backend/test_engine_spatial.py::test_hidden_physical_piece_still_reserves_its_connector",
    "tests/backend/test_engine_spatial.py::test_detached_group_attaches_rigidly_without_duplicate_physical_ids",
    "tests/backend/test_engine_spatial.py::test_nested_groups_merge_membership_before_the_outer_attachment",
    "tests/backend/test_engine_incremental_diagnostics.py::test_enumeration_reuses_prefix_with_identical_full_reports_and_counts",
    "tests/backend/test_engine_incremental_diagnostics.py::test_nested_group_membership_survives_prefix_reuse",
    "tests/backend/test_engine_verification_cache.py::test_mid_search_mutations_fail_before_any_candidate_is_returned",
    "tests/backend/test_engine_exploration.py::test_poor_fit_unsupported_connection_and_failed_review_continue",
    "tests/backend/test_engine_exploration.py::test_no_renderable_proposal_records_gap_and_continues",
    "tests/backend/test_engine_exploration.py::test_resume_is_idempotent_and_rejects_candidate_and_render_tampering",
    "tests/backend/test_engine_efficiency_repairs.py::test_camera_uncertainty_and_failed_review_preserve_evidence_without_regeneration",
    "tests/backend/test_engine_efficiency_sequence.py::test_valid_unnumbered_attachment_reaches_later_instructions_without_repair",
    "tests/backend/test_engine_alpha.py::test_source_only_overview_is_retained_and_later_batch_builds",
    "tests/backend/test_engine_alpha.py::test_batches_resume_without_repeating_inference_and_keep_uncertain_material",
    "tests/backend/test_engine_alpha.py::test_hard_invalid_proposals_fail",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python-only", action="store_true", help="Only Python tests and schema drift; no UI claim")
    parser.add_argument("--e2e", action="store_true", help="Also run Playwright; no external inference")
    parser.add_argument("--quick", action="store_true",
                        help="Selected routine regression checks; full suite and production build are not run")
    args = parser.parse_args()
    if args.quick and args.e2e:
        parser.error("--quick cannot include --e2e; use the full check for browser/release validation")
    pytest = [sys.executable, "-m", "pytest"]
    if args.quick:
        pytest.extend(QUICK_TESTS)
    commands = [
        pytest,
        [sys.executable, "tools/export_schema.py", "--check"],
    ]
    if not args.python_only:
        commands.append([sys.executable, "-m", "ruff", "check", "apps/api", "tools", "tests/backend"])
        commands.extend([["npm", "run", "typecheck"], ["npm", "test"]] if args.quick else [["npm", "run", "check"]])
    if args.e2e:
        commands.append(["npm", "run", "test:e2e"])
    scope = "python-contracts-only" if args.python_only else "local-software"
    print("CHECK SCOPE:", ("quick-" if args.quick else "") + scope, flush=True)
    if args.quick:
        print("Selected regressions only. Full regression, production build and browser checks are not run.", flush=True)
    for command in commands:
        print("RUN:", " ".join(command), flush=True)
        try:
            result = subprocess.run(command, cwd=ROOT, check=False)
        except FileNotFoundError as error:
            print(f"BLOCKED: {error}")
            return 2
        if result.returncode:
            return result.returncode
    print("Selected checks passed. This does not certify the target model or physical build.")
    if args.quick:
        print("Run tools/check.py without --quick for full CI/release checks.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
