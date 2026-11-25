"""Sharded, attested source-check suite: coverage, fingerprint and reuse gates."""

from __future__ import annotations

import contextlib
import io
import json
import os
from collections import Counter
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch
import zipfile

from ci.tests import source_checks as checks

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "ci") not in sys.path:
    sys.path.insert(0, str(ROOT / "ci"))
WORKFLOW = (ROOT / ".github/workflows/product-validation.yml").read_text(encoding="utf-8")


def job(name):
    return WORKFLOW.split(f"\n  {name}:\n", 1)[1].split("\n\n  ", 1)[0]


def git(root, *arguments):
    return subprocess.run(["git", *arguments], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def report(shard, executed, *, suite, tree="a" * 40, commit="b" * 40, passed=True, env=None, lint="auto"):
    lint = ({"version": checks.ACTIONLINT_VERSION, "passed": True} if shard == 0 else None) if lint == "auto" else lint
    return {"schemaVersion": 1, "kind": "codex-agent-source-check-shard", "shard": shard,
            "shards": checks.SHARDS, "commit": commit, "tree": tree,
            "environment": {"python": "3"} if env is None else env, "suite": suite,
            "assigned": checks.inventory(executed), "executed": sorted(executed), "actionlint": lint,
            "elapsedSeconds": 1.0, "moduleSeconds": {}, "result": {"testsRun": len(executed), "failures": 0, "errors": 0,
                                              "skipped": 0, "expectedFailures": 0,
                                              "unexpectedSuccesses": 0, "passed": passed}}


class SourceCheckWorkflowTest(unittest.TestCase):
    def test_matrix_runner_and_join_pin_the_same_shard_count_and_tool_versions(self):
        shards = job("workflow-source-shards")
        self.assertIn("        shard:\n" + "".join(f"          - {index}\n" for index in range(checks.SHARDS)), shards)
        self.assertIn("      fail-fast: false\n", shards)
        self.assertIn(f"--shards {checks.SHARDS} ", shards)
        for name in ("workflow-source-checks", "workflow-source-record"):
            self.assertIn(f"--shards {checks.SHARDS} ", job(name))
            self.assertIn("pattern: codex-agent-source-check-shard-*-attempt-*", job(name))
        self.assertIn("name: codex-agent-source-check-shard-${{ matrix.shard }}-attempt-${{ github.run_attempt }}", shards)
        self.assertEqual(2, WORKFLOW.count(f"actionlint@v{checks.ACTIONLINT_VERSION}"))
        self.assertIn(f"key: actionlint-v1-${{{{ runner.os }}}}-${{{{ runner.arch }}}}-v{checks.ACTIONLINT_VERSION}", shards)
        self.assertEqual(checks.JOB_NAME, "product-validation / workflow-source-checks")
        self.assertEqual(checks.RECORD_JOB_NAME, "product-validation / workflow-source-record")

    def test_no_job_that_runs_tested_code_can_sign(self):
        # Every job that executes the tested tree (shards, the tested join and
        # reuse discovery) lacks any OIDC or attestation permission.
        for name in ("workflow-source-reuse", "workflow-source-shards", "workflow-source-checks"):
            self.assertNotIn("id-token", job(name))
            self.assertNotIn("attestations", job(name))
            self.assertNotIn("secrets.", job(name))
            self.assertNotIn("actions/attest", job(name))
        self.assertIn("    permissions:\n      actions: read\n      contents: read\n    outputs:\n",
                      job("workflow-source-checks"))
        # Only the protected record job signs, and nothing in it executes the tested tree.
        signer = job("workflow-source-record")
        self.assertEqual(1, WORKFLOW.count("\n  workflow-source-record:\n"))
        self.assertIn("    permissions:\n      actions: read\n      contents: read\n"
                      "      id-token: write\n      attestations: write\n", signer)
        self.assertNotIn("secrets.", signer)
        self.assertNotIn("actions/cache", signer)
        self.assertNotIn("uses: ./", signer)
        self.assertNotIn("PYTHONPATH", signer)
        self.assertNotIn("working-directory", signer)
        steps = signer.split("\n      - ")[1:]
        uses = [line.strip() for step in steps for line in step.splitlines() if line.strip().startswith("uses:")
                or line.startswith("uses:")]
        self.assertEqual(["uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1"] * 2 + [
            "uses: actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c # v8.0.1",
            "uses: actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6 # v4.2.2",
            "uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1"], uses)
        protected = signer.split("      - id: protected\n", 1)[1].split("\n      - ", 1)[0] + "\n"
        for line in ("repository: ${{ fromJSON(toJSON(job)).workflow_repository }}",
                     "ref: ${{ fromJSON(toJSON(job)).workflow_sha }}", "path: protected-source",
                     "fetch-depth: 0", "persist-credentials: false"):
            self.assertIn(f"          {line}\n", protected)
        tested = signer.split("      - id: tested\n", 1)[1].split("\n      - ", 1)[0]
        self.assertIn("          path: tested-tree\n          persist-credentials: false", tested)
        self.assertNotIn("ref:", tested)
        self.assertLess(signer.index("id: protected"), signer.index("id: tested"))
        record = signer.split("      - id: record\n", 1)[1].split("\n      - ", 1)[0]
        script = record.split("        run: |\n", 1)[1]
        commands = [line.strip() for line in script.splitlines()
                    if line.strip() and not line.strip().startswith("#")]
        self.assertEqual(['set -euo pipefail', 'test "$NATIVE_WORKFLOW_SHA" = "$PUBLISHER_SHA"',
                          'test "$(git -C protected-source rev-parse \'HEAD^{commit}\')" = "$NATIVE_WORKFLOW_SHA"',
                          'python3 -I -B protected-source/ci/tests/source_checks.py accept --source tested-tree \\',
                          '--reports "$RUNNER_TEMP/source-check-shards" --shards 8 --publisher-sha "$PUBLISHER_SHA" \\',
                          '--record "$RUNNER_TEMP/source-check-record/source-checks.json" '
                          '--github-output "$GITHUB_OUTPUT"'], commands)
        self.assertIn("NATIVE_WORKFLOW_SHA: ${{ fromJSON(toJSON(job)).workflow_sha }}", record)
        # The signed file and the upload name both come from the protected step.
        self.assertIn("name: ${{ steps.record.outputs.artifact_name }}", signer)
        self.assertNotIn("steps.accept", signer)
        for step in steps[steps.index(next(step for step in steps if step.startswith("id: attest"))):]:
            self.assertIn("steps.record.outcome == 'success' && steps.record.outputs.record == 'true'", step)
        self.assertIn("create-storage-record: false", signer)
        # Publication never decides a result: every step after the decision may fail.
        self.assertEqual(len(steps) - 1, signer.count("continue-on-error: true"))
        self.assertNotIn("actions/cache", job("workflow-source-checks"))
        self.assertNotIn("actions/cache", job("workflow-source-reuse"))
        self.assertIn("bash .github/actions/restore-reuse-qualification/install-gh.sh", job("workflow-source-reuse"))
        # The unsigned tested-tree record is never uploaded.
        self.assertNotIn("upload-artifact", job("workflow-source-checks"))
        # Records are only signed by the exact protected publisher for same-repo PR/merge-group runs.
        publication = (signer.split("      - id: publication\n", 1)[1].split("\n      - ", 1)[0]
                       .split("\n      # ", 1)[0])
        self.assertEqual(publication, job("workflow-source-checks").split("      - id: publication\n", 1)[1]
                         .split("\n      - ", 1)[0].replace("        if: steps.mode.outputs.reused == 'false'\n", "", 1))
        for guard in ('[ "$NATIVE_WORKFLOW_SHA" = "$PUBLISHER_SHA" ]',
                      '[ "$NATIVE_WORKFLOW_PATH" = .github/workflows/product-validation.yml ]',
                      '[ "$GITHUB_REPOSITORY" = codex-agent-labs/codex-agent ]',
                      '[ "$GITHUB_EVENT_NAME" = pull_request ] && [ "$FORK" = false ]'):
            self.assertIn(guard, publication)
        script = textwrap.dedent(publication.split("        run: |\n", 1)[1])
        good = {"PLAN_RESULT": "success", "PUBLISHER_SHA": "a" * 40, "NATIVE_WORKFLOW_SHA": "a" * 40,
                "NATIVE_WORKFLOW_REPOSITORY": "codex-agent-labs/codex-agent",
                "NATIVE_WORKFLOW_PATH": ".github/workflows/product-validation.yml",
                "GITHUB_REPOSITORY": "codex-agent-labs/codex-agent", "GITHUB_EVENT_NAME": "pull_request",
                "FORK": "false"}
        cases = [({}, True), ({"GITHUB_EVENT_NAME": "merge_group", "FORK": ""}, True),
                 ({"FORK": "true"}, False), ({"FORK": ""}, False), ({"GITHUB_EVENT_NAME": "workflow_dispatch"}, False),
                 ({"NATIVE_WORKFLOW_SHA": "b" * 40}, False), ({"PLAN_RESULT": "failure"}, False),
                 ({"PUBLISHER_SHA": ""}, False), ({"NATIVE_WORKFLOW_PATH": ".github/workflows/ci.yml"}, False),
                 ({"GITHUB_REPOSITORY": "fork/codex-agent"}, False)]
        for change, expected in cases:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary) / "output"
                subprocess.run(["bash", "-c", script], check=True,
                               env={**os.environ, **good, **change, "GITHUB_OUTPUT": str(output)})
                self.assertEqual(f"publish={str(expected).lower()}\n", output.read_text())

    def test_shards_run_only_without_an_attested_pass_and_reuse_fails_open_to_execution(self):
        self.assertIn("    if: '!cancelled() && !inputs.toolingOnly && !inputs.runtimeRecoveryOnly && !inputs.sdkRecoveryOnly"
                      " && needs.workflow-source-reuse.outputs.reused != ''true'''\n", job("workflow-source-shards"))
        # The join and merge gate still run (and fail) when the suite was not completed.
        self.assertIn("    if: always() && !cancelled() && !inputs.toolingOnly && !inputs.runtimeRecoveryOnly"
                      " && !inputs.sdkRecoveryOnly\n", job("workflow-source-checks"))
        reuse = job("workflow-source-reuse")
        step = reuse.split("      - id: reuse\n", 1)[1]
        script = textwrap.dedent(step.split("        run: |\n", 1)[1])
        for change in ({"PLAN_RESULT": "failure"}, {"NATIVE_GH": "false"}, {"PUBLISHER_SHA": ""}):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary) / "output"
                env = {**os.environ, "PLAN_RESULT": "success", "NATIVE_GH": "true", "PUBLISHER_SHA": "a" * 40,
                       "GITHUB_OUTPUT": str(output), **change}
                subprocess.run(["bash", "-c", script], check=True, env=env)
                self.assertEqual("reused=false\n", output.read_text())
        self.assertIn("continue-on-error: true\n        run: bash .github/actions/restore-reuse-qualification", reuse)

    def test_remote_final_alone_arms_a_full_campaign_but_keeps_the_privileged_event_gate(self):
        expression = ("FORCE_FULL: ${{ contains(github.event.pull_request.labels.*.name, 'ci:full') || "
                      "!inputs.runtimeRecoveryOnly && !inputs.sdkRecoveryOnly && "
                      "contains(github.event.pull_request.labels.*.name, 'ci:remote-final') }}")
        self.assertEqual(2, WORKFLOW.count(expression))
        self.assertEqual(2, WORKFLOW.count("FORCE_FULL: "))
        gate = ("github.event_name == 'pull_request' && github.event.action == 'labeled' && "
                "github.event.label.name == 'ci:remote-final' && github.event.pull_request.draft == false && "
                "contains(github.event.pull_request.labels.*.name, 'merge-ready') && "
                "contains(github.event.pull_request.labels.*.name, 'ci:remote-final') && "
                "github.event.pull_request.base.repo.full_name == github.repository && "
                "github.event.pull_request.head.repo.full_name == github.repository && "
                "github.event.pull_request.head.repo.fork == false && "
                "github.ref == format('refs/pull/{0}/merge', github.event.pull_request.number)")
        self.assertEqual(2, WORKFLOW.count(gate))


