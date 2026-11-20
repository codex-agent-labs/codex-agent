"""Retained replay context stays distinct from a current collector's transport."""
from copy import deepcopy
import unittest

import completed_sdk_reuse as completed
from products.inventory import canonical_json_bytes
from ci.tests.test_collector_controls import CollectorControlsTest
from ci.tests.test_collector_receipt_publication import CollectorReceiptPublicationTest
from ci.tests.test_completed_sdk_reuse import CompletedSdkControlsTest
from ci.tests.test_prepare_sdk_completion import PrepareSdkCompletionTest


class CheckpointRetainedStateTest(unittest.TestCase):
    def current_transport(self, fixture):
        fixture.producer={**fixture.producer,'runAttempt':fixture.producer['runAttempt']+1}
        fixture.source={**fixture.source,'producer':fixture.producer}
        fixture.run['run_attempt']=fixture.producer['runAttempt']
        fixture.artifacts[700]['name']='codex-agent-sdk-wave-9-state-'+fixture.producer['tree']+'-attempt-'+str(fixture.producer['runAttempt'])

    def test_current_control_upload_preserves_earlier_state_and_exact_receipts(self):
        f=CollectorControlsTest();f.setUp();self.addCleanup(f.doCleanups)
        retained=canonical_json_bytes([f.controls,f.references])
        state_producer=deepcopy(f.producer)
        self.current_transport(f)
        result=f.fetch()
        self.assertEqual(retained,canonical_json_bytes([result['controls'],result['references']]))
        self.assertEqual(state_producer,result['controls']['runtime-state/producer.json'])
        self.assertEqual(f.producer,result['source']['producer'])
        self.assertEqual([701],f.downloads)
        self.assertFalse(any('/attempts/'+str(state_producer['runAttempt'])+'/' in url for url in f.urls))
        self.assertEqual(1,sum('/actions/artifacts/700' in url for url in f.urls))
        self.assertEqual(1,sum('/actions/artifacts/701' in url for url in f.urls))
        artifact,job=deepcopy(f.artifacts[700]),deepcopy(f.job)
        for fault in ('expired','old-upload','failed-collector'):
            try:
                if fault=='expired':f.artifacts[700]['expired']=True
                elif fault=='old-upload':f.artifacts[700]['name']=f.artifacts[700]['name'].rsplit('-',1)[0]+'-'+str(state_producer['runAttempt'])
                else:f.job['conclusion']='failure'
                with self.subTest(fault=fault),self.assertRaises(ValueError):f.fetch()
            finally:f.artifacts[700],f.job=deepcopy(artifact),deepcopy(job)
        for field,value in (('runAttempt',f.producer['runAttempt']+1),('runId',f.producer['runId']+1),
                ('commit','e'*40),('tree','e'*40),('pullRequest',32)):
            with self.subTest(field=field):
                changed=deepcopy(f.controls);changed['runtime-state/producer.json'][field]=value
                with self.assertRaisesRegex(ValueError,'current workflow run or earlier attempt'):
                    completed.prepare_collector_controls(f.source,f.reference_bytes,changed)
        self.assertEqual(retained,canonical_json_bytes([f.controls,f.references]))

    def test_real_exporter_selects_current_upload_without_relabeling_held_state(self):
        f=CollectorReceiptPublicationTest();f.setUp();self.addCleanup(f.doCleanups)
        original=canonical_json_bytes(f.fixture.controls)
        self.current_transport(f.fixture)
        # Existing real exporter/CLI check retains all exact source/output checks,
        # now with an independently observed current-attempt upload.
        f.test_post_upload_cli_publishes_only_small_controls_and_explicit_name()
        self.assertEqual(original,canonical_json_bytes(f.fixture.controls))
        self.assertEqual(f.fixture.producer['runAttempt']-1,
            f.fixture.controls['runtime-state/producer.json']['runAttempt'])

    def test_collected_recipe_allows_only_same_run_earlier_context_and_legacy_stays_exact(self):
        f=PrepareSdkCompletionTest();f.setUp();self.addCleanup(f.doCleanups)
        original=canonical_json_bytes(f.controls)
        f.source={**f.source,'producer':{**f.producer,'runAttempt':f.producer['runAttempt']+1}}
        spec,controls,report=f.run_prepare()
        self.assertEqual(original,canonical_json_bytes(f.controls))
        self.assertEqual(f.producer,controls['runtime-state/producer.json'])
        self.assertNotEqual(f.producer,spec['source']['producer'])
        self.assertEqual(1,report['inheritedSdkObjects'])
        for field,value in (('runAttempt',f.producer['runAttempt']-1),('runId',f.producer['runId']+1)):
            old=deepcopy(f.source)
            try:
                f.source['producer'][field]=value
                with self.subTest(field=field),self.assertRaises(ValueError):f.run_prepare()
            finally:f.source=old
        legacy=CompletedSdkControlsTest();legacy.setUp();self.addCleanup(legacy.doCleanups)
        legacy.spec['source']['producer']={**legacy.spec['source']['producer'],
            'runAttempt':legacy.spec['source']['producer']['runAttempt']+1}
        with self.assertRaisesRegex(ValueError,'original consumer or policy'):
            completed.validate_controls(legacy.spec,legacy.controls,legacy.base)


if __name__=='__main__':unittest.main()
