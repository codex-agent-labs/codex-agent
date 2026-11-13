import 'dart:async';

import 'errors.dart';

String _nonBlank(String value, String name) {
  if (value.trim().isEmpty ||
      value.codeUnits.any((unit) => unit < 0x20 || unit == 0x7f)) {
    throw ArgumentError.value(
        value, name, 'must be nonblank and contain no control characters');
  }
  return value;
}

List<T> _immutable<T>(Iterable<T> values) => List<T>.unmodifiable(values);

List<T>? _nullableImmutable<T>(Iterable<T>? values) =>
    values == null ? null : _immutable(values);

Map<K, V> _immutableMap<K, V>(Map<K, V> values) =>
    Map<K, V>.unmodifiable(values);

/// A state projection with an explicit current-value read and broadcast changes.
final class CodexObservableState<T> {
  CodexObservableState({
    required Future<T> Function() current,
    required Stream<T> Function() changes,
  })  : _current = current,
        _changes = changes;

  final Future<T> Function() _current;
  final Stream<T> Function() _changes;

  Future<T> get current => _current();
  Stream<T> get changes => _changes();
}

final class CodexClientInfo {
  CodexClientInfo({
    required String name,
    required String title,
    required String version,
  })  : name = _nonBlank(name, 'name'),
        title = _nonBlank(title, 'title'),
        version = _nonBlank(version, 'version');

  final String name;
  final String title;
  final String version;
}

/// A decision for an approval request.
enum CodexApprovalDecision {
  accept(0),
  decline(1);

  const CodexApprovalDecision(this.value);
  final int value;
}

/// The agent authentication state.
enum CodexAuthenticationStatus {
  signedOut(0),
  authenticating(1),
  authenticated(2);

  const CodexAuthenticationStatus(this.value);
  final int value;
}

/// A capability available to an agent.
enum CodexCapability {
  webSearch(0);

  const CodexCapability(this.value);
  final int value;
}

/// The freshness of catalog data.
enum CodexCatalogFreshness {
  live(0),
  freshCache(1),
  staleCache(2);

  const CodexCatalogFreshness(this.value);
  final int value;
}

/// The collaboration mode for a conversation.
enum CodexCollaborationMode {
  defaultMode(0),
  plan(1);

  const CodexCollaborationMode(this.value);
  final int value;
}

enum CodexHostStateKind {
  newHost(0),
  restoring(1),
  workspaceRequired(2),
  preparing(3),
  ready(4),
  failed(5),
  closed(6);

  const CodexHostStateKind(this.value);
  final int value;

  static CodexHostStateKind fromValue(int value) => values.firstWhere(
        (candidate) => candidate.value == value,
        orElse: () => throw CodexNativeException(value, 'unknown host state'),
      );
}

enum CodexWorkspaceSelectionReason {
  notSelected(0),
  notFound(1),
  accessRevoked(2),
  invalidSelection(3);

  const CodexWorkspaceSelectionReason(this.value);
  final int value;

  static CodexWorkspaceSelectionReason fromValue(int value) =>
      values.firstWhere(
        (candidate) => candidate.value == value,
        orElse: () => throw CodexNativeException(
          value,
          'unknown workspace selection reason',
        ),
      );
}

enum CodexConversationStatus {
  newConversation(0),
  opening(1),
  ready(2),
  startingTurn(3),
  runningTurn(4),
  cancellingTurn(5),
  reloading(6),
  failed(7),
  closed(8);

  const CodexConversationStatus(this.value);
  final int value;

  static CodexConversationStatus fromValue(int value) => values.firstWhere(
        (candidate) => candidate.value == value,
        orElse: () => throw CodexNativeException(
          value,
          'unknown conversation status',
        ),
      );
}

enum CodexApprovalPreset {
  never(0),
  autoReview(1),
  askMe(2),
  strict(3);

  const CodexApprovalPreset(this.value);
  final int value;
}

/// The action taken for an elicitation request.
enum CodexElicitationAction {
  accept(0),
  decline(1),
  cancel(2);

  const CodexElicitationAction(this.value);
  final int value;
}

/// The reason elicitation input is invalid.
enum CodexElicitationValidationReason {
  missingRequired(0),
  unknownField(1),
  invalidType(2),
  nonFiniteNumber(3),
  belowMinimum(4),
  aboveMaximum(5),
  nonInteger(6),
  invalidFormat(7),
  invalidSelection(8),
  duplicateSelection(9);

