from __future__ import annotations

import copy
import unittest

from ci.products.aggregate import (
    runtime_component_id,
    validate_runtime_aggregate,
    validate_runtime_variant,
)
from ci.tests.test_products import (
    DIGEST_C,
    producer,
    runtime_aggregate,
    runtime_variant,
)


class RuntimeVariantSecurityTest(unittest.TestCase):
    def test_reusable_variant_rejects_execution_and_signing_identity(self) -> None:
        for field, value in (
            ("producer", producer()),
            ("signing", {"trustDomain": "development"}),
            ("sourceRuntimeVersion", "0.2.0"),
        ):
            variant = runtime_variant()
            variant[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_runtime_variant(variant)

    def test_component_id_uses_contract_compatibility_not_release_version(self) -> None:
        variant = runtime_variant()
        identity = variant["componentId"]

        version_only = copy.deepcopy(variant)
        version_only["contract"]["version"] = "0.2.1"
        self.assertEqual(identity, runtime_component_id(version_only))
        with self.assertRaises(ValueError):
            validate_runtime_variant(version_only)

        for field in ("digest", "componentDigest"):
            changed = copy.deepcopy(variant)
            changed["contract"][field] = DIGEST_C
            with self.subTest(field=field):
                self.assertNotEqual(identity, runtime_component_id(changed))

    def test_reusable_aggregate_rejects_provenance_and_signing_identity(self) -> None:
        for field, value in (
            ("producer", producer()),
            ("signing", {"trustDomain": "development"}),
            ("reused", True),
            ("sourceRuntimeVersion", "0.2.0"),
        ):
            aggregate = runtime_aggregate()
            aggregate[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_runtime_aggregate(aggregate)


if __name__ == "__main__":
    unittest.main()
