"""Envelope tamper checks; native cryptography is exercised by hosted proof."""
import copy
import json
from pathlib import Path
import subprocess
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from ci.tests import test_runtime_original_ci as fixture
import reuse_qualification as qualification
from products.inventory import canonical_json_bytes, load_canonical_json_bytes, sha256_bytes
from products.registry import PhaseInstanceId
from products.verified_evidence import runtime_original_cache

adapter, TARGET = fixture.adapter, fixture.TARGET


class ReuseQualificationTest(unittest.TestCase):
    def test_windows_native_installer_verifies_before_extracting(self):
        # Shell composition only; this fake executable is not native evidence.
        installer = Path(__file__).resolve().parents[2] / ".github/actions/restore-reuse-qualification/install-gh.sh"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            commands = root / "commands"
            commands.mkdir()
            archive = root / "fixture.zip"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("bin/gh.exe", b"fixture, not a genuine executable")
            scripts = {
                "uname": 'if [ "$1" = -s ]; then echo "$TEST_OS"; else echo x86_64; fi',
                "curl": 'for argument; do destination="$argument"; done; cp "$TEST_ARCHIVE" "$destination"',
                "shasum": 'test "$*" = "-a 256 --check --status"; read -r digest file; '
                          'test "$digest" = ae64e556ecc240b200f7eba60d550e4bb60d78e860e69dd88c449405b86067f4; '
                          'test -f "$file"; test "$TEST_HASH_OK" = true',
            }
            for name, body in scripts.items():
                command = commands / name
                command.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + body + "\n")
                command.chmod(0o755)
            for name, os_name, hash_ok in (("windows", "MINGW64_NT-10.0-20348", "true"),
                                          ("bad-hash", "MINGW64_NT-10.0-20348", "false"),
                                          ("unknown", "Unknown", "true")):
                with self.subTest(name=name):
                    work = root / name
                    work.mkdir()
                    environment = {**os.environ, "PATH": str(commands) + os.pathsep + os.environ["PATH"],
                        "TEST_OS": os_name, "TEST_ARCHIVE": str(archive), "TEST_HASH_OK": hash_ok,
                        "RUNNER_TEMP": str(work), "GITHUB_PATH": str(work / "path"),
                        "GITHUB_OUTPUT": str(work / "output")}
                    result = subprocess.run(["bash", str(installer)], env=environment,
                                            capture_output=True, text=True)
                    binary = work / "reuse-qualification-gh/bin/gh.exe"
                    self.assertEqual(0 if name != "bad-hash" else 1, result.returncode, result.stderr)
                    self.assertEqual(name == "windows", binary.exists())
                    if name == "windows":
                        self.assertEqual(str(binary.parent) + "\n", (work / "path").read_text())
                        self.assertEqual("supported=true\n", (work / "output").read_text())
                    elif name == "unknown":
                        self.assertEqual("supported=false\n", (work / "output").read_text())
                        self.assertFalse((work / "reuse-qualification-gh").exists())
                    else:
                        self.assertFalse((work / "output").exists())

    def test_portable_benchmark_metrics_are_canonical_json(self):
        import ast
        source = ast.parse((Path(__file__).resolve().parents[1] / "hosted_reuse_proof.py").read_text())
        report = next(node.value for node in ast.walk(source) if isinstance(node, ast.Assign)
                      and any(isinstance(target, ast.Name) and target.id == "report" for target in node.targets)
                      and isinstance(node.value, ast.Dict)
                      and any(isinstance(key, ast.Constant) and key.value == "portableQualification"
                              for key in node.value.keys))
        metrics = next(value for key, value in zip(report.keys, report.values)
                       if isinstance(key, ast.Constant) and key.value == "portableQualification")
        for session in ({}, {"qualificationHits": 46, "qualificationVerificationSeconds": 12.375}):
            value = eval(compile(ast.Expression(metrics), "benchmark-metrics", "eval"), {"session": session})
            self.assertEqual(session.get("qualificationHits", 0), value["qualificationHits"])
            self.assertEqual(str(session.get("qualificationVerificationSeconds", 0)), value["qualificationVerificationSeconds"])
            self.assertEqual(value, load_canonical_json_bytes(canonical_json_bytes(value)))

    def test_aggregate_metadata_phase_is_distinct_from_signed_handoff(self):
        from ci.tests.test_products import phase_receipt
        from products.receipt import compute_build_key
        receipt = phase_receipt()
        receipt.update(product="runtime", component="runtime-aggregate", phase="metadata", target="aggregate")
        identity = {key: receipt[key] for key in ("product", "component", "phase", "target")}
        receipt["buildKey"] = compute_build_key(**identity, inputs=receipt["inputs"])
        digest = sha256_bytes(b"fixture")
        value = {"schemaVersion": 1, "sourceCommit": "a" * 40,
                 "verifierPolicySha256": digest, "originals": [{
                     "identity": {"policy": digest, "locator": {
                         "instance": identity, "workflowSha": "b" * 40, "artifact": {}, "job": {}}},
                     "receipt": receipt, "receiptSha256": sha256_bytes(canonical_json_bytes(receipt)),
                     "objectSha256": digest, "originalFiles": [{
                         "relativePath": "shard/phase-receipt.json", "bytes": 7, "sha256": digest}]}]}
        self.assertEqual(value, qualification.validate(value))
        with patch("products.verified_evidence.runtime_original_cache", return_value=object()), \
                self.assertRaisesRegex(ValueError, "aggregate signature admission"):
            qualification.export_originals([{"kind": "aggregate"}], Path("unused"), plan={},
                producer={}, source_commit="a" * 40, trusted_workflow_sha="b" * 40, token="fixture")

    def test_native_authority_pins_and_exact_original_bindings(self):
        case = fixture.RuntimeOriginalCiTest()
        case.setUp()
        self.addCleanup(case.doCleanups)
        # Keep the synthetic HTTP functions fixed for the whole verification
        # profile; restoring a patched verifier midway correctly changes it.
        for mocked in (patch("reuse.api_request", side_effect=case.api()), patch.object(
                adapter, "download_artifact_to_file", side_effect=case.download_fixture)):
            mocked.start()
            self.addCleanup(mocked.stop)
        with patch("reuse.api_request", side_effect=case.api()), patch.object(
                adapter, "download_artifact_to_file", side_effect=case.download_fixture):
            captured = adapter.capture_runtime_original_ci_phases(
                {"binary": case.receipts["binary"]}, case.root / "cold",
                target=TARGET, trusted_workflow_sha=case.pin, token="not-a-real-token",
                recovery_projection=True)
        receipt = load_canonical_json_bytes(case.receipts["binary"].read_bytes())
        instance = PhaseInstanceId("runtime", TARGET, "binary", TARGET)
        artifact = captured["artifacts"]["binary"]
        source = {"kind": "phase", "receipt": receipt,
                  "artifactId": artifact["id"], "artifactSha256": artifact["digest"]}
        plan = {"event": "pull_request", "pullRequest": case.producer["pullRequest"],
                "repository": case.producer["repository"]}
        with patch("reuse.api_request", side_effect=case.api()):
            artifact, _, observed, workflow = adapter._authenticate_runtime_original_reference_source(
                plan, {**case.producer, "runId": 100}, source,
                trusted_workflow_sha=case.pin, token="not-a-real-token")
        job = next(row for row in observed[0]["jobs"] if row["name"].endswith(f"-{TARGET}-binary-{TARGET}"))
        locator = adapter._runtime_original_locator(artifact, workflow, instance, job)
        original = runtime_original_cache().read(locator)
        self.assertIsNotNone(original)
        record = {**original, "receiptSha256": sha256_bytes(canonical_json_bytes(receipt))}
        value = {"schemaVersion": 1, "sourceCommit": "a" * 40,
                 "verifierPolicySha256": original["identity"]["policy"], "originals": [record]}
        self.assertEqual(value, qualification.validate(value))
        paired = copy.deepcopy(value)
        other = copy.deepcopy(record)
        other["identity"]["locator"]["artifact"]["id"] += 1
        paired["originals"].append(other)
        self.assertEqual(paired, qualification.validate(paired))
        other["receipt"]["outputs"][0]["sha256"] = sha256_bytes(b"different output")
        other["receiptSha256"] = sha256_bytes(canonical_json_bytes(other["receipt"]))
        with self.assertRaisesRegex(ValueError, "Same phase key has conflicting qualified outputs"):
            qualification.validate(paired)
        with patch("reuse.api_request", side_effect=case.api()):
            issued = qualification.export_originals([source], case.root / "issued.json", plan=plan,
                producer={**case.producer, "runId": 100}, source_commit="a" * 40,
                trusted_workflow_sha=case.pin, token="not-a-real-token")
        self.assertEqual(value, issued)
        with patch("reuse.api_request", side_effect=case.api()), self.assertRaises(FileExistsError):
            qualification.export_originals([source], case.root / "issued.json", plan=plan,
                producer={**case.producer, "runId": 100}, source_commit="a" * 40,
                trusted_workflow_sha=case.pin, token="not-a-real-token")
        self.assertEqual(canonical_json_bytes(value), (case.root / "issued.json").read_bytes())
        with patch("reuse.api_request", side_effect=case.api()), \
                patch("products.verified_evidence.RuntimeOriginalCache.read", return_value=None), \
                self.assertRaisesRegex(ValueError, "completed exact original"):
            qualification.export_originals([source], case.root / "unqualified.json", plan=plan,
                producer={**case.producer, "runId": 100}, source_commit="a" * 40,
                trusted_workflow_sha=case.pin, token="not-a-real-token")
        self.assertFalse((case.root / "unqualified.json").exists())
        path, bundle = case.root / "qualification.json", case.root / "bundle.jsonl"
        path.write_bytes(canonical_json_bytes(value))
        bundle.write_bytes(b"fixture, not a cryptographic attestation\n")
        pins = {"signer_commit": "a" * 40, "source_commit": "b" * 40,
                "policy_sha256": value["verifierPolicySha256"]}
        verified = subprocess.CompletedProcess([], 0, json.dumps(
            [{"verificationResult": {"statement": "fixture"}}]).encode(), b"")
        with patch.object(qualification.subprocess, "run", return_value=verified) as native:
            self.assertEqual(value, qualification.authenticate(path, bundle, **pins))
        command = native.call_args.args[0]
        for flag, expected in (("--signer-digest", pins["signer_commit"]),
                ("--source-digest", pins["source_commit"]), ("--repo", qualification.REPOSITORY),
                ("--signer-workflow", f"{qualification.REPOSITORY}/{qualification.ISSUER_WORKFLOW}")):
            self.assertEqual(expected, command[command.index(flag) + 1])
        self.assertIn("--deny-self-hosted-runners", command)
        import hydrated_evidence
        from products.restore import verification_session
        with patch.dict(os.environ, {"CODEX_AGENT_HYDRATED_EVIDENCE": str(case.root / "raw-cache")}):
            projection_rows = [row for row in original["originalFiles"]
                               if not row["relativePath"].startswith("inputs/")]
            for row in projection_rows:
                hydrated_evidence.retain(row, case.root / "cold/phases/binary/original" / row["relativePath"])
            # The restored raw cache contains neither authority nor local seals.
            shutil.rmtree(case.root / "persistent-cache")
            shutil.rmtree(case.root / "authority")
            with verification_session() as session, patch.object(
                    qualification.subprocess, "run", return_value=verified) as native:
                projected = qualification.projection(locator, path, bundle,
                    signer_commit=pins["signer_commit"], source_commit=pins["source_commit"])
                self.assertIsNotNone(projected)
                self.assertEqual(1, session["qualificationHits"])
                self.assertEqual(sum(row["bytes"] for row in projection_rows), session["qualificationBodyReadBytes"])
                self.assertEqual(projected, qualification.projection(locator, path, bundle,
                    signer_commit=pins["signer_commit"], source_commit=pins["source_commit"]))
                self.assertEqual(1, native.call_count)
                self.assertFalse((case.root / "authority").exists())
            # A later public capture operation loses the first private session.
            # It must authenticate native authority again and use the real
            # shared fresh-locator path, rather than downloading the archive.
            options = {"CODEX_AGENT_REUSE_QUALIFICATION": str(path),
                       "CODEX_AGENT_REUSE_QUALIFICATION_BUNDLE": str(bundle),
                       "CODEX_AGENT_REUSE_QUALIFICATION_ISSUER": pins["signer_commit"],
                       "CODEX_AGENT_REUSE_QUALIFICATION_SOURCE": pins["source_commit"]}
            with patch.dict(os.environ, options), patch.object(
                    qualification.subprocess, "run", return_value=verified) as native, patch.object(
                    adapter, "download_artifact_to_file", side_effect=AssertionError("warm archive download")):
                reused = adapter.capture_runtime_original_ci_phases(
                    {"binary": case.receipts["binary"]}, case.root / "portable-warm",
                    target=TARGET, trusted_workflow_sha=case.pin, token="not-a-real-token",
                    recovery_projection=True)
            self.assertEqual(captured["artifacts"], reused["artifacts"])
            self.assertEqual(1, native.call_count)
            self.assertFalse((case.root / "persistent-cache/v1/verified-runtime-originals/blobs").exists())
            # Corruption cannot be converted into a completed private witness.
            hydrated_evidence.blob(projection_rows[0]).write_bytes(b"corrupt cache body")
            with verification_session() as session, patch.object(
                    qualification.subprocess, "run", return_value=verified), self.assertRaises(ValueError):
                qualification.projection(locator, path, bundle,
                    signer_commit=pins["signer_commit"], source_commit=pins["source_commit"])
            self.assertNotIn("qualifiedOriginalProjections", session)
        with patch.object(qualification.subprocess, "run", return_value=verified):
            for changed in ({**pins, "signer_commit": "c" * 40},
                            {**pins, "policy_sha256": "sha256:" + "0" * 64}):
                with self.assertRaisesRegex(ValueError, "incompatible"):
                    qualification.authenticate(path, bundle, **changed)
        for changed in ("receipt", "object", "policy", "duplicate"):
            tampered = copy.deepcopy(value)
            if changed == "receipt":
                tampered["originals"][0]["receipt"]["productVersion"] = "999.0.0"
            elif changed == "object":
                tampered["originals"][0]["objectSha256"] = "unhashed"
            elif changed == "policy":
                tampered["originals"][0]["identity"]["policy"] = "prior-policy"
            else:
                tampered["originals"].append(copy.deepcopy(record))
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                qualification.validate(tampered)
        with patch.object(qualification.subprocess, "run", side_effect=subprocess.CalledProcessError(
                1, ["gh", "attestation", "verify"], stderr=b"invalid signature or unsupported pin flag")), \
                self.assertRaises(subprocess.CalledProcessError):
            qualification.authenticate(path, bundle, **pins)
        with patch.object(qualification.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, b"[]")), \
                self.assertRaisesRegex(ValueError, "no verified"):
            qualification.authenticate(path, bundle, **pins)


