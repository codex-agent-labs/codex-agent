"""Candidate composition: real Runtime signatures, mocked upstream SDK admission.

These small local fixtures are not product bytes or hosted/release evidence.
"""

import copy
import json
import os
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

from ci import sdk_candidate_join as candidate
from ci.products.inventory import canonical_json_bytes, sha256_bytes, sha256_file, write_canonical_json
from ci.products.registry import NATIVE_BINDINGS, NATIVE_TARGETS, PhaseInstanceId
from ci.products.restore import object_relative_path
from ci.products.sdk_runtime_root import NAMESPACE, verify_external_library_authorization
from ci.tests.test_sdk_candidate_semantics import _selection
from ci.tests import test_sdk_runtime_root


class SdkCandidateJoinTest(unittest.TestCase):
    def setUp(self):
        fixture = self.fixture = test_sdk_runtime_root.SdkRuntimeRootTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        source = fixture.evidence("candidate", runtime_version="0.8.0")
        self.root = fixture.root
        self.runtime = self.root / "forwarded-runtime"
        self.runtime.mkdir()
        (self.runtime / "sdk-runtime-root.pub").write_bytes(fixture.root_public.read_bytes())
        delegation = self.runtime / "root-delegation"
        shutil.copytree(source, delegation, ignore=shutil.ignore_patterns("runtime-library-authorization.*"))
        claim = json.loads((source / "runtime-library-authorization.json").read_bytes())
        runtime = fixture.compatibility["runtime"]
        runtime["defaultManifestSha256"] = claim["aggregateManifestSha256"]
        self.claims = []
        for variant in runtime["embeddedVariants"]:
            target = variant["target"]
            value = copy.deepcopy(claim)
            value["runtimeIdentity"].update(target=target, componentId=sha256_bytes(target.encode()))
            value.update(variantBundleSha256=sha256_bytes((target + " bundle").encode()),
                         variantManifestSha256=sha256_bytes((target + " manifest").encode()))
            variant.update(componentId=value["runtimeIdentity"]["componentId"],
                bundleSha256=value["variantBundleSha256"], manifestSha256=value["variantManifestSha256"],
                runtimeLibrarySha256=value["runtimeLibrarySha256"])
            library = self.runtime / "library-authorizations" / target / Path(candidate._LIBRARY_PATHS[target]).name
            library.parent.mkdir(parents=True)
            library.write_bytes(fixture.library.read_bytes())
            evidence = library.with_name(library.name + ".evidence")
            shutil.copytree(delegation, evidence)
            path = evidence / "runtime-library-authorization.json"
            write_canonical_json(path, value)
            fixture._sign(path, fixture.root / "signer-candidate/development-ed25519", NAMESPACE,
                          evidence / "runtime-library-authorization.sig")
            self.claims.append((path, value))
        self.compatibility = canonical_json_bytes(fixture.compatibility)
        self.objects, self.promoted, self.maven = (self.root / name for name in ("objects", "promoted", "maven"))
        for directory in (self.objects, self.promoted, self.maven):
            directory.mkdir()
            (directory / "fixture.txt").write_bytes(b"SDK authority mocked, not a real candidate\n")
        self.rows = []
        for language, phase, target in ([(name, "package", "desktop") for name in NATIVE_BINDINGS]
                                       + [("csharp", "binary", "desktop"), ("sdk-core", "package", "common")]):
            identity = language + " " + phase
            key, receipt = sha256_bytes(identity.encode()), sha256_bytes((identity + " receipt").encode())
            relative = object_relative_path(key, receipt)
            path = self.objects / "objects" / relative
            path.parent.mkdir(parents=True)
            path.write_bytes(language.encode())
            self.rows.append(dict(product="sdk", component=language, phase=phase, target=target,
                buildKey=key, receiptSha256=receipt, objectSha256=sha256_file(path), relativePath=relative))
        write_canonical_json(self.objects / "object-pins.json", {"objects": self.rows})
        write_canonical_json(self.promoted / "product-index.json", {"fixture": "upstream signed SDK gate mocked"})
        self.parity, self.phases = (self.root / name for name in ("parity.zip", "phases.json"))
        self.parity.write_bytes(b"parity admission mocked")
        self.phases.write_bytes(b"[]\n")
        sdk = _selection(self.compatibility)
        sdk["dependencies"].update(contractDigest=fixture.compatibility["contract"]["digest"],
            runtimeManifestSha256=runtime["defaultManifestSha256"])
        sdk["joinPins"]["expected_object_pins_sha256"] = sha256_file(self.objects / "object-pins.json")
        sdk["joinPins"]["expected_promoted_index_sha256"] = sha256_file(self.promoted / "product-index.json")
        sdk["parity"].update(archiveSha256=sha256_file(self.parity), archiveBytes=self.parity.stat().st_size,
                             phaseIdentitiesSha256=sha256_file(self.phases))
        self.selection = dict(schemaVersion=1, sdk=sdk, runtime={
            "inventorySha256": self.inventory(), "rootPublicKeySha256": sha256_file(fixture.root_public)})

    def inventory(self):
        return sha256_bytes(canonical_json_bytes(candidate.regular_file_inventory(self.runtime)))

    def verify(self, *, bad_root_for=None, wrong_binary=False, verifier=verify_external_library_authorization,
               use_promoted_objects=False):
        originals = {PhaseInstanceId(*(row[field] for field in ("product", "component", "phase", "target"))):
            {"receipt": {**row, "productVersion": "0.8.0", "inputs": {"inventory": [{
                "relativePath": "gradle/release/keys/sdk-runtime-root.pub",
                "bytes": self.fixture.root_public.stat().st_size,
                "sha256": sha256_bytes(b"wrong") if bad_root_for == row["component"] else sha256_file(self.fixture.root_public)}]
                if (row["component"] in NATIVE_BINDINGS and
                    (row["component"] != "csharp" or row["phase"] == "binary")) else []}}}
            for row in self.rows}
        binary = originals[PhaseInstanceId("sdk", "csharp", "binary", "desktop")]["receipt"]
        binary["outputs"] = [{"kind": "artifact", "relativePath": "binding.dll", "bytes": 1,
                              "sha256": sha256_bytes(b"x")}]
        predecessor = candidate._upstream_record(binary)
        if wrong_binary:
            predecessor["buildKey"] = sha256_bytes(b"unselected binary")
        originals[PhaseInstanceId("sdk", "csharp", "package", "desktop")]["receipt"]["inputs"]["upstreamArtifacts"] = [predecessor]
        with patch.object(candidate, "verify_sdk_candidate_semantics", return_value={"admitted": False}) as sdk, \
             patch.object(candidate, "verify_release_sdk_campaign_objects", return_value=originals) as objects, \
             patch.object(candidate, "_package_compatibility", return_value=self.compatibility) as resource, \
             patch.object(candidate, "verify_external_library_authorization", side_effect=verifier) as signatures:
            result = candidate.join_sdk_candidate(self.promoted, self.objects, self.maven, self.runtime,
                self.selection, parity_archive=self.parity, parity_phase_identities=self.phases,
                use_promoted_objects=use_promoted_objects)
        self.assertEqual(1, sdk.call_count)
        self.assertIs(use_promoted_objects, sdk.call_args.kwargs["use_promoted_objects"])
        self.assertEqual(1, objects.call_count)
        self.assertEqual(1, resource.call_count)
        object_root = self.promoted if use_promoted_objects else self.objects / "objects"
        self.assertTrue(resource.call_args.args[0].is_relative_to(object_root))
        self.assertEqual(5, signatures.call_count)
        return result

    def test_shared_catalog_keeps_exact_runtime_root_and_default_checks(self):
        (self.objects / "objects/v1").rename(self.promoted / "v1")
        (self.objects / "objects").rmdir()
        before = candidate.regular_file_inventory(self.root)
        self.assertEqual(list(NATIVE_TARGETS), self.verify(use_promoted_objects=True)["runtimeAuthorizationTargets"])
        self.assertEqual(before, candidate.regular_file_inventory(self.root))
        with self.assertRaisesRegex(ValueError, "exact root-owning binary"):
            self.verify(use_promoted_objects=True, wrong_binary=True)

    def test_all_five_signed_defaults_and_original_producer_roots_are_required(self):
        before = candidate.regular_file_inventory(self.root)
        result = self.verify()
        self.assertFalse(result["admitted"])
        self.assertEqual(list(NATIVE_TARGETS), result["runtimeAuthorizationTargets"])
        self.assertEqual(before, candidate.regular_file_inventory(self.root))
        for language in NATIVE_BINDINGS:
            with self.subTest(language=language), self.assertRaisesRegex(ValueError, "original native producer inputs"):
                self.verify(bad_root_for=language)
        with self.assertRaisesRegex(ValueError, "exact root-owning binary"):
            self.verify(wrong_binary=True)

    def test_repinned_bad_library_signature_or_extra_file_cannot_pass(self):
        claim, _ = self.claims[0]
        library = claim.parent.with_name(claim.parent.name.removesuffix(".evidence"))
        for path in (library, claim.parent / "runtime-library-authorization.sig",
                     self.runtime / "sdk-runtime-root.pub"):
            before = path.read_bytes()
            path.write_bytes(before + b"bad")
            self.selection["runtime"]["inventorySha256"] = self.inventory()
            with self.subTest(path=path.name), self.assertRaises(ValueError):
                self.verify()
            path.write_bytes(before)
        (self.runtime / "extra").write_bytes(b"unexpected")
        self.selection["runtime"]["inventorySha256"] = self.inventory()
        with self.assertRaisesRegex(ValueError, "extra or missing"):
            self.verify()

    def test_compatible_newer_signed_runtime_is_not_the_embedded_default(self):
        path, value = self.claims[0]
        value["runtimeVersion"] = "0.8.1"
        write_canonical_json(path, value)
        self.fixture._sign(path, self.root / "signer-candidate/development-ed25519", NAMESPACE,
                           path.parent / "runtime-library-authorization.sig")
        self.selection["runtime"]["inventorySha256"] = self.inventory()
        with self.assertRaisesRegex(ValueError, "exact default Runtime"):
            self.verify()

    def test_late_sdk_mutation_and_tokens_fail_closed(self):
        calls = []
        def mutate(*args, **kwargs):
            result = verify_external_library_authorization(*args, **kwargs)
            calls.append(kwargs["target"])
            if len(calls) == 5:
                (self.maven / "fixture.txt").write_bytes(b"changed after SDK verification")
            return result
        with self.assertRaisesRegex(ValueError, "inputs changed"):
            self.verify(verifier=mutate)
        for name in ("GITHUB_TOKEN", "SIGNING_IN_MEMORY_KEY"):
            with patch.dict(os.environ, {name: "forbidden"}), self.assertRaisesRegex(ValueError, "token|secret"):
                self.verify()


if __name__ == "__main__":
    unittest.main()