class SourceCheckPartitionTest(unittest.TestCase):
    def test_partition_is_deterministic_complete_and_disjoint(self):
        modules = [f"test_m{index}" for index in range(40)] + ["test_m3"]
        weights = {"test_m1": 50, "test_m2": 40, "test_m3": 0.5}
        first = checks.partition(modules, 8, weights)
        self.assertEqual(first, checks.partition(list(reversed(modules)), 8, weights))
        flattened = [name for part in first for name in part]
        self.assertEqual(sorted(set(modules)), sorted(flattened))
        self.assertEqual(len(flattened), len(set(flattened)))
        self.assertEqual(8, len(first))
        with self.assertRaises(ValueError):
            checks.partition(modules, 0, weights)

    def test_real_suite_partition_covers_every_discovered_occurrence_once(self):
        loader = unittest.TestLoader()
        tests = list(checks._flatten(loader.discover(str(ROOT / "ci/tests"), top_level_dir=str(ROOT / "ci/tests"))))
        parts = checks.partition((checks.module_key(test) for test in tests), checks.SHARDS, checks.load_weights())
        owners = {name: index for index, part in enumerate(parts) for name in part}
        per_shard = [[test.id() for test in tests if owners[checks.module_key(test)] == index]
                     for index in range(checks.SHARDS)]
        self.assertEqual(Counter(test.id() for test in tests), sum((Counter(part) for part in per_shard), Counter()))
        self.assertTrue(all(per_shard))
        self.assertEqual(checks.inventory(test.id() for test in tests),
                         checks.inventory(value for part in per_shard for value in part))
        self.assertGreater(len(tests), 5000)

    def test_weights_name_only_discovered_modules(self):
        weights = checks.load_weights()
        modules = {path.stem for path in (ROOT / "ci/tests").glob("test*.py")}
        self.assertLessEqual(set(weights) - modules, {name for name in weights if name.startswith("ci.tests.")})


class SourceCheckJoinTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.ids = [f"test_m{index % 9}.T.test_{index}" for index in range(30)] + ["test_m1.T.test_1"]
        self.suite = checks.inventory(self.ids)
        self.parts = [sorted(self.ids[index::checks.SHARDS]) for index in range(checks.SHARDS)]

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, reports, attempt=1):
        for value in reports:
            directory = self.root / f"codex-agent-source-check-shard-{value['shard']}-attempt-{attempt}"
            directory.mkdir()
            (directory / f"shard-{value['shard']}.json").write_bytes(checks.canonical(value))

    def join(self, attempt=1):
        with patch.dict(os.environ, {"GITHUB_RUN_ATTEMPT": str(attempt)}):
            return checks.join_reports(self.root, checks.SHARDS, commit="b" * 40, tree="a" * 40)

    def test_complete_disjoint_passing_union_is_accepted_including_duplicate_occurrences(self):
        self.write([report(index, part, suite=self.suite) for index, part in enumerate(self.parts)])
        self.assertEqual((self.suite, {"python": "3"}), self.join())

    def test_every_coverage_or_result_gap_fails_closed(self):
        def missing(parts):
            parts[3] = parts[3][1:]
        def duplicate(parts):
            parts[4] = parts[4] + [parts[5][0]]
        def extra(parts):
            parts[2] = parts[2] + ["test_other.T.test_x"]
        for name, mutate, change in (("missing", missing, {}), ("duplicate", duplicate, {}), ("extra", extra, {}),
                                     ("failed", None, {"passed": False}), ("tree", None, {"tree": "c" * 40}),
                                     ("commit", None, {"commit": "c" * 40}), ("lint", None, {"lint": None}),
                                     ("suite", None, {"suite": checks.inventory(self.ids[1:])})):
            with self.subTest(name=name):
                shutil.rmtree(self.root)
                self.root.mkdir()
                parts = [list(part) for part in self.parts]
                if mutate is not None:
                    mutate(parts)
                reports = []
                for index, part in enumerate(parts):
                    values = dict(change) if index == 1 or name == "lint" and index == 0 else {}
                    reports.append(report(index, part, suite=values.pop("suite", self.suite), **values))
                self.write(reports)
                with self.assertRaises(ValueError):
                    self.join()

    def test_missing_shard_unexpected_upload_and_future_attempt_fail_closed(self):
        self.write([report(index, part, suite=self.suite) for index, part in enumerate(self.parts) if index != 7])
        with self.assertRaisesRegex(ValueError, "missing"):
            self.join()
        self.write([report(7, self.parts[7], suite=self.suite)], attempt=2)
        with self.assertRaisesRegex(ValueError, "malformed"):
            self.join(attempt=1)
        self.assertEqual(self.suite, self.join(attempt=2)[0])
        (self.root / "unexpected").mkdir()
        with self.assertRaisesRegex(ValueError, "Unexpected"):
            self.join(attempt=2)

    def test_newest_attempt_supersedes_an_earlier_report_for_the_same_shard(self):
        reports = [report(index, part, suite=self.suite) for index, part in enumerate(self.parts)]
        self.write(reports)
        self.write([report(2, self.parts[2], suite=self.suite, passed=False)], attempt=2)
        with self.assertRaises(ValueError):
            self.join(attempt=2)
        # An upload newer than the current attempt cannot exist; it fails closed.
        with self.assertRaisesRegex(ValueError, "malformed"):
            self.join(attempt=1)
        shutil.rmtree(self.root / "codex-agent-source-check-shard-2-attempt-2")
        self.write([report(2, self.parts[2], suite=self.suite)], attempt=3)
        self.assertEqual(self.suite, self.join(attempt=3)[0])

    def test_mixed_runner_images_still_pass_but_are_never_published(self):
        self.write([report(index, part, suite=self.suite, env={"python": str(index == 3)})
                    for index, part in enumerate(self.parts)])
        self.assertEqual((self.suite, None), self.join())


