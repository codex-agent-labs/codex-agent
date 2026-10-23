"""Official SDK original lookup: synthetic API, exact fresh shard bytes."""

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from ci import sdk_campaign_original_locator as locator
from ci import sdk_campaign_original_worker as worker
from ci.sdk_campaign_catalog_producer import FreshSdkOriginalPin
from ci.sdk_campaign_observation import ObservedSdkOriginal
from ci.tests import test_sdk_worker_collection as fixture_module
from ci.tests.product_chain_support import write_receipt
from ci.tests.test_product_resume_capture import archive
from products.inventory import canonical_json_bytes, load_canonical_json_bytes, regular_file_inventory, sha256_bytes
from products.receipt import validate_phase_receipt, write_output_manifest
from products.registry import PhaseInstanceId
from products.restore import PHASE_PLAN_KEYS, finalize_phase_object


class NativeValidationCohortTest(TestCase):
    def test_additive_cohort_preserves_all_originals_and_distinct_keys(self):
        directory = Path(locator.__file__).parent / "tests/data"
        old_raw = (directory / "retained-native-sdk-validations.json").read_bytes()
        self.assertEqual("sha256:524334a1398d55110639fdc42e0a3f61eb7b78ebe207a49cf752540427be5b63",
                         sha256_bytes(old_raw))
        old = load_canonical_json_bytes(old_raw)
        new = load_canonical_json_bytes(
            (directory / "retained-native-sdk-validations-39943202903.json").read_bytes())
        rows = locator.retained_native_validation_records()["originals"]
        self.assertEqual(22, len(old["originals"]))
        self.assertEqual(24, len(rows))
        self.assertEqual([{**row, "producer": old["producer"]} for row in old["originals"]]
                         + [{**row, "producer": new["producer"]} for row in new["originals"]], rows)
        dart = [row for row in rows if (row["component"], row["target"]) == ("dart", "macos-arm64")]
        self.assertEqual(2, len(dart))
        self.assertEqual(2, len({row["buildKey"] for row in dart}))
        self.assertEqual((39943202903, 12512225187, 120429656410),
            (dart[-1]["producer"]["runId"], dart[-1]["artifactId"], dart[-1]["jobId"]))
        windows = [row for row in rows if (row["component"], row["target"]) == ("dart", "windows-x64")]
        self.assertEqual((39943202903, 12514902456, 120429656372),
            (windows[-1]["producer"]["runId"], windows[-1]["artifactId"], windows[-1]["jobId"]))

    def test_cohort_scope_schema_and_duplicate_keys_fail_closed(self):
        directory = Path(locator.__file__).parent / "tests/data"
        old = load_canonical_json_bytes((directory / "retained-native-sdk-validations.json").read_bytes())
        new = load_canonical_json_bytes(
            (directory / "retained-native-sdk-validations-39943202903.json").read_bytes())
        mutations = (
            lambda value: value["producer"].update(pullRequest=32),
            lambda value: value["producer"].update(repository="other/repository"),
            lambda value: value.update(schemaVersion=True),
            lambda value: value["originals"][0].update(unexpected="field"),
            lambda value: value["originals"].append(deepcopy(value["originals"][0])),
            lambda value: value.update(originals=[deepcopy(old["originals"][0])]),
        )
        for number, mutate in enumerate(mutations):
            candidate = deepcopy(new)
            mutate(candidate)
            with self.subTest(mutation=number), patch.object(locator, "read_regular_file_bytes",
                    side_effect=lambda path, **_: canonical_json_bytes(
                        old if path.name == "retained-native-sdk-validations.json" else candidate)):
                with self.assertRaises(ValueError):
                    locator.retained_native_validation_records()


