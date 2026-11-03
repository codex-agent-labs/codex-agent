import 'errors.dart';
import 'models.dart';
import 'value_native.dart';

extension CodexApprovalPresetMetadata on CodexApprovalPreset {
  String get displayName => switch (this) {
        CodexApprovalPreset.never => 'Never',
        CodexApprovalPreset.autoReview => 'Auto review',
        CodexApprovalPreset.askMe => 'Ask me',
        CodexApprovalPreset.strict => 'Strict',
      };
}

extension CodexCapabilityMetadata on CodexCapability {
  String get id => switch (this) { CodexCapability.webSearch => 'web_search' };
  String get displayLabel =>
      switch (this) { CodexCapability.webSearch => 'Web search' };
  String? get icon => switch (this) { CodexCapability.webSearch => '🌐' };
  String get promptLabel =>
      switch (this) { CodexCapability.webSearch => 'Use 🌐 Web search' };
}

extension CodexSkillScopeMetadata on CodexSkillScope {
  String get displayName => switch (this) {
        CodexSkillScope.system => 'Built in',
        CodexSkillScope.user => 'User',
        CodexSkillScope.repo => 'Workspace',
        CodexSkillScope.plugin => 'Plugin',
        CodexSkillScope.admin => 'Managed',
      };
}

final class CodexAuthorizationUrl {
  const CodexAuthorizationUrl._(this.value, this.purpose);

  factory CodexAuthorizationUrl.chatGpt(String value) {
    final native = nativeAuthorizationUrl(
      'codex_agent_authorization_url_chat_gpt',
      value,
    );
    return CodexAuthorizationUrl._(native.value, native.purpose);
  }

  factory CodexAuthorizationUrl.external(String value) {
    final native = nativeAuthorizationUrl(
      'codex_agent_authorization_url_external',
      value,
    );
    return CodexAuthorizationUrl._(native.value, native.purpose);
  }

  final String value;
  final CodexAuthorizationPurpose purpose;

  @override
  String toString() => 'CodexAuthorizationUrl(purpose: $purpose)';
}

sealed class CodexAuthenticationMethod {
  const CodexAuthenticationMethod();
}

final class CodexApiKeyAuthentication extends CodexAuthenticationMethod {
  CodexApiKeyAuthentication(String value) : value = _required(value, 'value');
  final String value;
  @override
  String toString() => 'CodexApiKeyAuthentication(**redacted**)';
}

final class CodexChatGptBrowserAuthentication
    extends CodexAuthenticationMethod {
  const CodexChatGptBrowserAuthentication._();
  static const instance = CodexChatGptBrowserAuthentication._();
}

final class CodexChatGptDeviceCodeAuthentication
    extends CodexAuthenticationMethod {
  const CodexChatGptDeviceCodeAuthentication._();
  static const instance = CodexChatGptDeviceCodeAuthentication._();
}

String _required(String value, String name) {
  if (value.trim().isEmpty) throw ArgumentError.value(value, name, 'blank');
  return value;
}

List<T> _list<T>(Iterable<T>? values) =>
    List<T>.unmodifiable(values ?? const <Never>[]);
Set<T> _set<T>(Iterable<T>? values) => Set<T>.unmodifiable(values ?? const {});
Map<K, V> _map<K, V>(Map<K, V>? values) =>
    Map<K, V>.unmodifiable(values ?? const {});

final class CodexAuthenticationState {
  const CodexAuthenticationState({
    this.status = CodexAuthenticationStatus.signedOut,
    this.pendingSignInUrl,
    this.deviceVerificationUrl,
    this.deviceUserCode,
    this.failure,
  });
  final CodexAuthenticationStatus status;
  final CodexAuthorizationUrl? pendingSignInUrl;
  final CodexAuthorizationUrl? deviceVerificationUrl;
  final String? deviceUserCode;
  final CodexFailure? failure;
}

final class CodexConversationSnapshot {
  CodexConversationSnapshot({
    required this.summary,
    required Iterable<CodexMessage> messages,
  }) : messages = _list(messages);
  final CodexConversationSummary summary;
  final List<CodexMessage> messages;
}

sealed class CodexInvocation {
  const CodexInvocation();
  String get name;
  String get key;
}

