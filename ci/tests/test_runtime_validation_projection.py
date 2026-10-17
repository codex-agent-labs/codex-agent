"""Focused product-fact projection and portable proof checks."""

import copy
import unittest

from ci.products import c_abi
from ci.products.inventory import canonical_json_bytes, write_canonical_json
from ci.products.runtime_validation_projection import (
    _project_verified_reports, verify_projected_c_abi_evidence,
)
from ci.tests import test_product_c_abi


class RuntimeValidationProjectionTest(unittest.TestCase):
    def test_projection_excludes_only_external_execution_identity(self):
        desktop = {"schemaVersion": 3, "candidateCommit": "a" * 40,
                   "testTask": "original-task", "result": "passed", "binarySha256": "b" * 64}
        report = {"schemaVersion": 1, "producerCommit": "a" * 40, "producerTree": "b" * 40,
                  "consumers": [{"source": "consumer.c", "artifactSha256": "a" * 64,
                                 "executed": True, "exitCode": 0}], "gnuConsumers": [],
                  "archiveSha256": "b" * 64, "result": "passed"}
        other_desktop, other_report = copy.deepcopy((desktop, report))
        other_desktop.update(candidateCommit="c" * 40, testTask="imported-task")
        other_report.update(producerCommit="c" * 40, producerTree="d" * 40)
        other_report["consumers"][0]["artifactSha256"] = "e" * 64
        first = _project_verified_reports(desktop, report)
        self.assertEqual(canonical_json_bytes(list(first)),
                         canonical_json_bytes(list(_project_verified_reports(other_desktop, other_report))))
        self.assertEqual("a" * 64, report["consumers"][0]["artifactSha256"])
        self.assertTrue(first[1]["consumers"][0]["executed"])
        other_report["archiveSha256"] = "f" * 64
        self.assertNotEqual(first, _project_verified_reports(other_desktop, other_report))

    def test_projected_portable_verifier_preserves_execution_and_package_checks(self):
        fixture = test_product_c_abi.ProductCAbiTest()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        fixture.root = fixture.root.resolve()
        fixture.header, fixture.license, fixture.notice = (
            path.resolve() for path in (fixture.header, fixture.license, fixture.notice))
        fixture.consumer_sources = [path.resolve() for path in fixture.consumer_sources]
        for target in ("linuxArm64", "mingwX64"):
            with self.subTest(target=target):
                package_input = fixture._package_input(target)
                archive = fixture.root / f"{target}.zip"
                snapshot = c_abi.package_c_abi_sdk(package_input, archive)
                raw = c_abi.build_c_abi_package_evidence(fixture._evidence_values(target, snapshot))
                _, projected = _project_verified_reports({}, raw)
                evidence = fixture.root / f"{target}.json"

                def verify(report):
                    write_canonical_json(evidence, report)
                    return verify_projected_c_abi_evidence(
                        target, "1.2.3", "a" * 40, "b" * 40, archive, evidence,
                        fixture.header, fixture.license, fixture.notice, package_input.export_policy,
                        fixture.consumer_sources)

                self.assertEqual(projected, verify(projected))
                for field, value in (("language", "wrong"), ("compilerIdentitySha256", "0" * 64),
                                     ("executed", False), ("exitCode", True)):
                    bad = copy.deepcopy(projected)
                    bad["consumers"][0][field] = value
                    with self.subTest(field=field), self.assertRaises(ValueError):
                        verify(bad)
                for field, value in (("archiveSha256", "0" * 64), ("publicSymbols", []),
                                     ("publicSymbolVersions", [{"symbol": "wrong", "version": "wrong"}])):
                    bad = copy.deepcopy(projected)
                    bad[field] = value
                    with self.subTest(field=field), self.assertRaises(ValueError):
                        verify(bad)


if __name__ == "__main__":
    unittest.main()
