import assert from 'node:assert/strict';
import {test, mock} from 'node:test';
import {createHash} from 'node:crypto';
import {Readable, Writable} from 'node:stream';
import {pipeline} from 'node:stream/promises';
import {createGzip, createGunzip, gzipSync} from 'node:zlib';
import {verify, main, cacheResponse} from './cache.mjs';
import {mkdtemp, mkdir, writeFile, readFile, rm, realpath} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';

test('unavailable cache transport falls back; transient failures retry; successful bodies still require verification', async () => {
  for (const status of [403, 404, 410, 429, 503]) {
    let calls = 0;
    assert.equal(await cacheResponse('https://example.invalid/', async () => {
      calls++;
      return new Response('unavailable', {status});
    }), null);
    assert.equal(calls, status === 429 || status >= 500 ? 3 : 1);
  }
  assert.equal(await cacheResponse('https://example.invalid/', async () => { throw new TypeError('network'); }), null);
  let calls = 0;
  const response = await cacheResponse('https://example.invalid/', async () => {
    calls++;
    return new Response('body', {status: calls === 1 ? 503 : 200});
  });
  assert.equal(calls, 2);
  assert.equal(await response.text(), 'body');
  await assert.rejects(cacheResponse('https://example.invalid/', async () => { throw new Error('programming defect'); }), /programming defect/);
});

test('restore reports unavailable cache as a miss without publishing; corrupt HTTP-success remains fatal', async () => {
  const directory = await realpath(await mkdtemp(join(tmpdir(), 'hydrated-transport-check-')));
  const previous = {...process.env};
  const body = Buffer.from('qualified original');
  const digest = createHash('sha256').update(body).digest('hex');
  const row = {bytes: body.length, sha256: `sha256:${digest}`};
  try {
    const manifest = join(directory, 'manifest.json');
    await writeFile(manifest, JSON.stringify([row]));
    Object.assign(process.env, {INPUT_MODE: 'restore', INPUT_ROOT: directory, INPUT_MANIFEST: manifest,
      INPUT_REPORT: join(directory, 'miss-report.json')});
    const client = {GetCacheEntryDownloadURL: async ({key}) =>
      ({ok: true, matchedKey: key, signedDownloadUrl: 'https://example.invalid/body'})};
    const request = mock.method(globalThis, 'fetch', async () => new Response('unavailable', {status: 503}));
    await main(client);
    const report = JSON.parse(await readFile(process.env.INPUT_REPORT));
    assert.equal(report.misses, 1);
    assert.equal(report.hits, 0);
    const file = join(directory, 'blobs', digest.slice(0, 2), digest);
    await assert.rejects(readFile(file), {code: 'ENOENT'});
    request.mock.mockImplementation(async () => new Response(gzipSync(Buffer.from('tampered'))));
    process.env.INPUT_REPORT = join(directory, 'corrupt-report.json');
    await assert.rejects(main(client), /identity mismatch/);
    await assert.rejects(readFile(file), {code: 'ENOENT'});
    await assert.rejects(readFile(process.env.INPUT_REPORT), {code: 'ENOENT'});
  } finally {
    mock.restoreAll();
    for (const key of Object.keys(process.env)) if (!(key in previous)) delete process.env[key];
    Object.assign(process.env, previous);
    await rm(directory, {recursive: true, force: true});
  }
});

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
