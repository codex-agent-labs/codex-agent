// The JavaScript action supplies Actions cache service credentials to the child.
import {execFileSync, spawnSync} from 'node:child_process';
import {dirname, join, isAbsolute} from 'node:path';
import {fileURLToPath} from 'node:url';

const directory = dirname(fileURLToPath(import.meta.url));
if (!process.env.INPUT_SCRIPT?.trim()) throw Error('Missing caller capture command');
const root = process.env.CODEX_AGENT_HYDRATED_EVIDENCE ?? join(process.env.RUNNER_TEMP, 'hydrated-evidence');
if (!isAbsolute(root)) throw Error('Hydrated evidence root must be absolute');
execFileSync('npm', ['ci', '--ignore-scripts', '--no-audit', '--no-fund'], {cwd: directory, stdio: 'inherit'});
const result = spawnSync('bash', ['-e', '-o', 'pipefail', '-c', process.env.INPUT_SCRIPT], {
  stdio: 'inherit',
  env: {...process.env,
    CODEX_AGENT_HYDRATED_EVIDENCE: root,
    CODEX_AGENT_HOSTED_CACHE_BACKEND: join(directory, 'cache.mjs'),
    CODEX_AGENT_CACHE_NODE: process.execPath}
});
if (result.error) throw result.error;
process.exit(result.status ?? 1);
