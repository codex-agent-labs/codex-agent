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
const readRegularFile = exactBlock('function readRegularFile(file)', 'function canonicalJson(value)');
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

test('actual installed consumer binds declarations and entry points to npm archive bytes', () => {
  const verifyMember = exactBlock('function verifyInstalledPackageMember(', 'function hasModifier(node, kind)');
  const names = ['index.d.ts', 'index.cjs', 'index.mjs'];
  const entries = names.map((name) => `package/${name}`);
  const run = (archiveEntries, changedName, installedBytes, archiveBytes) =>
    vm.runInNewContext(`const archiveEntries = ${JSON.stringify(archiveEntries)};\n${readRegularFile}\n${verifyMember}\nverifyInstalledPackageMember(archiveEntries, changedName);`, {
      assert, Buffer, path, changedName, packageRoot: '/installed', tarballFile: '/selected.tgz',
      fs: { lstatSync: () => ({ isFile: () => true, isSymbolicLink: () => false }), readFileSync: (file) => {
        assert.equal(file, `/installed/${changedName}`);
        return installedBytes;
      } },
      execFileSync: (command, args) => {
        assert.equal(command, 'tar');
        assert.deepEqual(Array.from(args), ['-xOzf', '/selected.tgz', `package/${changedName}`]);
        return archiveBytes;
      },
    });
  for (const name of names) {
    const bytes = Buffer.from(name);
    run(entries, name, bytes, bytes);
    assert.throws(() => run(entries, name, bytes, Buffer.from(`${name} changed`)), /selected npm archive member/);
    assert.throws(() => run(entries.filter((entry) => entry !== `package/${name}`), name, bytes, bytes), /exactly one path/);
    assert.throws(() => run([...entries, `elsewhere/${name}`], name, bytes, bytes), /exactly one path/);
  }
});

test('installed package metadata and entrypoints reject symlinks before reading', () => {
  for (const name of ['package.json', 'META-INF/codex-agent/sdk-compatibility.json', 'index.cjs']) {
    assert.throws(() => vm.runInNewContext(`${readRegularFile}\nreadRegularFile(file);`, {
      assert, file: `/installed/${name}`,
      fs: {
        lstatSync: () => ({ isFile: () => true, isSymbolicLink: () => true }),
        readFileSync: () => assert.fail('A symlink must never be read'),
      },
    }), /not a regular file/);
  }
});

test('actual installed consumer binds Runtime dist inventory and bytes to npm archive', () => {
  const verifyRuntime = exactBlock('function verifyInstalledRuntimeMembers(', 'function hasModifier(node, kind)');
  const names = ['codex-agent-codex-agent-runtime-desktop.js', 'codex-agent-codex-agent-runtime-desktop.js.map'];
  const entries = names.map((name) => `package/dist/${name}`);
  const contents = Object.fromEntries(names.map((name) => [name, Buffer.from(name)]));
  const check = (archiveEntries = entries, installed = contents, archive = contents, symlink = '') =>
    vm.runInNewContext(`${verifyRuntime}\nverifyInstalledRuntimeMembers(archiveEntries);`, {
      assert, Buffer, path, packageRoot: '/installed', tarballFile: '/selected.tgz', archiveEntries,
      fs: {
        lstatSync: (file) => ({
          isDirectory: () => file === '/installed/dist',
          isFile: () => file !== '/installed/dist',
          isSymbolicLink: () => file.endsWith(symlink) && symlink !== '',
        }),
        readdirSync: () => Object.keys(installed),
        readFileSync: (file) => installed[path.basename(file)],
      },
      execFileSync: (command, args) => {
        assert.equal(command, 'tar');
        assert.deepEqual(Array.from(args.slice(0, 2)), ['-xOzf', '/selected.tgz']);
        return archive[path.posix.basename(args[2])];
      },
    });
  check();
  assert.throws(() => check(entries, { ...contents, [names[0]]: Buffer.from('changed') }), /differs from the selected npm archive/);
  assert.throws(() => check(entries, { ...contents, extra: Buffer.from('extra') }), /inventory must equal/);
  assert.throws(() => check(entries, contents, contents, names[0]), /not a regular file/);
  assert.throws(() => check([...entries, 'package/dist/nested/other.js']), /direct dist members/);
  assert.throws(() => check([...entries, 'package/dist/..\\index.mjs']), /must not contain backslashes/);
});
