"""Source checks for the reviewed Runtime merge contribution; no hosted or product execution."""
from pathlib import Path
import hashlib
import importlib.util
import json
import subprocess
import unittest
from unittest.mock import patch

import product_reuse
from products.restore import _VERIFICATION_SESSION

ROOT = Path(__file__).resolve().parents[2]
source = ROOT / ".github/actions/run-ci-lane/runtime_reviewed_validation.py"
spec = importlib.util.spec_from_file_location("runtime_reviewed_validation", source)
subject = importlib.util.module_from_spec(spec)
spec.loader.exec_module(subject)


def git(*arguments):
    return subprocess.check_output(["git", *arguments], cwd=ROOT, text=True).strip()


class _Native:
    def __init__(self, revision, records):
        self._revision, self._eligible, self._checkpoint = revision, True, None
        self._records = records

    def check_consumer(self, consumer):
        return None

    def _values(self):
        return None, self._records

    def envelope(self, record):
        receipt = {**{key: record[key] for key in product_reuse._IDENTITY_KEYS},
                   "buildKey": record["buildKey"], "producer": {"runId": 1}}
        return {"receipt": receipt, "receiptBytes": record["_receipt"]}


class ReviewedRuntimeContributionTest(unittest.TestCase):
    def setUp(self):
        self.revision, self.tree = git("rev-parse", "HEAD^{commit}"), git("rev-parse", "HEAD^{tree}")
        identities = sorted({i for values in subject._LANES.values() for i in values})
        self.records, self.originals = {}, []
        for index, identity in enumerate(identities):
            raw = json.dumps({"index": index}).encode()
            row = {**{key: getattr(identity, key) for key in product_reuse._IDENTITY_KEYS},
                   "buildKey": "sha256:" + f"{index:064x}",
                   "receiptSha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
                   "objectSha256": "sha256:" + f"{index + 100:064x}"}
            self.records[identity] = {**row, "_receipt": raw}
            self.originals.append(row)
        self.plan = {"validationCommit": self.revision, "validationTree": self.tree, "mergeReady": True,
                     "lanes": {"portable": {"build": True, "test": True, "metadata": False}}}
        self.consumer = {"producer": {"runId": 2, "runAttempt": 1}}
        self.environ = {"GITHUB_ACTIONS": "true", "GITHUB_JOB": "merge-gate"}

    def contribute(self, runtime_version):
        policy = {"runtimeVersion": runtime_version, "originals": self.originals,
                  "sourceObjects": [], "limits": ["l"],
                  "checks": {name: {"name": name} for name in subject._EXPECTED}}
        native = _Native(self.revision, self.records)
        token = _VERIFICATION_SESSION.set(object())
        try:
            with patch.object(subject, "CompletedFrozenReuse", _Native), \
                    patch.object(subject, "validate_remote_build_authorization", return_value=(True, None)), \
                    patch.object(subject, "_policy", return_value=(b"{}", policy)), \
                    patch.object(subject.products, "_consumer", return_value=self.consumer):
                return subject.reviewed_runtime_contribution(
                    native, plan=self.plan, plan_sha256="sha256:" + "a" * 64, root=ROOT,
                    consumer=self.consumer, environ=self.environ, trusted_workflow_sha="b" * 40)
        finally:
            _VERIFICATION_SESSION.reset(token)

    def test_runtime_version_is_compared_with_the_runtime_release_version(self):
        versions = product_reuse._versions(ROOT, self.revision)
        self.assertNotIn("runtime", versions)
        result = self.contribute(versions["runtime-release"])
        self.assertEqual("passed", result["result"])
        self.assertEqual(["portable"], sorted(result["lanes"]))
        self.assertEqual({"jvm", "portableFixtures"}, set(result["lanes"]["portable"]["checks"]))
        self.assertEqual(len(subject._LANES["portable"]), len(result["lanes"]["portable"]["originals"]))
        self.assertFalse(result["currentHostedTestExecution"])

    def test_differing_runtime_version_is_rejected(self):
        release = product_reuse._versions(ROOT, self.revision)["runtime-release"]
        major, minor, patch_ = release.split("-", 1)[0].split(".")
        with self.assertRaisesRegex(ValueError, "Reviewed Runtime version differs"):
            self.contribute(f"{major}.{minor}.{int(patch_) + 1}")


if __name__ == "__main__":
    unittest.main()
