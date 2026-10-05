import assert from 'node:assert/strict';
import {test} from 'node:test';
import {createHash} from 'node:crypto';
import {Readable, Writable} from 'node:stream';
import {pipeline} from 'node:stream/promises';
import {createGzip, createGunzip} from 'node:zlib';
import {verify, main} from './cache.mjs';
import {mkdtemp, mkdir, writeFile, readFile, rm, realpath} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';

test('gzip storage verifies exact bytes before publication; partial/tampered bodies fail', async () => {
  const body = Buffer.from('preserved original evidence');
  const row = {bytes: body.length, sha256: `sha256:${createHash('sha256').update(body).digest('hex')}`};
  let restored = Buffer.alloc(0);
  const sink = () => new Writable({write(chunk, _, done) { restored = Buffer.concat([restored, chunk]); done(); }});
  await pipeline(Readable.from([body]), createGzip(), createGunzip(), verify(row), sink());
  assert.deepEqual(restored, body);
  for (const candidate of [Buffer.from('tampered original evidence'), body.subarray(0, 3), Buffer.concat([body, body])]) {
    await assert.rejects(pipeline(Readable.from([candidate]), createGzip(), createGunzip(), verify(row), sink()), /identity mismatch|exceeds immutable size/);
  }
  await assert.rejects(pipeline(Readable.from([body]), verify({...row, sha256: 'sha256:' + '0'.repeat(64)}), sink()), /identity mismatch/);
});

test('repeated restores freshly verify occupied bodies and reject corruption', async () => {
  const directory = await realpath(await mkdtemp(join(tmpdir(), 'hydrated-storage-check-')));
  const previous = {...process.env};
  try {
    const body = Buffer.from('existing qualified body');
    const digest = createHash('sha256').update(body).digest('hex');
    const row = {sha256: `sha256:${digest}`, bytes: body.length};
    const file = join(directory, 'blobs', digest.slice(0, 2), digest);
    await mkdir(join(directory, 'blobs', digest.slice(0, 2)), {recursive: true});
    await writeFile(file, body);
    const manifest = join(directory, 'manifest.json');
    await writeFile(manifest, JSON.stringify([row]));
    Object.assign(process.env, {INPUT_MODE: 'restore', INPUT_ROOT: directory, INPUT_MANIFEST: manifest,
      ACTIONS_RUNTIME_TOKEN: 'local-check-only', ACTIONS_CACHE_SERVICE_V2: 'true', ACTIONS_RESULTS_URL: 'https://example.invalid/'});
    for (let attempt = 0; attempt < 2; attempt++) {
      process.env.INPUT_REPORT = join(directory, `report-${attempt}.json`);
      await main();
      const report = JSON.parse(await readFile(process.env.INPUT_REPORT));
      assert.equal(report.hits, 1);
      assert.equal(report.compressedBytes, 0);
    }
    await writeFile(file, 'corrupt');
    process.env.INPUT_REPORT = join(directory, 'corruption.json');
    await assert.rejects(main(), /identity mismatch/);
  } finally {
    for (const key of Object.keys(process.env)) if (!(key in previous)) delete process.env[key];
    Object.assign(process.env, previous);
    await rm(directory, {recursive: true, force: true});
  }
});
