// Subprocesses are injected fixtures. This never runs TypeScript, SDK code, npm, or a Runtime.
const assert = require('node:assert/strict');
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
  runValidation({ cwd: root, executable: '/fixture/node', spawn, stdout, stderr });
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
      () => runValidation({ cwd: root, executable: '/fixture/node', spawn, stdout, stderr }),
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
      () => runValidation({ cwd: root, spawn }),
      mutation.startsWith('compiler-') ? /Installed TypeScript compiler/ : /missing, empty, or not a regular file/,
    );
    assert.equal(calls, mutation.startsWith('compiler-') ? 0 : 2);
    for (const name of ['public-api.json', 'packed-tests.xml',
      'typescript-execution.json', 'packed-consumer-execution.json']) {
      assert.equal(fs.existsSync(path.join(root, name)), false, name);
    }
  }
});