final class CodexSkillInvocation extends CodexInvocation {
  const CodexSkillInvocation({required this.name, required this.path});
  @override
  final String name;
  final String path;
  @override
  String get key => 'skill:$path';
}

final class CodexPluginInvocation extends CodexInvocation {
  const CodexPluginInvocation({required this.name, required this.uri});
  @override
  final String name;
  final String uri;
  @override
  String get key => 'plugin:$uri';
}

final class CodexMessage {
  CodexMessage({
    required this.id,
    this.clientMessageId,
    required this.role,
    required this.text,
    this.collaborationMode = CodexCollaborationMode.defaultMode,
    this.reasoning,
    this.plan,
    this.shellCommand,
    this.exitCode,
    Iterable<CodexCapability>? capabilities,
    Iterable<CodexInvocation>? invocations,
  })  : capabilities = _set(capabilities),
        invocations = _list(invocations);
  final String id;
  final String? clientMessageId;
  final CodexMessageRole role;
  final String text;
  final CodexCollaborationMode collaborationMode;
  final String? reasoning;
  final String? plan;
  final String? shellCommand;
  final int? exitCode;
  final Set<CodexCapability> capabilities;
  final List<CodexInvocation> invocations;
}

final class CodexTurnRequest {
  CodexTurnRequest({
    required this.prompt,
    this.clientMessageId,
    this.model,
    this.effort,
    this.serviceTier,
    this.approvalPreset = CodexApprovalPreset.autoReview,
    Iterable<CodexCapability>? capabilities,
    Iterable<CodexInvocation>? invocations,
    this.collaborationMode = CodexCollaborationMode.defaultMode,
  })  : capabilities = _set(capabilities),
        invocations = _list(invocations);
  final String prompt;
  final String? clientMessageId;
  final String? model;
  final String? effort;
  final String? serviceTier;
  final CodexApprovalPreset approvalPreset;
  final Set<CodexCapability> capabilities;
  final List<CodexInvocation> invocations;
  final CodexCollaborationMode collaborationMode;
}

sealed class CodexFormValue {
  const CodexFormValue();
}

final class CodexTextFormValue extends CodexFormValue {
  const CodexTextFormValue(this.value);
  final String value;
}

final class CodexNumberFormValue extends CodexFormValue {
  const CodexNumberFormValue(this.value);
  final double value;
}

final class CodexBooleanFormValue extends CodexFormValue {
  const CodexBooleanFormValue(this.value);
  final bool value;
}

final class CodexTextListFormValue extends CodexFormValue {
  CodexTextListFormValue(Iterable<String> value) : value = _list(value);
  final List<String> value;
}

final class CodexFormField {
  CodexFormField({
    required this.name,
    required this.title,
    required this.type,
    this.description,
    this.isRequired = false,
    Iterable<CodexFormOption>? options,
    this.defaultValue,
    this.minimum,
    this.maximum,
    this.format,
    this.minimumLength,
    this.maximumLength,
    this.minimumSelections,
    this.maximumSelections,
    this.allowsOther = false,
    this.isSecret = false,
  }) : options = _list(options) {
    for (final bound in <int?>[
      minimumLength,
      maximumLength,
      minimumSelections,
      maximumSelections,
    ]) {
      if (bound != null && bound < 0) {
        throw ArgumentError.value(bound, 'bound', 'must not be negative');
      }
    }
    if (minimumLength != null &&
            maximumLength != null &&
            minimumLength! > maximumLength! ||
        minimumSelections != null &&
            maximumSelections != null &&
            minimumSelections! > maximumSelections!) {
      throw ArgumentError('minimum must not exceed maximum');
    }
  }
  final String name;
  final String title;
  final CodexFormFieldType type;
  final String? description;
  final bool isRequired;
  final List<CodexFormOption> options;
  final CodexFormValue? defaultValue;
  final double? minimum;
  final double? maximum;
  final CodexFormStringFormat? format;
  final int? minimumLength;
  final int? maximumLength;
  final int? minimumSelections;
  final int? maximumSelections;
  final bool allowsOther;
  final bool isSecret;

  bool accepts(CodexFormValue? value) => nativeFormFieldAccepts(this, value);
}

