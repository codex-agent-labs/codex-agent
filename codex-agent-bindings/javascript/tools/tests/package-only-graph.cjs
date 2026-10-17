const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');

test('SDK npm package phase has no Runtime compilation or linking dependency', () => {
  const root = path.resolve(__dirname, '../../../..');
  const fixture = fs.mkdtempSync(path.join(os.tmpdir(), 'codex-npm-package-graph-'));
  try {
    const result = spawnSync(path.join(root, 'gradlew'), [
      'ciProductPhase', '--dry-run', '--offline', '--console=plain',
      '-PcodexAgent.product=sdk', '-PcodexAgent.component=javascript',
      '-PcodexAgent.phase=package',
      `-PcodexAgent.contractBinaryStage=${fixture}`,
      `-PcodexAgent.runtimePackageStage=${fixture}`,
      '-PcodexAgent.runtimePackageVersion=0.8.0',
      `-PcodexAgent.candidateTree=${'a'.repeat(40)}`,
    ], { cwd: root, encoding: 'utf8', timeout: 120000 });
    const output = `${result.stdout || ''}\n${result.stderr || ''}`;
    assert.equal(result.status, 0, output);
    const tasks = [...output.matchAll(/^(:\S+) SKIPPED$/gm)].map((match) => match[1]);
    for (const name of ['stageNpmPackage', 'packageNpm', 'writeJavaScriptSdkPackageOutputManifest']) {
      assert.ok(tasks.includes(`:codex-agent-sdk:${name}`), output);
    }
    assert.ok(!tasks.some((task) =>
      task.startsWith(':codex-agent-runtime-desktop:') ||
      task.startsWith(':codex-agent-core:') ||
      /:(?:compile|link)[A-Z]/.test(task)), output);
  } finally {
    fs.rmSync(fixture, { recursive: true, force: true });
  }
});
