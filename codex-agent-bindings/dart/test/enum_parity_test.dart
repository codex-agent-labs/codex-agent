import 'dart:convert';
import 'dart:ffi';
import 'dart:io';

import 'package:codex_agent/codex_agent.dart';
import 'package:test/test.dart';

import 'agent_parity.dart';
import 'conversation_parity.dart';
import 'host_parity.dart';
import 'leaf_service_parity.dart';
import 'residual_parity.dart';
import 'synchronous_value_function_parity.dart';
import 'test_inputs.dart';

typedef _EnumValueNative = Int32 Function(Size);
typedef _EnumValueDart = int Function(int);

const _claimsHeader =
    'capabilityKey\tpublicSymbols\texecutedTests\tcompilerEvidenceIds\tsharedScenarios';
const _sharedScenarioIds = <String>{
  'async-failure',
  'async-success',
  'cancellation',
  'collection-immutability-ordering',
  'identity',
  'nullability',
  'parent-child-ownership',
  'repeated-close-dispose',
  'state-current-value',
  'state-subsequent-value',
  'structured-failure',
  'subscription-cancellation',
  'terminal-delivery',
  'value-conversion',
};

final class _Claim {
  const _Claim({
    required this.capabilityKey,
    required this.publicSymbols,
    required this.executedTests,
    required this.compilerEvidenceIds,
    required this.sharedScenarios,
  });

  final String capabilityKey;
  final List<String> publicSymbols;
  final List<String> executedTests;
  final List<String> compilerEvidenceIds;
  final List<String> sharedScenarios;
}

final _publicEnumValues = <String, int>{
  'CodexApprovalDecision.accept': CodexApprovalDecision.accept.value,
  'CodexApprovalDecision.decline': CodexApprovalDecision.decline.value,
  'CodexApprovalPreset.askMe': CodexApprovalPreset.askMe.value,
  'CodexApprovalPreset.autoReview': CodexApprovalPreset.autoReview.value,
  'CodexApprovalPreset.never': CodexApprovalPreset.never.value,
  'CodexApprovalPreset.strict': CodexApprovalPreset.strict.value,
  'CodexAuthenticationStatus.authenticated':
      CodexAuthenticationStatus.authenticated.value,
  'CodexAuthenticationStatus.authenticating':
      CodexAuthenticationStatus.authenticating.value,
  'CodexAuthenticationStatus.signedOut':
      CodexAuthenticationStatus.signedOut.value,
  'CodexCapability.webSearch': CodexCapability.webSearch.value,
  'CodexCatalogFreshness.freshCache': CodexCatalogFreshness.freshCache.value,
  'CodexCatalogFreshness.live': CodexCatalogFreshness.live.value,
  'CodexCatalogFreshness.staleCache': CodexCatalogFreshness.staleCache.value,
  'CodexCollaborationMode.defaultMode':
      CodexCollaborationMode.defaultMode.value,
  'CodexCollaborationMode.plan': CodexCollaborationMode.plan.value,
  'CodexConversationStatus.cancellingTurn':
      CodexConversationStatus.cancellingTurn.value,
  'CodexConversationStatus.closed': CodexConversationStatus.closed.value,
  'CodexConversationStatus.failed': CodexConversationStatus.failed.value,
  'CodexConversationStatus.newConversation':
      CodexConversationStatus.newConversation.value,
  'CodexConversationStatus.opening': CodexConversationStatus.opening.value,
  'CodexConversationStatus.ready': CodexConversationStatus.ready.value,
  'CodexConversationStatus.reloading': CodexConversationStatus.reloading.value,
  'CodexConversationStatus.runningTurn':
      CodexConversationStatus.runningTurn.value,
  'CodexConversationStatus.startingTurn':
      CodexConversationStatus.startingTurn.value,
  'CodexElicitationAction.accept': CodexElicitationAction.accept.value,
  'CodexElicitationAction.cancel': CodexElicitationAction.cancel.value,
  'CodexElicitationAction.decline': CodexElicitationAction.decline.value,
  'CodexElicitationValidationReason.aboveMaximum':
      CodexElicitationValidationReason.aboveMaximum.value,
  'CodexElicitationValidationReason.belowMinimum':
      CodexElicitationValidationReason.belowMinimum.value,
  'CodexElicitationValidationReason.duplicateSelection':
      CodexElicitationValidationReason.duplicateSelection.value,
  'CodexElicitationValidationReason.invalidFormat':
      CodexElicitationValidationReason.invalidFormat.value,
  'CodexElicitationValidationReason.invalidSelection':
      CodexElicitationValidationReason.invalidSelection.value,
  'CodexElicitationValidationReason.invalidType':
      CodexElicitationValidationReason.invalidType.value,
  'CodexElicitationValidationReason.missingRequired':
      CodexElicitationValidationReason.missingRequired.value,
  'CodexElicitationValidationReason.nonFiniteNumber':
      CodexElicitationValidationReason.nonFiniteNumber.value,
  'CodexElicitationValidationReason.nonInteger':
      CodexElicitationValidationReason.nonInteger.value,
  'CodexElicitationValidationReason.unknownField':
      CodexElicitationValidationReason.unknownField.value,
  'CodexFormFieldType.boolean': CodexFormFieldType.boolean.value,
  'CodexFormFieldType.integer': CodexFormFieldType.integer.value,
  'CodexFormFieldType.multiSelect': CodexFormFieldType.multiSelect.value,
  'CodexFormFieldType.number': CodexFormFieldType.number.value,
  'CodexFormFieldType.singleSelect': CodexFormFieldType.singleSelect.value,
  'CodexFormFieldType.string': CodexFormFieldType.string.value,
  'CodexFormStringFormat.dateTime': CodexFormStringFormat.dateTime.value,
  'CodexFormStringFormat.date': CodexFormStringFormat.date.value,
  'CodexFormStringFormat.email': CodexFormStringFormat.email.value,
  'CodexFormStringFormat.uri': CodexFormStringFormat.uri.value,
  'CodexHookRunStatus.blocked': CodexHookRunStatus.blocked.value,
  'CodexHookRunStatus.completed': CodexHookRunStatus.completed.value,
  'CodexHookRunStatus.failed': CodexHookRunStatus.failed.value,
  'CodexHookRunStatus.running': CodexHookRunStatus.running.value,
  'CodexHookRunStatus.stopped': CodexHookRunStatus.stopped.value,
  'CodexHookTrustStatus.managed': CodexHookTrustStatus.managed.value,
  'CodexHookTrustStatus.modified': CodexHookTrustStatus.modified.value,
  'CodexHookTrustStatus.trusted': CodexHookTrustStatus.trusted.value,
  'CodexHookTrustStatus.untrusted': CodexHookTrustStatus.untrusted.value,
  'CodexInstallationScope.user': CodexInstallationScope.user.value,
  'CodexInstallationScope.workspace': CodexInstallationScope.workspace.value,
  'CodexIntegrationAuthorizationStatus.authorized':
      CodexIntegrationAuthorizationStatus.authorized.value,
  'CodexIntegrationAuthorizationStatus.awaitingCompletion':
      CodexIntegrationAuthorizationStatus.awaitingCompletion.value,
  'CodexIntegrationAuthorizationStatus.failed':
      CodexIntegrationAuthorizationStatus.failed.value,
  'CodexIntegrationAuthorizationStatus.idle':
      CodexIntegrationAuthorizationStatus.idle.value,
  'CodexIntegrationAuthorizationStatus.starting':
      CodexIntegrationAuthorizationStatus.starting.value,
  'CodexMcpAuthStatus.bearerToken': CodexMcpAuthStatus.bearerToken.value,
  'CodexMcpAuthStatus.notLoggedIn': CodexMcpAuthStatus.notLoggedIn.value,
  'CodexMcpAuthStatus.oauth': CodexMcpAuthStatus.oauth.value,
  'CodexMcpAuthStatus.unknown': CodexMcpAuthStatus.unknown.value,
  'CodexMcpAuthStatus.unsupported': CodexMcpAuthStatus.unsupported.value,
  'CodexMcpAuthentication.chatGpt': CodexMcpAuthentication.chatGpt.value,
  'CodexMcpAuthentication.oauth': CodexMcpAuthentication.oauth.value,
  'CodexMcpEnvironmentSource.local': CodexMcpEnvironmentSource.local.value,
  'CodexMcpEnvironmentSource.remote': CodexMcpEnvironmentSource.remote.value,
  'CodexMcpToolApproval.approve': CodexMcpToolApproval.approve.value,
  'CodexMcpToolApproval.auto': CodexMcpToolApproval.auto.value,
  'CodexMcpToolApproval.prompt': CodexMcpToolApproval.prompt.value,
  'CodexMcpToolApproval.writes': CodexMcpToolApproval.writes.value,
  'CodexMcpToolExposureSurface.codeMode':
      CodexMcpToolExposureSurface.codeMode.value,
  'CodexMcpToolExposureSurface.deferred':
      CodexMcpToolExposureSurface.deferred.value,
  'CodexMcpToolExposureSurface.direct':
      CodexMcpToolExposureSurface.direct.value,
  'CodexMessageRole.assistant': CodexMessageRole.assistant.value,
  'CodexMessageRole.user': CodexMessageRole.user.value,
  'CodexPlanStepStatus.completed': CodexPlanStepStatus.completed.value,
  'CodexPlanStepStatus.inProgress': CodexPlanStepStatus.inProgress.value,
  'CodexPlanStepStatus.pending': CodexPlanStepStatus.pending.value,
  'CodexPluginAuthPolicy.onInstall': CodexPluginAuthPolicy.onInstall.value,
  'CodexPluginAuthPolicy.onUse': CodexPluginAuthPolicy.onUse.value,
  'CodexPluginInstallPolicy.available':
      CodexPluginInstallPolicy.available.value,
  'CodexPluginInstallPolicy.installedByDefault':
      CodexPluginInstallPolicy.installedByDefault.value,
  'CodexPluginInstallPolicy.notAvailable':
      CodexPluginInstallPolicy.notAvailable.value,
  'CodexResolution.defaultResolution': CodexResolution.defaultResolution.value,
  'CodexResolution.first': CodexResolution.first.value,
  'CodexResolution.preferred': CodexResolution.preferred.value,
  'CodexResourceOrigin.managed': CodexResourceOrigin.managed.value,
  'CodexResourceOrigin.plugin': CodexResourceOrigin.plugin.value,
  'CodexResourceOrigin.unknown': CodexResourceOrigin.unknown.value,
  'CodexResourceOrigin.user': CodexResourceOrigin.user.value,
  'CodexResourceOrigin.workspace': CodexResourceOrigin.workspace.value,
  'CodexSkillScope.admin': CodexSkillScope.admin.value,
  'CodexSkillScope.plugin': CodexSkillScope.plugin.value,
  'CodexSkillScope.repo': CodexSkillScope.repo.value,
  'CodexSkillScope.system': CodexSkillScope.system.value,
  'CodexSkillScope.user': CodexSkillScope.user.value,
  'CodexWorkActivity.runningCommand': CodexWorkActivity.runningCommand.value,
  'CodexWorkActivity.writingFiles': CodexWorkActivity.writingFiles.value,
  'CodexAuthorizationPurpose.chatGpt': CodexAuthorizationPurpose.chatGpt.value,
  'CodexAuthorizationPurpose.external':
      CodexAuthorizationPurpose.external.value,
  'CodexWorkspaceSelectionReason.accessRevoked':
      CodexWorkspaceSelectionReason.accessRevoked.value,
  'CodexWorkspaceSelectionReason.invalidSelection':
      CodexWorkspaceSelectionReason.invalidSelection.value,
  'CodexWorkspaceSelectionReason.notFound':
      CodexWorkspaceSelectionReason.notFound.value,
  'CodexWorkspaceSelectionReason.notSelected':
      CodexWorkspaceSelectionReason.notSelected.value,
};