class SourceCheckEndToEndTest(unittest.TestCase):
    """Run the real runner and join in a miniature repository."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve() / "repo"
        tests = self.root / "ci/tests"
        (tests / "data").mkdir(parents=True)
        shutil.copy2(ROOT / "ci/tests/source_checks.py", tests / "source_checks.py")
        (tests / "data/source-check-weights.json").write_text("{}\n")
        for index in range(12):
            (tests / f"test_m{index}.py").write_text(textwrap.dedent(f"""\
                import unittest
                class T{index}(unittest.TestCase):
                    def test_a(self):
                        self.assertTrue(True)
                    def test_b(self):
                        self.assertEqual({index}, {index})
                """))
        # Imported classes run twice under discovery; both occurrences must run.
        (tests / "test_shared.py").write_text("from test_m0 import T0\n")
        (tests / "test_fixture_skip.py").write_text(textwrap.dedent("""\
            import unittest
            class Skipped(unittest.TestCase):
                @classmethod
                def setUpClass(cls):
                    raise unittest.SkipTest("fixture-level skip")
                def test_never_started(self):
                    raise AssertionError("not run")
            """))
        workflows = self.root / ".github/workflows"
        workflows.mkdir(parents=True)
        (workflows / "product-validation.yml").write_text("name: fixture\n")
        (self.root / ".gitignore").write_text("__pycache__/\n")
        for command in (["init", "-q", "-b", "main"], ["add", "-A"],
                        ["-c", "user.name=f", "-c", "user.email=f@example.invalid", "commit", "-q", "-m", "fixture"]):
            git(self.root, *command)
        self.publisher = git(self.root, "rev-parse", "HEAD")
        git(self.root, "update-ref", checks.PUBLISHER_REF, self.publisher)
        self.environment = {key: value for key, value in os.environ.items()
                            if not key.startswith(("GITHUB_", "CODEX_AGENT_"))}
        self.environment.update(PYTHONPATH="", GITHUB_RUN_ATTEMPT="1")

    def tearDown(self):
        self.temporary.cleanup()

    def run_tool(self, *arguments, env=None, check=True):
        return subprocess.run([sys.executable, "ci/tests/source_checks.py", *arguments], cwd=self.root,
                              env={**self.environment, **(env or {})}, capture_output=True, text=True, check=check)

    def run_all_shards(self, reports, shard_env=None):
        for shard in range(checks.SHARDS):
            directory = reports / f"codex-agent-source-check-shard-{shard}-attempt-1"
            lint = ["--actionlint", str(self.actionlint)] if shard == 0 else []
            result = self.run_tool("run-shard", "--shard", str(shard), "--shards", str(checks.SHARDS),
                                   "--report", str(directory / f"shard-{shard}.json"), *lint, check=False,
                                   env=shard_env(shard) if shard_env else None)
            yield shard, result

    def fake_actionlint(self, exit_code=0):
        self.actionlint = Path(self.temporary.name) / "actionlint"
        self.actionlint.write_text(f'#!/bin/sh\n[ "$1" = -version ] && echo {checks.ACTIONLINT_VERSION} && exit 0\n'
                                   f'exit {exit_code}\n')
        self.actionlint.chmod(0o755)

    def test_all_shards_cover_the_suite_and_the_record_fingerprint_matches_reuse(self):
        self.fake_actionlint()
        reports = Path(self.temporary.name) / "reports"
        for shard, result in self.run_all_shards(reports):
            self.assertEqual(0, result.returncode, result.stderr)
        executed = []
        for path in reports.rglob("shard-*.json"):
            executed += json.loads(path.read_text())["executed"]
        self.assertEqual(12 * 2 + 2 + 1, len(executed))
        self.assertEqual(2, executed.count("test_m0.T0.test_a"))
        self.assertIn("test_fixture_skip.Skipped.test_never_started", executed)
        event = Path(self.temporary.name) / "event.json"
        event.write_text(json.dumps({"pull_request": {"number": 31}}))
        commit = git(self.root, "rev-parse", "HEAD")
        producer_env = {"GITHUB_REPOSITORY": checks.REPOSITORY, "GITHUB_SHA": commit,
                        "GITHUB_WORKFLOW_REF": f"{checks.REPOSITORY}/.github/workflows/ci.yml@refs/pull/31/merge",
                        "GITHUB_EVENT_NAME": "pull_request", "GITHUB_EVENT_PATH": str(event),
                        "GITHUB_RUN_ID": "77", "GITHUB_RUN_ATTEMPT": "1"}
        record_path = Path(self.temporary.name) / "record/source-checks.json"
        output = Path(self.temporary.name) / "output"
        result = self.run_tool("accept", "--reports", str(reports), "--shards", str(checks.SHARDS),
                               "--publisher-sha", self.publisher, "--record", str(record_path),
                               "--github-output", str(output), env=producer_env)
        self.assertIn("record=true\n", output.read_text())
        record = checks.load_canonical(record_path.read_bytes())
        self.assertEqual({"repository": checks.REPOSITORY, "workflowPath": ".github/workflows/ci.yml",
                          "commit": commit, "tree": git(self.root, "rev-parse", "HEAD^{tree}"),
                          "event": "pull_request", "runId": 77, "runAttempt": 1, "pullRequest": 31},
                         record["producer"])
        printed = json.loads(self.run_tool("fingerprint", "--publisher-sha", self.publisher).stdout)
        self.assertEqual(printed["inputs"], record["inputs"])
        self.assertEqual(printed["fingerprint"], record["fingerprint"])
        self.assertIn(f"artifact_name={checks.artifact_name(record['fingerprint'], 1)}\n", output.read_text())
        # Every reuse-relevant input changes the fingerprint.
        changed = json.loads(self.run_tool("fingerprint", "--publisher-sha", self.publisher,
                                           env={"CODEX_AGENT_X": "1"}).stdout)
        self.assertNotEqual(record["fingerprint"], changed["fingerprint"])
        changed = json.loads(self.run_tool("fingerprint", "--publisher-sha", self.publisher,
                                           env={"ImageOS": "other"}).stdout)
        self.assertNotEqual(record["fingerprint"], changed["fingerprint"])
        # A different hosted build of the same image (seen across parallel shards) is not an input.
        same = json.loads(self.run_tool("fingerprint", "--publisher-sha", self.publisher,
                                        env={"ImageVersion": "20261116.133.1"}).stdout)
        self.assertEqual(record["fingerprint"], same["fingerprint"])
        # The protected copy, run from its own checkout over the tested tree as
        # data, re-derives the identical record and upload name.
        protected = Path(self.temporary.name) / "protected"
        git(Path(self.temporary.name), "clone", "-q", str(self.root), str(protected))
        git(protected, "update-ref", checks.PUBLISHER_REF, self.publisher)
        # Only the protected checkout knows the publisher branch.
        git(self.root, "update-ref", "-d", checks.PUBLISHER_REF)
        stray = Path(self.temporary.name) / "workspace"
        (stray / "tested-tree").mkdir(parents=True)
        derived_path = Path(self.temporary.name) / "derived/source-checks.json"
        derived_output = Path(self.temporary.name) / "derived-output"
        subprocess.run([sys.executable, "-I", "-B", str(protected / "ci/tests/source_checks.py"), "accept",
                        "--source", str(self.root), "--reports", str(reports), "--shards", str(checks.SHARDS),
                        "--publisher-sha", self.publisher, "--record", str(derived_path),
                        "--github-output", str(derived_output)], cwd=stray, check=True, capture_output=True,
                       env={**self.environment, **producer_env})
        self.assertEqual(record_path.read_bytes(), derived_path.read_bytes())
        self.assertEqual(output.read_text(), derived_output.read_text())
        # Without the protected publisher branch the tested tree alone cannot publish.
        failed = self.run_tool("accept", "--reports", str(reports), "--shards", str(checks.SHARDS),
                               "--publisher-sha", self.publisher, "--record", str(derived_path),
                               env=producer_env, check=False)
        self.assertNotEqual(0, failed.returncode)
        git(self.root, "update-ref", checks.PUBLISHER_REF, self.publisher)
        (self.root / "README").write_text("changed\n")
        git(self.root, "add", "README")
        git(self.root, "-c", "user.name=f", "-c", "user.email=f@example.invalid", "commit", "-q", "-m", "next")
        changed = json.loads(self.run_tool("fingerprint", "--publisher-sha", self.publisher).stdout)
        self.assertNotEqual(record["inputs"]["tree"], changed["inputs"]["tree"])
        self.assertNotEqual(record["fingerprint"], changed["fingerprint"])

    def test_shards_on_different_builds_of_one_image_still_publish_a_record(self):
        # Campaign 45201645704: shard 1 ran on 20261116.133.1, the rest on 20261116.376.1.
        self.fake_actionlint()
        reports = Path(self.temporary.name) / "reports-mixed-image"
        image = lambda shard: {"ImageOS": "ubuntu24",
                               "ImageVersion": "20261116.133.1" if shard == 1 else "20261116.376.1"}
        self.assertEqual([0] * checks.SHARDS,
                         [result.returncode for _, result in self.run_all_shards(reports, image)])
        event = Path(self.temporary.name) / "event-mixed.json"
        event.write_text(json.dumps({"pull_request": {"number": 31}}))
        output = Path(self.temporary.name) / "output-mixed"
        self.run_tool("accept", "--reports", str(reports), "--shards", str(checks.SHARDS),
                      "--publisher-sha", self.publisher,
                      "--record", str(Path(self.temporary.name) / "mixed/source-checks.json"),
                      "--github-output", str(output),
                      env={"GITHUB_REPOSITORY": checks.REPOSITORY,
                           "GITHUB_SHA": git(self.root, "rev-parse", "HEAD"),
                           "GITHUB_WORKFLOW_REF": f"{checks.REPOSITORY}/.github/workflows/ci.yml@refs/pull/31/merge",
                           "GITHUB_EVENT_NAME": "pull_request", "GITHUB_EVENT_PATH": str(event),
                           "GITHUB_RUN_ID": "78", "GITHUB_RUN_ATTEMPT": "1", "ImageOS": "ubuntu24"})
        self.assertIn("record=true\n", output.read_text())

    def test_a_failing_test_or_actionlint_fails_its_shard_and_the_join(self):
        for case in ("actionlint", "test"):
            with self.subTest(case=case):
                self.fake_actionlint(1 if case == "actionlint" else 0)
                if case == "test":
                    (self.root / "ci/tests/test_m5.py").write_text(
                        "import unittest\nclass T5(unittest.TestCase):\n    def test_a(self):\n        self.fail('x')\n")
                    git(self.root, "-c", "user.name=f", "-c", "user.email=f@example.invalid",
                        "commit", "-q", "-am", "fail")
                reports = Path(self.temporary.name) / f"reports-{case}"
                failed = [shard for shard, result in self.run_all_shards(reports) if result.returncode != 0]
                self.assertEqual(1, len(failed))
                result = self.run_tool("accept", "--reports", str(reports), "--shards", str(checks.SHARDS),
                                       check=False)
                self.assertNotEqual(0, result.returncode)

    def test_dirty_checkout_is_never_tested_as_its_commit(self):
        self.fake_actionlint()
        (self.root / "ci/tests/untracked.txt").write_text("x\n")
        result = self.run_tool("run-shard", "--shard", "1", "--shards", str(checks.SHARDS),
                               "--report", str(Path(self.temporary.name) / "r.json"), check=False)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("clean checkout", result.stderr)


class SourceCheckReuseTest(unittest.TestCase):
    """Every listed record passes the existing original-CI gates or is a miss."""

    def setUp(self):
        self.current = checks.inputs(tree="a" * 40, blob="c" * 40, env={"python": "3"},
                                     suite={"count": 3, "sha256": "sha256:" + "d" * 64})
        self.producer = {"repository": checks.REPOSITORY, "workflowPath": ".github/workflows/ci.yml",
                         "commit": "b" * 40, "tree": "a" * 40, "event": "pull_request", "runId": 70,
                         "runAttempt": 2, "pullRequest": 31}
        self.record = {"schemaVersion": 1, "kind": "codex-agent-source-checks", "result": "passed",
                       "fingerprint": checks.fingerprint(self.current), "inputs": self.current,
                       "publisherSha": "e" * 40, "producer": self.producer}
        self.members = None

    def archive(self, record=None, members=None):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            for name, raw in (members or {checks.RECORD: checks.canonical(record or self.record),
                                          checks.BUNDLE: b'{"bundle":1}\n'}).items():
                archive.writestr(name, raw)
        return stream.getvalue()

    def authenticate(self, *, record=None, members=None, name=None, blob="c" * 40, attestation=None):
        import product_reuse as products
        raw = self.archive(record, members)
        digest = "sha256:" + __import__("hashlib").sha256(raw).hexdigest()
        attempt = (record or self.record)["producer"]["runAttempt"]
        listed = {"id": 9, "name": name or checks.artifact_name(self.record["fingerprint"], attempt),
                  "digest": digest, "workflow_run": {"id": 70}, "expired": False}
        detail = {**listed, "size_in_bytes": len(raw), "archive_download_url": "https://example.invalid/zip"}
        verified = attestation if attestation is not None else [{"verificationResult": {"signature": {"certificate": {
            "runInvocationURI": f"https://github.com/{checks.REPOSITORY}/actions/runs/70/attempts/2"}}}}]
        calls = []

        def run(command, **keywords):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, json.dumps(verified).encode(), b"")
        observation = {"run": {"id": 70}, "jobs": []}
        with patch.object(products, "api_json", return_value=detail), \
                patch.object(products, "download_artifact", return_value=raw), \
                patch.object(products, "_observe_ci_producer_jobs", return_value=[observation]) as observe, \
                patch.object(products, "_contract_ci_upload_metadata", return_value=detail) as metadata, \
                patch.object(products, "_require_artifact_job_window") as window, \
                patch.object(checks, "executor_blob", return_value=blob) as executor, \
                patch.object(checks.subprocess, "run", side_effect=run):
            result = checks.authenticate(listed, self.current, "token", root=ROOT)
        return result, calls, observe, metadata, window, executor

    def test_exact_original_attempt_upload_job_and_native_signature_are_all_required(self):
        result, calls, observe, metadata, window, executor = self.authenticate()
        self.assertEqual(70, result["sourceRunId"])
        self.assertEqual(2, result["sourceRunAttempt"])
        observe.assert_called_once()
        # The tested join and the protected signer both succeeded under the exact publisher.
        self.assertEqual({"sources": self.producer, "record": self.producer}, observe.call_args.args[0])
        self.assertEqual({"sources": checks.JOB_NAME, "record": checks.RECORD_JOB_NAME},
                         observe.call_args.kwargs["jobs_by_phase"])
        trusted = {"path": ".github/workflows/product-validation.yml", "sha": "e" * 40}
        self.assertEqual({"sources": trusted, "record": trusted},
                         observe.call_args.kwargs["trusted_workflows_by_phase"])
        self.assertEqual((9,), metadata.call_args.args[:1])
        self.assertEqual(checks.artifact_name(self.record["fingerprint"], 2), metadata.call_args.args[2])
        # The upload is bound to the protected signer's window, not the tested join's.
        window.assert_called_once()
        self.assertEqual(checks.RECORD_JOB_NAME, window.call_args.args[1])
        executor.assert_called_once_with(ROOT, "e" * 40)
        command, = calls
        for pair in (("--signer-digest", "e" * 40), ("--source-digest", "b" * 40),
                     ("--signer-workflow", f"{checks.REPOSITORY}/.github/workflows/product-validation.yml"),
                     ("--cert-oidc-issuer", "https://token.actions.githubusercontent.com")):
            self.assertEqual(pair[1], command[command.index(pair[0]) + 1])
        self.assertIn("--deny-self-hosted-runners", command)

    def test_any_changed_input_identity_or_transport_is_rejected(self):
        def changed(**fields):
            value = json.loads(json.dumps(self.record))
            for path, item in fields.items():
                target = value
                *parents, leaf = path.split("__")
                for parent in parents:
                    target = target[parent]
                target[leaf] = item
            return value
        other = checks.inputs(tree="f" * 40, blob="c" * 40, env={"python": "3"},
                              suite={"count": 3, "sha256": "sha256:" + "d" * 64})
        cases = {
            "fingerprint": dict(record=changed(fingerprint="sha256:" + "0" * 64)),
            "inputs": dict(record=changed(inputs=other, fingerprint=checks.fingerprint(other))),
            "environment": dict(record=changed(inputs__environment={"python": "2"})),
            "suite": dict(record=changed(inputs__suite={"count": 2, "sha256": "sha256:" + "d" * 64})),
            "tree": dict(record=changed(producer__tree="f" * 40)),
            "dispatch": dict(record=changed(producer__event="workflow_dispatch", producer__pullRequest=None)),
            "workflow": dict(record=changed(producer__workflowPath=".github/workflows/other.yml")),
            "result": dict(record=changed(result="failed")),
            "extra-field": dict(record=changed(extra=True)),
            "name": dict(name=checks.artifact_name(self.record["fingerprint"], 1)),
            "publisher": dict(blob="0" * 40),
            "members": dict(members={checks.RECORD: checks.canonical(self.record)}),
            "extra-member": dict(members={checks.RECORD: checks.canonical(self.record), checks.BUNDLE: b"x",
                                          "other": b"y"}),
            "attempt-uri": dict(attestation=[{"verificationResult": {"signature": {"certificate": {
                "runInvocationURI": f"https://github.com/{checks.REPOSITORY}/actions/runs/70/attempts/1"}}}}]),
            "no-attestation": dict(attestation=[]),
            "noncanonical": dict(members={checks.RECORD: json.dumps(self.record).encode(), checks.BUNDLE: b"x"}),
        }
        for name, change in cases.items():
            with self.subTest(case=name), self.assertRaises((ValueError, KeyError, TypeError)):
                self.authenticate(**change)

    def test_discovery_tries_newest_candidates_and_misses_without_a_token(self):
        value = checks.fingerprint(self.current)
        with patch.object(checks, "current_inputs", return_value=self.current), \
                patch.object(checks, "git", return_value=self.current["tree"]):
            self.assertEqual({"reused": False, "fingerprint": value, "reason": "github-token-unavailable"},
                             checks.discover_reuse("e" * 40, "", root=ROOT))
            import product_reuse as products
            listed = {checks.artifact_name(value, 1): [{"id": 1, "name": checks.artifact_name(value, 1),
                                                         "expired": False, "created_at": "2026-01-01"}],
                      checks.artifact_name(value, 2): [{"id": 2, "name": checks.artifact_name(value, 2),
                                                         "expired": False, "created_at": "2026-02-01"},
                                                        {"id": 3, "name": "other", "expired": False}]}
            def paginated(url, key, token):
                from urllib.parse import parse_qs, urlsplit
                return listed.get(parse_qs(urlsplit(url).query)["name"][0], [])
            attempts = []
            def authenticate(candidate, current, token, *, root):
                attempts.append(candidate["id"])
                if candidate["id"] == 2:
                    raise ValueError("bad signature")
                return {"sourceRunId": 5, "sourceRunAttempt": 1, "artifactId": 1,
                        "artifactSha256": "sha256:" + "1" * 64, "recordSha256": "sha256:" + "2" * 64}
            with patch.object(products, "paginated_items", side_effect=paginated), \
                    patch.object(checks, "authenticate", side_effect=authenticate):
                result = checks.discover_reuse("e" * 40, "token", root=ROOT)
            self.assertEqual([2, 1], attempts)
            self.assertTrue(result["reused"])
            with patch.object(products, "paginated_items", side_effect=paginated), \
                    patch.object(checks, "authenticate", side_effect=ValueError("bad")):
                result = checks.discover_reuse("e" * 40, "token", root=ROOT)
            self.assertFalse(result["reused"])
            self.assertEqual("no-authenticated-record", result["reason"])

    def test_cli_discovery_errors_are_misses_not_passes(self):
        import http.client
        for error in (OSError("network"), ImportError("verifier"), http.client.IncompleteRead(b"x", 3),
                      subprocess.TimeoutExpired("gh", 1)):
            with self.subTest(error=type(error).__name__), tempfile.TemporaryDirectory() as temporary, \
                    patch.object(checks, "discover_reuse", side_effect=error):
                output = Path(temporary) / "output"
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(0, checks.main(["discover-reuse", "--publisher-sha", "e" * 40,
                                                     "--github-output", str(output)]))
                self.assertIn("reused=false\n", output.read_text())
                self.assertIn(f"reason=discovery-unavailable:{type(error).__name__}\n", output.read_text())

    def test_a_candidate_import_or_truncated_read_is_a_miss(self):
        import http.client
        import product_reuse as products
        value = checks.fingerprint(self.current)
        listed = [{"id": 1, "name": checks.artifact_name(value, 1), "expired": False, "created_at": "2026-01-01"}]
        for error in (ImportError("verifier"), http.client.IncompleteRead(b"x", 3)):
            with self.subTest(error=type(error).__name__), \
                    patch.object(checks, "current_inputs", return_value=self.current), \
                    patch.object(products, "paginated_items", side_effect=lambda url, key, token: listed), \
                    patch.object(checks, "authenticate", side_effect=error):
                result = checks.discover_reuse("e" * 40, "token", root=ROOT)
            self.assertFalse(result["reused"])
            self.assertEqual("no-authenticated-record", result["reason"])

    def test_record_location_is_not_actions_cache(self):
        source = (ROOT / "ci/tests/source_checks.py").read_text()
        self.assertNotIn("actions/cache", source)
        self.assertNotIn("/caches", source)
        self.assertIn("/actions/artifacts?", source)


if __name__ == "__main__":
    unittest.main()
