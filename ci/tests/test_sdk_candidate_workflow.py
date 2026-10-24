"""Local composition fixtures, not S1048 approval or hosted candidate evidence."""

import copy
from contextlib import ExitStack
import os
from pathlib import Path
import subprocess
import tempfile
from threading import Barrier, Lock
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from ci import sdk_candidate_workflow as candidate
from ci.products.inventory import canonical_json_bytes, regular_file_inventory, sha256_bytes, sha256_file
from ci.tests.test_sdk_candidate_catalog import _selection as catalog_selection
from ci.tests.test_sdk_candidate_maven_transport import _selection as maven_selection
from ci.tests.test_sdk_candidate_semantics import _selection as semantic_selection


_D = "sha256:" + "1" * 64
_OTHER = "sha256:" + "2" * 64


def selection():
    catalog, maven = catalog_selection(), maven_selection()
    handoff = {key: _D for key in candidate.signature(candidate.forward_verified_sdk_phase10_bytes).parameters
               if key.startswith("expected_")}
    handoff.update({key: value for key, value in maven["phase11Pins"].items() if key in handoff})
    semantics = semantic_selection(b"fixture")
    semantics["joinPins"]["expected_validation_tree"] = "b" * 40
    # The promoted index is not the Phase-10 index: do not accidentally conflate them.
    catalog["indexSha256"] = _OTHER
    semantics["joinPins"]["expected_promoted_index_sha256"] = _OTHER
    parity = dict(schemaVersion=1, producer={**maven["producer"], "event": "pull_request",
        "pullRequest": 31, "commit": "d" * 40, "runId": 50}, trustedWorkflowSha="c" * 40,
        jobId=21, artifactId=22, artifactSha256=_D, artifactBytes=1, phaseIdentitiesSha256=_D)
    runtime = dict(schemaVersion=1, producer={**maven["producer"], "commit": "e" * 40, "runId": 60},
        trustedWorkflowSha="f" * 40, jobId=23, artifactId=24, artifactSha256=_D,
        artifactBytes=1, validationCommit="d" * 40, inventorySha256=_D)
    return dict(schemaVersion=1, trustedSourceCommit="c" * 40, landedCommit="a" * 40,
        catalog=catalog, maven=maven, mavenCaptureInventorySha256=_D, parity=parity, runtime=runtime,
        index=dict(producer=maven["producer"], handoffPins=handoff, carrierPins=dict(
            producerSha256=sha256_bytes(canonical_json_bytes(maven["producer"])), artifactId=25,
            artifactSha256=_D, artifactSize=1, trustedWorkflowSha="c" * 40, captureInventorySha256=_D)),
        join=dict(schemaVersion=1, sdk=semantics, runtime=dict(inventorySha256=_D, rootPublicKeySha256=_D)))


