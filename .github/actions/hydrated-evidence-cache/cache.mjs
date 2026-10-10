// Raw gzip bodies, never tar extraction. The pinned official toolkit supplies
// the Actions cache service and upload protocol; no portable trust is stored.
import {internalCacheTwirpClient} from './node_modules/@actions/cache/lib/internal/shared/cacheTwirpClient.js';
import {saveCache} from './node_modules/@actions/cache/lib/internal/cacheHttpClient.js';
import {createReadStream, createWriteStream} from 'node:fs';
import {lstat, mkdir, readFile, link, rm, writeFile} from 'node:fs/promises';
import {createHash, randomUUID} from 'node:crypto';
import {isAbsolute, join, dirname} from 'node:path';
import {pipeline} from 'node:stream/promises';
import {Readable, Transform, Writable} from 'node:stream';
import {createGzip, createGunzip} from 'node:zlib';

import {pathToFileURL} from 'node:url';

export function verify(row) {
  let bytes = 0;
  const hash = createHash('sha256');
  return new Transform({
    transform(chunk, _, done) {
      bytes += chunk.length;
      if (bytes > row.bytes) return done(Error('Cache body exceeds immutable size'));
      hash.update(chunk);
      done(null, chunk);
    },
    flush(done) {
      done(bytes === row.bytes && `sha256:${hash.digest('hex')}` === row.sha256 ? null : Error('Cache content identity mismatch'));
    }
  });
}

export async function cacheResponse(url, fetchBody = fetch) {
  // An unavailable accelerator is a miss, not permission to bypass original admission.
  for (let attempt = 0; attempt < 3; attempt++) {
    let response;
    try { response = await fetchBody(url); }
    catch (error) { if (!(error instanceof TypeError)) throw error; }
    if (response?.ok) return response;
    if (response?.body) await response.body.cancel();
    if (response && response.status !== 408 && response.status !== 429 && response.status < 500) break;
  }
  console.warn('Cache transport unavailable; restoring authenticated original evidence instead');
  return null;
}


export async function main(client = internalCacheTwirpClient()) {
const mode = process.env.INPUT_MODE;
const root = process.env.INPUT_ROOT;
if (!['restore', 'save'].includes(mode) || !isAbsolute(root)) throw Error('Invalid cache operation');
const records = JSON.parse(await readFile(process.env.INPUT_MANIFEST, 'utf8'));
if (!Array.isArray(records) || records.length > 16384) throw Error('Invalid cache manifest');
const unique = new Map();
for (const row of records) {
  if (!/^sha256:[0-9a-f]{64}$/.test(row.sha256) || !Number.isSafeInteger(row.bytes) || row.bytes < 0 || row.bytes > 8 * 1024 ** 3)
    throw Error('Invalid cache content identity');
  if (unique.has(row.sha256) && unique.get(row.sha256).bytes !== row.bytes) throw Error('Ambiguous cache identity');
  unique.set(row.sha256, row);
}
const version = createHash('sha256').update('codex-hydrated-evidence-raw-gzip-v1').digest('hex');
const stats = {mode, entries: unique.size, hits: 0, misses: 0, saved: 0, compressedBytes: 0, hydratedBytes: 0};
const started = performance.now();


async function safeParents(path) {
  const parent = dirname(path);
  if (parent !== path) await safeParents(parent);
  try { await mkdir(path); } catch (error) { if (error.code !== 'EEXIST') throw error; }
  const info = await lstat(path);
  if (!info.isDirectory() || info.isSymbolicLink()) throw Error('Unsafe cache directory');
}

async function entry(row) {
  const digest = row.sha256.slice(7);
  const key = `codex-hydrated-raw-v1-${digest}`;
  const file = join(root, 'blobs', digest.slice(0, 2), digest);
  await safeParents(dirname(file));
  const temporary = join(dirname(file), `.cache-${randomUUID()}`);
  try {
    if (mode === 'restore') {
      let existing;
      try { existing = await lstat(file); }
      catch (error) { if (error.code !== 'ENOENT') throw error; }
      if (existing) {
        if (!existing.isFile() || existing.isSymbolicLink()) throw Error('Unsafe occupied cache body');
        await pipeline(createReadStream(file), verify(row), new Writable({write(_chunk, _encoding, done) { done(); }}));
        stats.hits++;
        stats.hydratedBytes += row.bytes;
        return;
      }
    }
    const found = await client.GetCacheEntryDownloadURL({key, restoreKeys: [], version});
    if (found.ok && found.matchedKey !== key) throw Error('Cache returned a different content identity');
    if (mode === 'restore') {
      if (!found.ok) { stats.misses++; return; }
      if (new URL(found.signedDownloadUrl).protocol !== 'https:') throw Error('Unsafe cache download URL');
      const response = await cacheResponse(found.signedDownloadUrl);
      if (response === null) { stats.misses++; return; }
      let compressed = 0;
      const count = new Transform({transform(chunk, _, done) {
        compressed += chunk.length;
        done(compressed > row.bytes + Math.ceil(row.bytes / 1000) + 65536 ? Error('Oversized cache transport') : null, chunk);
      }});
      await pipeline(Readable.fromWeb(response.body), count, createGunzip(), verify(row), createWriteStream(temporary, {flags: 'wx', mode: 0o600}));
      // Never replace an occupied CAS entry, including a symlink or partial file.
      try { await lstat(file); throw Error('Occupied cache destination'); }
      catch (error) { if (error.code !== 'ENOENT') throw error; }
      await link(temporary, file);
      stats.hits++;
      stats.compressedBytes += compressed;
      stats.hydratedBytes += row.bytes;
    } else {
      const info = await lstat(file);
      if (!info.isFile() || info.isSymbolicLink()) throw Error('Unsafe cache body');
      await pipeline(createReadStream(file), verify(row), createGzip(), createWriteStream(temporary, {flags: 'wx', mode: 0o600}));
      if (found.ok) { stats.hits++; return; }
      const reservation = await client.CreateCacheEntry({key, version});
      if (!reservation.ok) throw Error('Cache reservation failed');
      const size = (await lstat(temporary)).size;
      await saveCache(-1, temporary, reservation.signedUploadUrl, {useAzureSdk: true, archiveSizeBytes: size, uploadConcurrency: 2, uploadChunkSize: 32 * 1024 ** 2});
      const published = await client.FinalizeCacheEntryUpload({key, version, sizeBytes: String(size)});
      if (!published.ok) throw Error('Cache finalization failed');
      stats.saved++;
      stats.compressedBytes += size;
      stats.hydratedBytes += row.bytes;
    }
  } finally { await rm(temporary, {force: true}); }
}

// ponytail: two independent bodies in-process; no hosted fanout jobs.
const pending = [...unique.values()];
await Promise.all(Array.from({length: 2}, async () => {
  while (pending.length) await entry(pending.shift());
}));
stats.seconds = (performance.now() - started) / 1000;
await writeFile(process.env.INPUT_REPORT, JSON.stringify(stats, null, 2) + '\n', {flag: 'wx'});
console.log(JSON.stringify(stats));

}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) await main();