List<String> _pair(String symbol) => <String>['$symbol:0', '$symbol:1'];

final _conversationId = CodexConversationId('CodexConversationId.value');
final _conversationSettings = CodexConversationSettings(
  approvalPreset: CodexApprovalPreset.strict,
  serviceTier: 'CodexConversationSettings.serviceTier',
);
final _conversationSummary = CodexConversationSummary(
  conversationId: _conversationId,
  title: 'CodexConversationSummary.title',
  updatedAtEpochSeconds: 17,
);
final _clientInfo = CodexClientInfo(
  name: 'CodexClientInfo.name',
  title: 'CodexClientInfo.title',
  version: 'CodexClientInfo.version',
);
final _failure = CodexFailure(
  code: 'CodexFailure.code',
  message: 'CodexFailure.message',
  isRecoverable: true,
);
final _workspace = CodexWorkspace(
  path: 'CodexWorkspace.path',
  displayName: 'CodexWorkspace.displayName',
);
final _validationIssue0 = CodexElicitationValidationIssue(
  fieldName: 'CodexElicitationValidation.issues:0',
  reason: CodexElicitationValidationReason.invalidFormat,
);
final _validationIssue1 = CodexElicitationValidationIssue(
  fieldName: 'CodexElicitationValidation.issues:1',
  reason: CodexElicitationValidationReason.invalidSelection,
);
final _validationIssue = CodexElicitationValidationIssue(
  fieldName: 'CodexElicitationValidationIssue.fieldName',
  reason: CodexElicitationValidationReason.invalidFormat,
);
final _validation = CodexElicitationValidation(
  issues: <CodexElicitationValidationIssue>[
    _validationIssue0,
    _validationIssue1,
  ],
);
final _formOption = CodexFormOption(
  value: 'CodexFormOption.value',
  title: 'CodexFormOption.title',
  description: 'CodexFormOption.description',
);
final _mcpEnvironmentVariable = CodexMcpEnvironmentVariable(
  name: 'CodexMcpEnvironmentVariable.name',
  source: CodexMcpEnvironmentSource.remote,
);
final _mcpOauth = CodexMcpOauthConfiguration(
  clientId: 'CodexMcpOauthConfiguration.clientId',
  callbackPort: 65535,
);
final _mcpTool = CodexMcpToolConfiguration(
  approval: CodexMcpToolApproval.prompt,
);
final _mcpHttp = CodexMcpHttpTransport(
  url: 'https://example.test/mcp',
  bearerTokenEnvironmentVariable:
      'CodexMcpHttpTransport.bearerTokenEnvironmentVariable',
  headers: const <String, String>{'first': 'one', 'second': 'two'},
  environmentHeaders: const <String, String>{
    'first-env': 'one-env',
    'second-env': 'two-env',
  },
  headersHelper: 'CodexMcpHttpTransport.headersHelper',
);
final _mcpStdio = CodexMcpStdioTransport(
  command: 'CodexMcpStdioTransport.command',
  arguments: _pair('CodexMcpStdioTransport.arguments'),
  workingDirectory: 'CodexMcpStdioTransport.workingDirectory',
  environment: const <String, String>{'first': 'one', 'second': 'two'},
  forwardedEnvironment: <CodexMcpEnvironmentVariable>[
    CodexMcpEnvironmentVariable(name: 'first'),
    CodexMcpEnvironmentVariable(
      name: 'second',
      source: CodexMcpEnvironmentSource.remote,
    ),
  ],
);
final _mcpServerConfiguration = CodexMcpServerConfiguration(
  name: 'mcp_server',
  transport: _mcpHttp,
  authentication: CodexMcpAuthentication.oauth,
  environmentId: 'local',
  isEnabled: true,
  isRequired: true,
  supportsParallelToolCalls: true,
  omitToolsFrom: const <CodexMcpToolExposureSurface>[
    CodexMcpToolExposureSurface.direct,
    CodexMcpToolExposureSurface.deferred,
  ],
  startupTimeoutSeconds: 17,
  toolTimeoutSeconds: 17,
  defaultToolApproval: CodexMcpToolApproval.prompt,
  enabledTools: _pair('CodexMcpServerConfiguration.enabledTools'),
  disabledTools: _pair('CodexMcpServerConfiguration.disabledTools'),
  scopes: _pair('CodexMcpServerConfiguration.scopes'),
  oauth: _mcpOauth,
  oauthResource: 'CodexMcpServerConfiguration.oauthResource',
  tools: <String, CodexMcpToolConfiguration>{
    'first': const CodexMcpToolConfiguration(
      approval: CodexMcpToolApproval.auto,
    ),
    'second': _mcpTool,
  },
);
final _mcpServer = CodexMcpServer(
  name: 'CodexMcpServer.name',
  displayName: 'CodexMcpServer.displayName',
  authStatus: CodexMcpAuthStatus.oauth,
  configuration: _mcpServerConfiguration,
  origin: CodexResourceOrigin.plugin,
  canRemove: true,
);
final _planStep0 = CodexPlanStep(
  text: 'CodexPlanProgress.steps:0',
  status: CodexPlanStepStatus.inProgress,
);
final _planStep1 = CodexPlanStep(
  text: 'CodexPlanProgress.steps:1',
  status: CodexPlanStepStatus.completed,
);
final _planStep = CodexPlanStep(
  text: 'CodexPlanStep.text',
  status: CodexPlanStepStatus.completed,
);
final _planProgress = CodexPlanProgress(
  explanation: 'CodexPlanProgress.explanation',
  steps: <CodexPlanStep>[_planStep0, _planStep1],
);
final _serviceTier0 = CodexServiceTier(
  id: 'CodexModel.serviceTiers:0',
  name: 'tier zero',
  description: 'tier zero description',
);
final _serviceTier1 = CodexServiceTier(
  id: 'CodexModel.serviceTiers:1',
  name: 'tier one',
  description: 'tier one description',
);
final _serviceTier = CodexServiceTier(
  id: 'CodexServiceTier.id',
  name: 'CodexServiceTier.name',
  description: 'CodexServiceTier.description',
);
final _model = CodexModel(
  id: 'CodexModel.id',
  displayName: 'CodexModel.displayName',
  description: 'CodexModel.description',
  supportedEfforts: _pair('CodexModel.supportedEfforts'),
  defaultEffort: 'CodexModel.defaultEffort',
  isDefault: true,
  serviceTiers: <CodexServiceTier>[_serviceTier0, _serviceTier1],
  defaultServiceTier: 'CodexModel.defaultServiceTier',
);
final _connector0 = CodexConnector(
  id: 'CodexPluginDetail.connectors:0',
  name: 'connector zero',
);
final _connector1 = CodexConnector(
  id: 'CodexPluginDetail.connectors:1',
  name: 'connector one',
);
final _connector = CodexConnector(
  id: 'CodexConnector.id',
  name: 'CodexConnector.name',
  description: 'CodexConnector.description',
  installUrl: 'CodexConnector.installUrl',
  isAccessible: true,
  isEnabled: true,
  pluginNames: _pair('CodexConnector.pluginNames'),
);
final _pluginReference = CodexPluginReference(
  id: 'CodexPluginReference.id',
  name: 'CodexPluginReference.name',
  marketplaceName: 'CodexPluginReference.marketplaceName',
  marketplacePath: 'CodexPluginReference.marketplacePath',
  remotePluginId: 'CodexPluginReference.remotePluginId',
);
final _pluginSkill0 = CodexPluginSkill(
  name: 'CodexPluginDetail.skills:0',
  description: 'skill zero',
  isEnabled: true,
);
final _pluginSkill1 = CodexPluginSkill(
  name: 'CodexPluginDetail.skills:1',
  description: 'skill one',
  isEnabled: true,
);
final _pluginSkill = CodexPluginSkill(
  name: 'CodexPluginSkill.name',
  description: 'CodexPluginSkill.description',
  isEnabled: true,
  path: 'CodexPluginSkill.path',
);
final _pluginSummary0 = CodexPluginSummary(
  reference: _pluginReference,
  displayName: 'CodexPluginCatalog.plugins:0',
  description: 'plugin zero',
  isInstalled: true,
  isEnabled: true,
  installPolicy: CodexPluginInstallPolicy.installedByDefault,
  authPolicy: CodexPluginAuthPolicy.onUse,
  isAvailable: true,
);
final _pluginSummary1 = CodexPluginSummary(
  reference: _pluginReference,
  displayName: 'CodexPluginCatalog.plugins:1',
  description: 'plugin one',
  isInstalled: true,
  isEnabled: true,
  installPolicy: CodexPluginInstallPolicy.available,
  authPolicy: CodexPluginAuthPolicy.onInstall,
  isAvailable: true,
);
final _pluginSummary = CodexPluginSummary(
  reference: _pluginReference,
  displayName: 'CodexPluginSummary.displayName',
  description: 'CodexPluginSummary.description',
  isInstalled: true,
  isEnabled: true,
  installPolicy: CodexPluginInstallPolicy.installedByDefault,
  authPolicy: CodexPluginAuthPolicy.onUse,
  isAvailable: true,
  capabilities: _pair('CodexPluginSummary.capabilities'),
  brandColor: 'CodexPluginSummary.brandColor',
  privacyPolicyUrl: 'CodexPluginSummary.privacyPolicyUrl',
  termsOfServiceUrl: 'CodexPluginSummary.termsOfServiceUrl',
  websiteUrl: 'CodexPluginSummary.websiteUrl',
);
final _pluginCatalog = CodexPluginCatalog(
  plugins: <CodexPluginSummary>[_pluginSummary0, _pluginSummary1],
  errors: _pair('CodexPluginCatalog.errors'),
  freshness: CodexCatalogFreshness.staleCache,
);
final _pluginDetail = CodexPluginDetail(
  summary: _pluginSummary,
  description: 'CodexPluginDetail.description',
  skills: <CodexPluginSkill>[_pluginSkill0, _pluginSkill1],
  connectors: <CodexConnector>[_connector0, _connector1],
  mcpServers: _pair('CodexPluginDetail.mcpServers'),
  hookCount: 17,
);
final _authConnector0 = CodexConnector(
  id: 'CodexPluginInstallResult.connectorsNeedingAuthentication:0',
  name: 'authentication connector zero',
);
final _authConnector1 = CodexConnector(
  id: 'CodexPluginInstallResult.connectorsNeedingAuthentication:1',
  name: 'authentication connector one',
);
final _pluginInstallResult = CodexPluginInstallResult(
  authPolicy: CodexPluginAuthPolicy.onUse,
  connectorsNeedingAuthentication: <CodexConnector>[
    _authConnector0,
    _authConnector1,
  ],
  message: 'CodexPluginInstallResult.message',
);
final _skill0 = CodexSkill(
  name: 'CodexSkillCatalog.skills:0',
  displayName: 'skill zero',
  description: 'skill zero',
  path: '/skill/zero',
  scope: CodexSkillScope.plugin,
  isEnabled: true,
);
final _skill1 = CodexSkill(
  name: 'CodexSkillCatalog.skills:1',
  displayName: 'skill one',
  description: 'skill one',
  path: '/skill/one',
  scope: CodexSkillScope.repo,
  isEnabled: true,
);
final _skill = CodexSkill(
  name: 'CodexSkill.name',
  displayName: 'CodexSkill.displayName',
  description: 'CodexSkill.description',
  path: 'CodexSkill.path',
  scope: CodexSkillScope.plugin,
  isEnabled: true,
  brandColor: 'CodexSkill.brandColor',
  dependencies: _pair('CodexSkill.dependencies'),
  canUninstall: true,
  origin: CodexResourceOrigin.plugin,
);
final _skillCatalog = CodexSkillCatalog(
  skills: <CodexSkill>[_skill0, _skill1],
  errors: _pair('CodexSkillCatalog.errors'),
);
final _skillChunk = CodexSkillChunk(
  content: 'CodexSkillChunk.content',
  nextOffset: 17,
  totalBytes: 17,
);
final _hook0 = CodexHookActivity(
  id: 'CodexTurnProgress.hookActivities:0',
  eventName: 'hook zero',
  handlerType: 'command',
  status: CodexHookRunStatus.completed,
);
final _hook1 = CodexHookActivity(
  id: 'CodexTurnProgress.hookActivities:1',
  eventName: 'hook one',
  handlerType: 'command',
  status: CodexHookRunStatus.running,
);
final _hookActivity = CodexHookActivity(
  id: 'CodexHookActivity.id',
  eventName: 'CodexHookActivity.eventName',
  handlerType: 'CodexHookActivity.handlerType',
  status: CodexHookRunStatus.completed,
  statusMessage: 'CodexHookActivity.statusMessage',
  details: _pair('CodexHookActivity.details'),
);
final _turnProgress = CodexTurnProgress(
  text: 'CodexTurnProgress.text',
  commentary: 'CodexTurnProgress.commentary',
  reasoning: 'CodexTurnProgress.reasoning',
  plan: 'CodexTurnProgress.plan',
  planProgress: _planProgress,
  shellOutput: 'CodexTurnProgress.shellOutput',
  shellExitCode: 17,
  workActivity: CodexWorkActivity.writingFiles,
  hookActivities: <CodexHookActivity>[_hook0, _hook1],
  isTruncated: true,
);
final _publicValueAccessors = <String, Object? Function()>{
  'CodexConnector.new': () => _connector,
  'CodexConnector.description': () => _connector.description,
  'CodexConnector.id': () => _connector.id,
  'CodexConnector.installUrl': () => _connector.installUrl,
  'CodexConnector.isAccessible': () => _connector.isAccessible,
  'CodexConnector.isEnabled': () => _connector.isEnabled,
  'CodexConnector.name': () => _connector.name,
  'CodexConnector.pluginNames': () => _connector.pluginNames,
  'CodexConversationSettings.new': () => _conversationSettings,
  'CodexConversationSettings.approvalPreset': () =>
      _conversationSettings.approvalPreset,
  'CodexConversationSettings.serviceTier': () =>
      _conversationSettings.serviceTier,
  'CodexConversationSummary.new': () => _conversationSummary,
  'CodexConversationSummary.conversationId': () =>
      _conversationSummary.conversationId,
  'CodexConversationSummary.title': () => _conversationSummary.title,
  'CodexConversationSummary.updatedAtEpochSeconds': () =>
      _conversationSummary.updatedAtEpochSeconds,
  'CodexElicitationValidationIssue.new': () => _validationIssue,
  'CodexElicitationValidationIssue.fieldName': () => _validationIssue.fieldName,
  'CodexElicitationValidationIssue.reason': () => _validationIssue.reason,
  'CodexElicitationValidation.new': () => _validation,
  'CodexElicitationValidation.isValid': () => _validation.isValid,
  'CodexElicitationValidation.issues': () => _validation.issues,
  'CodexFormOption.new': () => _formOption,
  'CodexFormOption.description': () => _formOption.description,
  'CodexFormOption.title': () => _formOption.title,
  'CodexFormOption.value': () => _formOption.value,
  'CodexHookActivity.new': () => _hookActivity,
  'CodexHookActivity.details': () => _hookActivity.details,
  'CodexHookActivity.eventName': () => _hookActivity.eventName,
  'CodexHookActivity.handlerType': () => _hookActivity.handlerType,
  'CodexHookActivity.id': () => _hookActivity.id,
  'CodexHookActivity.statusMessage': () => _hookActivity.statusMessage,
  'CodexHookActivity.status': () => _hookActivity.status,
  'CodexMcpEnvironmentVariable.new': () => _mcpEnvironmentVariable,
  'CodexMcpEnvironmentVariable.name': () => _mcpEnvironmentVariable.name,
  'CodexMcpEnvironmentVariable.source': () => _mcpEnvironmentVariable.source,
  'CodexMcpOauthConfiguration.new': () => _mcpOauth,
  'CodexMcpOauthConfiguration.callbackPort': () => _mcpOauth.callbackPort,
  'CodexMcpOauthConfiguration.clientId': () => _mcpOauth.clientId,
  'CodexMcpToolConfiguration.new': () => _mcpTool,
  'CodexMcpToolConfiguration.approval': () => _mcpTool.approval,
  'CodexMcpHttpTransport.new': () => _mcpHttp,
  'CodexMcpHttpTransport.bearerTokenEnvironmentVariable': () =>
      _mcpHttp.bearerTokenEnvironmentVariable,
  'CodexMcpHttpTransport.environmentHeaders': () => _mcpHttp.environmentHeaders,
  'CodexMcpHttpTransport.headers': () => _mcpHttp.headers,
  'CodexMcpHttpTransport.headersHelper': () => _mcpHttp.headersHelper,
  'CodexMcpHttpTransport.url': () => _mcpHttp.url,
  'CodexMcpStdioTransport.new': () => _mcpStdio,
  'CodexMcpStdioTransport.arguments': () => _mcpStdio.arguments,
  'CodexMcpStdioTransport.command': () => _mcpStdio.command,
  'CodexMcpStdioTransport.environment': () => _mcpStdio.environment,
  'CodexMcpStdioTransport.forwardedEnvironment': () =>
      _mcpStdio.forwardedEnvironment,
  'CodexMcpStdioTransport.workingDirectory': () => _mcpStdio.workingDirectory,
  'CodexMcpServerConfiguration.new': () => _mcpServerConfiguration,
  'CodexMcpServerConfiguration.authentication': () =>
      _mcpServerConfiguration.authentication,
  'CodexMcpServerConfiguration.defaultToolApproval': () =>
      _mcpServerConfiguration.defaultToolApproval,
  'CodexMcpServerConfiguration.disabledTools': () =>
      _mcpServerConfiguration.disabledTools,
  'CodexMcpServerConfiguration.enabledTools': () =>
      _mcpServerConfiguration.enabledTools,
  'CodexMcpServerConfiguration.environmentId': () =>
      _mcpServerConfiguration.environmentId,
  'CodexMcpServerConfiguration.isEnabled': () =>
      _mcpServerConfiguration.isEnabled,
  'CodexMcpServerConfiguration.isRequired': () =>
      _mcpServerConfiguration.isRequired,
  'CodexMcpServerConfiguration.name': () => _mcpServerConfiguration.name,
  'CodexMcpServerConfiguration.oauth': () => _mcpServerConfiguration.oauth,
  'CodexMcpServerConfiguration.oauthResource': () =>
      _mcpServerConfiguration.oauthResource,
  'CodexMcpServerConfiguration.omitToolsFrom': () =>
      _mcpServerConfiguration.omitToolsFrom,
  'CodexMcpServerConfiguration.scopes': () => _mcpServerConfiguration.scopes,
  'CodexMcpServerConfiguration.startupTimeoutSeconds': () =>
      _mcpServerConfiguration.startupTimeoutSeconds,
  'CodexMcpServerConfiguration.supportsParallelToolCalls': () =>
      _mcpServerConfiguration.supportsParallelToolCalls,
  'CodexMcpServerConfiguration.toolTimeoutSeconds': () =>
      _mcpServerConfiguration.toolTimeoutSeconds,
  'CodexMcpServerConfiguration.tools': () => _mcpServerConfiguration.tools,
  'CodexMcpServerConfiguration.transport': () =>
      _mcpServerConfiguration.transport,
  'CodexMcpServer.new': () => _mcpServer,
  'CodexMcpServer.authStatus': () => _mcpServer.authStatus,
  'CodexMcpServer.canRemove': () => _mcpServer.canRemove,
  'CodexMcpServer.configuration': () => _mcpServer.configuration,
  'CodexMcpServer.displayName': () => _mcpServer.displayName,
  'CodexMcpServer.isAuthorized': () => _mcpServer.isAuthorized,
  'CodexMcpServer.name': () => _mcpServer.name,
  'CodexMcpServer.origin': () => _mcpServer.origin,
  'CodexModel.new': () => _model,
  'CodexModel.defaultEffort': () => _model.defaultEffort,
  'CodexModel.defaultServiceTier': () => _model.defaultServiceTier,
  'CodexModel.description': () => _model.description,
  'CodexModel.displayName': () => _model.displayName,
  'CodexModel.id': () => _model.id,
  'CodexModel.isDefault': () => _model.isDefault,
  'CodexModel.serviceTiers': () => _model.serviceTiers,
  'CodexModel.supportedEfforts': () => _model.supportedEfforts,
  'CodexPlanProgress.new': () => _planProgress,
  'CodexPlanProgress.explanation': () => _planProgress.explanation,
  'CodexPlanProgress.steps': () => _planProgress.steps,
  'CodexPlanStep.new': () => _planStep,
  'CodexPlanStep.status': () => _planStep.status,
  'CodexPlanStep.text': () => _planStep.text,
  'CodexPluginCatalog.new': () => _pluginCatalog,
  'CodexPluginCatalog.errors': () => _pluginCatalog.errors,
  'CodexPluginCatalog.freshness': () => _pluginCatalog.freshness,
  'CodexPluginCatalog.plugins': () => _pluginCatalog.plugins,
  'CodexPluginDetail.new': () => _pluginDetail,
  'CodexPluginDetail.connectors': () => _pluginDetail.connectors,
  'CodexPluginDetail.description': () => _pluginDetail.description,
  'CodexPluginDetail.hookCount': () => _pluginDetail.hookCount,
  'CodexPluginDetail.mcpServers': () => _pluginDetail.mcpServers,
  'CodexPluginDetail.skills': () => _pluginDetail.skills,
  'CodexPluginDetail.summary': () => _pluginDetail.summary,
  'CodexPluginInstallResult.new': () => _pluginInstallResult,
  'CodexPluginInstallResult.authPolicy': () => _pluginInstallResult.authPolicy,
  'CodexPluginInstallResult.connectorsNeedingAuthentication': () =>
      _pluginInstallResult.connectorsNeedingAuthentication,
  'CodexPluginInstallResult.message': () => _pluginInstallResult.message,
  'CodexPluginReference.new': () => _pluginReference,
  'CodexPluginReference.id': () => _pluginReference.id,
  'CodexPluginReference.marketplaceName': () =>
      _pluginReference.marketplaceName,
  'CodexPluginReference.marketplacePath': () =>
      _pluginReference.marketplacePath,
  'CodexPluginReference.name': () => _pluginReference.name,
  'CodexPluginReference.remotePluginId': () => _pluginReference.remotePluginId,
  'CodexPluginReference.uri': () => _pluginReference.uri,
  'CodexPluginSkill.new': () => _pluginSkill,
  'CodexPluginSkill.description': () => _pluginSkill.description,
  'CodexPluginSkill.isEnabled': () => _pluginSkill.isEnabled,
  'CodexPluginSkill.name': () => _pluginSkill.name,
  'CodexPluginSkill.path': () => _pluginSkill.path,
  'CodexPluginSummary.new': () => _pluginSummary,
  'CodexPluginSummary.authPolicy': () => _pluginSummary.authPolicy,
  'CodexPluginSummary.brandColor': () => _pluginSummary.brandColor,
  'CodexPluginSummary.capabilities': () => _pluginSummary.capabilities,
  'CodexPluginSummary.description': () => _pluginSummary.description,
  'CodexPluginSummary.displayName': () => _pluginSummary.displayName,
  'CodexPluginSummary.installPolicy': () => _pluginSummary.installPolicy,
  'CodexPluginSummary.isAvailable': () => _pluginSummary.isAvailable,
  'CodexPluginSummary.isEnabled': () => _pluginSummary.isEnabled,
  'CodexPluginSummary.isInstalled': () => _pluginSummary.isInstalled,
  'CodexPluginSummary.privacyPolicyUrl': () => _pluginSummary.privacyPolicyUrl,
  'CodexPluginSummary.reference': () => _pluginSummary.reference,
  'CodexPluginSummary.termsOfServiceUrl': () =>
      _pluginSummary.termsOfServiceUrl,
  'CodexPluginSummary.websiteUrl': () => _pluginSummary.websiteUrl,
  'CodexServiceTier.new': () => _serviceTier,
  'CodexServiceTier.description': () => _serviceTier.description,
  'CodexServiceTier.id': () => _serviceTier.id,
  'CodexServiceTier.name': () => _serviceTier.name,
  'CodexSkillCatalog.new': () => _skillCatalog,
  'CodexSkillCatalog.errors': () => _skillCatalog.errors,
  'CodexSkillCatalog.skills': () => _skillCatalog.skills,
  'CodexSkillChunk.new': () => _skillChunk,
  'CodexSkillChunk.content': () => _skillChunk.content,
  'CodexSkillChunk.nextOffset': () => _skillChunk.nextOffset,
  'CodexSkillChunk.totalBytes': () => _skillChunk.totalBytes,
  'CodexSkill.new': () => _skill,
  'CodexSkill.brandColor': () => _skill.brandColor,
  'CodexSkill.canUninstall': () => _skill.canUninstall,
  'CodexSkill.dependencies': () => _skill.dependencies,
  'CodexSkill.description': () => _skill.description,
  'CodexSkill.displayName': () => _skill.displayName,
  'CodexSkill.isEnabled': () => _skill.isEnabled,
  'CodexSkill.name': () => _skill.name,
  'CodexSkill.origin': () => _skill.origin,
  'CodexSkill.path': () => _skill.path,
  'CodexSkill.scope': () => _skill.scope,
  'CodexTurnProgress.new': () => _turnProgress,
  'CodexTurnProgress.commentary': () => _turnProgress.commentary,
  'CodexTurnProgress.hookActivities': () => _turnProgress.hookActivities,
  'CodexTurnProgress.isTruncated': () => _turnProgress.isTruncated,
  'CodexTurnProgress.planProgress': () => _turnProgress.planProgress,
  'CodexTurnProgress.plan': () => _turnProgress.plan,
  'CodexTurnProgress.reasoning': () => _turnProgress.reasoning,
  'CodexTurnProgress.shellExitCode': () => _turnProgress.shellExitCode,
  'CodexTurnProgress.shellOutput': () => _turnProgress.shellOutput,
  'CodexTurnProgress.text': () => _turnProgress.text,
  'CodexTurnProgress.workActivity': () => _turnProgress.workActivity,
  'CodexClientInfo.new': () => _clientInfo,
  'CodexClientInfo.name': () => _clientInfo.name,
  'CodexClientInfo.title': () => _clientInfo.title,
  'CodexClientInfo.version': () => _clientInfo.version,
  'CodexFailure.new': () => _failure,
  'CodexFailure.code': () => _failure.code,
  'CodexFailure.isRecoverable': () => _failure.isRecoverable,
  'CodexFailure.message': () => _failure.message,
  'CodexWorkspace.new': () => _workspace,
  'CodexWorkspace.displayName': () => _workspace.displayName,
  'CodexWorkspace.path': () => _workspace.path,
  'CodexConversationId.new': () => _conversationId,
  'CodexConversationId.value': () => _conversationId.value,
};

