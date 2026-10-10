"""Real local discovery/planning/continuation over explicit synthetic K/R objects.

Only impact selection and remote catalog transport are substituted. No planner,
Git inventory, object verifier, signature gate, or native projection is mocked.
Emitted SDK plans are control-flow evidence, not executed package/host acceptance.
"""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from ci.products.inventory import (
    load_canonical_json_bytes, regular_file_inventory,
    sha256_file, snapshot_regular_tree, write_canonical_json,
)
from ci.products.native_runtime_inputs import stage_native_runtime_evidence
from ci.products.registry import NATIVE_TARGETS
from ci.products.restore import store_local_object
from ci.products.signatures import sign_manifest
from ci.tests.product_chain_planned import planned_chain
from ci.tests import test_product_reuse_adapter as fixture


adapter = fixture.product_reuse


class NativeContinuationTest(unittest.TestCase):
    def test_original_objects_reach_package_then_host_plan_without_product_processes(self):
        popen = subprocess.Popen
        processes = []

        def guarded_process(command, *args, **kwargs):
            executable = Path(command[0]).name
            self.assertIn(executable, {"git", "ssh-keygen"}, "A product process must not start")
            self.assertFalse(kwargs.get("shell"), "A shell must not bypass the process guard")
            if executable == "git":
                arguments = command[3:] if command[1] == "-C" else command[1:]
                self.assertIn(arguments[0], {"init", "config", "add", "commit", "rev-parse", "ls-tree", "cat-file", "diff"},
                              "Only isolated local Git operations are permitted")
            processes.append(executable)
            return popen(command, *args, **kwargs)

        with tempfile.TemporaryDirectory(prefix="native-continuation-") as temporary, \
                patch.object(subprocess, "Popen", side_effect=guarded_process):
            root = Path(temporary).resolve()
            chain = planned_chain(root)
            repository, context = chain["repository"], chain["context"]
            original = regular_file_inventory(chain["root"], allow_empty=True)
            requested = (adapter.PhaseInstanceId("sdk", "python", "validation", "linux-x64"),)
            impact = fixture.impact_plan(changed=["codex-agent-bindings/python/fixture.py"])
            impact.update(headCommit=chain["commit"], validationCommit=chain["commit"], validationTree=chain["tree"])
            plan_path = repository / "impact.json"
            write_canonical_json(plan_path, impact)
            environment = {"GITHUB_RUN_ID": "301", "GITHUB_RUN_ATTEMPT": "1"}
            consumer = adapter._consumer(impact, environment)
            discovery = repository / "build/product-reuse"

            def local_catalog(_plan, destination, *_args):
                objects, entries, asset_names = {}, [], set()
                for instance, receipt in sorted(context["planned_receipts"].items()):
                    stored = store_local_object(context["phase_stages"][instance],
                                                context["receipt_paths"][instance], destination / "objects")
                    objects[receipt["buildKey"]] = stored["path"]
                    entry = fixture.ProductReuseAdapterTest.product_index_entry({
                        "receipt": receipt, "receiptSha256": stored["receiptSha256"],
                    })
                    artifact = next(output for output in receipt["outputs"]
                                    if (receipt["product"], receipt["productVersion"], output["relativePath"]) not in asset_names)
                    asset_names.add((receipt["product"], receipt["productVersion"], artifact["relativePath"]))
                    entry.update(artifactName=artifact["relativePath"], artifactSha256=artifact["sha256"])
                    entries.append(entry)
                producer = context["producer"]
                index = {
                    "schemaVersion": 1, "repository": producer["repository"],
                    "context": {"kind": "pull-request", **{key: producer[key] for key in
                                ("pullRequest", "commit", "tree", "runId", "runAttempt")}},
                    "entries": sorted(entries, key=lambda entry: entry["buildKey"]),
                    "trustDomain": "development", "signing": context["signing"], "producer": producer,
                }
                manifest = destination / "catalog/product-index.json"
                write_canonical_json(manifest, index)
                signature = sign_manifest(manifest, context["private_key"], context["signing"])
                public_key = destination / "catalog/development.pub"
                shutil.copyfile(context["public_key"], public_key)
                trust = destination / "catalog/contract-trust"
                snapshot_regular_tree(chain["contract"]["attestation"].parent, trust)
                attestation = trust / chain["contract"]["attestation"].name
                attestation_signature = trust / chain["contract"]["signature"].name

                def relative(path):
                    return path.relative_to(destination).as_posix()

                request = {
                    "manifest": relative(manifest), "signature": relative(signature),
                    "publicKey": relative(public_key), "keyring": None, "keysDirectory": None,
                    "contractAttestation": relative(attestation),
                    "contractAttestationSignature": relative(attestation_signature),
                    "contractPublicKey": relative(public_key),
                    "objects": [{"buildKey": key, "objectPath": relative(path)} for key, path in sorted(objects.items())],
                }
                return [adapter.Catalog("same-pr", index, sha256_file(manifest), request, objects,
                                        attestation, attestation_signature)]

            with patch.object(adapter, "_validate_plan", return_value=impact), \
                    patch.object(adapter, "_requested", return_value=requested), \
                    patch.object(adapter, "_discover_catalogs", side_effect=local_catalog) as transport:
                adapter.discover(plan_path, discovery, repository / "discovery-output",
                                 repository_root=repository, environ=environment)
                transport.assert_called_once()
                initial = load_canonical_json_bytes((discovery / "reuse-wave-result.json").read_bytes())
                self.assertTrue(initial["continuationRequirements"])
                self.assertTrue(all(not rows for rows in initial["matrices"].values()))
                self.assertEqual(consumer["producer"], load_canonical_json_bytes((discovery / "producer.json").read_bytes()))

                def advance(name, state=None, *, shards=(), evidence=()):
                    destination = repository / name
                    result = adapter.advance_products(
                        plan_path, discovery, state, list(shards), destination, repository / (name + "-output"),
                        repository_root=repository, environ=environment, native_evidence_roots=evidence)
                    return result, destination

                waiting, waiting_root = advance("native-wait")
                self.assertTrue(all(not rows for rows in waiting["matrices"].values()))
                self.assertEqual([{
                    "kind": "native-runtime-validation-evidence", "product": "sdk", "component": "python",
                    "phase": "package", "target": "desktop", "dependencies": [
                        {"product": "runtime", "component": target, "phase": "validation", "target": target}
                        for target in NATIVE_TARGETS],
                }], waiting["continuationRequirements"])
                records = []

                def relative(path):
                    return path.relative_to(root).as_posix()

                contract, variants = chain["contract"], chain["variants"]
                for target in NATIVE_TARGETS:
                    receipts = variants["variant_phase_receipts"][target]
                    records.append({
                        "receiptSha256": sha256_file(receipts["validation"]),
                        "contractEvidence": {
                            "stageRoot": relative(contract["payload"].parent.parent),
                            "phaseReceipt": relative(contract["receipt"]),
                            "attestation": relative(contract["attestation"]),
                            "attestationSignature": relative(contract["signature"]),
                            "publicKey": relative(context["public_key"]),
                            "expectedTrustDomain": "development", "keyring": None, "keysDirectory": None,
                        },
                        "runtimeEvidence": {
                            "target": target, "stageRoot": relative(variants["stages"]),
                            "phaseReceipts": {phase: relative(path) for phase, path in receipts.items()},
                            **{field: relative(variants[key][target]) for field, key in (
                                ("payload", "variant_bundles"), ("attestation", "variant_attestations"),
                                ("attestationSignature", "variant_attestation_signatures"),
                                ("publicKey", "variant_public_keys"))},
                            "keyring": None, "keysDirectory": None,
                        },
                    })
                handoff = repository / "incoming-native"
                stage_native_runtime_evidence(sorted(records, key=lambda record: record["receiptSha256"]), root, handoff)
                relocated = repository / "relocated-native"
                handoff.rename(relocated)
                ready, ready_root = advance("native-ready", waiting_root, evidence=(relocated,))
                self.assertEqual([], ready["continuationRequirements"])
                self.assertEqual(1, len(ready["matrices"]["sdk"]))
                self.assertEqual([], ready["matrices"]["runtime"])
                self.assertEqual("package", ready["matrices"]["sdk"][0]["phase"])
                package_plan = load_canonical_json_bytes((ready_root / "phase-plans/sdk-python-package-desktop.json").read_bytes())
                self.assertEqual(5, sum(record.get("semanticProjection", {}).get("kind") ==
                                       "runtime-native-validation-content" for record in package_plan["inputs"]["upstreamArtifacts"]))

                # Only simulate a completed package for continuation control.
                # This is NOT a Python compiler, installed SDK or parity receipt.
                stage = repository / "synthetic-sdk-package"
                payload = stage / "outputs/package.bin"
                payload.parent.mkdir(parents=True)
                payload.write_bytes(b"Synthetic SDK package for handoff planning only\n")
                fixture.write_output_manifest(stage, "sdk", "python", "package", "desktop", "0.2.9", {"artifact": "outputs"})
                shard = repository / "sdk-package-shard"
                fixture.finalize_phase_object(stage_root=stage, phase_plan=package_plan, producer=consumer["producer"],
                                              product_version="0.2.9", trust_domain="development", destination=shard)
                package = fixture.verify_phase_shard(shard, adapter.PhaseInstanceId("sdk", "python", "package", "desktop"))
                retained_handoff = regular_file_inventory(ready_root / "native-runtime-evidence")
                unavailable = repository / "incoming-unavailable"
                relocated.rename(unavailable)
                host, host_root = advance("host-ready", ready_root, shards=(shard,))
                self.assertEqual(retained_handoff, regular_file_inventory(host_root / "native-runtime-evidence"))
                self.assertEqual([], host["continuationRequirements"])
                self.assertEqual(["linux-x64"], [row["target"] for row in host["matrices"]["sdk"]])
                self.assertTrue(all(row["phase"] == "validation" for row in host["matrices"]["sdk"]))
                host_plan = load_canonical_json_bytes((host_root / "phase-plans/sdk-python-validation-linux-x64.json").read_bytes())
                upstream = host_plan["inputs"]["upstreamArtifacts"]
                self.assertEqual([package["receipt"]["buildKey"]], [record["buildKey"] for record in upstream if record["product"] == "sdk"])
                self.assertEqual(["linux-x64", "macos-arm64"], [record["target"] for record in upstream if record["product"] == "runtime"])
                selected = tuple(adapter._identity(row) for row in host["phases"] if row["state"] in {"reused", "retained"})
                carrier = fixture.verify_carrier(host_root / "reused-carrier", selected, consumer)
                sdk_original = next(record for record in carrier["objects"] if record["receipt"]["product"] == "sdk")
                self.assertEqual((shard / "phase-receipt.json").read_bytes(), sdk_original["receiptBytes"])
            self.assertEqual(original, regular_file_inventory(chain["root"], allow_empty=True))
            self.assertTrue(processes)
            self.assertEqual({"git", "ssh-keygen"}, set(processes))


if __name__ == "__main__":
    unittest.main()
