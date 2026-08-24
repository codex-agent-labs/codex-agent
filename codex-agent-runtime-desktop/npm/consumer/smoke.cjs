'use strict';

const assert = require('node:assert/strict');
const childProcess = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

assert.equal(process.version, 'v24.18.0');
process.argv.push('--not-an-evidence-argument');
const sdk = require('@codex-agent-labs/codex-agent');
assert.equal(typeof sdk.createCodexHost, 'function');
assert.throws(() => new sdk.CodexHost());
assert.throws(() => new sdk.CodexAgent());
assert.throws(() => new sdk.CodexConversation());
assert.throws(() => new sdk.CodexObservation());
for (const constructor of [
  sdk.CodexAgent,
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

const browserImport = childProcess.spawnSync(
  process.execPath,
  ['-e', "global.process=undefined;require('@codex-agent-labs/codex-agent')"],
  { cwd: __dirname, encoding: 'utf8' },
);
assert.notEqual(browserImport.status, 0);
assert.match(browserImport.stderr, /supports Node\.js only/);

const root = fs.mkdtempSync(path.join(os.tmpdir(), 'codex-agent-npm-'));
const bundle = path.join(root, 'bundle');
const data = path.join(root, 'data');
const workspace = path.join(root, 'workspace');
fs.mkdirSync(bundle);
fs.mkdirSync(data);
fs.mkdirSync(workspace);

async function settleCallbacks() {
  await new Promise((resolve) => setImmediate(resolve));
}

(async () => {
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

  const aborted = sdk.createCodexHost(bundle, path.join(root, 'aborted'), 'javascript', 'JavaScript', 'test');
  const controller = new AbortController();
  controller.abort();
  await assert.rejects(aborted.start(controller.signal), (error) => error.name === 'AbortError');
  assert.equal(aborted.state.status, 'new');
  assert.equal(await aborted.dispose(), undefined);
})().finally(() => fs.rmSync(root, { recursive: true, force: true }));