Directory _repositoryRoot() {
  var current = Directory.current.absolute;
  while (!File('${current.path}/settings.gradle.kts').existsSync()) {
    final parent = current.parent;
    if (parent.path == current.path) {
      throw StateError('repository root not found');
    }
    current = parent;
  }
  return current;
}

List<String> _evidenceList(String cell, String field, int lineNumber) {
  if (cell.isEmpty) throw FormatException('$field is empty', null, lineNumber);
  final values = cell.split(',');
  if (values.any((value) => value.isEmpty || value.trim() != value)) {
    throw FormatException('$field is malformed', null, lineNumber);
  }
  final sorted = values.toList()..sort();
  if (values.join(',') != sorted.join(',') ||
      values.toSet().length != values.length) {
    throw FormatException('$field must be sorted and unique', null, lineNumber);
  }
  return values;
}

List<_Claim> _readClaims() {
  final contents = File('parity/capability-claims.tsv').readAsStringSync();
  return _parseClaims(contents);
}

List<_Claim> _parseClaims(String contents) {
  if (!contents.endsWith('\n') || contents.contains('\r')) {
    throw const FormatException('capability claims must use canonical LF');
  }
  final lines = contents.substring(0, contents.length - 1).split('\n');
  if (lines.isEmpty || lines.first != _claimsHeader) {
    throw const FormatException('invalid capability claims header');
  }
  final claims = <_Claim>[];
  for (var index = 1; index < lines.length; index++) {
    final cells = lines[index].split('\t');
    if (cells.length != 5 ||
        cells.any(
          (cell) =>
              cell.isEmpty ||
              cell.trim() != cell ||
              cell.contains('*') ||
              cell.codeUnits.any((value) => value < 0x20),
        )) {
      throw FormatException(
          'claim row must contain five nonempty cells', null, index + 1);
    }
    final sharedScenarios =
        _evidenceList(cells[4], 'sharedScenarios', index + 1);
    if (sharedScenarios.any((value) => !_sharedScenarioIds.contains(value))) {
      throw FormatException(
        'sharedScenarios contains a non-contract scenario',
        null,
        index + 1,
      );
    }
    claims.add(
      _Claim(
        capabilityKey: cells[0],
        publicSymbols: _evidenceList(cells[1], 'publicSymbols', index + 1),
        executedTests: _evidenceList(cells[2], 'executedTests', index + 1),
        compilerEvidenceIds:
            _evidenceList(cells[3], 'compilerEvidenceIds', index + 1),
        sharedScenarios: sharedScenarios,
      ),
    );
  }
  final keys = claims.map((claim) => claim.capabilityKey).toList();
  final sortedKeys = keys.toList()..sort();
  if (keys.join('\n') != sortedKeys.join('\n') ||
      keys.toSet().length != keys.length) {
    throw const FormatException('capability keys must be sorted and unique');
  }
  for (final evidence in <List<String>>[
    claims.expand((claim) => claim.publicSymbols).toList(),
    claims.expand((claim) => claim.executedTests).toList(),
  ]) {
    if (evidence.toSet().length != evidence.length) {
      throw const FormatException('per-capability evidence IDs must be unique');
    }
  }
  return claims;
}

