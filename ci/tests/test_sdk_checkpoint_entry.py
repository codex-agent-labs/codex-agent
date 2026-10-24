"""Protected job entry/output boundaries; core/native issuance is an explicit seam."""
from contextlib import ExitStack
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import completed_sdk_reuse as completed
import reuse_qualification as native
from products.inventory import canonical_json_bytes, sha256_bytes
from ci.tests.test_sdk_checkpoint_issuer import SdkCheckpointIssuerTest


class SdkCheckpointEntryTest(unittest.TestCase):
    def setUp(self):
        self.fixture = SdkCheckpointIssuerTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        f = self.fixture
        self.root = f.root
        self.owner = self.root / 'owner.json'
        self.owner.write_bytes(canonical_json_bytes(f.policy))
        self.frozen = self.root / 'frozen.json'
        self.frozen.write_bytes(canonical_json_bytes(f.fixture.base))
        self.output = self.root / 'github-output'
        self.selectors = json.dumps({'source':f.fixture.source,'controlArtifact':f.control_selector})
        self.env = {'QUALIFICATION_ISSUER_SHA':f.policy['issuerCommit'],
            'QUALIFICATION_ISSUER_REPOSITORY':native.REPOSITORY,'QUALIFICATION_ISSUER_PATH':native.ISSUER_WORKFLOW,
            'CODEX_AGENT_CHECKPOINT_OWNER_POLICY':str(self.owner),'GITHUB_REPOSITORY':native.REPOSITORY,
            'GITHUB_EVENT_NAME':'pull_request','GITHUB_REF':'refs/pull/31/merge','GITHUB_SHA':f.producer['commit'],
            'GITHUB_RUN_ID':str(f.producer['runId']),'GITHUB_RUN_ATTEMPT':str(f.producer['runAttempt']),
            'GITHUB_JOB':'completed-sdk-checkpoint','GITHUB_OUTPUT':str(self.output)}
        self.noop=False;self.change_owner=False

    def engine(self,policy,source,control,work,**kw):
        self.assertEqual(self.fixture.policy,policy)
        self.assertEqual(self.fixture.fixture.source,source)
        self.assertEqual(self.fixture.control_selector,control)
        self.assertEqual(self.fixture.fixture.base,kw['frozen'])
        self.assertEqual(policy['issuerCommit'],kw['revision'])
        self.assertEqual(self.root,kw['root'])
        work=Path(work);work.mkdir()
        if self.change_owner:self.owner.write_bytes(canonical_json_bytes({**policy,'issuerCommit':'e'*40}))
        if self.noop:
            return {'reusedCheckpoint':policy['bootstrap'],'reusedCheckpointSubjectSha256':policy['bootstrapProofSha256']}
        # Not a valid native proof: this fixture tests protected entry/output only.
        (work/'completion.json').write_bytes(canonical_json_bytes({'native':'issuer core seam'}))
        return {'checkpointArtifactName':'sdk-completed-checkpoint-fixture'}

    def issue(self,*,environment=None,selectors=None,preceding_selector=""):
        work=self.root/'issued'
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ,environment or self.env,clear=True))
            stack.enter_context(patch.object(native,'__file__',str(self.root/'ci/reuse_qualification.py')))
            stack.enter_context(patch.object(native.subprocess,'check_output',return_value=self.fixture.policy['issuerCommit']+'\n'))
            self.compatible=stack.enter_context(patch.object(native,'_compatible_verifier',return_value=True))
            stack.enter_context(patch.object(native,'_frozen_spec_path',return_value='frozen.json'))
            stack.enter_context(patch('products.inventory.git_regular_blob_bytes',return_value=canonical_json_bytes(self.fixture.fixture.base)))
            self.core=stack.enter_context(patch.object(completed,'issue_checkpoint',side_effect=self.engine))
            native.issue_sdk_checkpoint(work,self.selectors if selectors is None else selectors,'fixture-token',
                preceding_selector=preceding_selector)
        return work

    def test_approved_entry_and_uploaded_selector_preserve_exact_source(self):
        work=self.issue()
        self.core.assert_called_once();self.compatible.assert_called_once()
        self.assertIn('issue=true\n',self.output.read_text())
        result=native.sdk_checkpoint_job_output(work,'321','a'*64,str(self.output))
        self.assertEqual('sdk-checkpoint',result['kind'])
        self.assertEqual(self.fixture.fixture.source,result['source'])
        self.assertEqual(321,result['native']['artifactId'])
        self.assertEqual(self.fixture.producer['commit'],result['native']['sourceCommit'])
        self.assertEqual(sha256_bytes((work/'completion.json').read_bytes()),result['subjectSha256'])
        (work/'completion.json').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'subject changed'):
            native.sdk_checkpoint_job_output(work,'321','a'*64,self.output)

    def test_unchanged_entry_exports_exact_prior_and_rejects_new_upload(self):
        self.noop=True;work=self.issue()
        self.assertFalse((work/'completion.json').exists())
        self.assertIn('issue=false\n',self.output.read_text())
        result=native.sdk_checkpoint_job_output(work,'','',self.output)
        self.assertEqual({'kind':'existing-sdk-completion','native':self.fixture.policy['bootstrap'],
            'subjectSha256':self.fixture.policy['bootstrapProofSha256']},result)
        with self.assertRaisesRegex(ValueError,'another upload'):
            native.sdk_checkpoint_job_output(work,'321','a'*64,self.output)

    def test_wrong_issuer_or_attempt_never_reaches_core(self):
        faults={'QUALIFICATION_ISSUER_REPOSITORY':'fork/repo','QUALIFICATION_ISSUER_PATH':'.github/workflows/other.yml',
            'QUALIFICATION_ISSUER_SHA':'e'*40,'GITHUB_REPOSITORY':'fork/repo','GITHUB_EVENT_NAME':'workflow_dispatch',
            'GITHUB_REF':'refs/pull/32/merge','GITHUB_SHA':'e'*40,'GITHUB_RUN_ID':'2','GITHUB_RUN_ATTEMPT':'99',
            'GITHUB_JOB':'other-job'}
        for field,value in faults.items():
            with self.subTest(field=field),self.assertRaises(ValueError):self.issue(environment={**self.env,field:value})
            self.core.assert_not_called()
        bad=deepcopy(self.fixture.policy);bad['issuerCommit']='e'*40
        self.owner.write_bytes(canonical_json_bytes(bad))
        with self.assertRaisesRegex(ValueError,'not approved'):self.issue()
        self.core.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_mutated_policy_or_untrusted_selector_policy_cannot_publish(self):
        raw=json.loads(self.selectors);raw['ownerPolicy']=self.fixture.policy
        with self.assertRaises(ValueError):self.issue(selectors=json.dumps(raw))
        self.core.assert_not_called()
        self.change_owner=True
        with self.assertRaisesRegex(ValueError,'policy changed'):self.issue()
        self.assertFalse(self.output.exists())
        self.assertFalse((self.root/'issued/checkpoint-issue.json').exists())

    def test_dynamic_noop_preserves_exact_previous_selector_without_upload(self):
        f=self.fixture
        previous={'kind':'sdk-checkpoint','source':f.fixture.source,
            'subjectSha256':sha256_bytes(b'previous outer subject'),
            'native':{'artifactId':77,'artifactSha256':sha256_bytes(b'previous upload'),
                'runId':f.producer['runId'],'runAttempt':f.producer['runAttempt'],
                'signerCommit':f.policy['issuerCommit'],'sourceCommit':f.producer['commit']}}
        def engine(policy,source,control,work,**kw):
            self.assertEqual(previous,kw['previous']);Path(work).mkdir()
            return {'reusedCheckpoint':previous['native'],'reusedCheckpointSubjectSha256':previous['subjectSha256'],
                'reusedCheckpointOutput':previous}
        self.engine=engine
        work=self.issue(preceding_selector=json.dumps(previous))
        self.assertIn('issue=false\n',self.output.read_text())
        self.assertEqual(previous,native.sdk_checkpoint_job_output(work,'','',self.output))
        with self.assertRaisesRegex(ValueError,'another upload'):
            native.sdk_checkpoint_job_output(work,'88','b'*64,self.output)

    def test_explicit_invalid_previous_selector_never_falls_back(self):
        for text in ('null','{}','x'*16385):
            with self.subTest(text=text[:20]),self.assertRaises(ValueError):self.issue(preceding_selector=text)
            self.core.assert_not_called()