if __name__ == "__main__":
    unittest.main()


class PortablePolicyTest(unittest.TestCase):
    def test_independent_source_and_loaded_code_profile(self):
        source = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory(prefix="portable-profile-test-") as temporary:
            root = Path(temporary).resolve()
            for folder in ("ci", ".github"):
                for path in (source / folder).rglob("*"):
                    relative = path.relative_to(source)
                    if (path.is_file() and path.suffix in {".py", ".json", ".yaml", ".yml", ".sh", ".js", ".mjs"}
                            and not {"tests", "__pycache__", "node_modules"}.intersection(relative.parts)):
                        target = root / relative
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(path.read_bytes())
            def git(*args):
                return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True).stdout
            git("init", "-q")
            git("add", "ci", ".github")
            git("-c", "user.name=Qualification Test", "-c", "user.email=test@example.invalid",
                "commit", "-qm", "Trusted control baseline")
            commit = git("rev-parse", "HEAD").decode().strip()
            script = ("import sys; sys.path.insert(0, sys.argv[1]); "
                      "import reuse_qualification as q; import product_reuse as p; "
                      "{mutation}; print(q._compatible_verifier(sys.argv[2]))")
            for mutation, successful in (
                ("pass", True),
                ("from pathlib import Path; from products.verified_evidence import _source_identity; "
                 "before = _source_identity(); caller = Path('.github/workflows/portable-reuse-proof.yml'); "
                 "caller.write_text(caller.read_text() + '\\n# caller-only change\\n'); "
                 "assert _source_identity() != before", True),
                ("p._retry_github_get = lambda operation: operation", False),
                ("q.LIMIT += 1", False),
                ("q.configure.__defaults__ = (False,)", False),
                ("from pathlib import Path; sdk = Path('.github/workflows/sdk-validation.yml'); "
                 "sdk.write_text(sdk.read_text() + '\\n# incompatible SDK policy change\\n')", False),
                ("from pathlib import Path; issuer = Path('.github/workflows/reuse-qualification.yml'); "
                 "issuer.write_text(issuer.read_text() + '\\n# incompatible issuer change\\n')", False),
                ("from pathlib import Path; Path('.github/extra-authority.py').write_text('# extra')", False),
            ):
                with self.subTest(mutation=mutation):
                    result = subprocess.run([sys.executable, "-I", "-S", "-c", script.format(mutation=mutation),
                                             str(root / "ci"), commit], cwd=root, capture_output=True, timeout=90)
                    self.assertEqual(result.returncode == 0, successful, result.stderr.decode())
                    git("checkout", "--", ".github/workflows")
            self.assertEqual(git("rev-parse", "HEAD").decode().strip(), commit)


