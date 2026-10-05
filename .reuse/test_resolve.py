import base64
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("authority", Path(__file__).with_name("resolve.py"))
authority = importlib.util.module_from_spec(spec)
spec.loader.exec_module(authority)


class AuthorityTests(unittest.TestCase):
    def setUp(self):
        self.protection = {"restrictions": {"users": [{"login": "ciurlaro", "id": 19213191}], "teams": [], "apps": []},
                           **{name: {"enabled": enabled} for name, enabled in (
                               ("enforce_admins", True), ("block_creations", True),
                               ("allow_force_pushes", False), ("allow_deletions", False))}}
        self.manifest = json.loads(Path(__file__).with_name("approvals.json").read_text())

    def test_exact_sole_owner_and_weakened_governance(self):
        authority.protection(self.protection)
        mutations = [("enforce_admins", False), ("block_creations", False),
                     ("allow_force_pushes", True), ("allow_deletions", True)]
        for name, enabled in mutations:
            value = copy.deepcopy(self.protection); value[name]["enabled"] = enabled
            with self.subTest(name=name), self.assertRaises(ValueError): authority.protection(value)
        for field in ("users", "teams", "apps"):
            value = copy.deepcopy(self.protection); value["restrictions"][field].append({"login": "other", "id": 2})
            with self.subTest(field=field), self.assertRaises(ValueError): authority.protection(value)
        value = copy.deepcopy(self.protection); value["restrictions"]["users"][0]["id"] = 2
        with self.assertRaises(ValueError): authority.protection(value)

    def test_manifest_conflicts_and_unapproved_issuer(self):
        self.assertEqual(authority.manifest(self.manifest), self.manifest)
        for mutation in (
            lambda v: v.update(activeVerifier="b" * 40),
            lambda v: v["approvedVerifiers"].append(v["activeVerifier"]),
            lambda v: v["qualifications"].append(copy.deepcopy(v["qualifications"][0])),
            lambda v: v["qualifications"][0].update(issuerSha="b" * 40),
            lambda v: v["qualifications"][0].update(runAttempt=True),
            lambda v: v.update(sourceSha="b" * 40),
            lambda v: v.update(schemaVersion=True),
        ):
            value = copy.deepcopy(self.manifest); mutation(value)
            with self.assertRaises(ValueError): authority.manifest(value)
        with self.assertRaises(ValueError): authority.decode(b'{"a":1,"a":2}')
        with self.assertRaises(ValueError): authority.decode(b"x" * (authority.LIMIT + 1))

    def test_exact_resolution_and_races(self):
        revision = "c" * 40
        def api(path):
            if path.endswith("/protection"): return copy.deepcopy(self.protection)
            if path.startswith("branches/"): return {"name": "reuse-authority", "protected": True, "commit": {"sha": revision}}
            name = path.split("?")[0].removeprefix("contents/")
            raw = Path(__file__).with_name(Path(name).name).read_bytes()
            return {"type": "file", "path": name, "encoding": "base64", "content": base64.b64encode(raw).decode(),
                    "sha": hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()}
        with patch.object(authority, "api", side_effect=api):
            self.assertEqual(authority.resolve(revision)["activeVerifier"], self.manifest["activeVerifier"])
            with self.assertRaises(ValueError): authority.resolve("d" * 40)
            with self.assertRaises(ValueError): authority.resolve("")
            with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}), self.assertRaises(ValueError): authority.resolve()
        calls = 0
        def race(path):
            nonlocal calls
            value = api(path)
            if path == "branches/reuse-authority":
                calls += 1
                if calls == 2: value["commit"]["sha"] = "d" * 40
            return value
        with patch.object(authority, "api", side_effect=race), self.assertRaises(ValueError): authority.resolve()
        def altered(path):
            value = api(path)
            if path.startswith("contents/"): value["sha"] = "0" * 40
            return value
        with patch.object(authority, "api", side_effect=altered), self.assertRaises(ValueError): authority.resolve()

    def test_hosted_missing_read_credential_fails_closed(self):
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}, clear=True), self.assertRaises(ValueError):
            authority.api("branches/reuse-authority/protection")


if __name__ == "__main__": unittest.main()
