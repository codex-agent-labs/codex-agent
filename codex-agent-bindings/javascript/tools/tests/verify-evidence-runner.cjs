// Subprocesses are injected fixtures. This never runs TypeScript, SDK code, npm, or a Runtime.
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');
const { pathToFileURL } = require('node:url');

const runnerUrl = pathToFileURL(path.resolve(__dirname, '../../consumer/verify.mjs')).href;

function fixture() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'codex-agent-js-evidence-'));
  const typeScript = path.join(root, 'node_modules/typescript/bin/tsc');
  fs.mkdirSync(path.dirname(typeScript), { recursive: true });
  fs.writeFileSync(typeScript, 'fixture installed compiler');
  return { root, typeScript };
}

function stream() {
  const chunks = [];
  return {
    value: () => Buffer.concat(chunks),
    write: (value) => chunks.push(Buffer.from(value)),
  };
}

function readEnvelope(root, name) {
  const bytes = fs.readFileSync(path.join(root, name));
  const value = JSON.parse(bytes);
  assert.deepEqual(
    Object.keys(value),
    ['command', 'exitCode', 'schemaVersion', 'stderrBase64', 'stdoutBase64'],
  );
  assert.deepEqual(bytes, Buffer.from(`${JSON.stringify(value)}\n`));
  return value;
}

test('retains exact compiler and behavior bytes from the installed consumer commands', async (context) => {
  const { runValidation } = await import(runnerUrl);
  const { root, typeScript } = fixture();
  context.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const commands = [];
  const raw = [
    { stdout: Buffer.from([0x00, 0xff, 0x0d, 0x0a]), stderr: Buffer.alloc(0) },
    { stdout: Buffer.alloc(0), stderr: Buffer.from([0x80, 0x00, 0x0a]) },
  ];
  const stdout = stream();
  const stderr = stream();
  const spawn = (command, args, options) => {
    commands.push([command, ...args]);
    assert.deepEqual(options, {
      cwd: root,
      encoding: null,
      maxBuffer: 64 * 1024 * 1024,
      shell: false,
    });
    if (commands.length === 2) {
      fs.writeFileSync(path.join(root, 'public-api.json'), '{}\n');
      fs.writeFileSync(path.join(root, 'packed-tests.xml'), '<testsuites/>\n');
    }
    return { ...raw[commands.length - 1], error: undefined, signal: null, status: 0 };
  };
  runValidation({ cwd: root, executable: '/fixture/node', spawn, stdout, stderr,
    preflight: (_cwd, _archive, run) => run() });
  assert.deepEqual(commands, [
    ['/fixture/node', typeScript, '--noEmit'],
    ['/fixture/node', '--test', '--test-reporter=junit',
      '--test-reporter-destination=packed-tests.xml', 'smoke.cjs', 'smoke.mjs'],
  ]);
  const compiler = readEnvelope(root, 'typescript-execution.json');
  const behavior = readEnvelope(root, 'packed-consumer-execution.json');
  assert.deepEqual(Buffer.from(compiler.stdoutBase64, 'base64'), raw[0].stdout);
  assert.deepEqual(Buffer.from(compiler.stderrBase64, 'base64'), raw[0].stderr);
  assert.deepEqual(Buffer.from(behavior.stdoutBase64, 'base64'), raw[1].stdout);
  assert.deepEqual(Buffer.from(behavior.stderrBase64, 'base64'), raw[1].stderr);
  assert.deepEqual(stdout.value(), Buffer.concat(raw.map((value) => value.stdout)));
  assert.deepEqual(stderr.value(), Buffer.concat(raw.map((value) => value.stderr)));
});

test('failure forwards exact diagnostics and publishes no success evidence', async (context) => {
  const { runValidation } = await import(runnerUrl);
  for (const failure of [1, 2]) {
    const { root } = fixture();
    context.after(() => fs.rmSync(root, { recursive: true, force: true }));
    for (const name of ['public-api.json', 'packed-tests.xml',
      'typescript-execution.json', 'packed-consumer-execution.json']) {
      fs.writeFileSync(path.join(root, name), 'stale');
    }
    const diagnostic = Buffer.from([failure, 0x00, 0xff, 0x0d, 0x0a]);
    const stdout = stream();
    const stderr = stream();
    let calls = 0;
    const spawn = () => {
      calls += 1;
      if (calls === 2) {
        fs.writeFileSync(path.join(root, 'public-api.json'), 'partial');
        fs.writeFileSync(path.join(root, 'packed-tests.xml'), 'partial');
      }
      return {
        error: undefined,
        signal: null,
        status: calls === failure ? 7 : 0,
        stdout: Buffer.alloc(0),
        stderr: calls === failure ? diagnostic : Buffer.alloc(0),
      };
    };
    assert.throws(
      () => runValidation({ cwd: root, executable: '/fixture/node', spawn, stdout, stderr,
        preflight: (_cwd, _archive, run) => run() }),
      /validation command failed/,
    );
    assert.equal(calls, failure);
    assert.deepEqual(stderr.value(), diagnostic);
    assert.deepEqual(stdout.value(), Buffer.alloc(0));
    for (const name of ['public-api.json', 'packed-tests.xml',
      'typescript-execution.json', 'packed-consumer-execution.json']) {
      assert.equal(fs.existsSync(path.join(root, name)), false, name);
    }
  }
});