class SdkCandidateWorkflowTest(unittest.TestCase):
    def test_preflight_cross_binds_every_input_but_preserves_mixed_producers(self):
        selected = selection()
        self.assertEqual(candidate._selection(selected), selected)
        for path, replacement in (
            (("catalog", "indexSha256"), _D),
            (("index", "handoffPins", "expected_index_sha256"), _OTHER),
            (("index", "handoffPins", "expected_source_commit"), "f" * 40),
            (("maven", "trustedWorkflowSha"), "f" * 40),
            (("parity", "artifactBytes"), 2),
            (("join", "runtime", "rootPublicKeySha256"), "bad"),
            (("trustedSourceCommit",), "main"),
            (("schemaVersion",), True),
        ):
            changed = copy.deepcopy(selected)
            parent = changed
            for part in path[:-1]:
                parent = parent[part]
            parent[path[-1]] = replacement
            with self.subTest(path=path), self.assertRaises(ValueError):
                candidate._selection(changed)
        with self.assertRaises(ValueError):
            candidate._selection({**selected, "bypass": True})

    def test_concurrent_capture_routes_one_catalog_and_only_consumed_inputs(self):
        selected = candidate._selection(selection())
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            workspace = Path(temporary).resolve() / "work"
            barrier, lock, calls = Barrier(4), Lock(), []
            def observe(name, destination):
                with lock:
                    calls.append((name, destination))
                if name != "runtime":
                    barrier.wait(timeout=10)
                return {"admitted": False}
            catalog = stack.enter_context(patch.object(candidate.custody, "capture_sdk_candidate_catalog",
                side_effect=lambda _, path, **kw: observe("catalog", path)))
            index = stack.enter_context(patch.object(candidate, "capture_official_sdk_phase10_index",
                side_effect=lambda _, pins, path, **kw: observe("index", path)))
            stack.enter_context(patch.object(candidate.maven, "capture_sdk_candidate_maven",
                side_effect=lambda _, path, **kw: observe("maven", path)))
            parity = stack.enter_context(patch.object(candidate.custody, "capture_sdk_candidate_parity",
                side_effect=lambda _, archive, path, **kw: observe("parity", path)))
            runtime = stack.enter_context(patch.object(candidate.custody, "capture_sdk_candidate_runtime",
                side_effect=lambda _, archive, path, **kw: observe("runtime", path)))
            result = candidate.capture(selected, workspace, Path(temporary), token="fixture")
            self.assertEqual(len(calls), 5)
            self.assertEqual([row["input"] for row in result], ["catalog", "index", "maven", "parity", "runtime"])
            self.assertTrue(all(row["elapsedNs"] > 0 for row in result))
            catalog.assert_called_once_with(selected["catalog"], workspace / "candidate/catalog", token="fixture")
            self.assertEqual(parity.call_args.args[1], workspace / "candidate/parity/original.zip")
            self.assertEqual(runtime.call_args.args[1], workspace / "capture/runtime.zip")
            self.assertEqual(index.call_args.kwargs["index_handoff_pins"], selected["index"]["handoffPins"])
            with self.assertRaises(FileExistsError):
                candidate.capture(selected, workspace, Path(temporary), token="fixture")
            self.assertEqual(len(calls), 5)

    def test_runtime_forwarding_extracts_once_and_rejects_unpinned_bytes(self):
        selected = selection()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            key = root / "landed/gradle/release/keys/sdk-runtime-root.pub"
            key.parent.mkdir(parents=True)
            key.write_bytes(b"public fixture, no signing key\n")
            archive = root / "runtime.zip"
            files = []
            with ZipFile(archive, "w") as zipped:
                for target, library in candidate._LIBRARY_PATHS.items():
                    path = target + "/" + Path(library).name
                    for name, raw in ((path, b"library fixture"),
                        (path + ".evidence/sdk-runtime-release-keyring.json", b"{}\n"),
                        (path + ".evidence/runtime-library-authorization.json", b"{}\n"),
                        (path + ".evidence/runtime-library-authorization.sig", b"signature fixture\n")):
                        zipped.writestr(name, raw)
                        files.append(dict(relativePath=name, bytes=len(raw), sha256=sha256_bytes(raw)))
            files.sort(key=lambda row: row["relativePath"])
            selected["runtime"].update(artifactSha256=sha256_file(archive), artifactBytes=archive.stat().st_size,
                                       inventorySha256=sha256_bytes(canonical_json_bytes(files)))
            selected["join"]["runtime"]["rootPublicKeySha256"] = sha256_file(key)
            with patch.object(candidate, "safe_extract", wraps=candidate.safe_extract) as extract:
                candidate._forward_runtime(selected, archive, root / "landed", root / "output")
            extract.assert_called_once()
            self.assertEqual(regular_file_inventory(root / "output/library-authorizations"), files)
            self.assertEqual([row["relativePath"] for row in regular_file_inventory(root / "output/root-delegation")],
                             ["sdk-runtime-release-keyring.json"])
            selected["runtime"]["artifactSha256"] = _OTHER
            with self.assertRaisesRegex(ValueError, "approved upload"):
                candidate._forward_runtime(selected, archive, root / "landed", root / "rejected")
            self.assertFalse((root / "rejected").exists())

    def test_offline_composition_joins_shared_objects_and_retains_transport_without_bulk_copy(self):
        selected = selection()
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            workspace = Path(temporary).resolve()
            (workspace / "candidate").mkdir()
            for path in ("index/transport.json", "maven/transport.json", "runtime-controls/transport.json",
                         "runtime-controls/library-inventory.json"):
                target = workspace / "capture" / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(canonical_json_bytes({"original": path}))
            barrier = Barrier(3)
            def independent(*args, **kwargs):
                barrier.wait(timeout=10)
                return {"admitted": False}
            mvn = stack.enter_context(patch.object(candidate.maven, "forward_sdk_candidate_maven", side_effect=independent))
            index = stack.enter_context(patch.object(candidate, "forward_verified_sdk_phase10_bytes", side_effect=independent))
            runtime = stack.enter_context(patch.object(candidate, "_forward_runtime", side_effect=independent))
            join = stack.enter_context(patch.object(candidate, "join_sdk_candidate", return_value={"admitted": False}))
            result = candidate.forward(selected, workspace, workspace / "landed", b"pins fixture\n")
            self.assertFalse(result["admitted"])
            self.assertEqual([row["input"] for row in result["forwarding"]], ["maven", "index", "runtime"])
            self.assertGreater(result["joinElapsedNs"], 0)
            for method in (mvn, index, runtime, join):
                method.assert_called_once()
            self.assertTrue(join.call_args.kwargs["use_promoted_objects"])
            self.assertEqual(join.call_args.args[0], workspace / "candidate/catalog")
            self.assertEqual({row["relativePath"] for row in regular_file_inventory(workspace / "candidate")},
                {"objects-control/object-pins.json", "evidence/index-transport.json", "evidence/maven-transport.json",
                 "evidence/runtime-transport.json", "evidence/runtime-library-inventory.json"})
            with patch.dict(os.environ, {"GITHUB_TOKEN": ""}), self.assertRaisesRegex(ValueError, "token"):
                candidate.forward(selected, workspace, workspace / "landed", b"fixture")
            join.assert_called_once()

    def test_cli_binds_object_pins_to_phase10_not_promoted_index_before_capture(self):
        selected = selection()
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            root = Path(temporary).resolve()
            path, pins = root / "selection.json", root / "pins.json"
            raw = canonical_json_bytes(selected)
            path.write_bytes(raw)
            pins.write_bytes(b"object pin fixture\n")
            stack.enter_context(patch.dict(os.environ, {"GITHUB_TOKEN": "fixture"}))
            stack.enter_context(patch.object(candidate, "_check_sources"))
            objects = stack.enter_context(patch.object(candidate, "_object_pins", return_value=(pins.read_bytes(), {})))
            capture = stack.enter_context(patch.object(candidate, "capture"))
            args = ["capture", "--selection", str(path), "--expected-selection-sha256", _D,
                "--object-pins", str(pins), "--workspace", str(root / "work"),
                "--trusted-repository", str(root / "trusted"), "--landed-repository", str(root / "landed")]
            with self.assertRaisesRegex(ValueError, "independent S1048 selection"):
                candidate.main(args)
            capture.assert_not_called()
            objects.assert_not_called()
            # Stop at the checked source boundary, before any network/file output.
            args[4] = sha256_bytes(raw)
            with patch.object(candidate, "_check_sources", side_effect=ValueError("checked source")), \
                 self.assertRaisesRegex(ValueError, "checked source"):
                candidate.main(args)
            objects.assert_called_once_with(pins, _D, _D)
            self.assertNotEqual(selected["catalog"]["indexSha256"], _D)
            capture.assert_not_called()

    def test_checkout_identity_and_tracked_edits_are_checked(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            def git(*args):
                return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.DEVNULL).decode().strip()
            git("init", "--quiet")
            (root / "tracked").write_text("original\n")
            git("add", "tracked")
            git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                "-c", "commit.gpgsign=false", "commit", "-m", "fixture")
            selected = selection()
            selected.update(trustedSourceCommit=git("rev-parse", "HEAD"), landedCommit=git("rev-parse", "HEAD"))
            selected["join"]["sdk"]["joinPins"]["expected_validation_tree"] = git("rev-parse", "HEAD^{tree}")
            candidate._check_sources(selected, root, root)
            (root / "tracked").write_text("changed\n")
            with self.assertRaisesRegex(ValueError, "tracked edits"):
                candidate._check_sources(selected, root, root)
            selected["trustedSourceCommit"] = "0" * 40
            with self.assertRaisesRegex(ValueError, "commit/tree"):
                candidate._check_sources(selected, root, root)

    def test_workflow_checks_pins_before_source_execution_and_has_no_build_or_sign_step(self):
        path = Path(__file__).resolve().parents[2] / ".github/workflows/sdk-candidate.yml"
        raw = path.read_text()
        self.assertIn("environment: release-candidate", raw)
        self.assertIn("cancel-in-progress: false", raw)
        self.assertIn("refs/tags/$GITHUB_REF_NAME^{commit}", raw)
        self.assertIn('merge-base --is-ancestor "$GITHUB_SHA" origin/main', raw)
        self.assertLess(raw.index('sdk-candidate-selection.json" | cut'), raw.index("uses: actions/checkout@"))
        self.assertLess(raw.index('git -C trusted-source rev-parse'), raw.index("sdk_candidate_workflow.py capture"))
        self.assertEqual(raw.count("GITHUB_TOKEN:"), 1)
        self.assertLess(raw.index("sdk_candidate_workflow.py forward"), raw.index("uses: actions/upload-artifact@"))
        for forbidden in ("./gradlew", "cargo build", "cmake --build", "xcodebuild", "ssh-keygen", "secrets."):
            self.assertNotIn(forbidden, raw)


if __name__ == "__main__":
    unittest.main()
