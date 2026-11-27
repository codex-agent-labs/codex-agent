import assert from 'node:assert/strict';
import {test} from 'node:test';
import {mkdtemp, mkdir, writeFile, readFile, rm, realpath} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join, delimiter} from 'node:path';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';

test('capture and later shell use the same caller cache; invalid roots fail before execution', async () => {
  const scratch = await realpath(await mkdtemp(join(tmpdir(), 'cache-execute-')));
  try {
    const bin = join(scratch, 'bin');
    await mkdir(bin);
    // Dependency installation is outside this local wiring check.
    await writeFile(join(bin, 'npm'), '#!/bin/sh\nexit 0\n', {mode: 0o700});
    const env = {...process.env, PATH: bin + delimiter + process.env.PATH, RUNNER_TEMP: scratch,
      INPUT_SCRIPT: 'printf "%s" "$CODEX_AGENT_HYDRATED_EVIDENCE" > "$RUNNER_TEMP/captured"'};
    for (const root of [join(scratch, 'approved reuse', 'hydrated-evidence'), undefined]) {
      if (root === undefined) delete env.CODEX_AGENT_HYDRATED_EVIDENCE;
      else env.CODEX_AGENT_HYDRATED_EVIDENCE = root;
      const result = spawnSync(process.execPath, [fileURLToPath(new URL('./execute.mjs', import.meta.url))], {env});
      assert.equal(result.status, 0, result.stderr.toString());
      assert.equal(await readFile(join(scratch, 'captured'), 'utf8'), root ?? join(scratch, 'hydrated-evidence'));
    }
    await rm(join(scratch, 'captured'));
    env.CODEX_AGENT_HYDRATED_EVIDENCE = 'relative-root';
    const result = spawnSync(process.execPath, [fileURLToPath(new URL('./execute.mjs', import.meta.url))], {env});
    assert.notEqual(result.status, 0);
    assert.match(result.stderr.toString(), /root must be absolute/);
    await assert.rejects(readFile(join(scratch, 'captured')), {code: 'ENOENT'});
  } finally { await rm(scratch, {recursive: true, force: true}); }
});
