import assert from 'node:assert/strict';
import {test, mock} from 'node:test';
import {createHash} from 'node:crypto';
import {Readable, Writable} from 'node:stream';
import {pipeline} from 'node:stream/promises';
import {createGzip, createGunzip, gzipSync, gunzipSync} from 'node:zlib';
import {verify, main, cacheResponse, azureCacheChunks} from './cache.mjs';
import {BlockBlobClient} from '@azure/storage-blob';
import {mkdtemp, mkdir, writeFile, readFile, rm, realpath} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import fs from 'node:fs';
import {syncBuiltinESMExports} from 'node:module';

test('parallel Azure segments are bounded, ordered and pinned to one ETag', async () => {
  const size = 128 * 1024 ** 2 + 7;
  const calls = [];
  const client = {downloadToBuffer: async (offset, count, options) => {
    calls.push([offset, count]);
    assert.equal(options.concurrency, 8);
    assert.equal(options.blockSize, 8 * 1024 ** 2);
    assert.deepEqual(options.conditions, {ifMatch: '"immutable"'});
    assert.equal(options.abortSignal.aborted, false);
    return Buffer.alloc(count, calls.length);
  }};
  let total = 0, ordinal = 0;
  for await (const body of azureCacheChunks(client, {contentLength: size, etag: '"immutable"'}, size)) {
    assert.equal(body[0], ++ordinal);
    assert.equal(body.at(-1), ordinal);
    total += body.length;
  }
  assert.equal(total, size);
  assert.deepEqual(calls, [[0, 128 * 1024 ** 2], [128 * 1024 ** 2, 7]]);
  async function consume(client, properties) {
    for await (const _ of azureCacheChunks(client, properties, 10)) { /* consume */ }
  }
  const noRead = {downloadToBuffer: async () => assert.fail('Invalid properties reached body storage')};
  for (const contentLength of [-1, 11, 1.5, '1', null, Number.MAX_SAFE_INTEGER + 1])
    await assert.rejects(consume(noRead, {contentLength, etag: '"immutable"'}), /transport properties/);
  for (const etag of [undefined, '', 'W/"weak"', '"bad\nvalue"', '"' + 'a'.repeat(257) + '"'])
    await assert.rejects(consume(noRead, {contentLength: 1, etag}), /transport properties/);
  for (const body of [Buffer.alloc(1), Buffer.alloc(3), new Uint8Array(2)])
    await assert.rejects(consume({downloadToBuffer: async () => body},
      {contentLength: 2, etag: '"immutable"'}), /segment length/);
  const changed = Object.assign(Error('ETag changed'), {statusCode: 412});
  await assert.rejects(consume({downloadToBuffer: async () => { throw changed; }},
    {contentLength: 2, etag: '"immutable"'}), error => error === changed);
});

test('large Azure restore uses parallel bounded bytes through the same gzip and SHA publication gate', async () => {
  const directory = await realpath(await mkdtemp(join(tmpdir(), 'parallel-cache-')));
  const previous = {...process.env};
  try {
    const bytes = 256 * 1024 ** 2;
    const block = Buffer.alloc(1024 ** 2);
    const hash = createHash('sha256');
    for (let i = 0; i < 256; i++) hash.update(block);
    const digest = hash.digest('hex');
    const compressed = [];
    await pipeline(Readable.from((async function* () { for (let i = 0; i < 256; i++) yield block; })()),
      createGzip(), new Writable({write(chunk, _, done) { compressed.push(chunk); done(); }}));
    const archive = Buffer.concat(compressed);
    const manifest = join(directory, 'manifest.json'), report = join(directory, 'report.json');
    await writeFile(manifest, JSON.stringify([{bytes, sha256: `sha256:${digest}`} ]));
    Object.assign(process.env, {INPUT_MODE: 'restore', INPUT_ROOT: directory,
      INPUT_MANIFEST: manifest, INPUT_REPORT: report});
    mock.method(globalThis, 'fetch', () => assert.fail('Large Azure body used the sequential fetch'));
    mock.method(BlockBlobClient.prototype, 'getProperties', async () => ({contentLength: archive.length, etag: '"immutable"'}));
    const download = mock.method(BlockBlobClient.prototype, 'downloadToBuffer', async (offset, count, options) => {
      assert.equal(offset, 0);
      assert.equal(count, archive.length);
      assert.equal(options.conditions.ifMatch, '"immutable"');
      return archive;
    });
    const client = {GetCacheEntryDownloadURL: async ({key}) => ({ok: true, matchedKey: key,
      signedDownloadUrl: 'https://cache.blob.core.windows.net/fixture/body'})};
    await main(client);
    const stats = JSON.parse(await readFile(report));
    assert.equal(stats.parallelEntries, 1);
    assert.equal(stats.hits, 1);
    assert.equal(stats.hydratedBytes, bytes);
    assert.equal(stats.compressedBytes, archive.length);
    assert.equal((await fs.promises.stat(join(directory, 'blobs', digest.slice(0, 2), digest))).size, bytes);
    assert.equal(download.mock.callCount(), 1);
    await rm(report);
    await rm(join(directory, 'blobs', digest.slice(0, 2), digest));
    download.mock.mockImplementation(async () => Buffer.alloc(archive.length));
    await assert.rejects(main(client));
    await assert.rejects(readFile(join(directory, 'blobs', digest.slice(0, 2), digest)), {code: 'ENOENT'});
    await assert.rejects(readFile(report), {code: 'ENOENT'});
  } finally {
    mock.restoreAll();
    for (const key of Object.keys(process.env)) if (!(key in previous)) delete process.env[key];
    Object.assign(process.env, previous);
    await rm(directory, {recursive: true, force: true});
  }
});

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
