"""Narrow routing checks only; no product or signature authentication claims."""
import ast
import json
import os
from pathlib import Path
import re
import textwrap
import unittest

ROOT = Path(os.environ.get('TOOLING_ONLY_CANDIDATE_ROOT', Path(__file__).resolve().parents[2]))

def jobs(source):
    return dict(re.findall(r'(?ms)^  ([a-z][a-z0-9-]*):\n(.*?)(?=^  [a-z][a-z0-9-]*:|\Z)', source))

def condition(job):
    m = re.search(r'(?m)^    if: (.*)$', job)
    if not m: return 'success()'
    value=m[1]
    if value == '>-':
        value = re.match(r'((?:\n      .*?)+)(?=\n    \S)', job[m.end():])[1].replace('\n',' ')
    if value.startswith("'"):
        assert value.endswith("'");value=value[1:-1].replace("''", "'")
    if value.startswith('${{'): value=value[3:-2].strip()
    return value

def evaluate(expression, *, tooling=True, authorized=True, event='pull_request'):
    """Evaluate saved Boolean routing with all normal plan/predecessor jobs skipped."""
    def value(match):
        key=match[0]
        if key=='inputs.toolingOnly': return repr(tooling)
        if key=='inputs.sdkRecoveryOnly': return 'True'
        if key.startswith('inputs.'): return 'False'
        if key=='github.event_name': return repr(event)
        if key=='github.event.pull_request.labels.*.name': return repr(['ci:tooling-only','ci:remote-final','merge-ready'])
        if key.startswith('github.'): return "''"
        if key=='needs.*.result': return repr(['skipped'])
        if key.startswith('needs.tooling-plan.'):
            return repr('success' if key.endswith('.result') else ('true' if authorized and key.endswith(('.event_authorized','.remote_build_authorized')) else ''))
        if key.startswith('needs.'):
            return repr('skipped' if key.endswith('.result') else '')
        raise AssertionError(key)
    expression=re.sub(r'(?:inputs\.[\w-]+|github\.[\w.*-]+|needs\.[\w.*-]+)',value,expression)
    expression=re.sub(r'!(?!=)', ' not ', expression).replace('&&',' and ').replace('||',' or ')
    expression=re.sub(r'\btrue\b','True',expression);expression=re.sub(r'\bfalse\b','False',expression)
    expression=expression.strip()
    return bool(eval(expression, {'__builtins__':{}}, {'always':lambda:True,'cancelled':lambda:False,
        'success':lambda:False, 'contains':lambda seq,item:item in seq,'fromJSON':json.loads,
        'toJSON':json.dumps,'format':lambda fmt,*a:fmt.format(*a)}))

class ToolingOnlyWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=(ROOT/'.github/workflows/product-validation.yml').read_text()
        cls.jobs=jobs(cls.source)

    def test_tooling_mode_schedules_no_normal_product_or_merge_jobs(self):
        selected={name for name,job in self.jobs.items() if evaluate(condition(job))}
        self.assertEqual({'tooling-plan','contract-validation','tooling-only-status'},selected)

    def test_unauthorized_and_dispatch_context_do_not_grant_signing(self):
        self.assertFalse(evaluate(condition(self.jobs['contract-validation']),authorized=False))
        self.assertFalse(evaluate(condition(self.jobs['tooling-only-status']),authorized=False))
        self.assertFalse(evaluate(condition(self.jobs['tooling-plan']),event='workflow_dispatch'))
        self.assertFalse(evaluate(condition(self.jobs['tooling-plan']),tooling=False))

    def test_normal_and_tooling_plans_use_identical_authority_and_impact_gates(self):
        normal=self.jobs['plan'];tooling=self.jobs['tooling-plan']
        shared=lambda job:job[job.index('    steps:\n')+len('    steps:\n'):job.index('      - id: impact\n')]
        self.assertEqual(shared(normal),shared(tooling))
        impact=lambda job:job[job.index('      - id: impact\n'):job.index('      - id: validation-reuse\n') if '      - id: validation-reuse\n' in job else job.index('      - id: tooling\n')]
        self.assertEqual(impact(normal),impact(tooling))
        self.assertTrue(evaluate(condition(normal),tooling=False))

    def test_discovery_is_existing_full_authenticated_gate_before_missing_lane(self):
        job=self.jobs['tooling-plan']
        self.assertIn('candidate_run_ids=run_ids',job)
        self.assertIn("'merge-base', '--is-ancestor', introduction, revision",job)
        self.assertIn('git_inventory(repository, introduction, _COMPILER_INPUTS) != git_inventory(repository, revision, _COMPILER_INPUTS)',job)
        self.assertIn("created='>=' + since",job)
        self.assertIn('40171845008',job)
        self.assertNotIn('/actions/artifacts',job)
        self.assertIn('result = discover_tooling_ci(',job)
        self.assertNotIn('product_reuse.py discover',job)
        self.assertNotIn('restore-reuse-qualification',job)
        body=re.search(r"(?ms)          python3 -B - <<'PYTHON'\n(.*?)^          PYTHON",job)[1]
        tree=ast.parse(textwrap.dedent(body))
        node=next(n for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='values' for t in n.targets))
        for selected in (None, {'artifactId':1}):
            local={'selected':selected,'canonical_json_bytes':lambda value:(json.dumps(value,separators=(',',':'))+'\n').encode(),'dict':dict,'str':str}
            exec(compile(ast.Module(body=[node],type_ignores=[]),'<saved selector>','exec'),{},local)
            self.assertEqual(local['values']['tooling_miss'],str(selected is None).lower())
            rows=json.loads(local['values']['contract_matrix'])['include']
            self.assertEqual(rows,[] if selected else [dict(lane='contracts',build=False,test=False,metadata=False)])

    def test_no_product_completion_or_new_signing_semantics(self):
        job=self.jobs['tooling-plan']
        self.assertIn("      contract_reconciliation_required: 'false'",job)
        self.assertIn("      native_contract_complete: 'false'",job)
        self.assertIn('      contract_next_phase: none',job)
        caller=self.jobs['contract-validation']
        self.assertIn('uses: ./.github/workflows/contract-validation.yml',caller)
        self.assertIn('needs.tooling-plan.outputs.publisher_sha',caller)
        self.assertIn('needs.tooling-plan.outputs.source_sha',caller)
        self.assertNotIn('CI / merge-gate',self.jobs['tooling-only-status'])
        ci=(ROOT/'.github/workflows/ci.yml').read_text()
        self.assertIn("toolingOnly: ${{ github.event_name == 'pull_request' && contains(github.event.pull_request.labels.*.name, 'ci:tooling-only') }}",ci)
        # Existing event-authority logic remains byte-identical above; the selector
        # label neither replaces ci:remote-final nor grants release authority.
        self.assertIn("github.event.label.name == 'ci:remote-final'",job)

if __name__=='__main__':unittest.main()
