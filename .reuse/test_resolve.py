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

    def test_retained_verifiers_have_bounded_growth_without_dropping_older_authority(self):
        value = copy.deepcopy(self.manifest)
        retained = list(value["approvedVerifiers"])
        additions = (f"{index:040x}" for index in range(2048))
        while len(value["approvedVerifiers"]) < 1024:
            candidate = next(additions)
            if candidate not in value["approvedVerifiers"]:
                value["approvedVerifiers"].append(candidate)
        self.assertIs(value, authority.manifest(value))
        self.assertEqual(retained, value["approvedVerifiers"][:len(retained)])
        self.assertEqual(self.manifest["qualifications"], value["qualifications"])
        self.assertLess(len(json.dumps(value, sort_keys=True).encode()), 64 * 1024)
        value["approvedVerifiers"].append(next(additions))
        with self.assertRaises(ValueError): authority.manifest(value)

    def test_publication_checks_overlap_but_join_every_read_before_return_or_failure(self):
        from threading import Barrier, Lock
        publisher, source = "c" * 40, self.manifest["activeVerifier"]
        names = ["a", "b", "c", "product-validation"]
        bodies = {f".github/workflows/{name}.yml": b"name: exact reviewed workflow\n" for name in names}
        publication = {"schemaVersion": 1, "sourceSha": source, "workflows": [
            {"path": path, "bytes": len(raw), "sha256": "sha256:" + hashlib.sha256(raw).hexdigest()}
            for path, raw in bodies.items()]}
        for failing in (False, True):
            barrier, lock, finished = Barrier(4, timeout=5), Lock(), set()
            def contents(path, revision, **_):
                if path == ".reuse/workflow-publication.json": return json.dumps(publication).encode()
                if revision == publisher:
                    barrier.wait()
                    with lock: finished.add(path)
                    if failing and path.endswith('/a.yml'): raise ValueError('one original read failed')
                return bodies[path]
            def api(path):
                self.assertEqual(set(bodies), finished)
                if path.endswith('/protection'): return copy.deepcopy(self.protection)
                return {"commit": {"sha": publisher}}
            with patch.object(authority, 'resolve', return_value={"authorityCommit": publisher,
                    "approvedVerifiers": [source]}), patch.object(authority, 'contents', side_effect=contents), \
                    patch.object(authority, 'api', side_effect=api):
                if failing:
                    with self.assertRaisesRegex(ValueError, 'one original read failed'):
                        authority.resolve_publication(publisher)
                else:
                    self.assertEqual(publication['workflows'], authority.resolve_publication(publisher)['workflows'])
            self.assertEqual(set(bodies), finished)

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

    def test_publication_binds_native_publisher_and_approved_source(self):
        publisher, source = "c" * 40, self.manifest["activeVerifier"]
        entry, child = ".github/workflows/product-validation.yml", ".github/workflows/child.yml"
        bodies = {entry: b"jobs:\n  child:\n    uses: ./.github/workflows/child.yml\n", child: b"name: reviewed child\n"}
        publication = {"schemaVersion": 1, "sourceSha": source, "workflows": [
            {"path": path, "bytes": len(raw), "sha256": "sha256:" + hashlib.sha256(raw).hexdigest()}
            for path, raw in sorted(bodies.items())]}

        def contents(path, revision, **_):
            if path == ".reuse/workflow-publication.json": return json.dumps(publication).encode()
            self.assertIn(revision, (publisher, source))
            return bodies[path]

        def api(path):
            if path.endswith("/protection"): return copy.deepcopy(self.protection)
            return {"commit": {"sha": publisher}}

        with patch.object(authority, "resolve", return_value={"authorityCommit": publisher,
                "activeVerifier": "f" * 40, "approvedVerifiers": [source, "f" * 40]}), \
             patch.object(authority, "contents", side_effect=contents), patch.object(authority, "api", side_effect=api):
            result = authority.resolve_publication(publisher)
            self.assertEqual((publisher, source), (result["publisherSha"], result["sourceSha"]))
            publication["sourceSha"] = "e" * 40
            with self.assertRaises(ValueError): authority.resolve_publication(publisher)
            publication["sourceSha"] = source
            publication["workflows"] = [row for row in publication["workflows"] if row["path"] == entry]
            with self.assertRaisesRegex(ValueError, "required child"): authority.resolve_publication(publisher)
            publication["workflows"] = [{"path": path, "bytes": len(raw),
                "sha256": "sha256:" + hashlib.sha256(raw).hexdigest()} for path, raw in sorted(bodies.items())]
            with patch.object(authority, "contents", side_effect=lambda path, rev, **kw:
                    contents(path, rev, **kw) + (b"tampered" if path == child and rev == publisher else b"")):
                with self.assertRaisesRegex(ValueError, "exact reviewed"): authority.resolve_publication(publisher)


if __name__ == "__main__": unittest.main()