bool _sameSet(Set<String> left, Set<String> right) =>
    left.length == right.length && left.containsAll(right);

Set<String> _canonicalEnumCapabilities(Directory repositoryRoot) {
  final report = canonicalApiReport();
  final document =
      jsonDecode(report.readAsStringSync()) as Map<String, dynamic>;
  return {
    for (final owner in document['owners'] as List<dynamic>)
      for (final capability
          in (owner as Map<String, dynamic>)['capabilities'] as List<dynamic>)
        if ((capability as String).contains('|kind=enum-entry|')) capability,
  };
}

const _valueOwners = <String>{
  'AgentConnector',
  'AgentConversationSettings',
  'AgentConversationSummary',
  'AgentElicitationValidation',
  'AgentElicitationValidationIssue',
  'AgentFormOption',
  'AgentHookActivity',
  'AgentMcpEnvironmentVariable',
  'AgentMcpOauthConfiguration',
  'AgentMcpToolConfiguration',
  'AgentModel',
  'AgentPlanProgress',
  'AgentPlanStep',
  'AgentPluginCatalog',
  'AgentPluginDetail',
  'AgentPluginInstallResult',
  'AgentPluginReference',
  'AgentPluginSkill',
  'AgentPluginSummary',
  'AgentServiceTier',
  'AgentSkill',
  'AgentSkillCatalog',
  'AgentSkillChunk',
  'AgentTurnProgress',
  'CodexClientInfo',
  'CodexFailure',
  'CodexWorkspace',
  'ConversationId',
};