class QualificationTransportTest(unittest.TestCase):
    def test_carrier_reference_receipt_copy_is_exact(self):
        source = {"relativePath": "original", "receipt": {"original": "receipt bytes"}}
        raw = canonical_json_bytes(source["receipt"])
        member = {"relativePath": "original/shard/phase-receipt.json", "source": "original",
                  "sourcePath": "shard/phase-receipt.json", "sha256": sha256_bytes(raw), "bytes": len(raw)}
        self.assertEqual(qualification._original_receipt_bytes(source, [member]), raw)
        for field, changed in (("source", "other"), ("sourcePath", "other"),
                               ("bytes", len(raw) + 1), ("sha256", "sha256:" + "0" * 64)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                qualification._original_receipt_bytes(source, [{**member, field: changed}])
        with self.assertRaises(ValueError):
            qualification._original_receipt_bytes(source, [member, member])

    def test_fixed_issuer_metadata_and_bounded_artifact(self):
        import io
        import zipfile
        import product_reuse as products
        commit, issuer = "a" * 40, "b" * 40
        run = {"id": 123, "run_attempt": 1, "path": ".github/workflows/portable-reuse-proof.yml",
               "event": "pull_request", "head_sha": commit,
               "repository": {"full_name": qualification.REPOSITORY, "fork": False},
               "head_repository": {"full_name": qualification.REPOSITORY, "fork": False},
               "pull_requests": [{"number": 31}],
               "referenced_workflows": [{"path": f"{qualification.REPOSITORY}/{qualification.ISSUER_WORKFLOW}@{issuer}",
                                         "sha": issuer}]}
        job = {"id": 456, "run_id": 123, "head_sha": commit, "name": "cold / qualify",
               "status": "completed", "conclusion": "success", "started_at": "2026-10-05T01:00:00Z",
               "completed_at": "2026-10-05T01:02:00Z"}
        def archive(extra=False):
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, "w") as output:
                for name in ("qualification.json", "bundle.jsonl", "qualification-issue.json", "proof.json",
                             "prepare.json", "cache-save.json"):
                    output.writestr(name, b"{}\n")
                if extra:
                    output.writestr("private-key", b"untrusted")
            return stream.getvalue()
        raw = archive()
        artifact = {"id": 789, "digest": sha256_bytes(raw), "expired": False,
                    "name": "reuse-qualification-123-1", "created_at": "2026-10-05T01:01:00Z",
                    "archive_download_url": f"https://api.github.com/repos/{qualification.REPOSITORY}/actions/artifacts/789/zip",
                    "workflow_run": {"id": 123, "head_sha": commit}, "size_in_bytes": len(raw)}
        def api(url, token):
            if "/git/commits/" in url:
                return {"sha": commit, "tree": {"sha": "c" * 40}}
            return run if "/attempts/" in url else artifact
        with tempfile.TemporaryDirectory(prefix="qualification-transport-test-") as temporary, \
                patch.object(products, "api_json", side_effect=api), \
                patch.object(products, "paginated_items", return_value=[job]), \
                patch.object(products, "_observe_tested_commit", return_value={"sha": commit}) as tested, \
                patch.object(products, "download_artifact", return_value=raw) as download, \
                patch.object(qualification, "authenticate", return_value={"localTransportTest": True}) as native:
            options = dict(artifact_id=789, artifact_sha256=artifact["digest"], run_id=123, run_attempt=1,
                           signer_commit=issuer, source_commit=commit, token="synthetic")
            result = qualification.fetch_qualification(Path(temporary) / "valid", **options)
            self.assertEqual(result["downloadedQualificationBytes"], len(raw))
            self.assertEqual(tested.call_args.kwargs["expected_commit"], commit)
            self.assertEqual(native.call_args.kwargs["signer_commit"], issuer)
            self.assertEqual(native.call_args.kwargs["source_commit"], commit)
            for field, changed in (("event", "workflow_dispatch"), ("run_attempt", 2),
                                   ("path", ".github/workflows/ci.yml")):
                original = run[field]
                run[field] = changed
                with self.subTest(field=field), self.assertRaises(ValueError):
                    qualification.fetch_qualification(Path(temporary) / field, **options)
                run[field] = original
            job["conclusion"] = "failure"
            with self.assertRaisesRegex(ValueError, "did not succeed"):
                qualification.fetch_qualification(Path(temporary) / "failed", **options)
            job["conclusion"] = "success"
            artifact["created_at"] = "2026-10-05T01:03:00Z"
            with self.assertRaisesRegex(ValueError, "outside"):
                qualification.fetch_qualification(Path(temporary) / "wrong-window", **options)
            artifact["created_at"] = "2026-10-05T01:01:00Z"
            self.assertEqual(native.call_count, 1)
            self.assertEqual(download.call_count, 1)
            bad = archive(extra=True)
            download.return_value = bad
            artifact.update(digest=sha256_bytes(bad), size_in_bytes=len(bad))
            with self.assertRaisesRegex(ValueError, "unexpected"):
                qualification.fetch_qualification(Path(temporary) / "extra", **{**options, "artifact_sha256": artifact["digest"]})
            self.assertEqual(native.call_count, 1)
