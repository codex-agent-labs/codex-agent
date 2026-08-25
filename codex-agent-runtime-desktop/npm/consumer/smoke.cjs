'use strict';

const assert = require('node:assert/strict');
const childProcess = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');

const sdk = require('@codex-agent-labs/codex-agent');

async function settleCallbacks() {
  await new Promise((resolve) => setImmediate(resolve));
}

test('cjs exposes the exact Node-only SDK surface', () => {
  assert.equal(process.version, 'v24.18.0');
  process.argv.push('--not-an-evidence-argument');
  assert.equal(typeof sdk.createCodexHost, 'function');
  assert.throws(() => new sdk.CodexHost());
  assert.throws(() => new sdk.CodexAgent());
  assert.throws(() => new sdk.CodexAuthentication());
  assert.throws(() => new sdk.CodexAuthenticationState());
  assert.throws(() => new sdk.CodexConversation());
  assert.throws(() => new sdk.CodexObservation());
  for (const constructor of [
    sdk.AgentElicitationValidation,
    sdk.AgentElicitationValidationIssue,
    sdk.AgentFormOption,
    sdk.CodexAgent,
    sdk.CodexAuthentication,
    sdk.CodexAuthenticationState,
    sdk.CodexConversation,
    sdk.CodexConversationState,
    sdk.CodexError,
    sdk.CodexFailure,
    sdk.CodexHost,
    sdk.CodexHostState,
    sdk.CodexMessage,
    sdk.CodexObservation,
    sdk.CodexTurnProgress,
    sdk.CodexWorkspace,
  ]) {
    assert.deepEqual(Object.keys(constructor), []);
    assert.deepEqual(Object.keys(constructor.prototype), []);
  }

  const option = new sdk.AgentFormOption('value');
  assert.equal(option.value, 'value');
  assert.equal(option.title, 'value');
  assert.equal(option.description, null);
  assert.equal(Object.isFrozen(option), true);
  const describedOption = new sdk.AgentFormOption('custom', 'Custom title', 'Custom description');
  assert.equal(describedOption.value, 'custom');
  assert.equal(describedOption.title, 'Custom title');
  assert.equal(describedOption.description, 'Custom description');
  assert.throws(() => new sdk.AgentFormOption({ mutable: true }));
  assert.throws(() => new sdk.AgentFormOption('value', { mutable: true }));
  assert.throws(() => new sdk.AgentFormOption('value', 'title', { mutable: true }));

  const firstIssue = new sdk.AgentElicitationValidationIssue('first', 'missing_required');
  const secondIssue = new sdk.AgentElicitationValidationIssue('second', 'invalid_format');
  assert.equal(firstIssue.fieldName, 'first');
  assert.equal(firstIssue.reason, 'missing_required');
  assert.equal(secondIssue.fieldName, 'second');
  assert.equal(secondIssue.reason, 'invalid_format');
  assert.equal(Object.isFrozen(firstIssue), true);
  assert.throws(() => new sdk.AgentElicitationValidationIssue('field', 'not_a_reason'));
  assert.throws(() => new sdk.AgentElicitationValidationIssue({ mutable: true }, 'missing_required'));
  assert.throws(() => new sdk.AgentElicitationValidationIssue('field', { mutable: true }));
  const sourceIssues = [firstIssue, secondIssue];
  const validation = new sdk.AgentElicitationValidation(sourceIssues);
  assert.notEqual(validation.issues, sourceIssues);
  assert.notEqual(validation.issues[0], firstIssue);
  assert.notEqual(validation.issues[1], secondIssue);
  assert.equal(validation.issues[0].fieldName, 'first');
  assert.equal(validation.issues[0].reason, 'missing_required');
  assert.equal(validation.issues[1].fieldName, 'second');
  assert.equal(validation.issues[1].reason, 'invalid_format');
  sourceIssues.reverse();
  assert.equal(validation.issues[0].fieldName, 'first');
  assert.equal(validation.issues[1].fieldName, 'second');
  assert.equal(validation.isValid, false);
  assert.equal(Object.isFrozen(validation.issues), true);
  assert.equal(Object.isFrozen(validation), true);
  assert.equal(new sdk.AgentElicitationValidation([]).isValid, true);
  assert.throws(() => new sdk.AgentElicitationValidation(''));
  assert.throws(() => new sdk.AgentElicitationValidation(() => {}));
  assert.throws(() => new sdk.AgentElicitationValidation({ length: 0 }));
  assert.throws(() => new sdk.AgentElicitationValidation(new Proxy({ length: 0 }, {})));

  const mutableIssue = { fieldName: 'external', reason: 'unknown_field' };
  const proxiedIssue = new Proxy(mutableIssue, {});
  const proxyValidation = new sdk.AgentElicitationValidation([proxiedIssue]);
  assert.notEqual(proxyValidation.issues[0], proxiedIssue);
  mutableIssue.fieldName = 'mutated';
  mutableIssue.reason = 'invalid_format';
  assert.equal(proxyValidation.issues[0].fieldName, 'external');
  assert.equal(proxyValidation.issues[0].reason, 'unknown_field');

  const assertImmutableOwnGraph = (root) => {
    const seen = new Set();
    const visit = (value) => {
      if (value === null || typeof value !== 'object' || seen.has(value)) return;
      seen.add(value);
      assert.equal(Object.isFrozen(value), true);
      for (const key of Reflect.ownKeys(value)) {
        const nested = value[key];
        assert.equal(Reflect.set(value, key, nested), false);
        visit(nested);
      }
    };
    visit(root);
  };
  for (const snapshot of [option, describedOption, firstIssue, secondIssue, validation, proxyValidation]) {
    assertImmutableOwnGraph(snapshot);
  }

  const browserImport = childProcess.spawnSync(
    process.execPath,
    ['-e', "global.process=undefined;require('@codex-agent-labs/codex-agent')"],
    { cwd: __dirname, encoding: 'utf8' },
  );
  assert.notEqual(browserImport.status, 0);
  assert.match(browserImport.stderr, /supports Node\.js only/);
});