const _mcpOwners = <String>{
  'AgentMcpEnvironmentVariable',
  'AgentMcpOauthConfiguration',
  'AgentMcpServer',
  'AgentMcpServerConfiguration',
  'AgentMcpToolConfiguration',
  'AgentMcpTransport.Http',
  'AgentMcpTransport.Stdio',
};

const _mcpAdditionalOwnerPrefixes = <String>{
  'CodexMcpHttpTransport.',
  'CodexMcpServer.',
  'CodexMcpServerConfiguration.',
  'CodexMcpStdioTransport.',
};

String _capabilityOwner(String capability) =>
    capability.split('|owner=')[1].split('|')[0].split('/').last;

bool _isMcpAdditionalSymbol(String symbol) => _mcpAdditionalOwnerPrefixes.any(
      symbol.startsWith,
    );

Set<String> _canonicalValueCapabilities(Directory repositoryRoot) {
  final report = canonicalApiReport();
  final document =
      jsonDecode(report.readAsStringSync()) as Map<String, dynamic>;
  return {
    for (final owner in document['owners'] as List<dynamic>)
      for (final capability
          in (owner as Map<String, dynamic>)['capabilities'] as List<dynamic>)
        if (_valueOwners.contains(
          _capabilityOwner(capability as String),
        ))
          capability,
  };
}

Set<String> _canonicalMcpCapabilities(Directory repositoryRoot) {
  final report = canonicalApiReport();
  final document =
      jsonDecode(report.readAsStringSync()) as Map<String, dynamic>;
  return {
    for (final owner in document['owners'] as List<dynamic>)
      for (final capability
          in (owner as Map<String, dynamic>)['capabilities'] as List<dynamic>)
        if (_mcpOwners.contains(_capabilityOwner(capability as String)))
          capability,
  };
}

Map<String, dynamic> _bootstrap(Directory repositoryRoot) => jsonDecode(
      cAbiBootstrapEvidence().readAsStringSync(),
    ) as Map<String, dynamic>;

Set<String> _verifyValueClaims(
  List<_Claim> claims,
  Directory repositoryRoot,
) {
  if (claims.length != 142 ||
      !_sameSet(
        claims.map((claim) => claim.capabilityKey).toSet(),
        _canonicalValueCapabilities(repositoryRoot),
      ) ||
      !_sameSet(
        claims.expand((claim) => claim.publicSymbols).toSet(),
        _publicValueAccessors.keys
            .where((symbol) => !_isMcpAdditionalSymbol(symbol))
            .toSet(),
      )) {
    throw StateError(
        'Dart ordinary-value claims are incomplete, stale, or overclaimed');
  }

  final bootstrap = _bootstrap(repositoryRoot);
  final bootstrapClaims = <String, Map<String, dynamic>>{
    for (final claim in bootstrap['claims'] as List<dynamic>)
      (claim as Map<String, dynamic>)['capabilityKey'] as String: claim,
  };
  final passedNativeTests = <String>{
    for (final nativeTest in bootstrap['nativeTests'] as List<dynamic>)
      if ((nativeTest as Map<String, dynamic>)['status'] == 'passed')
        nativeTest['testId'] as String,
  };
  final header = cAbiHeader().readAsStringSync();
  final headerReferences = <String>{};

  for (var index = 0; index < claims.length; index++) {
    final claim = claims[index];
    final bootstrapClaim = bootstrapClaims[claim.capabilityKey];
    if (bootstrapClaim == null) {
      throw StateError('missing C ABI bootstrap claim');
    }
    final expectedHeaders =
        (bootstrapClaim['headerReferences'] as List<dynamic>)
            .cast<String>()
            .map((name) => 'c-header:$name')
            .toSet();
    final expectedNativeTests =
        (bootstrapClaim['nativeTestIds'] as List<dynamic>)
            .cast<String>()
            .map((testId) => 'cabi-fixture:$testId')
            .toSet();
    final expectedDart =
        'dart-analyzer-value:${index.toString().padLeft(3, '0')}';
    final evidence = claim.compilerEvidenceIds.toSet();
    if (!_sameSet(
      evidence,
      <String>{...expectedHeaders, ...expectedNativeTests, expectedDart},
    )) {
      throw StateError('inexact evidence for ${claim.capabilityKey}');
    }
    for (final reference in expectedHeaders) {
      final name = reference.substring('c-header:'.length);
      if (!RegExp('\\b${RegExp.escape(name)}\\s*\\(').hasMatch(header)) {
        throw StateError('stale C-header reference: $name');
      }
      headerReferences.add(name);
    }
    for (final reference in expectedNativeTests) {
      final testId = reference.substring('cabi-fixture:'.length);
      if (!passedNativeTests.contains(testId)) {
        throw StateError('stale or failed C ABI fixture: $testId');
      }
    }
  }
  return headerReferences;
}