class CheckpointWorkflowPermissionsTest(unittest.TestCase):
    def test_native_issuer_permissions_cross_every_existing_caller_edge(self):
        import re
        workflows = Path(__file__).resolve().parents[2] / '.github/workflows'
        sources = {name: (workflows / (name + '.yml')).read_text() for name in (
            'ci', 'product-validation', 'sdk-core-binary-validation',
            'sdk-core-package-validation', 'reuse-qualification', 'portable-reuse-proof')}
        def job(workflow, name):
            match = re.search(r'^  ' + re.escape(name) + r':\n(.*?)(?=^  [A-Za-z_][A-Za-z0-9_-]*:|\Z)',
                              sources[workflow], re.M | re.S)
            self.assertIsNotNone(match, (workflow, name))
            return match.group(1)
        signing = {'contents': 'read', 'actions': 'read', 'id-token': 'write', 'attestations': 'write'}
        for workflow, names in (
            ('ci', ('product-validation',)),
            ('product-validation', ('sdk-checkpoint-9', 'sdk-checkpoint-10', 'sdk-core-binary-wave')),
            ('sdk-core-binary-validation', ('sdk-checkpoint-11',)),
            ('reuse-qualification', ('qualify', 'completed-sdk', 'completed-sdk-checkpoint')),
            ('portable-reuse-proof', ('cold', 'completion')),
        ):
            for name in names:
                with self.subTest(workflow=workflow, job=name):
                    block = re.search(r'^    permissions:\n((?:^      [a-z-]+: (?:read|write|none)\n)+)',
                                      job(workflow, name), re.M)
                    self.assertIsNotNone(block)
                    actual = dict(re.findall(r'^      ([a-z-]+): (read|write|none)$', block.group(1), re.M))
                    expected = dict(signing, deployments='read') if workflow == 'ci' else signing
                    self.assertEqual(expected, actual)
        # Core package consumes the forwarded checkpoint; it has no native issuer yet.
        package = sources['sdk-core-package-validation']
        self.assertNotIn('uses: codex-agent-labs/codex-agent/.github/workflows/reuse-qualification.yml', package)
        self.assertIn('CODEX_AGENT_SDK_CHECKPOINT: ${{ fromJSON(inputs.binaryWave).outputs.checkpoint }}', package)
        self.assertNotIn('attestations:', job('product-validation', 'sdk-core-package-wave'))
        top = sources['ci'].split('\npermissions:\n', 1)[1].split('\nconcurrency:', 1)[0]
        self.assertEqual({'actions': 'read', 'contents': 'read'},
                         dict(re.findall(r'^  ([a-z-]+): (read|write|none)$', top, re.M)))


if __name__=='__main__':unittest.main()
