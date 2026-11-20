import assert from 'node:assert/strict';
import {test, mock} from 'node:test';
import {createHash} from 'node:crypto';
import {Readable, Writable} from 'node:stream';
import {pipeline} from 'node:stream/promises';
import {createGzip, createGunzip, gzipSync, gunzipSync} from 'node:zlib';
import {verify, main, cacheResponse} from './cache.mjs';
import {mkdtemp, mkdir, writeFile, readFile, rm, realpath} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join, dirname} from 'node:path';
import fs from 'node:fs';
import fsPromises from 'node:fs/promises';
import {syncBuiltinESMExports} from 'node:module';

test('cache service failures and competing saves preserve original bytes; integrity and defects remain fatal', async () => {
  const root = await realpath(await mkdtemp(join(tmpdir(), 'cache-outage-')));
  const previous = {...process.env};
  try {
    const body = Buffer.from('verified original');
    const digest = createHash('sha256').update(body).digest('hex');
    const file = join(root, 'blobs', digest.slice(0, 2), digest);
    await mkdir(join(root, 'blobs', digest.slice(0, 2)), {recursive: true});
    const manifest = join(root, 'manifest.json'), report = join(root, 'report.json');
    await writeFile(manifest, JSON.stringify([{bytes: body.length, sha256: `sha256:${digest}`} ]));
    Object.assign(process.env, {INPUT_ROOT: root, INPUT_MANIFEST: manifest, INPUT_REPORT: report});
    // Windows rejects mkdir on an existing drive root with EPERM, not EEXIST.
    const realMkdir = fsPromises.mkdir;
    mock.method(fsPromises, 'mkdir', async (path, ...options) => {
      if (dirname(path) === path) throw Object.assign(Error('Cannot create drive root'), {code: 'EPERM'});
      return realMkdir(path, ...options);
    });
    syncBuiltinESMExports();
    const outage = () => { throw Object.assign(Error('connection reset'), {code: 'ECONNRESET'}); };
    process.env.INPUT_MODE = 'restore';
    await main({GetCacheEntryDownloadURL: outage});
    assert.equal(JSON.parse(await readFile(report)).misses, 1);
    await assert.rejects(readFile(file), {code: 'ENOENT'});
    await rm(report);
    process.env.INPUT_MODE = 'save';
    await writeFile(file, body);
    for (const failure of ['lookup', 'reservation', 'upload', 'finalization']) {
      const client = {
        GetCacheEntryDownloadURL: failure === 'lookup' ? outage : async () => ({ok: false}),
        CreateCacheEntry: async () => ({ok: failure !== 'reservation', signedUploadUrl: 'https://example.invalid/upload'}),
        FinalizeCacheEntryUpload: async () => ({ok: false})
      };
      await main(client, failure === 'upload' ? outage : async () => {});
      const stats = JSON.parse(await readFile(report));
      assert.equal(stats.saved, 0);
      assert.equal(stats.skipped, 1);
      assert.deepEqual(await readFile(file), body);
      await rm(report);
    }
    await writeFile(file, Buffer.alloc(body.length));
    await assert.rejects(main({GetCacheEntryDownloadURL: outage}), /identity mismatch/);
    await assert.rejects(main({GetCacheEntryDownloadURL: async () => { throw Error('programming defect'); }}), /programming defect/);
    await assert.rejects(main({GetCacheEntryDownloadURL: async () => ({})}), /Malformed cache lookup/);
    await assert.rejects(main({GetCacheEntryDownloadURL: async ({key}) => ({ok: true, matchedKey: key + '-wrong'})}), /different content identity/);
    await assert.rejects(readFile(report), {code: 'ENOENT'});
  } finally {
    mock.restoreAll();
    syncBuiltinESMExports();
    for (const key of Object.keys(process.env)) if (!(key in previous)) delete process.env[key];
    Object.assign(process.env, previous);
    await rm(root, {recursive: true, force: true});
  }
});