  const CodexElicitationValidationReason(this.value);
  final int value;
}

/// The data type of a form field.
enum CodexFormFieldType {
  string(0),
  number(1),
  integer(2),
  boolean(3),
  singleSelect(4),
  multiSelect(5);

  const CodexFormFieldType(this.value);
  final int value;
}

/// The expected format of a string form field.
enum CodexFormStringFormat {
  email(0),
  uri(1),
  date(2),
  dateTime(3);

  const CodexFormStringFormat(this.value);
  final int value;
}

/// The execution state of a hook run.
enum CodexHookRunStatus {
  running(0),
  completed(1),
  failed(2),
  blocked(3),
  stopped(4);

  const CodexHookRunStatus(this.value);
  final int value;
}

/// The trust state of a hook.
enum CodexHookTrustStatus {
  managed(0),
  untrusted(1),
  trusted(2),
  modified(3);

  const CodexHookTrustStatus(this.value);
  final int value;
}

/// The installation scope of a resource.
enum CodexInstallationScope {
  user(0),
  workspace(1);

  const CodexInstallationScope(this.value);
  final int value;
}

/// The state of integration authorization.
enum CodexIntegrationAuthorizationStatus {
  idle(0),
  starting(1),
  awaitingCompletion(2),
  authorized(3),
  failed(4);

  const CodexIntegrationAuthorizationStatus(this.value);
  final int value;
}

/// The authentication state of an MCP server.
enum CodexMcpAuthStatus {
  unknown(0),
  unsupported(1),
  notLoggedIn(2),
  bearerToken(3),
  oauth(4);

  const CodexMcpAuthStatus(this.value);
  final int value;
}

/// The authentication mechanism of an MCP server.
enum CodexMcpAuthentication {
  oauth(0),
  chatGpt(1);

  const CodexMcpAuthentication(this.value);
  final int value;
}

/// The source of an MCP environment value.
enum CodexMcpEnvironmentSource {
  local(0),
  remote(1);

  const CodexMcpEnvironmentSource(this.value);
  final int value;
}

/// The approval policy for an MCP tool.
enum CodexMcpToolApproval {
  auto(0),
  prompt(1),
  writes(2),
  approve(3);

  const CodexMcpToolApproval(this.value);
  final int value;
}

/// A surface on which an MCP tool is exposed.
enum CodexMcpToolExposureSurface {
  codeMode(0),
  deferred(1),
  direct(2);

  const CodexMcpToolExposureSurface(this.value);
  final int value;
}

/// The author of a message.
enum CodexMessageRole {
  user(0),
  assistant(1);

  const CodexMessageRole(this.value);
  final int value;
}

/// The state of a plan step.
enum CodexPlanStepStatus {
  pending(0),
  inProgress(1),
  completed(2);

  const CodexPlanStepStatus(this.value);
  final int value;
}

/// When a plugin requests authentication.
enum CodexPluginAuthPolicy {
  onInstall(0),
  onUse(1);

  const CodexPluginAuthPolicy(this.value);
  final int value;
}

/// The installation policy for a plugin.
enum CodexPluginInstallPolicy {
  notAvailable(0),
  available(1),
  installedByDefault(2);

  const CodexPluginInstallPolicy(this.value);
  final int value;
}

/// How a value was resolved.
enum CodexResolution {
  preferred(0),
  defaultResolution(1),
  first(2);

  const CodexResolution(this.value);
  final int value;
}

/// The origin of a resource.
enum CodexResourceOrigin {
  user(0),
  workspace(1),
  plugin(2),
  managed(3),
  unknown(4);

  const CodexResourceOrigin(this.value);
  final int value;
}

/// The scope of a skill.
enum CodexSkillScope {
  system(0),
  user(1),
  repo(2),
  plugin(3),
  admin(4);

  const CodexSkillScope(this.value);
  final int value;
}

/// The agent's current work activity.
enum CodexWorkActivity {
  runningCommand(0),
  writingFiles(1);

  const CodexWorkActivity(this.value);
  final int value;
}

/// The purpose of an authorization request.
enum CodexAuthorizationPurpose {
  chatGpt(0),
  external(1);

