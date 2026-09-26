import { execFileSync, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const outputs = [
  'public-api.json',
  'packed-tests.xml',
  'typescript-execution.json',
  'packed-consumer-execution.json',
];

function removeOutputs(cwd) {
  for (const name of outputs) fs.rmSync(path.join(cwd, name), { force: true });
  for (const name of outputs) fs.rmSync(path.join(cwd, `.${name}.tmp`), { force: true });
}

function exactFile(file, label) {
  const stat = fs.lstatSync(file, { throwIfNoEntry: false });
  if (!stat?.isFile() || stat.isSymbolicLink() || stat.size === 0) {
    throw new Error(`${label} is missing, empty, or not a regular file: ${file}`);
  }
  return file;
}

export function systemTar() {
  const executable = process.platform === 'win32'
    ? path.join(process.env.SystemRoot ?? '', 'System32', 'tar.exe')
    : process.platform === 'darwin' ? '/usr/bin/bsdtar' : '/usr/bin/tar';
  if (!path.isAbsolute(executable)) throw new Error('The system tar path must be absolute');
  return exactFile(executable, 'System tar');
}

export function verifySelectedPackage(cwd, archive = process.env.CODEX_AGENT_NPM_TARBALL) {
  if (!archive) throw new Error('The selected npm archive must be supplied before SDK execution');
  exactFile(archive, 'Selected npm archive');
  const tar = systemTar();
  const packageRoot = path.join(cwd, 'node_modules', '@codex-agent-labs', 'codex-agent');
  const entries = execFileSync(tar, ['-tzf', archive], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 })
    .trimEnd().split('\n');
  const types = execFileSync(tar, ['-tvzf', archive], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 })
    .trimEnd().split('\n');
  if (types.length !== entries.length || types.some((line) => !['-', 'd'].includes(line[0]))) {
    throw new Error('Selected npm archive has an unsafe member type');
  }
  const expected = [];
  for (const entry of entries) {
    const parts = entry.split('/');
    if (parts[0] !== 'package' || parts.slice(1).some((part, index) =>
      part === '.' || part === '..' || part.includes('\\') || (part === '' && index < parts.length - 2)) ||
        parts.some((part) => /[\x00-\x1f\x7f]/.test(part)) || parts.length < 2) {
      throw new Error(`Selected npm archive has an unsafe member: ${entry}`);
    }
    if (!entry.endsWith('/')) expected.push(parts.slice(1).join('/'));
  }
  if (new Set(expected).size !== expected.length || !expected.includes('package.json') ||
      !expected.includes('index.cjs') || !expected.includes('index.mjs') ||
      !expected.some((name) => name.startsWith('dist/') && name.endsWith('.js'))) {
    throw new Error('Selected npm archive has missing or duplicate executable members');
  }
  const installed = [];
  function visit(directory, prefix = '') {
    const stat = fs.lstatSync(directory);
    if (!stat.isDirectory() || stat.isSymbolicLink()) throw new Error(`Installed npm directory is not real: ${directory}`);
    for (const name of fs.readdirSync(directory)) {
      const relative = prefix ? `${prefix}/${name}` : name;
      const file = path.join(directory, name);
      const member = fs.lstatSync(file);
      if (member.isDirectory() && !member.isSymbolicLink()) visit(file, relative);
      else {
        if (!member.isFile() || member.isSymbolicLink()) {
          throw new Error(`Installed npm member is not a regular file: ${file}`);
        }
        installed.push(relative);
      }
    }
  }
  visit(packageRoot);
  if (installed.sort().join('\n') !== expected.sort().join('\n')) {
    throw new Error('Installed npm inventory differs from the selected archive');
  }
  for (const name of expected) {
    const member = `package/${name}`;
    const archiveBytes = execFileSync(tar, ['-xOzf', archive, member], { maxBuffer: 64 * 1024 * 1024 });
    if (!fs.readFileSync(path.join(packageRoot, ...name.split('/'))).equals(archiveBytes)) {
      throw new Error(`Installed npm member differs from the selected archive: ${name}`);
    }
  }
}

function installedTypeScriptCompiler(cwd) {
  let current = cwd;
  for (const member of ['node_modules', 'typescript', 'bin']) {
    current = path.join(current, member);
    const stat = fs.lstatSync(current, { throwIfNoEntry: false });
    if (!stat?.isDirectory() || stat.isSymbolicLink()) {
      throw new Error(`Installed TypeScript compiler has a missing or symbolic directory: ${current}`);
    }
  }
  return exactFile(path.join(current, 'tsc'), 'Installed TypeScript compiler');
}

function run(command, cwd, spawn, stdout, stderr) {
  const result = spawn(command[0], command.slice(1), {
    cwd,
    encoding: null,
    maxBuffer: 64 * 1024 * 1024,
    shell: false,
  });
  const capturedStdout = Buffer.from(result.stdout ?? []);
  const capturedStderr = Buffer.from(result.stderr ?? []);
  if (capturedStdout.length !== 0) stdout.write(capturedStdout);
  if (capturedStderr.length !== 0) stderr.write(capturedStderr);
  if (result.error) throw result.error;
  if (!Number.isInteger(result.status) || result.status !== 0 || result.signal !== null) {
    throw new Error(`JavaScript/TypeScript validation command failed: ${command[0]} (${result.status ?? result.signal})`);
  }
  return { command, exitCode: result.status, stderr: capturedStderr, stdout: capturedStdout };
}

function envelope(execution) {
  return `${JSON.stringify({
    command: execution.command,
    exitCode: execution.exitCode,
    schemaVersion: 1,
    stderrBase64: execution.stderr.toString('base64'),
    stdoutBase64: execution.stdout.toString('base64'),
  })}\n`;
}

function publish(cwd, name, execution) {
  const temporary = path.join(cwd, `.${name}.tmp`);
  fs.writeFileSync(temporary, envelope(execution), { encoding: 'utf8', flag: 'wx', mode: 0o600 });
  fs.renameSync(temporary, path.join(cwd, name));
}

export function runValidation({
  cwd = process.cwd(),
  executable = process.execPath,
  spawn = spawnSync,
  stdout = process.stdout,
  stderr = process.stderr,
  preflight = verifySelectedPackage,
} = {}) {
  cwd = path.resolve(cwd);
  removeOutputs(cwd);
  try {
    preflight(cwd);
    const typeScript = installedTypeScriptCompiler(cwd);
    const compiler = run([executable, typeScript, '--noEmit'], cwd, spawn, stdout, stderr);
    const tests = run([
      executable,
      '--test',
      '--test-reporter=junit',
      '--test-reporter-destination=packed-tests.xml',
      'smoke.cjs',
      'smoke.mjs',
    ], cwd, spawn, stdout, stderr);
    exactFile(path.join(cwd, 'public-api.json'), 'Packed public API evidence');
    exactFile(path.join(cwd, 'packed-tests.xml'), 'Packed consumer JUnit evidence');
    publish(cwd, 'typescript-execution.json', compiler);
    publish(cwd, 'packed-consumer-execution.json', tests);
  } catch (error) {
    removeOutputs(cwd);
    throw error;
  }
}

if (process.argv[1] && pathToFileURL(path.resolve(process.argv[1])).href === import.meta.url) {
  try {
    runValidation();
  } catch (error) {
    process.stderr.write(`${error?.stack ?? error}\n`);
    process.exitCode = 1;
  }
}
