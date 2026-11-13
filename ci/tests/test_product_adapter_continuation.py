"""Actual local planning over two original, signed synthetic adapter histories.

Only fixture construction, impact selection, and remote catalog transport are
substituted. The planner, Git inventory, signatures, receipts, object restoration,
and transported adapter evidence verifier all execute normally. These are
development-trust control-flow tests, not product or hosted-runner acceptance.
Cross-index conflict comparison is covered separately by adapter content tests;
an adapter comparison carrier is not a new continuation requirement.
"""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from ci.products.adapter_runtime_inputs import stage_adapter_runtime_evidence
from ci.products.inventory import (
    load_canonical_json_bytes, regular_file_inventory, sha256_file,
    snapshot_regular_tree, write_canonical_json,
)
from ci.products.registry import PhaseInstanceId
from ci.products.restore import store_local_object
from ci.products.runtime_adapter_content import map_adapter_comparison_record
from ci.products.signatures import sign_manifest
from ci.tests import product_chain_planned
from ci.tests import test_product_reuse_adapter as fixture


adapter = fixture.product_reuse


class AdapterContinuationTest(unittest.TestCase):
    @staticmethod
    def comparison_record(chain, root):
        """Use the already signed originals, never reconstructed receipts."""
        component, target = "jvm", "linux-x64"
        source = chain["compatibility_args"]
        aggregate_inputs = {key: source[key] for key in (
            "contract_payload", "contract_metadata_receipt", "contract_attestation",
            "contract_attestation_signature", "contract_public_key", "required_trust_domain",
        )}
        for field, source_field in (
            ("aggregate_metadata_receipt", "runtime_metadata_receipt"),
            ("aggregate_attestation", "runtime_attestation"),
            ("aggregate_attestation_signature", "runtime_attestation_signature"),
            ("aggregate_public_key", "runtime_public_key"),
        ):
            aggregate_inputs[field] = source[source_field]
        aggregate_inputs.update({key: chain["variants"][key] for key in (
            "variant_bundles", "variant_phase_receipts", "variant_attestations",
            "variant_attestation_signatures", "variant_public_keys", "variant_validation_evidence",
        )})
        aggregate_inputs.update({key: chain["adapters"][key] for key in (
            "adapter_receipts", "adapter_report_files", "runtime_maven_files", "adapter_evidence",
        )})
        validation = PhaseInstanceId("runtime", component, "validation", target)
        stages = chain["adapters"]["phase_stages"]
        return map_adapter_comparison_record({
            "receiptSha256": sha256_file(chain["context"]["receipt_paths"][validation]),
            "component": component, "target": target,
            "aggregateManifest": chain["aggregate"], "aggregateInputs": aggregate_inputs,
            "adapterPackageStage": stages[PhaseInstanceId("runtime", component, "package", component)],
            "nativePackageStage": chain["variants"]["stages"] / target / "package",
            "validationStage": stages[validation],
            "distributionManifest": chain["adapters"]["distribution_manifest"],
        }, lambda path: path.relative_to(root).as_posix())

    @staticmethod
    def catalog_transport(chain):
        """Substitute only transport with a genuinely signed same-PR catalog."""
        context = chain["context"]

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
                                if (receipt["product"], receipt["productVersion"], output["relativePath"])
                                not in asset_names)
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

        return local_catalog

    def test_two_original_histories_replay_relocated_evidence_and_real_source_change_misses(self):
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

        original_builder = product_chain_planned.build_chain

        def raw_chain(*args, **kwargs):
            # This opt-in is applied before the FIRST original receipt exists;
            # the existing builder and sole original-plan factory remain real.
            kwargs["context"]["adapter_raw_closure"] = True
            return original_builder(*args, **kwargs)

        with tempfile.TemporaryDirectory(prefix="adapter-continuation-") as temporary, \
                patch.object(subprocess, "Popen", side_effect=guarded_process), \
                patch.object(product_chain_planned, "build_chain", side_effect=raw_chain):
            root = Path(temporary).resolve()
            chains, results = [], []
            requested = (adapter.PhaseInstanceId("runtime", "jvm", "metadata", "jvm"),)
            for number, name in enumerate(("left", "right"), 1):
                # Actual local commits differ only in producer time, not their
                # trees. No phase key, receipt or already signed byte is edited.
                date = f"2026-01-0{number}T12:00:00+0000"
                with patch.dict(os.environ, {"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}):
                    chain = product_chain_planned.planned_chain(root / name)
                chains.append(chain)
                repository, context = chain["repository"], chain["context"]
                original = regular_file_inventory(chain["root"], allow_empty=True)
                impact = fixture.impact_plan(changed=["codex-agent-runtime-desktop/src/jvmMain/kotlin/Fixture.kt"])
                impact.update(headCommit=chain["commit"], validationCommit=chain["commit"], validationTree=chain["tree"])
                plan_path = repository / "impact.json"
                write_canonical_json(plan_path, impact)
                environment = {"GITHUB_RUN_ID": str(300 + number), "GITHUB_RUN_ATTEMPT": "1"}
                consumer = adapter._consumer(impact, environment)
                discovery = repository / "build/product-reuse"
                handoff = repository / "incoming-adapter"
                stage_adapter_runtime_evidence([self.comparison_record(chain, root)], root, handoff)
                relocated = repository / "relocated-adapter"
                handoff.rename(relocated)

                with patch.object(adapter, "_validate_plan", return_value=impact), \
                        patch.object(adapter, "_requested", return_value=requested), \
                        patch.object(adapter, "_discover_catalogs", side_effect=self.catalog_transport(chain)) as transport:
                    adapter.discover(plan_path, discovery, repository / "discovery-output",
                                     repository_root=repository, environ=environment)
                    transport.assert_called_once()
                    initial = load_canonical_json_bytes((discovery / "reuse-wave-result.json").read_bytes())
                    self.assertTrue(all(not rows for rows in initial["matrices"].values()))
                    self.assertEqual(["runtime-validation-evidence"],
                                     [item["kind"] for item in initial["continuationRequirements"]])
                    self.assertEqual(5, len(initial["continuationRequirements"][0]["dependencies"]))

                    ready_root = repository / "adapter-ready"
                    ready = adapter.advance_products(
                        plan_path, discovery, None, [], ready_root, repository / "ready-output",
                        repository_root=repository, environ=environment, adapter_evidence_roots=(relocated,))
                    self.assertTrue(ready["fullReuse"])
                    self.assertEqual([], ready["continuationRequirements"])
                    self.assertTrue(all(not rows for rows in ready["matrices"].values()))
                    retained = regular_file_inventory(ready_root / "adapter-runtime-evidence", allow_empty=True)
                    self.assertTrue(retained)
                    # Incoming transport is no longer at its supplied address;
                    # continuation must authenticate and retain its own capture.
                    relocated.rename(repository / "incoming-unavailable")
                    replay_root = repository / "adapter-replayed"
                    replay = adapter.advance_products(
                        plan_path, discovery, ready_root, [], replay_root, repository / "replay-output",
                        repository_root=repository, environ=environment)
                    self.assertTrue(replay["fullReuse"])
                    self.assertEqual(retained, regular_file_inventory(replay_root / "adapter-runtime-evidence", allow_empty=True))
                    self.assertEqual([], replay["continuationRequirements"])
                    selected = tuple(adapter._identity(row) for row in replay["phases"]
                                     if row["state"] in {"reused", "retained"})
                    carrier = fixture.verify_carrier(replay_root / "carrier", selected, consumer)
                    for record in carrier["objects"]:
                        identity = PhaseInstanceId(*(record["receipt"][key] for key in
                                                     ("product", "component", "phase", "target")))
                        self.assertEqual(context["receipt_paths"][identity].read_bytes(), record["receiptBytes"])
                        self.assertEqual(chain["commit"], record["receipt"]["producer"]["commit"])
                        self.assertNotEqual(consumer["producer"]["runId"], record["receipt"]["producer"]["runId"])
                    results.append({tuple(row[key] for key in ("product", "component", "phase", "target")): row["buildKey"]
                                    for row in replay["phases"]})
                self.assertEqual(original, regular_file_inventory(chain["root"], allow_empty=True))

            self.assertNotEqual(chains[0]["commit"], chains[1]["commit"])
            self.assertEqual(chains[0]["tree"], chains[1]["tree"])
            self.assertEqual(results[0], results[1])
            validation = PhaseInstanceId("runtime", "jvm", "validation", "linux-x64")
            left = chains[0]["context"]["planned_receipts"][validation]
            right = chains[1]["context"]["planned_receipts"][validation]
            self.assertEqual(left["buildKey"], right["buildKey"])
            self.assertNotEqual(left["outputs"], right["outputs"])
            self.assertNotEqual(sha256_file(chains[0]["context"]["receipt_paths"][validation]),
                                sha256_file(chains[1]["context"]["receipt_paths"][validation]))

            # A meaningful source input is added to the ACTUAL Git tree. Reuse
            # must stop at the binary miss, without inventing a replacement run.
            chain = chains[1]
            repository = chain["repository"]
            relative = "codex-agent-runtime-desktop/src/jvmMain/kotlin/Fixture.kt"
            source = repository / relative
            source.parent.mkdir(parents=True)
            source.write_bytes(b"// A changed byte-affecting JVM source input\n")

            def git(*args):
                return subprocess.run(("git", *args), cwd=repository, check=True,
                                      capture_output=True, text=True).stdout.strip()

            git("add", relative)
            git("commit", "-qm", "synthetic meaningful JVM input mutation")
            changed_commit, changed_tree = git("rev-parse", "HEAD"), git("rev-parse", "HEAD^{tree}")
            self.assertNotEqual(chain["tree"], changed_tree)
            impact.update(headCommit=changed_commit, validationCommit=changed_commit, validationTree=changed_tree)
            write_canonical_json(plan_path, impact)
            discovery.rename(repository / "original-discovery")
            with patch.object(adapter, "_validate_plan", return_value=impact), \
                    patch.object(adapter, "_requested", return_value=requested), \
                    patch.object(adapter, "_discover_catalogs", side_effect=self.catalog_transport(chain)):
                adapter.discover(plan_path, discovery, repository / "changed-output",
                                 repository_root=repository, environ=environment)
            changed = load_canonical_json_bytes((discovery / "reuse-wave-result.json").read_bytes())
            builds = [row for rows in changed["matrices"].values() for row in rows]
            self.assertEqual([("runtime", "jvm", "binary", "jvm")],
                             [tuple(row[key] for key in ("product", "component", "phase", "target")) for row in builds])
            self.assertNotEqual(results[1][("runtime", "jvm", "binary", "jvm")], builds[0]["buildKey"])
            self.assertFalse(changed["fullReuse"])
            self.assertEqual(original, regular_file_inventory(chain["root"], allow_empty=True))
            self.assertEqual({"git", "ssh-keygen"}, set(processes))


if __name__ == "__main__":
    unittest.main()