  const CodexAuthorizationPurpose(this.value);
  final int value;
}

final class CodexConversationId {
  CodexConversationId(String value) : value = _nonBlank(value, 'value');
  final String value;
}

final class CodexConversationSettings {
  const CodexConversationSettings({
    this.approvalPreset = CodexApprovalPreset.autoReview,
    this.serviceTier,
  });

  final CodexApprovalPreset approvalPreset;
  final String? serviceTier;
}

final class CodexElicitationValidationIssue {
  const CodexElicitationValidationIssue({
    required this.fieldName,
    required this.reason,
  });

  final String fieldName;
  final CodexElicitationValidationReason reason;
}

final class CodexElicitationValidation {
  CodexElicitationValidation(
      {required Iterable<CodexElicitationValidationIssue> issues})
      : issues = _immutable(issues);

  final List<CodexElicitationValidationIssue> issues;
  bool get isValid => issues.isEmpty;
}

final class CodexFormOption {
  CodexFormOption({required this.value, String? title, this.description})
      : title = title ?? value;

  final String value;
  final String title;
  final String? description;
}

final class CodexMcpEnvironmentVariable {
  CodexMcpEnvironmentVariable({required String name, this.source})
      : name = _nonBlank(name, 'name');

  final String name;
  final CodexMcpEnvironmentSource? source;
}

final class CodexMcpOauthConfiguration {
  CodexMcpOauthConfiguration({this.clientId, this.callbackPort}) {
    final port = callbackPort;
    if (port != null && (port < 1 || port > 65535)) {
      throw ArgumentError.value(
          port, 'callbackPort', 'must be between 1 and 65535');
    }
  }

  final String? clientId;
  final int? callbackPort;
}

final class CodexMcpToolConfiguration {
  const CodexMcpToolConfiguration({this.approval});
  final CodexMcpToolApproval? approval;
}

sealed class CodexMcpTransport {
  const CodexMcpTransport();
}

/// An HTTP MCP transport.
final class CodexMcpHttpTransport extends CodexMcpTransport {
  CodexMcpHttpTransport({
    required String url,
    this.bearerTokenEnvironmentVariable,
    Map<String, String>? headers,
    Map<String, String>? environmentHeaders,
    this.headersHelper,
  })  : url = _safeMcpHttpUrl(url),
        headers = headers == null ? null : _immutableMap(headers),
        environmentHeaders = environmentHeaders == null
            ? null
            : _immutableMap(environmentHeaders) {
    final bearer = bearerTokenEnvironmentVariable;
    if (bearer != null) _nonBlank(bearer, 'bearerTokenEnvironmentVariable');
    final helper = headersHelper;
    if (helper != null) _nonBlank(helper, 'headersHelper');
  }

  final String url;
  final String? bearerTokenEnvironmentVariable;
  final Map<String, String>? headers;
  final Map<String, String>? environmentHeaders;
  final String? headersHelper;
}

/// A subprocess MCP transport.
final class CodexMcpStdioTransport extends CodexMcpTransport {
  CodexMcpStdioTransport({
    required String command,
    Iterable<String> arguments = const <String>[],
    this.workingDirectory,
    Map<String, String>? environment,
    Iterable<CodexMcpEnvironmentVariable> forwardedEnvironment =
        const <CodexMcpEnvironmentVariable>[],
  })  : command = _nonBlank(command, 'command'),
        arguments = _immutable(arguments),
        environment = environment == null ? null : _immutableMap(environment),
        forwardedEnvironment = _immutable(forwardedEnvironment);

  final String command;
  final List<String> arguments;
  final String? workingDirectory;
  final Map<String, String>? environment;
  final List<CodexMcpEnvironmentVariable> forwardedEnvironment;
}