final class CodexElicitation {
  CodexElicitation({
    required this.requestId,
    required this.serverName,
    required this.conversationId,
    required this.message,
    Iterable<CodexFormField>? form,
    this.url,
  }) : form = form == null ? null : _list(form);
  final String requestId;
  final String serverName;
  final CodexConversationId conversationId;
  final String message;
  final List<CodexFormField>? form;
  final String? url;

  Map<String, CodexFormValue> initialValues() =>
      nativeElicitationInitialValues(this);

  CodexElicitationValidation validate(Map<String, CodexFormValue> content) =>
      nativeElicitationValidate(this, content);

  CodexElicitationResponse accept(Map<String, CodexFormValue> content) =>
      nativeElicitationAccept(this, content);

  bool accepts(CodexElicitationResponse response) =>
      nativeElicitationAccepts(this, response);
}

final class CodexElicitationResponse {
  CodexElicitationResponse({
    required this.action,
    Map<String, CodexFormValue>? content,
  }) : content = _map(content);
  final CodexElicitationAction action;
  final Map<String, CodexFormValue> content;

  factory CodexElicitationResponse.decline() => nativeResponseFactory(
        'codex_agent_elicitation_response_decline',
      );

  factory CodexElicitationResponse.cancel() => nativeResponseFactory(
        'codex_agent_elicitation_response_cancel',
      );
}

sealed class CodexHookHandler {
  const CodexHookHandler();
}

final class CodexCommandHookHandler extends CodexHookHandler {
  const CodexCommandHookHandler({required this.command, this.isAsync = false});
  final String command;
  final bool isAsync;
}

final class CodexMcpToolHookHandler extends CodexHookHandler {
  const CodexMcpToolHookHandler({required this.server, required this.tool});
  final String server;
  final String tool;
}

final class CodexPromptHookHandler extends CodexHookHandler {
  const CodexPromptHookHandler._();
  static const instance = CodexPromptHookHandler._();
}

final class CodexAgentHookHandler extends CodexHookHandler {
  const CodexAgentHookHandler._();
  static const instance = CodexAgentHookHandler._();
}

final class CodexHook {
  CodexHook({
    required this.key,
    required this.currentHash,
    required this.isEnabled,
    required this.eventName,
    required this.handler,
    required this.isManaged,
    required this.source,
    required this.sourcePath,
    required this.timeoutSeconds,
    required this.trustStatus,
    this.matcher,
    this.pluginId,
    this.statusMessage,
    CodexResourceOrigin? origin,
    this.canUninstall = false,
  }) : origin = origin ?? _hookOrigin(source, isManaged, pluginId);
  final String key;
  final String currentHash;
  final bool isEnabled;
  final String eventName;
  final CodexHookHandler handler;
  final bool isManaged;
  final String source;
  final String sourcePath;
  final int timeoutSeconds;
  final CodexHookTrustStatus trustStatus;
  final String? matcher;
  final String? pluginId;
  final String? statusMessage;
  final CodexResourceOrigin origin;
  bool get canTrust =>
      trustStatus == CodexHookTrustStatus.untrusted ||
      trustStatus == CodexHookTrustStatus.modified;
  final bool canUninstall;
}

CodexResourceOrigin _hookOrigin(String source, bool managed, String? pluginId) {
  if (pluginId != null || source == 'PLUGIN') return CodexResourceOrigin.plugin;
  if (managed ||
      const <String>{
        'SYSTEM',
        'MDM',
        'CLOUD_REQUIREMENTS',
        'CLOUD_MANAGED_CONFIG',
        'LEGACY_MANAGED_CONFIG_FILE',
        'LEGACY_MANAGED_CONFIG_MDM',
      }.contains(source)) {
    return CodexResourceOrigin.managed;
  }
  return switch (source) {
    'USER' => CodexResourceOrigin.user,
    'PROJECT' => CodexResourceOrigin.workspace,
    _ => CodexResourceOrigin.unknown,
  };
}

final class CodexHookCatalog {
  CodexHookCatalog({
    required Iterable<CodexHook> hooks,
    Iterable<String>? warnings,
    Iterable<String>? errors,
  })  : hooks = _list(hooks),
        warnings = _list(warnings),
        errors = _list(errors);
  final List<CodexHook> hooks;
  final List<String> warnings;
  final List<String> errors;
}

