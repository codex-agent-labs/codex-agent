'use strict';

const assert = require('node:assert/strict');
const childProcess = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');

const sdk = require('@codex-agent-labs/codex-agent');

async function settleCallbacks() {
  await new Promise((resolve) => setImmediate(resolve));
}

test('cjs exposes the exact Node-only SDK surface', () => {
  assert.equal(process.version, 'v24.18.0');
  process.argv.push('--not-an-evidence-argument');
  assert.equal(typeof sdk.createCodexHost, 'function');
  assert.equal(typeof sdk.codexApprovalPresetDisplayName, 'function');
  assert.equal(typeof sdk.agentSkillScopeDisplayName, 'function');
  assert.equal(typeof sdk.agentCapabilityId, 'function');
  assert.equal(typeof sdk.agentCapabilityDisplayLabel, 'function');
  assert.equal(typeof sdk.agentCapabilityIcon, 'function');
  assert.equal(typeof sdk.agentCapabilityPromptLabel, 'function');
  assert.equal(typeof sdk.CodexAuthorizationUrl, 'function');
  assert.throws(
    () => new sdk.CodexAuthorizationUrl(),
    (error) => error?.message === 'Codex authorization URLs are created by the SDK',
  );
  const chatGptAuthorizationUrl = sdk.CodexAuthorizationUrl.chatGpt(
    'https://AUTH.OPENAI.COM/authorize?client=cjs',
  );
  const externalAuthorizationUrl = sdk.CodexAuthorizationUrl.external(
    'http://localhost:8787/callback',
  );
  assert.deepEqual(
    [chatGptAuthorizationUrl.value, chatGptAuthorizationUrl.purpose],
    ['https://AUTH.OPENAI.COM/authorize?client=cjs', 'chat_gpt'],
  );
  assert.deepEqual(
    [externalAuthorizationUrl.value, externalAuthorizationUrl.purpose],
    ['http://localhost:8787/callback', 'external'],
  );
  assert.equal(Object.isFrozen(chatGptAuthorizationUrl), true);
  assert.equal(Object.isFrozen(externalAuthorizationUrl), true);
  assert.throws(
    () => sdk.CodexAuthorizationUrl.chatGpt('https://example.com/login'),
    (error) => error?.message === 'ChatGPT authorization URL uses an untrusted host',
  );
  assert.throws(
    () => sdk.CodexAuthorizationUrl.external('http://example.com/login'),
    (error) => error?.message === 'Authorization URL is not HTTPS or loopback HTTP',
  );
  for (const invalid of [0, null, undefined, new String('https://auth.openai.com/'), new Proxy({}, {})]) {
    assert.throws(
      () => sdk.CodexAuthorizationUrl.chatGpt(invalid),
      (error) => error?.message === 'value must be a string',
    );
    assert.throws(
      () => sdk.CodexAuthorizationUrl.external(invalid),
      (error) => error?.message === 'value must be a string',
    );
  }
  for (const [clientInfo, message] of [
    [[Object.create(null), 'Client', '1.0'], 'clientName must be a string'],
    [['client', [], '1.0'], 'clientTitle must be a string'],
    [['client', 'Client', new String('1.0')], 'clientVersion must be a string'],
    [[' ', 'Client', '1.0'], 'Client name must not be blank or contain control characters'],
    [['client\u0000', 'Client', '1.0'], 'Client name must not be blank or contain control characters'],
    [['client', ' ', '1.0'], 'Client title must not be blank or contain control characters'],
    [['client', 'Client\u0000', '1.0'], 'Client title must not be blank or contain control characters'],
    [['client', 'Client', ' '], 'Client version must not be blank or contain control characters'],
    [['client', 'Client', '1.0\u0000'], 'Client version must not be blank or contain control characters'],
  ]) {
    assert.throws(
      () => sdk.createCodexHost('/bundle', '/data', ...clientInfo),
      (error) => error?.message === message,
    );
  }
  assert.deepEqual(
    ['never', 'auto_review', 'ask_me', 'strict'].map((preset) =>
      sdk.codexApprovalPresetDisplayName(preset)),
    ['Never', 'Auto review', 'Ask me', 'Strict'],
  );
  assert.throws(() => sdk.codexApprovalPresetDisplayName('AUTO_REVIEW'));
  assert.throws(() => sdk.codexApprovalPresetDisplayName(0));
  assert.deepEqual(
    ['admin', 'plugin', 'repo', 'system', 'user'].map((scope) =>
      sdk.agentSkillScopeDisplayName(scope)),
    ['Managed', 'Plugin', 'Workspace', 'Built in', 'User'],
  );
  for (const [invalid, message] of [
    ['unknown', 'Unknown skill scope: unknown'],
    ['SYSTEM', 'Unknown skill scope: SYSTEM'],
    [0, 'scope must be a string'],
    [null, 'scope must be a string'],
    [undefined, 'scope must be a string'],
    [new String('system'), 'scope must be a string'],
    [new Proxy({}, {}), 'scope must be a string'],
  ]) {
    assert.throws(
      () => sdk.agentSkillScopeDisplayName(invalid),
      (error) => error?.message === message,
    );
  }
  for (const [project, expected] of [
    [sdk.agentCapabilityId, 'web_search'],
    [sdk.agentCapabilityDisplayLabel, 'Web search'],
    [sdk.agentCapabilityIcon, '🌐'],
    [sdk.agentCapabilityPromptLabel, 'Use 🌐 Web search'],
  ]) {
    assert.equal(project('web_search'), expected);
    for (const [invalid, message] of [
      ['unknown', 'Unknown agent capability: unknown'],
      ['WEB_SEARCH', 'Unknown agent capability: WEB_SEARCH'],
      [0, 'capability must be a string'],
      [null, 'capability must be a string'],
      [undefined, 'capability must be a string'],
      [new String('web_search'), 'capability must be a string'],
      [new Proxy({}, {}), 'capability must be a string'],
    ]) {
      assert.throws(() => project(invalid), (error) => error?.message === message);
    }
  }
  assert.throws(() => new sdk.CodexHost());
  assert.throws(() => new sdk.CodexAgent());
  assert.throws(() => new sdk.CodexAuthentication());
  assert.throws(() => new sdk.CodexConnectors());
  assert.throws(() => new sdk.CodexModels());
  assert.throws(() => new sdk.CodexSkills());
  assert.throws(() => new sdk.CodexHooks());
  assert.throws(() => new sdk.CodexMcpServers());
  assert.throws(() => new sdk.CodexAuthenticationState());
  assert.throws(() => new sdk.CodexConversation());
  assert.throws(() => new sdk.CodexObservation());
  assert.equal(typeof sdk.CodexAgent.prototype.rename, 'function');
  assert.equal(typeof sdk.CodexAgent.prototype.delete, 'function');
  assert.equal(typeof sdk.CodexAgent.prototype.listConversations, 'function');
  assert.equal(typeof sdk.CodexAgent.prototype.readConversation, 'function');
  assert.equal(typeof sdk.CodexConversation.prototype.sendRequest, 'function');
  assert.equal(typeof Object.getOwnPropertyDescriptor(sdk.CodexAgent.prototype, 'skills')?.get, 'function');
  assert.equal(typeof sdk.CodexSkills.prototype.list, 'function');
  assert.equal(typeof sdk.CodexSkills.prototype.read, 'function');
  assert.equal(typeof sdk.CodexSkills.prototype.install, 'function');
  assert.equal(typeof sdk.CodexSkills.prototype.uninstall, 'function');
  assert.equal(typeof Object.getOwnPropertyDescriptor(sdk.CodexAgent.prototype, 'hooks')?.get, 'function');
  assert.equal(typeof sdk.CodexHooks.prototype.list, 'function');
  assert.equal(typeof sdk.CodexHooks.prototype.install, 'function');
  assert.equal(typeof sdk.CodexHooks.prototype.uninstall, 'function');
  assert.equal(typeof sdk.CodexHooks.prototype.trust, 'function');
  assert.equal(typeof Object.getOwnPropertyDescriptor(sdk.CodexAgent.prototype, 'mcpServers')?.get, 'function');
  assert.equal(typeof sdk.CodexMcpServers.prototype.list, 'function');
  assert.equal(typeof sdk.CodexMcpServers.prototype.add, 'function');
  assert.equal(typeof sdk.CodexMcpServers.prototype.remove, 'function');
  for (const constructor of [
    sdk.AgentConnector,
    sdk.AgentConversation,
    sdk.AgentConversationSummary,
    sdk.AgentElicitationValidation,
    sdk.AgentElicitationValidationIssue,
    sdk.AgentFormBooleanValue,
    sdk.AgentFormNumberValue,
    sdk.AgentFormOption,
    sdk.AgentFormTextListValue,
    sdk.AgentFormTextValue,
    sdk.AgentHookActivity,
    sdk.AgentHook,
    sdk.AgentHookCatalog,
    sdk.AgentMcpEnvironmentVariable,
    sdk.AgentMcpOauthConfiguration,
    sdk.AgentMcpToolConfiguration,
    sdk.AgentMcpStdioTransport,
    sdk.AgentMcpHttpTransport,
    sdk.AgentMcpServerConfiguration,
    sdk.AgentMcpServer,
    sdk.AgentModel,
    sdk.AgentPlanProgress,
    sdk.AgentPlanStep,
    sdk.AgentPluginInvocation,
    sdk.AgentServiceTier,
    sdk.AgentSkill,
    sdk.AgentSkillCatalog,
    sdk.AgentSkillChunk,
    sdk.AgentSkillInvocation,
    sdk.CodexAgent,
    sdk.CodexAuthentication,
    sdk.CodexAuthenticationState,
    sdk.CodexConnectors,
    sdk.CodexConversation,
    sdk.CodexConversationState,
    sdk.CodexError,
    sdk.CodexFailure,
    sdk.CodexHost,
    sdk.CodexHostState,
    sdk.CodexMessage,
    sdk.CodexModels,
    sdk.CodexSkills,
    sdk.CodexHooks,
    sdk.CodexMcpServers,
    sdk.CodexObservation,
    sdk.CodexTurnProgress,
    sdk.CodexWorkspace,
  ]) {
    assert.deepEqual(Object.keys(constructor), []);
    assert.deepEqual(Object.keys(constructor.prototype), []);
  }

  const option = new sdk.AgentFormOption('value');
  assert.equal(option.value, 'value');
  assert.equal(option.title, 'value');
  assert.equal(option.description, null);
  assert.equal(Object.isFrozen(option), true);
  const describedOption = new sdk.AgentFormOption('custom', 'Custom title', 'Custom description');
  assert.equal(describedOption.value, 'custom');
  assert.equal(describedOption.title, 'Custom title');
  assert.equal(describedOption.description, 'Custom description');
  assert.throws(() => new sdk.AgentFormOption({ mutable: true }));
  assert.throws(() => new sdk.AgentFormOption('value', { mutable: true }));
  assert.throws(() => new sdk.AgentFormOption('value', 'title', { mutable: true }));

  const textValue = new sdk.AgentFormTextValue('');
  assert.equal(textValue.value, '');
  for (const invalid of [
    null,
    undefined,
    0,
    -0,
    NaN,
    Infinity,
    -Infinity,
    false,
    1n,
    Symbol('value'),
    {},
    [],
    () => {},
    new String('value'),
    new Number(1),
    new Boolean(true),
    new Proxy({}, {}),
  ]) {
    assert.throws(() => new sdk.AgentFormTextValue(invalid));
  }

  const numericEdges = [NaN, Infinity, -Infinity, -0, 0, Number.MIN_VALUE, Number.MAX_VALUE];
  const numberValues = numericEdges.map((value) => new sdk.AgentFormNumberValue(value));
  numberValues.forEach((numberValue, index) => {
    assert.equal(Object.is(numberValue.value, numericEdges[index]), true);
  });
  for (const invalid of [
    null,
    undefined,
    '',
    '1',
    false,
    true,
    1n,
    Symbol('value'),
    {},
    [],
    () => {},
    new String('1'),
    new Number(1),
    new Boolean(false),
    new Proxy({}, {}),
  ]) {
    assert.throws(() => new sdk.AgentFormNumberValue(invalid));
  }

  const falseValue = new sdk.AgentFormBooleanValue(false);
  const trueValue = new sdk.AgentFormBooleanValue(true);
  assert.equal(falseValue.value, false);
  assert.equal(trueValue.value, true);
  for (const invalid of [
    null,
    undefined,
    '',
    'false',
    0,
    1,
    NaN,
    Infinity,
    1n,
    Symbol('value'),
    {},
    [],
    () => {},
    new String('false'),
    new Number(0),
    new Boolean(false),
    new Proxy({}, {}),
  ]) {
    assert.throws(() => new sdk.AgentFormBooleanValue(invalid));
  }

  const emptyTextListValue = new sdk.AgentFormTextListValue([]);
  assert.deepEqual(emptyTextListValue.value, []);
  const sourceTextList = ['', 'duplicate', 'duplicate'];
  const textListValue = new sdk.AgentFormTextListValue(sourceTextList);
  assert.notEqual(textListValue.value, sourceTextList);
  assert.deepEqual(textListValue.value, ['', 'duplicate', 'duplicate']);
  sourceTextList.splice(0, sourceTextList.length, 'mutated');
  assert.deepEqual(textListValue.value, ['', 'duplicate', 'duplicate']);
  const proxyTextListTarget = ['first', 'second'];
  const proxyTextListInput = new Proxy(proxyTextListTarget, {});
  const proxyTextListValue = new sdk.AgentFormTextListValue(proxyTextListInput);
  assert.notEqual(proxyTextListValue.value, proxyTextListInput);
  assert.notEqual(proxyTextListValue.value, proxyTextListTarget);
  proxyTextListTarget.reverse();
  assert.deepEqual(proxyTextListValue.value, ['first', 'second']);

  for (const invalid of [
    null,
    undefined,
    '',
    0,
    false,
    1n,
    Symbol('value'),
    {},
    { 0: 'value', length: 1 },
    () => {},
    new String('value'),
    new Number(1),
    new Boolean(true),
    new Proxy({ 0: 'value', length: 1 }, {}),
  ]) {
    assert.throws(() => new sdk.AgentFormTextListValue(invalid));
  }
  const sparseTextList = new Array(2);
  sparseTextList[1] = 'value';
  assert.throws(() => new sdk.AgentFormTextListValue(sparseTextList));
  const inheritedSparseTextList = new Array(1);
  Object.setPrototypeOf(inheritedSparseTextList, { 0: 'inherited' });
  assert.equal(Object.hasOwn(inheritedSparseTextList, 0), false);
  assert.throws(() => new sdk.AgentFormTextListValue(inheritedSparseTextList));
  const proxiedSparseTextList = new Proxy(inheritedSparseTextList, {});
  assert.throws(() => new sdk.AgentFormTextListValue(proxiedSparseTextList));
  const revokedTextList = Proxy.revocable(['value'], {});
  revokedTextList.revoke();
  assert.throws(() => new sdk.AgentFormTextListValue(revokedTextList.proxy));
  for (const invalid of [
    null,
    undefined,
    0,
    false,
    1n,
    Symbol('value'),
    {},
    [],
    ['nested'],
    () => {},
    new String('value'),
    new Number(1),
    new Boolean(true),
    new Proxy({}, {}),
  ]) {
    assert.throws(() => new sdk.AgentFormTextListValue([invalid]));
  }

  const defaultMcpEnvironmentVariable = new sdk.AgentMcpEnvironmentVariable('TOKEN');
  const undefinedMcpEnvironmentVariable = new sdk.AgentMcpEnvironmentVariable('TOKEN', undefined);
  const nullMcpEnvironmentVariable = new sdk.AgentMcpEnvironmentVariable('TOKEN', null);
  assert.equal(defaultMcpEnvironmentVariable.source, null);
  assert.equal(undefinedMcpEnvironmentVariable.source, null);
  assert.equal(nullMcpEnvironmentVariable.source, null);
  const mcpEnvironmentSources = ['local', 'remote'];
  const mcpEnvironmentVariables = mcpEnvironmentSources.map(
    (source) => new sdk.AgentMcpEnvironmentVariable('TOKEN', source),
  );
  assert.deepEqual(mcpEnvironmentVariables.map(({ source }) => source), mcpEnvironmentSources);
  const permissiveMcpEnvironmentNames = [' TOKEN ', 'TOKEN\u0000SUFFIX'];
  const permissiveMcpEnvironmentVariables = permissiveMcpEnvironmentNames.map(
    (name) => new sdk.AgentMcpEnvironmentVariable(name),
  );
  assert.deepEqual(permissiveMcpEnvironmentVariables.map(({ name }) => name), permissiveMcpEnvironmentNames);
  for (const invalidName of [
    '',
    ' ',
    '\t\n',
    null,
    undefined,
    0,
    -0,
    NaN,
    Infinity,
    -Infinity,
    false,
    true,
    1n,
    Symbol('name'),
    {},
    [],
    () => {},
    new String('TOKEN'),
    new Number(0),
    new Boolean(false),
    new Proxy({}, {}),
  ]) {
    assert.throws(() => new sdk.AgentMcpEnvironmentVariable(invalidName));
  }
  for (const invalidSource of [
    '',
    ' ',
    'LOCAL',
    'Local',
    'unknown',
    0,
    -0,
    NaN,
    Infinity,
    -Infinity,
    false,
    true,
    1n,
    Symbol('source'),
    {},
    [],
    () => {},
    new String('local'),
    new Number(0),
    new Boolean(false),
    new Proxy({}, {}),
  ]) {
    assert.throws(() => new sdk.AgentMcpEnvironmentVariable('TOKEN', invalidSource));
  }

  const defaultMcpOauthConfiguration = new sdk.AgentMcpOauthConfiguration();
  const undefinedMcpOauthConfiguration = new sdk.AgentMcpOauthConfiguration(undefined, undefined);
  const nullMcpOauthConfiguration = new sdk.AgentMcpOauthConfiguration(null, null);
  for (const configuration of [
    defaultMcpOauthConfiguration,
    undefinedMcpOauthConfiguration,
    nullMcpOauthConfiguration,
  ]) {
    assert.equal(configuration.clientId, null);
    assert.equal(configuration.callbackPort, null);
  }
  const blankMcpOauthConfiguration = new sdk.AgentMcpOauthConfiguration('', null);
  const whitespaceMcpOauthConfiguration = new sdk.AgentMcpOauthConfiguration(' \t\n', null);
  assert.equal(blankMcpOauthConfiguration.clientId, '');
  assert.equal(whitespaceMcpOauthConfiguration.clientId, ' \t\n');
  const minimumMcpOauthPort = new sdk.AgentMcpOauthConfiguration('client', 1);
  const maximumMcpOauthPort = new sdk.AgentMcpOauthConfiguration('client', 65535);
  assert.equal(minimumMcpOauthPort.callbackPort, 1);
  assert.equal(maximumMcpOauthPort.callbackPort, 65535);
  for (const invalidClientId of [
    0,
    -0,
    NaN,
    Infinity,
    -Infinity,
    false,
    true,
    1n,
    Symbol('clientId'),
    {},
    [],
    () => {},
    new String('client'),
    new Number(0),
    new Boolean(false),
    new Proxy({}, {}),
  ]) {
    assert.throws(() => new sdk.AgentMcpOauthConfiguration(invalidClientId));
  }
  for (const invalidPort of [
    0,
    -0,
    -1,
    65536,
    1.5,
    -1.5,
    Number.MIN_VALUE,
    NaN,
    Infinity,
    -Infinity,
    '',
    '1',
    false,
    true,
    1n,
    Symbol('callbackPort'),
    {},
    [],
    () => {},
    new Number(1),
    new String('1'),
    new Boolean(false),
    new Proxy({}, {}),
  ]) {
    assert.throws(() => new sdk.AgentMcpOauthConfiguration(null, invalidPort));
  }

  const defaultMcpToolConfiguration = new sdk.AgentMcpToolConfiguration();
  const undefinedMcpToolConfiguration = new sdk.AgentMcpToolConfiguration(undefined);
  const nullMcpToolConfiguration = new sdk.AgentMcpToolConfiguration(null);
  assert.equal(defaultMcpToolConfiguration.approval, null);
  assert.equal(undefinedMcpToolConfiguration.approval, null);
  assert.equal(nullMcpToolConfiguration.approval, null);
  const mcpToolApprovals = ['approve', 'auto', 'prompt', 'writes'];
  const mcpToolConfigurations = mcpToolApprovals.map(
    (approval) => new sdk.AgentMcpToolConfiguration(approval),
  );
  assert.deepEqual(mcpToolConfigurations.map(({ approval }) => approval), mcpToolApprovals);
  for (const invalid of [
    '',
    ' ',
    'APPROVE',
    'Approve',
    'unknown',
    0,
    -0,
    NaN,
    Infinity,
    -Infinity,
    true,
    false,
    1n,
    Symbol('approval'),
    {},
    [],
    ['approve'],
    () => {},
    new String('approve'),
    new Number(0),
    new Boolean(false),
    new Proxy({}, {}),
    new Proxy(new String('approve'), {}),
  ]) {
    assert.throws(() => new sdk.AgentMcpToolConfiguration(invalid));
  }

  const defaultStdioTransport = new sdk.AgentMcpStdioTransport('node');
  assert.deepEqual(
    [
      defaultStdioTransport.command,
      defaultStdioTransport.arguments,
      defaultStdioTransport.workingDirectory,
      defaultStdioTransport.environment,
      defaultStdioTransport.forwardedEnvironment,
    ],
    ['node', [], null, null, []],
  );
  const sourceArguments = ['server.js', '--stdio'];
  const sourceEnvironment = { TOKEN: 'secret', EMPTY: '' };
  const sourceForwardedEnvironment = [new sdk.AgentMcpEnvironmentVariable('HOME', 'local')];
  const stdioTransport = new sdk.AgentMcpStdioTransport(
    'node', sourceArguments, '/workspace', sourceEnvironment, sourceForwardedEnvironment,
  );
  sourceArguments[0] = 'changed';
  sourceEnvironment.TOKEN = 'changed';
  sourceForwardedEnvironment.length = 0;
  assert.deepEqual(stdioTransport.arguments, ['server.js', '--stdio']);
  assert.deepEqual(stdioTransport.environment, { TOKEN: 'secret', EMPTY: '' });
  assert.deepEqual(
    stdioTransport.forwardedEnvironment.map(({ name, source }) => [name, source]),
    [['HOME', 'local']],
  );
  assert.equal(Object.isFrozen(stdioTransport), true);
  assert.equal(Object.isFrozen(stdioTransport.arguments), true);
  assert.equal(Object.isFrozen(stdioTransport.environment), true);
  assert.equal(Object.isFrozen(stdioTransport.forwardedEnvironment), true);
  assert.equal(Object.isFrozen(stdioTransport.forwardedEnvironment[0]), true);
  assert.deepEqual(Reflect.ownKeys(stdioTransport), [
    'command', 'arguments', 'workingDirectory', 'environment', 'forwardedEnvironment',
  ]);
  assert.throws(() => new sdk.AgentMcpStdioTransport('   '), /MCP command must not be blank/);
  assert.throws(() => new sdk.AgentMcpStdioTransport('node', new Array(1)));
  assert.throws(() => new sdk.AgentMcpStdioTransport('node', [1]));
  assert.throws(() => new sdk.AgentMcpStdioTransport('node', [], null, []));
  assert.throws(() => new sdk.AgentMcpStdioTransport('node', [], null, { TOKEN: 1 }));
  assert.throws(() => new sdk.AgentMcpStdioTransport('node', [], null, null, [{}]));

  const httpTransport = new sdk.AgentMcpHttpTransport(
    'https://mcp.example.com:443/path',
    'MCP_TOKEN',
    { 'X-Static': 'value' },
    { Authorization: 'MCP_AUTH' },
    'mcp-headers',
  );
  assert.deepEqual(
    [
      httpTransport.url,
      httpTransport.bearerTokenEnvironmentVariable,
      httpTransport.headers,
      httpTransport.environmentHeaders,
      httpTransport.headersHelper,
    ],
    [
      'https://mcp.example.com:443/path',
      'MCP_TOKEN',
      { 'X-Static': 'value' },
      { Authorization: 'MCP_AUTH' },
      'mcp-headers',
    ],
  );
  assert.equal(Object.isFrozen(httpTransport), true);
  assert.equal(Object.isFrozen(httpTransport.headers), true);
  assert.equal(Object.isFrozen(httpTransport.environmentHeaders), true);
  assert.deepEqual(Reflect.ownKeys(httpTransport), [
    'url', 'bearerTokenEnvironmentVariable', 'headers', 'environmentHeaders', 'headersHelper',
  ]);
  assert.equal(new sdk.AgentMcpHttpTransport('http://127.0.0.1:8787/mcp').url,
    'http://127.0.0.1:8787/mcp');
  for (const unsafeUrl of [
    'http://example.com/mcp', 'http://localhost.evil.example/mcp', 'https:///missing-host',
  ]) {
    assert.throws(() => new sdk.AgentMcpHttpTransport(unsafeUrl),
      /MCP HTTP URL must use HTTPS or a loopback HTTP address/);
  }
  assert.throws(() => new sdk.AgentMcpHttpTransport('https://mcp.example.com', ' '));
  assert.throws(() => new sdk.AgentMcpHttpTransport('https://mcp.example.com', null, null, null, ' '));

  const hiddenRecord = {};
  Object.defineProperty(hiddenRecord, 'TOKEN', { value: 'secret', enumerable: false });
  const symbolRecord = { TOKEN: 'secret', [Symbol('hidden')]: 'value' };
  const inheritedRecord = Object.create({ TOKEN: 'inherited' });
  inheritedRecord.OWN = 'value';
  for (const invalidRecord of [[], new Map(), inheritedRecord, hiddenRecord, symbolRecord]) {
    assert.throws(() => new sdk.AgentMcpStdioTransport('node', [], null, invalidRecord));
    assert.throws(() => new sdk.AgentMcpHttpTransport('https://mcp.example.com', null, invalidRecord));
  }

  const toolConfiguration = new sdk.AgentMcpToolConfiguration('prompt');
  const oauthConfiguration = new sdk.AgentMcpOauthConfiguration('client', 9876);
  const mcpConfiguration = new sdk.AgentMcpServerConfiguration(
    'remote', httpTransport, 'chat_gpt', 'local', false, true, true,
    ['code_mode', 'deferred'], 3.5, 9, 'writes', ['read'], [], ['files.read'],
    oauthConfiguration, 'https://mcp.example.com/resource', { write: toolConfiguration },
  );
  assert.deepEqual(
    [
      mcpConfiguration.name,
      mcpConfiguration.authentication,
      mcpConfiguration.environmentId,
      mcpConfiguration.isEnabled,
      mcpConfiguration.isRequired,
      mcpConfiguration.supportsParallelToolCalls,
      mcpConfiguration.omitToolsFrom,
      mcpConfiguration.startupTimeoutSeconds,
      mcpConfiguration.toolTimeoutSeconds,
      mcpConfiguration.defaultToolApproval,
      mcpConfiguration.enabledTools,
      mcpConfiguration.disabledTools,
      mcpConfiguration.scopes,
      mcpConfiguration.oauth.clientId,
      mcpConfiguration.oauth.callbackPort,
      mcpConfiguration.oauthResource,
      mcpConfiguration.tools.write.approval,
    ],
    [
      'remote', 'chat_gpt', 'local', false, true, true, ['code_mode', 'deferred'],
      3.5, 9, 'writes', ['read'], [], ['files.read'], 'client', 9876,
      'https://mcp.example.com/resource', 'prompt',
    ],
  );
  assert.notEqual(mcpConfiguration.transport, httpTransport);
  assert.notEqual(mcpConfiguration.oauth, oauthConfiguration);
  assert.notEqual(mcpConfiguration.tools.write, toolConfiguration);
  assert.equal(Object.isFrozen(mcpConfiguration), true);
  assert.equal(Object.isFrozen(mcpConfiguration.transport), true);
  assert.equal(Object.isFrozen(mcpConfiguration.omitToolsFrom), true);
  assert.equal(Object.isFrozen(mcpConfiguration.enabledTools), true);
  assert.equal(Object.isFrozen(mcpConfiguration.disabledTools), true);
  assert.equal(Object.isFrozen(mcpConfiguration.scopes), true);
  assert.equal(Object.isFrozen(mcpConfiguration.tools), true);
  assert.equal(Object.isFrozen(mcpConfiguration.tools.write), true);
  assert.deepEqual(Reflect.ownKeys(mcpConfiguration), [
    'name', 'transport', 'authentication', 'environmentId', 'isEnabled', 'isRequired',
    'supportsParallelToolCalls', 'omitToolsFrom', 'startupTimeoutSeconds',
    'toolTimeoutSeconds', 'defaultToolApproval', 'enabledTools', 'disabledTools', 'scopes',
    'oauth', 'oauthResource', 'tools',
  ]);
  const defaultMcpConfiguration = new sdk.AgentMcpServerConfiguration('local', defaultStdioTransport);
  assert.deepEqual(
    [
      defaultMcpConfiguration.authentication,
      defaultMcpConfiguration.environmentId,
      defaultMcpConfiguration.isEnabled,
      defaultMcpConfiguration.isRequired,
      defaultMcpConfiguration.supportsParallelToolCalls,
      defaultMcpConfiguration.omitToolsFrom,
      defaultMcpConfiguration.startupTimeoutSeconds,
      defaultMcpConfiguration.toolTimeoutSeconds,
      defaultMcpConfiguration.defaultToolApproval,
      defaultMcpConfiguration.enabledTools,
      defaultMcpConfiguration.disabledTools,
      defaultMcpConfiguration.scopes,
      defaultMcpConfiguration.oauth,
      defaultMcpConfiguration.oauthResource,
      defaultMcpConfiguration.tools,
    ],
    [null, 'local', true, false, false, null, null, null, null, null, null, null, null, null, {}],
  );
  assert.throws(() => new sdk.AgentMcpServerConfiguration('invalid.name', defaultStdioTransport));
  assert.throws(() => new sdk.AgentMcpServerConfiguration(
    'stdio-auth', defaultStdioTransport, 'oauth',
  ), /MCP stdio servers do not support authentication/);
  assert.throws(() => new sdk.AgentMcpServerConfiguration(
    'remote-helper', httpTransport, null, 'remote', true, false, false,
  ), /MCP HTTP headers helpers are only supported for local servers/);
  for (const invalidTimeout of [0, -1, NaN, Infinity, Number.MAX_VALUE]) {
    assert.throws(() => new sdk.AgentMcpServerConfiguration(
      'invalid-timeout', defaultStdioTransport, null, 'local', true, false, false,
      null, invalidTimeout,
    ));
  }
  assert.throws(() => new sdk.AgentMcpServerConfiguration(
    'invalid-tools', defaultStdioTransport, null, 'local', true, false, false,
    null, null, null, null, null, null, null, null, null, { read: {} },
  ));

  const mcpServer = new sdk.AgentMcpServer(
    'remote', 'Remote', 'oauth', mcpConfiguration, 'user', true,
  );
  assert.deepEqual(
    [
      mcpServer.name, mcpServer.displayName, mcpServer.authStatus, mcpServer.origin,
      mcpServer.canRemove, mcpServer.isAuthorized,
    ],
    ['remote', 'Remote', 'oauth', 'user', true, true],
  );
  assert.notEqual(mcpServer.configuration, mcpConfiguration);
  assert.equal(Object.isFrozen(mcpServer), true);
  assert.equal(Object.isFrozen(mcpServer.configuration), true);
  assert.deepEqual(Reflect.ownKeys(mcpServer), [
    'name', 'displayName', 'authStatus', 'configuration', 'origin', 'canRemove', 'isAuthorized',
  ]);
  assert.equal(new sdk.AgentMcpServer('new', 'New', 'not_logged_in').isAuthorized, false);
  assert.equal(new sdk.AgentMcpServer('token', 'Token', 'bearer_token').isAuthorized, true);
  assert.throws(() => new sdk.AgentMcpServer('server', 'Server', 'AUTHORIZED'));
  assert.throws(() => new sdk.AgentMcpServer('server', 'Server', 'oauth', {}));

  const firstIssue = new sdk.AgentElicitationValidationIssue('first', 'missing_required');
  const secondIssue = new sdk.AgentElicitationValidationIssue('second', 'invalid_format');
  assert.equal(firstIssue.fieldName, 'first');
  assert.equal(firstIssue.reason, 'missing_required');
  assert.equal(secondIssue.fieldName, 'second');
  assert.equal(secondIssue.reason, 'invalid_format');
  assert.equal(Object.isFrozen(firstIssue), true);
  assert.throws(() => new sdk.AgentElicitationValidationIssue('field', 'not_a_reason'));
  assert.throws(() => new sdk.AgentElicitationValidationIssue({ mutable: true }, 'missing_required'));
  assert.throws(() => new sdk.AgentElicitationValidationIssue('field', { mutable: true }));
  const sourceIssues = [firstIssue, secondIssue];
  const validation = new sdk.AgentElicitationValidation(sourceIssues);
  assert.notEqual(validation.issues, sourceIssues);
  assert.notEqual(validation.issues[0], firstIssue);
  assert.notEqual(validation.issues[1], secondIssue);
  assert.equal(validation.issues[0].fieldName, 'first');
  assert.equal(validation.issues[0].reason, 'missing_required');
  assert.equal(validation.issues[1].fieldName, 'second');
  assert.equal(validation.issues[1].reason, 'invalid_format');
  sourceIssues.reverse();
  assert.equal(validation.issues[0].fieldName, 'first');
  assert.equal(validation.issues[1].fieldName, 'second');
  assert.equal(validation.isValid, false);
  assert.equal(Object.isFrozen(validation.issues), true);
  assert.equal(Object.isFrozen(validation), true);
  assert.equal(new sdk.AgentElicitationValidation([]).isValid, true);
  assert.throws(() => new sdk.AgentElicitationValidation(''));
  assert.throws(() => new sdk.AgentElicitationValidation(() => {}));
  assert.throws(() => new sdk.AgentElicitationValidation({ length: 0 }));
  assert.throws(() => new sdk.AgentElicitationValidation(new Proxy({ length: 0 }, {})));

  const mutableIssue = { fieldName: 'external', reason: 'unknown_field' };
  const proxiedIssue = new Proxy(mutableIssue, {});
  const proxyValidation = new sdk.AgentElicitationValidation([proxiedIssue]);
  assert.notEqual(proxyValidation.issues[0], proxiedIssue);
  mutableIssue.fieldName = 'mutated';
  mutableIssue.reason = 'invalid_format';
  assert.equal(proxyValidation.issues[0].fieldName, 'external');
  assert.equal(proxyValidation.issues[0].reason, 'unknown_field');

  const planStatuses = ['pending', 'in_progress', 'completed'];
  const planSteps = planStatuses.map((status, index) => new sdk.AgentPlanStep(`step-${index}`, status));
  assert.deepEqual(planSteps.map((step) => step.status), planStatuses);
  assert.equal(new sdk.AgentPlanStep('', 'pending').text, '');
  for (const invalidStatus of ['', 'PENDING', 'inProgress', 'unknown']) {
    assert.throws(() => new sdk.AgentPlanStep('step', invalidStatus));
  }
  const invalidRequiredStrings = [
    null,
    undefined,
    0,
    false,
    1n,
    Symbol('value'),
    {},
    [],
    () => {},
    new String('value'),
    new Proxy({}, {}),
  ];
  for (const invalid of invalidRequiredStrings) {
    assert.throws(() => new sdk.AgentPlanStep(invalid, 'pending'));
    assert.throws(() => new sdk.AgentPlanStep('step', invalid));
  }

  const defaultPlan = new sdk.AgentPlanProgress();
  assert.equal(defaultPlan.explanation, null);
  assert.deepEqual(defaultPlan.steps, []);
  assert.equal(Object.isFrozen(defaultPlan.steps), true);
  assert.equal(Object.isFrozen(defaultPlan), true);
  const undefinedPlan = new sdk.AgentPlanProgress(undefined, undefined);
  assert.equal(undefinedPlan.explanation, null);
  assert.deepEqual(undefinedPlan.steps, []);
  const sourcePlanSteps = [planSteps[0], planSteps[2]];
  const plan = new sdk.AgentPlanProgress('Ready', sourcePlanSteps);
  assert.notEqual(plan.steps, sourcePlanSteps);
  assert.notEqual(plan.steps[0], sourcePlanSteps[0]);
  assert.notEqual(plan.steps[1], sourcePlanSteps[1]);
  assert.deepEqual(plan.steps.map((step) => [step.text, step.status]), [
    ['step-0', 'pending'],
    ['step-2', 'completed'],
  ]);
  sourcePlanSteps.reverse();
  assert.deepEqual(plan.steps.map((step) => step.status), ['pending', 'completed']);

  const invalidPlanExplanations = [
    0,
    false,
    1n,
    Symbol('value'),
    {},
    [],
    () => {},
    new String('value'),
    new Proxy({}, {}),
  ];
  for (const invalidExplanation of invalidPlanExplanations) {
    assert.throws(() => new sdk.AgentPlanProgress(invalidExplanation));
  }
  const invalidPlanStepArrays = [
    null,
    '',
    0,
    false,
    1n,
    Symbol('value'),
    {},
    { length: 0 },
    () => {},
    new Proxy({ length: 0 }, {}),
  ];
  for (const invalidSteps of invalidPlanStepArrays) {
    assert.throws(() => new sdk.AgentPlanProgress(null, invalidSteps));
  }
  assert.throws(() => new sdk.AgentPlanProgress(null, new Array(1)));
  const inheritedSparsePlanSteps = new Array(1);
  Object.setPrototypeOf(inheritedSparsePlanSteps, { 0: planSteps[0] });
  assert.equal(Object.hasOwn(inheritedSparsePlanSteps, 0), false);
  assert.throws(() => new sdk.AgentPlanProgress(null, inheritedSparsePlanSteps));
  assert.throws(() => new sdk.AgentPlanProgress(null, new Proxy(inheritedSparsePlanSteps, {})));
  for (const invalidStep of [null, undefined, '', 0, false, 1n, Symbol('value'), {}, [], () => {}]) {
    assert.throws(() => new sdk.AgentPlanProgress(null, [invalidStep]));
  }
  assert.throws(() => new sdk.AgentPlanProgress(null, [{ text: {}, status: 'pending' }]));
  assert.throws(() => new sdk.AgentPlanProgress(null, [{ text: 'step', status: {} }]));
  assert.throws(() => new sdk.AgentPlanProgress(null, [{ text: 'step', status: 'unknown' }]));
  const revokedPlanSteps = Proxy.revocable([], {});
  revokedPlanSteps.revoke();
  assert.throws(() => new sdk.AgentPlanProgress(null, revokedPlanSteps.proxy));

  const mutablePlanStep = { text: 'external-step', status: 'in_progress' };
  const proxiedPlanStep = new Proxy(mutablePlanStep, {});
  const proxiedPlanArrayTarget = [proxiedPlanStep];
  const proxiedPlan = new sdk.AgentPlanProgress('Proxy plan', new Proxy(proxiedPlanArrayTarget, {}));
  assert.notEqual(proxiedPlan.steps, proxiedPlanArrayTarget);
  assert.notEqual(proxiedPlan.steps[0], proxiedPlanStep);
  mutablePlanStep.text = 'mutated';
  mutablePlanStep.status = 'completed';
  proxiedPlanArrayTarget.length = 0;
  assert.equal(proxiedPlan.steps[0].text, 'external-step');
  assert.equal(proxiedPlan.steps[0].status, 'in_progress');

  const defaultHookActivity = new sdk.AgentHookActivity('hook', 'afterTurn', 'command', 'running');
  assert.equal(defaultHookActivity.id, 'hook');
  assert.equal(defaultHookActivity.eventName, 'afterTurn');
  assert.equal(defaultHookActivity.handlerType, 'command');
  assert.equal(defaultHookActivity.status, 'running');
  assert.equal(defaultHookActivity.statusMessage, null);
  assert.deepEqual(defaultHookActivity.details, []);
  const undefinedHookActivity = new sdk.AgentHookActivity(
    'hook', 'afterTurn', 'command', 'running', undefined, undefined,
  );
  assert.equal(undefinedHookActivity.statusMessage, null);
  assert.deepEqual(undefinedHookActivity.details, []);
  const hookStatuses = ['running', 'completed', 'failed', 'blocked', 'stopped'];
  const hookActivities = hookStatuses.map(
    (status) => new sdk.AgentHookActivity('hook', 'afterTurn', 'command', status, null, []),
  );
  assert.deepEqual(hookActivities.map(({ status }) => status), hookStatuses);
  const permissiveHookActivity = new sdk.AgentHookActivity('', '', '', 'completed', '', ['', 'same', 'same']);
  assert.deepEqual(permissiveHookActivity.details, ['', 'same', 'same']);

  const sourceHookDetails = ['first', 'second'];
  const detachedHookActivity = new sdk.AgentHookActivity(
    'hook', 'afterTurn', 'command', 'completed', 'Complete', sourceHookDetails,
  );
  assert.notEqual(detachedHookActivity.details, sourceHookDetails);
  sourceHookDetails.splice(0, sourceHookDetails.length, 'mutated');
  assert.deepEqual(detachedHookActivity.details, ['first', 'second']);
  const proxyHookDetailsTarget = ['proxy-first', 'proxy-second'];
  const proxyHookDetails = new Proxy(proxyHookDetailsTarget, {});
  const proxyHookActivity = new sdk.AgentHookActivity(
    'hook', 'afterTurn', 'command', 'running', null, proxyHookDetails,
  );
  assert.notEqual(proxyHookActivity.details, proxyHookDetails);
  assert.notEqual(proxyHookActivity.details, proxyHookDetailsTarget);
  proxyHookDetailsTarget.reverse();
  assert.deepEqual(proxyHookActivity.details, ['proxy-first', 'proxy-second']);

  const invalidHookStrings = [
    null, undefined, 0, -0, NaN, Infinity, -Infinity, false, true, 1n, Symbol('value'), {}, [],
    () => {}, new String('value'), new Number(1), new Boolean(true), new Proxy({}, {}),
  ];
  for (const invalid of invalidHookStrings) {
    assert.throws(() => new sdk.AgentHookActivity(invalid, 'afterTurn', 'command', 'running'));
    assert.throws(() => new sdk.AgentHookActivity('hook', invalid, 'command', 'running'));
    assert.throws(() => new sdk.AgentHookActivity('hook', 'afterTurn', invalid, 'running'));
    assert.throws(() => new sdk.AgentHookActivity('hook', 'afterTurn', 'command', invalid));
    if (invalid !== null && invalid !== undefined) {
      assert.throws(() => new sdk.AgentHookActivity('hook', 'afterTurn', 'command', 'running', invalid));
    }
  }
  for (const invalidStatus of ['', 'RUNNING', 'Running', 'inProgress', 'unknown']) {
    assert.throws(() => new sdk.AgentHookActivity('hook', 'afterTurn', 'command', invalidStatus));
  }
  for (const invalidDetails of [
    null, '', 0, false, 1n, Symbol('details'), {}, { length: 0 }, () => {}, new String('value'),
    new Proxy({ length: 0 }, {}),
  ]) {
    assert.throws(() => new sdk.AgentHookActivity(
      'hook', 'afterTurn', 'command', 'running', null, invalidDetails,
    ));
  }
  const sparseHookDetails = new Array(2);
  sparseHookDetails[1] = 'value';
  assert.throws(() => new sdk.AgentHookActivity(
    'hook', 'afterTurn', 'command', 'running', null, sparseHookDetails,
  ));
  const inheritedSparseHookDetails = new Array(1);
  Object.setPrototypeOf(inheritedSparseHookDetails, { 0: 'inherited' });
  assert.equal(Object.hasOwn(inheritedSparseHookDetails, 0), false);
  assert.throws(() => new sdk.AgentHookActivity(
    'hook', 'afterTurn', 'command', 'running', null, inheritedSparseHookDetails,
  ));
  assert.throws(() => new sdk.AgentHookActivity(
    'hook', 'afterTurn', 'command', 'running', null, new Proxy(inheritedSparseHookDetails, {}),
  ));
  const revokedHookDetails = Proxy.revocable(['value'], {});
  revokedHookDetails.revoke();
  assert.throws(() => new sdk.AgentHookActivity(
    'hook', 'afterTurn', 'command', 'running', null, revokedHookDetails.proxy,
  ));
  for (const invalid of invalidHookStrings) {
    assert.throws(() => new sdk.AgentHookActivity(
      'hook', 'afterTurn', 'command', 'running', null, [invalid],
    ));
  }

  const sourceHandler = { type: 'command', command: './check', isAsync: true };
  const hook = new sdk.AgentHook(
    'review-hook', 'sha256:review', true, 'preToolUse', sourceHandler, false,
    'PROJECT', '/workspace/.codex/hooks.json', 9007199254740993n, 'untrusted',
    'Shell', null, 'Review shell commands', undefined, true,
  );
  assert.deepEqual(
    [
      hook.key, hook.currentHash, hook.isEnabled, hook.eventName, hook.isManaged, hook.source,
      hook.sourcePath, hook.timeoutSeconds, hook.trustStatus, hook.matcher, hook.pluginId,
      hook.statusMessage, hook.origin, hook.canUninstall, hook.canTrust,
    ],
    [
      'review-hook', 'sha256:review', true, 'preToolUse', false, 'PROJECT',
      '/workspace/.codex/hooks.json', 9007199254740993n, 'untrusted', 'Shell', null,
      'Review shell commands', 'workspace', true, true,
    ],
  );
  assert.deepEqual(hook.handler, { type: 'command', command: './check', isAsync: true });
  assert.notEqual(hook.handler, sourceHandler);
  sourceHandler.command = 'changed';
  assert.equal(hook.handler.command, './check');
  assert.equal(Object.isFrozen(hook), true);
  assert.equal(Object.isFrozen(hook.handler), true);
  assert.deepEqual(Object.keys(hook), []);
  assert.deepEqual(Object.keys(hook.handler), ['type', 'command', 'isAsync']);

  for (const [handler, expected] of [
    [{ type: 'agent' }, { type: 'agent' }],
    [{ type: 'command', command: './check', isAsync: false },
      { type: 'command', command: './check', isAsync: false }],
    [{ type: 'mcp_tool', server: 'review', tool: 'lint' },
      { type: 'mcp_tool', server: 'review', tool: 'lint' }],
    [{ type: 'prompt' }, { type: 'prompt' }],
  ]) {
    const value = new sdk.AgentHook(
      `hook-${handler.type}`, 'hash', false, 'stop', handler, false,
      'USER', '/hooks.json', 10n, 'trusted',
    );
    assert.deepEqual(value.handler, expected);
    assert.equal(Object.isFrozen(value.handler), true);
  }

  for (const [invalidHandler, message] of [
    [null, 'handler must be an object'],
    [undefined, 'handler must be an object'],
    [0, 'handler must be an object'],
    ['command', 'handler must be an object'],
    [new String('command'), 'handler.type must be a string'],
    [{}, 'handler.type must be a string'],
    [{ type: 'future' }, 'Unknown hook handler type: future'],
    [{ type: 'command', command: 1, isAsync: false }, 'handler.command must be a string'],
    [{ type: 'command', command: './check', isAsync: 'false' }, 'handler.isAsync must be a boolean'],
    [{ type: 'mcp_tool', server: 1, tool: 'lint' }, 'handler.server must be a string'],
    [{ type: 'mcp_tool', server: 'review', tool: 1 }, 'handler.tool must be a string'],
  ]) {
    assert.throws(
      () => new sdk.AgentHook(
        'invalid', 'hash', false, 'stop', invalidHandler, false,
        'USER', '/hooks.json', 10n, 'trusted',
      ),
      (error) => error?.message === message,
    );
  }
  for (const invalid of invalidHookStrings) {
    assert.throws(() => new sdk.AgentHook(
      invalid, 'hash', false, 'stop', { type: 'prompt' }, false,
      'USER', '/hooks.json', 10n, 'trusted',
    ));
    assert.throws(() => new sdk.AgentHook(
      'hook', 'hash', false, 'stop', { type: 'prompt' }, false,
      'USER', '/hooks.json', 10n, invalid,
    ));
  }
  for (const invalid of [0, 1, '', 'true', {}, [], new Boolean(true)]) {
    assert.throws(() => new sdk.AgentHook(
      'hook', 'hash', invalid, 'stop', { type: 'prompt' }, false,
      'USER', '/hooks.json', 10n, 'trusted',
    ));
  }
  for (const invalid of [0, 1, '', false, {}, [], Object(1n)]) {
    assert.throws(() => new sdk.AgentHook(
      'hook', 'hash', false, 'stop', { type: 'prompt' }, false,
      'USER', '/hooks.json', invalid, 'trusted',
    ));
  }
  for (const boundary of [-9223372036854775808n, 9223372036854775807n]) {
    assert.equal(new sdk.AgentHook(
      'hook', 'hash', false, 'stop', { type: 'prompt' }, false,
      'USER', '/hooks.json', boundary, 'trusted',
    ).timeoutSeconds, boundary);
  }
  for (const overflow of [-9223372036854775809n, 9223372036854775808n]) {
    assert.throws(
      () => new sdk.AgentHook(
        'hook', 'hash', false, 'stop', { type: 'prompt' }, false,
        'USER', '/hooks.json', overflow, 'trusted',
      ),
      (error) => error?.message === 'timeoutSeconds must fit a signed 64-bit integer',
    );
  }
  for (const invalid of ['', 'TRUSTED', 'unknown']) {
    assert.throws(
      () => new sdk.AgentHook(
        'hook', 'hash', false, 'stop', { type: 'prompt' }, false,
        'USER', '/hooks.json', 10n, invalid,
      ),
      (error) => error?.message === `Unknown hook trust status: ${invalid}`,
    );
  }
  for (const invalid of [null, '', 'USER', 'repo', 0, false, {}, []]) {
    assert.throws(() => new sdk.AgentHook(
      'hook', 'hash', false, 'stop', { type: 'prompt' }, false,
      'USER', '/hooks.json', 10n, 'trusted', null, null, null, invalid,
    ));
  }

  const sourceHooks = [hook];
  const sourceWarnings = ['warning'];
  const sourceErrors = ['error'];
  const hookCatalog = new sdk.AgentHookCatalog(sourceHooks, sourceWarnings, sourceErrors);
  sourceHooks.length = 0;
  sourceWarnings[0] = 'changed';
  sourceErrors[0] = 'changed';
  assert.deepEqual(hookCatalog.hooks.map(({ key }) => key), ['review-hook']);
  assert.deepEqual(hookCatalog.warnings, ['warning']);
  assert.deepEqual(hookCatalog.errors, ['error']);
  assert.notEqual(hookCatalog.hooks[0], hook);
  assert.equal(Object.isFrozen(hookCatalog), true);
  assert.equal(Object.isFrozen(hookCatalog.hooks), true);
  assert.equal(Object.isFrozen(hookCatalog.warnings), true);
  assert.equal(Object.isFrozen(hookCatalog.errors), true);
  assert.equal(Object.isFrozen(hookCatalog.hooks[0]), true);
  assert.equal(Object.isFrozen(hookCatalog.hooks[0].handler), true);
  assert.deepEqual(new sdk.AgentHookCatalog([]).warnings, []);
  assert.deepEqual(new sdk.AgentHookCatalog([]).errors, []);
  for (const invalid of [null, undefined, '', 0, false, {}, { length: 0 }, () => {}]) {
    assert.throws(() => new sdk.AgentHookCatalog(invalid));
    if (invalid !== undefined) {
      assert.throws(() => new sdk.AgentHookCatalog([], invalid));
      assert.throws(() => new sdk.AgentHookCatalog([], [], invalid));
    }
  }
  assert.throws(() => new sdk.AgentHookCatalog(new Array(1)));
  assert.throws(() => new sdk.AgentHookCatalog([], new Array(1)));
  assert.throws(() => new sdk.AgentHookCatalog([], [], new Array(1)));
  assert.throws(() => new sdk.AgentHookCatalog([{}]));
  assert.throws(() => new sdk.AgentHookCatalog([], [0]));
  assert.throws(() => new sdk.AgentHookCatalog([], [], [0]));

  const defaultConnector = new sdk.AgentConnector('drive', 'Google Drive');
  assert.equal(defaultConnector.id, 'drive');
  assert.equal(defaultConnector.name, 'Google Drive');
  assert.equal(defaultConnector.description, '');
  assert.equal(defaultConnector.installUrl, null);
  assert.equal(defaultConnector.isAccessible, false);
  assert.equal(defaultConnector.isEnabled, true);
  assert.deepEqual(defaultConnector.pluginNames, []);
  const undefinedConnector = new sdk.AgentConnector(
    'drive', 'Google Drive', undefined, undefined, undefined, undefined, undefined,
  );
  assert.equal(undefinedConnector.description, '');
  assert.equal(undefinedConnector.installUrl, null);
  assert.equal(undefinedConnector.isAccessible, false);
  assert.equal(undefinedConnector.isEnabled, true);
  assert.deepEqual(undefinedConnector.pluginNames, []);

  const sourceConnectorPluginNames = ['Drive', 'Workspace'];
  const customConnector = new sdk.AgentConnector(
    'slack',
    'Slack',
    'Team messaging',
    'https://example.com/install',
    true,
    false,
    sourceConnectorPluginNames,
  );
  assert.equal(customConnector.id, 'slack');
  assert.equal(customConnector.name, 'Slack');
  assert.equal(customConnector.description, 'Team messaging');
  assert.equal(customConnector.installUrl, 'https://example.com/install');
  assert.equal(customConnector.isAccessible, true);
  assert.equal(customConnector.isEnabled, false);
  assert.deepEqual(customConnector.pluginNames, ['Drive', 'Workspace']);
  assert.notEqual(customConnector.pluginNames, sourceConnectorPluginNames);
  sourceConnectorPluginNames.splice(0, sourceConnectorPluginNames.length, 'mutated');
  assert.deepEqual(customConnector.pluginNames, ['Drive', 'Workspace']);

  const proxyConnectorPluginNamesTarget = ['Proxy'];
  const proxyConnectorPluginNames = new Proxy(proxyConnectorPluginNamesTarget, {});
  const proxyConnector = new sdk.AgentConnector(
    'proxy', 'Proxy', '', null, false, true, proxyConnectorPluginNames,
  );
  assert.notEqual(proxyConnector.pluginNames, proxyConnectorPluginNames);
  assert.notEqual(proxyConnector.pluginNames, proxyConnectorPluginNamesTarget);
  proxyConnectorPluginNamesTarget[0] = 'mutated';
  assert.deepEqual(proxyConnector.pluginNames, ['Proxy']);

  for (const invalid of invalidHookStrings) {
    assert.throws(() => new sdk.AgentConnector(invalid, 'Google Drive'));
    assert.throws(() => new sdk.AgentConnector('drive', invalid));
    if (invalid !== undefined) {
      assert.throws(() => new sdk.AgentConnector('drive', 'Google Drive', invalid));
    }
    if (invalid !== null && invalid !== undefined) {
      assert.throws(() => new sdk.AgentConnector('drive', 'Google Drive', '', invalid));
    }
  }
  for (const invalidBoolean of [null, 0, 1, '', 'true', {}, [], new Boolean(true), new Proxy({}, {})]) {
    assert.throws(() => new sdk.AgentConnector('drive', 'Google Drive', '', null, invalidBoolean));
    assert.throws(() => new sdk.AgentConnector('drive', 'Google Drive', '', null, true, invalidBoolean));
  }
  for (const invalidPluginNames of [null, '', 0, false, {}, { length: 0 }, () => {}]) {
    assert.throws(() => new sdk.AgentConnector(
      'drive', 'Google Drive', '', null, false, true, invalidPluginNames,
    ));
  }
  const sparseConnectorPluginNames = new Array(2);
  sparseConnectorPluginNames[1] = 'Drive';
  assert.throws(() => new sdk.AgentConnector(
    'drive', 'Google Drive', '', null, false, true, sparseConnectorPluginNames,
  ));
  const inheritedConnectorPluginNames = new Array(1);
  Object.setPrototypeOf(inheritedConnectorPluginNames, { 0: 'inherited' });
  assert.throws(() => new sdk.AgentConnector(
    'drive', 'Google Drive', '', null, false, true, inheritedConnectorPluginNames,
  ));
  const revokedConnectorPluginNames = Proxy.revocable(['Drive'], {});
  revokedConnectorPluginNames.revoke();
  assert.throws(() => new sdk.AgentConnector(
    'drive', 'Google Drive', '', null, false, true, revokedConnectorPluginNames.proxy,
  ));
  for (const invalid of invalidHookStrings) {
    assert.throws(() => new sdk.AgentConnector(
      'drive', 'Google Drive', '', null, false, true, [invalid],
    ));
  }

  const skillInvocation = new sdk.AgentSkillInvocation('review', '/skills/review/SKILL.md');
  const pluginInvocation = new sdk.AgentPluginInvocation('tools', 'plugin://tools@official');
  assert.deepEqual(
    [skillInvocation.name, skillInvocation.path, skillInvocation.key],
    ['review', '/skills/review/SKILL.md', 'skill:/skills/review/SKILL.md'],
  );
  assert.deepEqual(
    [pluginInvocation.name, pluginInvocation.uri, pluginInvocation.key],
    ['tools', 'plugin://tools@official', 'plugin:plugin://tools@official'],
  );
  for (const invalid of [null, undefined, 0, false, {}, [], new String('value'), new Proxy({}, {})]) {
    assert.throws(
      () => new sdk.AgentSkillInvocation(invalid, '/skills/review/SKILL.md'),
      (error) => error?.message === 'name must be a string',
    );
    assert.throws(
      () => new sdk.AgentSkillInvocation('review', invalid),
      (error) => error?.message === 'path must be a string',
    );
    assert.throws(
      () => new sdk.AgentPluginInvocation(invalid, 'plugin://tools@official'),
      (error) => error?.message === 'name must be a string',
    );
    assert.throws(
      () => new sdk.AgentPluginInvocation('tools', invalid),
      (error) => error?.message === 'uri must be a string',
    );
  }

  const conversationSummary = new sdk.AgentConversationSummary(
    'conversation', 'Conversation title', 1n,
  );
  assert.equal(conversationSummary.conversationId, 'conversation');
  assert.equal(conversationSummary.title, 'Conversation title');
  assert.equal(conversationSummary.updatedAtEpochSeconds, 1n);
  assert.equal(Object.isFrozen(conversationSummary), true);
  const permissiveConversationSummary = new sdk.AgentConversationSummary(
    'conversation-negative-time', '', -1n,
  );
  assert.equal(permissiveConversationSummary.title, '');
  assert.equal(permissiveConversationSummary.updatedAtEpochSeconds, -1n);
  for (const boundary of [-9223372036854775808n, 9223372036854775807n]) {
    assert.equal(
      new sdk.AgentConversationSummary('conversation-boundary', 'Boundary', boundary)
        .updatedAtEpochSeconds,
      boundary,
    );
  }
  for (const outOfRange of [-9223372036854775809n, 9223372036854775808n]) {
    assert.throws(
      () => new sdk.AgentConversationSummary('conversation-range', 'Range', outOfRange),
      /updatedAtEpochSeconds must fit a signed 64-bit integer/,
    );
  }
  for (const boxed of [Object(1n), new Proxy(Object(1n), {})]) {
    assert.throws(
      () => new sdk.AgentConversationSummary('conversation-boxed', 'Boxed', boxed),
      /updatedAtEpochSeconds must be a bigint/,
    );
  }
  assert.throws(() => new sdk.AgentConversationSummary('', 'Title', 1n));
  for (const invalid of invalidHookStrings) {
    assert.throws(() => new sdk.AgentConversationSummary(invalid, 'Title', 1n));
    assert.throws(() => new sdk.AgentConversationSummary('conversation', invalid, 1n));
  }
  for (const invalid of [null, undefined, 0, 1, -1, '', false, {}, []]) {
    assert.throws(() => new sdk.AgentConversationSummary('conversation', 'Title', invalid));
  }

  const sourceConversationMessages = [];
  const historicalConversation = new sdk.AgentConversation(
    conversationSummary,
    sourceConversationMessages,
  );
  sourceConversationMessages.push(null);
  assert.notEqual(historicalConversation.summary, conversationSummary);
  assert.deepEqual(
    [historicalConversation.summary.conversationId, historicalConversation.summary.title,
      historicalConversation.summary.updatedAtEpochSeconds],
    ['conversation', 'Conversation title', 1n],
  );
  assert.deepEqual(historicalConversation.messages, []);
  assert.equal(Object.isFrozen(historicalConversation.summary), true);
  assert.equal(Object.isFrozen(historicalConversation.messages), true);
  assert.equal(Object.isFrozen(historicalConversation), true);
  for (const invalidSummary of [null, undefined, 0, false, {}, [], new Proxy({}, {})]) {
    assert.throws(
      () => new sdk.AgentConversation(invalidSummary, []),
      (error) => error?.message === 'summary must be an AgentConversationSummary',
    );
  }
  for (const invalidMessages of [null, undefined, 0, false, {}, new Set()]) {
    assert.throws(
      () => new sdk.AgentConversation(conversationSummary, invalidMessages),
      (error) => error?.message === 'messages must be an array',
    );
  }
  assert.throws(
    () => new sdk.AgentConversation(conversationSummary, [{}]),
    (error) => error?.message === 'messages[0] must be a CodexMessage',
  );
  const malformedMessage = new sdk.CodexMessage(
    'message', null, 'user', 'Text', 'default', null, null, null, null, {}, [],
  );
  assert.throws(
    () => new sdk.AgentConversation(conversationSummary, [malformedMessage]),
    (error) => error?.message === 'capabilities must be an array',
  );
  assert.throws(
    () => new sdk.AgentConversation(conversationSummary, Array(1)),
    (error) => error?.message === 'messages must not contain sparse elements',
  );

  const serviceTier = new sdk.AgentServiceTier('fast', 'Fast', 'Lowest latency');
  assert.equal(serviceTier.id, 'fast');
  assert.equal(serviceTier.name, 'Fast');
  assert.equal(serviceTier.description, 'Lowest latency');
  for (const invalid of invalidHookStrings) {
    assert.throws(() => new sdk.AgentServiceTier(invalid, 'Fast', 'Lowest latency'));
    assert.throws(() => new sdk.AgentServiceTier('fast', invalid, 'Lowest latency'));
    assert.throws(() => new sdk.AgentServiceTier('fast', 'Fast', invalid));
  }

  const defaultModel = new sdk.AgentModel(
    'model-default', 'Default model', 'Default description', ['medium'], 'medium', true,
  );
  assert.deepEqual(defaultModel.serviceTiers, []);
  assert.equal(defaultModel.defaultServiceTier, null);
  const sourceEfforts = ['low', 'medium', 'high'];
  const sourceServiceTiers = [serviceTier];
  const model = new sdk.AgentModel(
    'model', 'Model', 'Description', sourceEfforts, 'medium', false, sourceServiceTiers, 'fast',
  );
  assert.equal(model.id, 'model');
  assert.equal(model.displayName, 'Model');
  assert.equal(model.description, 'Description');
  assert.deepEqual(model.supportedEfforts, ['low', 'medium', 'high']);
  assert.equal(model.defaultEffort, 'medium');
  assert.equal(model.isDefault, false);
  assert.deepEqual(model.serviceTiers.map(({ id }) => id), ['fast']);
  assert.equal(model.defaultServiceTier, 'fast');
  assert.notEqual(model.supportedEfforts, sourceEfforts);
  assert.notEqual(model.serviceTiers, sourceServiceTiers);
  sourceEfforts.splice(0, sourceEfforts.length, 'mutated');
  sourceServiceTiers.length = 0;
  assert.deepEqual(model.supportedEfforts, ['low', 'medium', 'high']);
  assert.deepEqual(model.serviceTiers.map(({ id }) => id), ['fast']);
  assert.equal(Object.isFrozen(model.supportedEfforts), true);
  assert.equal(Object.isFrozen(model.serviceTiers), true);
  assert.equal(Object.isFrozen(serviceTier), true);
  assert.equal(Object.isFrozen(defaultModel), true);
  assert.equal(Object.isFrozen(model), true);
  assert.equal(Object.isFrozen(model.serviceTiers[0]), true);
  for (const invalid of invalidHookStrings) {
    assert.throws(() => new sdk.AgentModel(
      invalid, 'Model', 'Description', ['medium'], 'medium', true,
    ));
    assert.throws(() => new sdk.AgentModel(
      'model', 'Model', 'Description', ['medium'], invalid, true,
    ));
    if (invalid !== null && invalid !== undefined) {
      assert.throws(() => new sdk.AgentModel(
        'model', 'Model', 'Description', ['medium'], 'medium', true, [], invalid,
      ));
    }
  }
  assert.throws(() => new sdk.AgentModel(
    'model', 'Model', 'Description', ['medium', 1], 'medium', true,
  ));
  assert.throws(() => new sdk.AgentModel(
    'model', 'Model', 'Description', ['medium'], 'medium', 'true',
  ));
  assert.throws(() => new sdk.AgentModel(
    'model', 'Model', 'Description', ['medium'], 'medium', true, [{}],
  ));
  const sparseEfforts = new Array(1);
  assert.throws(() => new sdk.AgentModel(
    'model', 'Model', 'Description', sparseEfforts, 'medium', true,
  ));
  const revokedServiceTiers = Proxy.revocable([serviceTier], {});
  revokedServiceTiers.revoke();
  assert.throws(() => new sdk.AgentModel(
    'model', 'Model', 'Description', ['medium'], 'medium', true, revokedServiceTiers.proxy,
  ));

  const defaultSkillOrigins = new Map([
    ['admin', 'managed'],
    ['plugin', 'plugin'],
    ['repo', 'workspace'],
    ['system', 'managed'],
    ['user', 'user'],
  ]);
  const defaultSkills = [...defaultSkillOrigins].map(([scope, origin]) => {
    const value = new sdk.AgentSkill(
      `${scope}-skill`, `${scope} skill`, 'Description', `/skills/${scope}/SKILL.md`, scope, true,
    );
    assert.equal(value.brandColor, null);
    assert.deepEqual(value.dependencies, []);
    assert.equal(value.canUninstall, false);
    assert.equal(value.origin, origin);
    return value;
  });
  const sourceSkillDependencies = ['git', 'rg'];
  const skill = new sdk.AgentSkill(
    'review', 'Review', 'Review changes', '/skills/review/SKILL.md', 'user', true,
    '#123456', sourceSkillDependencies, true, 'plugin',
  );
  assert.deepEqual(
    [
      skill.name,
      skill.displayName,
      skill.description,
      skill.path,
      skill.scope,
      skill.isEnabled,
      skill.brandColor,
      skill.canUninstall,
      skill.origin,
    ],
    [
      'review',
      'Review',
      'Review changes',
      '/skills/review/SKILL.md',
      'user',
      true,
      '#123456',
      true,
      'plugin',
    ],
  );
  assert.notEqual(skill.dependencies, sourceSkillDependencies);
  assert.deepEqual(skill.dependencies, ['git', 'rg']);
  sourceSkillDependencies.reverse();
  assert.deepEqual(skill.dependencies, ['git', 'rg']);

  for (const invalid of invalidHookStrings) {
    assert.throws(() => new sdk.AgentSkill(
      invalid, 'Review', 'Description', '/skills/review/SKILL.md', 'user', true,
    ));
    assert.throws(() => new sdk.AgentSkill(
      'review', invalid, 'Description', '/skills/review/SKILL.md', 'user', true,
    ));
    assert.throws(() => new sdk.AgentSkill(
      'review', 'Review', invalid, '/skills/review/SKILL.md', 'user', true,
    ));
    assert.throws(() => new sdk.AgentSkill(
      'review', 'Review', 'Description', invalid, 'user', true,
    ));
    assert.throws(() => new sdk.AgentSkill(
      'review', 'Review', 'Description', '/skills/review/SKILL.md', invalid, true,
    ));
  }
  for (const invalidScope of ['', 'USER', 'workspace', 'unknown']) {
    assert.throws(() => new sdk.AgentSkill(
      'review', 'Review', 'Description', '/skills/review/SKILL.md', invalidScope, true,
    ));
  }
  for (const invalidBoolean of [null, undefined, 0, 1, '', 'true', {}, [], new Boolean(true)]) {
    assert.throws(() => new sdk.AgentSkill(
      'review', 'Review', 'Description', '/skills/review/SKILL.md', 'user', invalidBoolean,
    ));
    if (invalidBoolean !== undefined) {
      assert.throws(() => new sdk.AgentSkill(
        'review', 'Review', 'Description', '/skills/review/SKILL.md', 'user', true,
        null, [], invalidBoolean,
      ));
    }
  }
  for (const invalidColor of [0, false, 1n, {}, [], new String('#123456')]) {
    assert.throws(() => new sdk.AgentSkill(
      'review', 'Review', 'Description', '/skills/review/SKILL.md', 'user', true, invalidColor,
    ));
  }
  for (const invalidOrigin of [null, '', 'USER', 'repo', 0, false, {}, [], new String('user')]) {
    assert.throws(() => new sdk.AgentSkill(
      'review', 'Review', 'Description', '/skills/review/SKILL.md', 'user', true,
      null, [], false, invalidOrigin,
    ));
  }
  for (const invalidDependencies of [null, '', 0, false, {}, { length: 0 }, () => {}]) {
    assert.throws(() => new sdk.AgentSkill(
      'review', 'Review', 'Description', '/skills/review/SKILL.md', 'user', true,
      null, invalidDependencies,
    ));
  }
  const sparseSkillDependencies = new Array(2);
  sparseSkillDependencies[1] = 'git';
  assert.throws(() => new sdk.AgentSkill(
    'review', 'Review', 'Description', '/skills/review/SKILL.md', 'user', true,
    null, sparseSkillDependencies,
  ));
  const inheritedSkillDependencies = new Array(1);
  Object.setPrototypeOf(inheritedSkillDependencies, { 0: 'inherited' });
  assert.throws(() => new sdk.AgentSkill(
    'review', 'Review', 'Description', '/skills/review/SKILL.md', 'user', true,
    null, inheritedSkillDependencies,
  ));
  const revokedSkillDependencies = Proxy.revocable(['git'], {});
  revokedSkillDependencies.revoke();
  assert.throws(() => new sdk.AgentSkill(
    'review', 'Review', 'Description', '/skills/review/SKILL.md', 'user', true,
    null, revokedSkillDependencies.proxy,
  ));
  for (const invalid of invalidHookStrings) {
    assert.throws(() => new sdk.AgentSkill(
      'review', 'Review', 'Description', '/skills/review/SKILL.md', 'user', true,
      null, [invalid],
    ));
  }

  const sourceCatalogSkills = [skill, defaultSkills[0]];
  const sourceCatalogErrors = ['first warning', 'second warning'];
  const skillCatalog = new sdk.AgentSkillCatalog(sourceCatalogSkills, sourceCatalogErrors);
  assert.notEqual(skillCatalog.skills, sourceCatalogSkills);
  assert.notEqual(skillCatalog.errors, sourceCatalogErrors);
  assert.notEqual(skillCatalog.skills[0], skill);
  assert.deepEqual(skillCatalog.skills.map(({ name }) => name), ['review', 'admin-skill']);
  assert.deepEqual(skillCatalog.errors, ['first warning', 'second warning']);
  sourceCatalogSkills.reverse();
  sourceCatalogErrors.reverse();
  assert.deepEqual(skillCatalog.skills.map(({ name }) => name), ['review', 'admin-skill']);
  assert.deepEqual(skillCatalog.errors, ['first warning', 'second warning']);
  assert.deepEqual(new sdk.AgentSkillCatalog([]).errors, []);
  for (const invalid of [null, undefined, '', 0, false, {}, { length: 0 }, () => {}]) {
    assert.throws(() => new sdk.AgentSkillCatalog(invalid));
    if (invalid !== undefined) assert.throws(() => new sdk.AgentSkillCatalog([], invalid));
  }
  assert.throws(() => new sdk.AgentSkillCatalog(new Array(1)));
  assert.throws(() => new sdk.AgentSkillCatalog([], new Array(1)));
  assert.throws(() => new sdk.AgentSkillCatalog([{}]));
  assert.throws(() => new sdk.AgentSkillCatalog([], [0]));
  const revokedCatalogSkills = Proxy.revocable([skill], {});
  revokedCatalogSkills.revoke();
  assert.throws(() => new sdk.AgentSkillCatalog(revokedCatalogSkills.proxy));

  const skillChunk = new sdk.AgentSkillChunk('content', 7n, 20n);
  const terminalSkillChunk = new sdk.AgentSkillChunk('', null, 0n);
  assert.deepEqual(
    [skillChunk.content, skillChunk.nextOffset, skillChunk.totalBytes],
    ['content', 7n, 20n],
  );
  assert.deepEqual(
    [terminalSkillChunk.content, terminalSkillChunk.nextOffset, terminalSkillChunk.totalBytes],
    ['', null, 0n],
  );
  for (const boundary of [-9223372036854775808n, 9223372036854775807n]) {
    assert.equal(new sdk.AgentSkillChunk('boundary', boundary, boundary).totalBytes, boundary);
  }
  for (const invalidContent of invalidHookStrings) {
    assert.throws(() => new sdk.AgentSkillChunk(invalidContent, null, 0n));
  }
  for (const invalidOffset of [0, 1, '', false, {}, [], Object(1n)]) {
    assert.throws(() => new sdk.AgentSkillChunk('content', invalidOffset, 20n));
  }
  for (const invalidTotal of [null, undefined, 0, 1, '', false, {}, [], Object(20n)]) {
    assert.throws(() => new sdk.AgentSkillChunk('content', null, invalidTotal));
  }
  for (const outOfRange of [-9223372036854775809n, 9223372036854775808n]) {
    assert.throws(() => new sdk.AgentSkillChunk('range', outOfRange, 0n));
    assert.throws(() => new sdk.AgentSkillChunk('range', null, outOfRange));
  }

  const assertImmutableOwnGraph = (root) => {
    const seen = new Set();
    const visit = (value) => {
      if (value === null || typeof value !== 'object' || seen.has(value)) return;
      seen.add(value);
      assert.equal(Object.isFrozen(value), true);
      for (const key of Reflect.ownKeys(value)) {
        const nested = value[key];
        assert.equal(Reflect.set(value, key, nested), false);
        visit(nested);
      }
    };
    visit(root);
  };
  for (const snapshot of [
    option,
    describedOption,
    textValue,
    ...numberValues,
    falseValue,
    trueValue,
    emptyTextListValue,
    textListValue,
    proxyTextListValue,
    defaultMcpEnvironmentVariable,
    undefinedMcpEnvironmentVariable,
    nullMcpEnvironmentVariable,
    ...mcpEnvironmentVariables,
    ...permissiveMcpEnvironmentVariables,
    defaultMcpOauthConfiguration,
    undefinedMcpOauthConfiguration,
    nullMcpOauthConfiguration,
    blankMcpOauthConfiguration,
    whitespaceMcpOauthConfiguration,
    minimumMcpOauthPort,
    maximumMcpOauthPort,
    defaultMcpToolConfiguration,
    undefinedMcpToolConfiguration,
    nullMcpToolConfiguration,
    ...mcpToolConfigurations,
    firstIssue,
    secondIssue,
    validation,
    proxyValidation,
    ...planSteps,
    defaultPlan,
    undefinedPlan,
    plan,
    proxiedPlan,
    defaultHookActivity,
    undefinedHookActivity,
    ...hookActivities,
    permissiveHookActivity,
    detachedHookActivity,
    proxyHookActivity,
    defaultConnector,
    undefinedConnector,
    customConnector,
    proxyConnector,
    skillInvocation,
    pluginInvocation,
    conversationSummary,
    permissiveConversationSummary,
    historicalConversation,
    serviceTier,
    defaultModel,
    model,
    ...defaultSkills,
    skill,
    skillCatalog,
    skillChunk,
    terminalSkillChunk,
  ]) {
    assertImmutableOwnGraph(snapshot);
  }
  for (const value of [textValue, ...numberValues, falseValue, trueValue, textListValue]) {
    assert.deepEqual(Reflect.ownKeys(value), ['value']);
  }
  for (const environment of [
    defaultMcpEnvironmentVariable,
    undefinedMcpEnvironmentVariable,
    nullMcpEnvironmentVariable,
    ...mcpEnvironmentVariables,
    ...permissiveMcpEnvironmentVariables,
  ]) {
    assert.deepEqual(Reflect.ownKeys(environment), ['name', 'source']);
  }
  for (const oauth of [
    defaultMcpOauthConfiguration,
    undefinedMcpOauthConfiguration,
    nullMcpOauthConfiguration,
    blankMcpOauthConfiguration,
    whitespaceMcpOauthConfiguration,
    minimumMcpOauthPort,
    maximumMcpOauthPort,
  ]) {
    assert.deepEqual(Reflect.ownKeys(oauth), ['clientId', 'callbackPort']);
  }
  for (const configuration of [
    defaultMcpToolConfiguration,
    undefinedMcpToolConfiguration,
    nullMcpToolConfiguration,
    ...mcpToolConfigurations,
  ]) {
    assert.deepEqual(Reflect.ownKeys(configuration), ['approval']);
  }
  assert.deepEqual(Reflect.ownKeys(planSteps[0]).sort(), ['status', 'text']);
  assert.deepEqual(Reflect.ownKeys(plan).sort(), ['explanation', 'steps']);
  for (const activity of [
    defaultHookActivity,
    undefinedHookActivity,
    ...hookActivities,
    permissiveHookActivity,
    detachedHookActivity,
    proxyHookActivity,
  ]) {
    assert.deepEqual(
      Reflect.ownKeys(activity),
      ['id', 'eventName', 'handlerType', 'status', 'statusMessage', 'details'],
    );
  }
  for (const candidate of [hook, ...hookCatalog.hooks]) {
    assert.deepEqual(
      Reflect.ownKeys(candidate),
      [
        'key', 'currentHash', 'isEnabled', 'eventName', 'handler', 'isManaged', 'source',
        'sourcePath', 'timeoutSeconds', 'trustStatus', 'matcher', 'pluginId', 'statusMessage',
        'origin', 'canUninstall', 'canTrust',
      ],
    );
  }
  assert.deepEqual(Reflect.ownKeys(hookCatalog), ['hooks', 'warnings', 'errors']);
  for (const connector of [defaultConnector, undefinedConnector, customConnector, proxyConnector]) {
    assert.deepEqual(
      Reflect.ownKeys(connector),
      ['id', 'name', 'description', 'installUrl', 'isAccessible', 'isEnabled', 'pluginNames'],
    );
  }
  for (const summary of [conversationSummary, permissiveConversationSummary]) {
    assert.deepEqual(
      Reflect.ownKeys(summary),
      ['conversationId', 'title', 'updatedAtEpochSeconds'],
    );
  }
  assert.deepEqual(Reflect.ownKeys(historicalConversation), ['summary', 'messages']);
  for (const tier of [serviceTier, ...model.serviceTiers]) {
    assert.deepEqual(Reflect.ownKeys(tier), ['id', 'name', 'description']);
  }
  for (const candidate of [defaultModel, model]) {
    assert.deepEqual(
      Reflect.ownKeys(candidate),
      [
        'id',
        'displayName',
        'description',
        'supportedEfforts',
        'defaultEffort',
        'isDefault',
        'serviceTiers',
        'defaultServiceTier',
      ],
    );
  }
  for (const candidate of [...defaultSkills, skill, ...skillCatalog.skills]) {
    assert.deepEqual(
      Reflect.ownKeys(candidate),
      [
        'name',
        'displayName',
        'description',
        'path',
        'scope',
        'isEnabled',
        'brandColor',
        'dependencies',
        'canUninstall',
        'origin',
      ],
    );
  }
  assert.deepEqual(Reflect.ownKeys(skillCatalog), ['skills', 'errors']);
  for (const candidate of [skillChunk, terminalSkillChunk]) {
    assert.deepEqual(Reflect.ownKeys(candidate), ['content', 'nextOffset', 'totalBytes']);
  }
  const browserImport = childProcess.spawnSync(
    process.execPath,
    ['-e', "global.process=undefined;require('@codex-agent-labs/codex-agent')"],
    { cwd: __dirname, encoding: 'utf8' },
  );
  assert.notEqual(browserImport.status, 0);
  assert.match(browserImport.stderr, /supports Node\.js only/);
});

