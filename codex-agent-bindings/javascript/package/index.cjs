'use strict';

if (typeof process === 'undefined' || !process.versions?.node) {
  throw new Error('@codex-agent-labs/codex-agent supports Node.js only');
}

const api = require('./dist/codex-agent-codex-agent-runtime-desktop.js');

function hideEnumerableProperties(value) {
  for (const key of Object.keys(value)) {
    Object.defineProperty(value, key, { enumerable: false });
  }
}

for (const value of Object.values(api)) {
  if (typeof value === 'function') {
    hideEnumerableProperties(value);
    if (value.prototype) hideEnumerableProperties(value.prototype);
  }
}

Object.defineProperty(api.CodexHost.prototype, Symbol.asyncDispose, {
  value: api.CodexHost.prototype.dispose,
});
Object.defineProperty(api.CodexConversation.prototype, Symbol.asyncDispose, {
  value: api.CodexConversation.prototype.dispose,
});
Object.defineProperty(api.CodexObservation.prototype, Symbol.dispose, {
  value: api.CodexObservation.prototype.dispose,
});

module.exports = api;
