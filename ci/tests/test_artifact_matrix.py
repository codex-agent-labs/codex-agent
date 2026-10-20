import copy
import unittest

from ci.products.inventory import canonical_json_bytes, sha256_bytes
from ci.products.registry import PHASE_INSTANCE_IDS
from ci.tests.test_product_plan import receipt
from docs.artifact_matrix import FIELDS, approved_receipts, render


class ArtifactMatrixTest(unittest.TestCase):
    def test_projection_requires_exact_approved_originals(self):
        originals = [receipt(item) for item in PHASE_INSTANCE_IDS]
        selected = next(row for row in originals if row["component"] == "sdk-core" and row["phase"] == "package")
        version = selected["productVersion"]
        selected["outputs"][0]["relativePath"] = (
            f"outputs/maven/io/github/codex-agent-labs/codex-agent/{version}/codex-agent-{version}.pom")
        report = dict(result="passed", phaseCount=len(originals), originalPhases=[{
            **{field: row[field] for field in FIELDS}, "state": "retained", "misses": [],
            "buildKey": row["buildKey"], "receiptSha256": sha256_bytes(canonical_json_bytes(row)),
        } for row in originals], sdkParity=dict(result="passed", languageCount=11, satisfied=6104,
                                               excluded=12, scenarioCount=14))
        raw = canonical_json_bytes(report)
        digest = sha256_bytes(raw)
        accepted, rows = approved_receipts(raw, digest, [{"receipts": originals}, originals[:1]])
        text = render(accepted, rows, digest)
        self.assertIn(f"`io.github.codex-agent-labs:codex-agent:{version}`", text)
        self.assertIn("6104 satisfied claims", text)
        self.assertEqual(text, render(accepted, list(reversed(rows)), digest))
        with self.assertRaisesRegex(ValueError, "approved digest"):
            approved_receipts(raw, sha256_bytes(b"wrong"), [originals])
        with self.assertRaisesRegex(ValueError, "Missing accepted"):
            approved_receipts(raw, digest, [originals[1:]])
        changed = copy.deepcopy(originals)
        changed[0]["producer"]["runId"] += 1
        with self.assertRaisesRegex(ValueError, "accepted original"):
            approved_receipts(raw, digest, [changed])
        for mutate in (
            lambda value: value.update(result="failed"),
            lambda value: value["originalPhases"].append(value["originalPhases"][0]),
            lambda value: value["originalPhases"][0].update(misses=["missing input"]),
        ):
            changed_report = copy.deepcopy(report)
            mutate(changed_report)
            changed_raw = canonical_json_bytes(changed_report)
            with self.assertRaises(ValueError):
                approved_receipts(changed_raw, sha256_bytes(changed_raw), [originals])
        selected["outputs"][0]["relativePath"] = "outputs/maven/io/github/codex-agent-labs/codex-agent/99.0.0/codex-agent-99.0.0.pom"
        with self.assertRaisesRegex(ValueError, "Maven identity"):
            render(report, originals, digest)


if __name__ == "__main__":
    unittest.main()
