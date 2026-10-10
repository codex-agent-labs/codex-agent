"""Cross-process original authentication reuse; real verifiers, synthetic HTTP."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from ci.tests import test_runtime_original_ci as runtime_fixture

adapter = runtime_fixture.adapter
fixture = runtime_fixture.fixture


def probe(shared, mode):
    shared = Path(shared).resolve()
    case = runtime_fixture.RuntimeOriginalCiTest()
    case.setUp()
    try:
        upload = case.root / "runtime-uploads/binary"
        (upload / "inputs").mkdir()
        (upload / "inputs/predecessor.bin").write_bytes(b"irrelevant predecessor\n" * 524_288)
        (upload / "opaque-proof.bin").write_bytes(b"required original proof\n" * 65_536)
        if mode == "cold":
            shared.mkdir(parents=True, exist_ok=True)
            raw = fixture.archive_tree(upload)
            (shared / "original.zip").write_bytes(raw)
        else:
            raw = (shared / "original.zip").read_bytes()
        case.archives["binary"] = raw
        case.artifacts["binary"].update(digest=fixture.sha256_bytes(raw), size_in_bytes=len(raw))
        instance = runtime_fixture.PhaseInstanceId("runtime", runtime_fixture.TARGET, "binary", runtime_fixture.TARGET)
        receipt = fixture.load_canonical_json_bytes(case.receipts["binary"].read_bytes())
        plan = {"event": "pull_request", "pullRequest": 31, "repository": fixture.REPOSITORY}
        run = case.failed_run()
        downloaded = extracted = 0
        api = case.api(run=run)
        actual_extract = adapter._extract_runtime_original_projection

        def request(url, token):
            nonlocal downloaded
            body = api(url, token)
            if url.endswith("/zip"):
                downloaded += len(body)
            return body

        def download(artifact, token, destination, **kwargs):
            nonlocal downloaded
            downloaded += len(raw)
            Path(destination).write_bytes(raw)

        def extract(archive, zipped, destination):
            nonlocal extracted
            import zipfile
            with zipfile.ZipFile(archive) as archive_file:
                extracted += sum(info.file_size for info in archive_file.infolist()
                                 if not info.filename.startswith("inputs/"))
            return actual_extract(archive, zipped, destination)

        with mock.patch("products.verified_evidence._authority_root", return_value=shared / "authority"), \
                mock.patch("products.verified_evidence.native_cache_root", return_value=shared / "cas"), \
                mock.patch("reuse.api_request", side_effect=request) as requests, \
                mock.patch.object(adapter, "download_artifact_to_file", side_effect=download), \
                mock.patch.object(adapter, "_extract_runtime_original_projection", side_effect=extract):
            started = time.perf_counter()
            captured = case.root / "discovered"
            adapter.capture_prior_failed_runtime_phases(plan, {"runId": 100, "runAttempt": 1},
                {instance: receipt["buildKey"]}, captured, trusted_workflow_sha=case.pin,
                token="not-a-real-token", attempts=(run,))
            # Independent public operation/session: all original gates still run.
            admitted = adapter._prior_failed_runtime_objects(captured, case.root,
                trusted_workflow_sha=case.pin, token="not-a-real-token", plan=plan,
                consumer_producer={"runId": 100, "runAttempt": 1})
            from products.inventory import regular_file_inventory
            inventory = regular_file_inventory(captured, allow_empty=True)
            return {"mode": mode, "downloadedBytes": downloaded, "extractedBytes": extracted,
                    "seconds": time.perf_counter() - started, "records": admitted,
                    "inventory": inventory, "freshApiRequests": requests.call_count}
    finally:
        case.doCleanups()


class PersistentRuntimeEvidenceTest(unittest.TestCase):
    def test_actual_cli_loaded_policy_is_bound_without_importing_another_verifier(self):
        script = '''
import runpy, sys, types
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'ci'))
namespace = runpy.run_path('ci/product_reuse.py', run_name='cli_policy_probe')
main = types.ModuleType('__main__')
main.__dict__.update(namespace)
sys.modules['__main__'] = main
from products.verified_evidence import _source_identity
before = _source_identity()
main._CATALOG_ZIP_LIMITS['max_members'] = 1
assert before != _source_identity()
assert 'product_reuse' not in sys.modules
'''
        subprocess.run([sys.executable, "-c", script], check=True, capture_output=True, text=True)

    def test_concurrent_conflicting_seals_fail_closed(self):
        from products.verified_evidence import RuntimeOriginalCache
        from products.inventory import regular_file_inventory
        from concurrent.futures import ThreadPoolExecutor
        import threading
        with tempfile.TemporaryDirectory(prefix="persistent-concurrent-conflict-") as temporary:
            root = Path(temporary).resolve()
            original = root / "original"
            original.mkdir()
            (original / "proof").write_bytes(b"fully verified original")
            with mock.patch("products.verified_evidence._authority_root", return_value=root / "authority"), \
                    mock.patch("products.verified_evidence.native_cache_root", return_value=root / "cas"):
                cache = RuntimeOriginalCache()
                read = cache.read
                barrier = threading.Barrier(2)

                def both_observe_missing(locator):
                    record = read(locator)
                    if record is None:
                        barrier.wait(timeout=10)
                    return record

                def publish(producer):
                    try:
                        cache.record_verified({}, original, regular_file_inventory(original),
                                              {"producer": producer}, "sha256:" + "b" * 64)
                    except ValueError as error:
                        self.assertIn("conflicting", str(error))
                        return "rejected"
                    return "accepted"

                with mock.patch.object(cache, "read", side_effect=both_observe_missing), \
                        ThreadPoolExecutor(max_workers=2) as executor:
                    results = list(executor.map(publish, ("one original", "different original")))
                self.assertEqual(["accepted", "rejected"], sorted(results))

    def test_authority_overlap_symlink_publication_and_loaded_verifier_identity(self):
        from products.verified_evidence import RuntimeOriginalCache, _source_identity, _private_key
        from products.inventory import regular_file_inventory
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory(prefix="persistent-authority-boundaries-") as temporary:
            root = Path(temporary).resolve()
            authority = root / "authority"
            with mock.patch("products.verified_evidence._authority_root", return_value=authority), \
                    mock.patch("products.verified_evidence.native_cache_root", return_value=root):
                with self.assertRaisesRegex(ValueError, "disjoint"):
                    RuntimeOriginalCache()
                self.assertFalse(authority.exists())
            with ThreadPoolExecutor(max_workers=4) as executor:
                keys = list(executor.map(lambda _: _private_key(authority), range(4)))
            self.assertTrue(all(len(key) == 32 and key == keys[0] for key in keys))
            policy = _source_identity()
            with mock.patch.object(adapter, "_contract_ci_upload_metadata", lambda *args: {"new": "verifier"}):
                self.assertNotEqual(policy, _source_identity())
            self.assertEqual(policy, _source_identity())
            from products.registry import PhaseInstanceId, PhaseId
            with mock.patch.object(PhaseInstanceId, "logical_phase", property(
                    lambda instance: PhaseId(instance.product, instance.component, "binary"))):
                self.assertNotEqual(policy, _source_identity())
            self.assertEqual(policy, _source_identity())
            with mock.patch.dict(adapter._CATALOG_ZIP_LIMITS, {"max_members": 1}):
                self.assertNotEqual(policy, _source_identity())
            self.assertEqual(policy, _source_identity())
            from products.verified_evidence import runtime_original_cache
            from products.restore import verification_session
            with mock.patch("products.verified_evidence._authority_root", return_value=authority), \
                    mock.patch("products.verified_evidence.native_cache_root", return_value=root / "session-cas"), \
                    verification_session():
                runtime_original_cache()
                with mock.patch.dict(adapter._CATALOG_ZIP_LIMITS, {"max_members": 1}):
                    with self.assertRaisesRegex(ValueError, "policy changed"):
                        runtime_original_cache()
            original = root / "original"
            original.mkdir()
            (original / "proof").write_bytes(b"verified bytes")
            rows = regular_file_inventory(original)
            for directory in ("records", "blobs"):
                with mock.patch("products.verified_evidence._authority_root", return_value=authority), \
                        mock.patch("products.verified_evidence.native_cache_root", return_value=root / directory):
                    cache = RuntimeOriginalCache()
                    cache.root.mkdir(parents=True)
                    outside = root / (directory + "-outside")
                    outside.mkdir()
                    (cache.root / directory).symlink_to(outside, target_is_directory=True)
                    with self.assertRaisesRegex(ValueError, "unsafe"):
                        cache.record_verified({}, original, rows, {}, "sha256:" + "b" * 64)
                    self.assertEqual([], list(outside.iterdir()))

    def test_separate_process_discovery_and_recheck_do_not_download_or_extract_warm(self):
        with tempfile.TemporaryDirectory(prefix="persistent-runtime-proof-") as temporary:
            results = []
            for mode in ("cold", "warm"):
                script = ("import json; from ci.tests.test_persistent_runtime_evidence import probe; "
                          f"print(json.dumps(probe({temporary!r}, {mode!r})))")
                result = subprocess.run([sys.executable, "-c", script], check=True, capture_output=True, text=True)
                results.append(json.loads(result.stdout))
            cold, warm = results
            self.assertGreater(cold["downloadedBytes"], 10 * 1024 * 1024)
            self.assertGreater(cold["extractedBytes"], 1024 * 1024)
            self.assertLess(cold["extractedBytes"], cold["downloadedBytes"])
            self.assertEqual(0, warm["downloadedBytes"])
            self.assertEqual(0, warm["extractedBytes"])
            self.assertEqual(cold["records"], warm["records"])
            self.assertEqual(cold["inventory"], warm["inventory"])
            self.assertGreater(warm["freshApiRequests"], 0)

    def test_seal_corruption_partial_body_changed_policy_and_wrong_locator(self):
        from products.verified_evidence import RuntimeOriginalCache
        from products.inventory import regular_file_inventory
        with tempfile.TemporaryDirectory(prefix="persistent-runtime-negatives-") as temporary:
            root = Path(temporary).resolve()
            original = root / "original"
            original.mkdir()
            (original / "proof").write_bytes(b"authenticated original bytes")
            rows = regular_file_inventory(original)
            with mock.patch("products.verified_evidence._authority_root", return_value=root / "authority"), \
                    mock.patch("products.verified_evidence.native_cache_root", return_value=root / "cas"):
                cache = RuntimeOriginalCache()
                locator = {"authenticatedOrigin": "original workflow/job/upload", "receiptSha": "a" * 64}
                cache.record_verified(locator, original, rows, {"producer": "exact original"}, "sha256:" + "b" * 64)
                record = cache.read(locator)
                path, _ = cache._entry(locator)
                raw = path.read_bytes()
                forged = fixture.load_canonical_json_bytes(raw)
                forged["record"]["receipt"]["producer"] = "caller claim"
                path.write_bytes(fixture.canonical_json_bytes(forged))
                with self.assertRaisesRegex(ValueError, "seal"):
                    cache.read(locator)
                path.write_bytes(raw)
                self.assertIsNone(cache.read({**locator, "authenticatedOrigin": "wrong workflow/job/upload"}))
                with mock.patch("products.verified_evidence._source_identity", return_value="changed verifier/policy"):
                    self.assertIsNone(RuntimeOriginalCache().read(locator))
                blob = cache._blob(rows[0])
                original_bytes = blob.read_bytes()
                blob.write_bytes(b"x" * len(original_bytes))
                with self.assertRaisesRegex(ValueError, "digest"):
                    cache.materialize(record, root / "tampered")
                blob.unlink()
                with self.assertRaises(ValueError):
                    cache.materialize(record, root / "partial")
                # A seal cannot travel to a machine lacking its verifier authority.
                with mock.patch("products.verified_evidence._authority_root", return_value=root / "other-authority"):
                    with self.assertRaisesRegex(ValueError, "seal"):
                        RuntimeOriginalCache().read(locator)


if __name__ == "__main__":
    unittest.main()
