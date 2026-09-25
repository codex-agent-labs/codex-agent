'use strict';

// Pure JavaScript source regression: no SDK, TypeScript or Runtime execution.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../../consumer/smoke.mjs'), 'utf8');

function exactBlock(start, end) {
  const first = source.indexOf(start);
  const last = source.indexOf(end, first);
  assert.ok(first >= 0 && last > first, 'The actual consumer evidence block must exist');
  assert.equal(source.indexOf(start, first + start.length), -1, 'The evidence block must be unique');
  return source.slice(first, last);
}

const helpers = exactBlock('function canonicalJson(value)', 'function hasModifier(node, kind)');
const verifyPackageIdentity = exactBlock('function verifyInstalledPackageIdentity(', 'function hasModifier(node, kind)');
const mutation = exactBlock('  const wrongDefaultVersion =',
  '  assert.throws(\n    () => verifySdkCompatibility(Buffer.concat(');

for (const expectedDefaultRuntimeVersion of ['0.8.0', '0.8.1']) {
  test(`actual installed consumer rejects a changed default when selected default is ${expectedDefaultRuntimeVersion}`, () => {
    const declaration = {
      contract: {}, platformRuntime: {},
      runtime: { defaultRuntimeVersion: expectedDefaultRuntimeVersion, embeddedVariants: [
        'linux-arm64', 'linux-x64', 'macos-arm64', 'macos-x64', 'windows-x64',
      ].map((target) => ({ target })) },
      schemaVersion: 1, sdkVersion: '0.8.0',
    };
    vm.runInNewContext(`${helpers}\nverifySdkCompatibility(compatibilityBytes);\n${mutation}\n` +
      "assert.equal(wrongDefaultVersion, expectedDefaultRuntimeVersion === '0.8.0' ? '0.8.1' : '0.8.2');", {
      assert, Buffer, expectedDefaultRuntimeVersion,
      compatibilityBytes: Buffer.from(`${JSON.stringify(declaration)}\n`),
    });
  });
}

test('actual installed consumer rejects duplicate or substituted Runtime targets', () => {
  const declaration = {
    contract: {}, platformRuntime: {},
    runtime: { defaultRuntimeVersion: '0.8.0', embeddedVariants: [
      'linux-arm64', 'linux-x64', 'macos-arm64', 'macos-x64', 'windows-x64',
    ].map((target) => ({ target })) },
    schemaVersion: 1, sdkVersion: '0.8.0',
  };
  for (const target of ['macos-arm64', 'unknown-target']) {
    const changed = structuredClone(declaration);
    changed.runtime.embeddedVariants[4].target = target;
    assert.throws(() => vm.runInNewContext(`${helpers}\nverifySdkCompatibility(compatibilityBytes);`, {
      assert, Buffer, expectedDefaultRuntimeVersion: '0.8.0',
      compatibilityBytes: Buffer.from(`${JSON.stringify(changed)}\n`),
    }), /exact five sorted Desktop Runtime targets/);
  }
});

test('actual installed consumer binds npm package identity to the selected archive and SDK declaration', () => {
  const compatibility = { sdkVersion: '0.8.0' };
  const packageBytes = Buffer.from('{"name":"@codex-agent-labs/codex-agent","version":"0.8.0"}\n');
  const check = (installedBytes, archiveBytes) => vm.runInNewContext(
    `${verifyPackageIdentity}\nverifyInstalledPackageIdentity(installedBytes, archiveBytes, compatibility);`,
    { assert, Buffer, installedBytes, archiveBytes, compatibility },
  );
  check(packageBytes, packageBytes);
  assert.throws(() => check(packageBytes, Buffer.concat([packageBytes, Buffer.from('\n')])), /selected npm archive member/);
  assert.throws(() => check(Buffer.from('{"name":"other","version":"0.8.0"}\n'), Buffer.from('{"name":"other","version":"0.8.0"}\n')), /@codex-agent-labs\/codex-agent/);
  assert.throws(() => check(Buffer.from('{"name":"@codex-agent-labs/codex-agent","version":"0.8.1"}\n'), Buffer.from('{"name":"@codex-agent-labs/codex-agent","version":"0.8.1"}\n')), /0\.8\.0/);
});
