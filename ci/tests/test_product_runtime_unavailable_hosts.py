from __future__ import annotations

import copy
import unittest

from ci.products.aggregate import (
    RUNTIME_TARGETS,
    runtime_component_id,
    validate_runtime_aggregate,
    validate_runtime_variant,
)
from ci.products.inventory import sha256_bytes
from ci.tests.test_products import DIGEST_A, DIGEST_B, runtime_aggregate, runtime_variant


LOCAL_HOST_TARGET = "macos-arm64"
UNAVAILABLE_HOST_TARGETS = tuple(
    target for target in RUNTIME_TARGETS if target != LOCAL_HOST_TARGET
)


def _unavailable_host_variant(target: str) -> dict:
    """Create identity-only fixture data; this is not host execution evidence."""
    variant = runtime_variant(target)
    variant["contract"]["componentDigest"] = sha256_bytes(
        f"fixture-contract:{target}".encode(),
    )
    variant["appServer"]["binarySha256"] = sha256_bytes(
        f"fixture-app-server:{target}".encode(),
    )
    variant["inputs"]["binaryBuildKey"] = sha256_bytes(
        f"fixture-binary:{target}".encode(),
    )
    variant["toolchainProfile"]["digest"] = sha256_bytes(
        f"fixture-toolchain:{target}".encode(),
    )
    variant["componentId"] = runtime_component_id(variant)
    return variant


class RuntimeUnavailableHostFixtureTest(unittest.TestCase):
    def test_four_unavailable_host_fixtures_have_exact_bound_identities(self) -> None:
        self.assertEqual(
            ("macos-x64", "linux-arm64", "linux-x64", "windows-x64"),
            UNAVAILABLE_HOST_TARGETS,
        )
        fixtures = {
            target: _unavailable_host_variant(target)
            for target in UNAVAILABLE_HOST_TARGETS
        }

        for target, variant in fixtures.items():
            with self.subTest(target=target):
                validate_runtime_variant(variant)
                self.assertEqual(target, variant["target"])
                self.assertEqual(runtime_component_id(variant), variant["componentId"])
                self.assertEqual(DIGEST_A, variant["contract"]["digest"])
                self.assertEqual(
                    sha256_bytes(f"fixture-contract:{target}".encode()),
                    variant["contract"]["componentDigest"],
                )
                self.assertEqual({
                    "version": "1.13.0",
                    "minimumCompatibleVersion": "1.0.0",
                    "identitySchemaVersion": 1,
                    "headerSha256": DIGEST_A,
                    "symbolSetSha256": DIGEST_B,
                    "symbolCount": 778,
                }, variant["cAbi"])
                self.assertEqual("0.149.0", variant["appServer"]["version"])
                self.assertEqual("rust-v0.149.0", variant["appServer"]["releaseTag"])
                self.assertEqual(
                    sha256_bytes(f"fixture-app-server:{target}".encode()),
                    variant["appServer"]["binarySha256"],
                )
                self.assertEqual({
                    "id": target,
                    "digest": sha256_bytes(f"fixture-toolchain:{target}".encode()),
                }, variant["toolchainProfile"])

        aggregate = runtime_aggregate()
        records = {record["target"]: record for record in aggregate["variants"]}
        for target, variant in fixtures.items():
            records[target]["componentId"] = variant["componentId"]
            aggregate["compatibility"]["toolchainProfileDigests"][target] = (
                variant["toolchainProfile"]["digest"]
            )
        validate_runtime_aggregate(aggregate)

    def test_aggregate_rejects_missing_and_duplicate_fixture_targets(self) -> None:
        missing = runtime_aggregate()
        missing["variants"].pop()
        duplicate = runtime_aggregate()
        duplicate["variants"][1]["target"] = duplicate["variants"][0]["target"]

        for name, aggregate in (("missing", missing), ("duplicate", duplicate)):
            with self.subTest(name=name), self.assertRaisesRegex(
                ValueError, "exactly five sorted supported targets",
            ):
                validate_runtime_aggregate(aggregate)

    def test_fixture_identity_rejects_wrong_target_contract_abi_server_and_toolchain(self) -> None:
        target = UNAVAILABLE_HOST_TARGETS[0]
        baseline = _unavailable_host_variant(target)
        invalid = {}

        invalid["target"] = copy.deepcopy(baseline)
        invalid["target"]["target"] = UNAVAILABLE_HOST_TARGETS[1]
        invalid["target"]["toolchainProfile"]["id"] = UNAVAILABLE_HOST_TARGETS[1]

        invalid["Contract"] = copy.deepcopy(baseline)
        invalid["Contract"]["contract"]["digest"] = sha256_bytes(b"wrong-contract")

        invalid["ABI"] = copy.deepcopy(baseline)
        invalid["ABI"]["cAbi"]["version"] = "1.12.0"

        invalid["app-server"] = copy.deepcopy(baseline)
        invalid["app-server"]["appServer"]["version"] = "0.148.0"
        invalid["app-server"]["appServer"]["releaseTag"] = "rust-v0.148.0"

        invalid["toolchain"] = copy.deepcopy(baseline)
        invalid["toolchain"]["toolchainProfile"]["digest"] = sha256_bytes(
            b"wrong-toolchain",
        )

        for name, variant in invalid.items():
            with self.subTest(name=name), self.assertRaisesRegex(
                ValueError, "componentId mismatch",
            ):
                validate_runtime_variant(variant)


if __name__ == "__main__":
    unittest.main()