/// The complete immutable configuration of an MCP server.
final class CodexMcpServerConfiguration {
  CodexMcpServerConfiguration({
    required String name,
    required this.transport,
    this.authentication,
    String environmentId = 'local',
    this.isEnabled = true,
    this.isRequired = false,
    this.supportsParallelToolCalls = false,
    Iterable<CodexMcpToolExposureSurface>? omitToolsFrom,
    this.startupTimeoutSeconds,
    this.toolTimeoutSeconds,
    this.defaultToolApproval,
    Iterable<String>? enabledTools,
    Iterable<String>? disabledTools,
    Iterable<String>? scopes,
    this.oauth,
    this.oauthResource,
    Map<String, CodexMcpToolConfiguration> tools =
        const <String, CodexMcpToolConfiguration>{},
  })  : name = _mcpServerName(name),
        environmentId = _nonBlank(environmentId, 'environmentId'),
        omitToolsFrom = _nullableImmutable(omitToolsFrom),
        enabledTools = _nullableImmutable(enabledTools),
        disabledTools = _nullableImmutable(disabledTools),
        scopes = _nullableImmutable(scopes),
        tools = _immutableMap(tools) {
    _mcpTimeout(startupTimeoutSeconds, 'startupTimeoutSeconds');
    _mcpTimeout(toolTimeoutSeconds, 'toolTimeoutSeconds');
    if (transport is CodexMcpStdioTransport &&
        (authentication != null || oauth != null || oauthResource != null)) {
      throw ArgumentError(
          'stdio transports do not support authentication or OAuth');
    }
    if (transport case CodexMcpHttpTransport(headersHelper: final String _)
        when environmentId != 'local') {
      throw ArgumentError.value(environmentId, 'environmentId',
          'headers helpers are supported only for local servers');
    }
  }

  final String name;
  final CodexMcpTransport transport;
  final CodexMcpAuthentication? authentication;
  final String environmentId;
  final bool isEnabled;
  final bool isRequired;
  final bool supportsParallelToolCalls;
  final List<CodexMcpToolExposureSurface>? omitToolsFrom;
  final double? startupTimeoutSeconds;
  final double? toolTimeoutSeconds;
  final CodexMcpToolApproval? defaultToolApproval;
  final List<String>? enabledTools;
  final List<String>? disabledTools;
  final List<String>? scopes;
  final CodexMcpOauthConfiguration? oauth;
  final String? oauthResource;
  final Map<String, CodexMcpToolConfiguration> tools;
}

/// An installed or discoverable MCP server.
final class CodexMcpServer {
  const CodexMcpServer({
    required this.name,
    required this.displayName,
    required this.authStatus,
    this.configuration,
    this.origin = CodexResourceOrigin.unknown,
    this.canRemove = false,
  });

  final String name;
  final String displayName;
  final CodexMcpAuthStatus authStatus;
  final CodexMcpServerConfiguration? configuration;
  final CodexResourceOrigin origin;
  final bool canRemove;
  bool get isAuthorized =>
      authStatus == CodexMcpAuthStatus.bearerToken ||
      authStatus == CodexMcpAuthStatus.oauth;
}

String _safeMcpHttpUrl(String value) {
  if (value.isEmpty ||
      value.codeUnits.any((unit) => unit <= 0x20 || unit == 0x7f)) {
    throw ArgumentError.value(value, 'url', 'must be a safe HTTP URL');
  }
  final uri = Uri.tryParse(value);
  if (uri == null ||
      !uri.hasAuthority ||
      uri.host.isEmpty ||
      uri.userInfo.isNotEmpty ||
      (uri.hasPort && (uri.port < 1 || uri.port > 65535))) {
    throw ArgumentError.value(value, 'url', 'must be a safe HTTP URL');
  }
  final loopback =
      uri.host == 'localhost' || uri.host == '127.0.0.1' || uri.host == '::1';
  if (uri.scheme != 'https' && !(uri.scheme == 'http' && loopback)) {
    throw ArgumentError.value(value, 'url', 'must use HTTPS or loopback HTTP');
  }
  return value;
}

String _mcpServerName(String value) {
  if (value.isEmpty ||
      value.codeUnits.any((unit) =>
          !(unit >= 0x30 && unit <= 0x39) &&
          !(unit >= 0x41 && unit <= 0x5a) &&
          !(unit >= 0x61 && unit <= 0x7a) &&
          unit != 0x2d &&
          unit != 0x5f)) {
    throw ArgumentError.value(
        value, 'name', "may contain only ASCII letters, numbers, '-', and '_'");
  }
  return value;
}

void _mcpTimeout(double? value, String name) {
  if (value != null &&
      (!value.isFinite || value <= 0 || value >= 18446744073709551616.0)) {
    throw ArgumentError.value(
        value, name, 'must be finite, positive, and <2^64');
  }
}