test('save hits verify every byte without a gzip file or upload; corrupt hits fail', async () => {
  const directory = await realpath(await mkdtemp(join(tmpdir(), 'hydrated-save-hit-')));
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
    Object.assign(process.env, {INPUT_MODE: 'save', INPUT_ROOT: directory, INPUT_MANIFEST: manifest,
      INPUT_REPORT: join(directory, 'report.json')});
    const client = {GetCacheEntryDownloadURL: async ({key}) => ({ok: true, matchedKey: key}),
      CreateCacheEntry: async () => assert.fail('A save hit must not reserve an upload')};
    mock.method(fs, 'createWriteStream', () => assert.fail('A save hit must not write a gzip file'));
    syncBuiltinESMExports();
    await main(client);
    const report = JSON.parse(await readFile(process.env.INPUT_REPORT));
    assert.equal(report.hits, 1);
    assert.equal(report.saved, 0);
    assert.equal(report.compressedBytes, 0);
    assert.deepEqual(await readFile(file), body);
    for (const corrupt of [Buffer.alloc(body.length), body.subarray(0, 3), Buffer.concat([body, body])]) {
      await writeFile(file, corrupt);
      process.env.INPUT_REPORT = join(directory, 'corrupt-report.json');
      await assert.rejects(main(client), /identity mismatch|exceeds immutable size/);
      await assert.rejects(readFile(process.env.INPUT_REPORT), {code: 'ENOENT'});
    }
    await assert.rejects(main({GetCacheEntryDownloadURL: async () => ({ok: true, matchedKey: 'wrong'})}),
      /different content identity/);
  } finally {
    mock.restoreAll();
    syncBuiltinESMExports();
    for (const key of Object.keys(process.env)) if (!(key in previous)) delete process.env[key];
    Object.assign(process.env, previous);
    await rm(directory, {recursive: true, force: true});
  }
});

test('compressed-body hint skips compression without changing keys, decoding or full-byte verification', async () => {
  const directory = await realpath(await mkdtemp(join(tmpdir(), 'hydrated-compression-')));
  const previous = {...process.env};
  try {
    const body = Buffer.alloc(128 * 1024, 'a');
    const digest = createHash('sha256').update(body).digest('hex');
    const row = {sha256: `sha256:${digest}`, bytes: body.length};
    const file = join(directory, 'blobs', digest.slice(0, 2), digest);
    const manifest = join(directory, 'manifest.json'), report = join(directory, 'report.json');
    await mkdir(join(directory, 'blobs', digest.slice(0, 2)), {recursive: true});
    Object.assign(process.env, {INPUT_ROOT: directory, INPUT_MANIFEST: manifest, INPUT_REPORT: report});
    const identity = {key: `codex-hydrated-raw-v1-${digest}`, version: createHash('sha256')
      .update('codex-hydrated-evidence-raw-gzip-v1').digest('hex')};
    for (const hint of [{}, {gzipLevel: 0}]) {
      await writeFile(file, body);
      await writeFile(manifest, JSON.stringify([{...row, ...hint}]));
      process.env.INPUT_MODE = 'save';
      let uploaded;
      const client = {
        GetCacheEntryDownloadURL: async (request) => {
          assert.deepEqual(request, {...identity, restoreKeys: []});
          return {ok: false};
        },
        CreateCacheEntry: async (request) => {
          assert.deepEqual(request, identity);
          return {ok: true, signedUploadUrl: 'https://example.invalid/upload'};
        },
        FinalizeCacheEntryUpload: async (request) => {
          assert.deepEqual(request, {...identity, sizeBytes: String(uploaded.length)});
          return {ok: true};
        }
      };
      await main(client, async (_id, path) => { uploaded = await readFile(path); });
      assert.deepEqual(gunzipSync(uploaded), body);
      assert.ok(hint.gzipLevel === 0 ? uploaded.length > body.length : uploaded.length < 1000);
      assert.equal(JSON.parse(await readFile(report)).saved, 1);
      await rm(report);
      await writeFile(file, Buffer.alloc(body.length));
      await assert.rejects(main(client), /identity mismatch/);
      await rm(file);
      // Legacy callers decode either transport without needing the hint.
      await writeFile(manifest, JSON.stringify([row]));
      process.env.INPUT_MODE = 'restore';
      mock.method(globalThis, 'fetch', async () => new Response(uploaded));
      await main({GetCacheEntryDownloadURL: async (request) => {
        assert.deepEqual(request, {...identity, restoreKeys: []});
        return {ok: true, matchedKey: identity.key, signedDownloadUrl: 'https://example.invalid/body'};
      }});
      assert.deepEqual(await readFile(file), body);
      assert.equal(JSON.parse(await readFile(report)).hits, 1);
      await rm(report);
      mock.restoreAll();
    }
    for (const invalid of [-1, 1, null, false, '0', {}]) {
      await writeFile(manifest, JSON.stringify([{...row, gzipLevel: invalid}]));
      await assert.rejects(main({GetCacheEntryDownloadURL: async () => assert.fail('Invalid hint reached service')}),
        /Invalid cache compression hint/);
    }
  } finally {
    mock.restoreAll();
    for (const key of Object.keys(process.env)) if (!(key in previous)) delete process.env[key];
    Object.assign(process.env, previous);
    await rm(directory, {recursive: true, force: true});
  }
});

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
