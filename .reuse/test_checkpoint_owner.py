"""Separate opt-in owner provisioning; legacy descriptor shape stays exact."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import os
import sys
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import consumer
from products.inventory import canonical_json_bytes

APPROVAL={**json.loads(Path(__file__).with_name('approvals.json').read_bytes()),'authorityCommit':'a'*40}
DOCUMENT=json.loads(Path(__file__).with_name('completed-reuse.json').read_bytes())


class CheckpointOwnerTest(unittest.TestCase):
    def descriptor(self):
        return {'schemaVersion':1,'kind':'sdk-checkpoint-owner-authorization',
            'parent':deepcopy(DOCUMENT['policy']['sdkCompletion']),'parentProofSha256':'sha256:'+'a'*64,
            'bootstrap':deepcopy(DOCUMENT['policy']['sdkCompletion']),'bootstrapProofSha256':'sha256:'+'b'*64,
            'collectors':['product-validation / sdk-collect-9']}

    def provision(self,root,*,enabled=False,changed=False):
        raw=canonical_json_bytes(DOCUMENT);owner=canonical_json_bytes(self.descriptor());reads=[]
        def fetch(path,revision):
            self.assertEqual(APPROVAL['authorityCommit'],revision);reads.append(path)
            if path=='.reuse/completed-reuse.json':return raw
            self.assertEqual('.reuse/checkpoint-owner.json',path)
            return owner+b' ' if changed and reads.count(path)>1 else owner
        with patch.object(consumer.authority,'contents',side_effect=fetch), \
             patch.object(consumer,'history',return_value={}) as history, \
             patch.object(consumer,'retained_sdk_binding_current',return_value=True), \
             patch.object(consumer,'completed_sdk_spec',return_value=({'sdkInputs':{'source':DOCUMENT['retainedSdkInputsSource']}},38)):
            result,env=consumer.completed_environment(root,root,APPROVAL,checkpoint=enabled)
            self.assertEqual(len(DOCUMENT['gitHistory']),history.call_count)
        self.assertEqual(2,reads.count('.reuse/completed-reuse.json'))
        self.assertEqual(2 if enabled else 0,reads.count('.reuse/checkpoint-owner.json'))
        return result,env

    def test_separate_owner_uses_protected_publisher_and_disabled_reads_nothing_new(self):
        for enabled in (False,True):
            with self.subTest(enabled=enabled),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary).resolve();result,env=self.provision(root,enabled=enabled)
                self.assertEqual(0,result['productArtifactDownloads'])
                self.assertEqual(canonical_json_bytes(DOCUMENT['policy']),Path(env['CODEX_AGENT_COMPLETED_REUSE_POLICY']).read_bytes())
                if enabled:
                    owner=json.loads(Path(env['CODEX_AGENT_CHECKPOINT_OWNER_POLICY']).read_bytes())
                    self.assertEqual(APPROVAL['authorityCommit'],owner['issuerCommit'])
                    self.assertEqual(APPROVAL['authorityCommit'],owner['collectorWorkflowSha'])
                    self.assertNotEqual(APPROVAL['activeVerifier'],owner['issuerCommit'])
                    self.assertEqual(DOCUMENT['policy']['sdkCompletion'],owner['bootstrap'])
                else:self.assertNotIn('CODEX_AGENT_CHECKPOINT_OWNER_POLICY',env)

    def test_unapproved_owner_caller_sha_or_changed_provision_never_exports(self):
        for fault in ('issuer','workflow','bootstrap','parent','role','kind','version'):
            value=self.descriptor()
            if fault=='issuer':value['issuerCommit']='f'*40
            elif fault=='workflow':value['collectorWorkflowSha']='f'*40
            elif fault=='bootstrap':value['bootstrap']['artifactId']+=1
            elif fault=='parent':value['parent']['sourceCommit']='f'*40
            elif fault=='role':value['collectors']=['unknown']
            elif fault=='kind':value['kind']='sdk-checkpoint-owner'
            else:value['schemaVersion']=True
            with self.subTest(fault=fault),self.assertRaises(ValueError):
                consumer.checkpoint_owner_policy(canonical_json_bytes(value),APPROVAL,DOCUMENT)
        document={**DOCUMENT,'checkpointOwner':self.descriptor()}
        with self.assertRaises(ValueError):consumer.completed_descriptor(canonical_json_bytes(document),APPROVAL)
        with tempfile.TemporaryDirectory() as temporary,self.assertRaisesRegex(ValueError,'changed during provisioning'):
            self.provision(Path(temporary).resolve(),enabled=True,changed=True)
    def test_cli_opt_in_uses_one_existing_provision_pass_and_rejects_other_modes(self):
        old_cwd=Path.cwd()
        try:
            with tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary).resolve();work=root/'work';envfile=root/'env'
                arguments=['consumer','provision','--repository-root',str(root),'--work',str(work),'--checkpoint-owner']
                with patch.object(sys,'argv',arguments),patch.dict(os.environ,{'GITHUB_ENV':str(envfile)}), \
                     patch.object(consumer,'approved',return_value=APPROVAL), \
                     patch.object(consumer,'snapshot',return_value={}), \
                     patch.object(consumer,'completed_environment',return_value=({}, {'CODEX_AGENT_CHECKPOINT_OWNER_POLICY':str(work/'owner.json')})) as provision, \
                     patch.object(consumer.authority,'protection'), \
                     patch.object(consumer.authority,'api',side_effect=[{}, {'commit':{'sha':APPROVAL['authorityCommit']}}]),redirect_stdout(io.StringIO()):
                    consumer.main()
                    provision.assert_called_once_with(root,work,APPROVAL,checkpoint=True)
                self.assertIn('CODEX_AGENT_CHECKPOINT_OWNER_POLICY=',envfile.read_text())
                for mode in ('setup','restore','verify'):
                    with patch.object(sys,'argv',[*arguments[:1],mode,*arguments[2:]]), \
                         patch.object(consumer,'approved') as approve,self.assertRaisesRegex(ValueError,'combined provisioning'):
                        consumer.main()
                    approve.assert_not_called()
        finally:os.chdir(old_cwd)


if __name__=='__main__':unittest.main()