class SdkCampaignOriginalLocatorTest(TestCase):
    def test_native_validation_recovers_exact_originals_without_product_download(self):
        reviewed = locator.retained_native_validation_records()
        consumer = {**reviewed["originals"][0]["producer"], "runId": 40000000000, "runAttempt": 1}
        for row in reviewed["originals"]:
            options = {"component": row["component"], "target": row["target"], "phase": "validation"}
            origin = locator.retained_core_origin(build_key=row["buildKey"], consumer=consumer, **options)
            with self.subTest(component=row["component"], target=row["target"]):
                self.assertEqual(row["producer"], origin["producer"])
                for public, internal in (("artifactId", "artifact_id"), ("jobId", "job_id"),
                        ("receiptSha256", "receipt_sha256"), ("objectSha256", "object_sha256")):
                    self.assertEqual(row[public], origin[internal])
                for change, key in (({}, "sha256:" + "0" * 64), ({"pullRequest": 32}, row["buildKey"]),
                        ({"event": "merge_group"}, row["buildKey"]), ({"runId": True}, row["buildKey"]),
                        ({"runId": row["producer"]["runId"]}, row["buildKey"]),
                        ({"runId": row["producer"]["runId"] - 1}, row["buildKey"]),
                        ({"repository": "other/repository"}, row["buildKey"])):
                    self.assertIsNone(locator.retained_core_origin(build_key=key,
                        consumer={**consumer, **change}, **options))
                with patch.object(locator.products, "_validate_plan", return_value={"event": "pull_request", "remoteBuildAuthorized": True}), \
                        patch.object(locator.products, "_consumer", return_value={"producer": consumer}), \
                        patch.object(locator, "_locate", return_value={name: origin[name] for name in
                            ("artifact_id", "artifact_sha256")}) as observe:
                    def call():
                        return locator.locate_retained_core_binary_upload(self.fixture.plan_path,
                            self.fixture.repository, expected_build_key=row["buildKey"], token="synthetic",
                            environ={}, **options)
                    self.assertEqual(origin, call())
                    self.assertEqual(row["jobId"], observe.call_args.kwargs["expected_job_id"])
                    self.assertEqual(row["buildKey"], observe.call_args.kwargs["expected_build_key"])
                    self.assertEqual({"validation": {"path": origin["workflow_path"], "sha": row["workflowSha"]}},
                                     observe.call_args.kwargs["trusted_workflows_by_phase"])
                    observe.return_value = {"artifact_id": row["artifactId"], "artifact_sha256": "sha256:" + "f" * 64}
                    with self.assertRaisesRegex(ValueError, "reviewed successful original"):
                        call()

    def test_android_metadata_recovers_only_exact_successful_original(self):
        consumer = {**self.fixture.producer, "runId": 40000000000, "runAttempt": 1}
        key = locator.RETAINED_ANDROID_METADATA_KEY
        options = {"phase": "metadata", "component": "sdk-android", "target": "android"}
        origin = locator.retained_core_origin(build_key=key, consumer=consumer, **options)
        self.assertEqual((12098433883, 117374782553), (origin["artifact_id"], origin["job_id"]))
        for changed, other in (({}, "sha256:" + "0" * 64), ({"runId": 39024902373}, key),
                ({"pullRequest": 32}, key), ({"runAttempt": True}, key)):
            self.assertIsNone(locator.retained_core_origin(build_key=other, consumer={**consumer, **changed}, **options))
        with patch.object(locator.products, "_validate_plan", return_value={"event": "pull_request", "remoteBuildAuthorized": True}), \
                patch.object(locator.products, "_consumer", return_value={"producer": consumer}), \
                patch.object(locator, "_locate", return_value={n: origin[n] for n in ("artifact_id", "artifact_sha256")}) as observed:
            actual = locator.locate_retained_core_binary_upload(self.fixture.plan_path, self.fixture.repository,
                expected_build_key=key, token="fixture", environ={}, **options)
            self.assertEqual(origin, actual)
            self.assertEqual(origin["job_id"], observed.call_args.kwargs["expected_job_id"])
            self.assertEqual(key, observed.call_args.kwargs["expected_build_key"])

    def test_retained_metadata_keeps_exact_original_context_and_later_pr(self):
        key = 'sha256:7b8511fe614ab935af4333da9210808083d5f134a89ac013085dff52c0aefc5a'
        consumer = {**self.fixture.producer, "runId": 40000000000, "runAttempt": 1}
        origin = locator.retained_core_origin("metadata", key, consumer)
        self.assertEqual(12068740640, origin["artifact_id"])
        self.assertEqual(117099192243, origin["job_id"])
        self.assertEqual('sha256:575d0fcd155861ad1127b7c7deb01ba0298aaf74f729c4301eb1ac4c90f477e7', origin["receipt_sha256"])
        self.assertEqual({'metadataRequest': '/tmp/core-metadata-inputs-yxs0r4ag/metadata-request.json', 'repositoryRoot': '/home/runner/work/codex-agent/codex-agent'}, origin["context"])
        for target, changed_key, change in (("android", key, {}), ("common", "sha256:" + "0" * 64, {}),
                ("common", key, {"runId": 38937733736}), ("common", key, {"runId": 38937733736 - 1}),
                ("common", key, {"runId": True}), ("common", key, {"runAttempt": False}),
                ("common", key, {"pullRequest": 32}), ("common", key, {"event": "merge_group"}),
                ("common", key, {"workflowPath": "other.yml"}), ("common", key, {"repository": "other/repo"})):
            self.assertIsNone(locator.retained_core_origin("metadata", changed_key,
                {**consumer, **change}, target=target))
        with patch.object(locator.products, "_validate_plan", return_value={"event": "pull_request", "remoteBuildAuthorized": True}), \
                patch.object(locator.products, "_consumer", return_value={"producer": consumer}), \
                patch.object(locator, "_locate", return_value={field: origin[field] for field in
                    ("artifact_id", "artifact_sha256")}) as observe:
            def call():
                return locator.locate_retained_core_binary_upload(self.fixture.plan_path, self.fixture.repository,
                    expected_build_key=key, token="synthetic", environ={}, phase="metadata")
            self.assertEqual(origin, call())
            self.assertEqual(origin["job_id"], observe.call_args.kwargs["expected_job_id"])
            self.assertEqual(key, observe.call_args.kwargs["expected_build_key"])
            self.assertEqual({"metadata": {"path": origin["workflow_path"], "sha": origin["workflow_sha"]}},
                             observe.call_args.kwargs["trusted_workflows_by_phase"])
            observe.return_value = {"artifact_id": origin["artifact_id"], "artifact_sha256": "sha256:" + "f" * 64}
            with self.assertRaisesRegex(ValueError, "reviewed successful original"):
                call()

    def test_retained_android_validation_binds_exact_target_original_and_later_pr(self):
        key = locator.RETAINED_CORE_ANDROID_VALIDATION_KEY
        consumer = {**self.fixture.producer, "runId": 40000000000, "runAttempt": 1}
        origin = locator.retained_core_origin("validation", key, consumer, target="android")
        self.assertEqual(11990927907, origin["artifact_id"])
        for target, changed_key, change in (("jvm", key, {}), ("common", key, {}),
                ("android", "sha256:" + "0" * 64, {}), ("android", key, {"pullRequest": 32}),
                ("android", key, {"event": "merge_group"}), ("android", key, {"runId": 38768220181}),
                ("android", key, {"runId": True}), ("android", key, {"runAttempt": 0})):
            self.assertIsNone(locator.retained_core_origin("validation", changed_key, {**consumer, **change}, target=target))
        with patch.object(locator.products, "_validate_plan", return_value={"event": "pull_request", "remoteBuildAuthorized": True}), \
                patch.object(locator.products, "_consumer", return_value={"producer": consumer}), \
                patch.object(locator, "_locate", return_value={name: origin[name] for name in
                    ("artifact_id", "artifact_sha256")}) as observe:
            result = locator.locate_retained_core_binary_upload(self.fixture.plan_path, self.fixture.repository,
                expected_build_key=key, token="synthetic", environ={}, phase="validation", target="android")
            self.assertEqual(origin, result)
            self.assertEqual(origin["job_id"], observe.call_args.kwargs["expected_job_id"])
            self.assertIn("-validation-android-" + key[7:], observe.call_args.kwargs["name"])
            self.assertEqual({"validation": {"path": origin["workflow_path"], "sha": origin["workflow_sha"]}},
                observe.call_args.kwargs["trusted_workflows_by_phase"])

    def test_successful_core_validation_siblings_keep_exact_original_routes(self):
        consumer = {**self.fixture.producer, "runId": 40000000000, "runAttempt": 1}
        rows = (
            ("ios-arm64", "sha256:cd75408f1678521c7c8a3ec4a2d9d3077b244468b06e1d0277d2b2e280bc4526", 11994444162, 116566324230),
            ("ios-simulator-arm64", "sha256:04c1c231cf4442734cfa544321cd41f3a46951ce66dff3634c6ee3576cbfaf06", 11995665186, 116566324093),
            ("jvm", "sha256:cf5ea06b6743251e3b4b495e961e9c3185829ccafe023c2ac361d0725479d2f6", 11994318412, 116566323763),
            ("linux-arm64", "sha256:1193bd6254ebcfa6f1a5ad1e44128cde4210d094790b69e1c10653fbc0871852", 12000985511, 116614307314),
            ("linux-x64", "sha256:5cc349c57628460f4988674a798c397324a7002c65f84e4035d523aa3779bfd2", 11997978627, 116595906434),
            ("macos-arm64", "sha256:fe2acd38a99d7960b4b584ea1fbe0d94bc72264ae2ce46f6280fa62614c3c98f", 11994962517, 116566323856),
            ("macos-x64", "sha256:5c9b2857e70101c4245577540bcc8e75222d336c321a4fecbd745272d0180524", 11996805810, 116566323760),
            ("node-js", "sha256:05bdd186e96b395ed4cc99d5b6167ab1b3f0e0494e7257f47da528b4644cc2fb", 11995046121, 116566323778),
            ("node-wasm", "sha256:a9366d071b40d9ee2f328943189765cf0ece959453f877b577deaa03391f3b6a", 11993489491, 116566323791),
        )
        for target, key, artifact, job in rows:
            with self.subTest(target=target):
                origin = locator.retained_core_origin("validation", key, consumer, target=target)
                self.assertEqual((artifact, job), (origin["artifact_id"], origin["job_id"]))
                run, workflow = ((38784033203, "b4fbebd49866c0607bceee8fa9882f041ef0f2b0") if target == "linux-x64"
                                 else (38790148727, "844ec467af054a7d785c5023faf54e547d8a7761") if target == "linux-arm64"
                                 else (38776265359, "d1946db206f57cb392d344b1a2110d4438802782"))
                self.assertEqual((run, 1), (origin["producer"]["runId"], origin["producer"]["runAttempt"]))
                self.assertEqual(workflow, origin["workflow_sha"])
                self.assertEqual("product-validation / sdk-core-validation-wave / sdk-core-validation-" + target,
                                 origin["job_name"])
                for changed_key, changes in (("sha256:" + "0" * 64, {}), (key, {"pullRequest": 32}),
                        (key, {"runId": run}), (key, {"event": "merge_group"}),
                        (key, {"repository": "other/repository"}), (key, {"runAttempt": True})):
                    self.assertIsNone(locator.retained_core_origin("validation", changed_key,
                        {**consumer, **changes}, target=target))
                with patch.object(locator.products, "_validate_plan", return_value={"event": "pull_request", "remoteBuildAuthorized": True}), \
                        patch.object(locator.products, "_consumer", return_value={"producer": consumer}), \
                        patch.object(locator, "_locate", return_value={name: origin[name] for name in
                            ("artifact_id", "artifact_sha256")}) as observe:
                    self.assertEqual(origin, locator.locate_retained_core_binary_upload(self.fixture.plan_path,
                        self.fixture.repository, expected_build_key=key, token="synthetic", environ={},
                        phase="validation", target=target))
                    self.assertEqual(job, observe.call_args.kwargs["expected_job_id"])
                    self.assertEqual({"validation": {"path": origin["workflow_path"], "sha": origin["workflow_sha"]}},
                                     observe.call_args.kwargs["trusted_workflows_by_phase"])
        for target in ("windows-x64", "linux-x64", "linux-arm64", "unknown"):
            self.assertIsNone(locator.retained_core_origin("validation", rows[0][1], consumer, target=target))

    def test_retained_package_lookup_binds_exact_original_and_later_consumer(self):
        key = locator.RETAINED_CORE_PACKAGE_KEY
        consumer = {**self.fixture.producer, "runId": 40000000000, "runAttempt": 1}
        origin = locator.retained_core_origin("package", key, consumer)
        self.assertEqual(11964185144, origin["artifact_id"])
        for phase, change in (("binary", {}), ("validation", {}), ("package", {"pullRequest": 32}),
                ("package", {"runId": 38715748096}), ("package", {"runId": True}),
                ("package", {"repository": "other/repository"}), ("package", {"event": "merge_group"})):
            self.assertIsNone(locator.retained_core_origin(phase, key, {**consumer, **change}))
        plan = {"event": "pull_request", "remoteBuildAuthorized": True}
        with patch.object(locator.products, "_validate_plan", return_value=plan), \
                patch.object(locator.products, "_consumer", return_value={"producer": consumer}), \
                patch.object(locator, "_locate", return_value={name: origin[name] for name in
                    ("artifact_id", "artifact_sha256")}) as observe:
            result = locator.locate_retained_core_binary_upload(self.fixture.plan_path, self.fixture.repository,
                expected_build_key=key, token="synthetic-token", environ={}, phase="package")
            self.assertEqual(origin, result)
            self.assertEqual("package", observe.call_args.kwargs["phase"])
            self.assertEqual(origin["job_id"], observe.call_args.kwargs["expected_job_id"])
            self.assertEqual({"package": {"path": origin["workflow_path"], "sha": origin["workflow_sha"]}},
                observe.call_args.kwargs["trusted_workflows_by_phase"])

    def test_retained_android_binary_has_exact_original_and_later_pr_lookup(self):
        key = locator.RETAINED_ANDROID_BINARY_KEY
        consumer = {**self.fixture.producer, 'runId': 40000000000, 'runAttempt': 1}
        options = {'phase': 'binary', 'component': 'sdk-android', 'target': 'android'}
        origin = locator.retained_core_origin('binary', key, consumer, component='sdk-android', target='android')
        self.assertEqual(12079777755, origin['artifact_id'])
        self.assertEqual(117231503731, origin['job_id'])
        for changes in ({'pullRequest': 32}, {'runId': 38977473655}, {'runId': True}, {'event': 'merge_group'}):
            self.assertIsNone(locator.retained_core_origin('binary', key, {**consumer, **changes},
                component='sdk-android', target='android'))
        self.assertIsNone(locator.retained_core_origin('package', key, consumer, component='sdk-android', target='android'))
        self.assertIsNone(locator.retained_core_origin('binary', key, consumer, component='sdk-core', target='android'))
        plan = {'event': 'pull_request', 'remoteBuildAuthorized': True}
        with patch.object(locator.products, '_validate_plan', return_value=plan), \
                patch.object(locator.products, '_consumer', return_value={'producer': consumer}), \
                patch.object(locator, '_locate', return_value={name: origin[name] for name in
                    ('artifact_id', 'artifact_sha256')}) as observe:
            result = locator.locate_retained_core_binary_upload(self.fixture.plan_path, self.fixture.repository,
                expected_build_key=key, token='synthetic-token', environ={}, **options)
            self.assertEqual(origin, result)
            self.assertEqual(origin['job_id'], observe.call_args.kwargs['expected_job_id'])
            self.assertIn('sdk-android-binary-android-', observe.call_args.kwargs['name'])
            observe.return_value = {**observe.return_value, 'artifact_id': 1}
            with self.assertRaisesRegex(ValueError, 'reviewed successful original'):
                locator.locate_retained_core_binary_upload(self.fixture.plan_path, self.fixture.repository,
                    expected_build_key=key, token='synthetic-token', environ={}, **options)

    def test_retained_locator_imports_from_direct_ci_script_path(self):
        import subprocess, sys
        from pathlib import Path
        subprocess.run([sys.executable, '-I', '-B', '-c',
            'import sys; sys.path.insert(0, sys.argv[1]); '
            'import sdk_campaign_original_locator as locator; '
            'assert callable(locator.locate_retained_core_binary_upload)',
            str(Path(__file__).resolve().parents[1])], check=True, capture_output=True)

    def test_retained_android_validation_keeps_exact_original_and_later_consumer(self):
        key = 'sha256:2ff282b398d370be407038bdbf3e4cace0ef024c1c9d2e2f0fca5ba20a228637'
        consumer = {**self.fixture.producer, 'runId': 40000000000, 'runAttempt': 1}
        selected = lambda value, candidate: locator.retained_core_origin(
            'validation', value, candidate, component='sdk-android', target='android')
        origin = selected(key, consumer)
        self.assertEqual((12096069461, 117360148445), (origin['artifact_id'], origin['job_id']))
        self.assertEqual('5dc62a5b0ac0e8af4e647e6311f0dd480c89fbe2', origin['workflow_sha'])
        self.assertIsNone(selected('sha256:' + '0' * 64, consumer))
        for change in ({'pullRequest': 32}, {'runId': 39019855381}, {'runAttempt': True}, {'event': 'merge_group'}):
            self.assertIsNone(selected(key, {**consumer, **change}))

    def test_retained_core_lookup_binds_election_original_and_lifetime(self):
        key = "sha256:296617d18df79576fe74240e0668ba2541f297aa84fb37c3c1f6fde0c0cfbb97"
        consumer = {**self.fixture.producer, "runId": 40000000000, "runAttempt": 1}
        origin = locator.retained_core_binary_origin(key, consumer)
        self.assertEqual(11951616809, origin["artifact_id"])
        for change in ({"repository": "other/repository"}, {"workflowPath": "other.yml"},
                       {"pullRequest": 32}, {"event": "merge_group"}, {"runId": True},
                       {"runAttempt": 0}, {"runId": 38687858579}, {"runId": 38687858578}):
            self.assertIsNone(locator.retained_core_binary_origin(key, {**consumer, **change}))
        self.assertIsNone(locator.retained_core_binary_origin("sha256:" + "0" * 64, consumer))
        plan = {"event": "pull_request", "remoteBuildAuthorized": True}
        path = self.fixture.plan_path
        before = path.read_bytes()
        def call():
            return locator.locate_retained_core_binary_upload(path, self.fixture.repository,
                expected_build_key=key, token="synthetic-token", environ={})
        with patch.object(locator.products, "_validate_plan", return_value=plan), \
                patch.object(locator.products, "_consumer", return_value={"producer": consumer}), \
                patch.object(locator, "_locate", return_value={field: origin[field] for field in
                    ("artifact_id", "artifact_sha256")}) as observe:
            self.assertEqual(origin, call())
            self.assertEqual(origin["job_id"], observe.call_args.kwargs["expected_job_id"])
            self.assertEqual(key, observe.call_args.kwargs["expected_build_key"])
            self.assertEqual({"binary": {"path": origin["workflow_path"], "sha": origin["workflow_sha"]}},
                             observe.call_args.kwargs["trusted_workflows_by_phase"])
            observe.return_value = {"artifact_id": 999, "artifact_sha256": origin["artifact_sha256"]}
            with self.assertRaisesRegex(ValueError, "reviewed successful original"): call()
            observe.return_value = {field: origin[field] for field in ("artifact_id", "artifact_sha256")}
            for mutation in (lambda *a, **k: path.write_bytes(b"changed"),
                             lambda producer, **k: producer.update(tree="f" * 40)):
                def changed(*args, **kwargs):
                    mutation(*args, **kwargs)
                    return observe.return_value
                observe.side_effect = changed
                with self.assertRaisesRegex(ValueError, "changed during lookup"): call()
                path.write_bytes(before)
            observe.reset_mock(side_effect=True)
            plan["remoteBuildAuthorized"] = False
            with self.assertRaisesRegex(ValueError, "authorized"): call()
            observe.assert_not_called()

    def setUp(self):
        self.fixture = fixture_module.SdkWorkerCollectionTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.original_names = self.fixture.names
        from ci.tests.test_runtime_reference_transport import RangeOpener
        self.range_opener = RangeOpener({})
        self.enterContext(patch('runtime_reference_archive.urllib.request.build_opener', return_value=self.range_opener))

    def selected(self, *, core=False, android_phase=None):
        if core or android_phase is not None:
            instance = (PhaseInstanceId("sdk", "sdk-core", "package", "common") if core else
                PhaseInstanceId("sdk", "sdk-android", android_phase, "android"))
            base = self.fixture.repository / ("core-original" if core else f"android-{android_phase}-original")
            stage = base / "stage"
            (stage / "outputs").mkdir(parents=True)
            (stage / "outputs/package").write_bytes(b"exact Core package")
            manifest = write_output_manifest(stage, "sdk", instance.component, instance.phase, instance.target, "0.3.0",
                {"package": "outputs"})
            receipt = write_receipt(base / "fixture-receipt.json", product="sdk", component=instance.component,
                phase=instance.phase, target=instance.target, outputs=manifest["outputs"], upstream=[],
                version="0.3.0", version_identity="0.3.0",
                context={"producer": self.fixture.producer})
            ready = {name: receipt[name] for name in PHASE_PLAN_KEYS}
            shard = base / "shard"
            descriptor = finalize_phase_object(stage_root=stage, phase_plan=ready,
                producer=self.fixture.producer, product_version="0.3.0",
                trust_domain="development", destination=shard)
            files = {"shard/" + row["relativePath"]: (shard / row["relativePath"]).read_bytes()
                for row in regular_file_inventory(shard)}
            self.fixture.names = lambda selected, key: locator.fresh_sdk_worker_route(
                selected, descriptor["receipt"])
        else:
            self.fixture.names = self.original_names
            instance, ready, shard, descriptor, files = self.fixture.shard("package")
        record = {"product": instance.product, "component": instance.component,
            "phase": instance.phase, "target": instance.target,
            "buildKey": ready["buildKey"], "receiptSha256": descriptor["receiptSha256"],
            "objectSha256": descriptor["objectSha256"], "state": "retained",
            "source": None, "transportSource": None, "misses": []}
        original = ObservedSdkOriginal(descriptor["receiptBytes"], canonical_json_bytes(record),
            shard / descriptor["objectPath"], shard.parent / "stage")
        raw = archive(files)
        self.range_opener.archives[901] = raw
        return instance, ready, original, raw

    def locate(self, instance, original, digest=None, environ=None, workflow_path=None, job_name=None):
        return locator.locate_fresh_sdk_original_upload(instance, original,
            expected_receipt_sha256=digest or sha256_bytes(original.receipt_bytes),
            trusted_workflow_sha=fixture_module.PIN, token="synthetic-token",
            environ={} if environ is None else environ,
            trusted_workflow_path=workflow_path, trusted_job_name=job_name)

    def child_reference(self, query, workflow_path):
        original = query.side_effect
        def api(url, token):
            result = original(url, token)
            if url.endswith(f"/attempts/{self.fixture.producer['runAttempt']}"):
                return {**result, "referenced_workflows": [*result["referenced_workflows"], {
                    "path": f"{self.fixture.producer['repository']}/{workflow_path}@{fixture_module.PIN}",
                    "sha": fixture_module.PIN,
                }]}
            return result
        query.side_effect = api

    def test_fresh_pin_is_derived_from_official_worker_not_observed_state(self):
        for family in ("javascript", "core", "android"):
            with self.subTest(family=family):
                instance, ready, original, raw = self.selected(
                    core=family == "core",
                    android_phase="package" if family == "android" else None)
                job, _ = locator.fresh_sdk_worker_route(instance,
                    validate_phase_receipt(load_canonical_json_bytes(original.receipt_bytes)))
                child = ".github/workflows/sdk-android-package-validation.yml"
                arguments = dict(producer=self.fixture.producer, expected_build_key=ready["buildKey"],
                    expected_product_version="0.3.0", trusted_workflow_sha=fixture_module.PIN,
                    trusted_workflow_path=child if family == "android" else ".github/workflows/product-validation.yml",
                    trusted_job_name=job, token="synthetic-token", environ={})
                with self.fixture.official_api({instance: ready}, {instance: raw}) as (query, _, download):
                    if family == "android":
                        self.child_reference(query, child)
                    pin = locator.discover_fresh_sdk_original_pin(instance, **arguments)
                    self.assertEqual(sha256_bytes(original.receipt_bytes), pin["receipt_sha256"])
                    self.assertEqual(sha256_bytes(raw), pin["artifact_sha256"])
                    self.assertEqual(901, pin["artifact_id"])
                    self.assertEqual(job, pin["job_name"])
                    self.assertIsInstance(FreshSdkOriginalPin(**pin), FreshSdkOriginalPin)
                    download.assert_not_called()
                    with self.assertRaisesRegex(ValueError, "independent phase identity"):
                        locator.discover_fresh_sdk_original_pin(
                            instance, **{**arguments, "expected_product_version": "0.9.0"})
                    self.assertEqual(0, download.call_count)
                    with self.assertRaisesRegex(ValueError, "missing or ambiguous"):
                        locator.discover_fresh_sdk_original_pin(
                            instance, **{**arguments, "expected_build_key": "sha256:" + "0" * 64})
                    with self.assertRaisesRegex(ValueError, "caller-pinned workflow"):
                        locator.discover_fresh_sdk_original_pin(
                            instance, **{**arguments, "trusted_workflow_sha": "f" * 40})
                    with self.assertRaisesRegex(ValueError, "caller-pinned workflow"):
                        locator.discover_fresh_sdk_original_pin(
                            instance, **{**arguments, "trusted_workflow_path": ".github/workflows/other.yml"})
                    self.assertEqual(0, download.call_count)
                with patch.object(locator.products, "api_json") as api, \
                     self.assertRaisesRegex(ValueError, "independent version, token and workflow route"):
                    locator.discover_fresh_sdk_original_pin(instance,
                        **{**arguments, "trusted_job_name": ""})
                api.assert_not_called()
                with patch.dict(locator.os.environ, {"CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY": ""}), \
                     patch.object(locator.products, "api_json") as api, \
                     self.assertRaisesRegex(ValueError, "signing-secret"):
                    locator.discover_fresh_sdk_original_pin(instance, **arguments)
                api.assert_not_called()

    def test_core_and_noncore_official_locator_feed_exact_worker_verifier(self):
        for core in (True, False):
            with self.subTest(core=core):
                instance, ready, original, raw = self.selected(core=core)
                expected_job, expected_name = locator.fresh_sdk_worker_route(
                    instance, validate_phase_receipt(load_canonical_json_bytes(original.receipt_bytes)))
                self.assertEqual("product-validation / sdk-core-package-wave / sdk-core-package-common" if core
                                 else "product-validation / sdk-javascript-package-node", expected_job)
                self.assertTrue(expected_name.startswith("codex-agent-sdk-worker-"))
                with self.fixture.official_api({instance: ready}, {instance: raw}) as (_, _, download):
                    pin = self.locate(instance, original)
                    self.assertEqual({"artifact_id": 901, "artifact_sha256": sha256_bytes(raw)}, pin)
                    self.assertFalse(download.called)
                    with worker.held_fresh_sdk_worker_upload(instance, original,
                            canonical_json_bytes({"captureProducer": self.fixture.producer}),
                            expected_receipt_sha256=sha256_bytes(original.receipt_bytes),
                            artifact_id=pin["artifact_id"], artifact_sha256=pin["artifact_sha256"],
                            trusted_workflow_sha=fixture_module.PIN, token="synthetic-token", environ={}) as (evidence, _):
                        self.assertEqual(901, evidence["artifact"]["id"])
                    download.assert_called_once()

    def test_independent_receipt_digest_and_reused_state_reject_before_api(self):
        instance, _, original, _ = self.selected()
        reused = replace(original, replay_record_canonical=canonical_json_bytes({
            **load_canonical_json_bytes(original.replay_record_canonical),
            "state": "reused", "source": "same-pr", "transportSource": {"kind": "same-pr"}}))
        with patch.object(locator.products, "api_json") as api, self.assertRaisesRegex(ValueError, "independent"):
            self.locate(instance, original, digest="sha256:" + "0" * 64)
        api.assert_not_called()
        with patch.object(locator.products, "api_json") as api, self.assertRaisesRegex(ValueError, "retained"):
            self.locate(instance, reused)
        api.assert_not_called()

    def test_ambiguous_listing_and_detail_mismatch_reject(self):
        instance, ready, original, raw = self.selected()
        with self.fixture.official_api({instance: ready}, {instance: raw}) as (_, listing, download):
            previous = listing.side_effect
            listing.side_effect = lambda url, field, token: (
                previous(url, field, token) * 2 if field == "artifacts" else previous(url, field, token))
            with self.assertRaisesRegex(ValueError, "ambiguous"):
                self.locate(instance, original)
            download.assert_not_called()
        with self.fixture.official_api({instance: ready}, {instance: raw}) as (query, _, download):
            previous = query.side_effect
            def wrong_detail(url, token):
                value = previous(url, token)
                return {**value, "digest": "sha256:" + "0" * 64} if "/actions/artifacts/" in url else value
            query.side_effect = wrong_detail
            with self.assertRaisesRegex(ValueError, "differs"):
                self.locate(instance, original)
            download.assert_not_called()

    def test_four_android_original_routes_match_worker_uploads(self):
        producer = self.fixture.producer
        for phase in ("binary", "package", "validation", "metadata"):
            with self.subTest(phase=phase):
                instance, _, original, raw = self.selected(android_phase=phase)
                receipt = validate_phase_receipt(load_canonical_json_bytes(original.receipt_bytes))
                job, name = locator.fresh_sdk_worker_route(instance, receipt)
                self.assertEqual(
                    f"product-validation / sdk-android-{phase}-result / sdk-android-{phase}-android", job)
                self.assertEqual(f"codex-agent-sdk-worker-sdk-android-{phase}-android-"
                    f"{receipt['buildKey'].removeprefix('sha256:')}-{producer['tree']}-attempt-{producer['runAttempt']}", name)
                child = (".github/workflows/sdk-android-validation.yml" if phase == "validation" else
                         f".github/workflows/sdk-android-{phase}-validation.yml")
                with self.fixture.official_api({instance: receipt}, {instance: raw}) as (query, _, download):
                    self.child_reference(query, child)
                    pin = self.locate(instance, original, workflow_path=child, job_name=job)
                    self.assertEqual({"artifact_id": 901, "artifact_sha256": sha256_bytes(raw)}, pin)
                    download.assert_not_called()
                    with worker.held_fresh_sdk_worker_upload(instance, original,
                            canonical_json_bytes({"captureProducer": producer}),
                            expected_receipt_sha256=sha256_bytes(original.receipt_bytes),
                            artifact_id=pin["artifact_id"], artifact_sha256=pin["artifact_sha256"],
                            trusted_workflow_sha=fixture_module.PIN, token="synthetic-token", environ={},
                            trusted_workflow_path=child, trusted_job_name=job) as (evidence, _):
                        self.assertEqual(901, evidence["artifact"]["id"])
                    download.assert_called_once()
                if phase == "package":
                    with self.fixture.official_api({instance: receipt}, {instance: raw}) as (query, _, download):
                        self.child_reference(query, child)
                        with self.assertRaises(ValueError):
                            locator.discover_fresh_sdk_original_pin(instance,
                                producer=producer, expected_build_key=receipt["buildKey"],
                                expected_product_version=receipt["productVersion"],
                                trusted_workflow_sha=fixture_module.PIN,
                                trusted_workflow_path=child,
                                trusted_job_name="product-validation / sdk-sdk-android-package-android",
                                token="synthetic-token", environ={})
                        download.assert_not_called()

    def test_invalid_android_route_and_signing_context_reject_before_api(self):
        instance, _, original, _ = self.selected()
        android = PhaseInstanceId("sdk", "sdk-android", "package", "desktop")
        with self.assertRaisesRegex(ValueError, "one exact worker phase"):
            locator.fresh_sdk_worker_route(android, {"producer": self.fixture.producer})
        with patch.object(locator.products, "api_json") as api, self.assertRaisesRegex(ValueError, "signing-secret"):
            self.locate(instance, original, environ={"CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY": ""})
        api.assert_not_called()
