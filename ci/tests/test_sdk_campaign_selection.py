"""Structural SDK campaign selection fixtures, not hosted release evidence."""

from contextlib import contextmanager, redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import ci.products.sdk_campaign_dev_catalog as dev_catalog
from ci import sdk_campaign_catalog_producer as campaign
from ci import sdk_campaign_reused_original as reused_catalog
from ci.sdk_campaign_observation import ObservedSdkOriginal
from ci.sdk_campaign_catalog_caller import (
    SDK_CAMPAIGN_INSTANCES as CALLER_SDK_INSTANCES,
    main as catalog_caller_main,
    stage_completed_sdk_catalog,
)
import ci.sdk_campaign_catalog_caller as catalog_caller
from ci.products.index import IndexEntrySource
from ci.products.index import SignedProductIndex, verify_signed_product_index
from ci.products.receipt import write_output_manifest
from ci.products.restore import finalize_phase_object, object_relative_path
from ci.products.inventory import sha256_bytes
from ci.products.sdk_campaign_dev_catalog import stage_sdk_same_pr_catalog
from ci.products.sdk_campaign_selection import (
    SDK_CAMPAIGN_INSTANCES, held_sdk_campaign_selection, verify_sdk_campaign_objects,
    verify_sdk_campaign_selection,
)
from ci.tests.product_chain_support import write_receipt
from ci.tests.test_product_resume_capture import archive


class SdkCampaignSelectionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="sdk-campaign-selection-")
        cls.root = Path(cls.temporary.name).resolve()
        cls.sources, cls.envelopes, cls.archives, cls.stages = {}, {}, {}, {}
        producer = {"repository": "owner/repository", "workflowPath": ".github/workflows/product-validation.yml",
                    "commit": "a" * 40, "tree": "b" * 40, "event": "pull_request",
                    "runId": 3, "runAttempt": 1, "pullRequest": 31}
        for position, instance in enumerate(sorted(SDK_CAMPAIGN_INSTANCES)):
            directory = cls.root / str(position)
            stage = directory / "stage"
            output = stage / "outputs/fixture"
            output.mkdir(parents=True)
            (output / "content.bin").write_bytes(str(instance).encode())
            manifest = write_output_manifest(stage, instance.product, instance.component,
                instance.phase, instance.target, "0.8.0", {"fixture": "outputs/fixture"})
            receipt = write_receipt(directory / "planned.json", product="sdk",
                component=instance.component, phase=instance.phase, target=instance.target,
                version="0.8.0", version_identity="0.8.0", outputs=manifest["outputs"],
                upstream=[], context={"producer": producer})
            plan = {name: receipt[name] for name in (
                "schemaVersion", "product", "component", "phase", "target", "buildKey", "inputs")}
            shard = directory / "shard"
            finalized = finalize_phase_object(stage_root=stage, phase_plan=plan,
                producer=producer, product_version="0.8.0", trust_domain="development",
                destination=shard)
            cls.sources[instance] = IndexEntrySource(finalized["receiptBytes"],
                "outputs/fixture/content.bin")
            cls.envelopes[instance] = {name: finalized[name] for name in (
                "receipt", "receiptBytes", "receiptSha256", "objectSha256")}
            cls.archives[instance] = shard / finalized["objectPath"]
            cls.stages[instance] = stage

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_complete_exact_selection(self):
        selected = verify_sdk_campaign_selection(
            self.sources, self.envelopes, self.archives, self.stages)
        self.assertEqual(verify_sdk_campaign_objects(
            self.sources, self.envelopes, self.archives), selected)
        self.assertEqual(set(selected), SDK_CAMPAIGN_INSTANCES)
        self.assertEqual({receipt["productVersion"] for receipt in selected.values()}, {"0.8.0"})

    def test_same_pr_catalog_keeps_all_originals_and_development_trust(self):
        with tempfile.TemporaryDirectory(prefix="sdk-campaign-catalog-") as temporary:
            destination = Path(temporary).resolve() / "catalog"
            producer = next(iter(self.envelopes.values()))["receipt"]["producer"]
            index = stage_sdk_same_pr_catalog(self.sources, self.envelopes,
                self.archives, producer=producer, destination=destination)
            signed, _ = verify_signed_product_index(SignedProductIndex(
                destination / "product-index.json", destination / "product-index.sig"),
                destination / "public-key.pub")
            self.assertEqual(signed, index)
            self.assertEqual(len(index["entries"]), len(SDK_CAMPAIGN_INSTANCES))
            self.assertEqual(index["trustDomain"], "development")
            first = min(SDK_CAMPAIGN_INSTANCES)
            self.assertEqual(
                (destination / object_relative_path(self.envelopes[first]["receipt"]["buildKey"],
                    sha256_bytes(self.sources[first].receipt_bytes))).read_bytes(),
                self.archives[first].read_bytes(),
            )

    def test_completed_pin_checks_real_signed_exact_61_catalog(self):
        producer = next(iter(self.envelopes.values()))["receipt"]["producer"]
        name = (f"codex-agent-product-catalog-v1-pull-request-{producer['pullRequest']}-"
                f"{producer['tree']}-attempt-{producer['runAttempt']}")
        with tempfile.TemporaryDirectory(prefix="sdk-completed-catalog-") as temporary:
            destination = Path(temporary).resolve() / "catalog"
            stage_sdk_same_pr_catalog(self.sources, self.envelopes, self.archives,
                producer=producer, destination=destination)
            raw = archive({row["relativePath"]: (destination / row["relativePath"]).read_bytes()
                for row in dev_catalog.regular_file_inventory(destination)})
            digest = sha256_bytes(raw)
            index_sha = sha256_bytes((destination / "product-index.json").read_bytes())
            key_sha = sha256_bytes((destination / "public-key.pub").read_bytes())
            def original_id(instance):
                return reused_catalog.PhaseInstanceId(instance.product, instance.component,
                    instance.phase, instance.target)
            observations = {original_id(instance): ObservedSdkOriginal(
                source.receipt_bytes, b"unused-replay", self.archives[instance], self.stages[instance])
                for instance, source in self.sources.items()}
            artifact_paths = {original_id(instance): source.artifact_path
                for instance, source in self.sources.items()}
            api = f"https://api.github.com/repos/{producer['repository']}/actions/artifacts/901"
            artifact = {"id": 901, "name": name, "digest": digest,
                "expired": False, "size_in_bytes": len(raw),
                "archive_download_url": api + "/zip",
                "created_at": "2026-01-01T00:05:00Z",
                "workflow_run": {"id": producer["runId"], "head_sha": producer["commit"]}}
            run = {"id": producer["runId"], "run_attempt": producer["runAttempt"],
                "path": producer["workflowPath"], "head_sha": producer["commit"]}
            observed = {"run": run, "testedCommit": {"sha": producer["commit"],
                "tree": {"sha": producer["tree"]}}}
            job = {"name": "product-validation / sdk-catalog",
                "started_at": "2026-01-01T00:00:00Z", "completed_at": "2026-01-01T00:10:00Z"}
            completed_pin = {"producer": producer, "artifact_name": name,
                "artifact_id": 901, "artifact_sha256": digest,
                "index_sha256": index_sha, "public_key_sha256": key_sha,
                "trusted_workflow_path": ".github/workflows/product-validation.yml",
                "trusted_job_name": job["name"]}
            def download(_artifact, _token, path, **_kwargs):
                Path(path).write_bytes(raw)
            with patch.object(reused_catalog.product_reuse, "api_json", return_value=artifact), \
                 patch.object(reused_catalog.product_reuse, "download_artifact_to_file", side_effect=download), \
                 patch.object(reused_catalog.product_reuse, "_same_pr_run", return_value=observed), \
                 patch.object(reused_catalog.product_reuse, "_observe_ci_producer_jobs",
                     return_value=[{**observed, "jobs": [job]}]):
                with reused_catalog.held_completed_sdk_catalog(
                        producer=producer, artifact_name=name,
                        artifact_id=901, artifact_sha256=digest,
                        index_sha256=index_sha, public_key_sha256=key_sha,
                        trusted_workflow_sha="a" * 40, token="synthetic-token", environ={},
                        trusted_workflow_path=".github/workflows/product-validation.yml",
                        trusted_job_name=job["name"]) as held:
                    self.assertEqual(index_sha, held.values["indexSha256"])
                    reused_catalog.verify_completed_sdk_catalog_originals(
                        held, observations, artifact_paths)
                    wrong_paths = dict(artifact_paths)
                    wrong_paths[min(reused_catalog.SDK_CAMPAIGN_INSTANCES)] = "outputs/other.bin"
                    with self.assertRaisesRegex(ValueError, "selected artifact"):
                        reused_catalog.verify_completed_sdk_catalog_originals(
                            held, observations, wrong_paths)
                    first, second = sorted(observations)[:2]
                    crossed = dict(observations)
                    crossed[first] = ObservedSdkOriginal(observations[first].receipt_bytes,
                        b"unused-replay", observations[second].object_path,
                        observations[first].stage_path)
                    with self.assertRaises(ValueError):
                        reused_catalog.verify_completed_sdk_catalog_originals(
                            held, crossed, artifact_paths)
                @contextmanager
                def semantic_replay(*_args, **_kwargs):
                    yield ({"verified": True}, {"workers": True})
                with patch.object(campaign, "held_sdk_campaign_semantic_replay",
                        side_effect=semantic_replay) as replay:
                    with campaign.held_completed_sdk_campaign_replay(
                            observations, b"current-transport", {}, artifact_paths, {},
                            completed_catalog_pin=completed_pin,
                            trusted_workflow_sha="a" * 40, token="synthetic-token",
                            environ={}) as result:
                        self.assertEqual(({"verified": True}, {"workers": True}), result)
                    replay.assert_called_once()
                    with self.assertRaisesRegex(ValueError, "selected artifact"):
                        with campaign.held_completed_sdk_campaign_replay(
                                observations, b"current-transport", {}, wrong_paths, {},
                                completed_catalog_pin=completed_pin,
                                trusted_workflow_sha="a" * 40, token="synthetic-token",
                                environ={}):
                            pass
                    replay.assert_called_once()
                with self.assertRaisesRegex(ValueError, "independent digest"):
                    with reused_catalog.held_completed_sdk_catalog(
                            producer=producer, artifact_name=name, artifact_id=901,
                            artifact_sha256=digest, index_sha256=index_sha,
                            public_key_sha256="sha256:" + "0" * 64,
                            trusted_workflow_sha="a" * 40, token="synthetic-token", environ={},
                            trusted_workflow_path=".github/workflows/product-validation.yml",
                            trusted_job_name=job["name"]):
                        pass
                with self.assertRaisesRegex(ValueError, "current attempt"):
                    with reused_catalog.held_completed_sdk_catalog(
                            producer=producer, artifact_name=name + "-stale", artifact_id=901,
                            artifact_sha256=digest, index_sha256=index_sha,
                            public_key_sha256=key_sha,
                            trusted_workflow_sha="a" * 40, token="synthetic-token", environ={},
                            trusted_workflow_path=".github/workflows/product-validation.yml",
                            trusted_job_name=job["name"]):
                        pass

    def test_same_pr_catalog_rejects_partial_selection_before_output(self):
        with tempfile.TemporaryDirectory(prefix="sdk-campaign-catalog-") as temporary:
            destination = Path(temporary).resolve() / "catalog"
            producer = next(iter(self.envelopes.values()))["receipt"]["producer"]
            first = min(SDK_CAMPAIGN_INSTANCES)
            with self.assertRaisesRegex(ValueError, "all 62 phases"):
                stage_sdk_same_pr_catalog({key: value for key, value in self.sources.items()
                    if key != first}, self.envelopes, self.archives,
                    producer=producer, destination=destination)
            self.assertFalse(destination.exists())

    def test_same_pr_catalog_rejects_changed_selected_artifact_path(self):
        with tempfile.TemporaryDirectory(prefix="sdk-campaign-catalog-") as temporary:
            destination = Path(temporary).resolve() / "catalog"
            producer = next(iter(self.envelopes.values()))["receipt"]["producer"]
            first = min(SDK_CAMPAIGN_INSTANCES)
            sources = dict(self.sources)
            original_writer = dev_catalog.write_signed_product_index

            def mutate_selection(*args, **kwargs):
                sources[first] = IndexEntrySource(sources[first].receipt_bytes, "outputs/other")
                return original_writer(*args, **kwargs)

            with patch.object(dev_catalog, "write_signed_product_index", side_effect=mutate_selection):
                with self.assertRaisesRegex(ValueError, "selection changed"):
                    stage_sdk_same_pr_catalog(sources, self.envelopes, self.archives,
                        producer=producer, destination=destination)
            self.assertFalse(destination.exists())

    def test_completed_state_caller_keeps_original_receipts(self):
        producer = next(iter(self.envelopes.values()))["receipt"]["producer"]
        caller_id = type(next(iter(CALLER_SDK_INSTANCES)))
        converted = {instance: caller_id(instance.product, instance.component, instance.phase, instance.target)
            for instance in SDK_CAMPAIGN_INSTANCES}
        records = {converted[instance]: {"state": "retained", "buildKey": envelope["receipt"]["buildKey"],
            "receiptSha256": envelope["receiptSha256"], "objectSha256": envelope["objectSha256"]}
            for instance, envelope in self.envelopes.items()}
        archives = {converted[instance]: archive for instance, archive in self.archives.items()}
        state = SimpleNamespace(prior_by_instance=records, sources=archives,
            expected_fixed={"versions": {"sdk": "0.8.0"}}, producer=producer)
        with tempfile.TemporaryDirectory(prefix="sdk-campaign-caller-") as temporary:
            destination = Path(temporary).resolve() / "catalog"
            result = stage_completed_sdk_catalog(state, destination)
            self.assertEqual(result["phaseCount"], len(SDK_CAMPAIGN_INSTANCES))
            self.assertGreater(result["objectBytes"], 0)
            self.assertTrue((destination / "product-index.sig").is_file())
            oversized = Path(temporary).resolve() / "oversized"
            with patch.object(catalog_caller.products, "_CATALOG_LIMIT",
                    result["objectBytes"] + 32 * 1024 * 1024 - 1):
                with self.assertRaisesRegex(ValueError, "bounded transport capacity"):
                    stage_completed_sdk_catalog(state, oversized)
            self.assertFalse(oversized.exists())
            incomplete = dict(records)
            incomplete[min(CALLER_SDK_INSTANCES)] = {
                **incomplete[min(CALLER_SDK_INSTANCES)], "state": "build"}
            with self.assertRaisesRegex(ValueError, "unresolved phase"):
                stage_completed_sdk_catalog(SimpleNamespace(prior_by_instance=incomplete,
                    sources=archives, expected_fixed=state.expected_fixed, producer=producer),
                    Path(temporary).resolve() / "rejected")

            with patch.object(catalog_caller.products, "_verified_product_state", return_value=state) as replay:
                stdout = StringIO()
                repository = Path(__file__).resolve().parents[2]
                github_output = Path(temporary).resolve() / "github-output"
                with redirect_stdout(stdout):
                    self.assertEqual(catalog_caller_main([
                        "--plan", str(self.root / "plan.json"),
                        "--discovery-root", str(repository / "build/catalog-fixture-discovery"),
                        "--state-root", str(repository / "build/catalog-fixture-state"),
                        "--repository-root", str(repository),
                        "--destination", str(Path(temporary).resolve() / "from-cli"),
                        "--github-output", str(github_output),
                        "--sdk-original-workflow-sha", "a" * 40,
                    ]), 0)
                self.assertIn('"phaseCount":62', stdout.getvalue())
                self.assertEqual(json.loads(stdout.getvalue()), {
                    key: int(value) if key in {"phaseCount", "objectBytes"} else value
                    for key, value in (row.split("=", 1)
                        for row in github_output.read_text().splitlines())})
                replay.assert_called_once()
                with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
                    catalog_caller_main([
                        "--plan", str(self.root / "plan.json"),
                        "--discovery-root", str(repository / "build/catalog-fixture-discovery"),
                        "--state-root", str(repository / "build/catalog-fixture-state"),
                        "--repository-root", str(repository),
                        "--destination", str(repository / "build/catalog-fixture-state/catalog"),
                        "--sdk-original-workflow-sha", "a" * 40,
                    ])
                replay.assert_called_once()
                with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
                    catalog_caller_main([
                        "--plan", str(self.root / "plan.json"),
                        "--discovery-root", str(repository / "build/catalog-fixture-discovery"),
                        "--state-root", str(repository / "build/catalog-fixture-state"),
                        "--repository-root", str(repository),
                        "--destination", str(Path(temporary).resolve() / "separate"),
                        "--github-output", str(repository / "build/catalog-fixture-state/output"),
                        "--sdk-original-workflow-sha", "a" * 40,
                    ])
                replay.assert_called_once()


    def test_completed_catalog_uses_native_receipts_without_deferred_bodies(self):
        import reuse_qualification as qualification
        from products.inventory import load_canonical_json_bytes
        from products.registry import PhaseInstanceId
        instances = sorted(SDK_CAMPAIGN_INSTANCES)
        deferred = set(instances[:2])
        rows = {PhaseInstanceId(instance.product, instance.component, instance.phase, instance.target): {
            **{name: self.envelopes[instance]["receipt"][name]
               for name in ("product", "component", "phase", "target", "buildKey")},
            "state": "retained", "receiptSha256": self.envelopes[instance]["receiptSha256"],
            "objectSha256": self.envelopes[instance]["objectSha256"]}
            for instance in instances}
        cap = qualification.CompletedFrozenReuse(
            {"expectedResult": {"phases": [rows[PhaseInstanceId(i.product, i.component, i.phase, i.target)] for i in sorted(deferred)]}},
            [self.envelopes[i]["receipt"] for i in sorted(deferred)],
            qualification._COMPLETED_FROZEN, revision="a" * 40)
        archives = {PhaseInstanceId(i.product, i.component, i.phase, i.target): p for i,p in self.archives.items() if i not in deferred}
        producer = {**next(iter(self.envelopes.values()))["receipt"]["producer"],
                    "commit": "c" * 40, "tree": "d" * 40, "runId": 9}
        state = SimpleNamespace(prior_by_instance=rows, sources=archives,
            expected_fixed={"versions": {"sdk": "0.8.0"}}, producer=producer, completed_frozen=cap)
        # Only the external native authentication constructor is a fixture seam.
        # Real capability envelope checks, object checks, signing and index reads follow.
        with tempfile.TemporaryDirectory(prefix="sdk-qualified-catalog-") as temporary:
            root = Path(temporary).resolve()
            writer = catalog_caller.stage_sdk_same_pr_catalog
            writer_module = __import__(writer.__module__, fromlist=["_snapshot_archive"])
            with patch.object(writer_module, "_snapshot_archive",
                    wraps=writer_module._snapshot_archive) as snapshot:
                result = stage_completed_sdk_catalog(state, root / "catalog")
            self.assertEqual(62, result["phaseCount"])
            self.assertEqual(60, snapshot.call_count)
            self.assertEqual(sum(path.stat().st_size for path in archives.values()), result["objectBytes"])
            index, _ = verify_signed_product_index(SignedProductIndex(
                root / "catalog/product-index.json", root / "catalog/product-index.sig"),
                root / "catalog/public-key.pub")
            self.assertEqual(62, len(index["entries"]))
            self.assertEqual(producer, index["producer"])
            for instance in instances:
                original = self.envelopes[instance]
                path = root / "catalog" / object_relative_path(
                    original["receipt"]["buildKey"], original["receiptSha256"])
                self.assertEqual(instance not in deferred, path.exists())
                if instance not in deferred:
                    self.assertEqual(self.archives[instance].read_bytes(), path.read_bytes())
                entry, = [e for e in index["entries"] if e["receiptSha256"] == original["receiptSha256"]]
                self.assertEqual(sha256_bytes(original["receiptBytes"]), entry["receiptSha256"])
                if instance in deferred:
                    self.assertEqual(original["receipt"]["producer"],
                        cap.envelope(rows[PhaseInstanceId(instance.product, instance.component, instance.phase, instance.target)])["receipt"]["producer"])
            # Existing generic catalog layout supports index-only entries. Their
            # absent objects remain absent to ordinary lookup, never synthesized.
            catalog = catalog_caller.products._read_catalog_directory("same-pr", root / "catalog",
                root, None, repository=producer["repository"],
                pull_request=producer["pullRequest"], provenance_root=root / "provenance",
                workflow_run={"run": {"id": producer["runId"], "run_attempt": producer["runAttempt"],
                    "path": producer["workflowPath"]},
                    "testedCommit": {"sha": producer["commit"], "tree": {"sha": producer["tree"]}}})
            self.assertEqual(60, len(catalog.objects))
            self.assertEqual({self.envelopes[i]["receipt"]["buildKey"] for i in instances if i not in deferred},
                             set(catalog.objects))
            before = dict(rows)
            for label, change in (
                ("no-authority", {"completed_frozen": None}),
                ("untyped-authority", {"completed_frozen": SimpleNamespace(envelope=cap.envelope)}),
                ("missing-new-object", {"sources": dict(list(archives.items())[1:])}),
            ):
                with self.subTest(label=label), self.assertRaises((ValueError, FileNotFoundError)):
                    stage_completed_sdk_catalog(SimpleNamespace(**{**vars(state), **change}), root / label)
                self.assertFalse((root / label).exists())
            bad = dict(rows)
            selected = PhaseInstanceId(*(getattr(min(deferred), name) for name in ("product", "component", "phase", "target")))
            bad[selected] = {**bad[selected], "objectSha256": "sha256:" + "f" * 64}
            with self.assertRaisesRegex(ValueError, "proved identity"):
                stage_completed_sdk_catalog(SimpleNamespace(**{**vars(state), "prior_by_instance": bad}),
                                            root / "wrong-qualified")
            self.assertFalse((root / "wrong-qualified").exists())
            self.assertEqual(before, rows)

    def test_catalog_cli_holds_explicit_completed_policy_through_output(self):
        import reuse_qualification as qualification
        from products.inventory import canonical_json_bytes
        instance = min(SDK_CAMPAIGN_INSTANCES)
        original = self.envelopes[instance]
        row = {**{name: original["receipt"][name]
                  for name in ("product", "component", "phase", "target", "buildKey")},
               "receiptSha256": original["receiptSha256"], "objectSha256": original["objectSha256"]}
        cap = qualification.CompletedFrozenReuse({"expectedResult": {"phases": [row]}},
            [original["receipt"]], qualification._COMPLETED_FROZEN, revision="d" * 40)
        with tempfile.TemporaryDirectory(prefix="sdk-catalog-cli-policy-") as temporary:
            root = Path(temporary).resolve()
            plan, policy, output = root / "plan.json", root / "policy.json", root / "github-output"
            plan.write_bytes(b"authenticated current plan fixture")
            policy_value = {"schemaVersion": 1, "kind": "completed-frozen-reuse",
                "consumerCommit": "c" * 40, "verifierPolicySha256": "sha256:" + "a" * 64,
                "artifactId": 71, "artifactSha256": "sha256:" + "e" * 64,
                "runId": 72, "runAttempt": 1, "signerCommit": "b" * 40, "sourceCommit": "a" * 40}
            policy.write_bytes(canonical_json_bytes(policy_value))
            args = ["--plan", str(plan), "--discovery-root", str(root / "discovery"),
                    "--state-root", str(root / "state"), "--repository-root", str(root),
                    "--destination", str(root / "catalog"), "--github-output", str(output),
                    "--sdk-original-workflow-sha", "a" * 40, "--completed-frozen-policy", str(policy)]
            consumer = {"kind": "ci", "producer": {"repository": qualification.REPOSITORY,
                        "pullRequest": 31, "event": "pull_request"}}
            state = SimpleNamespace(completed_frozen=cap)
            def replay(*unused, **options):
                self.assertIs(cap, options["completed_frozen"])
                return state
            result = {"phaseCount": 62, "objectBytes": 1, "indexSha256": "sha256:" + "a" * 64,
                      "publicKeySha256": "sha256:" + "b" * 64}
            with patch.object(catalog_caller.products, "_validate_plan",
                    return_value={"validationCommit": "d" * 40}), \
                 patch.object(catalog_caller.products, "_consumer", return_value=consumer), \
                 patch.object(qualification, "fetch_completed_frozen", return_value=(cap, {})) as fetch, \
                 patch.object(catalog_caller.products, "_verified_product_state", side_effect=replay), \
                 patch.object(catalog_caller, "stage_completed_sdk_catalog", return_value=result), \
                 redirect_stdout(StringIO()):
                self.assertEqual(0, catalog_caller_main(args))
                fetch.assert_called_once()
                self.assertEqual("c" * 40, fetch.call_args.kwargs["consumer_commit"])
                self.assertEqual("d" * 40, fetch.call_args.kwargs["revision"])
                self.assertTrue(output.exists())
                output.unlink()
                def mutate_policy(*unused, **options):
                    policy.write_bytes(b"changed caller policy")
                    return result
                with patch.object(catalog_caller, "stage_completed_sdk_catalog", side_effect=mutate_policy), \
                     redirect_stderr(StringIO()), self.assertRaises(SystemExit):
                    catalog_caller_main(args)
                self.assertFalse(output.exists())
            policy.write_bytes(canonical_json_bytes(policy_value))
            with patch.object(qualification, "fetch_completed_frozen", side_effect=ValueError("bad native proof")), \
                 patch.object(catalog_caller.products, "_validate_plan",
                     return_value={"validationCommit": "d" * 40}), \
                 patch.object(catalog_caller.products, "_verified_product_state") as replay, \
                 redirect_stderr(StringIO()), self.assertRaises(SystemExit):
                catalog_caller_main(args)
            replay.assert_not_called()
            self.assertFalse(output.exists())

    def test_partial_or_cross_paired_selection_fails(self):
        first, second = sorted(SDK_CAMPAIGN_INSTANCES)[:2]
        with self.assertRaisesRegex(ValueError, "every exact SDK phase"):
            verify_sdk_campaign_selection({key: value for key, value in self.sources.items()
                if key != first}, self.envelopes, self.archives, self.stages)
        envelopes = dict(self.envelopes)
        envelopes[first], envelopes[second] = envelopes[second], envelopes[first]
        with self.assertRaisesRegex(ValueError, "wrong phase identity"):
            verify_sdk_campaign_selection(self.sources, envelopes, self.archives, self.stages)

    def test_wrong_object_or_changed_stage_fails(self):
        first = min(SDK_CAMPAIGN_INSTANCES)
        envelopes = dict(self.envelopes)
        envelopes[first] = {**envelopes[first], "objectSha256": "sha256:" + "0" * 64}
        with self.assertRaisesRegex(ValueError, "expected transport identity"):
            verify_sdk_campaign_selection(self.sources, envelopes, self.archives, self.stages)
        file = self.stages[first] / "outputs/fixture/content.bin"
        original = file.read_bytes()
        try:
            file.write_bytes(b"changed")
            with self.assertRaises(ValueError):
                verify_sdk_campaign_selection(self.sources, self.envelopes,
                    self.archives, self.stages)
        finally:
            file.write_bytes(original)

    def test_held_selection_uses_private_exact_stages_and_detects_late_change(self):
        first = min(SDK_CAMPAIGN_INSTANCES)
        with held_sdk_campaign_selection(self.sources, self.envelopes,
                self.archives, self.stages) as (sources, envelopes, stages, receipts):
            self.assertEqual(set(stages), SDK_CAMPAIGN_INSTANCES)
            self.assertEqual(sources[first].receipt_bytes, self.sources[first].receipt_bytes)
            self.assertEqual(envelopes[first], self.envelopes[first])
            self.assertEqual(receipts[first]["productVersion"], "0.8.0")
            self.assertNotEqual(stages[first], self.stages[first])
            self.assertEqual((stages[first] / "outputs/fixture/content.bin").read_bytes(),
                             (self.stages[first] / "outputs/fixture/content.bin").read_bytes())
        with self.assertRaisesRegex(ValueError, "Held SDK campaign selection changed"):
            with held_sdk_campaign_selection(self.sources, self.envelopes,
                    self.archives, self.stages) as (_, _, stages, _):
                (stages[first] / "outputs/fixture/content.bin").write_bytes(b"changed")
        extra = self.stages[first] / "unrelated-file"
        try:
            with self.assertRaisesRegex(ValueError, "Held SDK campaign selection changed"):
                with held_sdk_campaign_selection(self.sources, self.envelopes,
                        self.archives, self.stages):
                    extra.write_bytes(b"late")
        finally:
            extra.unlink(missing_ok=True)
        original_digest = self.envelopes[first]["objectSha256"]
        try:
            with self.assertRaises(ValueError):
                with held_sdk_campaign_selection(self.sources, self.envelopes,
                        self.archives, self.stages):
                    self.envelopes[first]["objectSha256"] = "sha256:" + "0" * 64
        finally:
            self.envelopes[first]["objectSha256"] = original_digest


if __name__ == "__main__":
    unittest.main()
