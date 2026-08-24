import assert from 'node:assert/strict';
import { CodexHost, createCodexHost } from '@codex-agent-labs/codex-agent';

assert.equal(typeof CodexHost, 'function');
assert.equal(typeof createCodexHost, 'function');
