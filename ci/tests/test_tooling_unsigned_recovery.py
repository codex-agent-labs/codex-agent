"""Focused cross-run unsigned-tooling recovery; synthetic fixture, no hosted claim."""
import copy
import io
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest import mock
import zipfile

from ci import tooling_release
from ci.products.inventory import load_canonical_json_bytes, regular_file_inventory, sha256_bytes
from ci.products.tooling import INPUT_NAMES, JAR, verified_tooling_capture
from ci.tests.test_tooling_release import ToolingReleaseTest, WORKFLOW_PIN


@unittest.skipUnless(shutil.which('ssh-keygen'), 'OpenSSH signing tool unavailable')
class UnsignedToolingRecoveryTest(unittest.TestCase):
    setUp = ToolingReleaseTest.setUp
    artifact_for = ToolingReleaseTest.artifact_for
    api = ToolingReleaseTest.api

    def recovery(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED) as archive:
            for path in [self.plan_path, *(self.plan_path.parent/'inventories/contracts'/name for name in INPUT_NAMES.values())]:
                archive.writestr(path.relative_to(self.plan_path.parent).as_posix(), path.read_bytes())
        plan_raw = output.getvalue()
        plan_artifact = {**self.artifact, 'id':702, 'name':f"codex-agent-ci-plan-{self.producer['tree']}",
            'digest':sha256_bytes(plan_raw), 'size_in_bytes':len(plan_raw),
            'archive_download_url':'https://api.github.com/repos/codex-agent-labs/codex-agent/actions/artifacts/702/zip'}
        locator = dict(producer=self.producer, workflowSha=WORKFLOW_PIN,
            planArtifactId=702, planArtifactSha256=plan_artifact['digest'], planArtifactBytes=len(plan_raw),
            planSha256=sha256_bytes(self.plan_path.read_bytes()), artifactId=701,
            artifactSha256=self.artifact['digest'], artifactBytes=len(self.archive))
        self.run['referenced_workflows'].append({
            'path':f'codex-agent-labs/codex-agent/.github/workflows/contract-validation.yml@{WORKFLOW_PIN}',
            'sha':WORKFLOW_PIN})
        self.jobs[0]['name'] = 'product-validation / contract-validation / product-contracts (false, contracts, false, false)'
        self.jobs.append({**self.jobs[0], 'id':802, 'name':'product-validation / tooling-plan'})
        original_api = self.api()
        def api(url, token):
            self.assertEqual('not-a-real-token', token)
            if url == plan_artifact['archive_download_url'].removesuffix('/zip'):
                return json.dumps(plan_artifact).encode()
            if url == plan_artifact['archive_download_url']:
                return plan_raw
            return original_api(url, token)
        caller = {**self.producer, 'runId':202, 'runAttempt':1, 'commit':self.source_sha,
            'tree':subprocess.check_output(['git','rev-parse','HEAD^{tree}'],cwd=self.repository,text=True).strip()}
        self.environment.values.update(GITHUB_SHA=caller['commit'],GITHUB_RUN_ID='202',GITHUB_RUN_ATTEMPT='1')
        return locator, caller, api, plan_raw, plan_artifact

    def invoke(self, caller, locator):
        return tooling_release.attest_tooling_ci(self.repository, self.plan_path, self.destination,
            trusted_source_sha=self.source_sha, trusted_workflow_sha=WORKFLOW_PIN,
            transport_producer=caller, event_payload=self.event, environment=self.environment,
            token='not-a-real-token', original_tooling=locator)

    def test_old_original_bytes_and_producer_survive_new_signing_context(self):
        locator, caller, api, plan_raw, plan_artifact = self.recovery()
        before = regular_file_inventory(self.lane, allow_empty=True)
        plan_before = self.plan_path.read_bytes()
        def policy(jar, evidence, repository, revision):
            self.assertEqual(0,self.environment.secret_reads)
            self.assertEqual(self.source_sha,revision)
            self.assertEqual((self.lane/JAR).read_bytes(),jar.read_bytes())
        with mock.patch.object(tooling_release,'RETAINED_UNSIGNED_TOOLING',locator), \
             mock.patch.object(tooling_release,'_verify_tooling_policy',side_effect=policy) as gate, \
             mock.patch('reuse.api_request',side_effect=api):
            result = self.invoke(caller,locator)
        gate.assert_called_once()
        evidence = self.destination/'tooling-evidence'
        self.assertEqual(before,regular_file_inventory(evidence/'original/lane',allow_empty=True))
        self.assertEqual(before,regular_file_inventory(self.lane,allow_empty=True))
        self.assertEqual(plan_before,(evidence/'original/plan.json').read_bytes())
        self.assertEqual(plan_before,self.plan_path.read_bytes())
        self.assertEqual((self.lane/'lane-receipt.json').read_bytes(),(evidence/'original/lane/lane-receipt.json').read_bytes())
        self.assertEqual(plan_raw,(self.destination/'transport/original-plan.zip').read_bytes())
        transport=load_canonical_json_bytes((self.destination/'transport/original-ci.json').read_bytes())
        self.assertEqual(self.producer,transport['producer'])
        self.assertEqual(plan_artifact,transport['planArtifact'])
        self.assertEqual(caller,result['transportProducer'])
        self.assertEqual(self.producer,result['originalToolingProducer'])
        self.assertNotEqual(caller,self.producer)
        policy_root=self.destination/'caller-policy'
        with verified_tooling_capture(evidence,self.repository,policy_root/f"keys/{self.signing['keyId']}.pub",
                required_trust_domain='release',keyring=policy_root/self.keyring.name,keys_directory=policy_root/'keys') as jar:
            self.assertEqual((self.lane/JAR).read_bytes(),jar.read_bytes())
        self.assertGreater(self.environment.secret_reads,0)

    def test_wrong_original_locator_rejects_before_secret_or_retrieval(self):
        locator,caller,_,_,_=self.recovery()
        wrong=copy.deepcopy(locator);wrong['artifactSha256']='sha256:'+'0'*64
        self.environment.forbid_secret=True
        with mock.patch.object(tooling_release,'RETAINED_UNSIGNED_TOOLING',locator), \
             mock.patch('reuse.api_request',side_effect=AssertionError('No retrieval permitted')):
            with self.assertRaisesRegex(ValueError,'reviewed original locator'):
                self.invoke(caller,wrong)
        self.assertEqual(0,self.environment.secret_reads)
        self.assertFalse(self.destination.exists())