test('installed compiler and required semantic outputs fail closed without fallback', async (context) => {
  const { runValidation } = await import(runnerUrl);
  for (const mutation of ['compiler-missing', 'compiler-symlink', 'compiler-parent-symlink',
    'api-missing', 'junit-empty']) {
    const { root, typeScript } = fixture();
    context.after(() => fs.rmSync(root, { recursive: true, force: true }));
    if (mutation === 'compiler-missing') fs.rmSync(typeScript);
    if (mutation === 'compiler-symlink') {
      fs.rmSync(typeScript);
      fs.symlinkSync(__filename, typeScript);
    }
    if (mutation === 'compiler-parent-symlink') {
      const outside = path.join(root, 'outside-typescript');
      fs.renameSync(path.dirname(path.dirname(typeScript)), outside);
      fs.symlinkSync(outside, path.dirname(path.dirname(typeScript)));
    }
    let calls = 0;
    const spawn = () => {
      calls += 1;
      if (calls === 2) {
        if (mutation !== 'api-missing') fs.writeFileSync(path.join(root, 'public-api.json'), '{}\n');
        fs.writeFileSync(path.join(root, 'packed-tests.xml'), mutation === 'junit-empty' ? '' : '<testsuites/>\n');
      }
      return { error: undefined, signal: null, status: 0, stdout: Buffer.alloc(0), stderr: Buffer.alloc(0) };
    };
    assert.throws(
      () => runValidation({ cwd: root, spawn, preflight: (_cwd, _archive, run) => run() }),
      mutation.startsWith('compiler-') ? /Installed TypeScript compiler/ : /missing, empty, or not a regular file/,
    );
    assert.equal(calls, mutation.startsWith('compiler-') ? 0 : 2);
    for (const name of ['public-api.json', 'packed-tests.xml',
      'typescript-execution.json', 'packed-consumer-execution.json']) {
      assert.equal(fs.existsSync(path.join(root, name)), false, name);
    }
  }
});

test('selected npm archive is checked before any compiler or SDK test process', async (context) => {
  const { runValidation, verifySelectedPackage } = await import(runnerUrl);
  const { root } = fixture();
  context.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const source = path.join(root, 'source/package');
  const installed = path.join(root, 'node_modules/@codex-agent-labs/codex-agent');
  for (const directory of [source, installed]) fs.mkdirSync(path.join(directory, 'dist'), { recursive: true });
  const members = {
    'package.json': '{"name":"@codex-agent-labs/codex-agent"}\n',
    'index.cjs': 'module.exports = {};\n',
    'index.mjs': 'export default {};\n',
    'dist/runtime.js': 'export const loaded = true;\n',
  };
  for (const [name, bytes] of Object.entries(members)) {
    for (const directory of [source, installed]) fs.writeFileSync(path.join(directory, name), bytes);
  }
  const archive = path.join(root, 'selected.tgz');
  const systemTar = process.platform === 'win32'
    ? path.join(process.env.SystemRoot, 'System32', 'tar.exe')
    : process.platform === 'darwin' ? '/usr/bin/bsdtar' : '/usr/bin/tar';
  execFileSync(systemTar, ['-czf', archive, '-C', path.join(root, 'source'), 'package']);
  const shadowDirectory = path.join(root, 'node_modules/.bin');
  fs.mkdirSync(shadowDirectory, { recursive: true });
  for (const name of new Set([process.platform === 'win32' ? 'tar.exe' : 'tar', path.basename(systemTar)])) {
    fs.writeFileSync(path.join(shadowDirectory, name), 'This package-controlled tar must never execute', { mode: 0o755 });
  }
  const pathKey = Object.keys(process.env).find((name) => name.toLowerCase() === 'path') ?? 'PATH';
  const originalPath = process.env[pathKey];
  try {
    process.env[pathKey] = `${shadowDirectory}${path.delimiter}${originalPath ?? ''}`;
    verifySelectedPackage(root, archive);
  } finally {
    if (originalPath === undefined) delete process.env[pathKey];
    else process.env[pathKey] = originalPath;
  }
  let spawned = 0;
  const spawn = () => { spawned += 1; assert.fail('SDK or compiler must not execute before archive verification'); };
  fs.writeFileSync(path.join(installed, 'index.cjs'), 'module.exports = { tampered: true };\n');
  assert.throws(() => runValidation({ cwd: root, spawn,
    preflight: (cwd, _archive, run) => verifySelectedPackage(cwd, archive, run) }),
    /differs from the selected archive/);
  assert.equal(spawned, 0);
  assert.equal(fs.existsSync(path.join(root, 'packed-consumer-execution.json')), false);
  fs.writeFileSync(path.join(installed, 'index.cjs'), members['index.cjs']);
  fs.writeFileSync(path.join(installed, 'extra.cjs'), 'malicious');
  assert.throws(() => verifySelectedPackage(root, archive), /inventory differs/);
  fs.rmSync(path.join(installed, 'extra.cjs'));
  fs.rmSync(path.join(installed, 'index.mjs'));
  fs.symlinkSync(path.join(source, 'index.mjs'), path.join(installed, 'index.mjs'));
  assert.throws(() => verifySelectedPackage(root, archive), /not a regular file/);
});

