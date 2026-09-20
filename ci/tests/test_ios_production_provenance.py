"""Production-copy provenance controls, not native execution or CI admission."""

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import reuse  # noqa: E402
import stage  # noqa: E402
from products.inventory import regular_file_inventory, sha256_bytes  # noqa: E402
from sdk_apple_native import NATIVE_FILES, NATIVE_TOOLCHAINS  # noqa: E402
from sdk_apple_source import _original_transport_producer  # noqa: E402


class IosProductionProvenanceTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def receipt(self, lane, *, old=False):
        tree = ("a" if old else "b") * 40
        return {
            "repository": "example/codex-agent",
            "workflowPath": ".github/workflows/ci.yml",
            "event": "pull_request", "pullRequest": 31,
            "runId": 71 if old else 81, "runAttempt": 1 if old else 2,
            "validationCommit": ("c" if old else "d") * 40,
            "validationTree": tree,
            "artifactName": f"codex-agent-ci-{lane}-{tree}",
            "artifacts": [], "evidence": [],
        }

    def write_files(self, source, receipt, contents):
        source.mkdir(parents=True)
        for relative, (kind, value) in contents.items():
            path = source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(value)
            collection = "artifacts" if kind in {"rust-archive", "aar"} else "evidence"
            receipt[collection].append({
                "relativePath": relative, "kind": kind,
                "sha256": sha256_bytes(value).removeprefix("sha256:"),
            })

    def check_native_copy(self, nested):
        for lane in ("ios-rust-device", "ios-rust-simulator"):
            with self.subTest(lane=lane, nested=nested):
                source = self.root / lane / "original"
                output = self.root / lane / "copy"
                receipt = self.receipt(lane)
                oldest = self.receipt(lane, old=True) if nested else receipt
                proof = json.dumps({
                    "candidateCommit": oldest["validationCommit"],
                    "candidateTree": oldest["validationTree"],
                    "scope": "synthetic production-copy fixture",
                }, sort_keys=True).encode()
                contents = {
                    relative: (("rust-archive", b"!<arch>\nsynthetic-original\n")
                               if relative.endswith(".a") else ("rust-proof", proof))
                    for relative in NATIVE_FILES[lane]
                }
                contents["lane-result.txt"] = ("lane-result", b"original lane result\n")
                contents[NATIVE_TOOLCHAINS[lane]] = (
                    "rust-toolchain-evidence", b'{"scope":"original toolchain observations"}\n',
                )
                self.write_files(source, receipt, contents)
                previous = None
                if nested:
                    oldest_before = deepcopy(oldest)
                    digest = reuse.write_transport_provenance(
                        source, oldest, oldest["artifactName"],
                    )
                    raw = (source / "transport-provenance.json").read_bytes()
                    self.assertEqual(digest, sha256_bytes(raw).removeprefix("sha256:"))
                    self.assertEqual(oldest, oldest_before)
                    previous = json.loads(raw)
                    receipt["evidence"].append({
                        "relativePath": "transport-provenance.json",
                        "kind": "transport-provenance", "sha256": digest,
                    })
                (source / "lane-receipt.json").write_text(json.dumps(receipt, sort_keys=True))
                before = regular_file_inventory(source)
                output.mkdir()

                artifacts, evidence = stage.restore_production_files(source, output, lane)

                self.assertEqual(artifacts, {
                    path: kind for path, (kind, _) in contents.items() if kind == "rust-archive"
                })
                self.assertEqual(evidence, {
                    **{path: kind for path, (kind, _) in contents.items()
                       if kind in {"rust-proof", "rust-toolchain-evidence"}},
                    "transport-provenance.json": "transport-provenance",
                })
                self.assertEqual(
                    {item["relativePath"] for item in regular_file_inventory(output)},
                    set(artifacts) | set(evidence),
                )
                for relative in NATIVE_FILES[lane]:
                    self.assertEqual((output / relative).read_bytes(), contents[relative][1])
                chain = json.loads((output / "transport-provenance.json").read_bytes())
                self.assertEqual(chain["previous"], previous)
                self.assertEqual(chain["source"]["runId"], receipt["runId"])
                self.assertEqual(chain["sourceTransportArtifactName"], receipt["artifactName"])
                producer, name = _original_transport_producer(output, receipt, lane_name=lane)
                self.assertEqual(producer, {
                    "repository": oldest["repository"], "workflowPath": oldest["workflowPath"],
                    "event": oldest["event"], "pullRequest": oldest["pullRequest"],
                    "runId": oldest["runId"], "runAttempt": oldest["runAttempt"],
                    "commit": oldest["validationCommit"], "tree": oldest["validationTree"],
                })
                self.assertEqual(name, oldest["artifactName"])
                self.assertEqual(regular_file_inventory(source), before)

    def test_native_production_copy_retains_original_producer_and_bytes(self):
        self.check_native_copy(nested=False)

    def test_native_production_copy_preserves_nested_original_provenance(self):
        self.check_native_copy(nested=True)

    def test_other_lanes_keep_existing_production_copy_behavior(self):
        for lane, contents, expected_artifacts in (
            ("android", {"payload/original.aar": ("aar", b"original aar")},
             {"payload/original.aar": "aar"}),
            ("ios-native-tests", {"payload/proof.json": ("native-test-proof", b"{}")}, {}),
        ):
            with self.subTest(lane=lane):
                source = self.root / lane / "original"
                output = self.root / lane / "copy"
                receipt = self.receipt(lane)
                self.write_files(source, receipt, contents)
                # An unrelated prior transport file remains external and is not copied.
                (source / "transport-provenance.json").write_bytes(b"unselected provenance")
                receipt["evidence"].append({
                    "relativePath": "transport-provenance.json", "kind": "transport-provenance",
                    "sha256": sha256_bytes(b"unselected provenance").removeprefix("sha256:"),
                })
                (source / "lane-receipt.json").write_text(json.dumps(receipt, sort_keys=True))
                before = regular_file_inventory(source)
                output.mkdir()
                self.assertEqual(stage.restore_production_files(source, output, lane),
                                 (expected_artifacts, {}))
                self.assertFalse((output / "transport-provenance.json").exists())
                self.assertEqual({p.relative_to(output).as_posix()
                                  for p in output.rglob("*") if p.is_file()},
                                 set(expected_artifacts))
                self.assertEqual(regular_file_inventory(source), before)


if __name__ == "__main__":
    unittest.main()