final class CodexPlanStep {
  const CodexPlanStep({required this.text, required this.status});
  final String text;
  final CodexPlanStepStatus status;
}

final class CodexPlanProgress {
  CodexPlanProgress(
      {this.explanation, Iterable<CodexPlanStep> steps = const []})
      : steps = _immutable(steps);

  final String? explanation;
  final List<CodexPlanStep> steps;
}

final class CodexServiceTier {
  const CodexServiceTier({
    required this.id,
    required this.name,
    required this.description,
  });

  final String id;
  final String name;
  final String description;
}

final class CodexModel {
  CodexModel({
    required this.id,
    required this.displayName,
    required this.description,
    required Iterable<String> supportedEfforts,
    required this.defaultEffort,
    required this.isDefault,
    Iterable<CodexServiceTier> serviceTiers = const [],
    this.defaultServiceTier,
  })  : supportedEfforts = _immutable(supportedEfforts),
        serviceTiers = _immutable(serviceTiers);

  final String id;
  final String displayName;
  final String description;
  final List<String> supportedEfforts;
  final String defaultEffort;
  final bool isDefault;
  final List<CodexServiceTier> serviceTiers;
  final String? defaultServiceTier;
}

final class CodexConnector {
  CodexConnector({
    required this.id,
    required this.name,
    this.description = '',
    this.installUrl,
    this.isAccessible = false,
    this.isEnabled = true,
    Iterable<String> pluginNames = const [],
  }) : pluginNames = _immutable(pluginNames);

  final String id;
  final String name;
  final String description;
  final String? installUrl;
  final bool isAccessible;
  final bool isEnabled;
  final List<String> pluginNames;
}

final class CodexPluginReference {
  const CodexPluginReference({
    required this.id,
    required this.name,
    required this.marketplaceName,
    this.marketplacePath,
    this.remotePluginId,
  });

  final String id;
  final String name;
  final String marketplaceName;
  final String? marketplacePath;
  final String? remotePluginId;
  String get uri => 'plugin://$name@$marketplaceName';
}

final class CodexPluginSkill {
  const CodexPluginSkill({
    required this.name,
    required this.description,
    required this.isEnabled,
    this.path,
  });

  final String name;
  final String description;
  final bool isEnabled;
  final String? path;
}

final class CodexPluginSummary {
  CodexPluginSummary({
    required this.reference,
    required this.displayName,
    required this.description,
    required this.isInstalled,
    required this.isEnabled,
    required this.installPolicy,
    required this.authPolicy,
    required this.isAvailable,
    Iterable<String> capabilities = const [],
    this.brandColor,
    this.privacyPolicyUrl,
    this.termsOfServiceUrl,
    this.websiteUrl,
  }) : capabilities = _immutable(capabilities);

  final CodexPluginReference reference;
  final String displayName;
  final String description;
  final bool isInstalled;
  final bool isEnabled;
  final CodexPluginInstallPolicy installPolicy;
  final CodexPluginAuthPolicy authPolicy;
  final bool isAvailable;
  final List<String> capabilities;
  final String? brandColor;
  final String? privacyPolicyUrl;
  final String? termsOfServiceUrl;
  final String? websiteUrl;
}

final class CodexPluginCatalog {
  CodexPluginCatalog({
    required Iterable<CodexPluginSummary> plugins,
    Iterable<String> errors = const [],
    this.freshness = CodexCatalogFreshness.live,
  })  : plugins = _immutable(plugins),
        errors = _immutable(errors);

  final List<CodexPluginSummary> plugins;
  final List<String> errors;
  final CodexCatalogFreshness freshness;
}

final class CodexPluginDetail {
  CodexPluginDetail({
    required this.summary,
    required this.description,
    required Iterable<CodexPluginSkill> skills,
    required Iterable<CodexConnector> connectors,
    required Iterable<String> mcpServers,
    required this.hookCount,
  })  : skills = _immutable(skills),
        connectors = _immutable(connectors),
        mcpServers = _immutable(mcpServers);

  final CodexPluginSummary summary;
  final String description;
  final List<CodexPluginSkill> skills;
  final List<CodexConnector> connectors;
  final List<String> mcpServers;
  final int hookCount;
}