Set<String> _verifyMcpClaims(
  List<_Claim> claims,
  Directory repositoryRoot,
) {
  final additional = claims
      .where((claim) => claim.executedTests.single.startsWith('dart.mcp:'))
      .toList();
  final expectedSymbols = _publicValueAccessors.keys
      .where((symbol) =>
          symbol.startsWith('CodexMcp') &&
          !symbol.startsWith('CodexMcpEnvironmentSource.') &&
          !symbol.startsWith('CodexMcpAuthStatus.') &&
          !symbol.startsWith('CodexMcpAuthentication.') &&
          !symbol.startsWith('CodexMcpToolApproval.') &&
          !symbol.startsWith('CodexMcpToolExposureSurface.'))
      .toSet();
  if (claims.length != 46 ||
      additional.length != 38 ||
      !_sameSet(
        claims.map((claim) => claim.capabilityKey).toSet(),
        _canonicalMcpCapabilities(repositoryRoot),
      ) ||
      !_sameSet(
        claims.expand((claim) => claim.publicSymbols).toSet(),
        expectedSymbols,
      )) {
    throw StateError('Dart MCP claims are incomplete, stale, or overclaimed');
  }

  final bootstrap = _bootstrap(repositoryRoot);
  final bootstrapClaims = <String, Map<String, dynamic>>{
    for (final claim in bootstrap['claims'] as List<dynamic>)
      (claim as Map<String, dynamic>)['capabilityKey'] as String: claim,
  };
  final passedNativeTests = <String>{
    for (final nativeTest in bootstrap['nativeTests'] as List<dynamic>)
      if ((nativeTest as Map<String, dynamic>)['status'] == 'passed')
        nativeTest['testId'] as String,
  };
  final header = cAbiHeader().readAsStringSync();
  final headerReferences = <String>{};
  final ordinaryCapabilityKeys =
      _canonicalValueCapabilities(repositoryRoot).toList()..sort();
  additional.sort(
    (left, right) => left.capabilityKey.compareTo(right.capabilityKey),
  );

  for (final claim in claims) {
    final bootstrapClaim = bootstrapClaims[claim.capabilityKey];
    if (bootstrapClaim == null) {
      throw StateError('missing C ABI bootstrap claim');
    }
    final expectedHeaders =
        (bootstrapClaim['headerReferences'] as List<dynamic>)
            .cast<String>()
            .map((name) => 'c-header:$name')
            .toSet();
    final expectedNativeTests =
        (bootstrapClaim['nativeTestIds'] as List<dynamic>)
            .cast<String>()
            .map((testId) => 'cabi-fixture:$testId')
            .toSet();
    final additionalIndex = additional.indexOf(claim);
    final ordinaryIndex = ordinaryCapabilityKeys.indexOf(claim.capabilityKey);
    final expectedDart = additionalIndex >= 0
        ? 'dart-analyzer-mcp:${additionalIndex.toString().padLeft(3, '0')}'
        : 'dart-analyzer-value:${ordinaryIndex.toString().padLeft(3, '0')}';
    if (ordinaryIndex < 0 && additionalIndex < 0) {
      throw StateError('MCP claim has no exact Dart evidence family');
    }
    if (!_sameSet(
      claim.compilerEvidenceIds.toSet(),
      <String>{...expectedHeaders, ...expectedNativeTests, expectedDart},
    )) {
      throw StateError('inexact MCP evidence for ${claim.capabilityKey}');
    }
    for (final reference in expectedHeaders) {
      final name = reference.substring('c-header:'.length);
      if (!RegExp('\\b${RegExp.escape(name)}\\s*\\(').hasMatch(header)) {
        throw StateError('stale C-header reference: $name');
      }
      headerReferences.add(name);
    }
    for (final reference in expectedNativeTests) {
      final testId = reference.substring('cabi-fixture:'.length);
      if (!passedNativeTests.contains(testId)) {
        throw StateError('stale or failed C ABI fixture: $testId');
      }
    }
  }
  return headerReferences;
}

Future<void> _compileValueHeaderReferences(
  Directory repositoryRoot,
  Set<String> references,
) async {
  final directory =
      Directory.systemTemp.createTempSync('codex_agent_dart_values_');
  try {
    final source = File('${directory.path}/value_references.c');
    final lines = references.toList()..sort();
    source.writeAsStringSync(
      '#include "codex_agent.h"\n'
      'void codex_agent_dart_value_references(void) {\n'
      '${lines.map((name) => '  (void)sizeof(&$name);').join('\n')}\n'
      '}\n',
    );
    final include = requiredCSdkInclude().path;
    final output = '${directory.path}/value_references.o';
    final result = Platform.isWindows
        ? await Process.run('cl', <String>[
            '/nologo',
            '/W4',
            '/WX',
            '/c',
            '/I$include',
            source.path,
            '/Fo$output',
          ])
        : await Process.run('cc', <String>[
            '-std=c11',
            '-Wall',
            '-Wextra',
            '-Werror',
            '-pedantic',
            '-I',
            include,
            '-c',
            source.path,
            '-o',
            output,
          ]);
    if (result.exitCode != 0) {
      throw StateError(
        'C-header value-reference compilation failed: '
        '${result.stdout}\n${result.stderr}',
      );
    }
  } finally {
    directory.deleteSync(recursive: true);
  }
}

void _validateClaims(List<_Claim> claims, Directory repositoryRoot) {
  final enumClaims = claims
      .where((claim) => claim.capabilityKey.contains('|kind=enum-entry|'))
      .toList();
  final capabilityKeys = enumClaims.map((claim) => claim.capabilityKey).toSet();
  final publicSymbols =
      enumClaims.expand((claim) => claim.publicSymbols).toSet();
  if (enumClaims.length != 110 ||
      !_sameSet(capabilityKeys, _canonicalEnumCapabilities(repositoryRoot)) ||
      !_sameSet(publicSymbols, _publicEnumValues.keys.toSet())) {
    throw StateError('Dart enum claims are incomplete, stale, or overclaimed');
  }
}

Future<String> _buildEnumFixture(Directory repositoryRoot) async {
  final source = File('test/native/enum_values.c').absolute.path;
  final include = requiredCSdkInclude().path;
  final output = File(
    '${Directory.systemTemp.path}/codex_agent_dart_enums_$pid'
    '${Platform.isWindows ? '.dll' : Platform.isMacOS ? '.dylib' : '.so'}',
  ).path;
  final result = Platform.isWindows
      ? await Process.run('cl', <String>[
          '/nologo',
          '/LD',
          '/I$include',
          source,
          '/link',
          '/OUT:$output',
        ])
      : await Process.run('cc', <String>[
          '-std=c11',
          '-Wall',
          '-Wextra',
          '-Werror',
          '-pedantic',
          ...(Platform.isMacOS
              ? const <String>['-dynamiclib']
              : const <String>['-shared', '-fPIC']),
          '-I',
          include,
          source,
          '-o',
          output,
        ]);
  if (result.exitCode != 0) {
    throw StateError(
      'enum fixture compilation failed: ${result.stdout}\n${result.stderr}',
    );
  }
  return output;
}

List<String> _nestedMarkers(String symbol, List<dynamic> values) =>
    switch (symbol) {
      'CodexElicitationValidation.issues' => values
          .cast<CodexElicitationValidationIssue>()
          .map((value) => value.fieldName)
          .toList(),
      'CodexModel.serviceTiers' =>
        values.cast<CodexServiceTier>().map((value) => value.id).toList(),
      'CodexPlanProgress.steps' =>
        values.cast<CodexPlanStep>().map((value) => value.text).toList(),
      'CodexPluginCatalog.plugins' => values
          .cast<CodexPluginSummary>()
          .map((value) => value.displayName)
          .toList(),
      'CodexPluginDetail.connectors' =>
        values.cast<CodexConnector>().map((value) => value.id).toList(),
      'CodexPluginDetail.skills' =>
        values.cast<CodexPluginSkill>().map((value) => value.name).toList(),
      'CodexPluginInstallResult.connectorsNeedingAuthentication' =>
        values.cast<CodexConnector>().map((value) => value.id).toList(),
      'CodexSkillCatalog.skills' =>
        values.cast<CodexSkill>().map((value) => value.name).toList(),
      'CodexTurnProgress.hookActivities' =>
        values.cast<CodexHookActivity>().map((value) => value.id).toList(),
      _ => throw StateError('unknown nested collection $symbol'),
    };

void _expectExactValue(String symbol, Object? value) {
  final member = symbol.substring(symbol.indexOf('.') + 1);
  if (member == 'new') {
    expect(value.runtimeType.toString(), symbol.split('.').first);
    return;
  }
  if (value is String) {
    expect(
      value,
      symbol == 'CodexPluginReference.uri'
          ? 'plugin://CodexPluginReference.name@CodexPluginReference.marketplaceName'
          : symbol,
    );
    return;
  }
  if (value is bool) {
    expect(value, symbol != 'CodexElicitationValidation.isValid');
    return;
  }
  if (value is int) {
    expect(value,
        symbol == 'CodexMcpOauthConfiguration.callbackPort' ? 65535 : 17);
    return;
  }
  final expectedEnum = <String, Object>{
    'CodexConversationSettings.approvalPreset': CodexApprovalPreset.strict,
    'CodexElicitationValidationIssue.reason':
        CodexElicitationValidationReason.invalidFormat,
    'CodexHookActivity.status': CodexHookRunStatus.completed,
    'CodexMcpEnvironmentVariable.source': CodexMcpEnvironmentSource.remote,
    'CodexMcpToolConfiguration.approval': CodexMcpToolApproval.prompt,
    'CodexPlanStep.status': CodexPlanStepStatus.completed,
    'CodexPluginCatalog.freshness': CodexCatalogFreshness.staleCache,
    'CodexPluginInstallResult.authPolicy': CodexPluginAuthPolicy.onUse,
    'CodexPluginSummary.authPolicy': CodexPluginAuthPolicy.onUse,
    'CodexPluginSummary.installPolicy':
        CodexPluginInstallPolicy.installedByDefault,
    'CodexSkill.origin': CodexResourceOrigin.plugin,
    'CodexSkill.scope': CodexSkillScope.plugin,
    'CodexTurnProgress.workActivity': CodexWorkActivity.writingFiles,
  }[symbol];
  if (expectedEnum != null) {
    expect(value, expectedEnum);
    return;
  }
  if (value is List<dynamic>) {
    expect(value, hasLength(2));
    expect(value.clear, throwsUnsupportedError);
    if (value.first is String) {
      expect(value, _pair(symbol));
    } else {
      expect(_nestedMarkers(symbol, value), _pair(symbol));
    }
    return;
  }
  final expectedNestedType = <String, String>{
    'CodexConversationSummary.conversationId': 'CodexConversationId',
    'CodexPluginDetail.summary': 'CodexPluginSummary',
    'CodexPluginSummary.reference': 'CodexPluginReference',
    'CodexTurnProgress.planProgress': 'CodexPlanProgress',
  }[symbol];
  if (expectedNestedType != null) {
    expect(value.runtimeType.toString(), expectedNestedType);
    return;
  }
  throw StateError(
      'unverified Dart value symbol $symbol (${value.runtimeType})');
}

List<String> _expectedScenarios(String capability) {
  final scenarios = <String>{'value-conversion'};
  if (capability.contains('?')) scenarios.add('nullability');
  if (capability.contains('kotlin.collections')) {
    scenarios.add('collection-immutability-ordering');
  }
  if (capability.contains('/CodexFailure|')) {
    scenarios.add('structured-failure');
  }
  return scenarios.toList()..sort();
}

