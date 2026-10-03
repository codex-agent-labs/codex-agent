from __future__ import annotations

import hashlib
import fnmatch
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import textwrap
import unittest
import urllib.error
import urllib.request
import zipfile
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch


CI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CI_ROOT))

from impact import (  # noqa: E402
    LANES,
    M8_OWNER_LANES,
    NATIVE_WRAPPER_LANES,
    _legacy_lane_states,
    effective_pathspecs,
    plan,
    validate_legacy_lane_projection,
    write_github_outputs,
)
from evidence import main as evidence_main  # noqa: E402
from receipt import (  # noqa: E402
    aggregate,
    create_receipt,
    parse_files,
    required_lanes,
    safe_extract,
    validate_receipt,
)
from reuse import (  # noqa: E402
    OriginBoundRedirectHandler,
    candidate_artifacts,
    promoted_artifacts,
    restore,
)
from stage import OUTPUTS, archive_tree, copy_matches, restore_production_files, safe_extract_tar, selected_output  # noqa: E402
from validation_reuse import (  # noqa: E402
    M8_FILES,
    M11_FILES,
    discover as discover_validation,
    materialize,
    validate as validate_aggregate_reuse,
)


class RunLaneContractTest(unittest.TestCase):
    def test_runtime_package_callers_forward_original_manifest_version(self):
        sources = ((CI_ROOT.parent / ".github/actions/run-ci-lane/action.yml", 2),
                   (CI_ROOT / "run-lane.sh", 1))
        for path, count in sources:
            source = path.read_text()
            self.assertEqual(count, source.count("-PcodexAgent.runtimeBinaryStage="))
            self.assertEqual(count, source.count("-PcodexAgent.runtimeBinaryVersion="))
            extracts = re.findall(r"python3 -c '([^']*load_canonical_json[^']*)'", source)
            self.assertEqual(count, len(extracts))
            with tempfile.TemporaryDirectory() as temporary:
                manifest = Path(temporary) / "output-manifest.json"
                manifest.write_text('{"productVersion":"0.2.0"}\n')
                for script in extracts:
                    result = subprocess.run([sys.executable, "-B", "-c", script, str(manifest)],
                                            cwd=CI_ROOT.parent, text=True, capture_output=True)
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertEqual("0.2.0\n", result.stdout)
                manifest.write_text('{"productVersion":"0.2.0","productVersion":"0.2.1"}\n')
                result = subprocess.run([sys.executable, "-B", "-c", extracts[0], str(manifest)],
                                        cwd=CI_ROOT.parent, text=True, capture_output=True)
                self.assertNotEqual(0, result.returncode)

    def test_contract_binary_is_finalized_only_from_the_elected_phase_plan(self) -> None:
        action = (CI_ROOT.parent / ".github/actions/run-ci-lane/action.yml").read_text(
            encoding="utf-8"
        )
        self.assertEqual(1, action.count("python3 -m ci.products restore store-phase"))
        self.assertIn(
            "plan=build/ci/product-reuse/phase-plans/contract-contract-binary-common.json",
            action,
        )
        self.assertIn("producer=build/ci/product-reuse/producer.json", action)
        self.assertIn("stage=build/product-stage/contract/contract/binary", action)
        self.assertIn("--phase-plan \"$plan\"", action)
        self.assertIn("--producer \"$producer\"", action)
        self.assertIn("--trust-domain \"$trust_domain\"", action)
        self.assertIn("pull_request) trust_domain=development ;;", action)
        self.assertIn("merge_group) trust_domain=release ;;", action)
        self.assertIn("*) exit 1 ;;", action)
        self.assertIn(
            "name: codex-agent-product-phase-contract-contract-binary-common-${{ inputs.validation-tree }}",
            action,
        )
        self.assertIn("steps.contract-product-shard.outputs.ready == 'true'", action)
        self.assertIn("overwrite: false", action)
        upload = action.split("    - id: contract-product-shard-upload\n", 1)[1].split(
            "\n    - name: Stage the exact Desktop Runtime binary product", 1,
        )[0]
        self.assertIn("continue-on-error: true", upload)
        self.assertEqual(2, action.count("steps.contract-product.outcome"))
        self.assertEqual(1, action.count("steps.contract-product-shard.outcome"))
        self.assertEqual(1, action.count("steps.contract-product-shard-upload.outcome"))

    def test_ci_caller_pins_the_reviewed_product_workflow(self) -> None:
        caller = (CI_ROOT.parent / ".github/workflows/ci.yml").read_text(
            encoding="utf-8"
        )
        references = re.findall(
            r"uses: codex-agent-labs/codex-agent/\.github/workflows/product-validation\.yml@([^\s]+)",
            caller,
        )
        self.assertEqual(1, len(references))
        reviewed = references[0]
        self.assertIn(f"trustedWorkflowSha: {reviewed}", caller)
        self.assertRegex(references[0], r"^[0-9a-f]{40}$")
        self.assertIn("workflow_dispatch:", caller)
        for value in ("baseCommit", "validationCommit", "validationTree"):
            self.assertIn(f"      {value}:\n", caller)
            self.assertIn(f"      {value}: ${{{{ inputs.{value} || '' }}}}", caller)
        for permission in (
            "      actions: read",
            "      contents: read",
            "      deployments: read",
            "      id-token: write",
        ):
            self.assertIn(permission, caller)
        self.assertEqual(1, caller.count("\n  product-validation:\n"))
        self.assertEqual(1, caller.count("\n  merge-gate:\n"))
        gate = caller.split("\n  merge-gate:\n", 1)[1]
        self.assertIn("'SDK custody / complete' ||", gate)
        self.assertIn("'Contract record / complete' ||", gate)
        self.assertIn("'SDK authority / complete' ||", gate)
        self.assertIn("'SDK Maven sidecars / complete' || 'CI / merge-gate'", gate)
        self.assertIn("if: always()", gate)
        self.assertIn("needs: [product-validation, build-logic-diagnostics, sdk-failed-catalog-custody, runtime-toolchain-capture, runtime-phase10-record, contract-phase10-record, sdk-phase10-authority, sdk-phase10-record, sdk-phase10-maven-sidecars]", gate)
        self.assertIn('test "$PRODUCT_VALIDATION_RESULT" = success', gate)
        self.assertIn('test "$SDK_CUSTODY_RESULT" = skipped', gate)
        product_caller = caller.split("\n  product-validation:\n", 1)[1]
        self.assertNotIn("actions/checkout@", product_caller)
        self.assertNotIn("./gradlew", product_caller)

    def test_remote_product_jobs_are_guarded_before_materialization(self) -> None:
        workflow = (CI_ROOT.parent / ".github/workflows/product-validation.yml").read_text(
            encoding="utf-8"
        )

        def job(name: str) -> str:
            match = re.search(
                rf"^  {re.escape(name)}:\n(?P<body>.*?)(?=^  [a-z0-9-]+:\n|\Z)",
                workflow,
                re.MULTILINE | re.DOTALL,
            )
            self.assertIsNotNone(match, name)
            return match.group("body")

        dispatch = job("dispatch-authorization")
        self.assertIn("if: github.event_name == 'workflow_dispatch'", dispatch)
        self.assertIn("environment: product-attestation", dispatch)
        self.assertIn("actions: read", dispatch)
        for policy in (
            ".can_admins_bypass == false",
            "custom_branch_policies: true",
            '.type == "required_reviewers" and (.reviewers | length) > 0',
            '.type == "branch_policy"',
            ".total_count > 0 and (.branch_policies | length) == .total_count",
        ):
            self.assertIn(policy, dispatch)
        for exact_identity in (
            'test "$GITHUB_SHA" = "$VALIDATION_COMMIT"',
            'test "$(git rev-parse \'HEAD^{tree}\')" = "$VALIDATION_TREE"',
            'git merge-base --is-ancestor "$BASE_COMMIT" "$VALIDATION_COMMIT"',
        ):
            self.assertIn(exact_identity, dispatch)

        plan_job = job("plan")
        self.assertIn("needs: dispatch-authorization", plan_job)
        self.assertIn(
            "event_authorized: ${{ steps.event-authorization.outputs.authorized }}",
            plan_job,
        )
        self.assertIn(
            "remote_build_authorized: ${{ steps.impact.outputs.remote_build_authorized }}",
            plan_job,
        )
        self.assertIn(
            "remote_build_authorization_reason: ${{ steps.impact.outputs.remote_build_authorization_reason }}",
            plan_job,
        )
        for argument in (
            '--event-payload "$GITHUB_EVENT_PATH"',
            '--github-ref "$GITHUB_REF"',
            '--github-sha "$GITHUB_SHA"',
        ):
            self.assertIn(argument, plan_job)
        event_authorization = plan_job.split("- id: event-authorization", 1)[1].split(
            "- uses: actions/checkout@", 1,
        )[0]
        for condition in (
            "github.event.action == 'checks_requested'",
            "github.sha == github.event.merge_group.head_sha",
            "github.ref == github.event.merge_group.head_ref",
            "github.event.action == 'labeled'",
            "github.event.label.name == 'ci:remote-final'",
            "github.event.pull_request.draft == false",
            "contains(github.event.pull_request.labels.*.name, 'merge-ready')",
            "contains(github.event.pull_request.labels.*.name, 'ci:remote-final')",
            "github.event.pull_request.head.repo.full_name == github.repository",
            "github.event.pull_request.head.repo.fork == false",
            "needs.dispatch-authorization.outputs.approved == 'true'",
            "github.sha == inputs.validationCommit",
        ):
            self.assertIn(condition, event_authorization)
        self.assertNotIn("merge_commit_sha", event_authorization)

        event_guard = "needs.plan.outputs.event_authorized == 'true'"
        planner_guard = "needs.plan.outputs.remote_build_authorized == 'true'"
        for name in (
            "product",
            "contract-validation",
            "product-resume",
            "android",
            "android-runtime-evidence",
            "desktop",
            "apple",
            "consumers",
            "sdk-javascript",
        ):
            with self.subTest(job=name):
                self.assertIn(event_guard, job(name))
                self.assertIn(planner_guard, job(name))
        child = (CI_ROOT.parent / ".github/workflows/contract-validation.yml").read_text()
        self.assertGreaterEqual(child.count("fromJSON(inputs.planOutputs).event_authorized == 'true'"), 2)
        self.assertGreaterEqual(child.count("fromJSON(inputs.planOutputs).remote_build_authorized == 'true'"), 2)

        lint = job("workflow-lint")
        self.assertEqual(3, lint.count(event_guard))
        self.assertEqual(3, lint.count(planner_guard))
        self.assertLess(lint.index(event_guard), lint.index("uses: ./.github/actions/setup-kmp"))

        self.assertLess(
            workflow.index("- id: validation-reuse"),
            workflow.index("- id: product-reuse"),
        )
        self.assertLess(
            workflow.index("- id: product-reuse"),
            workflow.index("\n  product:"),
        )
        product_reuse = plan_job.split("- id: product-reuse", 1)[1].split(
            "- uses: actions/upload-artifact@", 1,
        )[0]
        self.assertIn("steps.event-authorization.outputs.authorized == 'true'", product_reuse)
        self.assertIn("steps.impact.outputs.remote_build_authorized == 'true'", product_reuse)
        self.assertIn("steps.validation-reuse.outputs.reused != 'true'", product_reuse)
        self.assertIn("python3 ci/product_reuse.py discover", product_reuse)
        self.assertIn("--destination build/product-reuse", product_reuse)
        self.assertIn("--handoff build/ci/product-reuse", product_reuse)
        self.assertNotIn("cp ", product_reuse)
        self.assertNotIn("cp -R", product_reuse)
        self.assertNotIn("--destination build/ci/", product_reuse)
        self.assertIn(
            "contract_reconciliation_required: ${{ steps.product-reuse.outputs.contract_reconciliation_required }}",
            plan_job,
        )
        self.assertIn(
            "contract_next_phase: ${{ steps.product-reuse.outputs.contract_next_phase }}",
            plan_job,
        )
        self.assertIn(
            "name: codex-agent-product-carrier-${{ steps.impact.outputs.validation_tree }}",
            plan_job,
        )
        self.assertIn(
            "if: steps.product-reuse.outputs.full_reuse == 'true' && steps.product-reuse.outputs.product_reuse_reason == 'verified-full-reuse'",
            plan_job,
        )
        for name in (
            "product", "android", "android-runtime-evidence", "desktop", "apple", "consumers",
            "sdk-javascript", "merge-gate",
        ):
            self.assertNotIn("product_target_jobs_required", job(name))

        gate = job("merge-gate")
        self.assertLess(
            gate.index('if [ "$EVENT_AUTHORIZED" != true ]'),
            gate.index("uses: actions/checkout@"),
        )
        self.assertLess(
            gate.index('if [ "$REMOTE_BUILD_AUTHORIZED" != true ]'),
            gate.index("uses: actions/checkout@"),
        )

    def test_contract_package_validation_and_metadata_continue_from_exact_phase_artifacts(self) -> None:
        workflow = (CI_ROOT.parent / ".github/workflows/contract-validation.yml").read_text(
            encoding="utf-8"
        )
        match = re.search(
            r"^  contract-continuation:\n(?P<body>.*?)(?=^  contract-attestation:\n)",
            workflow,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(match)
        job = match.group("body")
        for guard in (
            "fromJSON(inputs.planOutputs).event_authorized == 'true'",
            "fromJSON(inputs.planOutputs).remote_build_authorized == 'true'",
            "fromJSON(inputs.planOutputs).validation_reused != 'true'",
            "fromJSON(inputs.planOutputs).contract_reconciliation_required == 'true'",
        ):
            self.assertIn(guard, job)
        self.assertNotIn("fromJSON(inputs.planOutputs).contract_next_phase != 'none'", job)
        self.assertIn("needs: [contract-binary, product-tooling]", job)
        self.assertIn("fromJSON(inputs.planOutputs).contract_next_phase != 'binary' || needs.contract-binary.result == 'success'", job)
        self.assertNotIn("contains(needs.*.result", job)
        self.assertIn("cache-read-only: \"true\"", job)
        self.assertNotIn("fromJSON(inputs.planOutputs).contract_next_phase != 'metadata'", job)
        self.assertEqual(4, job.count("python3 ci/product_reuse.py advance-contract"))
        self.assertEqual(4, job.count("python3 ci/product_reuse.py materialize-contract"))
        self.assertEqual(4, job.count("--with-receipt"))
        self.assertEqual(3, job.count("python3 -m ci.products restore store-phase"))
        self.assertIn("-PcodexAgent.phase=package", job)
        self.assertIn("-PcodexAgent.phase=validation", job)
        self.assertIn("-PcodexAgent.phase=metadata", job)
        self.assertIn('-PcodexAgent.contractValidationStageRoot="$PWD/build/contract-handoff/validation/stage"', job)
        self.assertNotIn("ssh-keygen", job)
        self.assertNotIn("secrets.", job)
        self.assertEqual(1, job.count("ci.products.contract_attestation capture-closure"))
        self.assertNotIn("ci.products.contract_attestation build", job)
        self.assertIn("for phase in binary package validation metadata; do", job)
        for phase in ("binary", "package", "validation", "metadata"):
            self.assertIn(f'--{phase}-receipt "$originals/{phase}/receipt/phase-receipt.json"', job)
        self.assertIn('--execution-archive "$originals/binary/stage/outputs/execution/contract-execution.zip"', job)
        self.assertIn("build/contract-attestation-inputs/phases/metadata/stage", job)
        self.assertIn("build/contract-attestation-inputs/execution-closure", job)
        self.assertIn(
            "codex-agent-product-phase-contract-contract-binary-common-${{ fromJSON(inputs.planOutputs).validation_tree }}",
            job,
        )
        for phase in ("package", "validation", "metadata"):
            self.assertIn(
                f"codex-agent-product-phase-contract-contract-{phase}-common-${{{{ fromJSON(inputs.planOutputs).validation_tree }}}}",
                job,
            )
        self.assertIn("binary/receipt/phase-receipt.json", job)
        self.assertIn("package/receipt/phase-receipt.json", job)
        self.assertIn('id: reconcile_binary', job)
        self.assertIn('id: reconcile_package', job)
        self.assertIn('id: reconcile_validation', job)
        self.assertIn('id: reconcile_metadata', job)
        self.assertIn('steps.reconcile_binary.outputs.next_phase', job)
        self.assertIn('steps.reconcile_package.outputs.next_phase', job)
        self.assertIn('steps.reconcile_validation.outputs.next_phase', job)
        self.assertIn('steps.reconcile_metadata.outputs.next_phase', job)
        self.assertIn(
            "if: steps.select_after_binary.outputs.next_phase == 'package'",
            job,
        )
        self.assertIn(
            "if: steps.select_after_package.outputs.next_phase == 'validation'",
            job,
        )
        self.assertIn("metadata:false|none:true", job)
        self.assertIn('test "$next_phase:$complete" = none:true', job)
        self.assertIn("path: ${{ steps.select_final_state.outputs.state }}", job)
        ordered = (
            "Reconcile the fresh Contract binary phase",
            "Materialize the exact Contract binary stage and receipt",
            "Produce and finalize the Contract package phase",
            "Reconcile the fresh Contract package phase",
            "Materialize the exact Contract package stage and receipt",
            "Produce and finalize the Contract validation phase",
            "Reconcile the fresh Contract validation phase",
            "Materialize the exact Contract validation stage and receipt",
            "Produce and finalize the deterministic Contract metadata phase",
            "Upload the Contract metadata phase",
            "Reconcile the fresh Contract metadata phase",
            "Preserve the complete unsigned Contract state for separate attestation",
            "Capture unsigned Contract attestation inputs from exact original phases",
            "Preserve unsigned payload and full original execution closure",
        )
        positions = [job.index(value) for value in ordered]
        self.assertEqual(sorted(positions), positions)
        self.assertIn("codex-agent-contract-phase-state-${{ fromJSON(inputs.planOutputs).validation_tree }}", job)
        parent = (CI_ROOT.parent / ".github/workflows/product-validation.yml").read_text()
        merge_gate = parent.split("\n  merge-gate:\n", 1)[1]
        self.assertIn("contract-validation", merge_gate.split("\n    runs-on:", 1)[0])

    def test_contract_workflow_state_scripts_cover_metadata_only_and_fail_closed(self) -> None:
        workflow = (CI_ROOT.parent / ".github/workflows/contract-validation.yml").read_text()
        job = workflow.split("\n  contract-continuation:\n", 1)[1].split("\n  contract-attestation:\n", 1)[0]
        selectors = (("select_after_binary", "binary", "package"),
                     ("select_after_package", "package", "validation"),
                     ("select_after_validation", "validation", "metadata"),
                     ("select_final_state", "metadata", "none"))
        scripts = {}
        for step, _, _ in selectors:
            body = job.split(f"        id: {step}\n", 1)[1].split("\n      - ", 1)[0]
            scripts[step] = "\n".join(line[10:] for line in body.split("        run: |\n", 1)[1].splitlines())
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "outputs"
            for initial in ("binary", "package", "validation", "metadata"):
                current, state, complete = initial, "build/ci/product-reuse", "false"
                for step, elected, successor in selectors:
                    output.unlink(missing_ok=True)
                    environment = {**os.environ, "GITHUB_OUTPUT": str(output), "INITIAL_NEXT_PHASE": initial,
                        "CURRENT_NEXT_PHASE": current, "CURRENT_STATE": state, "CURRENT_COMPLETE": complete,
                        "RECONCILED_NEXT_PHASE": successor if current == elected else "",
                        "RECONCILED_COMPLETE": ("true" if successor == "none" else "false") if current == elected else ""}
                    with self.subTest(initial=initial, step=step):
                        result = subprocess.run(["bash", "-euo", "pipefail", "-c", scripts[step]],
                            env=environment, capture_output=True, text=True)
                        self.assertEqual(0, result.returncode, result.stderr)
                    values = dict(line.split("=", 1) for line in output.read_text().splitlines())
                    current, state, complete = values["next_phase"], values["state"], values["contract_complete"]
                self.assertEqual(("none", "build/contract-state/after-metadata", "true"), (current, state, complete))
            for next_phase, complete in (("metadata", "false"), ("none", "false"), ("", "")):
                output.unlink(missing_ok=True)
                result = subprocess.run(["bash", "-euo", "pipefail", "-c", scripts["select_final_state"]],
                    env={**environment, "CURRENT_NEXT_PHASE": "metadata", "RECONCILED_NEXT_PHASE": next_phase,
                         "RECONCILED_COMPLETE": complete}, capture_output=True)
                self.assertNotEqual(0, result.returncode)
                self.assertFalse(output.exists())

    def test_c_abi_evidence_inputs_are_lf_canonical(self) -> None:
        root = CI_ROOT.parent
        c_abi = root / "codex-agent-runtime-desktop/native/c-api"
        shared = (root / "ci/lanes/shared.production.pathspec").read_text(
            encoding="utf-8"
        )
        self.assertIn(".gitattributes", shared.splitlines())
        paths = [
            "LICENSE",
            "THIRD_PARTY_NOTICES.md",
            *(
                path.relative_to(root).as_posix()
                for directory in ("include", "exports", "consumer")
                for path in sorted((c_abi / directory).rglob("*"))
                if path.is_file()
            ),
        ]

        resolved = subprocess.run(
            ["git", "check-attr", "text", "eol", "--", *paths],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        expected = [
            line
            for path in paths
            for line in (f"{path}: text: set", f"{path}: eol: lf")
        ]
        self.assertEqual(expected, resolved)

    def test_native_wrapper_package_installs_rust_quality_components(self) -> None:
        workflow = (
            CI_ROOT.parent / ".github/workflows/sdk-validation.yml"
        ).read_text(encoding="utf-8")
        package = workflow.split("\n  native-wrapper-language:", 1)[1].split(
            "\n  native-wrapper-package-validation:", 1
        )[0]
        action = package.split(
            "uses: dtolnay/rust-toolchain@a5f673d0ba8626c3977bb416a1612774bc82181b",
            1,
        )[1].split("- uses: dart-lang/setup-dart@", 1)[0]

        self.assertEqual(
            ["components: rustfmt,clippy"],
            [
                line.strip()
                for line in action.splitlines()
                if line.strip().startswith("components:")
            ],
        )
        self.assertNotIn("toolchain:", action)
        for command in ("cargo fmt ", "cargo clippy "):
            self.assertLess(
                package.index("components: rustfmt,clippy"), package.index(command)
            )
        self.assertEqual(
            [
                'CODEX_AGENT_LIBRARY="$sdk" cargo test --manifest-path "$binding/rust/Cargo.toml" --all-targets --release --locked --offline',
                'CODEX_AGENT_REAL_SDK="$sdk" cargo test --manifest-path "$binding/rust/Cargo.toml" \\',
            ],
            [
                line.strip()
                for line in package.splitlines()
                if 'cargo test --manifest-path "$binding/rust/Cargo.toml"' in line
            ],
        )

    def test_native_wrapper_dart_behavior_runs_declared_sdk_floor(self) -> None:
        root = CI_ROOT.parent
        workflow = (root / ".github/workflows/sdk-validation.yml").read_text(
            encoding="utf-8"
        )
        language = workflow.split("\n  native-wrapper-language:", 1)[1].split(
            "\n  native-wrapper-package-validation:", 1
        )[0]
        pubspec = (
            root / "codex-agent-bindings/dart/pubspec.yaml"
        ).read_text(encoding="utf-8")
        floor = re.search(r'^  sdk: ">=([0-9.]+) <4\.0\.0"$', pubspec, re.MULTILINE)
        action = language.split("uses: dart-lang/setup-dart@", 1)[1].split(
            "- name: Execute the wrapper behavior and parity suite", 1
        )[0]

        self.assertIsNotNone(floor)
        self.assertIn("if: matrix.language == 'dart'", action)
        self.assertEqual(
            [f'sdk: "{floor.group(1)}"'],
            [line.strip() for line in action.splitlines() if line.strip().startswith("sdk:")],
        )
        self.assertLess(
            language.index(f'sdk: "{floor.group(1)}"'),
            language.index("dart pub get --enforce-lockfile"),
        )

    def test_native_wrapper_package_emits_csharp_aggregate_evidence(self) -> None:
        workflow = (
            CI_ROOT.parent / ".github/workflows/sdk-validation.yml"
        ).read_text(encoding="utf-8")
        package = workflow.split("\n  native-wrapper-language:", 1)[1].split(
            "\n  native-wrapper-package-validation:", 1
        )[0]
        lines = [line.strip() for line in package.splitlines()]
        project = (
            'dotnet run --project '
            '"$binding/csharp/tests/CodexAgent.Tests/CodexAgent.Tests.csproj" \\'
        )
        arguments = [
            (index, line)
            for index, line in enumerate(lines)
            if line.startswith("--configuration Release --no-build")
        ]

        self.assertEqual(2, lines.count(project))
        self.assertEqual(
            [
                '--configuration Release --no-build -- --real-mcp-values "$sdk"',
                "--configuration Release --no-build",
            ],
            [line for _, line in arguments],
        )
        self.assertLess(
            arguments[-1][0],
            lines.index(
                'cp "$csharp/artifacts"/{compiler-evidence.tsv,executed-tests.tsv} '
                '"$evidence/"'
            ),
        )

    def test_native_wrapper_validation_stages_once_fans_out_and_collects(self) -> None:
        workflow = (
            CI_ROOT.parent / ".github/workflows/sdk-validation.yml"
        ).read_text(encoding="utf-8")
        stage = workflow.split("\n  native-wrapper-sdk-stage:", 1)[1].split(
            "\n  native-wrapper-language:", 1
        )[0]
        language = workflow.split("\n  native-wrapper-language:", 1)[1].split(
            "\n  native-wrapper-package-validation:", 1
        )[0]
        package = workflow.split("\n  native-wrapper-package-validation:", 1)[1].split(
            "\n  native-wrapper-release-assembly:", 1
        )[0]
        assembly = workflow.split("\n  native-wrapper-release-assembly:", 1)[1].split(
            "\n  native-wrapper-host-consumers:", 1
        )[0]
        consumers = workflow.split("\n  native-wrapper-host-consumers:", 1)[1]

        self.assertEqual(1, stage.count("python3 -B -m ci.sdk_native_prepared_receiver"))
        self.assertIn("uses: ./.github/actions/capture-sdk-tooling", stage)
        self.assertIn("uses: ./.github/actions/capture-runtime-state", stage)
        self.assertIn("product: sdk", stage)
        self.assertIn("sdk-family: ${{ format('native-{0}', inputs.preparationPhase) }}", stage)
        self.assertIn('test "$STATE_ID" = "$PREPARATION_STATE_ID"', stage)
        self.assertIn('test "$STATE_SHA" = "$PREPARATION_STATE_SHA"', stage)
        self.assertIn('test "$STATE_WAVE" = "$PREPARATION_STATE_WAVE"', stage)
        self.assertIn('test "$SDK_STATE_WAVE" = "$PREPARATION_SDK_STATE_WAVE"', stage)
        self.assertIn('--preparation-state-root "$STATE"', stage)
        self.assertIn('--prepared-artifact-id "$PREPARED_ARTIFACT_ID"', stage)
        self.assertIn('--prepared-artifact-sha256 "$PREPARED_ARTIFACT_SHA256"', stage)
        self.assertIn('--sdk-inputs-artifact-id "$SDK_INPUTS_ARTIFACT_ID"', stage)
        self.assertIn('--sdk-inputs-artifact-sha256 "$SDK_INPUTS_ARTIFACT_SHA256"', stage)
        self.assertIn('--trusted-workflow-sha "$TRUSTED_WORKFLOW_SHA"', stage)
        self.assertLess(stage.index("name: Require one exact original preparation state"),
                        stage.index("uses: ./.github/actions/capture-runtime-state"))
        self.assertLess(stage.index("python3 -B -m ci.sdk_native_prepared_receiver"),
                        stage.index("uses: actions/upload-artifact@"))
        for forbidden in ("setup-kmp", "./gradlew", "prepareNativeWrapperPackageSources",
                          "codex-agent-ci-desktop-", "codex-agent-ci-contracts-"):
            self.assertNotIn(forbidden, stage)
        self.assertIn("name: codex-agent-native-wrapper-sdk-stage-${{ inputs.validationTree }}", stage)
        self.assertIn("path: build/sdk-native-prepared-receiver/upload", stage)
        self.assertIn("retention-days: 1", stage)
        versioned_sdk_root = "native-wrapper-c-abi-sdks/${{ inputs.validationTree }}"
        self.assertEqual(3, workflow.count(versioned_sdk_root))
        self.assertNotIn("native-wrapper-c-abi-sdks/linux-x64", workflow)

        self.assertIn("needs: native-wrapper-sdk-stage", language)
        self.assertIn("fail-fast: false", language)
        self.assertIn(
            "name: codex-agent-native-wrapper-sdk-stage-${{ inputs.validationTree }}",
            language,
        )
        self.assertEqual(
            ["python", "csharp", "rust", "cpp", "dart"],
            [
                line.strip().removeprefix("- language: ")
                for line in language.splitlines()
                if line.strip().startswith("- language: ")
            ],
        )
        self.assertIn(
            "name: codex-agent-native-wrapper-evidence-${{ matrix.language }}-${{ inputs.validationTree }}",
            language,
        )
        self.assertIn("path: build/native-wrapper-evidence", language)
        self.assertIn("include-hidden-files: true", language)
        self.assertIn("retention-days: 1", language)
        for check in (
            'test "${actual_files[*]}" = "${expected_files[*]}"',
            'test -f "$evidence/$file"',
            'test -s "$evidence/$file"',
            'test ! -L "$evidence/$file"',
        ):
            self.assertIn(check, language)

        self.assertIn("needs: native-wrapper-sdk-stage", package)
        self.assertIn(
            "name: codex-agent-native-wrapper-sdk-stage-${{ inputs.validationTree }}",
            package,
        )
        self.assertIn('python "$tool/ci/native_wrappers.py" package', package)
        self.assertLess(package.index("python -m pip install build==1.3.0 setuptools==80.9.0 wheel==0.45.1"),
                        package.index("test_package_only_process.py"))
        self.assertLess(package.index("test_package_only_process.py"),
                        package.index('python "$tool/ci/native_wrappers.py" package'))
        self.assertEqual(2, package.count("-p test_package_only_process.py -v"))
        self.assertLess(package.index("codex-agent-bindings/cpp/tools/tests"),
                        package.index('python "$tool/ci/native_wrappers.py" package'))
        self.assertNotIn("test_package_root_requirement.py", package)
        self.assertNotIn('--repository "$PWD"', package)
        self.assertIn('cp -R ci/products "$tool/ci/"', package)
        self.assertIn('test ! -e "$tool/codex-agent-runtime-desktop"', package)
        self.assertIn('--sdk-version-file "$PWD/gradle/release/versions/sdk.txt"', package)
        self.assertIn("codex-agent-sdk/build/native-wrapper-package-sources", package)
        self.assertIn("codex-agent-sdk/build/native-wrapper-c-abi-sdks", package)
        self.assertIn(
            "name: codex-agent-native-wrapper-package-validation-${{ inputs.validationTree }}",
            package,
        )
        self.assertIn("retention-days: 1", package)
        self.assertIn('--sdk-version-file "$PWD/gradle/release/versions/sdk.txt"', consumers)

        self.assertIn("if: always()", assembly)
        self.assertIn(
            "needs: [native-wrapper-sdk-stage, native-wrapper-language, native-wrapper-package-validation]",
            assembly,
        )
        self.assertLess(
            assembly.index("name: Require every parallel native-wrapper validation"),
            assembly.index("uses: actions/download-artifact@"),
        )
        for result in (
            "needs.native-wrapper-sdk-stage.result",
            "needs.native-wrapper-language.result",
            "needs.native-wrapper-package-validation.result",
        ):
            self.assertIn(result, assembly)
        for result in ("SDK_STAGE_RESULT", "LANGUAGE_RESULT", "PACKAGE_RESULT"):
            self.assertIn(f'test "${result}" = success', assembly)
        self.assertIn(
            "pattern: codex-agent-native-wrapper-evidence-*-${{ inputs.validationTree }}",
            assembly,
        )
        self.assertIn("merge-multiple: true", assembly)
        self.assertIn("expected_languages=(cpp csharp dart python rust)", assembly)
        self.assertIn(
            "expected_files=(compiler-evidence.tsv executed-tests.tsv test-program)",
            assembly,
        )
        for check in (
            'test "${actual_languages[*]}" = "${expected_languages[*]}"',
            'test "${actual_files[*]}" = "${expected_files[*]}"',
            'test -d "$directory"',
            'test ! -L "$directory"',
            'test -f "$directory/$file"',
            'test -s "$directory/$file"',
            'test ! -L "$directory/$file"',
        ):
            self.assertIn(check, assembly)
        self.assertIn(
            "name: codex-agent-native-wrapper-packages-${{ inputs.validationTree }}",
            assembly,
        )
        self.assertIn("retention-days: 90", assembly)
        self.assertIn("needs: native-wrapper-release-assembly", consumers)

    def test_native_wrapper_workflow_is_sdk_owned_and_authorized_before_invocation(self) -> None:
        workflows = CI_ROOT.parent / ".github/workflows"
        desktop = (workflows / "desktop-runtime-evidence.yml").read_text(encoding="utf-8")
        parent = (workflows / "product-validation.yml").read_text(encoding="utf-8")
        sdk = (workflows / "sdk-validation.yml").read_text(encoding="utf-8")
        caller = parent.split("\n  sdk-native-wrappers:", 1)[1].split("\n  apple:", 1)[0]
        gate = parent.split("\n  merge-gate:", 1)[1]

        self.assertNotIn("native-wrapper-", desktop)
        self.assertNotIn("nativeWrappers", desktop)
        self.assertIn("needs: [workflow-lint, plan, sdk-plan, sdk-csharp-binary-result, sdk-native-prepare, sdk-inputs]", caller)
        for condition in (
            "needs.plan.outputs.event_authorized == 'true'",
            "needs.plan.outputs.remote_build_authorized == 'true'",
            "needs.plan.outputs.validation_reused != 'true'",
            "needs.plan.outputs.native_wrappers == 'true'",
            "needs.sdk-csharp-binary-result.result == 'success'",
            "needs.sdk-native-prepare.result == 'success'",
        ):
            self.assertIn(condition, caller)
        for field, source in (
            ("planId", "needs.plan.outputs.plan_id"),
            ("trustedWorkflowSha", "inputs.trustedWorkflowSha"),
            ("stateArtifactId", "needs.sdk-csharp-binary-result.outputs.artifact_id"),
            ("stateArtifactSha256", "needs.sdk-csharp-binary-result.outputs.artifact_digest"),
            ("stateWave", "needs.sdk-csharp-binary-result.outputs.state_wave"),
            ("sdkStateWave", "needs.sdk-csharp-binary-result.outputs.sdk_state_wave"),
            ("preparationStateArtifactId", "needs.sdk-native-prepare.outputs.preparation_state_id"),
            ("preparationStateArtifactSha256", "needs.sdk-native-prepare.outputs.preparation_state_digest"),
            ("preparationStateWave", "needs.sdk-native-prepare.outputs.preparation_state_wave"),
            ("preparationSdkStateWave", "needs.sdk-native-prepare.outputs.preparation_sdk_state_wave"),
            ("preparationComponent", "needs.sdk-native-prepare.outputs.preparation_component"),
            ("preparationPhase", "needs.sdk-native-prepare.outputs.preparation_phase"),
            ("preparationTarget", "needs.sdk-native-prepare.outputs.preparation_target"),
            ("preparationBuildKey", "needs.sdk-native-prepare.outputs.preparation_build_key"),
            ("sdkPreparedArtifactId", "needs.sdk-native-prepare.outputs.artifact_id"),
            ("sdkPreparedArtifactSha256", "needs.sdk-native-prepare.outputs.artifact_digest"),
            ("sdkInputsArtifactId", "needs.sdk-inputs.outputs.artifact_id"),
            ("sdkInputsArtifactSha256", "needs.sdk-inputs.outputs.artifact_digest"),
            ("toolingRequired", "needs.plan.outputs.tooling_required"),
            ("toolingArtifactId", "needs.sdk-plan.outputs.tooling_artifact_id"),
            ("toolingArtifactSha256", "needs.sdk-plan.outputs.tooling_artifact_sha256"),
            ("toolingTransportProducer", "needs.sdk-plan.outputs.tooling_transport_producer"),
        ):
            self.assertIn(f"{field}: ${{{{ {source} }}}}", caller)
        self.assertIn("uses: ./.github/workflows/sdk-validation.yml", caller)
        self.assertIn("sdk-native-wrappers", gate.split("\n    needs:", 1)[1].split("\n    runs-on:", 1)[0])
        self.assertIn('test "$NATIVE_WRAPPERS_RESULT" = success || exit 1', gate)
        self.assertIn("native-wrapper-release-assembly:", sdk)

    def test_native_wrapper_preparation_state_guard_fails_closed(self) -> None:
        workflow = (CI_ROOT.parent / ".github/workflows/sdk-validation.yml").read_text(encoding="utf-8")
        guard = workflow.split("      - name: Require one exact original preparation state\n", 1)[1].split(
            "      - name: Select installed caller Java for SDK tooling\n", 1
        )[0]
        script = textwrap.dedent(guard.split("        run: |\n", 1)[1])
        values = {
            "STATE_ID": "11", "STATE_SHA": "sha256:" + "a" * 64,
            "STATE_WAVE": "0", "SDK_STATE_WAVE": "2",
            "PREPARATION_STATE_ID": "11", "PREPARATION_STATE_SHA": "sha256:" + "a" * 64,
            "PREPARATION_STATE_WAVE": "0", "PREPARATION_SDK_STATE_WAVE": "2",
            "TOOLING_REQUIRED": "false", "TOOLING_ARTIFACT_ID": "",
            "TOOLING_ARTIFACT_SHA256": "", "TOOLING_TRANSPORT_PRODUCER": "",
        }

        def accepted(changes: dict[str, str]) -> bool:
            result = subprocess.run(["bash", "-c", script], env={**os.environ, **values, **changes},
                                    capture_output=True, text=True)
            return result.returncode == 0

        self.assertTrue(accepted({}))
        for field, wrong in (
            ("PREPARATION_STATE_ID", "12"), ("PREPARATION_STATE_SHA", "sha256:" + "b" * 64),
            ("PREPARATION_STATE_WAVE", "1"), ("PREPARATION_SDK_STATE_WAVE", "3"),
            ("TOOLING_REQUIRED", "unknown"), ("TOOLING_ARTIFACT_ID", "12"),
        ):
            with self.subTest(field=field):
                self.assertFalse(accepted({field: wrong}))
        self.assertTrue(accepted({"TOOLING_REQUIRED": "true", "TOOLING_ARTIFACT_ID": "12",
                                  "TOOLING_ARTIFACT_SHA256": "sha256:" + "b" * 64,
                                  "TOOLING_TRANSPORT_PRODUCER": "{}"}))

    def test_action_and_lane_driver_bind_every_execution_to_the_candidate_tree(self) -> None:
        action = (CI_ROOT.parent / ".github/actions/run-ci-lane/action.yml").read_text(encoding="utf-8")
        driver = (CI_ROOT / "run-lane.sh").read_text(encoding="utf-8")

        self.assertEqual(2, action.count("CI_VALIDATION_TREE: ${{ inputs.validation-tree }}"))
        self.assertIn('tree=${CI_VALIDATION_TREE:?validation tree is required}', driver)
        self.assertIn(
            '-PcodexAgent.candidateCommit="$commit" -PcodexAgent.candidateTree="$tree"',
            driver,
        )

    def test_contracts_run_only_contract_owned_binding_receipt_gates(self) -> None:
        driver = (CI_ROOT / "run-lane.sh").read_text(encoding="utf-8")
        contracts = driver.split("  contracts)", 1)[1].split("  portable)", 1)[0]
        self.assertIn('if [ "$build" = true ] || [ "$test_lane" = true ]; then', contracts)
        self.assertEqual(1, contracts.count(":codex-agent-core:verifyKotlinBindingParity"))
        self.assertNotIn(":build-logic:test", contracts)
        self.assertNotIn(":codex-agent-core:verifyJavaBindingParity", contracts)
        self.assertNotIn(":codex-agent-core:auditCrossLanguageBindingParity", contracts)
        self.assertNotIn(":codex-agent-core:verifyCrossLanguageApiCoverage", contracts)

    def test_node_js_stages_only_Runtime_binding_validation(self) -> None:
        driver = (CI_ROOT / "run-lane.sh").read_text(encoding="utf-8")
        node_js = driver.split("  node-js)", 1)[1].split("  node-wasm)", 1)[0]
        self.assertIn('if [ "$build" = true ] || [ "$test_lane" = true ]; then', node_js)
        self.assertEqual(1, node_js.count(":codex-agent-runtime-desktop:writeNodeJsBindingValidationOutputManifest"))
        self.assertNotIn(":codex-agent-sdk:", node_js)
        self.assertNotIn(":codex-agent-runtime-desktop:verifyPackedNpmConsumers", node_js)
        self.assertNotIn(":codex-agent-runtime-desktop:jsNodeTest", node_js)

    def test_swift_tests_run_the_single_transitive_apple_binding_receipt_gate(self) -> None:
        driver = (CI_ROOT / "run-lane.sh").read_text(encoding="utf-8")
        swift_tests = driver.split("  ios-swift-tests)", 1)[1].split("  ios-package)", 1)[0]
        self.assertEqual(1, swift_tests.count(":codex-agent-runtime-ios:generateCodexAgentAppleBindingEvidence"))
        self.assertNotIn(":codex-agent-runtime-ios:verifyCodexAgentSwiftAuthenticationTests", swift_tests)
        self.assertNotIn(":codex-agent-runtime-ios:generateCodexAgentAppleCompilerEvidence", swift_tests)

    def test_sdk_parity_owns_m8_through_m11_and_merge_gate_consumes_exact_handoff(self) -> None:
        workflows = CI_ROOT.parent / ".github/workflows"
        parent = (workflows / "product-validation.yml").read_text(encoding="utf-8")
        parity = (workflows / "sdk-binding-parity.yml").read_text(encoding="utf-8")
        caller = parent.split("\n  sdk-parity:", 1)[1].split("\n  merge-gate:", 1)[0]
        merge_gate = parent.split("\n  merge-gate:", 1)[1]
        assemble = 'java -jar "$release_tool" assemble-c-abi-binding-receipt'
        audit = 'java -jar "$release_tool" audit-cross-language-bindings'

        for dependency in ("product", "desktop", "apple", "sdk-javascript", "sdk-native-wrappers"):
            self.assertIn(dependency, caller.split("    needs:", 1)[1].split("    uses:", 1)[0])
        for condition in (
            "needs.plan.outputs.event_authorized == 'true'",
            "needs.plan.outputs.remote_build_authorized == 'true'",
            "needs.plan.outputs.validation_reused != 'true'",
            "needs.plan.outputs.lane_ios_swift_tests_test == 'true'",
            "needs.plan.outputs.native_wrappers == 'true'",
        ):
            self.assertIn(condition, caller)
        self.assertIn("uses: ./.github/workflows/sdk-binding-parity.yml", caller)
        self.assertIn("sdk-parity", merge_gate.split("    needs:", 1)[1].split("    runs-on:", 1)[0])
        self.assertLess(
            merge_gate.index("name: Require readiness and successful prerequisites"),
            merge_gate.index("uses: actions/checkout@"),
        )
        self.assertIn("if grep -Eq 'failure|cancelled' <<<\"$RESULTS\"; then", merge_gate)
        self.assertIn('test "$SDK_PARITY_RESULT" = success || exit 1', merge_gate)
        self.assertIn('[[ "$SDK_PARITY_ARTIFACT_ID" =~ ^[1-9][0-9]*$ ]] || exit 1', merge_gate)
        self.assertIn('artifact-ids: ${{ needs.sdk-parity.outputs.artifact_id }}', merge_gate)
        self.assertLess(
            merge_gate.index('artifact-ids: ${{ needs.sdk-parity.outputs.artifact_id }}'),
            merge_gate.index("name: Stage the exact reusable validation artifact"),
        )
        self.assertNotIn(assemble, merge_gate)
        self.assertNotIn("./gradlew verifySdkBindingParity", merge_gate)
        self.assertEqual(1, parity.count(assemble))
        self.assertEqual(3, parity.count(audit))
        self.assertEqual(2, parity.count("advance-cross-language-binding-receipt"))
        self.assertIn("--phase M8", parity)
        self.assertIn("phases=(M9_PYTHON M9_CSHARP M9_RUST M9_CPP M9_DART)", parity)
        self.assertIn("--phase M11", parity)
        self.assertEqual(1, parity.count("./gradlew verifySdkBindingParity"))
        self.assertLess(parity.index("--phase M11"), parity.index("./gradlew verifySdkBindingParity"))
        self.assertLess(
            parity.index("./gradlew verifySdkBindingParity"),
            parity.index("name: Stage exact SDK parity evidence"),
        )
        for task in ("Python", "CSharp", "Rust", "Cpp", "Dart"):
            self.assertEqual(1, parity.count(f":codex-agent-sdk:verify{task}BindingParity"))
            self.assertNotIn(f":codex-agent-runtime-desktop:verify{task}BindingParity", parity)
        for literal in ("6116", "3324", "2780", "3880", "4436", "4992", "5548", "6104", "12"):
            self.assertIn(literal, parity)
        self.assertIn("codex-agent-native-wrapper-packages-", parity)
        self.assertIn("codex-agent-native-wrapper-host-*", parity)
        self.assertIn("path: build/ci/sdk-parity-evidence", parity)
        self.assertIn("build/ci/plan/reused-native-wrapper-release", merge_gate)
        self.assertIn("path: build/ci/final-validation/*", merge_gate)


class GitFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.git("init", "-q")
        self.git("config", "user.email", "ci@example.invalid")
        self.git("config", "user.name", "CI Fixture")
        self.write("README.md", "baseline\n")
        self.write("ci/impact.py", "# planner\n")
        for lane in LANES:
            self.write(f"configured/{lane}.txt", "configured\n")
            platform = "desktop-linux-x64-only/**\n" if lane == "desktop-linux-x64" else ""
            runtime_version = (
                "gradle/release/versions/runtime.txt\n"
                if lane.startswith("desktop-") else ""
            )
            self.write(
                f"ci/lanes/{lane}.production.pathspec",
                f"configured/{lane}.txt\n{platform}{runtime_version}",
            )
        inventories = {
            "shared.production": "common/**\n.gitattributes\n",
            "android.production": (
                "android/**\nconfigured/android.txt\nlegal/openai-codex/**\n"
                "gradle/release/versions/contract.txt\n"
                "gradle/release/versions/sdk.txt\n"
            ),
            "android.test": "codex-agent-runtime-android/src/test/**\n",
            "android.metadata": "android-metadata/**\n",
            "node-js.production": (
                "js/**\nconfigured/node-js.txt\n"
                "gradle/release/versions/runtime.txt\n"
                "gradle/release/versions/sdk.txt\n"
            ),
            "node-wasm.production": (
                "wasm/**\nconfigured/node-wasm.txt\n"
                "gradle/release/versions/runtime.txt\n"
            ),
            "portable.production": (
                "desktop-runtime/**\njs/**\nwasm/**\n"
                "codex-agent-core/src/jvmMain/**\nconfigured/portable.txt\n"
                "gradle/release/versions/runtime.txt\n"
            ),
            "contracts.production": "configured/contracts.txt\n",
            "contracts.test": "binding-contract-tests/**\n",
            "contracts.metadata": (
                "Package.swift\n.github/workflows/promote.yml\ngradle/release/**\n"
            ),
            "node-js.test": "binding-node-tests/**\n",
            "consumer-common.production": (
                "codex-agent-core/src/jvmMain/**\nconfigured/consumer-common.txt\n"
            ),
            "consumer-desktop.production": (
                "codex-agent-core/src/jvmMain/**\nconfigured/consumer-desktop.txt\n"
            ),
            "ios-package.metadata": "Package.swift\n",
            "ios-privacy-metrics.metadata": "privacy-policy/**\n",
            "ios-kotlin-tests.test": "ios-sim-tests/**\n",
            "ios-swift-tests.test": (
                "ios-swift-auth-tests/**\n"
                "gradle/build-logic/src/main/kotlin/CrossLanguage*.kt\n"
                "gradle/build-logic/src/main/kotlin/ReleaseToolingCli.kt\n"
                "gradle/build-logic/src/main/kotlin/codexagent.core-verification.gradle.kts\n"
                "gradle/build-logic/src/test/kotlin/CrossLanguage*.kt\n"
                "codex-agent-core/build.gradle.kts\n"
                "codex-agent-core/src/commonMain/**\n"
                "codex-agent-core/src/commonTest/**\n"
                "codex-agent-core/src/jvmAndAndroidMain/**\n"
                "codex-agent-core/src/jvmTest/**\n"
                "codex-agent-runtime-desktop/build.gradle.kts\n"
                "codex-agent-bindings/javascript/**\n"
                "codex-agent-runtime-desktop/src/commonMain/**\n"
                "codex-agent-runtime-desktop/src/commonTest/**\n"
                "codex-agent-runtime-desktop/src/webMain/**\n"
                "codex-agent-runtime-desktop/src/webTest/**\n"
                "codex-agent-runtime-desktop/src/jsMain/**\n"
                "codex-agent-runtime-desktop/src/jsTest/**\n"
                "codex-agent-runtime-ios/apple/CompilerEvidence/**\n"
                "codex-agent-runtime-ios/apple/Tests/**\n"
            ),
            "ios-package.production": (
                "configured/ios-package.txt\n"
                "codex-agent-runtime-ios/apple/Sources/**\n"
                "gradle/release/versions/contract.txt\n"
                "gradle/release/versions/sdk.txt\n"
            ),
        }
        for name, contents in inventories.items():
            self.write(f"ci/lanes/{name}.pathspec", contents)
        for lane in (name for name in LANES if name.startswith("desktop-")):
            self.write(f"ci/lanes/{lane}.test.pathspec", "desktop-tests/**\njs/**\nwasm/**\n")
        self.git("add", ".")
        self.git("commit", "-qm", "base")
        self.base = self.git("rev-parse", "HEAD")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def git(self, *arguments: str) -> str:
        return subprocess.run(
            ["git", *arguments],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def write(self, relative: str, contents: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")

    def commit(self, relative: str, contents: str) -> str:
        self.write(relative, contents)
        self.git("add", relative)
        self.git("commit", "-qm", relative)
        return self.git("rev-parse", "HEAD")

    def pull_request_event(
        self,
        *,
        base: str,
        target: str,
        pull_request: int = 7,
        labels: tuple[str, ...] = ("merge-ready", "ci:remote-final"),
        action: str = "labeled",
        event_label: str = "ci:remote-final",
        draft: bool = False,
        head_repository: str = "codex-agent-labs/codex-agent",
        head_fork: bool = False,
    ) -> dict[str, object]:
        repository = "codex-agent-labs/codex-agent"
        payload: dict[str, object] = {
            "action": action,
            "number": pull_request,
            "repository": {"full_name": repository},
            "pull_request": {
                "number": pull_request,
                "draft": draft,
                "merge_commit_sha": target,
                "labels": [{"name": label} for label in labels],
                "base": {
                    "sha": base,
                    "repo": {"full_name": repository, "fork": False},
                },
                "head": {
                    "sha": target,
                    "repo": {"full_name": head_repository, "fork": head_fork},
                },
            },
        }
        if action in {"labeled", "unlabeled"}:
            payload["label"] = {"name": event_label}
        return payload

    def pull_request_authorization(
        self,
        *,
        base: str,
        target: str,
        pull_request: int = 7,
        merge_ready: bool = True,
    ) -> dict[str, object]:
        labels = ("merge-ready", "ci:remote-final") if merge_ready else ()
        return {
            "event_payload": self.pull_request_event(
                base=base,
                target=target,
                pull_request=pull_request,
                labels=labels,
                action="labeled" if merge_ready else "synchronize",
            ),
            "github_ref": f"refs/pull/{pull_request}/merge",
            "github_sha": target,
            "dispatch_approved": False,
        }

    def make_plan(
        self,
        relative: str,
        contents: str = "changed\n",
        *,
        merge_ready: bool = True,
        force_full: bool = False,
        require_android_evidence: bool = False,
        pull_request: int = 7,
        base: str | None = None,
    ) -> tuple[dict[str, object], Path, str]:
        target = self.commit(relative, contents)
        effective_base = base or self.base
        output = self.root / "build/ci/impact-plan.json"
        result = plan(
            root=self.root,
            base=effective_base,
            target=target,
            head=target,
            event="pull_request",
            pull_request=pull_request,
            force_full=force_full,
            require_android_evidence=require_android_evidence,
            repository="codex-agent-labs/codex-agent",
            output=output,
            **self.pull_request_authorization(
                base=effective_base,
                target=target,
                pull_request=pull_request,
                merge_ready=merge_ready,
            ),
        )
        return result, output, target


class ImpactPlanTest(GitFixture):
    def test_legacy_lane_plan_is_recomputed_from_authoritative_product_selection(self) -> None:
        result, _, _ = self.make_plan(
            "codex-agent-runtime-android/src/test/kotlin/ProjectionTest.kt"
        )
        validate_legacy_lane_projection(result, self.root)
        mutations = (
            ("missing selected action", lambda value: value["lanes"]["android"].update(test=False)),
            ("invented action", lambda value: value["lanes"]["ios-package"].update(metadata=True)),
            ("reuse bypass", lambda value: value["lanes"]["android"].update(reuseAllowed=False)),
            ("invented reason", lambda value: value["lanes"]["android"].update(reasons=["invented"])),
            ("changed path substitution", lambda value: value.update(changedPaths=["README.md"])),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                candidate = json.loads(json.dumps(result))
                mutate(candidate)
                with self.assertRaisesRegex(ValueError, "authoritative product-to-legacy projection"):
                    validate_legacy_lane_projection(candidate, self.root)
        full_lanes, full, unknown = _legacy_lane_states(
            self.root,
            result["changedPaths"],
            force_full=True,
            remote_authorized=True,
            remote_reason="pull-request-final",
        )
        coordinated = json.loads(json.dumps(result))
        coordinated.update(lanes=full_lanes, full=full, unknownPaths=unknown)
        with self.assertRaisesRegex(ValueError, "authoritative product-to-legacy projection"):
            validate_legacy_lane_projection(coordinated, self.root)
        coordinated["fullRequested"] = True
        validate_legacy_lane_projection(coordinated, self.root)

    def test_binding_inputs_require_all_five_language_receipt_owners(self) -> None:
        base = self.base
        inputs = (
            "codex-agent-core/src/commonMain/kotlin/sample/Canonical.kt",
            "codex-agent-core/src/jvmAndAndroidMain/kotlin/sample/CodexJava.kt",
            "codex-agent-runtime-desktop/src/jsMain/kotlin/sample/CodexNode.kt",
            "codex-agent-runtime-ios/apple/CompilerEvidence/CodexFailureSwiftConsumer.swift",
            "codex-agent-runtime-ios/apple/CompilerEvidence/CodexFailureObjectiveCConsumer.m",
            "codex-agent-runtime-ios/apple/Tests/CodexAgentObservationTests/CodexAgentObservationTests.swift",
            "gradle/build-logic/src/main/kotlin/ReleaseToolingCli.kt",
        )
        for relative in inputs:
            with self.subTest(relative=relative):
                result, _, target = self.make_plan(relative, base=base)
                base = target
                self.assertTrue(result["lanes"]["contracts"]["build"])
                self.assertTrue(result["lanes"]["contracts"]["test"])
                self.assertTrue(result["lanes"]["node-js"]["test"])
                self.assertTrue(result["lanes"]["ios-swift-tests"]["test"])
                self.assertTrue(result["full"] or "required-by:ios-swift-tests" in result["lanes"]["contracts"]["reasons"])
                self.assertTrue(result["full"] or "required-by:ios-swift-tests" in result["lanes"]["node-js"]["reasons"])

    def test_rename_is_classified_by_its_destination(self) -> None:
        old = "codex-agent-runtime-desktop/src/jsMain/kotlin/Old.kt"
        new = "codex-agent-runtime-desktop/src/jsMain/kotlin/Main.kt"
        base = self.commit(old, "old\n")
        self.git("mv", old, new)
        self.git("commit", "-qm", "move into classified JS input")
        target = self.git("rev-parse", "HEAD")

        result = plan(
            root=self.root,
            base=base,
            target=target,
            head=target,
            event="pull_request",
            pull_request=7,
            force_full=False,
            repository="codex-agent-labs/codex-agent",
            output=self.root / "build/ci/rename-impact-plan.json",
            **self.pull_request_authorization(base=base, target=target),
        )

        self.assertEqual([], result["unknownPaths"])
        self.assertTrue(result["lanes"]["node-js"]["build"])

    def test_rename_from_unclassified_source_forces_full_validation(self) -> None:
        base = self.commit("legacy/old.txt", "old\n")
        destination = "codex-agent-runtime-desktop/src/jsMain/kotlin/Main.kt"
        (self.root / destination).parent.mkdir(parents=True, exist_ok=True)
        self.git("mv", "legacy/old.txt", destination)
        self.git("commit", "-qm", "move unclassified input into JS")
        target = self.git("rev-parse", "HEAD")

        result = plan(
            root=self.root,
            base=base,
            target=target,
            head=target,
            event="pull_request",
            pull_request=7,
            force_full=False,
            repository="codex-agent-labs/codex-agent",
            output=self.root / "build/ci/unclassified-rename-impact-plan.json",
            **self.pull_request_authorization(base=base, target=target),
        )

        self.assertEqual(["legacy/old.txt"], result["unknownPaths"])
        self.assertTrue(result["full"])
        self.assertTrue(all(not state["reuseAllowed"] for state in result["lanes"].values()))

    def test_deleted_classified_input_still_selects_its_lane(self) -> None:
        removed = "codex-agent-runtime-desktop/src/jsMain/kotlin/Removed.kt"
        base = self.commit(removed, "old\n")
        self.git("rm", removed)
        self.git("commit", "-qm", "remove classified JS input")
        target = self.git("rev-parse", "HEAD")

        result = plan(
            root=self.root,
            base=base,
            target=target,
            head=target,
            event="pull_request",
            pull_request=7,
            force_full=False,
            repository="codex-agent-labs/codex-agent",
            output=self.root / "build/ci/deletion-impact-plan.json",
            **self.pull_request_authorization(base=base, target=target),
        )

        self.assertEqual([], result["unknownPaths"])
        self.assertTrue(result["lanes"]["node-js"]["build"])

    def test_deleted_unclassified_input_forces_full_validation(self) -> None:
        base = self.commit("legacy/removed.txt", "old\n")
        self.git("rm", "legacy/removed.txt")
        self.git("commit", "-qm", "remove unclassified input")
        target = self.git("rev-parse", "HEAD")

        result = plan(
            root=self.root,
            base=base,
            target=target,
            head=target,
            event="pull_request",
            pull_request=7,
            force_full=False,
            repository="codex-agent-labs/codex-agent",
            output=self.root / "build/ci/unclassified-deletion-impact-plan.json",
            **self.pull_request_authorization(base=base, target=target),
        )

        self.assertEqual(["legacy/removed.txt"], result["unknownPaths"])
        self.assertTrue(result["full"])
        self.assertTrue(all(not state["reuseAllowed"] for state in result["lanes"].values()))

    def test_docs_only_runs_no_product_lane(self) -> None:
        result, _, _ = self.make_plan("README.md", "docs\n")
        self.assertEqual([], result["unknownPaths"])
        self.assertFalse(any(
            state[action]
            for state in result["lanes"].values()
            for action in ("build", "test", "metadata")
        ))

    def test_any_m8_owner_activity_runs_the_exact_m8_coordinator_closure(self) -> None:
        self.assertEqual({
            "contracts",
            "node-js",
            "desktop-macos-arm64",
            "desktop-macos-x64",
            "desktop-linux-arm64",
            "desktop-linux-x64",
            "desktop-windows-x64",
            "ios-swift-tests",
        }, set(M8_OWNER_LANES))
        base = self.base
        cases = (
            (".github/workflows/promote.yml", "metadata-only\n", "contracts", "metadata"),
            ("codex-agent-runtime-desktop/src/linuxMain/kotlin/Runtime.kt", "platform-only\n", "desktop-linux-x64", "build"),
        )
        for relative, contents, owner, action in cases:
            with self.subTest(relative=relative):
                result, _, target = self.make_plan(relative, contents, base=base)
                base = target
                self.assertEqual([], result["unknownPaths"])
                self.assertTrue(result["lanes"][owner][action])
                self.assertTrue(result["lanes"]["ios-swift-tests"]["test"])
                self.assertTrue(all(
                    any(result["lanes"][lane][item] for item in ("build", "test", "metadata"))
                    for lane in M8_OWNER_LANES
                ))

    def test_c_abi_sdk_legal_inputs_are_owned_by_all_five_desktop_lanes(self) -> None:
        root = CI_ROOT.parent
        desktop_lanes = {lane for lane in LANES if lane.startswith("desktop-")}
        for relative in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
            with self.subTest(relative=relative):
                self.assertEqual(desktop_lanes, {
                    lane
                    for lane in desktop_lanes
                    if relative in effective_pathspecs(root, lane, "production")
                })

    def test_android_change_excludes_unrelated_platforms(self) -> None:
        result, _, _ = self.make_plan("codex-agent-runtime-android/src/main/kotlin/Main.kt")
        self.assertTrue(result["lanes"]["android"]["build"])
        self.assertTrue(result["lanes"]["consumer-android"]["build"])
        for lane in ("node-js", "node-wasm", "desktop-macos-arm64", "ios-framework-device"):
            self.assertFalse(result["lanes"][lane]["build"])

    def test_neutral_legal_change_retains_android_runtime_ownership(self) -> None:
        result, _, _ = self.make_plan(
            "legal/openai-codex/openai-codex-LICENSE.txt",
            "license\n",
        )
        self.assertEqual([], result["unknownPaths"])
        self.assertTrue(result["lanes"]["android"]["build"])
        self.assertTrue(result["lanes"]["consumer-android"]["build"])

    def test_contract_and_sdk_versions_select_android_and_ios_package_owners(self) -> None:
        base = self.base
        for product in ("contract", "sdk"):
            with self.subTest(product=product):
                result, _, target = self.make_plan(
                    f"gradle/release/versions/{product}.txt",
                    "0.2.1\n",
                    base=base,
                )
                base = target
                self.assertEqual([], result["unknownPaths"])
                self.assertTrue(result["lanes"]["android"]["build"])
                self.assertTrue(result["lanes"]["consumer-android"]["build"])
                self.assertTrue(result["lanes"]["ios-package"]["build"])
                if product == "sdk":
                    self.assertTrue(result["lanes"]["node-js"]["build"])
                    self.assertTrue(result["lanes"]["consumer-node-js"]["build"])

    def test_runtime_version_selects_every_current_runtime_owner(self) -> None:
        result, _, _ = self.make_plan(
            "gradle/release/versions/runtime.txt",
            "0.3.0\n",
        )
        self.assertEqual([], result["unknownPaths"])
        expected = {
            "portable", "node-js", "node-wasm",
            "desktop-macos-arm64", "desktop-macos-x64",
            "desktop-linux-arm64", "desktop-linux-x64", "desktop-windows-x64",
            "consumer-desktop", "consumer-node-js", "consumer-node-wasm",
        }
        self.assertTrue(all(result["lanes"][lane]["build"] for lane in expected))

    def test_queue_disabled_bootstrap_full_plan_requires_android_evidence(self) -> None:
        result, _, _ = self.make_plan(
            "README.md",
            "bootstrap\n",
            force_full=True,
            require_android_evidence=True,
        )
        self.assertTrue(result["lanes"]["android"]["build"])
        self.assertTrue(result["androidEvidenceRequired"])

    def test_js_and_wasm_are_independent(self) -> None:
        js_path = "codex-agent-runtime-desktop/src/jsMain/kotlin/Main.kt"
        result, plan_path, _ = self.make_plan(js_path)
        self.assertTrue(result["lanes"]["portable"]["build"])
        self.assertTrue(result["lanes"]["node-js"]["build"])
        self.assertTrue(result["lanes"]["contracts"]["build"])
        self.assertFalse(result["lanes"]["node-wasm"]["build"])
        contracts_inventory = plan_path.parent / "inventories/contracts/production-inputs.git-tree"
        self.assertNotIn(f"\t{js_path}\n", contracts_inventory.read_text(encoding="utf-8"))
        for lane in (name for name in LANES if name.startswith("desktop-")):
            self.assertTrue(result["lanes"][lane]["build"])
            self.assertTrue(result["lanes"][lane]["test"])
        self.assertTrue(result["lanes"]["consumer-desktop"]["build"])
        output = self.root / "selection.out"
        subprocess.run([
            sys.executable, str(CI_ROOT / "lane_selection.py"), "--plan", str(plan_path),
            "--lane", "desktop-linux-x64", "--github-output", str(output),
        ], check=True)
        selection = dict(line.split("=", 1) for line in output.read_text().splitlines())
        self.assertEqual("true", selection["node_js"])
        self.assertEqual("true", selection["node_wasm"])

    def test_wasm_change_keeps_js_product_independent_but_desktop_evidence_complete(self) -> None:
        result, plan_path, _ = self.make_plan(
            "codex-agent-runtime-desktop/src/wasmJsMain/kotlin/Main.kt"
        )
        self.assertTrue(result["lanes"]["portable"]["build"])
        self.assertFalse(result["lanes"]["node-js"]["build"])
        self.assertFalse(result["lanes"]["node-wasm"]["build"])
        for lane in (name for name in LANES if name.startswith("desktop-")):
            self.assertTrue(result["lanes"][lane]["build"])
            self.assertTrue(result["lanes"][lane]["test"])
        self.assertTrue(result["lanes"]["consumer-desktop"]["build"])
        output = self.root / "selection.out"
        subprocess.run([
            sys.executable, str(CI_ROOT / "lane_selection.py"), "--plan", str(plan_path),
            "--lane", "desktop-linux-x64", "--github-output", str(output),
        ], check=True)
        selection = dict(line.split("=", 1) for line in output.read_text().splitlines())
        self.assertEqual("true", selection["node_js"])
        self.assertEqual("true", selection["node_wasm"])

    def test_real_runner_pathspecs_keep_js_and_wasm_product_inputs_independent(self) -> None:
        root = CI_ROOT.parent
        js = "codex-agent-runtime-desktop/src/jsMain/kotlin/OnlyJs.kt"
        wasm = "codex-agent-runtime-desktop/src/wasmJsMain/kotlin/OnlyWasm.kt"

        def matches(lane: str, category: str, path: str) -> bool:
            return any(
                fnmatch.fnmatchcase(path, spec)
                for spec in effective_pathspecs(root, lane, category)
            )

        self.assertTrue(matches("portable", "production", js))
        self.assertTrue(matches("portable", "production", wasm))
        self.assertTrue(matches("node-js", "production", js))
        self.assertFalse(matches("node-js", "production", wasm))
        self.assertFalse(matches("node-wasm", "production", js))
        self.assertTrue(matches("node-wasm", "production", wasm))
        for npm in (
            "codex-agent-bindings/javascript/package/index.cjs",
            "codex-agent-bindings/javascript/consumer/smoke.ts",
        ):
            self.assertEqual(
                {"contracts", "node-js", "consumer-node-js"},
                {lane for lane in LANES if matches(lane, "production", npm)},
            )
            self.assertEqual(
                set(),
                {lane for lane in LANES if matches(lane, "test", npm)},
            )
            self.assertFalse(any(matches(lane, "metadata", npm) for lane in LANES))
        for lane in (name for name in LANES if name.startswith("desktop-")):
            self.assertFalse(matches(lane, "production", js))
            self.assertFalse(matches(lane, "production", wasm))
            self.assertTrue(matches(lane, "test", js))
            self.assertTrue(matches(lane, "test", wasm))

    def test_runtime_source_change_invalidates_portable_runner(self) -> None:
        result, _, _ = self.make_plan("codex-agent-runtime-desktop/src/commonMain/kotlin/Main.kt")
        self.assertTrue(result["lanes"]["portable"]["build"])

    def test_test_only_does_not_build_or_propagate(self) -> None:
        result, _, _ = self.make_plan("codex-agent-runtime-android/src/test/kotlin/Test.kt")
        self.assertTrue(result["lanes"]["android"]["test"])
        self.assertFalse(result["lanes"]["android"]["build"])
        self.assertFalse(result["lanes"]["consumer-android"]["build"])

    def test_shared_ios_test_selects_both_validation_targets(self) -> None:
        result, _, _ = self.make_plan("codex-agent-runtime-ios/src/iosTest/kotlin/Test.kt")
        self.assertTrue(result["lanes"]["ios-kotlin-tests"]["test"])
        self.assertTrue(result["lanes"]["consumer-ios-device"]["build"])
        self.assertTrue(result["lanes"]["consumer-ios-simulator"]["build"])

    def test_swift_test_selects_both_frameworks(self) -> None:
        result, _, _ = self.make_plan("ios-swift-auth-tests/Test.swift")
        self.assertTrue(result["lanes"]["ios-swift-tests"]["test"])
        for lane in ("ios-framework-device", "ios-framework-simulator", "ios-swift-build"):
            self.assertTrue(result["lanes"][lane]["build"])

    def test_device_framework_change_invalidates_swift_tests(self) -> None:
        result, plan_path, _ = self.make_plan("configured/ios-framework-device.txt", "device changed\n")
        self.assertTrue(result["lanes"]["ios-framework-device"]["build"])
        self.assertTrue(result["lanes"]["ios-swift-tests"]["test"])
        inventory = plan_path.parent / "inventories/ios-swift-tests/production-inputs.git-tree"
        self.assertIn("\tconfigured/ios-framework-device.txt\n", inventory.read_text(encoding="utf-8"))

    def test_checksum_contract_metadata_change_runs_m8_without_ios_package_build(self) -> None:
        result, _, _ = self.make_plan("Package.swift", "// checksum only\n")
        self.assertTrue(result["lanes"]["ios-package"]["metadata"])
        self.assertTrue(result["lanes"]["ios-swift-tests"]["test"])
        self.assertTrue(result["lanes"]["ios-package"]["build"])
        self.assertTrue(all(
            any(result["lanes"][lane][action] for action in ("build", "test", "metadata"))
            for lane in M8_OWNER_LANES
        ))

    def test_swift_wrapper_change_keeps_framework_production_compatible(self) -> None:
        prior_path = self.root / "build/ci/prior/impact-plan.json"
        plan(
            root=self.root,
            base=self.base,
            target=self.base,
            head=self.base,
            event="pull_request",
            pull_request=7,
            force_full=False,
            require_android_evidence=False,
            repository="codex-agent-labs/codex-agent",
            output=prior_path,
            **self.pull_request_authorization(base=self.base, target=self.base),
        )
        wrapper = "codex-agent-runtime-ios/apple/Sources/Wrapper.swift"
        result, current_path, _ = self.make_plan(wrapper, "public struct Wrapper {}\n")
        self.assertTrue(result["lanes"]["ios-package"]["build"])
        package = Path("inventories/ios-package/production-inputs.git-tree")
        self.assertNotEqual(
            (prior_path.parent / package).read_bytes(),
            (current_path.parent / package).read_bytes(),
        )
        self.assertIn(
            f"\t{wrapper}\n",
            (current_path.parent / package).read_text(encoding="utf-8"),
        )
        for lane in ("ios-framework-device", "ios-framework-simulator"):
            self.assertTrue(result["lanes"][lane]["build"])
            relative = Path("inventories", lane, "production-inputs.git-tree")
            self.assertEqual(
                (prior_path.parent / relative).read_bytes(),
                (current_path.parent / relative).read_bytes(),
            )

    def test_unrepresentable_facade_validation_falls_back_to_full_legacy_execution(self) -> None:
        result, _, _ = self.make_plan(
            "gradle/release/kmp-consumer-template/src/commonMain/kotlin/Consumer.kt"
        )
        self.assertTrue(result["full"])
        self.assertEqual([], result["unknownPaths"])
        self.assertTrue(all(state["reuseAllowed"] for state in result["lanes"].values()))

    def test_m8_binding_owner_change_requires_every_receipt_and_host_proof_lane(self) -> None:
        result, _, _ = self.make_plan(
            "gradle/build-logic/src/main/kotlin/CrossLanguageApiCoverage.kt",
            "// binding owner changed\n",
        )
        self.assertTrue(result["lanes"]["ios-swift-tests"]["test"])
        self.assertTrue(result["lanes"]["contracts"]["test"])
        self.assertTrue(result["lanes"]["node-js"]["test"])
        for lane in (name for name in LANES if name.startswith("desktop-")):
            self.assertTrue(result["lanes"][lane]["build"], lane)
            self.assertTrue(result["lanes"][lane]["test"], lane)

    def test_privacy_workflow_uses_only_framework_artifacts_and_complete_gate(self) -> None:
        apple = (CI_ROOT.parent / ".github/workflows/apple-runtime-evidence.yml").read_text(encoding="utf-8")
        select = apple[apple.index("\n  select:"):apple.index("\n\n  native-tests:")]
        privacy = apple[apple.index("\n  privacy-metrics:"):apple.index("\n\n  consumer-common:")]
        self.assertIn("needs: [select, framework-device, framework-simulator]", privacy)
        self.assertEqual(2, privacy.count("uses: actions/download-artifact@"))
        for lane, path in (("framework-device", "device"), ("framework-simulator", "simulator")):
            self.assertIn(f"needs.{lane}.outputs.artifact_name", privacy)
            self.assertIn(f"path: build/ci/privacy-inputs/{path}", privacy)
        for removed in ("needs.kotlin-tests", "needs.swift-tests", "needs.package"):
            self.assertNotIn(removed, privacy)

        selected = (
            lane for lane in LANES
            if lane.startswith("ios-") or lane in {
                "consumer-common", "consumer-ios-device", "consumer-ios-simulator",
            }
        )
        for lane in selected:
            self.assertIn(f"--lane {lane}", select)
        for job in ("kotlin-tests", "swift-tests", "package", "privacy-metrics"):
            self.assertIn(f"\n  {job}:\n", apple)

        workflow = (CI_ROOT.parent / ".github/workflows/product-validation.yml").read_text(encoding="utf-8")
        sdk_consumers = (CI_ROOT.parent / ".github/workflows/sdk-consumer-validation.yml").read_text(
            encoding="utf-8"
        )
        caller = workflow.split("\n  consumers:", 1)[1].split("\n  sdk-ios-binary-plan:", 1)[0]
        for consumer in ("consumer-desktop", "consumer-node-js", "consumer-node-wasm"):
            self.assertEqual(2, sdk_consumers.count(f"matrix.lane == '{consumer}'"))
        self.assertIn("uses: ./.github/workflows/sdk-consumer-validation.yml", caller)
        self.assertIn("needs.plan.outputs.event_authorized == 'true'", caller)
        self.assertIn("needs.plan.outputs.remote_build_authorized == 'true'", caller)
        self.assertIn("needs.plan.outputs.consumer_matrix != '[]'", caller)
        self.assertIn("fail-fast: false", sdk_consumers)
        gate = workflow[workflow.index("\n  merge-gate:"):]
        self.assertIn(
            "needs: [workflow-lint, plan, product, contract-validation, contract-phase10-pgp-authority, contract-phase10-maven, contract-phase10-output-record, product-resume, runtime-linux-arm64-supervisor, runtime-workers-1, runtime-collect-1, runtime-workers-2, runtime-collect-2, runtime-workers-3, runtime-collect-3, runtime-workers-4, runtime-collect-4, runtime-continuation, runtime-signing-prepare-native, runtime-native-attestation, runtime-aggregate, runtime-collect-5, runtime-aggregate-continuation, runtime-signing-prepare-aggregate, runtime-aggregate-attestation, runtime-phase10-maven, sdk-inputs, sdk-ios-binary-plan, sdk-ios-binary, sdk-collect-3, android, android-runtime-evidence, desktop, sdk-native-wrappers, apple, consumers, sdk-javascript, sdk-native-packages, sdk-ios-packages, sdk-javascript-metadata-result, sdk-native-result, sdk-android-binary-result, sdk-android-package-result, sdk-android-validation-result, sdk-android-metadata-result, sdk-completion, sdk-catalog, sdk-parity]",
            gate,
        )
        self.assertIn("pattern: codex-agent-ci-*", gate)
        self.assertIn("python3 ci/receipt.py aggregate --plan", gate)

    def test_unknown_and_planner_changes_force_full(self) -> None:
        unknown, _, unknown_target = self.make_plan("unclassified/input.txt")
        self.assertTrue(unknown["full"])
        self.assertEqual(["unclassified/input.txt"], unknown["unknownPaths"])
        self.assertTrue(all(state["build"] for state in unknown["lanes"].values()))
        self.assertTrue(all(not state["reuseAllowed"] for state in unknown["lanes"].values()))

        planner, planner_path, planner_target = self.make_plan(
            "ci/impact.py", "# changed planner\n", base=unknown_target,
        )
        self.assertTrue(planner["full"])
        self.assertEqual([], planner["unknownPaths"])
        self.assertTrue(all(state["reuseAllowed"] for state in planner["lanes"].values()))
        for lane in LANES:
            inventory = planner_path.parent / "inventories" / lane / "production-inputs.git-tree"
            self.assertIn("\tci/impact.py\n", inventory.read_text(encoding="utf-8"))

        forced, _, _ = self.make_plan(
            "README.md", "forced full\n", base=planner_target, force_full=True,
        )
        self.assertTrue(forced["full"])
        self.assertTrue(all(state["reuseAllowed"] for state in forced["lanes"].values()))

    def test_consumer_matrix_selects_the_required_host(self) -> None:
        result, _, desktop_target = self.make_plan(
            "codex-agent-runtime-desktop/src/jvmMain/kotlin/Consumer.kt",
            "consumer changed\n",
        )
        output = self.root / "github-output"
        write_github_outputs(output, result)
        values = dict(line.split("=", 1) for line in output.read_text(encoding="utf-8").splitlines())
        matrix = json.loads(values["consumer_matrix"])
        self.assertEqual(["macos-26"], [item["runner"] for item in matrix if item["lane"] == "consumer-desktop"])

        result, _, _ = self.make_plan(
            "codex-agent-runtime-android/src/main/kotlin/Main.kt", base=desktop_target
        )
        output = self.root / "github-output-android"
        write_github_outputs(output, result)
        values = dict(line.split("=", 1) for line in output.read_text(encoding="utf-8").splitlines())
        matrix = json.loads(values["consumer_matrix"])
        self.assertTrue(matrix)
        self.assertTrue(all(item["runner"] == "ubuntu-24.04" for item in matrix))

    def test_native_wrapper_changes_select_all_five_build_and_test_owners(self) -> None:
        result, _, _ = self.make_plan(
            "codex-agent-bindings/python/src/codex_agent/_ffi.py",
            "wrapper changed\n",
        )
        self.assertTrue(all(
            result["lanes"][lane]["build"] and result["lanes"][lane]["test"]
            for lane in NATIVE_WRAPPER_LANES
        ))
        output = self.root / "github-output-native-wrappers"
        write_github_outputs(output, result)
        values = dict(line.split("=", 1) for line in output.read_text(encoding="utf-8").splitlines())
        self.assertEqual("true", values["native_wrappers"])

    def test_checkout_attribute_policy_change_selects_every_lane(self) -> None:
        result, _, _ = self.make_plan(".gitattributes", "* text eol=lf\n")

        self.assertEqual([], result["unknownPaths"])
        self.assertTrue(result["full"])
        self.assertTrue(all(state["build"] for state in result["lanes"].values()))
        self.assertTrue(
            all(state["reuseAllowed"] for state in result["lanes"].values())
        )

    def test_shared_production_change_selects_every_lane(self) -> None:
        result, _, _ = self.make_plan("common/Api.kt")
        self.assertTrue(all(state["build"] for state in result["lanes"].values()))

    def test_contract_owner_change_runs_the_m8_coordinator(self) -> None:
        result, _, _ = self.make_plan("configured/contracts.txt")
        self.assertTrue(result["lanes"]["contracts"]["build"])
        self.assertTrue(result["lanes"]["ios-swift-tests"]["test"])
        self.assertTrue(all(
            any(result["lanes"][lane][action] for action in ("build", "test", "metadata"))
            for lane in M8_OWNER_LANES
        ))

    def test_jvm_only_change_uses_full_legacy_fallback_for_unrepresentable_facade_validation(self) -> None:
        result, _, _ = self.make_plan("codex-agent-core/src/jvmMain/kotlin/JvmOnly.kt")
        selected_consumers = {
            lane
            for lane, state in result["lanes"].items()
            if lane.startswith("consumer-") and state["build"]
        }
        self.assertTrue(result["full"])
        self.assertEqual({lane for lane in LANES if lane.startswith("consumer-")}, selected_consumers)

    def test_unlabeled_pr_spends_no_product_ci(self) -> None:
        result, _, _ = self.make_plan(
            "codex-agent-runtime-android/src/main/kotlin/Main.kt", merge_ready=False
        )
        self.assertFalse(result["remoteBuildAuthorized"])
        self.assertEqual("merge-ready-required", result["remoteBuildAuthorizationReason"])
        self.assertFalse(any(
            state[action]
            for state in result["lanes"].values()
            for action in ("build", "test", "metadata")
        ))
        self.assertTrue(all(state["reasons"] == ["merge-ready-required"] for state in result["lanes"].values()))

    def test_remote_final_pr_authorization_is_emitted_to_github_outputs(self) -> None:
        result, _, _ = self.make_plan("codex-agent-runtime-android/src/main/kotlin/Main.kt")
        self.assertTrue(result["remoteBuildAuthorized"])
        self.assertEqual("pull-request-final", result["remoteBuildAuthorizationReason"])

        output = self.root / "github-authorization-output"
        write_github_outputs(output, result)
        values = dict(
            line.split("=", 1)
            for line in output.read_text(encoding="utf-8").splitlines()
        )
        self.assertEqual("true", values["remote_build_authorized"])
        self.assertEqual(
            "pull-request-final",
            values["remote_build_authorization_reason"],
        )

        contradictory = dict(
            result,
            remoteBuildAuthorizationReason="merge-ready-required",
        )
        with self.assertRaisesRegex(ValueError, "contradictory"):
            write_github_outputs(output, contradictory)
        wrong_event_reason = dict(
            result,
            remoteBuildAuthorizationReason="merge-group",
        )
        with self.assertRaisesRegex(ValueError, "does not match its event"):
            write_github_outputs(output, wrong_event_reason)

    def test_ci_full_label_cannot_authorize_or_emit_product_matrices(self) -> None:
        target = self.commit("android/Main.kt", "changed\n")
        payload = self.pull_request_event(
            base=self.base,
            target=target,
            labels=("ci:full",),
            event_label="ci:full",
        )
        result = plan(
            root=self.root,
            base=self.base,
            target=target,
            head=target,
            event="pull_request",
            pull_request=7,
            force_full=True,
            repository="codex-agent-labs/codex-agent",
            output=self.root / "build/ci/ci-full-only.json",
            event_payload=payload,
            github_ref="refs/pull/7/merge",
            github_sha=target,
            dispatch_approved=False,
        )
        self.assertTrue(result["full"])
        self.assertFalse(result["remoteBuildAuthorized"])
        github_output = self.root / "build/ci/ci-full-only.out"
        write_github_outputs(github_output, result)
        values = dict(
            line.split("=", 1)
            for line in github_output.read_text(encoding="utf-8").splitlines()
        )
        self.assertEqual("[]", values["product_matrix"])
        self.assertEqual("[]", values["consumer_matrix"])
        self.assertEqual("[]", values["desktop_matrix"])

    def test_pull_request_authorization_failures_are_fail_closed(self) -> None:
        target = self.commit("android/Main.kt", "changed\n")
        cases = {
            "draft-pull-request": self.pull_request_event(
                base=self.base,
                target=target,
                draft=True,
            ),
            "merge-ready-required": self.pull_request_event(
                base=self.base,
                target=target,
                labels=(),
                action="synchronize",
            ),
            "remote-final-required": self.pull_request_event(
                base=self.base,
                target=target,
                labels=("merge-ready",),
                event_label="merge-ready",
            ),
            "remote-final-event-required": self.pull_request_event(
                base=self.base,
                target=target,
                action="synchronize",
            ),
            "untrusted-pull-request": self.pull_request_event(
                base=self.base,
                target=target,
                head_repository="someone/example",
                head_fork=True,
            ),
        }
        for reason, payload in cases.items():
            with self.subTest(reason=reason):
                result = plan(
                    root=self.root,
                    base=self.base,
                    target=target,
                    head=target,
                    event="pull_request",
                    pull_request=7,
                    force_full=True,
                    repository="codex-agent-labs/codex-agent",
                    output=self.root / f"build/ci/{reason}.json",
                    event_payload=payload,
                    github_ref="refs/pull/7/merge",
                    github_sha=target,
                    dispatch_approved=False,
                )
                self.assertFalse(result["remoteBuildAuthorized"])
                self.assertEqual(reason, result["remoteBuildAuthorizationReason"])
                self.assertTrue(result["full"])
                self.assertTrue(all(
                    not state[action]
                    for state in result["lanes"].values()
                    for action in ("build", "test", "metadata")
                ))
                self.assertTrue(all(
                    state["reasons"] == [reason]
                    for state in result["lanes"].values()
                ))
                github_output = self.root / f"build/ci/{reason}.out"
                write_github_outputs(github_output, result)
                values = dict(
                    line.split("=", 1)
                    for line in github_output.read_text(encoding="utf-8").splitlines()
                )
                for matrix in ("product_matrix", "consumer_matrix", "desktop_matrix"):
                    self.assertEqual("[]", values[matrix])
                for selector in ("any_desktop", "native_wrappers", "any_apple"):
                    self.assertEqual("false", values[selector])

    def test_malformed_pull_request_labels_and_numbers_write_no_plan(self) -> None:
        target = self.commit("android/Main.kt", "changed\n")
        duplicate = self.pull_request_event(base=self.base, target=target)
        duplicate["pull_request"]["labels"].append({"name": "merge-ready"})
        wrong_type = self.pull_request_event(base=self.base, target=target)
        wrong_type["pull_request"]["labels"] = "merge-ready"
        contradiction = self.pull_request_event(
            base=self.base,
            target=target,
            labels=("merge-ready",),
        )
        embedded_bool = self.pull_request_event(base=self.base, target=target)
        embedded_bool["pull_request"]["number"] = True
        cases = {
            "duplicate-labels": duplicate,
            "wrong-label-type": wrong_type,
            "contradictory-label-event": contradiction,
            "boolean-embedded-number": embedded_bool,
        }
        for name, payload in cases.items():
            with self.subTest(name=name):
                output = self.root / f"build/ci/malformed-{name}.json"
                with self.assertRaises(ValueError):
                    plan(
                        root=self.root,
                        base=self.base,
                        target=target,
                        head=target,
                        event="pull_request",
                        pull_request=7,
                        force_full=False,
                        repository="codex-agent-labs/codex-agent",
                        output=output,
                        event_payload=payload,
                        github_ref="refs/pull/7/merge",
                        github_sha=target,
                        dispatch_approved=False,
                    )
                self.assertFalse(output.exists())

        boolean_top = self.pull_request_event(
            base=self.base,
            target=target,
            pull_request=1,
        )
        boolean_top["number"] = True
        boolean_top["pull_request"]["number"] = True
        with self.assertRaisesRegex(ValueError, "event pull-request number"):
            plan(
                root=self.root,
                base=self.base,
                target=target,
                head=target,
                event="pull_request",
                pull_request=1,
                force_full=False,
                repository="codex-agent-labs/codex-agent",
                output=self.root / "build/ci/boolean-top-number.json",
                event_payload=boolean_top,
                github_ref="refs/pull/1/merge",
                github_sha=target,
                dispatch_approved=False,
            )

    def test_pull_request_head_and_validation_commit_are_distinct_identities(self) -> None:
        head = self.commit("android/Main.kt", "changed\n")
        self.git("commit", "--allow-empty", "-qm", "synthetic merge candidate")
        validation = self.git("rev-parse", "HEAD")
        payload = self.pull_request_event(base=self.base, target=validation)
        payload["pull_request"]["head"]["sha"] = head
        payload["pull_request"]["merge_commit_sha"] = head
        arguments = {
            "root": self.root,
            "base": self.base,
            "target": validation,
            "head": head,
            "event": "pull_request",
            "pull_request": 7,
            "force_full": False,
            "repository": "codex-agent-labs/codex-agent",
            "event_payload": payload,
            "github_ref": "refs/pull/7/merge",
            "github_sha": validation,
            "dispatch_approved": False,
        }
        result = plan(
            **arguments,
            output=self.root / "build/ci/distinct-pr-identities.json",
        )
        self.assertTrue(result["remoteBuildAuthorized"])
        self.assertEqual(head, result["headCommit"])
        self.assertEqual(validation, result["validationCommit"])

        wrong_head = json.loads(json.dumps(payload))
        wrong_head["pull_request"]["head"]["sha"] = validation
        with self.assertRaisesRegex(ValueError, "head SHA"):
            plan(
                **{**arguments, "event_payload": wrong_head},
                output=self.root / "build/ci/wrong-pr-head.json",
            )

        wrong_base = json.loads(json.dumps(payload))
        wrong_base["pull_request"]["base"]["sha"] = head
        with self.assertRaisesRegex(ValueError, "base SHA"):
            plan(
                **{**arguments, "event_payload": wrong_base},
                output=self.root / "build/ci/wrong-pr-base.json",
            )

        with self.assertRaisesRegex(ValueError, "Pull-request ref"):
            plan(
                **{**arguments, "github_ref": "refs/pull/8/merge"},
                output=self.root / "build/ci/wrong-pr-ref.json",
            )

        with self.assertRaisesRegex(ValueError, "GitHub SHA"):
            plan(
                **{**arguments, "github_sha": head},
                output=self.root / "build/ci/wrong-pr-runner-sha.json",
            )

    def test_merge_group_requires_the_exact_checks_requested_event(self) -> None:
        target = self.commit("android/Main.kt", "changed\n")
        head_ref = "refs/heads/gh-readonly-queue/main/pr-7-deadbeef"

        def payload(action: str) -> dict[str, object]:
            return {
                "action": action,
                "repository": {"full_name": "codex-agent-labs/codex-agent"},
                "merge_group": {
                    "base_sha": self.base,
                    "head_sha": target,
                    "head_ref": head_ref,
                },
            }

        denied = plan(
            root=self.root,
            base=self.base,
            target=target,
            head=target,
            event="merge_group",
            pull_request=7,
            force_full=False,
            repository="codex-agent-labs/codex-agent",
            output=self.root / "build/ci/merge-group-denied.json",
            event_payload=payload("destroyed"),
            github_ref=head_ref,
            github_sha=target,
            dispatch_approved=False,
        )
        self.assertFalse(denied["remoteBuildAuthorized"])
        self.assertEqual(
            "merge-group-event-required",
            denied["remoteBuildAuthorizationReason"],
        )

        authorized = plan(
            root=self.root,
            base=self.base,
            target=target,
            head=target,
            event="merge_group",
            pull_request=7,
            force_full=False,
            repository="codex-agent-labs/codex-agent",
            output=self.root / "build/ci/merge-group-authorized.json",
            event_payload=payload("checks_requested"),
            github_ref=head_ref,
            github_sha=target,
            dispatch_approved=False,
        )
        self.assertTrue(authorized["remoteBuildAuthorized"])
        self.assertEqual("merge-group", authorized["remoteBuildAuthorizationReason"])

    def test_dispatch_requires_exact_identity_and_protected_approval(self) -> None:
        target = self.commit("android/Main.kt", "changed\n")
        tree = self.git("rev-parse", f"{target}^{{tree}}")
        payload = {
            "repository": {"full_name": "codex-agent-labs/codex-agent"},
            "ref": "refs/heads/architecture/codex-agent-core",
            "inputs": {
                "baseCommit": self.base,
                "validationCommit": target,
                "validationTree": tree,
            },
        }
        arguments = {
            "root": self.root,
            "base": self.base,
            "target": target,
            "head": target,
            "event": "workflow_dispatch",
            "pull_request": None,
            "force_full": False,
            "repository": "codex-agent-labs/codex-agent",
            "event_payload": payload,
            "github_ref": "refs/heads/architecture/codex-agent-core",
            "github_sha": target,
        }

        denied = plan(
            **arguments,
            output=self.root / "build/ci/dispatch-denied.json",
            dispatch_approved=False,
        )
        self.assertFalse(denied["remoteBuildAuthorized"])
        self.assertEqual(
            "dispatch-approval-required",
            denied["remoteBuildAuthorizationReason"],
        )

        authorized = plan(
            **arguments,
            output=self.root / "build/ci/dispatch-authorized.json",
            dispatch_approved=True,
        )
        self.assertTrue(authorized["remoteBuildAuthorized"])
        self.assertEqual("protected-dispatch", authorized["remoteBuildAuthorizationReason"])

        tag_payload = json.loads(json.dumps(payload))
        tag_payload["ref"] = "refs/tags/v0.2.0"
        tag = plan(
            **{
                **arguments,
                "event_payload": tag_payload,
                "github_ref": "refs/tags/v0.2.0",
            },
            output=self.root / "build/ci/dispatch-tag.json",
            dispatch_approved=True,
        )
        self.assertTrue(tag["remoteBuildAuthorized"])

        bad_ref = json.loads(json.dumps(payload))
        bad_ref["ref"] = "refs/heads/other"
        bad_ref_output = self.root / "build/ci/dispatch-ref-mismatch.json"
        with self.assertRaisesRegex(ValueError, "runner ref"):
            plan(
                **{**arguments, "event_payload": bad_ref},
                output=bad_ref_output,
                dispatch_approved=True,
            )
        self.assertFalse(bad_ref_output.exists())

        bad_payload = json.loads(json.dumps(payload))
        bad_payload["inputs"]["validationTree"] = "0" * 40
        with self.assertRaisesRegex(ValueError, "dispatch identity"):
            plan(
                **{**arguments, "event_payload": bad_payload},
                output=self.root / "build/ci/dispatch-mismatch.json",
                dispatch_approved=True,
            )

    def test_unknown_event_and_mismatched_runner_identity_fail_closed(self) -> None:
        target = self.commit("android/Main.kt", "changed\n")
        payload = {"repository": {"full_name": "codex-agent-labs/codex-agent"}}
        result = plan(
            root=self.root,
            base=self.base,
            target=target,
            head=target,
            event="repository_dispatch",
            pull_request=None,
            force_full=True,
            repository="codex-agent-labs/codex-agent",
            output=self.root / "build/ci/unsupported-event.json",
            event_payload=payload,
            github_ref="refs/heads/main",
            github_sha=target,
            dispatch_approved=False,
        )
        self.assertFalse(result["remoteBuildAuthorized"])
        self.assertEqual("unsupported-event", result["remoteBuildAuthorizationReason"])
        self.assertFalse(any(
            state[action]
            for state in result["lanes"].values()
            for action in ("build", "test", "metadata")
        ))

        with self.assertRaisesRegex(ValueError, "GitHub SHA"):
            plan(
                root=self.root,
                base=self.base,
                target=target,
                head=target,
                event="repository_dispatch",
                pull_request=None,
                force_full=True,
                repository="codex-agent-labs/codex-agent",
                output=self.root / "build/ci/mismatched-runner.json",
                event_payload=payload,
                github_ref="refs/heads/main",
                github_sha="0" * 40,
                dispatch_approved=False,
            )


class RealImpactPlanTest(unittest.TestCase):
    def test_version_authorities_have_runtime_and_npm_owners(self) -> None:
        root = CI_ROOT.parent

        def owners(path: str) -> set[str]:
            return {
                lane
                for lane in LANES
                if any(
                    fnmatch.fnmatchcase(path, spec)
                    for spec in effective_pathspecs(root, lane, "production")
                )
            }

        self.assertTrue({"node-js", "consumer-node-js"}.issubset(
            owners("gradle/release/versions/sdk.txt"),
        ))
        self.assertTrue({
            "portable", "node-js", "node-wasm",
            "desktop-macos-arm64", "desktop-macos-x64",
            "desktop-linux-arm64", "desktop-linux-x64", "desktop-windows-x64",
            "consumer-desktop", "consumer-node-js", "consumer-node-wasm",
        }.issubset(owners("gradle/release/versions/runtime.txt")))

    def test_product_version_authorities_have_current_platform_owners(self) -> None:
        root = CI_ROOT.parent
        for product in ("contract", "sdk"):
            path = f"gradle/release/versions/{product}.txt"
            with self.subTest(product=product):
                owners = {
                    lane
                    for lane in LANES
                    if any(
                        fnmatch.fnmatchcase(path, spec)
                        for spec in effective_pathspecs(root, lane, "production")
                    )
                }
                self.assertIn("android", owners)
                self.assertIn("consumer-android", owners)
                self.assertIn("ios-package", owners)

    def test_neutral_legal_inputs_have_android_runtime_owners(self) -> None:
        root = CI_ROOT.parent
        for path in (
            "legal/openai-codex/openai-codex-LICENSE.txt",
            "legal/openai-codex/openai-codex-NOTICE.txt",
        ):
            with self.subTest(path=path):
                owners = {
                    lane
                    for lane in LANES
                    if any(
                        fnmatch.fnmatchcase(path, spec)
                        for spec in effective_pathspecs(root, lane, "production")
                    )
                }
                self.assertIn("android", owners)
                self.assertIn("consumer-android", owners)

    def test_c_abi_bootstrap_inputs_have_exact_desktop_owners(self) -> None:
        root = CI_ROOT.parent

        def matching_lanes(path: str, category: str) -> set[str]:
            return {
                lane
                for lane in LANES
                if any(
                    fnmatch.fnmatchcase(path, spec)
                    for spec in effective_pathspecs(root, lane, category)
                )
            }

        all_desktop_tests = {
            "desktop-macos-arm64", "desktop-macos-x64", "desktop-linux-arm64",
            "desktop-linux-x64", "desktop-windows-x64",
        }
        for path in (
            "codex-agent-core/src/commonTest/kotlin/io/github/codex_agent_labs/"
            "codexagent/agent/CrossLanguageDomainValueContractTest.kt",
            "codex-agent-core/src/commonMain/kotlin/io/github/codex_agent_labs/"
            "codexagent/agent/CodexHost.kt",
            "gradle/build-logic/src/main/kotlin/CrossLanguageApiCoverage.kt",
            "gradle/build-logic/src/main/kotlin/CrossLanguageBindingReceipt.kt",
            "gradle/build-logic/src/main/kotlin/CrossLanguageCAbiBootstrapEvidence.kt",
            "gradle/build-logic/src/main/kotlin/codexagent.native-wrapper-sdk.gradle.kts",
        ):
            with self.subTest(path=path):
                self.assertEqual(
                    all_desktop_tests,
                    {
                        lane
                        for lane in matching_lanes(path, "test")
                        if lane.startswith("desktop-")
                    },
                )

        for path in (
            "codex-agent-core/src/jvmAndAndroidMain/kotlin/io/github/codex_agent_labs/"
            "codexagent/agent/CodexJava.kt",
            "codex-agent-core/src/jvmTest/kotlin/io/github/codex_agent_labs/"
            "codexagent/agent/CodexPublicApiAdoptionTest.kt",
            "gradle/build-logic/src/main/kotlin/codexagent.core-verification.gradle.kts",
            "runtime/build-logic/src/main/kotlin/codexagent.desktop-runtime.gradle.kts",
        ):
            with self.subTest(path=path):
                self.assertEqual(
                    {"desktop-macos-arm64"},
                    {
                        lane
                        for lane in matching_lanes(path, "test")
                        if lane.startswith("desktop-")
                    },
                )

        native_interop = "codex-agent-runtime-desktop/src/nativeInterop/cinterop/codex_agent_c.def"
        self.assertEqual(
            {
                "desktop-macos-arm64", "desktop-macos-x64", "desktop-linux-arm64",
                "desktop-linux-x64", "desktop-windows-x64", "consumer-desktop",
            },
            matching_lanes(native_interop, "production"),
        )

    def test_objective_c_consumer_has_exact_existing_apple_lane_owners(self) -> None:
        root = CI_ROOT.parent
        consumers = (
            "codex-agent-runtime-ios/apple/Tests/CodexAgentObjectiveCConsumer/"
            "CodexAgentObjectiveCConsumer.m",
            "codex-agent-runtime-ios/apple/Tests/CodexAgentObjectiveCConsumer/"
            "include/CodexAgentObjectiveCConsumer.h",
        )

        def matching_lanes(path: str, category: str) -> set[str]:
            return {
                lane
                for lane in LANES
                if any(
                    fnmatch.fnmatchcase(path, spec)
                    for spec in effective_pathspecs(root, lane, category)
                )
            }

        for consumer in consumers:
            with self.subTest(consumer=consumer):
                self.assertEqual(
                    {"ios-swift-build", "ios-swift-tests"},
                    matching_lanes(consumer, "test"),
                )
                self.assertEqual(
                    {"ios-package", "ios-privacy-metrics"},
                    matching_lanes(consumer, "production"),
                )
                self.assertEqual(set(), matching_lanes(consumer, "metadata"))

    def test_build_logic_sources_have_explicit_narrow_owners(self) -> None:
        root = CI_ROOT.parent

        def matching_lanes(category: str, path: str) -> set[str]:
            return {
                lane
                for lane in LANES
                if any(
                    fnmatch.fnmatchcase(path, spec)
                    for spec in effective_pathspecs(root, lane, category)
                )
            }

        def direct_matching_lanes(category: str, path: str) -> set[str]:
            owners = set()
            for lane in LANES:
                pathspec = root / "ci/lanes" / f"{lane}.{category}.pathspec"
                if pathspec.is_file() and any(
                    fnmatch.fnmatchcase(path, spec)
                    for spec in pathspec.read_text(encoding="utf-8").splitlines()
                    if spec
                ):
                    owners.add(lane)
            return owners

        release_only_sources = (
            "CandidateCiProvenance.kt",
            "CandidateManifestValidation.kt",
            "CandidateModel.kt",
            "CandidatePayloadTasks.kt",
            "CandidateRuntimeEvidence.kt",
            "CentralPortalTask.kt",
            "PromotedCandidateTasks.kt",
            "ReleaseToolingCli.kt",
        )
        prefix = "gradle/build-logic/src/main/kotlin/"
        for filename in release_only_sources:
            with self.subTest(filename=filename):
                self.assertEqual({"contracts"}, matching_lanes("production", prefix + filename))

        cli = prefix + "ReleaseToolingCli.kt"
        self.assertEqual(
            {
                "desktop-macos-arm64", "desktop-macos-x64", "desktop-linux-arm64",
                "desktop-linux-x64", "desktop-windows-x64", "ios-swift-tests",
            },
            matching_lanes("test", cli),
        )
        self.assertEqual(set(), matching_lanes("metadata", cli))

        self.assertEqual(
            {
                "contracts", "ios-rust-device", "ios-rust-simulator",
                "ios-framework-device", "ios-framework-simulator",
                "ios-kotlin-tests", "ios-swift-build", "ios-swift-tests",
                "ios-package", "ios-privacy-metrics",
                "consumer-ios-device", "consumer-ios-simulator",
            },
            matching_lanes("production", prefix + "AppleReleaseCheckTasks.kt"),
        )
        self.assertEqual(
            {"contracts", "consumer-common"},
            matching_lanes("production", prefix + "MavenRepositoryTasks.kt"),
        )
        self.assertEqual(
            set(LANES),
            matching_lanes("production", "gradle/libs.versions.toml"),
        )
        shared_release_io = "gradle/build-logic/src/main/kotlin/ReleaseIo.kt"
        self.assertEqual(set(LANES), matching_lanes("production", shared_release_io))
        self.assertEqual(
            {"contracts"},
            matching_lanes("test", shared_release_io),
        )
        javascript_sdk = prefix + "codexagent.javascript-sdk.gradle.kts"
        self.assertEqual(
            {"contracts", "node-js", "consumer-node-js"},
            matching_lanes("production", javascript_sdk),
        )
        self.assertEqual({"node-js"}, matching_lanes("test", javascript_sdk))
        self.assertEqual(set(), matching_lanes("metadata", javascript_sdk))
        common_desktop_test = (
            "codex-agent-runtime-desktop/src/commonTest/kotlin/"
            "io/github/codex_agent_labs/codexagent/appserver/runtime/ExternalProcessCodexRuntimeTest.kt"
        )
        self.assertEqual(
            {
                "portable", "node-js", "node-wasm",
                "desktop-macos-arm64", "desktop-macos-x64",
                "desktop-linux-arm64", "desktop-linux-x64", "desktop-windows-x64",
                "ios-swift-tests",
            },
            matching_lanes("test", common_desktop_test),
        )
        self.assertEqual(set(), matching_lanes("production", common_desktop_test))
        self.assertEqual(set(), matching_lanes("metadata", common_desktop_test))
        shared_host_policy_test = (
            "codex-agent-runtime-desktop/src/commonTest/kotlin/"
            "io/github/codex_agent_labs/codexagent/appserver/runtime/host/SharedHostPolicyTest.kt"
        )
        self.assertEqual(
            matching_lanes("test", common_desktop_test),
            matching_lanes("test", shared_host_policy_test),
        )
        desktop_host_files_test = (
            "codex-agent-runtime-desktop/src/desktopTest/kotlin/"
            "io/github/codex_agent_labs/codexagent/appserver/runtime/host/DesktopHostFilesSecurityTest.kt"
        )
        self.assertEqual(
            {
                "portable", "desktop-macos-arm64", "desktop-macos-x64",
                "desktop-linux-arm64", "desktop-linux-x64", "desktop-windows-x64",
            },
            matching_lanes("test", desktop_host_files_test),
        )
        web_host_files_test = (
            "codex-agent-runtime-desktop/src/webTest/kotlin/"
            "io/github/codex_agent_labs/codexagent/appserver/runtime/NodeHostFilesSecurityTest.kt"
        )
        self.assertEqual(
            {"portable", "node-js", "node-wasm"},
            matching_lanes("test", web_host_files_test),
        )
        for test_path in (shared_host_policy_test, desktop_host_files_test, web_host_files_test):
            self.assertEqual(set(), matching_lanes("production", test_path))
            self.assertEqual(set(), matching_lanes("metadata", test_path))
        self.assertEqual(
            {"contracts", "portable", "consumer-common", "consumer-desktop"},
            matching_lanes(
                "production",
                "codex-agent-core/src/jvmMain/kotlin/io/github/codex_agent_labs/ClientJvm.kt",
            ),
        )
        codex_java_source = (
            "codex-agent-core/src/jvmAndAndroidMain/kotlin/"
            "io/github/codex_agent_labs/codexagent/agent/CodexJava.kt"
        )
        self.assertEqual(
            {
                "contracts", "android", "portable",
                "consumer-common", "consumer-android", "consumer-desktop",
            },
            matching_lanes("production", codex_java_source),
        )
        self.assertEqual(
            {"contracts", "desktop-macos-arm64", "ios-swift-tests"},
            matching_lanes("test", codex_java_source),
        )
        self.assertEqual(
            {"portable", "consumer-desktop"},
            matching_lanes(
                "production",
                "codex-agent-runtime-desktop/src/jvmMain/kotlin/"
                "io/github/codex_agent_labs/codexagent/agent/runtime/DesktopCodexJava.kt",
            ),
        )

        parity_inputs = (
            prefix + "CrossLanguageBindingAudit.kt",
            prefix + "PrepareCodexRuntimeTask.kt",
            "gradle/build-logic/src/test/kotlin/CrossLanguageBindingAuditTest.kt",
            "codex-agent-core/src/commonMain/kotlin/sample/Canonical.kt",
            "codex-agent-core/src/commonTest/kotlin/sample/CanonicalTest.kt",
            "codex-agent-core/src/jvmAndAndroidMain/kotlin/sample/CodexJava.kt",
            "codex-agent-core/src/jvmMain/kotlin/sample/JvmProjection.kt",
            "codex-agent-core/src/androidMain/kotlin/sample/AndroidProjection.kt",
            "codex-agent-core/src/nativeMain/kotlin/sample/NativeProjection.kt",
            "codex-agent-core/src/wasmJsMain/kotlin/sample/WasmProjection.kt",
            "codex-agent-core/src/jvmTest/java/sample/CodexJavaApiTest.java",
            "codex-agent-runtime-android/src/main/kotlin/sample/AndroidCodexJava.kt",
        )
        for path in parity_inputs:
            with self.subTest(parity_input=path):
                self.assertIn("contracts", matching_lanes("production", path))
        for runtime_path in (
            "runtime/build-logic/src/main/kotlin/GenerateDesktopDistributionSourceTask.kt",
            "runtime/build-logic/src/main/kotlin/codexagent.desktop-runtime.gradle.kts",
            "codex-agent-runtime-desktop/src/commonMain/kotlin/sample/DesktopCommon.kt",
            "codex-agent-runtime-desktop/src/desktopMain/kotlin/sample/Desktop.kt",
            "codex-agent-runtime-desktop/src/jvmMain/kotlin/sample/DesktopCodexJava.kt",
            "codex-agent-runtime-desktop/codex-app-server-distributions.json",
        ):
            with self.subTest(runtime_input=runtime_path):
                self.assertNotIn("contracts", direct_matching_lanes("production", runtime_path))

        runtime_owners = {
            "portable", "node-js", "node-wasm",
            "desktop-macos-arm64", "desktop-macos-x64", "desktop-linux-arm64",
            "desktop-linux-x64", "desktop-windows-x64",
        }
        for runtime_path in (
            "runtime/settings.gradle.kts",
            "runtime/build.gradle.kts",
            "runtime/gradle.properties",
            "runtime/settings-gradle.lockfile",
            "runtime/build-logic/build.gradle.kts",
            "runtime/build-logic/settings.gradle.kts",
            "runtime/build-logic/src/main/kotlin/DesktopRuntimeEvidenceGradleTasks.kt",
            "runtime/build-logic/src/main/kotlin/codexagent.desktop-runtime.gradle.kts",
        ):
            with self.subTest(standalone_runtime_input=runtime_path):
                self.assertEqual(
                    runtime_owners,
                    direct_matching_lanes("production", runtime_path),
                )

        self.assertEqual(
            {"contracts"},
            direct_matching_lanes("production", "ci/products/test_results.py"),
        )
        self.assertEqual(
            runtime_owners,
            direct_matching_lanes(
                "production", "runtime/build-logic/src/main/kotlin/JvmRuntimeEvidenceModel.kt",
            ),
        )
        self.assertEqual(
            runtime_owners,
            direct_matching_lanes(
                "production", "runtime/build-logic/src/main/kotlin/NodeRuntimeEvidenceModel.kt",
            ),
        )
        self.assertEqual(
            {
                "contracts", "desktop-macos-arm64", "desktop-macos-x64",
                "desktop-linux-arm64", "desktop-linux-x64", "desktop-windows-x64",
                "consumer-desktop",
            },
            direct_matching_lanes(
                "production", "ci/products/c_abi.py",
            ),
        )

        self.assertEqual(
            {"node-js"},
            direct_matching_lanes("production", javascript_sdk),
        )
        self.assertEqual(
            {
                "desktop-macos-arm64", "desktop-macos-x64", "desktop-linux-arm64",
                "desktop-linux-x64", "desktop-windows-x64",
            },
            direct_matching_lanes(
                "production", prefix + "codexagent.native-wrapper-sdk.gradle.kts",
            ),
        )
        self.assertEqual(
            {"contracts"},
            direct_matching_lanes(
                "production", prefix + "VerifyImportedSdkBindingParityTask.kt",
            ),
        )
        self.assertEqual(
            {"contracts"},
            matching_lanes("production", prefix + "CrossLanguageJavaBindingEvidence.kt"),
        )
        self.assertEqual(
            {"contracts"},
            matching_lanes(
                "production",
                "gradle/build-logic/src/test/kotlin/CrossLanguageJavaBindingEvidenceTest.kt",
            ),
        )

        canonical_receipt_evidence_inputs = (
            prefix + "CrossLanguageApiCoverage.kt",
            prefix + "CrossLanguageBindingParity.kt",
            prefix + "CrossLanguageBindingReceipt.kt",
            prefix + "CrossLanguageJavaScriptBindingEvidence.kt",
            prefix + "codexagent.core-verification.gradle.kts",
        )
        for path in canonical_receipt_evidence_inputs:
            with self.subTest(canonical_receipt_evidence_input=path):
                self.assertEqual(
                    {"contracts", "node-js", "consumer-node-js"},
                    matching_lanes("production", path),
                )
                self.assertEqual(
                    {"contracts", "node-js", "ios-swift-tests"} | (
                        {
                            "desktop-macos-arm64", "desktop-macos-x64", "desktop-linux-arm64",
                            "desktop-linux-x64", "desktop-windows-x64",
                        }
                        if Path(path).name.startswith("CrossLanguage")
                        else {"desktop-macos-arm64"}
                    ),
                    matching_lanes("test", path),
                )

        canonical_behavior_inputs = {
            "codex-agent-core/src/commonMain/kotlin/sample/Canonical.kt": {
                "contracts", "node-js", "ios-swift-tests", "desktop-macos-arm64",
                "desktop-macos-x64", "desktop-linux-arm64", "desktop-linux-x64",
                "desktop-windows-x64",
            },
            "codex-agent-core/src/commonTest/kotlin/sample/CanonicalTest.kt": {
                "contracts", "node-js", "desktop-macos-arm64",
                "desktop-macos-x64", "desktop-linux-arm64", "desktop-linux-x64",
                "desktop-windows-x64", "ios-kotlin-tests", "ios-swift-tests",
            },
            "codex-agent-core/src/jvmTest/kotlin/sample/CanonicalJvmTest.kt": {
                "contracts", "node-js", "desktop-macos-arm64", "ios-swift-tests",
            },
        }
        for path, test_lanes in canonical_behavior_inputs.items():
            with self.subTest(canonical_behavior_input=path):
                self.assertIn("node-js", matching_lanes("production", path))
                self.assertEqual(test_lanes, matching_lanes("test", path))

        self.assertIn(
            "contracts",
            matching_lanes(
                "production",
                "codex-agent-runtime-android/src/main/kotlin/"
                "io/github/codex_agent_labs/codexagent/agent/runtime/AndroidCodexJava.kt",
            ),
        )

        imported = prefix + "ImportedAppleFrameworkTasks.kt"
        self.assertEqual(
            {"ios-swift-build", "ios-swift-tests", "ios-package", "ios-privacy-metrics"},
            matching_lanes("production", imported),
        )
        self.assertEqual({"contracts"}, matching_lanes("test", imported))

        apple_compiler_sources = (
            prefix + "AppleCompilerEvidenceTask.kt",
            prefix + "codexagent.ios-runtime.gradle.kts",
        )
        for source in apple_compiler_sources:
            with self.subTest(apple_compiler_source=source):
                self.assertEqual({"contracts", "ios-swift-tests"}, matching_lanes("test", source))
        apple_compiler_task = prefix + "AppleCompilerEvidenceTask.kt"
        self.assertEqual(set(), matching_lanes("production", apple_compiler_task))
        self.assertEqual(set(), matching_lanes("metadata", apple_compiler_task))
        for consumer in (
            "codex-agent-runtime-ios/apple/CompilerEvidence/CodexFailureSwiftConsumer.swift",
            "codex-agent-runtime-ios/apple/CompilerEvidence/CodexFailureObjectiveCConsumer.m",
        ):
            with self.subTest(apple_compiler_consumer=consumer):
                self.assertEqual({"ios-swift-tests"}, matching_lanes("test", consumer))
                self.assertEqual(set(), matching_lanes("production", consumer))
                self.assertEqual(set(), matching_lanes("metadata", consumer))

        gradle_tasks = prefix + "ReleaseToolingGradleTasks.kt"
        self.assertEqual(
            {
                "ios-rust-device", "ios-rust-simulator",
                "ios-framework-device", "ios-framework-simulator",
                "ios-kotlin-tests", "ios-swift-build", "ios-swift-tests",
                "ios-package", "ios-privacy-metrics",
                "consumer-common", "consumer-android", "consumer-desktop",
                "consumer-ios-device", "consumer-ios-simulator",
                "consumer-node-js", "consumer-node-wasm",
            },
            matching_lanes("production", gradle_tasks),
        )
        self.assertEqual(
            {
                "contracts", "desktop-macos-arm64", "desktop-macos-x64",
                "desktop-linux-x64", "desktop-windows-x64",
            },
            matching_lanes("test", gradle_tasks),
        )

        future_source = prefix + "FutureProductionTask.kt"
        for category in ("production", "test", "metadata"):
            self.assertEqual(set(), matching_lanes(category, future_source))

    def test_real_base_to_fixed_head_allows_same_pr_repair_reuse(self) -> None:
        repository = CI_ROOT.parent

        def git(root: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                ["git", *arguments],
                cwd=root,
                check=check,
                capture_output=True,
                text=True,
            )

        def authorization(
            base_commit: str,
            target_commit: str,
            pull_request: int = 13,
        ) -> dict[str, object]:
            repository = "codex-agent-labs/codex-agent"
            return {
                "event_payload": {
                    "action": "labeled",
                    "label": {"name": "ci:remote-final"},
                    "number": pull_request,
                    "repository": {"full_name": repository},
                    "pull_request": {
                        "number": pull_request,
                        "draft": False,
                        "merge_commit_sha": target_commit,
                        "labels": [
                            {"name": "merge-ready"},
                            {"name": "ci:remote-final"},
                        ],
                        "base": {
                            "sha": base_commit,
                            "repo": {"full_name": repository, "fork": False},
                        },
                        "head": {
                            "sha": target_commit,
                            "repo": {"full_name": repository, "fork": False},
                        },
                    },
                },
                "github_ref": f"refs/pull/{pull_request}/merge",
                "github_sha": target_commit,
                "dispatch_approved": False,
            }

        base_result = git(repository, "merge-base", "HEAD", "origin/main", check=False)
        if base_result.returncode:
            self.skipTest("origin/main history is unavailable in this checkout")
        base = base_result.stdout.strip()
        target = git(repository, "rev-parse", "HEAD").stdout.strip()

        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            clone = temporary_root / "repository"
            subprocess.run(
                ["git", "clone", "--shared", "--quiet", str(repository), str(clone)],
                check=True,
                capture_output=True,
                text=True,
            )
            git(clone, "checkout", "--quiet", "--detach", target)
            git(clone, "config", "user.email", "ci@example.invalid")
            git(clone, "config", "user.name", "CI Fixture")

            for source in (CI_ROOT / "lanes").glob("*.pathspec"):
                shutil.copy2(source, clone / "ci/lanes" / source.name)
            shutil.copy2(CI_ROOT / "impact.py", clone / "ci/impact.py")
            shutil.copy2(CI_ROOT / "tests/test_ci.py", clone / "ci/tests/test_ci.py")
            if git(clone, "status", "--porcelain", "--", "ci/impact.py", "ci/lanes", "ci/tests/test_ci.py").stdout:
                git(clone, "add", "--", "ci/impact.py", "ci/lanes", "ci/tests/test_ci.py")
                git(clone, "commit", "--quiet", "-m", "Classify build logic inputs")
            fixed_target = git(clone, "rev-parse", "HEAD").stdout.strip()

            prior_path = clone / "build/test-plans/prior/impact-plan.json"
            prior = plan(
                root=clone,
                base=base,
                target=fixed_target,
                head=fixed_target,
                event="pull_request",
                pull_request=13,
                force_full=True,
                require_android_evidence=True,
                repository="codex-agent-labs/codex-agent",
                output=prior_path,
                **authorization(base, fixed_target),
            )
            self.assertEqual([], prior["unknownPaths"])
            self.assertTrue(all(state["reuseAllowed"] for state in prior["lanes"].values()))

            package_swift = clone / "Package.swift"
            package_swift.write_text(
                package_swift.read_text(encoding="utf-8") + "\n// same-PR checksum repair\n",
                encoding="utf-8",
            )
            git(clone, "add", "--", "Package.swift")
            git(clone, "commit", "--quiet", "-m", "Repair Swift checksum metadata")
            repair_target = git(clone, "rev-parse", "HEAD").stdout.strip()
            repair_path = clone / "build/test-plans/repair/impact-plan.json"
            repair = plan(
                root=clone,
                base=base,
                target=repair_target,
                head=repair_target,
                event="pull_request",
                pull_request=13,
                force_full=True,
                require_android_evidence=True,
                repository="codex-agent-labs/codex-agent",
                output=repair_path,
                **authorization(base, repair_target),
            )
            self.assertEqual([], repair["unknownPaths"])
            self.assertTrue(all(state["reuseAllowed"] for state in repair["lanes"].values()))

            receipt_root = temporary_root / "successful-android"
            receipt_root.mkdir()
            (receipt_root / "product.bin").write_text("product\n", encoding="utf-8")
            create_receipt(Namespace(
                plan=prior_path,
                lane="android",
                output=receipt_root,
                workflow_path=".github/workflows/ci.yml",
                artifact_name=f"codex-agent-ci-android-{prior['validationTree']}",
                run_id=101,
                run_attempt=1,
                runner=["os=Linux", "arch=X64"],
                toolchain=["java=25", "gradle=9.4.1", "validationActions=build,metadata,test"],
                artifact=["product.bin=binary"],
                evidence=[],
            ))
            validate_receipt(
                receipt_root / "lane-receipt.json",
                repair_path,
                receipt_root,
                "android",
                allow_compatible=True,
                runner={"os": "Linux", "arch": "X64"},
                toolchain={"java": "25", "gradle": "9.4.1"},
            )

            future_relative = "gradle/build-logic/src/main/kotlin/FutureProductionTask.kt"
            future = clone / future_relative
            future.write_text("class FutureProductionTask\n", encoding="utf-8")
            git(clone, "add", "--", future_relative)
            git(clone, "commit", "--quiet", "-m", "Add unmapped production build logic")
            unknown_target = git(clone, "rev-parse", "HEAD").stdout.strip()
            unknown = plan(
                root=clone,
                base=base,
                target=unknown_target,
                head=unknown_target,
                event="pull_request",
                pull_request=13,
                force_full=False,
                require_android_evidence=True,
                repository="codex-agent-labs/codex-agent",
                output=clone / "build/test-plans/unknown/impact-plan.json",
                **authorization(base, unknown_target),
            )
            self.assertEqual([future_relative], unknown["unknownPaths"])
            self.assertTrue(unknown["full"])
            self.assertTrue(all(not state["reuseAllowed"] for state in unknown["lanes"].values()))


class StageArchiveTest(unittest.TestCase):
    def test_desktop_lanes_stage_exact_c_abi_sdk_and_host_proof(self) -> None:
        targets = {
            "desktop-macos-arm64": "macos-arm64",
            "desktop-macos-x64": "macos-x64",
            "desktop-linux-arm64": "linux-arm64",
            "desktop-linux-x64": "linux-x64",
            "desktop-windows-x64": "windows-x64",
        }
        expected_sdks = set()
        expected_proofs = set()
        for lane, classifier in targets.items():
            with self.subTest(lane=lane):
                sdk = (
                    "build",
                    f"codex-agent-runtime-desktop/build/distributions/*-c-abi-{classifier}.zip",
                    "c-abi-sdk",
                )
                proof = (
                    "test",
                    "codex-agent-runtime-desktop/build/reports/cross-language-api/c-abi/"
                    f"packages/c-abi-package-{classifier}.json",
                    "c-abi-package-proof",
                )
                expected_sdks.add((lane, sdk))
                expected_proofs.add((lane, proof))
                self.assertEqual(1, OUTPUTS[lane].count(sdk))
                self.assertEqual(1, OUTPUTS[lane].count(proof))
                package_stage = (
                    "build",
                    "codex-agent-runtime-desktop/build/product-stage/runtime/"
                    f"{classifier}/package/**/*",
                    "runtime-package-stage-member",
                )
                validation_stage = (
                    "test",
                    "codex-agent-runtime-desktop/build/product-stage/runtime/"
                    f"{classifier}/validation/**/*",
                    "runtime-validation-stage-member",
                )
                binary_stage = (
                    "build",
                    "codex-agent-runtime-desktop/build/product-stage/runtime/"
                    f"{classifier}/binary/**/*",
                    "runtime-binary-stage-member",
                )
                self.assertEqual(1, OUTPUTS[lane].count(binary_stage))
                self.assertEqual(1, OUTPUTS[lane].count(package_stage))
                self.assertEqual(1, OUTPUTS[lane].count(validation_stage))

                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    for _, pattern, _ in (sdk, proof):
                        with self.subTest(pattern=pattern), self.assertRaisesRegex(
                            ValueError, "Required lane output did not match",
                        ):
                            copy_matches(root, root / "staged", pattern)

        self.assertEqual(expected_sdks, {
            (lane, output)
            for lane, outputs in OUTPUTS.items()
            for output in outputs
            if output[2] == "c-abi-sdk"
        })
        self.assertEqual(expected_proofs, {
            (lane, output)
            for lane, outputs in OUTPUTS.items()
            for output in outputs
            if output[2] == "c-abi-package-proof"
        })

    def test_macos_arm64_stages_exact_c_abi_bootstrap_evidence(self) -> None:
        observed = (
            (
                "test",
                "codex-agent-runtime-desktop/build/reports/cross-language-api/c-abi/bootstrap-evidence.json",
                "cross-language-c-abi-bootstrap-evidence",
            ),
            (
                "test",
                "codex-agent-runtime-desktop/build/reports/cross-language-api/c-abi/c-abi-scenarios.json",
                "cross-language-c-abi-scenario-proof",
            ),
        )
        for output in observed:
            self.assertEqual(1, OUTPUTS["desktop-macos-arm64"].count(output))
            self.assertFalse(any(
                output in outputs
                for lane, outputs in OUTPUTS.items()
                if lane != "desktop-macos-arm64"
            ))

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for _, pattern, _ in observed:
                with self.subTest(pattern=pattern), self.assertRaisesRegex(
                    ValueError, "Required lane output did not match",
                ):
                    copy_matches(root, root / "staged", pattern)

    def test_contracts_stages_only_legacy_binding_inputs_not_the_independent_product(self) -> None:
        expected = (
            ("build", "gradle/build-logic/build/libs/codex-agent-release-tooling.jar", "release-tooling"),
            ("test", "codex-agent-core/build/reports/cross-language-api/canonical-api.json", "cross-language-api-report-evidence"),
            ("test", "codex-agent-core/build/reports/cross-language-api/canonical-coverage.json", "cross-language-coverage-receipt-evidence"),
            ("test", "codex-agent-core/build/reports/cross-language-api/bindings/kotlin-parity.json", "cross-language-kotlin-binding-receipt-evidence"),
        )
        self.assertEqual(expected, OUTPUTS["contracts"])

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in (
                "gradle/build-logic/build/libs/codex-agent-release-tooling.jar",
                "codex-agent-core/build/reports/cross-language-api/canonical-api.json",
                "codex-agent-core/build/reports/cross-language-api/canonical-coverage.json",
                "codex-agent-core/build/reports/cross-language-api/bindings/kotlin-parity.json",
            ):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}\n", encoding="utf-8")
            clean = root / "clean-staged"
            for _, pattern, _ in expected:
                copy_matches(root, clean, pattern)
            self.assertEqual(
                ["canonical-api.json", "canonical-coverage.json", "kotlin-parity.json"],
                sorted(path.name for path in (clean / "payload").rglob("*.json")),
            )

            # Stale outputs must not rejoin the legacy contracts artifact.
            for relative in (
                "build/product-stage/contract/contract/binary/output-manifest.json",
                "build/product-stage/contract/contract/binary/outputs/evidence/canonical-api.json",
                "codex-agent-core/build/reports/cross-language-api/bindings/java-parity.json",
            ):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}\n", encoding="utf-8")
            output = root / "staged-with-stale"
            for _, pattern, _ in expected:
                copy_matches(root, output, pattern)
            names = [path.name for path in (output / "payload").rglob("*.json")]
            for name in ("canonical-api.json", "canonical-coverage.json", "kotlin-parity.json"):
                self.assertEqual(1, names.count(name), name)
            self.assertNotIn("java-parity.json", names)
            self.assertNotIn("output-manifest.json", names)

    def test_node_js_stages_exact_Runtime_binding_validation_and_rejects_missing_outputs(self) -> None:
        expected = (
            (
                "build",
                "codex-agent-runtime-desktop/build/product-stage/runtime/"
                "node-js/package/**/*",
                "runtime-package-stage-member",
            ),
            (
                "test",
                "codex-agent-runtime-desktop/build/product-stage/runtime/"
                "node-js/validation/node-js-binding/**/*",
                "runtime-binding-validation-stage-member",
            ),
        )
        self.assertEqual(expected, OUTPUTS["node-js"])
        for build, test in ((True, False), (False, True)):
            state = {"build": build, "test": test, "metadata": False}
            with self.subTest(build=build, test=test):
                self.assertTrue(selected_output("node-js", state, *expected[0][::2]))
                self.assertTrue(selected_output("node-js", state, expected[1][0], expected[1][2]))

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for _, pattern, _ in expected:
                with self.subTest(pattern=pattern):
                    with self.assertRaisesRegex(ValueError, "Required lane output did not match"):
                        copy_matches(root, root / "staged", pattern)

    def test_swift_tests_stage_exact_apple_binding_evidence_and_reject_missing_outputs(self) -> None:
        compiler_evidence = (
            "test",
            "codex-agent-runtime-ios/build/reports/cross-language-api/apple/compiler-evidence.json",
            "apple-compiler-evidence",
        )
        binding_outputs = (
            (
                "test",
                "codex-agent-runtime-ios/build/reports/cross-language-api/apple/binding-evidence.json",
                "apple-binding-evidence",
            ),
            (
                "test",
                "codex-agent-runtime-ios/build/reports/cross-language-api/bindings/swift-parity.json",
                "cross-language-swift-binding-receipt-evidence",
            ),
            (
                "test",
                "codex-agent-runtime-ios/build/reports/cross-language-api/bindings/objective-c-parity.json",
                "cross-language-objective-c-binding-receipt-evidence",
            ),
        )
        self.assertEqual((
            ("test", "codex-agent-runtime-ios/build/swift-authentication-tests-summary.json", "xctest-summary"),
            ("test", "codex-agent-runtime-ios/build/swift-authentication-tests.xcresult/**/*", "xctest-result"),
            ("test", "codex-agent-runtime-ios/build/apple-compiler-evidence-task/raw/**/*", "apple-compiler-raw-evidence"),
            ("test", "codex-agent-runtime-ios/build/swift-authentication-evidence-task/raw/**/*", "apple-xctest-raw-evidence"),
            compiler_evidence,
            *binding_outputs,
        ), OUTPUTS["ios-swift-tests"])

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for _, pattern, _ in binding_outputs:
                with self.subTest(pattern=pattern), self.assertRaisesRegex(
                    ValueError, "Required lane output did not match",
                ):
                    copy_matches(root, root / "staged", pattern)

    def test_apple_raw_execution_transport_preserves_empty_streams_and_attempts(self) -> None:
        raw_outputs = [entry for entry in OUTPUTS["ios-swift-tests"] if entry[2].endswith("raw-evidence")]
        self.assertEqual(2, len(raw_outputs))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "staged"
            for action, pattern, kind in raw_outputs:
                self.assertEqual("test", action)
                self.assertTrue(selected_output("ios-swift-tests", {"test": True}, action, kind))
                with self.assertRaisesRegex(ValueError, "Required lane output did not match"):
                    copy_matches(root, output, pattern)
                raw = root / pattern.removesuffix("/**/*")
                for attempt in ("attempt-0", "attempt-1"):
                    directory = raw / attempt / "operation"
                    directory.mkdir(parents=True)
                    (directory / "stdout.bin").write_bytes(b"\x00\xffobserved\n")
                    (directory / "stderr.bin").write_bytes(b"")
                    (directory / "execution.json").write_bytes(b'{"fixture":true}\n')
                copied = copy_matches(root, output, pattern)
                self.assertEqual(6, len(copied))
                evidence = parse_files([f"{relative}={kind}" for relative in copied], output, include_bytes=False)
                self.assertEqual(set(copied), {record["relativePath"] for record in evidence})
                self.assertTrue(all(record["kind"] == kind for record in evidence))
                for relative in copied:
                    original = root / Path(relative).relative_to("payload")
                    self.assertEqual(original.read_bytes(), (output / relative).read_bytes())

    def test_recursive_output_globs_are_python_312_compatible(self) -> None:
        self.assertFalse([
            pattern
            for outputs in OUTPUTS.values()
            for _, pattern, _ in outputs
            if pattern.endswith("/**")
        ])

    def test_swift_products_archive_preserves_modes_and_rejects_unsafe_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            products = root / "codex-agent-runtime-ios/build/swift-simulator-compilation-products"
            executable = products / "Build/Products/Debug/TestBundle.xctest/Contents/MacOS/TestBundle"
            executable.parent.mkdir(parents=True)
            executable.write_text("binary\n", encoding="utf-8")
            executable.chmod(0o755)
            resource = products / "Build/Products/Debug/TestBundle.xctest/Contents/Info.plist"
            resource.write_text("plist\n", encoding="utf-8")
            resource.chmod(0o640)
            link = resource.parent / "TestBundleLink"
            link.symlink_to("MacOS/TestBundle")

            staged = root / "staged"
            relative = archive_tree(
                root,
                staged,
                "codex-agent-runtime-ios/build/swift-simulator-compilation-products",
            )[0]
            extracted = root / "extracted"
            subprocess.run([
                sys.executable,
                str(CI_ROOT / "stage.py"),
                "extract-tar",
                "--archive", str(staged / relative),
                "--output", str(extracted),
            ], check=True)
            restored = extracted / "swift-simulator-compilation-products/Build/Products/Debug/TestBundle.xctest/Contents"
            self.assertEqual(0o755, stat.S_IMODE((restored / "MacOS/TestBundle").stat().st_mode))
            self.assertEqual(0o640, stat.S_IMODE((restored / "Info.plist").stat().st_mode))
            self.assertTrue((restored / "TestBundleLink").is_symlink())
            self.assertEqual("MacOS/TestBundle", os.readlink(restored / "TestBundleLink"))

            traversal = root / "traversal.tar"
            with tarfile.open(traversal, "w") as archive:
                archive.addfile(tarfile.TarInfo("../escape"))
            with self.assertRaisesRegex(ValueError, "Unsafe archive member"):
                safe_extract_tar(traversal, root / "unsafe-extract")
            self.assertFalse((root / "escape").exists())

            unsafe_link = root / "unsafe-link.tar"
            member = tarfile.TarInfo("products/link")
            member.type = tarfile.SYMTYPE
            member.linkname = "../../escape"
            with tarfile.open(unsafe_link, "w") as archive:
                archive.addfile(member)
            with self.assertRaisesRegex(ValueError, "Unsafe archive link target"):
                safe_extract_tar(unsafe_link, root / "unsafe-link-extract")


class StageProductionRestoreTest(unittest.TestCase):
    @staticmethod
    def source(root: Path, artifacts: list[tuple[str, str]], evidence: list[tuple[str, str]]) -> Path:
        source = root / "source"
        source.mkdir()
        for relative, _ in (*artifacts, *evidence):
            file = source / relative
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(f"source:{relative}\n", encoding="utf-8")
        (source / "lane-receipt.json").write_text(json.dumps({
            "artifacts": [
                {"relativePath": relative, "kind": kind}
                for relative, kind in artifacts
            ],
            "evidence": [
                {"relativePath": relative, "kind": kind}
                for relative, kind in evidence
            ],
        }), encoding="utf-8")
        return source

    def test_restored_production_drops_test_owned_privacy_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self.source(root, [
                ("payload/privacy/policy.json", "privacy-runtime-input"),
                ("payload/privacy/evidence.json", "privacy-runtime-input"),
            ], [])
            artifacts, evidence = restore_production_files(
                source, root / "output", "ios-privacy-metrics",
            )
            self.assertEqual({}, artifacts)
            self.assertEqual({}, evidence)
            self.assertFalse((root / "output/payload/privacy/policy.json").exists())

    def test_restored_production_drops_metadata_owned_swift_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self.source(root, [
                ("payload/CodexAgent.xcframework.zip", "swift-package-binary"),
                ("payload/CodexAgent.xcframework.zip.sha256", "swiftpm-checksum"),
            ], [])
            artifacts, _ = restore_production_files(source, root / "output", "ios-package")
            self.assertEqual(
                {"payload/CodexAgent.xcframework.zip": "swift-package-binary"},
                artifacts,
            )
            self.assertFalse((root / "output/payload/CodexAgent.xcframework.zip.sha256").exists())

    def test_restored_contracts_production_drops_binding_test_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            binding_evidence = [
                (f"payload/{kind}.json", kind)
                for kind in (
                    "cross-language-api-report-evidence",
                    "cross-language-coverage-receipt-evidence",
                    "cross-language-kotlin-binding-receipt-evidence",
                    "cross-language-java-binding-receipt-evidence",
                )
            ]
            source = self.source(root, [], binding_evidence)
            artifacts, evidence = restore_production_files(source, root / "output", "contracts")
            self.assertEqual({}, artifacts)
            self.assertEqual({}, evidence)
            self.assertFalse((root / "output/payload").exists())

    def test_restored_node_js_production_drops_Runtime_binding_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            binding_receipt = (
                "payload/javascript-typescript-parity.json",
                "cross-language-javascript-typescript-binding-receipt-evidence",
            )
            source = self.source(root, [], [binding_receipt])
            artifacts, evidence = restore_production_files(source, root / "output", "node-js")
            self.assertEqual({}, artifacts)
            self.assertEqual({}, evidence)
            self.assertFalse((root / "output" / binding_receipt[0]).exists())

    def test_restored_desktop_production_keeps_c_abi_sdk_and_drops_host_proof(self) -> None:
        targets = {
            "desktop-macos-arm64": "macos-arm64",
            "desktop-macos-x64": "macos-x64",
            "desktop-linux-arm64": "linux-arm64",
            "desktop-linux-x64": "linux-x64",
            "desktop-windows-x64": "windows-x64",
        }
        for lane, classifier in targets.items():
            with self.subTest(lane=lane), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                sdk = (f"payload/runtime-{classifier}.zip", "c-abi-sdk")
                binary_stage = (f"payload/{classifier}/binary/output-manifest.json", "runtime-binary-stage-member")
                package_stage = (f"payload/{classifier}/package/output-manifest.json", "runtime-package-stage-member")
                validation_stage = (
                    f"payload/{classifier}/validation/output-manifest.json",
                    "runtime-validation-stage-member",
                )
                proof = (f"payload/proof-{classifier}.json", "c-abi-package-proof")
                test_evidence = [proof]
                if lane == "desktop-macos-arm64":
                    test_evidence.extend((
                        ("payload/bootstrap-evidence.json", "cross-language-c-abi-bootstrap-evidence"),
                        ("payload/c-abi-scenarios.json", "cross-language-c-abi-scenario-proof"),
                    ))
                source = self.source(root, [sdk, binary_stage, package_stage], [validation_stage, *test_evidence])

                artifacts, evidence = restore_production_files(source, root / "output", lane)

                self.assertEqual({
                    sdk[0]: sdk[1],
                    binary_stage[0]: binary_stage[1],
                    package_stage[0]: package_stage[1],
                }, artifacts)
                self.assertEqual({}, evidence)
                self.assertTrue((root / "output" / sdk[0]).is_file())
                self.assertTrue((root / "output" / binary_stage[0]).is_file())
                self.assertTrue((root / "output" / package_stage[0]).is_file())
                self.assertFalse((root / "output" / validation_stage[0]).exists())
                for relative, _ in test_evidence:
                    self.assertFalse((root / "output" / relative).exists())

    def test_restored_production_keeps_build_owned_evidence(self) -> None:
        cases = (
            ("ios-rust-device", "payload/rust-proof.json", "rust-proof"),
            ("ios-swift-build", "payload/swift-build.json", "swift-build-report"),
        )
        for lane, relative, kind in cases:
            with self.subTest(lane=lane), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                source = self.source(root, [], [(relative, kind)])
                expected = {relative: kind}
                if lane == "ios-rust-device":
                    receipt_path = source / "lane-receipt.json"
                    receipt = json.loads(receipt_path.read_text())
                    receipt.update(event="pull_request", runId=7, runAttempt=1, pullRequest=31,
                                   validationCommit="a" * 40, validationTree="b" * 40,
                                   artifactName=f"codex-agent-ci-{lane}-{'b' * 40}")
                    receipt_path.write_text(json.dumps(receipt))
                    expected["transport-provenance.json"] = "transport-provenance"
                _, evidence = restore_production_files(source, root / "output", lane)
                self.assertEqual(expected, evidence)
                self.assertTrue((root / "output" / relative).is_file())

    def test_restored_production_keeps_firebase_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            relative = "payload/external/android-runtime-evidence/evidence.json"
            source = self.source(root, [], [
                (relative, "firebase-runtime-evidence"),
                ("payload/android-test-report.xml", "test-report"),
            ])
            _, evidence = restore_production_files(source, root / "output", "android")
            self.assertEqual({relative: "firebase-runtime-evidence"}, evidence)
            self.assertTrue((root / "output" / relative).is_file())
            self.assertFalse((root / "output/payload/android-test-report.xml").exists())


class ReceiptTest(GitFixture):
    def setUp(self) -> None:
        super().setUp()
        self.first_plan, self.plan_path, self.first_target = self.make_plan(
            "codex-agent-runtime-android/src/test/kotlin/Test.kt"
        )
        self.first_tree = str(self.first_plan["validationTree"])
        self.receipt_root = self.root / "artifacts/android"
        self.receipt_root.mkdir(parents=True)
        self.write("artifacts/android/product.bin", "product\n")
        evidence_path = "data.0~token=="
        self.write(f"artifacts/android/{evidence_path}", "{}\n")
        create_receipt(Namespace(
            plan=self.plan_path,
            lane="android",
            output=self.receipt_root,
            workflow_path=".github/workflows/ci.yml",
            artifact_name=f"codex-agent-ci-android-{self.first_tree}",
            run_id=101,
            run_attempt=2,
            runner=["os=Linux", "arch=X64"],
            toolchain=["java=25", "gradle=9.4.1", "validationActions=build,metadata,test"],
            artifact=["product.bin=binary"],
            evidence=[f"{evidence_path}=xctest-result"],
        ))

    def test_exact_receipt_and_aggregate(self) -> None:
        receipt = validate_receipt(
            self.receipt_root / "lane-receipt.json",
            self.plan_path,
            self.receipt_root,
            "android",
        )
        self.assertNotIn("bytes", receipt["evidence"][0])
        self.assertEqual("data.0~token==", receipt["evidence"][0]["relativePath"])
        self.assertEqual(64, len(receipt["evidence"][0]["sha256"]))
        output = self.root / "build/ci/validation-receipt.json"
        aggregate(Namespace(plan=self.plan_path, receipts=self.receipt_root.parent, output=output))
        combined = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(["android"], list(combined["lanes"]))
        self.assertEqual(101, combined["lanes"]["android"]["runId"])

        plan_value = json.loads(self.plan_path.read_text(encoding="utf-8"))
        plan_value["lanes"]["ios-privacy-metrics"]["metadata"] = True
        self.plan_path.write_text(json.dumps(plan_value), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "authoritative product-to-legacy projection"):
            aggregate(Namespace(plan=self.plan_path, receipts=self.receipt_root.parent, output=output))

    def test_required_android_evidence_is_attached_fail_closed(self) -> None:
        plan_value = json.loads(self.plan_path.read_text(encoding="utf-8"))
        plan_value["androidEvidenceRequired"] = True
        self.plan_path.write_text(json.dumps(plan_value), encoding="utf-8")
        output = self.root / "build/ci/validation-receipt.json"
        with self.assertRaisesRegex(ValueError, "Firebase runtime evidence"):
            aggregate(Namespace(plan=self.plan_path, receipts=self.receipt_root.parent, output=output))
        with self.assertRaisesRegex(ValueError, "plan artifact name mismatch"):
            with patch.object(sys, "argv", [
                "evidence.py", "check", "--artifact", str(self.receipt_root),
                "--plan", str(self.plan_path), "--expected-plan-artifact", "codex-agent-ci-plan-wrong",
            ]):
                evidence_main()
        source = self.root / "firebase"
        self.write("firebase/result.xml", "<testsuite/>\n")
        with patch.object(sys, "argv", [
            "evidence.py", "attach", "--artifact", str(self.receipt_root),
            "--plan", str(self.plan_path), "--source", str(source),
            "--expected-commit", plan_value["validationCommit"],
            "--expected-artifact", f"codex-agent-ci-android-{self.first_tree}",
        ]):
            evidence_main()
        aggregate(Namespace(plan=self.plan_path, receipts=self.receipt_root.parent, output=output))
        receipt = json.loads((self.receipt_root / "lane-receipt.json").read_text(encoding="utf-8"))
        self.assertIn("firebase-runtime-evidence", {item["kind"] for item in receipt["evidence"]})
        provenance = self.receipt_root / "transport-provenance.json"
        provenance.write_text("{}\n", encoding="utf-8")
        import hashlib
        receipt["evidence"].append({
            "relativePath": provenance.name,
            "kind": "transport-provenance",
            "sha256": hashlib.sha256(provenance.read_bytes()).hexdigest(),
        })
        (self.receipt_root / "lane-receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
        replacement = self.root / "firebase-replacement"
        self.write("firebase-replacement/trusted.xml", "<testsuite tests='2'/>")
        with patch.object(sys, "argv", [
            "evidence.py", "attach", "--artifact", str(self.receipt_root),
            "--plan", str(self.plan_path), "--source", str(replacement), "--replace",
        ]):
            evidence_main()
        self.assertFalse((self.receipt_root / "payload/external/android-runtime-evidence/result.xml").exists())
        self.assertFalse(provenance.exists())
        self.assertTrue((self.receipt_root / "payload/external/android-runtime-evidence/trusted.xml").is_file())

    def test_identical_tree_reuses_pr_aggregate_only(self) -> None:
        reusable = self.root / "reusable-validation"
        reusable.mkdir()
        (reusable / "impact-plan.json").write_bytes(self.plan_path.read_bytes())
        aggregate(Namespace(
            plan=self.plan_path,
            receipts=self.receipt_root.parent,
            output=reusable / "validation-receipt.json",
        ))
        merge_plan = json.loads(self.plan_path.read_text(encoding="utf-8"))
        merge_plan.update(
            event="merge_group",
            remoteBuildAuthorized=True,
            remoteBuildAuthorizationReason="merge-group",
        )
        current = self.root / "merge-plan.json"
        current.write_text(json.dumps(merge_plan), encoding="utf-8")
        validate_aggregate_reuse(reusable, current)
        materialized = self.root / "queue-validation.json"
        materialize(reusable, current, materialized)
        queue_receipt = json.loads(materialized.read_text(encoding="utf-8"))
        self.assertEqual("merge_group", queue_receipt["event"])
        self.assertEqual(merge_plan["validationCommit"], queue_receipt["validationCommit"])

        m8_output = self.root / "materialized-m8"
        m8_output.mkdir()
        for name in M8_FILES:
            (reusable / name).write_bytes(f"exact:{name}".encode())
        materialize(reusable, current, m8_output / "validation-receipt.json")
        for name in M8_FILES:
            self.assertEqual((reusable / name).read_bytes(), (m8_output / name).read_bytes())
        (reusable / "c-abi-parity.json").unlink()
        with self.assertRaisesRegex(ValueError, "file set mismatch"):
            validate_aggregate_reuse(reusable, current)
        for name in M8_FILES:
            (reusable / name).unlink(missing_ok=True)

        m11_output = self.root / "materialized-m11"
        m11_output.mkdir()
        for name in M11_FILES:
            (reusable / name).write_bytes(f"exact:{name}".encode())
        materialize(reusable, current, m11_output / "validation-receipt.json")
        for name in M11_FILES:
            self.assertEqual((reusable / name).read_bytes(), (m11_output / name).read_bytes())
        (reusable / "dart-parity.json").unlink()
        with self.assertRaisesRegex(ValueError, "file set mismatch"):
            validate_aggregate_reuse(reusable, current)
        for name in M11_FILES:
            (reusable / name).unlink(missing_ok=True)
        nested = reusable / "nested"
        nested.mkdir()
        (nested / "canonical-api.json").write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "only root regular files"):
            validate_aggregate_reuse(reusable, current)
        shutil.rmtree(nested)

        original_plan = (reusable / "impact-plan.json").read_bytes()
        original_receipt = (reusable / "validation-receipt.json").read_bytes()
        _, required_plan_path, _ = self.make_plan(
            "codex-agent-core/src/jvmMain/kotlin/M8.kt",
            base=self.first_target,
        )
        (reusable / "impact-plan.json").write_bytes(required_plan_path.read_bytes())
        required_receipt = json.loads(original_receipt)
        swift = dict(required_receipt["lanes"]["android"])
        swift["artifactName"] = f"codex-agent-ci-ios-swift-tests-{self.first_tree}"
        required_receipt["lanes"]["ios-swift-tests"] = swift
        (reusable / "validation-receipt.json").write_text(json.dumps(required_receipt), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "lacks required M8"):
            validate_aggregate_reuse(reusable, current)
        (reusable / "impact-plan.json").write_bytes(original_plan)
        (reusable / "validation-receipt.json").write_bytes(original_receipt)

        _, native_plan_path, _ = self.make_plan(
            "codex-agent-bindings/python/src/m11.py",
            base=self.first_target,
        )
        (reusable / "impact-plan.json").write_bytes(native_plan_path.read_bytes())
        for name in M8_FILES:
            (reusable / name).write_bytes(f"exact:{name}".encode())
        with self.assertRaisesRegex(ValueError, "lacks required M11"):
            validate_aggregate_reuse(reusable, current)
        for name in M8_FILES:
            (reusable / name).unlink()
        (reusable / "impact-plan.json").write_bytes(original_plan)

        source_plan = json.loads((reusable / "impact-plan.json").read_text(encoding="utf-8"))
        source_plan["lanes"]["portable"].update(build=True, reasons=["ci-full-label"])
        (reusable / "impact-plan.json").write_text(json.dumps(source_plan), encoding="utf-8")
        source_receipt = json.loads((reusable / "validation-receipt.json").read_text(encoding="utf-8"))
        portable = dict(source_receipt["lanes"]["android"])
        portable["artifactName"] = f"codex-agent-ci-portable-{self.first_tree}"
        source_receipt["lanes"]["portable"] = portable
        (reusable / "validation-receipt.json").write_text(json.dumps(source_receipt), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "authoritative product-to-legacy projection"):
            materialize(reusable, current, materialized)
        (reusable / "impact-plan.json").write_bytes(original_plan)
        (reusable / "validation-receipt.json").write_bytes(original_receipt)

        merge_plan["validationTree"] = "0" * 40
        current.write_text(json.dumps(merge_plan), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "tree mismatch"):
            validate_aggregate_reuse(reusable, current)
        merge_plan["validationTree"] = self.first_tree
        merge_plan["androidEvidenceRequired"] = True
        current.write_text(json.dumps(merge_plan), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "lacks required Android evidence"):
            validate_aggregate_reuse(reusable, current)

    def test_same_pr_compatible_inventory_reuses_prior_lane(self) -> None:
        current_plan, current_path, _ = self.make_plan(
            "README.md",
            "later docs\n",
            base=self.first_target,
        )
        self.assertEqual([], [lane for lane, state in current_plan["lanes"].items() if state["build"]])
        with self.assertRaisesRegex(ValueError, "mismatch"):
            validate_receipt(
                self.receipt_root / "lane-receipt.json",
                current_path,
                self.receipt_root,
                "android",
            )
        validate_receipt(
            self.receipt_root / "lane-receipt.json",
            current_path,
            self.receipt_root,
            "android",
            allow_compatible=True,
            runner={"os": "Linux", "arch": "X64"},
            toolchain={"java": "25", "gradle": "9.4.1"},
        )

    def test_size_mismatch_and_extra_file_fail_closed(self) -> None:
        self.write("artifacts/android/product.bin", "different-size\n")
        with self.assertRaisesRegex(ValueError, "integrity-mismatched"):
            validate_receipt(
                self.receipt_root / "lane-receipt.json",
                self.plan_path,
                self.receipt_root,
            )

    def test_reuse_requires_complete_canonical_action_coverage(self) -> None:
        forced_path = self.root / "build/forced/impact-plan.json"
        forced = plan(
            root=self.root,
            base=self.base,
            target=self.first_target,
            head=self.first_target,
            event="pull_request",
            pull_request=7,
            force_full=True,
            require_android_evidence=False,
            repository="codex-agent-labs/codex-agent",
            output=forced_path,
            **self.pull_request_authorization(
                base=self.base,
                target=self.first_target,
            ),
        )
        self.assertEqual(
            {"build": True, "test": True, "metadata": True},
            {action: forced["lanes"]["android"][action] for action in ("build", "test", "metadata")},
        )
        receipt_path = self.receipt_root / "lane-receipt.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["toolchain"]["validationActions"] = "build,test"
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "action coverage mismatch"):
            validate_receipt(
                receipt_path,
                forced_path,
                self.receipt_root,
                "android",
                allow_compatible=True,
            )

        receipt["toolchain"]["validationActions"] = "build,metadata,test"
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        validate_receipt(
            receipt_path,
            forced_path,
            self.receipt_root,
            "android",
            allow_compatible=True,
        )

        receipt["toolchain"]["validationActions"] = "test"
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "action coverage mismatch"):
            validate_receipt(
                receipt_path,
                self.plan_path,
                self.receipt_root,
                "android",
                allow_compatible=True,
                categories=("production",),
            )
        receipt["toolchain"]["validationActions"] = "build"
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        validate_receipt(
            receipt_path,
            self.plan_path,
            self.receipt_root,
            "android",
            allow_compatible=True,
            categories=("production",),
        )

    def test_receipt_rejects_missing_or_malformed_action_coverage(self) -> None:
        receipt_path = self.receipt_root / "lane-receipt.json"
        original = json.loads(receipt_path.read_text(encoding="utf-8"))
        for value in (None, "", "test,build", "build,unknown", "build,build"):
            with self.subTest(value=value):
                receipt = json.loads(json.dumps(original))
                if value is None:
                    receipt["toolchain"].pop("validationActions")
                else:
                    receipt["toolchain"]["validationActions"] = value
                receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "action coverage"):
                    validate_receipt(receipt_path, self.plan_path, self.receipt_root, "android")

    def test_reuse_selects_full_or_production_compatible_receipt(self) -> None:
        archive = self.root / "lane.zip"
        with zipfile.ZipFile(archive, "w") as output:
            for file in self.receipt_root.iterdir():
                output.write(file, file.name)
        artifact = {
            "name": f"codex-agent-ci-android-{self.first_tree}",
            "archive_download_url": "https://example.invalid/lane.zip",
            "digest": f"sha256:{hashlib.sha256(archive.read_bytes()).hexdigest()}",
        }

        def arguments(plan_path: Path, destination: str, mode: str) -> Namespace:
            return Namespace(
                plan=plan_path,
                lane="android",
                destination=self.root / destination,
                mode=mode,
                workflow="ci.yml",
                runner=["os=Linux", "arch=X64"],
                toolchain=["java=25", "gradle=9.4.1"],
                token="token",
                api_url="https://api.github.invalid",
            )

        with (
            patch("reuse.candidate_artifacts", return_value=[artifact]),
            patch("reuse.promoted_artifacts", return_value=[]),
            patch("reuse.api_request", return_value=archive.read_bytes()),
        ):
            exact = restore(arguments(self.plan_path, "restored-full", "full"))
            self.assertTrue(exact["reused"])

            with (
                urllib.error.HTTPError(
                    "https://api.github.invalid/promote.yml", 404, "Not Found", {}, None,
                ) as not_found,
                patch("reuse.promoted_artifacts", side_effect=promoted_artifacts),
                patch("reuse.api_json", side_effect=not_found),
            ):
                missing_promotion = restore(arguments(
                    self.plan_path, "restored-without-promotion-workflow", "full",
                ))
            self.assertTrue(missing_promotion["reused"], missing_promotion)

            with (
                urllib.error.HTTPError(
                    "https://api.github.invalid/promote.yml", 500, "Server Error", {}, None,
                ) as server_error,
                patch("reuse.promoted_artifacts", side_effect=promoted_artifacts),
                patch("reuse.api_json", side_effect=server_error),
            ):
                promotion_failure = restore(arguments(
                    self.plan_path, "rejected-promotion-failure", "full",
                ))
            self.assertFalse(promotion_failure["reused"])
            self.assertEqual("discovery-unavailable:HTTPError", promotion_failure["reason"])

            valid_digest = artifact["digest"]
            artifact["digest"] = f"sha256:{'0' * 64}"
            corrupt = restore(arguments(self.plan_path, "rejected-corrupt-transport", "full"))
            self.assertFalse(corrupt["reused"])
            self.assertIn("discovery-unavailable", corrupt["reason"])
            artifact["digest"] = valid_digest

            current_plan, current_path, _ = self.make_plan(
                "codex-agent-runtime-android/src/test/kotlin/Test.kt",
                "later test\n",
                base=self.first_target,
            )
            self.assertTrue(current_plan["lanes"]["android"]["test"])
            incompatible = restore(arguments(current_path, "not-restored", "full"))
            self.assertFalse(incompatible["reused"])
            production = restore(arguments(current_path, "restored-production", "production"))
            self.assertTrue(production["reused"])

    def test_c_abi_sdk_reuse_requires_exact_commit_and_tree_identity(self) -> None:
        receipt_path = self.receipt_root / "lane-receipt.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["artifacts"][0]["kind"] = "c-abi-sdk"
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        archive = self.root / "c-abi-sdk-lane.zip"
        with zipfile.ZipFile(archive, "w") as output:
            for file in self.receipt_root.iterdir():
                output.write(file, file.name)
        artifact = {
            "name": f"codex-agent-ci-android-{self.first_tree}",
            "archive_download_url": "https://example.invalid/c-abi-sdk-lane.zip",
            "digest": f"sha256:{hashlib.sha256(archive.read_bytes()).hexdigest()}",
        }

        def identity_variant(name: str, commit: str, tree: str) -> Path:
            root = self.root / "build" / name
            shutil.copytree(self.plan_path.parent / "inventories", root / "inventories")
            value = json.loads(self.plan_path.read_text(encoding="utf-8"))
            value.update(validationCommit=commit, validationTree=tree)
            path = root / "impact-plan.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            return path

        mismatches = {
            "commit-only": identity_variant("commit-only", "c" * 40, self.first_tree),
            "tree-only": identity_variant("tree-only", self.first_target, "d" * 40),
        }

        def arguments(plan_path: Path, destination: str, mode: str) -> Namespace:
            return Namespace(
                plan=plan_path,
                lane="android",
                destination=self.root / destination,
                mode=mode,
                workflow="ci.yml",
                runner=["os=Linux", "arch=X64"],
                toolchain=["java=25", "gradle=9.4.1"],
                token="token",
                api_url="https://api.github.invalid",
            )

        with (
            patch("reuse.candidate_artifacts", return_value=[artifact]),
            patch("reuse.promoted_artifacts", return_value=[]),
            patch("reuse.api_request", return_value=archive.read_bytes()),
        ):
            self.assertTrue(restore(arguments(
                self.plan_path, "restored-exact-c-abi-sdk", "full",
            ))["reused"])
            for mismatch, plan_path in mismatches.items():
                for mode in ("full", "production"):
                    with self.subTest(mismatch=mismatch, mode=mode):
                        restored = restore(arguments(
                            plan_path, f"rejected-{mismatch}-c-abi-sdk-{mode}", mode,
                        ))
                        self.assertFalse(restored["reused"])
                        self.assertEqual("no-compatible-artifact", restored["reason"])

    def test_failed_lane_production_artifact_is_never_full_reuse(self) -> None:
        partial_root = self.root / "partial"
        shutil.copytree(self.receipt_root, partial_root)
        partial_name = f"codex-agent-ci-android-production-{self.first_tree}"
        receipt = json.loads((partial_root / "lane-receipt.json").read_text(encoding="utf-8"))
        receipt["artifactName"] = partial_name
        (partial_root / "lane-receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
        archive = self.root / "partial.zip"
        with zipfile.ZipFile(archive, "w") as output:
            for file in partial_root.rglob("*"):
                if file.is_file():
                    output.write(file, file.relative_to(partial_root))
        artifact = {
            "name": partial_name,
            "archive_download_url": "https://example.invalid/partial.zip",
            "digest": f"sha256:{hashlib.sha256(archive.read_bytes()).hexdigest()}",
        }

        def arguments(destination: str, mode: str) -> Namespace:
            return Namespace(
                plan=self.plan_path,
                lane="android",
                destination=self.root / destination,
                mode=mode,
                workflow="ci.yml",
                runner=["os=Linux", "arch=X64"],
                toolchain=["java=25", "gradle=9.4.1"],
                token="token",
                api_url="https://api.github.invalid",
            )

        with (
            patch("reuse.candidate_artifacts", return_value=[artifact]),
            patch("reuse.promoted_artifacts", return_value=[]),
            patch("reuse.api_request", return_value=archive.read_bytes()),
        ):
            self.assertFalse(restore(arguments("partial-full", "full"))["reused"])
            self.assertTrue(restore(arguments("partial-production", "production"))["reused"])

    def test_promoted_main_artifact_reuses_across_prs(self) -> None:
        archive = self.root / "promoted.zip"
        with zipfile.ZipFile(archive, "w") as output:
            for file in self.receipt_root.iterdir():
                output.write(file, file.name)
        promoted = {
            "name": f"codex-agent-promoted-android-{self.first_target}",
            "archive_download_url": "https://example.invalid/promoted.zip",
            "digest": f"sha256:{hashlib.sha256(archive.read_bytes()).hexdigest()}",
            "_promoted": True,
        }
        _, current_path, _ = self.make_plan(
            "README.md", "next PR\n", base=self.first_target, pull_request=8,
        )
        arguments = Namespace(
            plan=current_path,
            lane="android",
            destination=self.root / "restored-promoted",
            mode="full",
            workflow="ci.yml",
            runner=["os=Linux", "arch=X64"],
            toolchain=["java=25", "gradle=9.4.1"],
            token="token",
            api_url="https://api.github.invalid",
        )
        with (
            patch("reuse.candidate_artifacts", return_value=[]),
            patch("reuse.promoted_artifacts", return_value=[promoted]),
            patch("reuse.api_request", return_value=archive.read_bytes()),
        ):
            restored = restore(arguments)
            self.assertTrue(restored["reused"])
        transported = json.loads((arguments.destination / "lane-receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(8, transported["pullRequest"])
        self.assertTrue((arguments.destination / "transport-provenance.json").is_file())

    def test_unsafe_zip_members_are_rejected(self) -> None:
        traversal = self.root / "traversal.zip"
        with zipfile.ZipFile(traversal, "w") as archive:
            archive.writestr("../escape", "bad")
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            safe_extract(traversal, self.root / "extract-traversal")

        symlink = self.root / "symlink.zip"
        member = zipfile.ZipInfo("link")
        member.create_system = 3
        member.external_attr = (stat.S_IFLNK | 0o777) << 16
        with zipfile.ZipFile(symlink, "w") as archive:
            archive.writestr(member, "target")
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            safe_extract(symlink, self.root / "extract-symlink")

    def test_validation_discovery_paginates_and_api_failures_rebuild(self) -> None:
        reusable = self.root / "reusable-validation"
        reusable.mkdir()
        (reusable / "impact-plan.json").write_bytes(self.plan_path.read_bytes())
        aggregate(Namespace(
            plan=self.plan_path,
            receipts=self.receipt_root.parent,
            output=reusable / "validation-receipt.json",
        ))
        archive = self.root / "validation.zip"
        with zipfile.ZipFile(archive, "w") as output:
            for file in reusable.rglob("*"):
                if file.is_file():
                    output.write(file, file.relative_to(reusable))
        current = json.loads(self.plan_path.read_text(encoding="utf-8"))
        current.update(
            event="merge_group",
            remoteBuildAuthorized=True,
            remoteBuildAuthorizationReason="merge-group",
        )
        current_path = self.root / "merge-plan.json"
        current_path.write_text(json.dumps(current), encoding="utf-8")
        artifact = {
            "name": f"codex-agent-ci-validation-{self.first_tree}",
            "expired": False,
        }
        calls: list[str] = []

        def api(url: str, _token: str) -> dict[str, object]:
            calls.append(url)
            if "/workflows/" in url:
                if "&page=1" in url:
                    return {"workflow_runs": [
                        {"id": index, "conclusion": "success", "pull_requests": [{"number": 99}]}
                        for index in range(100)
                    ]}
                return {"workflow_runs": [
                    {"id": 999, "run_attempt": 3, "conclusion": "success", "pull_requests": [{"number": 7}]},
                ]}
            return {"artifacts": [artifact]}

        with (
            patch("reuse.api_json", side_effect=api),
            patch("validation_reuse.download_artifact", return_value=archive.read_bytes()),
        ):
            result = discover_validation(current_path, self.root / "validation-destination", "token", "https://api.invalid")
        self.assertTrue(result["reused"])
        self.assertEqual(999, result["sourceRunId"])
        self.assertTrue(any("&page=2" in url for url in calls))

        with patch("reuse.api_json", side_effect=OSError("offline")):
            self.assertEqual(
                {"reused": False},
                discover_validation(current_path, self.root / "offline", "token", "https://api.invalid"),
            )
        with patch("reuse.api_json", return_value={"workflow_runs": "malformed"}):
            self.assertEqual(
                {"reused": False},
                discover_validation(current_path, self.root / "malformed", "token", "https://api.invalid"),
            )

    def test_m11_validation_reuse_relays_the_exact_native_wrapper_release(self) -> None:
        reusable = self.root / "reusable-m11"
        reusable.mkdir()
        source_plan, source_plan_path, _ = self.make_plan(
            "codex-agent-bindings/python/src/m11.py",
            base=self.first_target,
        )
        (reusable / "impact-plan.json").write_bytes(source_plan_path.read_bytes())
        source_tree = str(source_plan["validationTree"])
        source_receipt = json.loads((self.receipt_root / "lane-receipt.json").read_text(encoding="utf-8"))
        lane_summary = {
            key: source_receipt[key]
            for key in ("runId", "runAttempt", "validationCommit", "validationTree", "result")
        }
        validation_receipt = {
            "schemaVersion": 1,
            "repository": source_plan["repository"],
            "event": "pull_request",
            "validationCommit": source_plan["validationCommit"],
            "validationTree": source_plan["validationTree"],
            "impactPlan": "impact-plan.json",
            "lanes": {
                lane: dict(lane_summary, artifactName=f"codex-agent-ci-{lane}-{self.first_tree}")
                for lane in required_lanes(source_plan)
            },
            "result": "passed",
        }
        (reusable / "validation-receipt.json").write_text(json.dumps(validation_receipt), encoding="utf-8")
        for name in M11_FILES:
            (reusable / name).write_text(f"exact:{name}", encoding="utf-8")
        validation_archive = self.root / "validation-m11.zip"
        with zipfile.ZipFile(validation_archive, "w") as output:
            for file in reusable.iterdir():
                output.write(file, file.name)

        native_release = self.root / "native-wrapper-release"
        for directory in ("evidence", "sdks"):
            self.write(f"native-wrapper-release/{directory}/proof.txt", directory)
        for language in ("python", "csharp", "rust", "cpp", "dart"):
            self.write(f"native-wrapper-release/packages/{language}/{language}.package", language)
        native_archive = self.root / "native-wrapper-release.zip"
        with zipfile.ZipFile(native_archive, "w") as output:
            for file in native_release.rglob("*"):
                if file.is_file():
                    output.write(file, file.relative_to(native_release))

        current = dict(
            source_plan,
            event="merge_group",
            remoteBuildAuthorized=True,
            remoteBuildAuthorizationReason="merge-group",
        )
        current_path = self.root / "merge-m11-plan.json"
        current_path.write_text(json.dumps(current), encoding="utf-8")
        for summary in validation_receipt["lanes"].values():
            summary["validationCommit"] = source_plan["validationCommit"]
            summary["validationTree"] = source_tree
            summary["artifactName"] = summary["artifactName"].replace(self.first_tree, source_tree)
        (reusable / "validation-receipt.json").write_text(json.dumps(validation_receipt), encoding="utf-8")
        validation_archive.unlink(missing_ok=True)
        with zipfile.ZipFile(validation_archive, "w") as output:
            for file in reusable.iterdir():
                output.write(file, file.name)

        validation_name = f"codex-agent-ci-validation-{source_tree}"
        native_name = f"codex-agent-native-wrapper-packages-{source_tree}"
        artifacts = [
            {"name": validation_name, "expired": False},
            {"name": native_name, "expired": False},
        ]

        def api(url: str, _token: str) -> dict[str, object]:
            if "/workflows/" in url:
                return {"workflow_runs": [{
                    "id": 999,
                    "run_attempt": 3,
                    "conclusion": "success",
                    "pull_requests": [{"number": source_plan["pullRequest"]}],
                }]}
            return {"artifacts": artifacts}

        with (
            patch("reuse.api_json", side_effect=api),
            patch(
                "validation_reuse.download_artifact",
                side_effect=lambda artifact, _token: (
                    native_archive.read_bytes() if artifact["name"] == native_name
                    else validation_archive.read_bytes()
                ),
            ),
        ):
            destination = self.root / "validation-m11-destination"
            result = discover_validation(current_path, destination, "token", "https://api.invalid")
        self.assertTrue(result["reused"])
        relayed = self.root / "reused-native-wrapper-release"
        self.assertEqual(
            {"python", "csharp", "rust", "cpp", "dart"},
            {path.name for path in (relayed / "packages").iterdir()},
        )

        artifacts.pop()
        with patch("reuse.api_json", side_effect=api), patch(
            "validation_reuse.download_artifact", return_value=validation_archive.read_bytes(),
        ):
            self.assertEqual(
                {"reused": False},
                discover_validation(current_path, self.root / "missing-native", "token", "https://api.invalid"),
            )


class DiscoveryPaginationTest(unittest.TestCase):
    def test_artifact_redirect_auth_is_bound_to_the_request_origin(self) -> None:
        handler = OriginBoundRedirectHandler()
        request = urllib.request.Request(
            "https://api.github.com/repos/example/actions/artifacts/1/zip",
            headers={"Accept": "application/zip", "Authorization": "Bearer token"},
        )
        same_origin = handler.redirect_request(
            request, None, 302, "Found", {}, "https://api.github.com:443/download",
        )
        self.assertEqual("Bearer token", same_origin.get_header("Authorization"))

        for url in (
            "http://api.github.com/download",
            "https://productionresults.blob.core.windows.net/download",
            "https://api.github.com:444/download",
        ):
            with self.subTest(url=url):
                redirected = handler.redirect_request(request, None, 302, "Found", {}, url)
                self.assertIsNone(redirected.get_header("Authorization"))
                self.assertEqual("application/zip", redirected.get_header("Accept"))

    def test_lane_discovery_finds_same_pr_beyond_first_page(self) -> None:
        calls: list[str] = []
        artifact = {
            "name": "codex-agent-ci-android-tree",
            "archive_download_url": "https://api.invalid/artifact.zip",
            "expired": False,
        }

        def api(url: str, _token: str) -> dict[str, object]:
            calls.append(url)
            if "/workflows/" in url:
                if "&page=1" in url:
                    return {"workflow_runs": [
                        {"id": index, "pull_requests": [{"number": 99}]}
                        for index in range(100)
                    ]}
                return {"workflow_runs": [{"id": 999, "pull_requests": [{"number": 7}]}]}
            return {"artifacts": [artifact]}

        with patch("reuse.api_json", side_effect=api):
            result = candidate_artifacts(
                "https://api.invalid", "codex-agent-labs/codex-agent", "ci.yml",
                "android", 7, "token", None,
            )
        self.assertEqual([artifact], result)
        self.assertTrue(any("&page=2" in url for url in calls))


if __name__ == "__main__":
    unittest.main()
