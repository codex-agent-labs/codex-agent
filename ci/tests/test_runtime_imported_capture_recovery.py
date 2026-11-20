"""Mocked metadata-only capture reuse; no hosted, cryptographic or product evidence."""
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from ci import runtime_phase10_library_caller as caller
from products.inventory import canonical_json_bytes, sha256_bytes
from products.registry import NATIVE_TARGETS

class ImportedCaptureRecoveryTest(unittest.TestCase):
    def setUp(self):
        digest='sha256:'+'a'*64
        prior=dict(schemaVersion=2,kind='sdk-runtime-library-imported-validation',trustedSourceCommit='3'*40,
            inputManifestSha256=digest,inputManifestBytes=123,custodyCheckpointSha256=digest,
            aggregateBuildKey=digest,metadataReceiptSha256=digest,aggregateManifestSha256=digest,
            contractDigest=digest,sourceTrustDomain='development',rootDelegationInventorySha256=digest,
            libraries=[dict(target=t,componentId=digest,runtimeLibrarySha256=digest,bundleSha256=digest,manifestSha256=digest) for t in sorted(NATIVE_TARGETS)])
        producer=dict(commit='1'*40,tree='2'*40,event='workflow_dispatch',repository='codex-agent-labs/codex-agent',
            runId=123,runAttempt=1,pullRequest=None,workflowPath='.github/workflows/ci.yml')
        original=dict(producer=producer,workflowSha='3'*40,jobId=456,artifactId=789,
            artifactSha256=digest,artifactBytes=1234,controlSha256=sha256_bytes(canonical_json_bytes(prior)),control=prior)
        self.control=dict(prior,trustedSourceCommit='4'*40,originalCapture=original)
        self.job='sdk-runtime-library-validation / runtime-library-imported-original-capture'
        self.observed=[dict(run={'id':123,'run_attempt':1},jobs=[dict(id=456,run_attempt=1,run_id=123,name=self.job)])]

    def validate(self,value):
        raw=canonical_json_bytes(value)
        return caller.validate_imported_validation_control(raw,expected_sha256=sha256_bytes(raw),trusted_source_commit=value['trustedSourceCommit'])

    def test_initial_and_recovery_controls_keep_exact_content_and_original_producer(self):
        before=copy.deepcopy(self.control)
        self.assertEqual(before,self.validate(self.control))
        self.assertEqual(before['originalCapture']['control'],self.validate(before['originalCapture']['control']))
        self.assertEqual(before,self.control)

    def test_original_identity_and_content_changes_are_rejected(self):
        for field,value in [('inputManifestSha256','sha256:'+'b'*64),('inputManifestBytes',124),
                            ('contractDigest','sha256:'+'b'*64),('rootDelegationInventorySha256','sha256:'+'b'*64)]:
            with self.subTest(field=field):
                changed=copy.deepcopy(self.control);changed[field]=value
                with self.assertRaisesRegex(ValueError,'exact imported content'):self.validate(changed)
        changed=copy.deepcopy(self.control);changed['originalCapture']['controlSha256']='sha256:'+'b'*64
        with self.assertRaisesRegex(ValueError,'independent pin'):self.validate(changed)
        changed=copy.deepcopy(self.control);changed['originalCapture']['control']['originalCapture']={}
        with self.assertRaisesRegex(ValueError,'initial capture directly'):self.validate(changed)
        changed=copy.deepcopy(self.control);changed['originalCapture']['producer']['event']='pull_request';changed['originalCapture']['producer']['pullRequest']=31
        with self.assertRaisesRegex(ValueError,'producer scope'):self.validate(changed)

    def test_exact_successful_original_is_forwarded_without_body_download(self):
        before=copy.deepcopy(self.control);artifact=dict(size_in_bytes=1234,id=789)
        with patch('product_reuse._observe_ci_producer_jobs',return_value=self.observed) as observe, \
             patch('product_reuse._contract_ci_upload_metadata',return_value=artifact) as metadata, \
             patch('product_reuse._require_artifact_job_window') as window, \
             patch('product_reuse._download_contract_ci_upload_bytes') as download:
            result=caller._recover_imported_validation_capture(self.validate(self.control),'observation-token')
        self.assertEqual(before['originalCapture'],result['originalCapture'])
        self.assertEqual(before,self.control);self.assertEqual(0,result['downloadedBytes'])
        download.assert_not_called();window.assert_called_once_with(self.observed[0],self.job,artifact)
        self.assertEqual({'capture':before['originalCapture']['producer']},observe.call_args.args[0])
        self.assertEqual('3'*40,observe.call_args.kwargs['trusted_workflows_by_phase']['capture']['sha'])
        metadata.assert_called_once_with(789,'sha256:'+'a'*64,'runtime-imported-validation-inputs-123-1',before['originalCapture']['producer'],self.observed[0]['run'],'observation-token')

    def test_wrong_original_job_attempt_or_size_fails(self):
        for job_field,value in [('id',999),('run_attempt',2),('run_id',999)]:
            observed=copy.deepcopy(self.observed);observed[0]['jobs'][0][job_field]=value
            with self.subTest(job_field=job_field),patch('product_reuse._observe_ci_producer_jobs',return_value=observed),self.assertRaisesRegex(ValueError,'job/attempt'):
                caller._recover_imported_validation_capture(self.validate(self.control),'token')
        with patch('product_reuse._observe_ci_producer_jobs',return_value=self.observed),patch('product_reuse._contract_ci_upload_metadata',return_value={'size_in_bytes':999}),self.assertRaisesRegex(ValueError,'size differs'):
            caller._recover_imported_validation_capture(self.validate(self.control),'token')

    def test_capture_route_creates_no_storage_or_capture_and_never_calls_lfs(self):
        with tempfile.TemporaryDirectory() as temporary,patch.dict(os.environ,{'GH_TOKEN':'token'},clear=True):
            root=Path(temporary).resolve();control=root/'control.json';raw=canonical_json_bytes(self.control);control.write_bytes(raw)
            with patch.object(caller,'_recover_imported_validation_capture',return_value={'originalCapture':self.control['originalCapture'],'downloadedBytes':0}) as recover,patch.object(caller,'_imported_lfs_batch') as lfs:
                result=caller.capture_imported_validation_objects(control,root/'capture',root/'cache',expected_control_sha256=sha256_bytes(raw),trusted_source_commit='4'*40)
            recover.assert_called_once();lfs.assert_not_called();self.assertFalse((root/'capture').exists());self.assertFalse((root/'cache').exists())
            self.assertEqual(0,result['downloadedBytes'])

    def test_recovery_remains_token_only_and_rejects_missing_token(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve();control=root/'control.json';raw=canonical_json_bytes(self.control);control.write_bytes(raw)
            for env in ({},{'GH_TOKEN':'token','RELEASE_PRIVATE_KEY':'forbidden'}):
                with self.subTest(env=list(env)),patch.dict(os.environ,env,clear=True),patch.object(caller,'_recover_imported_validation_capture') as recover,self.assertRaises(ValueError):
                    caller.capture_imported_validation_objects(control,root/'capture',root/'cache',expected_control_sha256=sha256_bytes(raw),trusted_source_commit='4'*40)
                recover.assert_not_called()

    def test_workflow_download_token_is_scoped_and_recovery_skips_upload(self):
        workflow=(Path(__file__).resolve().parents[2]/'.github/workflows/runtime-library-authorizations.yml').read_text()
        capture=workflow.split('  capture-imported:',1)[1].split('  authorize-imported:',1)[0]
        self.assertIn("if: steps.intake.outputs.artifact_id == ''",capture)
        self.assertIn('steps.intake.outputs.artifact_run_id || github.run_id',capture)
        authorize=workflow.split('  authorize-imported:',1)[1]
        download=authorize.split('      - name: Receive the authenticated original unique object capture',1)[1].split('      - name:',1)[0]
        self.assertIn('run-id: ${{ needs.capture-imported.outputs.artifact_run_id }}',download)
        self.assertIn('github-token: ${{ github.token }}',download)
        signing=authorize.split('      - name: Verify all original source and content gates',1)[1]
        self.assertNotIn('github-token:',signing);self.assertNotIn('GH_TOKEN:',signing)

if __name__=='__main__':unittest.main()