void _registerOrdinaryValueParity(
  List<_Claim> claims,
  Directory repositoryRoot,
  Map<String, Set<String>> passedCompilerEvidence,
  Set<String> passedTestIds,
) {
  test('dart.value.inventory', () {
    expect(() => _verifyValueClaims(claims, repositoryRoot), returnsNormally);
  });

  test('dart.value.inventory rejects stale capability and evidence references',
      () {
    final first = claims.first;
    final staleCapability = <_Claim>[
      _Claim(
        capabilityKey: '${first.capabilityKey}.stale',
        publicSymbols: first.publicSymbols,
        executedTests: first.executedTests,
        compilerEvidenceIds: first.compilerEvidenceIds,
        sharedScenarios: first.sharedScenarios,
      ),
      ...claims.skip(1),
    ];
    expect(
      () => _verifyValueClaims(staleCapability, repositoryRoot),
      throwsStateError,
    );
    final staleEvidence = <_Claim>[
      _Claim(
        capabilityKey: first.capabilityKey,
        publicSymbols: first.publicSymbols,
        executedTests: first.executedTests,
        compilerEvidenceIds: <String>[
          ...first.compilerEvidenceIds
              .where((value) => !value.startsWith('c-header:')),
          'c-header:codex_agent_removed_stale_symbol',
        ]..sort(),
        sharedScenarios: first.sharedScenarios,
      ),
      ...claims.skip(1),
    ];
    expect(
      () => _verifyValueClaims(staleEvidence, repositoryRoot),
      throwsStateError,
    );
    final staleFixture = <_Claim>[
      _Claim(
        capabilityKey: first.capabilityKey,
        publicSymbols: first.publicSymbols,
        executedTests: first.executedTests,
        compilerEvidenceIds: <String>[
          ...first.compilerEvidenceIds
              .where((value) => !value.startsWith('cabi-fixture:')),
          'cabi-fixture:removed-stale-test',
        ]..sort(),
        sharedScenarios: first.sharedScenarios,
      ),
      ...claims.skip(1),
    ];
    expect(
      () => _verifyValueClaims(staleFixture, repositoryRoot),
      throwsStateError,
    );
  });

  test('dart.value nullability, defaults, and defensive copies are exact', () {
    final mutable = <String>['first', 'second'];
    final connector =
        CodexConnector(id: 'id', name: 'name', pluginNames: mutable);
    mutable
      ..[0] = 'changed'
      ..add('third');
    expect(connector.pluginNames, <String>['first', 'second']);
    expect(connector.installUrl, isNull);
    expect(CodexConversationSettings().serviceTier, isNull);
    expect(CodexPlanProgress().steps, isEmpty);
    expect(CodexMcpOauthConfiguration().callbackPort, isNull);
    expect(CodexMcpToolConfiguration().approval, isNull);
    expect(CodexTurnProgress().hookActivities, isEmpty);
    expect(CodexWorkspace(path: '/workspace').displayName, '/workspace');
    expect(
        () => CodexMcpOauthConfiguration(callbackPort: 0), throwsArgumentError);
    expect(() => CodexConversationId('  '), throwsArgumentError);
  });

  for (var index = 0; index < claims.length; index++) {
    final claim = claims[index];
    final testId = 'dart.value:${index.toString().padLeft(3, '0')}';
    test(testId, () {
      expect(claim.publicSymbols, hasLength(1));
      expect(claim.executedTests, <String>[testId]);
      expect(claim.sharedScenarios, _expectedScenarios(claim.capabilityKey));
      final symbol = claim.publicSymbols.single;
      final accessor = _publicValueAccessors[symbol];
      expect(accessor, isNotNull, reason: claim.capabilityKey);
      _expectExactValue(symbol, accessor!());
      for (final evidenceId in claim.compilerEvidenceIds) {
        passedCompilerEvidence
            .putIfAbsent(evidenceId, () => <String>{})
            .add(symbol);
      }
      passedTestIds.add(testId);
    });
  }
}

void _expectMcpValue(String symbol, Object? value) {
  final member = symbol.substring(symbol.indexOf('.') + 1);
  if (member == 'new') {
    expect(value.runtimeType.toString(), symbol.split('.').first);
    return;
  }
  if (value is String) {
    final expected = switch (symbol) {
      'CodexMcpHttpTransport.url' => 'https://example.test/mcp',
      'CodexMcpServerConfiguration.name' => 'mcp_server',
      'CodexMcpServerConfiguration.environmentId' => 'local',
      _ => symbol,
    };
    expect(value, expected);
    return;
  }
  if (value is bool) {
    expect(value, isTrue);
    return;
  }
  if (value is num) {
    expect(value, 17);
    return;
  }
  final expectedEnum = <String, Object>{
    'CodexMcpServer.authStatus': CodexMcpAuthStatus.oauth,
    'CodexMcpServer.origin': CodexResourceOrigin.plugin,
    'CodexMcpServerConfiguration.authentication': CodexMcpAuthentication.oauth,
    'CodexMcpServerConfiguration.defaultToolApproval':
        CodexMcpToolApproval.prompt,
  }[symbol];
  if (expectedEnum != null) {
    expect(value, expectedEnum);
    return;
  }
  if (value is List<dynamic>) {
    expect(value, hasLength(2));
    expect(value.clear, throwsUnsupportedError);
    return;
  }
  if (value is Map<dynamic, dynamic>) {
    expect(value, hasLength(2));
    expect(value.clear, throwsUnsupportedError);
    return;
  }
  final expectedNestedType = <String, String>{
    'CodexMcpServer.configuration': 'CodexMcpServerConfiguration',
    'CodexMcpServerConfiguration.oauth': 'CodexMcpOauthConfiguration',
    'CodexMcpServerConfiguration.transport': 'CodexMcpHttpTransport',
  }[symbol];
  if (expectedNestedType != null) {
    expect(value.runtimeType.toString(), expectedNestedType);
    return;
  }
  throw StateError('unverified Dart MCP symbol $symbol (${value.runtimeType})');
}

void _registerMcpValueParity(
  List<_Claim> allMcpClaims,
  List<_Claim> additionalClaims,
  Directory repositoryRoot,
  Map<String, Set<String>> passedCompilerEvidence,
  Set<String> passedTestIds,
) {
  test('dart.mcp.inventory', () {
    expect(
      () => _verifyMcpClaims(allMcpClaims, repositoryRoot),
      returnsNormally,
    );
  });

  test('dart.mcp.inventory rejects stale exact references', () {
    final first = additionalClaims.first;
    final stale = <_Claim>[
      for (final claim in allMcpClaims)
        if (identical(claim, first))
          _Claim(
            capabilityKey: claim.capabilityKey,
            publicSymbols: claim.publicSymbols,
            executedTests: claim.executedTests,
            compilerEvidenceIds: <String>[
              ...claim.compilerEvidenceIds
                  .where((value) => !value.startsWith('cabi-fixture:')),
              'cabi-fixture:removed-stale-mcp-test',
            ]..sort(),
            sharedScenarios: claim.sharedScenarios,
          )
        else
          claim,
    ];
    expect(() => _verifyMcpClaims(stale, repositoryRoot), throwsStateError);
  });

  test('dart.mcp nested graph and defensive copies are exact', () {
    final arguments = <String>['first', 'second'];
    final environment = <String, String>{'first': 'one', 'second': 'two'};
    final forwarded = <CodexMcpEnvironmentVariable>[
      CodexMcpEnvironmentVariable(name: 'first'),
      CodexMcpEnvironmentVariable(name: 'second'),
    ];
    final stdio = CodexMcpStdioTransport(
      command: 'command',
      arguments: arguments,
      environment: environment,
      forwardedEnvironment: forwarded,
    );
    arguments[0] = 'changed';
    environment['first'] = 'changed';
    forwarded.clear();
    expect(stdio.arguments, <String>['first', 'second']);
    expect(
        stdio.environment, <String, String>{'first': 'one', 'second': 'two'});
    expect(stdio.forwardedEnvironment.map((value) => value.name),
        <String>['first', 'second']);
    expect(stdio.arguments.clear, throwsUnsupportedError);
    expect(stdio.environment!.clear, throwsUnsupportedError);

    final configuration = _mcpServer.configuration!;
    expect(configuration.transport, same(_mcpHttp));
    expect(configuration.oauth, same(_mcpOauth));
    expect(configuration.tools['second'], same(_mcpTool));
    expect(configuration.enabledTools,
        _pair('CodexMcpServerConfiguration.enabledTools'));
    expect(configuration.enabledTools!.clear, throwsUnsupportedError);
    expect(configuration.tools.clear, throwsUnsupportedError);
    expect(_mcpServer.isAuthorized, isTrue);
    expect(
      const CodexMcpServer(
        name: 'plain',
        displayName: 'plain',
        authStatus: CodexMcpAuthStatus.notLoggedIn,
      ).isAuthorized,
      isFalse,
    );
    expect(
      () => CodexMcpHttpTransport(url: 'http://example.test'),
      throwsArgumentError,
    );
    expect(
      () => CodexMcpServerConfiguration(
        name: 'bad name',
        transport: stdio,
      ),
      throwsArgumentError,
    );
  });

  for (final claim in additionalClaims) {
    final testId = claim.executedTests.single;
    test(testId, () {
      expect(testId, startsWith('dart.mcp:'));
      expect(claim.publicSymbols, hasLength(1));
      expect(claim.sharedScenarios, _expectedScenarios(claim.capabilityKey));
      final symbol = claim.publicSymbols.single;
      final accessor = _publicValueAccessors[symbol];
      expect(accessor, isNotNull, reason: claim.capabilityKey);
      _expectMcpValue(symbol, accessor!());
      for (final evidenceId in claim.compilerEvidenceIds) {
        passedCompilerEvidence
            .putIfAbsent(evidenceId, () => <String>{})
            .add(symbol);
      }
      passedTestIds.add(testId);
    });
  }
}

