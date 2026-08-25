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
  assert.deepEqual(
    ['never', 'auto_review', 'ask_me', 'strict'].map((preset) =>
      sdk.codexApprovalPresetDisplayName(preset)),
    ['Never', 'Auto review', 'Ask me', 'Strict'],
  );
  assert.throws(() => sdk.codexApprovalPresetDisplayName('AUTO_REVIEW'));
  assert.throws(() => sdk.codexApprovalPresetDisplayName(0));
  assert.throws(() => new sdk.CodexHost());
  assert.throws(() => new sdk.CodexAgent());
  assert.throws(() => new sdk.CodexAuthentication());
  assert.throws(() => new sdk.CodexConnectors());
  assert.throws(() => new sdk.CodexModels());
  assert.throws(() => new sdk.CodexAuthenticationState());
  assert.throws(() => new sdk.CodexConversation());
  assert.throws(() => new sdk.CodexObservation());
  assert.equal(typeof sdk.CodexAgent.prototype.rename, 'function');
  assert.equal(typeof sdk.CodexAgent.prototype.delete, 'function');
  assert.equal(typeof sdk.CodexAgent.prototype.listConversations, 'function');
  for (const constructor of [
    sdk.AgentConnector,
    sdk.AgentConversationSummary,
    sdk.AgentElicitationValidation,
    sdk.AgentElicitationValidationIssue,
    sdk.AgentFormBooleanValue,
    sdk.AgentFormNumberValue,
    sdk.AgentFormOption,
    sdk.AgentFormTextListValue,
    sdk.AgentFormTextValue,
    sdk.AgentHookActivity,
    sdk.AgentMcpEnvironmentVariable,
    sdk.AgentMcpOauthConfiguration,
    sdk.AgentMcpToolConfiguration,
    sdk.AgentModel,
    sdk.AgentPlanProgress,
    sdk.AgentPlanStep,
    sdk.AgentServiceTier,
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
    conversationSummary,
    permissiveConversationSummary,
    serviceTier,
    defaultModel,
    model,
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
  assert.equal(host.agent, null);

  await assert.rejects(
    host.selectWorkspace(workspace),
    (error) => error instanceof sdk.CodexError && error.code === 'runtime_prepare_failed',
  );
  await settleCallbacks();
  assert.equal(host.state.status, 'failed');
  assert.equal(host.state.failure.code, 'runtime_prepare_failed');
  assert.equal(Object.isFrozen(host.state), true);
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