test('cjs projects lifecycle state failure cleanup and terminal delivery', async (context) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'codex-agent-npm-'));
  context.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const bundle = path.join(root, 'bundle');
  const data = path.join(root, 'data');
  const workspace = path.join(root, 'workspace');
  fs.mkdirSync(bundle);
  fs.mkdirSync(data);
  fs.mkdirSync(workspace);

  const host = sdk.createCodexHost(bundle, data, 'javascript', 'JavaScript', 'test');
  assert.deepEqual(Object.keys(host), []);
  assert.equal(Object.isFrozen(host.state), true);
  assert.deepEqual(Object.keys(host.state), []);
  const states = [];
  const observation = host.observeState((state) => states.push(state.status));
  assert.deepEqual(Object.keys(observation), []);
  await settleCallbacks();
  assert.deepEqual(states, ['new']);

  assert.equal(await host.start(), undefined);
  await settleCallbacks();
  assert.equal(host.state.status, 'workspace_required');
  assert.equal(states.at(-1), 'workspace_required');
  assert.equal(host.state.workspace, null);
  assert.equal(host.state.agent, null);
  assert.equal(host.state.selectionReason, 'not_selected');
  assert.equal(host.state.selectionMessage, 'Select a workspace.');
  assert.equal(host.state.failure, null);
  assert.equal(Object.isFrozen(host.state), true);
  assert.equal(host.agent, null);

  await assert.rejects(
    host.selectWorkspace(workspace),
    (error) => error instanceof sdk.CodexError && error.code === 'runtime_prepare_failed',
  );
  await settleCallbacks();
  assert.equal(host.state.status, 'failed');
  assert.equal(host.state.workspace.path, fs.realpathSync(workspace));
  assert.equal(host.state.agent, null);
  assert.equal(host.state.selectionReason, null);
  assert.equal(host.state.selectionMessage, null);
  assert.equal(host.state.failure.code, 'runtime_prepare_failed');
  assert.equal(Object.isFrozen(host.state), true);
  assert.equal(Object.isFrozen(host.state.workspace), true);
  assert.equal(Object.isFrozen(host.state.failure), true);

  assert.equal(await host.close(), undefined);
  assert.equal(await host.dispose(), undefined);
  assert.equal(await host[Symbol.asyncDispose](), undefined);
  await settleCallbacks();
  assert.equal(states.at(-1), 'closed');
  assert.equal(observation.isClosed, true);
  assert.equal(observation.close(), undefined);
  assert.equal(observation.dispose(), undefined);
  assert.equal(observation[Symbol.dispose](), undefined);
});

test('cjs maps AbortSignal cancellation without starting', async (context) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'codex-agent-npm-'));
  context.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const bundle = path.join(root, 'bundle');
  fs.mkdirSync(bundle);
  const aborted = sdk.createCodexHost(bundle, path.join(root, 'aborted'), 'javascript', 'JavaScript', 'test');
  const controller = new AbortController();
  controller.abort();
  await assert.rejects(aborted.start(controller.signal), (error) => error.name === 'AbortError');
  assert.equal(aborted.state.status, 'new');
  assert.equal(await aborted.dispose(), undefined);
});
