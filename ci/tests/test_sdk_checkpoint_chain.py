"""Two actual local issuances; HTTP, native crypto, Git and Contract seams explicit."""
from contextlib import ExitStack, contextmanager
from copy import deepcopy
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

import completed_sdk_reuse as completed
import product_reuse as products
import reuse
import reuse_qualification as native
from products.inventory import canonical_json_bytes, sha256_bytes
from products.receipt import compute_build_key, write_output_manifest
from products.restore import PHASE_PLAN_KEYS, finalize_phase_object
from sdk_campaign_original_locator import fresh_sdk_worker_route
from ci.tests.test_sdk_checkpoint_consumer import SdkCheckpointConsumerTest


class SdkCheckpointChainTest(unittest.TestCase):
    def setUp(self):
        self.fixture = SdkCheckpointConsumerTest(); self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        c = self.fixture; f = c.f
        self.f = f
        f.policy['collectors'] = sorted([f.source['jobName'], 'product-validation / sdk-collect-10'])
        f.envelope['ownerPolicySha256'] = sha256_bytes(canonical_json_bytes(f.policy))
        f.upload(); c.output['subjectSha256'] = sha256_bytes(f.subject)
        self.source = {**deepcopy(f.source), 'jobName': 'product-validation / sdk-collect-10',
            'jobId': 995, 'artifactId': 996, 'artifactSha256': sha256_bytes(b'state ten')}
        self.collector = {**f.collector, 'id': 995, 'name': self.source['jobName'],
            'started_at': '2026-10-24T10:45:00Z', 'completed_at': '2026-10-24T10:55:00Z'}
        self.current = {**c.current, 'id': 997,
            'name': 'product-validation / sdk-checkpoint-10 / completed-sdk-checkpoint',
            'started_at': '2026-10-24T10:56:00Z'}
        f.jobs = [f.collector, f.issuer, self.collector, self.current, deepcopy(c.issued.job)]
        f.artifacts[996] = f.artifact(996,
            f'codex-agent-sdk-wave-10-state-{f.producer["tree"]}-attempt-{f.producer["runAttempt"]}',
            self.source['artifactSha256'], self.source['artifactBytes'], '10:50:00')
        c.workflow += (b'\n  sdk-checkpoint-10:\n    needs: [sdk-checkpoint-9, sdk-collect-10]\n'
            b'    uses: codex-agent-labs/codex-agent/.github/workflows/reuse-qualification.yml@reuse-authority\n')
        self.controls = deepcopy(c.issued.fixture.controls)
        self.references = deepcopy(c.issued.fixture.references)
        self.reads = []; self.number = 0; self.tamper = False

    def add_new(self):
        f = self.f
        receipt = deepcopy(self.fixture.issued.receipt)
        receipt.update(component='cpp')
        receipt['buildKey'] = compute_build_key(**{key: receipt[key] for key in (*completed.IDENTITY, 'inputs')})
        stage = f.root / 'third-stage'; (stage / 'outputs').mkdir(parents=True)
        (stage / 'outputs/value').write_bytes(b'one additional fully verified synthetic SDK object')
        write_output_manifest(stage, 'sdk', 'cpp', 'package', 'desktop', '0.2.0', {'evidence': 'outputs'})
        obj = finalize_phase_object(stage_root=stage, phase_plan={key: receipt[key] for key in PHASE_PLAN_KEYS},
            producer=f.producer, product_version='0.2.0', trust_domain='development', destination=f.root/'third')
        self.object = obj; self.body = (f.root / 'third' / obj['objectPath']).read_bytes()
        row = {**{key: obj['receipt'][key] for key in completed.IDENTITY},
            **{key: obj[key] for key in completed.OBJECT}, 'objectPath': obj['objectPath']}
        request = self.controls['runtime-state/reuse-wave-request.json']
        request['availableObjects'].append(row)
        request['phaseAuthorities'].append({**{key: row[key] for key in completed.IDENTITY},
            **{key: receipt['inputs'][key] for key in ('flagsDigest', 'toolchainProfileDigest', 'outputSchemaVersion')}})
        self.controls['runtime-state/reuse-wave-result.json']['phases'].append({**row, 'state': 'retained'})
        self.controls['runtime-state/original/cpp/phase-receipt.json'] = obj['receipt']
        name, artifact = fresh_sdk_worker_route(completed._identity(receipt), obj['receipt'])
        f.jobs.append({**self.fixture.issued.job, 'id': 447, 'name': name,
            'started_at': '2026-10-24T10:41:00Z', 'completed_at': '2026-10-24T10:44:00Z'})
        f.artifacts[446] = f.artifact(446, artifact, sha256_bytes(b'third upload'), len(self.body)+1000, '10:43:00')
        self.bind()

    def bind(self):
        # Preserve the original object declaration; replace only small control pins.
        inventory = [row for row in self.references['inventory'] if row['relativePath'] not in self.controls]
        for path, value in self.controls.items():
            if path.startswith('held-python/'):
                continue
            raw = value.encode() if path == completed.SOURCE_PLAN else canonical_json_bytes(value)
            inventory.append({'relativePath': path, 'bytes': len(raw), 'sha256': sha256_bytes(raw)})
        self.references['inventory'] = sorted(inventory, key=lambda row: row['relativePath'])
        first = self.references['inventory'][0]
        self.references['references'] = [{**first, 'sourcePath': first['relativePath']}]
        self.source['referenceControlSha256'] = sha256_bytes(canonical_json_bytes(self.references))

    @contextmanager
    def boundaries(self):
        c, f = self.fixture, self.f
        with c.boundaries(), ExitStack() as stack:
            api = f.api
            def listing(url, token):
                if url.endswith('/artifacts?per_page=100&page=1'):
                    f.urls.append(url)
                    return json.dumps({'artifacts': list(f.artifacts.values())}).encode()
                return api(url, token)
            stack.enter_context(patch.object(reuse, 'api_request', side_effect=listing))
            stack.enter_context(patch('sdk_handoff._ensure_observed_sdk_commit'))
            stack.enter_context(patch.object(products, '_validate_plan', return_value={}))
            stack.enter_context(patch.object(completed, '_inventory_revision', return_value=f.producer['commit']))
            stack.enter_context(patch.object(completed, 'validate_current'))
            stack.enter_context(patch.object(completed, '_base', return_value=c.issued.fixture.base))
            stack.enter_context(patch.object(native, '_sdk_parent_frozen_spec', return_value=c.issued.fixture.base))
            parent_sdk = deepcopy(c.issued.fixture.parent_sdk)
            parent_sdk['proof'] = deepcopy(f.envelope['completion']['parentProof'])
            stack.enter_context(patch.object(native, '_validate_completed_sdk', return_value=parent_sdk))
            self.bootstrap = stack.enter_context(patch.object(native, '_fetch_completed_sdk', side_effect=AssertionError('recursive bootstrap fetch')))
            collected = {'controls': self.controls, 'references': self.references, 'controlArchive': {'bytes': 4096},
                'stateLocator': products._runtime_original_locator(f.artifacts[996], self.source['workflowSha'],
                    completed.PhaseInstanceId('sdk', 'javascript', 'metadata', 'node'), self.collector)}
            stack.enter_context(patch.object(completed, 'fetch_collector_controls', return_value=collected))
            stack.enter_context(patch.object(completed, '_contract_files'))
            actual_original, actual_source = completed.observe_original, completed.observe_source
            def original(pin, receipt, token, **kwargs):
                if receipt['component'] == 'csharp':
                    self.assertEqual(c.issued.old_locator, kwargs['native_locator'])
                    return {}, [], c.issued.old_locator
                self.assertIn('_fresh_observation', kwargs)
                self.assertNotIn('native_locator', kwargs)
                return actual_original(pin, receipt, token, **kwargs)
            self.originals = stack.enter_context(patch.object(completed, 'observe_original', side_effect=original))
            def source(pin, token, **kwargs):
                if kwargs.get('contract'):
                    return {'name': 'contract'}, [{'run': {}}], f.envelope['completion']['contractSource']
                return actual_source(pin, token, **kwargs)
            stack.enter_context(patch.object(completed, 'observe_source', side_effect=source))
            def download(*args, destination, **kwargs):
                with zipfile.ZipFile(destination, 'w') as archive:
                    for row in f.spec['contractFiles']:
                        archive.writestr(row['relativePath'], b'{}')
            stack.enter_context(patch.object(products, '_download_contract_ci_upload', side_effect=download))
            @contextmanager
            def member(artifact, token, **kwargs):
                self.assertEqual(446, artifact['id'], 'old bodies must never open')
                self.reads.append(446)
                stream = io.BytesIO()
                with zipfile.ZipFile(stream, 'w') as archive:
                    archive.writestr('shard/'+self.object['objectPath'], self.body+(b'tamper' if self.tamper else b''))
                with zipfile.ZipFile(io.BytesIO(stream.getvalue())) as archive:
                    yield archive, SimpleNamespace(transferred=len(stream.getvalue()))
            stack.enter_context(patch('runtime_reference_archive.open_reference_archive', side_effect=member))
            yield

    def issue(self):
        self.number += 1; work = self.f.root / ('chain-'+str(self.number))
        with self.boundaries():
            report = completed.issue_checkpoint(self.f.policy, self.source, {'artifactId': 998,
                'artifactSha256': sha256_bytes(b'control ten')}, work, root=self.f.root,
                revision=self.f.policy['issuerCommit'], frozen=self.fixture.issued.fixture.base,
                token='synthetic', previous=self.fixture.output)
        return report, work

    def test_second_issuance_authenticates_one_flat_predecessor_and_only_new_body(self):
        self.add_new(); before = canonical_json_bytes(self.f.envelope)
        report, work = self.issue()
        self.assertEqual([446], self.reads)
        self.assertEqual([990], self.f.downloads)
        self.assertEqual(1, len(self.f.verified)); self.bootstrap.assert_not_called()
        self.assertEqual(len(self.body), report['verifiedObjectBytes'])
        self.assertEqual(37+len(self.fixture.issued.body), report['reusedObjectBytes'])
        self.assertEqual(1, sum('/actions/artifacts/445' in url for url in self.f.urls))
        envelope = json.loads((work/'completion.json').read_bytes())
        self.assertNotIn('reuseCompletion', envelope['recipe'])
        self.assertNotIn('reuseCompletionProofSha256', envelope['recipe'])
        self.assertEqual({'native': self.fixture.output['native'], 'subjectSha256': self.fixture.output['subjectSha256']},
            envelope['precedingCheckpoint'])
        self.assertNotEqual(sha256_bytes(canonical_json_bytes(self.f.envelope['completion'])),
            envelope['precedingCheckpoint']['subjectSha256'])
        self.assertEqual(before, canonical_json_bytes(self.f.envelope))
        self.assertEqual(3, len(envelope['completion']['members']))
        earlier = {completed._identity(row): i for i, row in enumerate(self.f.spec['completedPhases'])}
        for i, row in enumerate(envelope['recipe']['completedPhases']):
            if completed._identity(row) in earlier:
                old = earlier[completed._identity(row)]
                for field in ('members', 'originals'):
                    self.assertEqual(self.f.envelope['completion'][field][old], envelope['completion'][field][i])

    def test_noop_forwards_exact_authenticated_outer_selector_without_new_subject(self):
        report, work = self.issue()
        self.assertEqual(self.fixture.output, report['reusedCheckpointOutput'])
        self.assertEqual([], self.reads); self.assertEqual([990], self.f.downloads)
        self.assertEqual(0, report['verifiedObjectBytes'])
        self.assertFalse((work/'completion.json').exists()); self.bootstrap.assert_not_called()

    def test_wrong_actual_edge_source_subject_and_old_tuple_fail_without_body(self):
        saved = deepcopy((self.fixture.workflow, self.current, self.fixture.output, self.controls))
        for case in ('edge', 'role', 'subject', 'old-tuple'):
            with self.subTest(case=case):
                self.fixture.workflow, current, self.fixture.output, self.controls = deepcopy(saved)
                self.current.clear(); self.current.update(current)
                if case == 'edge': self.fixture.workflow = self.fixture.workflow.replace(b'[sdk-checkpoint-9, sdk-collect-10]', b'[sdk-collect-10]')
                elif case == 'role': self.current['name'] = 'unrelated job'
                elif case == 'subject': self.fixture.output['subjectSha256'] = sha256_bytes(b'wrong outer')
                else:
                    self.controls['runtime-state/reuse-wave-request.json']['availableObjects'][-1]['objectSha256'] = sha256_bytes(b'wrong old tuple')
                    self.bind()
                with self.assertRaises(ValueError): self.issue()
                self.assertEqual([], self.reads)

    def test_new_body_tampering_still_prevents_second_completion(self):
        self.add_new(); self.tamper = True
        with self.assertRaises(ValueError): self.issue()
        self.assertEqual([446], self.reads)
        self.assertFalse((self.f.root/'chain-1/completion.json').exists())

    def test_inheritance_requires_semantic_join_exact_inner_proof_and_active_next_job(self):
        f=self.f
        spec={**deepcopy(f.spec),'source':self.source}
        spec.pop('reuseCompletion');spec.pop('reuseCompletionProofSha256')
        with self.boundaries(),completed.checkpoint_consumer(f.policy,self.fixture.output,f.root/'private',
                root=f.root,consumer=self.fixture.consumer,job='sdk-checkpoint-10',token='synthetic',
                _next_source=self.source) as witness:
            unvalidated={**deepcopy(self.fixture.issued.fixture.parent_sdk),
                'extension':{'spec':f.spec,'proof':f.envelope['completion']}}
            with self.assertRaisesRegex(ValueError,'authenticated inner'):witness.inherit(spec,unvalidated)
            prior=witness.validate(root=f.root,revision=None,frozen=self.fixture.issued.fixture.base,
                consumer_revision=f.producer['commit'],token='synthetic')
            witness.inherit(spec,prior)
            self.assertEqual(f.policy['bootstrap'],witness.bootstrap())
            with self.assertRaisesRegex(ValueError,'another observation token'):witness.check(token='wrong')
            for key in ('members','originals','controls'):
                changed=deepcopy(prior);changed['extension']['proof'][key]=[]
                with self.subTest(key=key),self.assertRaisesRegex(ValueError,'authenticated inner'):
                    witness.inherit(spec,changed)
            changed=deepcopy(spec);changed['source']['artifactId']+=1
            with self.assertRaisesRegex(ValueError,'authenticated inner'):witness.inherit(changed,prior)
        with self.assertRaisesRegex(ValueError,'closed'):witness.inherit(spec,prior)

    def test_actual_second_issuer_workflow_has_both_required_edges(self):
        workflow=Path(__file__).resolve().parents[2]/'.github/workflows/product-validation.yml'
        raw=workflow.read_bytes()
        check=lambda value:completed._checkpoint_workflow_edges(value,'sdk-collect-9','sdk-checkpoint-9',
            'sdk-checkpoint-10',next_collector='sdk-collect-10')
        self.assertEqual(sha256_bytes(raw),check(raw))
        for before,after in [(b'[plan, sdk-collect-10, sdk-checkpoint-9]',b'[plan, sdk-collect-10]'),
                             (b'[plan, sdk-collect-10, sdk-checkpoint-9]',b'[plan, sdk-checkpoint-9]')]:
            with self.assertRaises(ValueError):check(raw.replace(before,after))

    def test_latest_flat_wrapper_custody_requires_no_previous_archive(self):
        self.add_new(); _,work=self.issue();f=self.f
        envelope=json.loads((work/'completion.json').read_bytes())
        f.envelope=envelope;f.spec=envelope['recipe'];f.source=f.spec['source'];f.collector=self.collector
        f.issuer=self.current;f.issuer.update(status='completed',conclusion='success',completed_at='2026-10-24T11:00:00Z')
        f.identity=completed.checkpoint_archive_identity(f.policy,f.source,signer_commit=f.policy['issuerCommit'],
            source_commit=f.producer['commit'],run_id=f.producer['runId'],run_attempt=f.producer['runAttempt'])
        selector={**f.selector,'artifactId':1990}
        f.artifacts[998]=f.artifact(998,completed.collector_control_artifact_name(f.source),
            envelope['sourceCheckpoint']['controlArtifact']['artifactSha256'],1000,'10:52:00')
        def upload():
            f.subject=canonical_json_bytes(f.envelope);stream=io.BytesIO()
            with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('completion.json',f.subject);archive.writestr('bundle.jsonl',b'explicit native crypto fixture')
            f.raw=stream.getvalue();selector['artifactSha256']=sha256_bytes(f.raw)
            f.artifacts[1990]=f.artifact(1990,f.identity['artifactName'],selector['artifactSha256'],len(f.raw),'10:58:00')
        def download(artifact,token):
            self.assertEqual(1990,artifact['id']);f.downloads.append(artifact['id']);return f.raw
        def fetch(number):
            upload()
            with self.fixture.boundaries(),patch.object(products,'download_artifact',side_effect=download):
                return completed.fetch_checkpoint_envelope(f.policy,f.source,selector,f.root/('flat-'+str(number)),token='synthetic')
        f.downloads.clear();f.verified.clear()
        custody=fetch(0)
        self.assertFalse(custody['semanticAuthority'])
        self.assertEqual(envelope,custody['envelope'])
        self.assertEqual([1990],f.downloads);self.assertEqual(1,len(f.verified))
        for number,case in enumerate(('attempt-type','campaign','self-pointer','legacy-inner-hash'),1):
            f.envelope=deepcopy(envelope)
            if case=='attempt-type':f.envelope['precedingCheckpoint']['native']['runAttempt']=True
            elif case=='campaign':f.envelope['precedingCheckpoint']['native']['runId']+=1
            elif case=='self-pointer':f.envelope['precedingCheckpoint']['native']['artifactId']=1990
            else:
                f.envelope['recipe']['reuseCompletion']=f.envelope['precedingCheckpoint']['native']
                f.envelope['recipe']['reuseCompletionProofSha256']=f.envelope['precedingCheckpoint']['subjectSha256']
                f.envelope['completion']['specSha256']=sha256_bytes(canonical_json_bytes(f.envelope['recipe']))
            with self.subTest(case=case),self.assertRaises(ValueError):fetch(number)


if __name__ == '__main__': unittest.main()