final class CodexPluginInstallResult {
  CodexPluginInstallResult({
    required this.authPolicy,
    required Iterable<CodexConnector> connectorsNeedingAuthentication,
    this.message,
  }) : connectorsNeedingAuthentication =
            _immutable(connectorsNeedingAuthentication);

  final CodexPluginAuthPolicy authPolicy;
  final List<CodexConnector> connectorsNeedingAuthentication;
  final String? message;
}

final class CodexSkill {
  CodexSkill({
    required this.name,
    required this.displayName,
    required this.description,
    required this.path,
    required this.scope,
    required this.isEnabled,
    this.brandColor,
    Iterable<String> dependencies = const [],
    this.canUninstall = false,
    CodexResourceOrigin? origin,
  })  : dependencies = _immutable(dependencies),
        origin = origin ?? _originFor(scope);

  final String name;
  final String displayName;
  final String description;
  final String path;
  final CodexSkillScope scope;
  final bool isEnabled;
  final String? brandColor;
  final List<String> dependencies;
  final bool canUninstall;
  final CodexResourceOrigin origin;

  static CodexResourceOrigin _originFor(CodexSkillScope scope) =>
      switch (scope) {
        CodexSkillScope.user => CodexResourceOrigin.user,
        CodexSkillScope.repo => CodexResourceOrigin.workspace,
        CodexSkillScope.plugin => CodexResourceOrigin.plugin,
        CodexSkillScope.system ||
        CodexSkillScope.admin =>
          CodexResourceOrigin.managed,
      };
}

final class CodexSkillCatalog {
  CodexSkillCatalog({
    required Iterable<CodexSkill> skills,
    Iterable<String> errors = const [],
  })  : skills = _immutable(skills),
        errors = _immutable(errors);

  final List<CodexSkill> skills;
  final List<String> errors;
}

final class CodexSkillChunk {
  const CodexSkillChunk({
    required this.content,
    required this.nextOffset,
    required this.totalBytes,
  });

  final String content;
  final int? nextOffset;
  final int totalBytes;
}

final class CodexHookActivity {
  CodexHookActivity({
    required this.id,
    required this.eventName,
    required this.handlerType,
    required this.status,
    this.statusMessage,
    Iterable<String> details = const [],
  }) : details = _immutable(details);

  final String id;
  final String eventName;
  final String handlerType;
  final CodexHookRunStatus status;
  final String? statusMessage;
  final List<String> details;
}

final class CodexTurnProgress {
  CodexTurnProgress({
    this.text = '',
    this.commentary = '',
    this.reasoning = '',
    this.plan = '',
    this.planProgress,
    this.shellOutput = '',
    this.shellExitCode,
    this.workActivity,
    Iterable<CodexHookActivity> hookActivities = const [],
    this.isTruncated = false,
  }) : hookActivities = _immutable(hookActivities);

  final String text;
  final String commentary;
  final String reasoning;
  final String plan;
  final CodexPlanProgress? planProgress;
  final String shellOutput;
  final int? shellExitCode;
  final CodexWorkActivity? workActivity;
  final List<CodexHookActivity> hookActivities;
  final bool isTruncated;
}

final class CodexWorkspace {
  CodexWorkspace({required String path, String? displayName})
      : path = _nonBlank(path, 'path'),
        displayName = _nonBlank(displayName ?? path, 'displayName') {
    if (path.contains('\u0000')) {
      throw ArgumentError.value(path, 'path', 'must not contain NUL');
    }
  }
  final String path;
  final String displayName;
}

final class CodexWorkspaceRequirement {
  const CodexWorkspaceRequirement({
    required this.reason,
    required this.message,
  });

  final CodexWorkspaceSelectionReason reason;
  final String message;
}

final class CodexConversationOpenOptions {
  const CodexConversationOpenOptions({
    this.conversationId,
    this.approvalPreset,
    this.serviceTier,
  });

  final String? conversationId;
  final CodexApprovalPreset? approvalPreset;
  final String? serviceTier;
}

final class CodexConversationSummary {
  const CodexConversationSummary({
    required this.conversationId,
    required this.title,
    required this.updatedAtEpochSeconds,
  });

  final CodexConversationId conversationId;
  final String title;
  final int updatedAtEpochSeconds;
}