test('cjs projects lifecycle state failure cleanup and terminal delivery', async (context) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'codex-agent-npm-'));
  context.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const bundle = path.join(root, 'bundle');
  const data = path.join(root, 'data');
  const workspace = path.join(root, 'workspace');
  fs.mkdirSync(bundle);
  fs.mkdirSync(data);
  fs.mkdirSync(workspace);

  const host = sdk.createCodexHost(bundle, data, 'javascript', 'JavaScript', 'test');
  assert.deepEqual(Object.keys(host), []);
  assert.equal(Object.isFrozen(host.state), true);
  assert.deepEqual(Object.keys(host.state), []);
  const states = [];
  const observation = host.observeState((state) => states.push(state.status));
  assert.deepEqual(Object.keys(observation), []);
  await settleCallbacks();
  assert.deepEqual(states, ['new']);

  assert.equal(await host.start(), undefined);
  await settleCallbacks();
  assert.equal(host.state.status, 'workspace_required');
  assert.equal(states.at(-1), 'workspace_required');
  assert.equal(host.agent, null);

  await assert.rejects(
    host.selectWorkspace(workspace),
    (error) => error instanceof sdk.CodexError && error.code === 'runtime_prepare_failed',
  );
  await settleCallbacks();
  assert.equal(host.state.status, 'failed');
  assert.equal(host.state.failure.code, 'runtime_prepare_failed');
  assert.equal(Object.isFrozen(host.state), true);
  assert.equal(Object.isFrozen(host.state.failure), true);

  assert.equal(await host.close(), undefined);
  assert.equal(await host.dispose(), undefined);
  assert.equal(await host[Symbol.asyncDispose](), undefined);
  await settleCallbacks();
  assert.equal(states.at(-1), 'closed');
  assert.equal(observation.isClosed, true);
  assert.equal(observation.close(), undefined);
  assert.equal(observation.dispose(), undefined);
  assert.equal(observation[Symbol.dispose](), undefined);
});

test('cjs maps AbortSignal cancellation without starting', async (context) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'codex-agent-npm-'));
  context.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const bundle = path.join(root, 'bundle');
  fs.mkdirSync(bundle);
  const aborted = sdk.createCodexHost(bundle, path.join(root, 'aborted'), 'javascript', 'JavaScript', 'test');
  const controller = new AbortController();
  controller.abort();
  await assert.rejects(aborted.start(controller.signal), (error) => error.name === 'AbortError');
  assert.equal(aborted.state.status, 'new');
  assert.equal(await aborted.dispose(), undefined);
});