test('selected npm archive rejects a symlink member even when installed bytes match', async (context) => {
  const { verifySelectedPackage, systemTar } = await import(runnerUrl);
  const { root } = fixture();
  context.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const source = path.join(root, 'source/package');
  const installed = path.join(root, 'node_modules/@codex-agent-labs/codex-agent');
  for (const directory of [source, installed]) fs.mkdirSync(path.join(directory, 'dist'), { recursive: true });
  for (const [name, bytes] of Object.entries({
    'package.json': '{}\n', 'index.cjs': '', 'dist/runtime.js': 'runtime\n',
  })) {
    for (const directory of [source, installed]) fs.writeFileSync(path.join(directory, name), bytes);
  }
  fs.symlinkSync('index.cjs', path.join(source, 'index.mjs'));
  fs.writeFileSync(path.join(installed, 'index.mjs'), '');
  const archive = path.join(root, 'selected.tgz');
  execFileSync(systemTar(), ['-czf', archive, '-C', path.join(root, 'source'), 'package']);
  assert.throws(() => verifySelectedPackage(root, archive), /unsafe member type/);
});

test('consumer execution holds the verified npm snapshot after the selected archive changes', async (context) => {
  const { runValidation, verifySelectedPackage, systemTar } = await import(runnerUrl);
  const { root } = fixture();
  context.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const source = path.join(root, 'source/package');
  const installed = path.join(root, 'node_modules/@codex-agent-labs/codex-agent');
  for (const directory of [source, installed]) fs.mkdirSync(path.join(directory, 'dist'), { recursive: true });
  for (const [name, bytes] of Object.entries({
    'package.json': '{}\n', 'index.cjs': 'module.exports = {};\n',
    'index.mjs': 'export default {};\n', 'dist/runtime.js': 'export {};\n',
  })) {
    for (const directory of [source, installed]) fs.writeFileSync(path.join(directory, name), bytes);
  }
  const archive = path.join(root, 'selected.tgz');
  execFileSync(systemTar(), ['-czf', archive, '-C', path.join(root, 'source'), 'package']);
  let calls = 0;
  let heldArchive;
  const spawn = (_command, _args, options) => {
    calls += 1;
    if (calls === 1) {
      assert.equal(options.env, undefined);
      fs.writeFileSync(archive, 'replaced after verification');
    } else {
      heldArchive = options.env.CODEX_AGENT_NPM_TARBALL;
      assert.notEqual(heldArchive, archive);
      assert.equal(path.basename(heldArchive), path.basename(archive));
      assert.deepEqual(execFileSync(systemTar(), ['-tzf', heldArchive], { encoding: 'utf8' })
        .split('\n').filter(Boolean).sort(),
      ['package/', 'package/dist/', 'package/dist/runtime.js', 'package/index.cjs',
        'package/index.mjs', 'package/package.json'].sort());
      fs.writeFileSync(path.join(root, 'public-api.json'), '{}\n');
      fs.writeFileSync(path.join(root, 'packed-tests.xml'), '<testsuites/>\n');
    }
    return { status: 0, signal: null, stdout: Buffer.alloc(0), stderr: Buffer.alloc(0) };
  };
  runValidation({ cwd: root, spawn,
    preflight: (cwd, _archive, run) => verifySelectedPackage(cwd, archive, run) });
  assert.equal(calls, 2);
  assert.equal(fs.existsSync(heldArchive), false, 'The private snapshot must be removed after execution');
});