void main() {
  final repositoryRoot = _repositoryRoot();
  final claims = _readClaims();
  final enumClaims = claims
      .where((claim) => claim.capabilityKey.contains('|kind=enum-entry|'))
      .toList();
  final valueClaims = claims
      .where((claim) =>
          _valueOwners.contains(_capabilityOwner(claim.capabilityKey)))
      .toList();
  final mcpClaims = claims
      .where(
          (claim) => _mcpOwners.contains(_capabilityOwner(claim.capabilityKey)))
      .toList();
  final additionalMcpClaims = mcpClaims
      .where((claim) => claim.executedTests.single.startsWith('dart.mcp:'))
      .toList();
  final residualClaims = claims
      .where((claim) => claim.executedTests.single.startsWith('dart.residual:'))
      .map(
        (claim) => DartResidualClaim(
          capabilityKey: claim.capabilityKey,
          publicSymbols: claim.publicSymbols,
          executedTests: claim.executedTests,
          compilerEvidenceIds: claim.compilerEvidenceIds,
          sharedScenarios: claim.sharedScenarios,
        ),
      )
      .toList();
  final functionClaims = claims
      .where((claim) => claim.executedTests.single.startsWith('dart.function:'))
      .map(
        (claim) => DartFunctionClaim(
          capabilityKey: claim.capabilityKey,
          publicSymbols: claim.publicSymbols,
          executedTests: claim.executedTests,
          compilerEvidenceIds: claim.compilerEvidenceIds,
          sharedScenarios: claim.sharedScenarios,
        ),
      )
      .toList();
  final leafClaims = claims
      .where((claim) => claim.executedTests.single.startsWith('dart.leaf:'))
      .map(
        (claim) => DartLeafClaim(
          capabilityKey: claim.capabilityKey,
          publicSymbols: claim.publicSymbols,
          executedTests: claim.executedTests,
          compilerEvidenceIds: claim.compilerEvidenceIds,
          sharedScenarios: claim.sharedScenarios,
        ),
      )
      .toList();
  final conversationClaims = claims
      .where((claim) =>
          claim.executedTests.single.startsWith('dart.conversation:'))
      .map(
        (claim) => DartConversationClaim(
          capabilityKey: claim.capabilityKey,
          publicSymbols: claim.publicSymbols,
          executedTests: claim.executedTests,
          compilerEvidenceIds: claim.compilerEvidenceIds,
          sharedScenarios: claim.sharedScenarios,
        ),
      )
      .toList();
  final agentClaims = claims
      .where((claim) => claim.executedTests.single.startsWith('dart.agent:'))
      .map(
        (claim) => DartAgentClaim(
          capabilityKey: claim.capabilityKey,
          publicSymbols: claim.publicSymbols,
          executedTests: claim.executedTests,
          compilerEvidenceIds: claim.compilerEvidenceIds,
          sharedScenarios: claim.sharedScenarios,
        ),
      )
      .toList();
  final hostClaims = claims
      .where((claim) => claim.executedTests.single.startsWith('dart.host:'))
      .map(
        (claim) => DartHostClaim(
          capabilityKey: claim.capabilityKey,
          publicSymbols: claim.publicSymbols,
          executedTests: claim.executedTests,
          compilerEvidenceIds: claim.compilerEvidenceIds,
          sharedScenarios: claim.sharedScenarios,
        ),
      )
      .toList();
  final priorCapabilities = claims
      .where(
          (claim) => !claim.executedTests.single.startsWith('dart.residual:'))
      .map((claim) => claim.capabilityKey)
      .toSet();
  final passedCompilerEvidence = <String, Set<String>>{};
  final passedTestIds = <String>{};
  late String libraryPath;
  late DynamicLibrary library;
  late _EnumValueDart nativeEnumValue;

  setUpAll(() async {
    final headerReferences = <String>{
      ..._verifyValueClaims(valueClaims, repositoryRoot),
      ..._verifyMcpClaims(mcpClaims, repositoryRoot),
    };
    await _compileValueHeaderReferences(repositoryRoot, headerReferences);
    final residualHeaderReferences = verifyResidualClaims(
      residualClaims,
      repositoryRoot,
      priorCapabilities,
    );
    await compileResidualHeaderReferences(
      repositoryRoot,
      residualHeaderReferences,
    );
    final functionHeaderReferences = verifyFunctionClaims(
      functionClaims,
      repositoryRoot,
    );
    await compileResidualHeaderReferences(
      repositoryRoot,
      functionHeaderReferences,
    );
    final leafHeaderReferences = verifyLeafClaims(
      leafClaims,
      repositoryRoot,
    );
    await verifyRealLeafBoundary(leafClaims, repositoryRoot);
    await compileResidualHeaderReferences(
      repositoryRoot,
      leafHeaderReferences,
    );
    final conversationHeaderReferences = verifyConversationClaims(
      conversationClaims,
      repositoryRoot,
    );
    await verifyRealConversationBoundary(conversationClaims, repositoryRoot);
    await compileResidualHeaderReferences(
      repositoryRoot,
      conversationHeaderReferences,
    );
    final agentHeaderReferences = verifyAgentClaims(
      agentClaims,
      repositoryRoot,
    );
    await verifyRealAgentBoundary(agentClaims, repositoryRoot);
    await compileResidualHeaderReferences(
      repositoryRoot,
      agentHeaderReferences,
    );
    final hostHeaderReferences = verifyHostClaims(
      hostClaims,
      repositoryRoot,
    );
    await verifyRealHostBoundary(hostClaims, repositoryRoot);
    await compileResidualHeaderReferences(
      repositoryRoot,
      hostHeaderReferences,
    );
    libraryPath = await _buildEnumFixture(repositoryRoot);
    library = DynamicLibrary.open(libraryPath);
    nativeEnumValue = library.lookupFunction<_EnumValueNative, _EnumValueDart>(
      'codex_agent_dart_enum_value',
    );
  });

  tearDownAll(() {
    final fixture = File(libraryPath);
    if (fixture.existsSync()) fixture.deleteSync();
    final expectedCompilerEvidence =
        claims.expand((claim) => claim.compilerEvidenceIds).toSet();
    final expectedTests = claims.expand((claim) => claim.executedTests).toSet();
    expect(passedCompilerEvidence.keys.toSet(), expectedCompilerEvidence);
    expect(passedTestIds, expectedTests);

    final output = Directory('build/parity')..createSync(recursive: true);
    final compilerIds = passedCompilerEvidence.keys.toList()..sort();
    File('${output.path}/compiler-evidence.tsv').writeAsStringSync(
      'compilerEvidenceId\tpublicSymbols\n'
      '${compilerIds.map((id) {
        final symbols = passedCompilerEvidence[id]!.toList()..sort();
        return '$id\t${symbols.join(',')}';
      }).join('\n')}\n',
    );
    final testIds = passedTestIds.toList()..sort();
    File('${output.path}/executed-tests.tsv').writeAsStringSync(
      'executedTestId\tstatus\n'
      '${testIds.map((id) => '$id\tpassed').join('\n')}\n',
    );
  });

  test('dart.enum.inventory', () => _validateClaims(claims, repositoryRoot));

  test('dart.enum.inventory rejects malformed, duplicate, and stale rows', () {
    final contents = File('parity/capability-claims.tsv').readAsStringSync();
    expect(
      () => _parseClaims(contents.replaceFirst(_claimsHeader, 'bad header')),
      throwsFormatException,
    );
    final firstRow = contents.split('\n')[1];
    expect(
      () => _parseClaims(
          contents.replaceFirst('$firstRow\n', '$firstRow\n$firstRow\n')),
      throwsFormatException,
    );
    expect(
      () => _parseClaims(
        contents.replaceFirst('\tvalue-conversion\n', '\tremote-execution\n'),
      ),
      throwsFormatException,
    );
    final first = claims.first;
    final stale = <_Claim>[
      _Claim(
        capabilityKey: '${first.capabilityKey}.stale',
        publicSymbols: first.publicSymbols,
        executedTests: first.executedTests,
        compilerEvidenceIds: first.compilerEvidenceIds,
        sharedScenarios: first.sharedScenarios,
      ),
      ...claims.skip(1),
    ];
    expect(() => _validateClaims(stale, repositoryRoot), throwsStateError);
  });

  for (var index = 0; index < enumClaims.length; index++) {
    final claim = enumClaims[index];
    final testId = 'dart.enum:${index.toString().padLeft(3, '0')}';
    test(testId, () {
      expect(claim.publicSymbols, hasLength(1));
      expect(claim.executedTests, <String>[testId]);
      expect(claim.compilerEvidenceIds, <String>['c-header-enum:$index']);
      expect(claim.sharedScenarios, <String>['value-conversion']);
      expect(
        _publicEnumValues[claim.publicSymbols.single],
        nativeEnumValue(index),
        reason: claim.capabilityKey,
      );
      passedCompilerEvidence
          .putIfAbsent(claim.compilerEvidenceIds.single, () => <String>{})
          .add(claim.publicSymbols.single);
      passedTestIds.add(testId);
      // Keep the library alive through the native call on every capability.
      expect(library, isA<DynamicLibrary>());
    });
  }

  _registerOrdinaryValueParity(
    valueClaims,
    repositoryRoot,
    passedCompilerEvidence,
    passedTestIds,
  );
  _registerMcpValueParity(
    mcpClaims,
    additionalMcpClaims,
    repositoryRoot,
    passedCompilerEvidence,
    passedTestIds,
  );
  registerResidualParity(
    residualClaims,
    repositoryRoot,
    priorCapabilities,
    passedCompilerEvidence,
    passedTestIds,
  );
  registerSynchronousValueFunctionParity(
    functionClaims,
    repositoryRoot,
    passedCompilerEvidence,
    passedTestIds,
  );
  registerLeafServiceParity(
    leafClaims,
    repositoryRoot,
    passedCompilerEvidence,
    passedTestIds,
  );
  registerConversationParity(
    conversationClaims,
    repositoryRoot,
    passedCompilerEvidence,
    passedTestIds,
  );
  registerAgentParity(
    agentClaims,
    repositoryRoot,
    passedCompilerEvidence,
    passedTestIds,
  );
  registerHostParity(
    hostClaims,
    repositoryRoot,
    passedCompilerEvidence,
    passedTestIds,
  );
}
