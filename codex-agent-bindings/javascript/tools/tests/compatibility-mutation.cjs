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
const mutation = exactBlock('  const wrongDefaultVersion =',
  '  assert.throws(\n    () => verifySdkCompatibility(Buffer.concat(');

for (const expectedDefaultRuntimeVersion of ['0.8.0', '0.8.1']) {
  test(`actual installed consumer rejects a changed default when selected default is ${expectedDefaultRuntimeVersion}`, () => {
    const declaration = {
      contract: {}, platformRuntime: {},
      runtime: { defaultRuntimeVersion: expectedDefaultRuntimeVersion, embeddedVariants: [{}, {}, {}, {}, {}] },
      schemaVersion: 1, sdkVersion: '0.8.0',
    };
    vm.runInNewContext(`${helpers}\nverifySdkCompatibility(compatibilityBytes);\n${mutation}\n` +
      "assert.equal(wrongDefaultVersion, expectedDefaultRuntimeVersion === '0.8.0' ? '0.8.1' : '0.8.2');", {
      assert, Buffer, expectedDefaultRuntimeVersion,
      compatibilityBytes: Buffer.from(`${JSON.stringify(declaration)}\n`),
    });
  });
}
