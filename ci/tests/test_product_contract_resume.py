"""Real local K4-to-JVM planning with synthetic products, not Runtime execution."""

from contextlib import ExitStack, chdir
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from ci.products.contract_attestation import build_contract_attestation, capture_contract_execution_closure
from ci.products.inventory import (
    load_canonical_json, publish_regular_tree as actual_publish_regular_tree,
    regular_file_inventory, sha256_file, write_canonical_json,
)
from ci.products.plan import plan_phase
from ci.products.selection import phase_git_inventory
from ci.products.signatures import generate_development_key, sign_manifest
from ci.tests.test_contract_execution_closure import execution_closure_fixture
from ci.tests import test_product_reuse_adapter as fixture


adapter = fixture.product_reuse
JVM = adapter.PhaseInstanceId("runtime", "jvm", "binary", "jvm")


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required")
class ContractProductResumeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temporary = tempfile.TemporaryDirectory(prefix="contract-products-resume-")
        cls.addClassCleanup(temporary.cleanup)
        cls.root = Path(temporary.name).resolve()
        helper = fixture.ProductReuseAdapterTest()
        helper.root = cls.root
        cls.repository, _, _ = helper.contract_repository()
        private, public, development = generate_development_key(cls.root / "signing")
        signing = {**development, "trustDomain": "release", "keyId": "fixture-release"}
        keys = cls.repository / "gradle/release/keys"
        keys.mkdir(parents=True)
        shutil.copyfile(public, keys / "fixture-release.pub")
        keyring = cls.repository / "gradle/release/product-signing-keys.json"
        write_canonical_json(keyring, {
            "schemaVersion": 1, "algorithm": signing["algorithm"], "namespace": signing["namespace"],
            "trustDomain": "release", "activeKey": {
                "keyId": signing["keyId"], "fingerprint": signing["fingerprint"],
            }, "retiredKeys": [],
        })
        def git(*arguments):
            return subprocess.run(["git", *arguments], cwd=cls.repository, check=True,
                                  capture_output=True, text=True).stdout.strip()
        git("add", "gradle/release")
        git("commit", "-qm", "synthetic public release policy")
        cls.commit, tree = git("rev-parse", "HEAD"), git("rev-parse", "HEAD^{tree}")
        cls.plan = {**fixture.impact_plan(changed=["codex-agent-runtime-desktop/src/jvmMain/Fixture.kt"]),
                    "headCommit": cls.commit, "validationCommit": cls.commit, "validationTree": tree}
        cls.plan_path = cls.repository / "impact-plan.json"
        write_canonical_json(cls.plan_path, cls.plan)
        cls.environment = {"GITHUB_RUN_ID": "7", "GITHUB_RUN_ATTEMPT": "2"}
        cls.producer = adapter._consumer(cls.plan, cls.environment)["producer"]

        def original_plan(instance, **arguments):
            outer = adapter.PhaseInstanceId(instance.product, instance.component, instance.phase, instance.target)
            authorities, unavailable = adapter._authorities(cls.repository, cls.commit, (outer,))
            if authorities is None:
                raise AssertionError(unavailable)
            authority = authorities[0]
            arguments.update(inventory=phase_git_inventory(cls.repository, cls.commit, instance), versions=fixture.VERSIONS,
                             toolchain_profile_digest=authority["toolchainProfileDigest"],
                             flags_digest=authority["flagsDigest"], output_schema_version=authority["outputSchemaVersion"])
            return plan_phase(instance, **arguments)

        cls.original = cls.repository / "build/original-contract"
        payload, cls.receipts, raw = execution_closure_fixture(
            cls.original, producer=cls.producer, plan_factory=original_plan)
        closure = cls.repository / "build/original-closure"
        capture_contract_execution_closure(payload, cls.receipts, raw, closure)
        cls.handoff = cls.repository / "build/release-handoff"
        build_contract_attestation(payload, cls.receipts["metadata"], signing, private, public, cls.handoff,
                                   execution_closure=closure, keyring=keyring, keys_directory=keys,
                                   complete_handoff=True)

        def saved_unavailable_catalog(_plan, destination, *_args):
            producer = cls.producer
            # The signed original exists, but its object is unavailable: normal
            # lookup must miss and elect the actual Contract build sequence.
            entry = fixture.ProductReuseAdapterTest.product_index_entry({
                "receipt": load_canonical_json(cls.receipts["binary"]),
                "receiptSha256": sha256_file(cls.receipts["binary"]),
            })
            index = {
                "schemaVersion": 1, "repository": producer["repository"],
                "context": {"kind": "pull-request", **{field: producer[field] for field in
                            ("pullRequest", "commit", "tree", "runId", "runAttempt")}},
                "entries": [entry], "trustDomain": "development", "signing": development, "producer": producer,
            }
            manifest = destination / "catalog/product-index.json"
            write_canonical_json(manifest, index)
            signature = sign_manifest(manifest, private, development)
            retained_key = manifest.parent / "public-key.pub"
            shutil.copyfile(public, retained_key)
            request = {
                "manifest": manifest.relative_to(destination).as_posix(),
                "signature": signature.relative_to(destination).as_posix(),
                "publicKey": retained_key.relative_to(destination).as_posix(),
                "keyring": None, "keysDirectory": None, "contractAttestation": None,
                "contractAttestationSignature": None, "contractPublicKey": None,
                "objects": [{"buildKey": entry["buildKey"], "objectPath": None}],
            }
            return [adapter.Catalog("same-pr", index, sha256_file(manifest), request, {})]

        cls.discovery = cls.repository / "build/product-reuse"
        with cls.control_seams(), mock.patch.object(adapter, "_discover_catalogs", side_effect=saved_unavailable_catalog):
            adapter.discover(cls.plan_path, cls.discovery, cls.root / "discovery-output",
                             repository_root=cls.repository, environ=cls.environment)
            state = cls.discovery
            for phase in ("binary", "package", "validation", "metadata"):
                elected = load_canonical_json(state / f"phase-plans/contract-contract-{phase}-common.json")
                shard = cls.repository / f"build/original-shards/{phase}"
                fixture.finalize_phase_object(
                    stage_root=cls.original / f"{phase}-stage", phase_plan=elected,
                    producer=cls.producer, product_version="0.2.0", trust_domain="development", destination=shard)
                descriptor = adapter.verify_phase_shard(shard, adapter.PhaseInstanceId("contract", "contract", phase, "common"))
                if descriptor["receiptBytes"] != cls.receipts[phase].read_bytes():
                    raise AssertionError("Original fixture receipt differs from real elected phase plan")
                next_state = cls.repository / f"build/contract-after-{phase}"
                result = adapter.advance_contract(
                    cls.plan_path, cls.discovery, None if state == cls.discovery else state, [shard],
                    next_state, cls.root / f"contract-{phase}-output",
                    repository_root=cls.repository, environ=cls.environment)
                state = next_state
            if result["fullReuse"] is not True:
                raise AssertionError("Actual four-phase Contract continuation did not complete")
        cls.state = state
        cls.original_bytes = {phase: path.read_bytes() for phase, path in cls.receipts.items()}
        cls.immutable = {path: regular_file_inventory(path, allow_empty=True)
                         for path in (cls.original, cls.discovery, cls.state, cls.handoff)}

    @classmethod
    def control_seams(cls):
        # Substitute only impact validation/selection. All inventories, authorities and plans are real.
        stack = ExitStack()
        stack.enter_context(mock.patch.object(adapter, "_validate_plan", return_value=cls.plan))
        stack.enter_context(mock.patch.object(adapter, "_requested", return_value=(JVM,)))
        return stack

    def setUp(self):
        self.scratch = Path(tempfile.mkdtemp(prefix="resume-case-", dir=self.repository))
        self.addCleanup(shutil.rmtree, self.scratch)

    def tearDown(self):
        for path, inventory in self.immutable.items():
            self.assertEqual(inventory, regular_file_inventory(path, allow_empty=True), str(path))

    def resume(self, *, handoff=None, environ=None, destination=None, routing_output=False):
        destination = self.scratch / "resumed" if destination is None else destination
        with self.control_seams():
            adapter.resume_products(self.plan_path, self.discovery, self.state,
                                    self.handoff if handoff is None else handoff, destination,
                                    self.scratch / "github-output", repository_root=self.repository,
                                    environ=self.environment if environ is None else environ,
                                    routing_output=routing_output, sdk_original_workflow_sha="c" * 40)
        return destination

    def completed_contract_fixture(self, *, incremental=False):
        """Synthetic native qualification over the real signed fixture and original objects."""
        import reuse_qualification as qualification
        from products.inventory import canonical_json_bytes, sha256_bytes
        from products.restore import object_relative_path
        contract = adapter.PhaseInstanceId("contract", "contract", "metadata", "common")
        records, _ = adapter._completed_contract_objects(self.plan, self.state, self.state, self.environment)
        authorities, _ = adapter._authorities(self.repository, self.commit, adapter._dependency_closure((contract,)))
        request = adapter._wave_request(self.plan, self.repository, self.repository / "build/product-reuse",
            (contract,), fixture.VERSIONS, authorities, [], None)
        request["availableObjects"] = records
        result = adapter._plan_with_sdk_tooling({**request, "artifactRoot": str(self.state)}, None)
        receipts = [load_canonical_json(self.receipts[phase]) for phase in ("binary", "package", "validation", "metadata")]
        files = []
        for receipt in receipts:
            prefix = f"inputs/predecessors/contract-contract-{receipt['phase']}-common/"
            raw = canonical_json_bytes(receipt)
            files.append({"relativePath": prefix + "phase-receipt.json", "bytes": len(raw), "sha256": sha256_bytes(raw)})
            files.extend({**row, "relativePath": prefix + "stage/" + row["relativePath"]}
                for row in regular_file_inventory(self.original / (receipt['phase'] + '-stage')))
        first = records[0]
        files.append({"relativePath": "shard/" + object_relative_path(first['buildKey'], first['receiptSha256']),
            "bytes": (self.state / first['objectPath']).stat().st_size, "sha256": first['objectSha256']})
        originals = [{"receipt": receipts[0], "receiptSha256": first['receiptSha256'],
            "objectSha256": first['objectSha256'], "identity": {"locator": {
                "artifact": {"id": 71, "digest": first['objectSha256']}}}, "originalFiles": files}]
        sdk_files = []
        for row in regular_file_inventory(self.handoff):
            name = row['relativePath']
            prefix = ('contractPayload' if name.endswith('.zip') and '/' not in name else
                      'contractPublicKey' if name == 'public-key.pub' else
                      'contractAttestationSignature' if name.endswith('.sig') else 'contractAttestation')
            sdk_files.append({**row, "relativePath": f"sdk-inputs/inputs/{prefix}/{name}"})
        sdk_files.extend({"relativePath": name, "bytes": 2, "sha256": sha256_bytes(b'{}')}
            for name in ('runtime-capture/plan/impact-plan.json', 'runtime-capture/capture-transport.json'))
        from products.contract_projection import verify_contract_component_projection
        from products.plan import plan_phase as native_plan
        from products.selection import phase_git_inventory as native_inventory
        from products.receipt import validate_phase_receipt
        projection = verify_contract_component_projection(self.original / 'metadata-stage', self.receipts['metadata'],
            self.handoff / 'codex-agent-contract-0.2.0.attestation.json',
            self.handoff / 'codex-agent-contract-0.2.0.attestation.sig', self.handoff / 'public-key.pub',
            expected_trust_domain='release', expected_contract_version='0.2.0', required_components=('jvm',),
            keyring=self.repository / 'gradle/release/product-signing-keys.json',
            keys_directory=self.repository / 'gradle/release/keys')
        runtime_authorities, _ = adapter._authorities(self.repository, self.commit, (JVM,))
        authority = runtime_authorities[0]
        runtime_plan = native_plan(JVM, inventory=native_inventory(self.repository, self.commit, JVM),
            versions=fixture.VERSIONS, toolchain_profile_digest=authority['toolchainProfileDigest'],
            flags_digest=authority['flagsDigest'], output_schema_version=authority['outputSchemaVersion'],
            upstream_receipts=[load_canonical_json(self.receipts['metadata'])], contract_projection=projection)
        receipts.append(validate_phase_receipt({**receipts[0], **runtime_plan,
            'productVersion': fixture.VERSIONS['runtime-release']}))
        sdk = {"spec": {}, "proof": {"sdkInputs": {"locator": {}, "files": sorted(sdk_files, key=lambda r: r['relativePath'])}}}
        if incremental:
            release = self.scratch / 'incremental-release'
            adapter.prepare_contract_release_controls(self.handoff, release)
            sdk['extension'] = {'spec': {'stateRoot': 'product-resume-state', 'completedPhases': []},
                'proof': {'controls': {'product-resume-state/reuse-wave-request.json': request},
                    'contractFiles': {row['relativePath']: (release / row['relativePath']).read_text()
                                      for row in regular_file_inventory(release)}}}
        cap = qualification.CompletedFrozenReuse({"request": request, "expectedResult": result}, receipts,
            qualification._COMPLETED_FROZEN, revision=self.commit, originals=originals,
            sdk=sdk,
            body_cache=self.scratch / 'body-cache')
        discovery = self.scratch / 'native-discovery'
        write_canonical_json(discovery / 'contract-reuse-request.json', request)
        write_canonical_json(discovery / 'contract-reuse-result.json', result)
        write_canonical_json(discovery / 'producer.json', self.producer)
        return cap, discovery

    def test_native_discovery_and_capture_resume_without_contract_body_or_forwarding_jobs(self):
        from contextlib import contextmanager, redirect_stderr
        from functools import partial
        import io
        import zipfile
        from copy import deepcopy
        from products.inventory import canonical_json_bytes, sha256_bytes
        cap, original = self.completed_contract_fixture(incremental=True)
        discovery = self.scratch / 'seeded'
        request = load_canonical_json(original / 'contract-reuse-request.json')
        request['availableObjects'] = []
        wave_request = adapter._wave_request
        def original_location(*args, **kwargs):
            # CI uses this fixed transport tag; the test keeps the original fixture immutable.
            return {**wave_request(*args, **kwargs), 'artifactRoot': str(self.repository / 'build/product-reuse')}
        with self.control_seams(), \
                mock.patch.object(adapter, '_discover_catalogs', return_value=[]), \
                mock.patch.object(adapter, 'verify_object', side_effect=AssertionError('Contract body opened')), \
                mock.patch.object(adapter, 'advance_contract', side_effect=AssertionError('Contract continuation ran')):
            with mock.patch.object(adapter, '_wave_request', side_effect=original_location):
                result = adapter.discover(self.plan_path, discovery, self.scratch / 'discover-output',
                    repository_root=self.repository, environ=self.environment, completed_frozen=cap)
            self.assertEqual('native-contract-complete', result['reason'])
            self.assertFalse(result['fullReuse'])  # The genuinely missing Runtime phase still must run.
            self.assertIn('native_contract_complete=true', (self.scratch / 'discover-output').read_text())
            tooling = discovery / 'tooling-discovery/capture/transport/original-upload.zip'
            tooling.parent.mkdir(parents=True)
            tooling.write_bytes(b'unneeded duplicate tooling transport')
            handoff = self.scratch / 'published-discovery'
            adapter._publish_discovery_handoff(discovery, handoff)
            self.assertTrue(tooling.is_file())
            self.assertFalse((handoff / 'tooling-discovery').exists())
            discovery = handoff
            files = regular_file_inventory(discovery)
            self.assertFalse(any(row['relativePath'].endswith('.zip') for row in files))
            packed = io.BytesIO()
            with zipfile.ZipFile(packed, 'w') as archive:
                archive.writestr('impact-plan.json', self.plan_path.read_bytes())
                for row in files:
                    archive.writestr('product-reuse/' + row['relativePath'], (discovery / row['relativePath']).read_bytes())
            raw = packed.getvalue()
            artifact = {'id': 77, 'digest': sha256_bytes(raw), 'size_in_bytes': len(raw)}
            captured = self.scratch / 'native-inputs'
            resumed = self.scratch / 'native-direct-resume'
            @contextmanager
            def native_authority(arguments):
                self.assertEqual(self.plan_path, arguments['plan'])
                yield {'completed_frozen': cap}
            argv = ['resume-products', '--runtime-matrix',
                '--native-contract-plan', str(self.plan_path), '--native-contract-plan-artifact-id', '77',
                '--native-contract-plan-artifact-sha256', artifact['digest'],
                '--completed-frozen-policy', str(self.scratch / 'synthetic-native-policy.json'),
                '--plan', str(captured / 'plan/impact-plan.json'),
                '--discovery-root', str(captured / 'plan/product-reuse'), '--state-root', str(captured / 'state'),
                '--contract-handoff', str(captured / 'release/contract-input'), '--destination', str(resumed),
                '--github-output', str(self.scratch / 'native-output'), '--sdk-original-workflow-sha', 'c' * 40]
            with mock.patch.object(adapter, '_observe_ci_producer_jobs', return_value=[{'run': {}}]) as observe, \
                    mock.patch.object(adapter, '_download_contract_ci_upload', return_value=(artifact, raw)) as download, \
                    mock.patch.object(adapter, '_require_artifact_job_window'), \
                    mock.patch('reuse_qualification.completed_frozen_options', side_effect=native_authority) as authority, \
                    mock.patch.object(adapter, 'capture_product_resume_inputs', side_effect=partial(
                        adapter.capture_product_resume_inputs, repository_root=self.repository, environ=self.environment)) as capture, \
                    mock.patch.object(adapter, 'resume_products', side_effect=partial(
                        adapter.resume_products, repository_root=self.repository, environ=self.environment)) as resume, \
                    mock.patch('sdk_ios_binary_recovery.capture_completed_ios_binary', return_value=[]):
                self.assertEqual(0, adapter.main(argv))
                self.assertEqual({'plan': 'product-validation / plan'}, observe.call_args.kwargs['jobs_by_phase'])
                download.assert_called_once()
                self.assertIs(cap, capture.call_args.kwargs['completed_frozen'])
                self.assertIs(cap, resume.call_args.kwargs['completed_frozen'])
                invalid = list(argv)
                invalid[invalid.index('--state-root') + 1] = str(self.scratch / 'wrong-state')
                with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    adapter.main(invalid)
                authority.assert_called_once()
                capture.assert_called_once()
                resume.assert_called_once()
        ordinary = self.resume(destination=self.scratch / 'ordinary-direct')
        self.assertEqual(load_canonical_json(ordinary / 'phase-plans/runtime-jvm-binary-jvm.json'),
                         load_canonical_json(resumed / 'phase-plans/runtime-jvm-binary-jvm.json'))
        self.assertFalse(any(row['relativePath'].endswith('.zip') for row in regular_file_inventory(resumed)))
        changed = deepcopy(request)
        changed['catalogs']['samePr'] = [{'unexpected': 'candidate'}]
        rejected = self.scratch / 'rejected-native-discovery'
        rejected.mkdir()
        trust = adapter._release_trust(self.repository, self.commit, rejected)
        with self.assertRaisesRegex(ValueError, 'unchanged catalogs'):
            adapter._seed_completed_contract_discovery(self.plan, changed, rejected,
                self.repository, self.environment, cap, trust)
        self.assertFalse((rejected / 'native-contract-state').exists())

    def test_native_discovery_composes_resume_under_the_same_capability(self):
        from products.inventory import load_canonical_json_bytes
        from runtime_reference_transport import validate_original_references
        cap, _ = self.completed_contract_fixture(incremental=True)
        discovery = self.scratch / 'composed-discovery'
        handoff = self.scratch / 'composed-handoff'
        output = self.scratch / 'composed-output'
        wave_request = adapter._wave_request
        def original_location(*args, **kwargs):
            request = wave_request(*args, **kwargs)
            if all(instance.product == 'contract' for instance in args[3]):
                request['artifactRoot'] = str(self.repository / 'build/product-reuse')
            return request
        with self.control_seams(), \
                mock.patch.object(adapter, '_discover_catalogs', return_value=[]), \
                mock.patch.object(adapter, '_wave_request', side_effect=original_location), \
                mock.patch.object(adapter, 'verify_object', side_effect=AssertionError('Contract body opened')), \
                mock.patch.object(adapter, 'capture_product_resume_inputs', side_effect=AssertionError('Plan recaptured')), \
                mock.patch.object(adapter, 'resume_products', wraps=adapter.resume_products) as resume, \
                mock.patch('sdk_ios_binary_recovery.capture_completed_ios_binary', return_value=[]):
            result = adapter.discover(self.plan_path, discovery, output,
                repository_root=self.repository, environ=self.environment, completed_frozen=cap,
                native_resume_handoff=handoff, tooling_workflow_sha='c' * 40,
                tooling_java_executable=Path('/unused-java'))
            self.assertEqual('native-contract-complete', result['reason'])
            resume.assert_called_once()
            self.assertIs(cap, resume.call_args.kwargs['completed_frozen'])
            self.assertTrue(resume.call_args.kwargs['routing_output'])
        values = dict(line.split('=', 1) for line in output.read_text().splitlines())
        self.assertEqual('true', values['native_resume_ready'])
        self.assertEqual('true', values['native_resume_runtime_workers_required'])
        self.assertIn('native_resume_routing_decisions', values)
        self.assertEqual('native-contract-complete', values['product_reuse_reason'])
        # A native Contract hit cannot bypass missing current SDK tooling.
        missing_output = self.scratch / 'missing-tooling-output'
        missing_handoff = self.scratch / 'missing-tooling-handoff'
        with self.control_seams(), \
                mock.patch.object(adapter, '_requested', return_value=(adapter.PhaseInstanceId('sdk', 'sdk-ios', 'package', 'ios'),)), \
                mock.patch.object(adapter, '_discover_catalogs', return_value=[]), \
                mock.patch.object(adapter, '_wave_request', side_effect=original_location), \
                mock.patch.object(adapter, '_resume_native_discovery', side_effect=AssertionError('Missing tooling admitted')):
            missed = adapter.discover(self.plan_path, self.scratch / 'missing-tooling', missing_output,
                repository_root=self.repository, environ=self.environment, completed_frozen=cap,
                native_resume_handoff=missing_handoff, tooling_workflow_sha='c' * 40,
                tooling_java_executable=Path('/unused-java'))
        self.assertEqual('native-contract-complete', missed['reason'])
        missing_values = dict(line.split('=', 1) for line in missing_output.read_text().splitlines())
        self.assertEqual('true', missing_values['tooling_miss'])
        self.assertEqual('false', missing_values['native_resume_ready'])
        self.assertFalse(missing_handoff.exists())
        references = validate_original_references(load_canonical_json_bytes(
            (handoff / 'runtime-original-references.json').read_bytes()))
        paths = {row['relativePath'] for row in references['inventory']}
        self.assertIn('product-resume-inputs/plan/impact-plan.json', paths)
        self.assertIn('product-resume-state/phase-plans/runtime-jvm-binary-jvm.json', paths)
        self.assertFalse(any(path.endswith('.zip') for path in paths))
        ordinary = self.resume(destination=self.scratch / 'ordinary-composed-comparison')
        self.assertEqual(load_canonical_json(ordinary / 'phase-plans/runtime-jvm-binary-jvm.json'),
                         load_canonical_json(handoff / 'product-resume-state/phase-plans/runtime-jvm-binary-jvm.json'))
        # The lightweight forwarding job still authenticates its exact original
        # upload. This is transport custody, not a saved phase-admission verdict.
        from ci.tests.test_product_resume_capture import archive
        from products.inventory import sha256_bytes
        files = {row['relativePath']: (handoff / row['relativePath']).read_bytes()
                 for row in regular_file_inventory(handoff)}
        observed = [{'run': {'head_sha': self.commit}, 'jobs': [{
            'name': 'product-validation / plan', 'started_at': '2026-10-14T00:00:00Z',
            'completed_at': '2026-10-14T00:01:00Z'}]}]
        for case in ('valid', 'bytes', 'plan', 'window', 'origin'):
            with self.subTest(case=case):
                members = dict(files)
                if case == 'plan':
                    members['product-resume-inputs/plan/impact-plan.json'] = b'{}\n'
                body = archive(members)
                artifact = {'id': 772, 'digest': sha256_bytes(body), 'size_in_bytes': len(body),
                    'name': 'codex-agent-planned-product-resume-' + self.producer['tree'],
                    'expired': False, 'created_at': '2026-10-14T00:00:30Z',
                    'archive_download_url': 'https://api.github.com/repos/codex-agent-labs/codex-agent/actions/artifacts/772/zip',
                    'workflow_run': {'id': self.producer['runId'], 'head_sha': self.commit}}
                if case == 'window':
                    artifact['created_at'] = '2026-10-13T00:00:30Z'
                if case == 'origin':
                    artifact['workflow_run']['id'] += 1
                forwarded = self.scratch / ('forwarded-' + case)
                with self.control_seams(), \
                        mock.patch.object(adapter, '_observe_ci_producer_jobs', return_value=observed) as observe, \
                        mock.patch.object(adapter, 'api_json', return_value=artifact), \
                        mock.patch.object(adapter, 'download_artifact', return_value=body + (b'x' if case == 'bytes' else b'')), \
                        mock.patch.object(adapter, 'resume_products', side_effect=AssertionError('Resume repeated')):
                    def capture():
                        adapter.capture_planned_native_resume(self.plan_path, forwarded,
                            artifact_id=772, artifact_sha256=artifact['digest'], trusted_workflow_sha='c' * 40,
                            token='fixture', repository_root=self.repository, environ=self.environment)
                    if case == 'valid':
                        capture()
                        self.assertEqual(regular_file_inventory(handoff), regular_file_inventory(forwarded))
                    else:
                        with self.assertRaises(ValueError):
                            capture()
                        self.assertFalse(forwarded.exists())
                    self.assertEqual({'plan': 'product-validation / plan'}, observe.call_args.kwargs['jobs_by_phase'])

    def test_native_contract_consumption_uses_bundle_once_and_reproduces_all_original_objects(self):
        from contextlib import contextmanager
        import io
        import zipfile
        import reuse_qualification as qualification
        from products.inventory import load_canonical_json_bytes
        from runtime_reference_archive import copy_reference_member
        cap, _ = self.completed_contract_fixture()
        native = load_canonical_json_bytes(cap._contract)
        sdk_raw, original_raw = io.BytesIO(), io.BytesIO()
        with zipfile.ZipFile(sdk_raw, 'w') as archive:
            for row in cap.sdk_original()['proof']['sdkInputs']['files']:
                if row['relativePath'].endswith('.zip'):
                    name = row['relativePath'].split('/', 3)[3]
                    archive.writestr(row['relativePath'], (self.handoff / name).read_bytes())
        with zipfile.ZipFile(original_raw, 'w') as archive:
            for phase in ('binary', 'package', 'validation', 'metadata'):
                for row in regular_file_inventory(self.original / (phase + '-stage')):
                    name = f"inputs/predecessors/contract-contract-{phase}-common/stage/" + row['relativePath']
                    archive.writestr(name, (self.original / (phase + '-stage') / row['relativePath']).read_bytes())
        remote_members = []
        @contextmanager
        def ranges(artifact, token):
            with zipfile.ZipFile(io.BytesIO(sdk_raw.getvalue() if artifact['id'] == 81 else original_raw.getvalue())) as archive:
                yield archive, None
        def copied(archive, name, destination, row):
            if name.startswith(('sdk-inputs/', 'inputs/predecessors/')):
                remote_members.append(name)
            return copy_reference_member(archive, name, destination, row)
        records, _ = adapter._completed_contract_objects(self.plan, self.state, self.state, self.environment)
        from runtime_reference_transport import selected_reference_paths
        references = [{'relativePath': 'product-resume-state/' + row['objectPath'],
                       'bytes': 1, 'sha256': row['objectSha256']} for row in records]
        transport = {'inventory': references, 'references': references}
        self.assertEqual({row['relativePath'] for row in references},
                         selected_reference_paths(transport, completed_frozen=cap))
        marker = {'relativePath': 'product-resume-state/authenticated-contract/contract-input/contract-manifest.json',
                  'bytes': 1, 'sha256': 'sha256:' + 'e' * 64}
        transport['inventory'] = [*references, marker]
        self.assertEqual({marker['relativePath']}, selected_reference_paths(transport, completed_frozen=cap))
        transport['references'] = references[1:]
        self.assertEqual({marker['relativePath'], references[0]['relativePath']},
                         selected_reference_paths(transport, completed_frozen=cap))
        with mock.patch.object(adapter, '_authenticate_runtime_original_reference_source', return_value=(
                {'id': 71}, None, [{'jobs': [{'name': 'product-validation / runtime-contract-binary-common'}]}], 'a' * 40)), \
                mock.patch.object(adapter, '_runtime_original_locator', return_value=native['locator']), \
                mock.patch.object(qualification, '_observe_completed_sdk_inputs', return_value=({'id': 81}, None, {})), \
                mock.patch('hydrated_evidence.copy', return_value=False), \
                mock.patch('runtime_reference_archive.open_reference_archive', side_effect=ranges), \
                mock.patch('runtime_reference_archive.copy_reference_member', side_effect=copied):
            for row in records:
                target = self.scratch / (row['phase'] + '-restored.zip')
                cap.capture_object(row, target, plan=self.plan, producer=self.producer,
                    trusted_workflow_sha='a' * 40, token='fixture')
                self.assertEqual((self.state / row['objectPath']).read_bytes(), target.read_bytes())
            self.assertEqual(3, len(remote_members))
            # Exercise the shared worker boundary, where the deferred execution
            # archive must rejoin the original signed closure before C# can run.
            from types import SimpleNamespace
            release = self.scratch / 'release-controls'
            adapter.prepare_contract_release_controls(self.handoff, release)
            small = release / 'contract-input'
            evidence = {'attestation': small / 'codex-agent-contract-0.2.0.attestation.json',
                'attestationSignature': small / 'codex-agent-contract-0.2.0.attestation.sig',
                'publicKey': small / 'public-key.pub'}
            def original(product, component, phase, target):
                self.assertEqual(('contract', 'contract', 'common'), (product, component, target))
                return {'stage': self.original / (phase + '-stage'), 'receiptPath': self.receipts[phase],
                        'receipt': load_canonical_json(self.receipts[phase])}
            def one_output(value, kind):
                outputs = [row for row in value['receipt']['outputs'] if row['kind'] == kind]
                self.assertEqual(1, len(outputs))
                return value['stage'] / outputs[0]['relativePath']
            prepared = self.scratch / 'worker-inputs'
            prepared.mkdir()
            trust = SimpleNamespace(keyring=self.repository / 'gradle/release/product-signing-keys.json',
                                    keys=self.repository / 'gradle/release/keys')
            _, _, handoff, _, inventory = adapter._capture_runtime_contract(
                self.repository, evidence, original, one_output, prepared, trust)
            self.assertEqual(regular_file_inventory(self.handoff), inventory)
            self.assertEqual(inventory, regular_file_inventory(handoff))
            cached = next((self.scratch / 'body-cache').iterdir())
            cached.write_bytes(b'corrupt')
            with self.assertRaises(ValueError):
                cap.capture_object(next(row for row in records if row['phase'] == 'binary'),
                    self.scratch / 'corrupt-result.zip', plan=self.plan, producer=self.producer,
                    trusted_workflow_sha='a' * 40, token='fixture')
            self.assertFalse((self.scratch / 'corrupt-result.zip').exists())

    def test_native_contract_controls_replay_identical_keys_without_product_bodies(self):
        cap, discovery = self.completed_contract_fixture()
        controls, release = self.scratch / 'controls', self.scratch / 'release'
        with self.control_seams():
            # Match the relative CLI paths used by the reusable workflow.
            with chdir(self.repository):
                adapter.prepare_contract_resume_controls(self.plan_path.relative_to(self.repository),
                    discovery.relative_to(self.repository), self.state.relative_to(self.repository),
                    controls.relative_to(self.repository), completed_frozen=cap,
                    repository_root=self.repository, environ=self.environment)
            adapter.prepare_contract_release_controls(self.handoff, release)
            with mock.patch.object(adapter, 'advance_contract', side_effect=AssertionError('unexpected legacy replay')), \
                    mock.patch.object(adapter, 'materialize_contract', side_effect=AssertionError('routing hydrated a body')), \
                    mock.patch('sdk_ios_binary_recovery.capture_completed_ios_binary', return_value=[]):
                result = self.scratch / 'native-resume'
                adapter.resume_products(controls / 'plan/impact-plan.json', controls / 'plan/product-reuse',
                    controls / 'state', release / 'contract-input', result, self.scratch / 'native-output',
                    completed_frozen=cap, repository_root=self.repository, environ=self.environment,
                    routing_output=True, sdk_original_workflow_sha='c' * 40)
                verified = adapter._verified_product_state(controls / 'plan/impact-plan.json', result, result,
                    self.repository, self.environment, None, completed_frozen=cap)
        ordinary = self.resume(destination=self.scratch / 'ordinary')
        self.assertEqual(load_canonical_json(ordinary / 'phase-plans/runtime-jvm-binary-jvm.json'),
                         verified.prior_ready_plans[JVM])
        self.assertFalse(any(row['relativePath'].endswith('.zip') for row in regular_file_inventory(controls)))
        self.assertFalse(any(row['relativePath'].endswith('.zip') for row in regular_file_inventory(result)))
        self.assertLess(sum(row['bytes'] for row in regular_file_inventory(result)),
                        sum(row['bytes'] for row in regular_file_inventory(ordinary)))

    def test_sdk_routing_uses_exact_native_contract_receipt_without_opening_deferred_body(self):
        from types import SimpleNamespace
        from sdk_native_continuation import emit
        cap, discovery = self.completed_contract_fixture()
        result = load_canonical_json(discovery / 'contract-reuse-result.json')
        request = load_canonical_json(discovery / 'contract-reuse-request.json')
        contract = adapter.PhaseInstanceId('contract', 'contract', 'metadata', 'common')
        # Only the pending SDK election is synthetic; Contract identity, receipt
        # and current Git selection are real. Routing grants no execution trust.
        result['phases'].append({'product': 'sdk', 'component': 'javascript',
                                 'phase': 'metadata', 'target': 'node', 'state': 'blocked'})
        sources = {contract: self.state / next(row['objectPath'] for row in request['availableObjects']
                                               if adapter._identity(row) == contract)}
        expected = adapter._sdk_input_selection_from_transition(self.plan, result, sources,
            fixture.VERSIONS, request, self.repository)
        self.assertEqual(1, len(expected['consumers']))
        sources[contract] = self.scratch / 'deferred-metadata.zip'
        state = SimpleNamespace(plan=self.plan, prior=result, sources=sources,
            expected_fixed={'versions': fixture.VERSIONS}, rebased_request=request, completed_frozen=cap)
        with mock.patch.object(adapter, 'verify_object', side_effect=AssertionError('routing opened a body')):
            self.assertEqual(expected, adapter._sdk_input_selection(state, self.repository))
            output = self.scratch / 'routing-output'
            emit(self.plan, result, [], sources, request, self.repository, self.environment, 'c' * 40,
                 output, completed_frozen=cap)
            fields = dict(line.split('=', 1) for line in output.read_text().splitlines())
            routing = json.loads(fields['routing_decisions'])
            self.assertEqual(expected, json.loads(routing['runtime']['sdk_input_selection']))
            record = next(row for row in result['phases'] if adapter._identity(row) == contract)
            record['objectSha256'] = 'sha256:' + 'f' * 64
            with self.assertRaisesRegex(ValueError, 'exact proved identity'):
                adapter._sdk_input_selection(state, self.repository)
        state.completed_frozen = None
        with self.assertRaisesRegex(ValueError, 'missing or unsafe'):
            adapter._sdk_input_selection(state, self.repository)
        state.completed_frozen = SimpleNamespace(envelope=lambda row: {})
        with self.assertRaisesRegex(ValueError, 'concrete native semantic evidence'):
            adapter._sdk_input_selection(state, self.repository)

    def test_native_contract_controls_reject_mutation_and_changed_current_trust(self):
        cap, _ = self.completed_contract_fixture()
        release = self.scratch / 'release'
        adapter.prepare_contract_release_controls(self.handoff, release)
        handoff = release / 'contract-input'
        keyring = self.repository / 'gradle/release/product-signing-keys.json'
        keys = keyring.parent / 'keys'
        cap.verify_contract_handoff(handoff, keyring=keyring, keys_directory=keys)
        for name in ('contract-manifest.json', 'codex-agent-contract-0.2.0.attestation.json',
                     'codex-agent-contract-0.2.0.attestation.sig', 'public-key.pub',
                     'execution-closure/receipts/binary.json', 'execution-closure/contract-execution-closure.json'):
            path = handoff / name
            raw = path.read_bytes()
            path.write_bytes(raw + b' ')
            with self.subTest(name=name), self.assertRaises(ValueError):
                cap.verify_contract_handoff(handoff, keyring=keyring, keys_directory=keys)
            path.write_bytes(raw)
        with self.assertRaises(ValueError):
            cap.verify_contract_handoff(handoff, keyring=self.scratch / 'missing-keyring', keys_directory=keys)
        cap._receipts = tuple((fields, raw) for fields, raw in cap._receipts if fields[0] != 'runtime')
        with self.assertRaisesRegex(ValueError, 'native semantic projection'):
            cap.verify_contract_handoff(handoff, keyring=keyring, keys_directory=keys)

    def test_prior_attempt_contract_snapshot_preserves_originals_and_current_consumer(self):
        baseline = self.resume(destination=self.scratch / "baseline")
        current = {**self.environment, "GITHUB_RUN_ATTEMPT": "3"}
        resumed = self.resume(environ=current)
        self.assertEqual(adapter._consumer(self.plan, current)["producer"],
                         load_canonical_json(resumed / "producer.json"))
        self.assertEqual(load_canonical_json(baseline / "phase-plans/runtime-jvm-binary-jvm.json"),
                         load_canonical_json(resumed / "phase-plans/runtime-jvm-binary-jvm.json"))
        request = load_canonical_json(resumed / "reuse-wave-request.json")
        for record in request["availableObjects"]:
            original = adapter.verify_object(resumed / record["objectPath"], build_key=record["buildKey"],
                                             receipt_sha256=record["receiptSha256"], object_sha256=record["objectSha256"])
            self.assertEqual(self.original_bytes[record["phase"]], original["receiptBytes"])
            self.assertEqual(self.producer, original["receipt"]["producer"])

    def test_sdk_scope_replays_required_contract_and_excludes_unrelated_ios_recovery(self):
        from products import reuse as reuse_planner
        javascript = adapter.PhaseInstanceId("sdk", "javascript", "metadata", "node")
        ios = adapter.PhaseInstanceId("sdk", "sdk-ios", "binary", "ios")
        requested = tuple(sorted((javascript, ios)))
        original_authorities = adapter._authorities
        original_plan = reuse_planner._plan
        def fixture_plan(identity, inputs, upstream, *location):
            # This fixture supplies synthetic Runtime build authorities only.
            # Contract byte/signature replay and dependency/key planning are real;
            # no Runtime build or host admission is claimed by this test.
            if identity.product == "runtime":
                return reuse_planner.plan_phase(identity, upstream_receipts=upstream, **inputs[identity])
            return original_plan(identity, inputs, upstream, *location)
        def authorities(root, revision, closure):
            rows = []
            for identity in closure:
                actual, _ = original_authorities(root, revision, (identity,))
                rows.extend(actual or [{**adapter._identity_record(identity),
                    "toolchainProfileDigest": "sha256:" + "a" * 64,
                    "flagsDigest": "sha256:" + "b" * 64, "outputSchemaVersion": 1}])
            return rows, None
        resumed = self.scratch / "sdk-state"
        with mock.patch.object(adapter, "_validate_plan", return_value=self.plan), \
                mock.patch.object(adapter, "_requested", return_value=requested), \
                mock.patch.object(adapter, "_authorities", side_effect=authorities), \
                mock.patch.object(reuse_planner, "_plan", side_effect=fixture_plan):
            adapter.resume_products(self.plan_path, self.discovery, self.state, self.handoff, resumed,
                self.scratch / "sdk-output", repository_root=self.repository, environ=self.environment)
            full = adapter._verified_product_state(self.plan_path, resumed, resumed,
                self.repository, self.environment, None)
            scope = adapter._verified_product_state(self.plan_path, resumed, resumed,
                self.repository, self.environment, None, requested_scope=(javascript,))
            self.assertNotIn(ios, scope.closure)
            self.assertEqual(adapter._scoped_reuse_result(full.prior, scope.closure), scope.prior)
            self.assertEqual({key: value for key, value in full.prior_ready_plans.items()
                              if key in scope.closure}, scope.prior_ready_plans)
            retry_environment = {**self.environment, "GITHUB_RUN_ATTEMPT": "3", "GITHUB_TOKEN": "synthetic"}
            original_producer_bytes = (resumed / "producer.json").read_bytes()
            with mock.patch.object(adapter, "_observe_ci_producer_jobs") as observe:
                retry = adapter._verified_product_state(self.plan_path, resumed, resumed,
                    self.repository, retry_environment, None, requested_scope=(javascript,),
                    sdk_original_workflow_sha="a" * 40)
            self.assertEqual(3, retry.producer["runAttempt"])
            self.assertEqual(scope.prior, retry.prior)
            self.assertEqual(original_producer_bytes, (resumed / "producer.json").read_bytes())
            self.assertEqual("3", retry_environment["GITHUB_RUN_ATTEMPT"])
            self.assertEqual(scope.producer, observe.call_args.args[0]["state"])
            with self.assertRaisesRegex(ValueError, "fresh original workflow authority"):
                adapter._verified_product_state(self.plan_path, resumed, resumed,
                    self.repository, retry_environment, None, requested_scope=(javascript,))
            (resumed / "prior-failed-sdk").mkdir()
            again = adapter._verified_product_state(self.plan_path, resumed, resumed,
                self.repository, self.environment, None, requested_scope=(javascript,))
            self.assertEqual(scope.prior, again.prior)
            with self.assertRaisesRegex(ValueError, "Prior SDK replay requires"):
                adapter._verified_product_state(self.plan_path, resumed, resumed,
                    self.repository, self.environment, None)
            (resumed / "prior-failed-sdk").rmdir()
            (resumed / "prior-failed-sdk-javascript").mkdir()
            with self.assertRaisesRegex(ValueError, "Prior JavaScript replay requires"):
                adapter._verified_product_state(self.plan_path, resumed, resumed,
                    self.repository, self.environment, None, requested_scope=(javascript,))
            with mock.patch("sdk_ios_binary_recovery.replay_prior_javascript_package") as replay:
                adapter._verified_product_state(self.plan_path, resumed, resumed,
                    self.repository, self.environment, None, requested_scope=(ios,))
            replay.assert_not_called()
            (resumed / "prior-failed-sdk-javascript").rmdir()
            required = next(iter(scope.sources.values()))
            required.chmod(0o600)
            required.write_bytes(b"damaged required input")
            with self.assertRaises(ValueError):
                adapter._verified_product_state(self.plan_path, resumed, resumed,
                    self.repository, self.environment, None, requested_scope=(javascript,))

    def test_recovered_javascript_package_is_carried_from_its_own_root(self):
        # Orchestration fixture: synthetic SDK election, real Contract replay,
        # original object/shard verification and carrier writing. No host proof.
        from products import reuse as reuse_planner
        import sdk_ios_binary_recovery as recovery
        from ci.tests.product_chain_support import write_receipt
        from ci.products.receipt import write_output_manifest
        package = adapter.PhaseInstanceId("sdk", "javascript", "package", "node")
        validation = adapter.PhaseInstanceId("sdk", "javascript", "validation", "node")
        stage = self.scratch / "package-stage"
        (stage / "outputs").mkdir(parents=True)
        (stage / "outputs/package.tgz").write_bytes(b"synthetic original package\n")
        manifest = write_output_manifest(stage, "sdk", "javascript", "package", "node", "0.2.0",
                                         {"package": "outputs"})
        receipt = write_receipt(self.scratch / "original-receipt.json", product="sdk", component="javascript",
            phase="package", target="node", outputs=manifest["outputs"], upstream=[], version="0.2.0",
            context={"producer": {**self.producer, "runId": 6}})
        package_plan = {field: receipt[field] for field in adapter.PHASE_PLAN_KEYS}
        original_authorities, original_plan = adapter._authorities, reuse_planner._plan
        original_wave = adapter._plan_with_sdk_tooling

        def authorities(root, revision, closure):
            rows = []
            for identity in closure:
                actual, _ = original_authorities(root, revision, (identity,))
                rows.extend(actual or [{**adapter._identity_record(identity),
                    "toolchainProfileDigest": "sha256:" + "a" * 64,
                    "flagsDigest": "sha256:" + "b" * 64, "outputSchemaVersion": 1}])
            return rows, None

        def fixture_plan(identity, inputs, upstream, *location):
            if identity.product == "runtime":
                return reuse_planner.plan_phase(identity, upstream_receipts=upstream, **inputs[identity])
            return original_plan(identity, inputs, upstream, *location)

        def elect(wave, tooling, **kwargs):
            records = [r for r in wave["availableObjects"] if adapter._identity(r) == package]
            # Missing Runtime fixtures do not claim actual SDK key planning.
            base = {**wave, "availableObjects": [r for r in wave["availableObjects"]
                                                  if adapter._identity(r) != package]}
            result = original_wave(base, tooling, **kwargs)
            for row in result["phases"]:
                identity = adapter._identity(row)
                if identity == package:
                    row.update(state="retained" if records else "build", buildKey=receipt["buildKey"],
                        receiptSha256=records[0]["receiptSha256"] if records else None,
                        objectSha256=records[0]["objectSha256"] if records else None,
                        misses=[] if records else [{"source": s, "reason": "fixture-miss"} for s in adapter.SOURCES])
                elif identity == validation and records:
                    row.update(state="build", buildKey="sha256:" + "c" * 64,
                        misses=[{"source": s, "reason": "fixture-miss"} for s in adapter.SOURCES])
            result["matrices"] = {product: [{**adapter._identity_record(adapter._identity(row)),
                "buildKey": row["buildKey"]} for row in result["phases"]
                if row["product"] == product and row["state"] == "build"]
                for product in ("contract", "runtime", "sdk")}
            return result

        def capture(plan, producer, key, destination, artifact_root, **kwargs):
            if kwargs.get("phase") == "validation":
                self.assertEqual("sha256:" + "c" * 64, key)
                self.assertEqual("prior-failed-sdk-javascript-validation", destination.name)
                return []  # This package-only fixture contains no successful validation.
            self.assertEqual(receipt["buildKey"], key)
            self.assertEqual("prior-failed-sdk-javascript", destination.name)
            fixture.finalize_phase_object(stage_root=stage, phase_plan=package_plan,
                producer=receipt["producer"], product_version="0.2.0", trust_domain="development",
                destination=destination / "javascript/package/node/original/shard")
            return [recovery._javascript_package_record(destination / "javascript/package/node", artifact_root)]

        def synthetic_election(result, requested, **kwargs):
            # Runtime execution prerequisites are intentionally absent here.
            # Only the root recovery-to-carrier path is under test; helper
            # tests independently authenticate uploads and original receipts.
            selected = tuple(adapter._identity(row) for row in result["phases"] if row["state"] == "retained")
            return result, selected, result["phases"]

        resumed = self.scratch / "js-resumed"
        with mock.patch.object(adapter, "_validate_plan", return_value=self.plan), \
                mock.patch.object(adapter, "_requested", return_value=(validation,)), \
                mock.patch.object(adapter, "_authorities", side_effect=authorities), \
                mock.patch.object(reuse_planner, "_plan", side_effect=fixture_plan), \
                mock.patch.object(adapter, "_plan_with_sdk_tooling", side_effect=elect), \
                mock.patch.object(adapter, "_validate_reuse_result", side_effect=synthetic_election), \
                mock.patch.object(adapter, "_prior_failed_pr_attempts", return_value=[]), \
                mock.patch.object(recovery, "capture_prior_javascript_package", side_effect=capture) as captured:
            result = adapter.resume_products(self.plan_path, self.discovery, self.state, self.handoff, resumed,
                self.scratch / "js-output", repository_root=self.repository,
                environ={**self.environment, "GITHUB_TOKEN": "synthetic"}, sdk_original_workflow_sha="a" * 40)
        self.assertEqual(2, captured.call_count)
        self.assertEqual("validation", captured.call_args.kwargs["phase"])
        reuse = load_canonical_json(resumed / "reuse-wave-result.json")
        self.assertEqual(["validation"], [row["phase"] for row in reuse["matrices"]["sdk"]])
        retained = next(row for row in reuse["phases"] if adapter._identity(row) == package)
        self.assertEqual("retained", retained["state"])
        self.assertEqual(receipt["buildKey"], retained["buildKey"])
        original = resumed / "prior-failed-sdk-javascript/javascript/package/node/original/shard"
        self.assertEqual((self.scratch / "original-receipt.json").read_bytes(),
                         (original / "phase-receipt.json").read_bytes())
        self.assertTrue(result["targetJobsRequired"])

    def test_independent_csharp_recovery_precedes_expensive_ios_admission(self):
        # Real Contract setup; synthetic SDK selection stops before publication.
        import sdk_ios_binary_recovery as recovery
        package = adapter.PhaseInstanceId("sdk", "sdk-ios", "package", "ios")
        csharp = adapter.PhaseInstanceId("sdk", "csharp", "binary", "desktop")
        key = "sha256:" + "a" * 64
        events = []
        original_wave = adapter._plan_with_sdk_tooling
        class Recovered(Exception):
            pass
        def elect(wave, *args, **kwargs):
            if all(row["product"] == "contract" for row in wave["requested"]):
                return original_wave(wave, *args, **kwargs)
            available = {adapter._identity(row) for row in wave["availableObjects"]}
            if package in available:
                events.append("package-gate")
                self.assertIn(csharp, available)
                raise Recovered
            return {"phases": [{**adapter._identity_record(instance), "buildKey": key,
                "state": "retained" if instance in available else "build"} for instance in (package, csharp)]}
        def captured(instance):
            events.append(instance.component)
            return [{**adapter._identity_record(instance), "buildKey": key}]
        with self.control_seams(), mock.patch.object(adapter, "_plan_with_sdk_tooling", side_effect=elect), \
                mock.patch.object(adapter, "_prior_failed_pr_attempts", return_value=[]), \
                mock.patch.object(recovery, "capture_prior_javascript_package", side_effect=lambda *_a, **_k: captured(csharp)), \
                mock.patch.object(recovery, "capture_prior_ios_binary", side_effect=lambda *_a, **_k: captured(package)), \
                self.assertRaises(Recovered):
            adapter.resume_products(self.plan_path, self.discovery, self.state, self.handoff,
                self.scratch / "cold-order", self.scratch / "cold-order-output", repository_root=self.repository,
                environ={**self.environment, "GITHUB_TOKEN": "synthetic"}, sdk_original_workflow_sha="a" * 40)
        self.assertEqual(["csharp", "sdk-ios", "package-gate"], events)

    def test_future_attempt_and_different_run_contract_snapshots_reject(self):
        for field, value in (("GITHUB_RUN_ATTEMPT", "1"), ("GITHUB_RUN_ID", "8")):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "Contract.*consumer"):
                self.resume(environ={**self.environment, field: value},
                            destination=self.scratch / field)
            self.assertFalse((self.scratch / field).exists())

    def test_completed_original_contract_unlocks_real_runtime_plan_and_retains_signed_catalog(self):
        with mock.patch.object(adapter, "materialize_contract", wraps=adapter.materialize_contract) as materialize:
            resumed = self.resume(routing_output=True)
        self.assertEqual(["binary", "metadata"], [call.args[2] for call in materialize.call_args_list])
        request = load_canonical_json(resumed / "reuse-wave-request.json")
        result = load_canonical_json(resumed / "reuse-wave-result.json")
        self.assertFalse(result["fullReuse"])
        self.assertEqual([], result["matrices"]["contract"])
        self.assertEqual([], result["matrices"]["sdk"])
        self.assertEqual(1, len(result["matrices"]["runtime"]))
        ready = load_canonical_json(resumed / "phase-plans/runtime-jvm-binary-jvm.json")
        self.assertEqual(ready["buildKey"], result["matrices"]["runtime"][0]["buildKey"])
        outputs = dict(line.split("=", 1) for line in (self.scratch / "github-output").read_text().splitlines())
        self.assertEqual(ready["buildKey"], json.loads(outputs["runtime_matrix"])["include"][0]["buildKey"])
        decisions = json.loads(outputs["routing_decisions"])
        self.assertEqual(self.producer, decisions["producer"])
        self.assertEqual([], decisions["ready"])
        self.assertEqual("not-selected", decisions["runtime"]["aggregate_state"])
        self.assertEqual(adapter._identity_record(JVM), {field: ready[field] for field in adapter._IDENTITY_KEYS})
        self.assertEqual("release", request["contractEvidence"]["expectedTrustDomain"])
        self.assertEqual(4, len(request["availableObjects"]))
        for record in request["availableObjects"]:
            original = adapter.verify_object(resumed / record["objectPath"], build_key=record["buildKey"],
                                             receipt_sha256=record["receiptSha256"], object_sha256=record["objectSha256"])
            self.assertEqual(self.original_bytes[record["phase"]], original["receiptBytes"])
        for field, basename in (("manifest", "product-index.json"), ("signature", "product-index.sig"),
                                ("publicKey", "public-key.pub")):
            self.assertEqual((self.discovery / "catalog" / basename).read_bytes(),
                             (resumed / request["catalogs"]["samePr"][field]).read_bytes())

    def test_receipt_only_contract_phases_still_reject_corrupt_original_objects(self):
        for phase in ("package", "validation"):
            state = self.scratch / phase / "state"
            shutil.copytree(self.state, state)
            with self.control_seams():
                records, _ = adapter._completed_contract_objects(
                    self.plan, state, state, self.environment)
                record = next(row for row in records if row["phase"] == phase)
                with (state / record["objectPath"]).open("ab") as changed:
                    changed.write(b"corrupt original")
                destination = self.scratch / phase / "handoff"
                with self.subTest(phase=phase), self.assertRaises(ValueError):
                    adapter._capture_completed_contract_handoff(self.plan_path, state, self.handoff,
                        destination, repository_root=self.repository, environ=self.environment)
            self.assertFalse(destination.exists())

    def test_later_continuation_replays_captured_inputs_without_original_discovery_or_handoff(self):
        resumed = self.resume()
        hidden = []
        try:
            for source in (self.discovery, self.state, self.handoff):
                target = source.with_name(source.name + "-hidden")
                source.rename(target)
                hidden.append((source, target))
            with self.control_seams(), self.assertRaisesRegex(ValueError, "shards and failures do not exactly partition"):
                # A JVM build remains genuinely required; do not synthesize a success receipt.
                adapter.advance_products(self.plan_path, resumed, None, [], self.scratch / "advanced",
                                         self.scratch / "advance-output", repository_root=self.repository,
                                         environ=self.environment)
        finally:
            for source, target in reversed(hidden):
                target.rename(source)

    def test_changed_signed_handoff_rejects_before_runtime_plans_are_published(self):
        changed = self.scratch / "changed-handoff"
        shutil.copytree(self.handoff, changed)
        receipt = changed / "execution-closure/receipts/metadata.json"
        receipt.write_bytes(receipt.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            self.resume(handoff=changed)
        self.assertFalse((self.scratch / "resumed").exists())

    def test_late_resume_control_mutation_cannot_publish(self):
        def mutate_during_copy(source, destination, **kwargs):
            if (Path(source) / "reuse-wave-result.json").exists():
                (Path(source) / "reuse-wave-result.json").write_bytes(b"changed during copy")
            actual_publish_regular_tree(source, destination, **kwargs)

        with mock.patch.object(adapter, "publish_regular_tree", side_effect=mutate_during_copy), \
                self.assertRaisesRegex(ValueError, "pinned inventory"):
            self.resume()
        self.assertFalse((self.scratch / "resumed").exists())


if __name__ == "__main__":
    unittest.main()