sealed class CodexIntegration {
  const CodexIntegration();
  String get id;
  String get displayName;
}

final class CodexConnectorIntegration extends CodexIntegration {
  const CodexConnectorIntegration(this.connector);
  final CodexConnector connector;
  @override
  String get id => connector.id;
  @override
  String get displayName => connector.name;
}

final class CodexMcpServerIntegration extends CodexIntegration {
  const CodexMcpServerIntegration(this.server);
  final CodexMcpServer server;
  @override
  String get id => server.name;
  @override
  String get displayName => server.displayName;
}

final class CodexIntegrationAuthorizationState {
  const CodexIntegrationAuthorizationState({
    this.status = CodexIntegrationAuthorizationStatus.idle,
    this.target,
    this.failure,
  });
  final CodexIntegrationAuthorizationStatus status;
  final CodexIntegration? target;
  final CodexFailure? failure;
}

sealed class CodexPendingInteraction {
  const CodexPendingInteraction();
  String get requestId;
  CodexConversationId get conversationId;
}

final class CodexPendingApproval extends CodexPendingInteraction {
  const CodexPendingApproval({
    required this.requestId,
    required this.conversationId,
    required this.title,
    required this.details,
  });
  @override
  final String requestId;
  @override
  final CodexConversationId conversationId;
  final String title;
  final String details;
}

final class CodexPendingElicitation extends CodexPendingInteraction {
  const CodexPendingElicitation(this.elicitation);
  final CodexElicitation elicitation;
  @override
  String get requestId => elicitation.requestId;
  @override
  CodexConversationId get conversationId => elicitation.conversationId;
}

final class CodexInteractionState {
  CodexInteractionState({
    Iterable<CodexPendingInteraction>? pending,
    Iterable<String>? resolvingRequestIds,
    this.failure,
  })  : pending = _list(pending),
        resolvingRequestIds = _set(resolvingRequestIds);
  final List<CodexPendingInteraction> pending;
  final Set<String> resolvingRequestIds;
  final CodexFailure? failure;

  List<CodexPendingInteraction> pendingFor(
          CodexConversationId conversationId) =>
      nativeInteractionPendingFor(this, conversationId);

  bool isResolving(CodexPendingInteraction interaction) =>
      nativeInteractionIsResolving(this, interaction);
}

final class CodexPathWorkspaceSelection {
  CodexPathWorkspaceSelection(String path) : path = _required(path, 'path') {
    if (path.contains('\u0000')) {
      throw ArgumentError.value(path, 'path', 'must not contain NUL');
    }
  }
  final String path;
}

sealed class CodexWorkspaceResolution {
  const CodexWorkspaceResolution();
}

final class CodexAvailableWorkspace extends CodexWorkspaceResolution {
  const CodexAvailableWorkspace(this.workspace);
  final CodexWorkspace workspace;
}

final class CodexWorkspaceSelectionRequired extends CodexWorkspaceResolution {
  const CodexWorkspaceSelectionRequired({
    required this.reason,
    required this.message,
  });
  final CodexWorkspaceSelectionReason reason;
  final String message;
}

sealed class CodexHostStateValue {
  const CodexHostStateValue();
}

final class CodexNewHostState extends CodexHostStateValue {
  const CodexNewHostState._();
  static const instance = CodexNewHostState._();
}

final class CodexRestoringHostState extends CodexHostStateValue {
  const CodexRestoringHostState._();
  static const instance = CodexRestoringHostState._();
}

final class CodexPreparingHostState extends CodexHostStateValue {
  const CodexPreparingHostState(this.workspace);
  final CodexWorkspace workspace;
}

final class CodexWorkspaceRequiredHostState extends CodexHostStateValue {
  const CodexWorkspaceRequiredHostState(this.requirement);
  final CodexWorkspaceSelectionRequired requirement;
}

final class CodexFailedHostState extends CodexHostStateValue {
  const CodexFailedHostState({required this.failure, this.workspace});
  final CodexWorkspace? workspace;
  final CodexFailure failure;
}

final class CodexClosedHostState extends CodexHostStateValue {
  const CodexClosedHostState._();
  static const instance = CodexClosedHostState._();
}
