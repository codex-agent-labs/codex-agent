part of 'client.dart';

/// Internal executable receipt hook. Hidden from the package entry point.
void Function(String symbol)? leafNativeCallObserver;

typedef _LeafAgentServiceNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeAgent>,
  Pointer<Pointer<Void>>,
);
typedef _LeafAgentServiceDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeAgent>,
  Pointer<Pointer<Void>>,
);
typedef _LeafAvailabilityNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Int32>,
);
typedef _LeafAvailabilityDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Int32>,
);
typedef _LeafOperationNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<NativeFunction<OperationCallbackNative>>,
  Pointer<Void>,
  Pointer<Pointer<CodexNativeOperation>>,
);
typedef _LeafOperationDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<NativeFunction<OperationCallbackNative>>,
  Pointer<Void>,
  Pointer<Pointer<CodexNativeOperation>>,
);
typedef _LeafIntOperationNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Int32,
  Pointer<NativeFunction<OperationCallbackNative>>,
  Pointer<Void>,
  Pointer<Pointer<CodexNativeOperation>>,
);
typedef _LeafIntOperationDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  int,
  Pointer<NativeFunction<OperationCallbackNative>>,
  Pointer<Void>,
  Pointer<Pointer<CodexNativeOperation>>,
);
typedef _LeafHandleOperationNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Void>,
  Pointer<NativeFunction<OperationCallbackNative>>,
  Pointer<Void>,
  Pointer<Pointer<CodexNativeOperation>>,
);
typedef _LeafHandleOperationDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Void>,
  Pointer<NativeFunction<OperationCallbackNative>>,
  Pointer<Void>,
  Pointer<Pointer<CodexNativeOperation>>,
);
typedef _LeafHandleIntOperationNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Void>,
  Int32,
  Pointer<NativeFunction<OperationCallbackNative>>,
  Pointer<Void>,
  Pointer<Pointer<CodexNativeOperation>>,
);
typedef _LeafHandleIntOperationDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Void>,
  int,
  Pointer<NativeFunction<OperationCallbackNative>>,
  Pointer<Void>,
  Pointer<Pointer<CodexNativeOperation>>,
);
typedef _LeafTwoHandleOperationNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Void>,
  Pointer<Void>,
  Pointer<NativeFunction<OperationCallbackNative>>,
  Pointer<Void>,
  Pointer<Pointer<CodexNativeOperation>>,
);
typedef _LeafTwoHandleOperationDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Void>,
  Pointer<Void>,
  Pointer<NativeFunction<OperationCallbackNative>>,
  Pointer<Void>,
  Pointer<Pointer<CodexNativeOperation>>,
);
typedef _LeafStringIntOperationNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<CodexStringView>,
  Int32,
  Pointer<NativeFunction<OperationCallbackNative>>,
  Pointer<Void>,
  Pointer<Pointer<CodexNativeOperation>>,
);
typedef _LeafStringIntOperationDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<CodexStringView>,
  int,
  Pointer<NativeFunction<OperationCallbackNative>>,
  Pointer<Void>,
  Pointer<Pointer<CodexNativeOperation>>,
);
typedef _LeafStringInt64OperationNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<CodexStringView>,
  Int64,
  Pointer<NativeFunction<OperationCallbackNative>>,
  Pointer<Void>,
  Pointer<Pointer<CodexNativeOperation>>,
);
typedef _LeafStringInt64OperationDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<CodexStringView>,
  int,
  Pointer<NativeFunction<OperationCallbackNative>>,
  Pointer<Void>,
  Pointer<Pointer<CodexNativeOperation>>,
);
typedef _LeafSnapshotHandleNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeSnapshot>,
  Pointer<Pointer<Void>>,
);
typedef _LeafSnapshotHandleDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeSnapshot>,
  Pointer<Pointer<Void>>,
);
typedef _LeafSnapshotIntNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeSnapshot>,
  Pointer<Int32>,
);
typedef _LeafSnapshotIntDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeSnapshot>,
  Pointer<Int32>,
);
typedef _LeafSnapshotCountNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeSnapshot>,
  Pointer<Size>,
);
typedef _LeafSnapshotCountDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeSnapshot>,
  Pointer<Size>,
);
typedef _LeafSnapshotAtNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeSnapshot>,
  Size,
  Pointer<Pointer<Void>>,
);
typedef _LeafSnapshotAtDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeSnapshot>,
  int,
  Pointer<Pointer<Void>>,
);
typedef _LeafOperationHandleNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeOperation>,
  Pointer<Pointer<Void>>,
);
typedef _LeafOperationHandleDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeOperation>,
  Pointer<Pointer<Void>>,
);
typedef _LeafOperationCountNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeOperation>,
  Pointer<Size>,
);
typedef _LeafOperationCountDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeOperation>,
  Pointer<Size>,
);
typedef _LeafOperationAtNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeOperation>,
  Size,
  Pointer<Pointer<Void>>,
);
typedef _LeafOperationAtDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeOperation>,
  int,
  Pointer<Pointer<Void>>,
);
typedef _LeafOperationIntNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeOperation>,
  Pointer<Int32>,
);
typedef _LeafOperationIntDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeOperation>,
  Pointer<Int32>,
);
typedef _LeafOperationStringNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeOperation>,
  Pointer<Uint8>,
  Size,
  Pointer<Size>,
);
typedef _LeafOperationStringDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeOperation>,
  Pointer<Uint8>,
  int,
  Pointer<Size>,
);

final class _LeafApi {
  _LeafApi(this.library)
      : agentAuthentication = library.lookupFunction<_LeafAgentServiceNative,
            _LeafAgentServiceDart>('codex_agent_agent_authentication'),
        agentInteractions = library.lookupFunction<_LeafAgentServiceNative,
            _LeafAgentServiceDart>('codex_agent_agent_interactions'),
        agentIntegrationAuthorization = library
            .lookupFunction<_LeafAgentServiceNative, _LeafAgentServiceDart>(
                'codex_agent_agent_integration_authorization'),
        agentModels = library.lookupFunction<_LeafAgentServiceNative,
            _LeafAgentServiceDart>('codex_agent_agent_models'),
        agentSkills = library.lookupFunction<_LeafAgentServiceNative,
            _LeafAgentServiceDart>('codex_agent_agent_skills'),
        agentHooks = library.lookupFunction<_LeafAgentServiceNative,
            _LeafAgentServiceDart>('codex_agent_agent_hooks'),
        agentPlugins = library.lookupFunction<_LeafAgentServiceNative,
            _LeafAgentServiceDart>('codex_agent_agent_plugins'),
        agentConnectors = library.lookupFunction<_LeafAgentServiceNative,
            _LeafAgentServiceDart>('codex_agent_agent_connectors'),
        agentMcpServers = library.lookupFunction<_LeafAgentServiceNative,
            _LeafAgentServiceDart>('codex_agent_agent_mcp_servers'),
        authenticationRelease = library.lookupFunction<
            CodexReleaseHandleNative<Void>,
            CodexReleaseHandleDart<Void>>('codex_agent_authentication_release'),
        interactionsRelease = library.lookupFunction<
            CodexReleaseHandleNative<Void>,
            CodexReleaseHandleDart<Void>>('codex_agent_interactions_release'),
        integrationAuthorizationRelease = library.lookupFunction<
                CodexReleaseHandleNative<Void>, CodexReleaseHandleDart<Void>>(
            'codex_agent_integration_authorization_release'),
        modelsRelease = library.lookupFunction<CodexReleaseHandleNative<Void>,
            CodexReleaseHandleDart<Void>>('codex_agent_models_release'),
        skillsRelease = library.lookupFunction<CodexReleaseHandleNative<Void>,
            CodexReleaseHandleDart<Void>>('codex_agent_skills_release'),
        hooksRelease = library.lookupFunction<CodexReleaseHandleNative<Void>,
            CodexReleaseHandleDart<Void>>('codex_agent_hooks_release'),
        pluginsRelease = library.lookupFunction<CodexReleaseHandleNative<Void>,
            CodexReleaseHandleDart<Void>>('codex_agent_plugins_release'),
        connectorsRelease = library.lookupFunction<
            CodexReleaseHandleNative<Void>,
            CodexReleaseHandleDart<Void>>('codex_agent_connectors_release'),
        mcpServersRelease = library.lookupFunction<
            CodexReleaseHandleNative<Void>,
            CodexReleaseHandleDart<Void>>('codex_agent_mcp_servers_release'),
        skillsIsAvailable = library.lookupFunction<_LeafAvailabilityNative,
            _LeafAvailabilityDart>('codex_agent_skills_is_available'),
        hooksIsAvailable = library.lookupFunction<_LeafAvailabilityNative,
            _LeafAvailabilityDart>('codex_agent_hooks_is_available'),
        pluginsIsAvailable = library.lookupFunction<_LeafAvailabilityNative,
            _LeafAvailabilityDart>('codex_agent_plugins_is_available'),
        connectorsIsAvailable = library.lookupFunction<_LeafAvailabilityNative,
            _LeafAvailabilityDart>('codex_agent_connectors_is_available'),
        mcpServersIsAvailable = library.lookupFunction<_LeafAvailabilityNative,
            _LeafAvailabilityDart>('codex_agent_mcp_servers_is_available'),
        authenticationAuthenticateApiKey = library.lookupFunction<
                _LeafHandleOperationNative, _LeafHandleOperationDart>(
            'codex_agent_authentication_authenticate_api_key'),
        authenticationAuthenticateChatGptBrowser = library.lookupFunction<
                _LeafHandleOperationNative, _LeafHandleOperationDart>(
            'codex_agent_authentication_authenticate_chat_gpt_browser'),
        authenticationAuthenticateChatGptDeviceCode = library.lookupFunction<
                _LeafHandleOperationNative, _LeafHandleOperationDart>(
            'codex_agent_authentication_authenticate_chat_gpt_device_code'),
        authenticationCancel =
            library.lookupFunction<_LeafOperationNative, _LeafOperationDart>(
                'codex_agent_authentication_cancel'),
        authenticationSignOut =
            library.lookupFunction<_LeafOperationNative, _LeafOperationDart>(
                'codex_agent_authentication_sign_out'),
        integrationAuthorizationAuthorize = library.lookupFunction<
                _LeafHandleOperationNative, _LeafHandleOperationDart>(
            'codex_agent_integration_authorization_authorize'),
        integrationAuthorizationCancel =
            library.lookupFunction<_LeafOperationNative, _LeafOperationDart>(
                'codex_agent_integration_authorization_cancel'),
        modelsList =
            library.lookupFunction<_LeafOperationNative, _LeafOperationDart>(
                'codex_agent_models_list'),
        modelsResolve = library.lookupFunction<_LeafIntOperationNative,
            _LeafIntOperationDart>('codex_agent_models_resolve'),
        modelsResolveEffort = library.lookupFunction<
            _LeafHandleIntOperationNative,
            _LeafHandleIntOperationDart>('codex_agent_models_resolve_effort'),
        modelsResolveServiceTier = library.lookupFunction<
                _LeafHandleIntOperationNative, _LeafHandleIntOperationDart>(
            'codex_agent_models_resolve_service_tier'),
        skillsList = library.lookupFunction<_LeafIntOperationNative,
            _LeafIntOperationDart>('codex_agent_skills_list'),
        skillsRead = library.lookupFunction<_LeafStringInt64OperationNative,
            _LeafStringInt64OperationDart>('codex_agent_skills_read'),
        skillsInstall = library.lookupFunction<_LeafStringIntOperationNative,
            _LeafStringIntOperationDart>('codex_agent_skills_install'),
        skillsUninstall = library.lookupFunction<_LeafHandleOperationNative,
            _LeafHandleOperationDart>('codex_agent_skills_uninstall'),
        hooksList =
            library.lookupFunction<_LeafOperationNative, _LeafOperationDart>(
                'codex_agent_hooks_list'),
        hooksInstall = library.lookupFunction<_LeafStringIntOperationNative,
            _LeafStringIntOperationDart>('codex_agent_hooks_install'),
        hooksUninstall = library.lookupFunction<_LeafHandleOperationNative,
            _LeafHandleOperationDart>('codex_agent_hooks_uninstall'),
        hooksTrust = library.lookupFunction<_LeafHandleOperationNative,
            _LeafHandleOperationDart>('codex_agent_hooks_trust'),
        pluginsList = library.lookupFunction<_LeafIntOperationNative,
            _LeafIntOperationDart>('codex_agent_plugins_list'),
        pluginsRead = library.lookupFunction<_LeafHandleOperationNative,
            _LeafHandleOperationDart>('codex_agent_plugins_read'),
        pluginsInstall = library.lookupFunction<_LeafHandleOperationNative,
            _LeafHandleOperationDart>('codex_agent_plugins_install'),
        pluginsUninstall = library.lookupFunction<_LeafHandleOperationNative,
            _LeafHandleOperationDart>('codex_agent_plugins_uninstall'),
        connectorsList = library.lookupFunction<_LeafIntOperationNative,
            _LeafIntOperationDart>('codex_agent_connectors_list'),
        mcpServersList =
            library.lookupFunction<_LeafOperationNative, _LeafOperationDart>(
                'codex_agent_mcp_servers_list'),
        mcpServersAdd = library.lookupFunction<_LeafHandleOperationNative,
            _LeafHandleOperationDart>('codex_agent_mcp_servers_add'),
        mcpServersRemove = library.lookupFunction<_LeafHandleOperationNative,
            _LeafHandleOperationDart>('codex_agent_mcp_servers_remove'),
        authenticationStateGet = library.lookupFunction<
            CodexGetSnapshotNative<Void>,
            CodexGetSnapshotDart<Void>>('codex_agent_authentication_state_get'),
        authenticationStateSubscribe = library.lookupFunction<
                CodexSubscribeNative<Void>, CodexSubscribeDart<Void>>(
            'codex_agent_authentication_state_subscribe'),
        authenticationIsAuthenticatedGet = library.lookupFunction<
                CodexGetSnapshotNative<Void>, CodexGetSnapshotDart<Void>>(
            'codex_agent_authentication_is_authenticated_get'),
        authenticationIsAuthenticatedSubscribe = library.lookupFunction<
                CodexSubscribeNative<Void>, CodexSubscribeDart<Void>>(
            'codex_agent_authentication_is_authenticated_subscribe'),
        authenticationIsAuthenticatingGet = library.lookupFunction<
                CodexGetSnapshotNative<Void>, CodexGetSnapshotDart<Void>>(
            'codex_agent_authentication_is_authenticating_get'),
        authenticationIsAuthenticatingSubscribe = library.lookupFunction<
                CodexSubscribeNative<Void>, CodexSubscribeDart<Void>>(
            'codex_agent_authentication_is_authenticating_subscribe'),
        authenticationStateValue = library.lookupFunction<
            _LeafSnapshotHandleNative,
            _LeafSnapshotHandleDart>('codex_agent_authentication_state_value'),
        integrationAuthorizationStateGet = library.lookupFunction<
                CodexGetSnapshotNative<Void>, CodexGetSnapshotDart<Void>>(
            'codex_agent_integration_authorization_state_get'),
        integrationAuthorizationStateSubscribe = library.lookupFunction<
                CodexSubscribeNative<Void>, CodexSubscribeDart<Void>>(
            'codex_agent_integration_authorization_state_subscribe'),
        integrationAuthorizationActiveGet = library.lookupFunction<
                CodexGetSnapshotNative<Void>, CodexGetSnapshotDart<Void>>(
            'codex_agent_integration_authorization_active_get'),
        integrationAuthorizationActiveSubscribe = library.lookupFunction<
                CodexSubscribeNative<Void>, CodexSubscribeDart<Void>>(
            'codex_agent_integration_authorization_active_subscribe'),
        integrationAuthorizationIsAuthorizingGet = library.lookupFunction<
                CodexGetSnapshotNative<Void>, CodexGetSnapshotDart<Void>>(
            'codex_agent_integration_authorization_is_authorizing_get'),
        integrationAuthorizationIsAuthorizingSubscribe = library.lookupFunction<
                CodexSubscribeNative<Void>, CodexSubscribeDart<Void>>(
            'codex_agent_integration_authorization_is_authorizing_subscribe'),
        integrationAuthorizationStateValue = library
            .lookupFunction<_LeafSnapshotHandleNative, _LeafSnapshotHandleDart>(
                'codex_agent_integration_authorization_state_value'),
        integrationAuthorizationActiveHasValue = library
            .lookupFunction<_LeafSnapshotIntNative, _LeafSnapshotIntDart>(
                'codex_agent_integration_authorization_active_has_value'),
        integrationAuthorizationActiveValue = library
            .lookupFunction<_LeafSnapshotHandleNative, _LeafSnapshotHandleDart>(
                'codex_agent_integration_authorization_active_value'),
        interactionsStateGet = library.lookupFunction<
            CodexGetSnapshotNative<Void>,
            CodexGetSnapshotDart<Void>>('codex_agent_interactions_state_get'),
        interactionsStateSubscribe = library.lookupFunction<
                CodexSubscribeNative<Void>, CodexSubscribeDart<Void>>(
            'codex_agent_interactions_state_subscribe'),
        interactionsApprovalsGet = library.lookupFunction<
                CodexGetSnapshotNative<Void>, CodexGetSnapshotDart<Void>>(
            'codex_agent_interactions_approvals_get'),
        interactionsApprovalsSubscribe = library.lookupFunction<
                CodexSubscribeNative<Void>, CodexSubscribeDart<Void>>(
            'codex_agent_interactions_approvals_subscribe'),
        interactionsElicitationsGet = library.lookupFunction<
                CodexGetSnapshotNative<Void>, CodexGetSnapshotDart<Void>>(
            'codex_agent_interactions_elicitations_get'),
        interactionsElicitationsSubscribe = library.lookupFunction<
                CodexSubscribeNative<Void>, CodexSubscribeDart<Void>>(
            'codex_agent_interactions_elicitations_subscribe'),
        interactionsStateValue = library.lookupFunction<
            _LeafSnapshotHandleNative,
            _LeafSnapshotHandleDart>('codex_agent_interactions_state_value'),
        interactionsApprovalsCount = library.lookupFunction<
            _LeafSnapshotCountNative,
            _LeafSnapshotCountDart>('codex_agent_interactions_approvals_count'),
        interactionsApprovalsAt =
            library.lookupFunction<_LeafSnapshotAtNative, _LeafSnapshotAtDart>(
                'codex_agent_interactions_approvals_at'),
        interactionsElicitationsCount = library
            .lookupFunction<_LeafSnapshotCountNative, _LeafSnapshotCountDart>(
                'codex_agent_interactions_elicitations_count'),
        interactionsElicitationsAt =
            library.lookupFunction<_LeafSnapshotAtNative, _LeafSnapshotAtDart>(
                'codex_agent_interactions_elicitations_at'),
        interactionsOpenUrl = library.lookupFunction<_LeafHandleOperationNative,
            _LeafHandleOperationDart>('codex_agent_interactions_open_url'),
        interactionsResolveApproval = library.lookupFunction<
                _LeafHandleIntOperationNative, _LeafHandleIntOperationDart>(
            'codex_agent_interactions_resolve_approval'),
        interactionsResolveElicitation = library.lookupFunction<
                _LeafTwoHandleOperationNative, _LeafTwoHandleOperationDart>(
            'codex_agent_interactions_resolve_elicitation'),
        operationModelsCount = library.lookupFunction<_LeafOperationCountNative,
            _LeafOperationCountDart>('codex_agent_operation_models_count'),
        operationModelAt = library.lookupFunction<_LeafOperationAtNative,
            _LeafOperationAtDart>('codex_agent_operation_model_at'),
        operationModel = library.lookupFunction<_LeafOperationHandleNative,
            _LeafOperationHandleDart>('codex_agent_operation_model'),
        operationStringCopy = library.lookupFunction<_LeafOperationStringNative,
            _LeafOperationStringDart>('codex_agent_operation_string_copy'),
        operationHasServiceTier = library.lookupFunction<
            _LeafOperationIntNative,
            _LeafOperationIntDart>('codex_agent_operation_has_service_tier'),
        operationServiceTier = library.lookupFunction<
            _LeafOperationHandleNative,
            _LeafOperationHandleDart>('codex_agent_operation_service_tier'),
        operationSkillCatalog = library.lookupFunction<
            _LeafOperationHandleNative,
            _LeafOperationHandleDart>('codex_agent_operation_skill_catalog'),
        operationSkillChunk = library.lookupFunction<_LeafOperationHandleNative,
            _LeafOperationHandleDart>('codex_agent_operation_skill_chunk'),
        operationSkill = library.lookupFunction<_LeafOperationHandleNative,
            _LeafOperationHandleDart>('codex_agent_operation_skill'),
        operationHookCatalog = library.lookupFunction<
            _LeafOperationHandleNative,
            _LeafOperationHandleDart>('codex_agent_operation_hook_catalog'),
        operationHook = library.lookupFunction<_LeafOperationHandleNative,
            _LeafOperationHandleDart>('codex_agent_operation_hook'),
        operationPluginCatalog = library.lookupFunction<
            _LeafOperationHandleNative,
            _LeafOperationHandleDart>('codex_agent_operation_plugin_catalog'),
        operationPluginDetail = library.lookupFunction<
            _LeafOperationHandleNative,
            _LeafOperationHandleDart>('codex_agent_operation_plugin_detail'),
        operationPluginInstallResult = library.lookupFunction<
                _LeafOperationHandleNative, _LeafOperationHandleDart>(
            'codex_agent_operation_plugin_install_result'),
        operationConnectorsCount = library.lookupFunction<
            _LeafOperationCountNative,
            _LeafOperationCountDart>('codex_agent_operation_connectors_count'),
        operationConnectorAt = library.lookupFunction<_LeafOperationAtNative,
            _LeafOperationAtDart>('codex_agent_operation_connector_at'),
        operationMcpServersCount = library.lookupFunction<
            _LeafOperationCountNative,
            _LeafOperationCountDart>('codex_agent_operation_mcp_servers_count'),
        operationMcpServerAt = library.lookupFunction<_LeafOperationAtNative,
            _LeafOperationAtDart>('codex_agent_operation_mcp_server_at'),
        operationMcpServer = library.lookupFunction<_LeafOperationHandleNative,
            _LeafOperationHandleDart>('codex_agent_operation_mcp_server');

  final DynamicLibrary library;
  final _LeafAgentServiceDart agentAuthentication;
  final _LeafAgentServiceDart agentInteractions;
  final _LeafAgentServiceDart agentIntegrationAuthorization;
  final _LeafAgentServiceDart agentModels;
  final _LeafAgentServiceDart agentSkills;
  final _LeafAgentServiceDart agentHooks;
  final _LeafAgentServiceDart agentPlugins;
  final _LeafAgentServiceDart agentConnectors;
  final _LeafAgentServiceDart agentMcpServers;
  final CodexReleaseHandleDart<Void> authenticationRelease;
  final CodexReleaseHandleDart<Void> interactionsRelease;
  final CodexReleaseHandleDart<Void> integrationAuthorizationRelease;
  final CodexReleaseHandleDart<Void> modelsRelease;
  final CodexReleaseHandleDart<Void> skillsRelease;
  final CodexReleaseHandleDart<Void> hooksRelease;
  final CodexReleaseHandleDart<Void> pluginsRelease;
  final CodexReleaseHandleDart<Void> connectorsRelease;
  final CodexReleaseHandleDart<Void> mcpServersRelease;
  final _LeafAvailabilityDart skillsIsAvailable;
  final _LeafAvailabilityDart hooksIsAvailable;
  final _LeafAvailabilityDart pluginsIsAvailable;
  final _LeafAvailabilityDart connectorsIsAvailable;
  final _LeafAvailabilityDart mcpServersIsAvailable;
  final _LeafHandleOperationDart authenticationAuthenticateApiKey;
  final _LeafHandleOperationDart authenticationAuthenticateChatGptBrowser;
  final _LeafHandleOperationDart authenticationAuthenticateChatGptDeviceCode;
  final _LeafOperationDart authenticationCancel;
  final _LeafOperationDart authenticationSignOut;
  final _LeafHandleOperationDart integrationAuthorizationAuthorize;
  final _LeafOperationDart integrationAuthorizationCancel;
  final _LeafOperationDart modelsList;
  final _LeafIntOperationDart modelsResolve;
  final _LeafHandleIntOperationDart modelsResolveEffort;
  final _LeafHandleIntOperationDart modelsResolveServiceTier;
  final _LeafIntOperationDart skillsList;
  final _LeafStringInt64OperationDart skillsRead;
  final _LeafStringIntOperationDart skillsInstall;
  final _LeafHandleOperationDart skillsUninstall;
  final _LeafOperationDart hooksList;
  final _LeafStringIntOperationDart hooksInstall;
  final _LeafHandleOperationDart hooksUninstall;
  final _LeafHandleOperationDart hooksTrust;
  final _LeafIntOperationDart pluginsList;
  final _LeafHandleOperationDart pluginsRead;
  final _LeafHandleOperationDart pluginsInstall;
  final _LeafHandleOperationDart pluginsUninstall;
  final _LeafIntOperationDart connectorsList;
  final _LeafOperationDart mcpServersList;
  final _LeafHandleOperationDart mcpServersAdd;
  final _LeafHandleOperationDart mcpServersRemove;
  final CodexGetSnapshotDart<Void> authenticationStateGet;
  final CodexSubscribeDart<Void> authenticationStateSubscribe;
  final CodexGetSnapshotDart<Void> authenticationIsAuthenticatedGet;
  final CodexSubscribeDart<Void> authenticationIsAuthenticatedSubscribe;
  final CodexGetSnapshotDart<Void> authenticationIsAuthenticatingGet;
  final CodexSubscribeDart<Void> authenticationIsAuthenticatingSubscribe;
  final _LeafSnapshotHandleDart authenticationStateValue;
  final CodexGetSnapshotDart<Void> integrationAuthorizationStateGet;
  final CodexSubscribeDart<Void> integrationAuthorizationStateSubscribe;
  final CodexGetSnapshotDart<Void> integrationAuthorizationActiveGet;
  final CodexSubscribeDart<Void> integrationAuthorizationActiveSubscribe;
  final CodexGetSnapshotDart<Void> integrationAuthorizationIsAuthorizingGet;
  final CodexSubscribeDart<Void> integrationAuthorizationIsAuthorizingSubscribe;
  final _LeafSnapshotHandleDart integrationAuthorizationStateValue;
  final _LeafSnapshotIntDart integrationAuthorizationActiveHasValue;
  final _LeafSnapshotHandleDart integrationAuthorizationActiveValue;
  final CodexGetSnapshotDart<Void> interactionsStateGet;
  final CodexSubscribeDart<Void> interactionsStateSubscribe;
  final CodexGetSnapshotDart<Void> interactionsApprovalsGet;
  final CodexSubscribeDart<Void> interactionsApprovalsSubscribe;
  final CodexGetSnapshotDart<Void> interactionsElicitationsGet;
  final CodexSubscribeDart<Void> interactionsElicitationsSubscribe;
  final _LeafSnapshotHandleDart interactionsStateValue;
  final _LeafSnapshotCountDart interactionsApprovalsCount;
  final _LeafSnapshotAtDart interactionsApprovalsAt;
  final _LeafSnapshotCountDart interactionsElicitationsCount;
  final _LeafSnapshotAtDart interactionsElicitationsAt;
  final _LeafHandleOperationDart interactionsOpenUrl;
  final _LeafHandleIntOperationDart interactionsResolveApproval;
  final _LeafTwoHandleOperationDart interactionsResolveElicitation;
  final _LeafOperationCountDart operationModelsCount;
  final _LeafOperationAtDart operationModelAt;
  final _LeafOperationHandleDart operationModel;
  final _LeafOperationStringDart operationStringCopy;
  final _LeafOperationIntDart operationHasServiceTier;
  final _LeafOperationHandleDart operationServiceTier;
  final _LeafOperationHandleDart operationSkillCatalog;
  final _LeafOperationHandleDart operationSkillChunk;
  final _LeafOperationHandleDart operationSkill;
  final _LeafOperationHandleDart operationHookCatalog;
  final _LeafOperationHandleDart operationHook;
  final _LeafOperationHandleDart operationPluginCatalog;
  final _LeafOperationHandleDart operationPluginDetail;
  final _LeafOperationHandleDart operationPluginInstallResult;
  final _LeafOperationCountDart operationConnectorsCount;
  final _LeafOperationAtDart operationConnectorAt;
  final _LeafOperationCountDart operationMcpServersCount;
  final _LeafOperationAtDart operationMcpServerAt;
  final _LeafOperationHandleDart operationMcpServer;
}

final Expando<_LeafApi> _leafApis = Expando<_LeafApi>('leaf service API');

_LeafApi _leafApi(_NativeContextOwner owner) =>
    _leafApis[owner] ??= _LeafApi(owner.api.library);

void _leafTrace(String symbol) => leafNativeCallObserver?.call(symbol);

final class _LeafFinalizerWork {
  const _LeafFinalizerWork(this.ticket, this.symbol);
  final _ReleaseTicket<Void> ticket;
  final String symbol;
}

abstract base class _LeafService implements Finalizable {
  _LeafService(
    _NativeContextOwner owner,
    _HostLifetime lifetime,
    Pointer<Pointer<Void>> slot,
    CodexReleaseHandleDart<Void> release,
    this._releaseSymbol,
  ) : _native = _OwnedNative<Void>(owner, lifetime, slot, release) {
    _finalizer.attach(
      this,
      _LeafFinalizerWork(_native.ticket, _releaseSymbol),
      detach: this,
    );
  }

  static final Finalizer<_LeafFinalizerWork> _finalizer =
      Finalizer<_LeafFinalizerWork>(
    (work) => work.ticket.finalize(work.symbol),
  );

  final _OwnedNative<Void> _native;
  final String _releaseSymbol;
  final _SubscriptionScope _subscriptions = _SubscriptionScope();

  _LeafApi get _api => _leafApi(_native.owner);
  Pointer<Void> get _handle => _native.requireHandle(runtimeType.toString());

  bool _availability(String symbol, _LeafAvailabilityDart call) {
    final result = nativeMemory.allocate<Int32>(sizeOf<Int32>());
    try {
      _leafTrace(symbol);
      checkStatus(
        call(_native.owner.require(), _handle, result),
        symbol,
      );
      return result.value != 0;
    } finally {
      nativeMemory.free(result);
    }
  }

  Future<void> close() async {
    await _subscriptions.close();
    await _native.ticket.close(_releaseSymbol);
    _finalizer.detach(this);
  }
}

Future<T> _leafOperation<T>(
  _LeafService service,
  String symbol,
  _OperationStarter start,
  T Function(Pointer<CodexNativeOperation>) decode, {
  CodexCancellation? cancellation,
  List<_LeafTemporary> temporaries = const <_LeafTemporary>[],
}) async {
  try {
    return await _runOperation<T>(
      service._native.owner,
      (callback, userData, out) {
        _leafTrace(symbol);
        return start(callback, userData, out);
      },
      decode,
      cancellation: cancellation,
      pin: service,
    );
  } finally {
    for (final temporary in temporaries.reversed) {
      temporary.destroy();
    }
  }
}

final class _LeafTemporary {
  _LeafTemporary(this.owner, this.slot, this.release, this.symbol);
  final _NativeContextOwner owner;
  final Pointer<Pointer<Void>> slot;
  final CodexReleaseHandleDart<Void> release;
  final String symbol;

  Pointer<Void> get value => slot.value;

  void destroy() {
    if (slot.value != nullptr && owner.open) {
      _releaseOwnedSlotOrDefer(owner, slot, release, symbol);
    } else {
      nativeMemory.free(slot);
    }
  }
}

/// Authentication operations and observable authentication state.
final class CodexAuthentication extends _LeafService {
  CodexAuthentication._(
    _NativeContextOwner owner,
    _HostLifetime lifetime,
    Pointer<Pointer<Void>> slot,
  ) : super(
          owner,
          lifetime,
          slot,
          _leafApi(owner).authenticationRelease,
          'codex_agent_authentication_release',
        ) {
    state = CodexObservableState<CodexAuthenticationState>(
      current: _readState,
      changes: _stateChanges,
    );
    isAuthenticatedState = CodexObservableState<bool>(
      current: _readIsAuthenticated,
      changes: _isAuthenticatedChanges,
    );
    isAuthenticatingState = CodexObservableState<bool>(
      current: _readIsAuthenticating,
      changes: _isAuthenticatingChanges,
    );
  }

  late final CodexObservableState<CodexAuthenticationState> state;
  late final CodexObservableState<bool> isAuthenticatedState;
  late final CodexObservableState<bool> isAuthenticatingState;

  Future<void> authenticate(
    CodexAuthenticationMethod method, {
    CodexCancellation? cancellation,
  }) {
    final temporary = _LeafCodec(_native.owner).authenticationMethod(method);
    final symbol = switch (method) {
      CodexApiKeyAuthentication() =>
        'codex_agent_authentication_authenticate_api_key',
      CodexChatGptBrowserAuthentication() =>
        'codex_agent_authentication_authenticate_chat_gpt_browser',
      CodexChatGptDeviceCodeAuthentication() =>
        'codex_agent_authentication_authenticate_chat_gpt_device_code',
    };
    final call = switch (method) {
      CodexApiKeyAuthentication() => _api.authenticationAuthenticateApiKey,
      CodexChatGptBrowserAuthentication() =>
        _api.authenticationAuthenticateChatGptBrowser,
      CodexChatGptDeviceCodeAuthentication() =>
        _api.authenticationAuthenticateChatGptDeviceCode,
    };
    return _leafOperation<void>(
      this,
      symbol,
      (callback, userData, out) => call(
        _native.owner.require(),
        _handle,
        temporary.value,
        callback,
        userData,
        out,
      ),
      (_) {},
      cancellation: cancellation,
      temporaries: <_LeafTemporary>[temporary],
    );
  }

  Future<void> cancel({CodexCancellation? cancellation}) =>
      _leafOperation<void>(
        this,
        'codex_agent_authentication_cancel',
        (callback, userData, out) => _api.authenticationCancel(
          _native.owner.require(),
          _handle,
          callback,
          userData,
          out,
        ),
        (_) {},
        cancellation: cancellation,
      );

  Future<void> signOut({CodexCancellation? cancellation}) =>
      _leafOperation<void>(
        this,
        'codex_agent_authentication_sign_out',
        (callback, userData, out) => _api.authenticationSignOut(
          _native.owner.require(),
          _handle,
          callback,
          userData,
          out,
        ),
        (_) {},
        cancellation: cancellation,
      );

  Future<CodexAuthenticationState> _readState() => _currentState(
        _native.owner,
        _handle,
        (context, handle, out) {
          _leafTrace('codex_agent_authentication_state_get');
          return _api.authenticationStateGet(context, handle, out);
        },
        _decodeAuthenticationState,
      );
  Stream<CodexAuthenticationState> _stateChanges() => _stateStream(
        _native.owner,
        (callback, userData, out) {
          _leafTrace('codex_agent_authentication_state_subscribe');
          return _api.authenticationStateSubscribe(
            _native.owner.require(),
            _handle,
            callback,
            userData,
            out,
          );
        },
        _decodeAuthenticationState,
        this,
        _subscriptions,
      );
  CodexAuthenticationState _decodeAuthenticationState(
    Pointer<CodexNativeSnapshot> snapshot,
  ) {
    _leafTrace('codex_agent_authentication_state_value');
    return _LeafCodec(_native.owner).authenticationState(
      _leafSnapshotHandle(
        _native.owner,
        'codex_agent_authentication_state_value',
        _api.authenticationStateValue,
        snapshot,
      ),
    );
  }

  Future<bool> _readIsAuthenticated() => _leafBooleanCurrent(
        this,
        'codex_agent_authentication_is_authenticated_get',
        _api.authenticationIsAuthenticatedGet,
      );
  Stream<bool> _isAuthenticatedChanges() => _leafBooleanChanges(
        this,
        'codex_agent_authentication_is_authenticated_subscribe',
        _api.authenticationIsAuthenticatedSubscribe,
      );
  Future<bool> _readIsAuthenticating() => _leafBooleanCurrent(
        this,
        'codex_agent_authentication_is_authenticating_get',
        _api.authenticationIsAuthenticatingGet,
      );
  Stream<bool> _isAuthenticatingChanges() => _leafBooleanChanges(
        this,
        'codex_agent_authentication_is_authenticating_subscribe',
        _api.authenticationIsAuthenticatingSubscribe,
      );
}

Future<bool> _leafBooleanCurrent(
  _LeafService service,
  String symbol,
  CodexGetSnapshotDart<Void> get,
) =>
    _currentState(
      service._native.owner,
      service._handle,
      (context, handle, out) {
        _leafTrace(symbol);
        return get(context, handle, out);
      },
      (snapshot) => _leafSnapshotBoolean(service, snapshot),
    );

Stream<bool> _leafBooleanChanges(
  _LeafService service,
  String symbol,
  CodexSubscribeDart<Void> subscribe,
) =>
    _stateStream(
      service._native.owner,
      (callback, userData, out) {
        _leafTrace(symbol);
        return subscribe(
          service._native.owner.require(),
          service._handle,
          callback,
          userData,
          out,
        );
      },
      (snapshot) => _leafSnapshotBoolean(service, snapshot),
      service,
      service._subscriptions,
    );

bool _leafSnapshotBoolean(
  _LeafService service,
  Pointer<CodexNativeSnapshot> snapshot,
) {
  final output = nativeMemory.allocate<Int32>(sizeOf<Int32>());
  try {
    _leafTrace('codex_agent_state_boolean_value');
    checkStatus(
      service._native.owner.api.stateBooleanValue(
        service._native.owner.require(),
        snapshot,
        output,
      ),
      'codex_agent_state_boolean_value',
    );
    return output.value != 0;
  } finally {
    nativeMemory.free(output);
  }
}

Pointer<Void> _leafSnapshotHandle(
  _NativeContextOwner owner,
  String symbol,
  _LeafSnapshotHandleDart call,
  Pointer<CodexNativeSnapshot> snapshot,
) {
  final slot = newHandleSlot<Void>();
  try {
    _leafTrace(symbol);
    checkStatus(call(owner.require(), snapshot, slot), symbol);
    if (slot.value == nullptr) {
      throw CodexException('$symbol returned an absent owned value');
    }
    return slot.value;
  } finally {
    nativeMemory.free(slot);
  }
}

Pointer<Void> _leafOperationHandle(
  _NativeContextOwner owner,
  String symbol,
  _LeafOperationHandleDart call,
  Pointer<CodexNativeOperation> operation,
) {
  final slot = newHandleSlot<Void>();
  try {
    _leafTrace(symbol);
    checkStatus(call(owner.require(), operation, slot), symbol);
    if (slot.value == nullptr) {
      throw CodexException('$symbol returned an absent owned value');
    }
    return slot.value;
  } finally {
    nativeMemory.free(slot);
  }
}

int _leafOperationCount(
  _NativeContextOwner owner,
  String symbol,
  _LeafOperationCountDart call,
  Pointer<CodexNativeOperation> operation,
) {
  final output = nativeMemory.allocate<Size>(sizeOf<Size>());
  try {
    _leafTrace(symbol);
    checkStatus(call(owner.require(), operation, output), symbol);
    return output.value;
  } finally {
    nativeMemory.free(output);
  }
}

Pointer<Void> _leafOperationAt(
  _NativeContextOwner owner,
  String symbol,
  _LeafOperationAtDart call,
  Pointer<CodexNativeOperation> operation,
  int index,
) {
  final slot = newHandleSlot<Void>();
  try {
    _leafTrace(symbol);
    checkStatus(call(owner.require(), operation, index, slot), symbol);
    if (slot.value == nullptr) {
      throw CodexException('$symbol returned an absent owned value');
    }
    return slot.value;
  } finally {
    nativeMemory.free(slot);
  }
}

String _leafOperationString(
  _NativeContextOwner owner,
  String symbol,
  _LeafOperationStringDart copy,
  Pointer<CodexNativeOperation> operation,
) {
  _leafTrace(symbol);
  return copyString(copy, owner.require(), operation);
}

/// Model catalog and resolution operations.
final class CodexModels extends _LeafService {
  CodexModels._(
    _NativeContextOwner owner,
    _HostLifetime lifetime,
    Pointer<Pointer<Void>> slot,
  ) : super(
          owner,
          lifetime,
          slot,
          _leafApi(owner).modelsRelease,
          'codex_agent_models_release',
        );

  Future<List<CodexModel>> list({CodexCancellation? cancellation}) =>
      _leafOperation<List<CodexModel>>(
        this,
        'codex_agent_models_list',
        (callback, userData, out) => _api.modelsList(
          _native.owner.require(),
          _handle,
          callback,
          userData,
          out,
        ),
        (operation) {
          final codec = _LeafCodec(_native.owner);
          return List<CodexModel>.unmodifiable(List<CodexModel>.generate(
            _leafOperationCount(
              _native.owner,
              'codex_agent_operation_models_count',
              _api.operationModelsCount,
              operation,
            ),
            (index) => codec.model(_leafOperationAt(
              _native.owner,
              'codex_agent_operation_model_at',
              _api.operationModelAt,
              operation,
              index,
            )),
          ));
        },
        cancellation: cancellation,
      );

  Future<CodexModel> resolve({
    CodexResolution resolution = CodexResolution.preferred,
    CodexCancellation? cancellation,
  }) =>
      _leafOperation<CodexModel>(
        this,
        'codex_agent_models_resolve',
        (callback, userData, out) => _api.modelsResolve(
          _native.owner.require(),
          _handle,
          resolution.value,
          callback,
          userData,
          out,
        ),
        (operation) => _LeafCodec(_native.owner).model(_leafOperationHandle(
          _native.owner,
          'codex_agent_operation_model',
          _api.operationModel,
          operation,
        )),
        cancellation: cancellation,
      );

  Future<String> resolveEffort(
    CodexModel model, {
    CodexResolution resolution = CodexResolution.preferred,
    CodexCancellation? cancellation,
  }) {
    final input = _LeafCodec(_native.owner).createModel(model);
    return _leafOperation<String>(
      this,
      'codex_agent_models_resolve_effort',
      (callback, userData, out) => _api.modelsResolveEffort(
        _native.owner.require(),
        _handle,
        input.value,
        resolution.value,
        callback,
        userData,
        out,
      ),
      (operation) => _leafOperationString(
        _native.owner,
        'codex_agent_operation_string_copy',
        _api.operationStringCopy,
        operation,
      ),
      cancellation: cancellation,
      temporaries: <_LeafTemporary>[input],
    );
  }

  Future<CodexServiceTier?> resolveServiceTier(
    CodexModel model, {
    CodexResolution resolution = CodexResolution.preferred,
    CodexCancellation? cancellation,
  }) {
    final input = _LeafCodec(_native.owner).createModel(model);
    return _leafOperation<CodexServiceTier?>(
      this,
      'codex_agent_models_resolve_service_tier',
      (callback, userData, out) => _api.modelsResolveServiceTier(
        _native.owner.require(),
        _handle,
        input.value,
        resolution.value,
        callback,
        userData,
        out,
      ),
      (operation) {
        final present = nativeMemory.allocate<Int32>(sizeOf<Int32>());
        try {
          _leafTrace('codex_agent_operation_has_service_tier');
          checkStatus(
            _api.operationHasServiceTier(
              _native.owner.require(),
              operation,
              present,
            ),
            'codex_agent_operation_has_service_tier',
          );
          if (present.value == 0) return null;
          return _LeafCodec(_native.owner).serviceTier(_leafOperationHandle(
            _native.owner,
            'codex_agent_operation_service_tier',
            _api.operationServiceTier,
            operation,
          ));
        } finally {
          nativeMemory.free(present);
        }
      },
      cancellation: cancellation,
      temporaries: <_LeafTemporary>[input],
    );
  }
}

/// Installed skills and skill-package operations.
final class CodexSkills extends _LeafService {
  CodexSkills._(_NativeContextOwner owner, _HostLifetime lifetime,
      Pointer<Pointer<Void>> slot)
      : super(owner, lifetime, slot, _leafApi(owner).skillsRelease,
            'codex_agent_skills_release');

  bool get isAvailable => _availability(
        'codex_agent_skills_is_available',
        _api.skillsIsAvailable,
      );

  Future<CodexSkillCatalog> list({
    bool forceReload = false,
    CodexCancellation? cancellation,
  }) =>
      _leafOperation<CodexSkillCatalog>(
        this,
        'codex_agent_skills_list',
        (callback, userData, out) => _api.skillsList(
          _native.owner.require(),
          _handle,
          forceReload ? 1 : 0,
          callback,
          userData,
          out,
        ),
        (operation) => _LeafCodec(_native.owner).skillCatalog(
          _leafOperationHandle(
            _native.owner,
            'codex_agent_operation_skill_catalog',
            _api.operationSkillCatalog,
            operation,
          ),
        ),
        cancellation: cancellation,
      );

  Future<CodexSkillChunk> read(
    String path, {
    int offset = 0,
    CodexCancellation? cancellation,
  }) async {
    final nativePath = NativeString(path);
    try {
      return await _leafOperation<CodexSkillChunk>(
        this,
        'codex_agent_skills_read',
        (callback, userData, out) => _api.skillsRead(
          _native.owner.require(),
          _handle,
          nativePath.view,
          offset,
          callback,
          userData,
          out,
        ),
        (operation) => _LeafCodec(_native.owner).skillChunk(
          _leafOperationHandle(
            _native.owner,
            'codex_agent_operation_skill_chunk',
            _api.operationSkillChunk,
            operation,
          ),
        ),
        cancellation: cancellation,
      );
    } finally {
      nativePath.close();
    }
  }

  Future<CodexSkill> install(
    String directory,
    CodexInstallationScope scope, {
    CodexCancellation? cancellation,
  }) async {
    final nativeDirectory = NativeString(directory);
    try {
      return await _leafOperation<CodexSkill>(
        this,
        'codex_agent_skills_install',
        (callback, userData, out) => _api.skillsInstall(
          _native.owner.require(),
          _handle,
          nativeDirectory.view,
          scope.value,
          callback,
          userData,
          out,
        ),
        (operation) => _LeafCodec(_native.owner).skill(_leafOperationHandle(
          _native.owner,
          'codex_agent_operation_skill',
          _api.operationSkill,
          operation,
        )),
        cancellation: cancellation,
      );
    } finally {
      nativeDirectory.close();
    }
  }

  Future<void> uninstall(
    CodexSkill skill, {
    CodexCancellation? cancellation,
  }) {
    final input = _LeafCodec(_native.owner).createSkill(skill);
    return _leafOperation<void>(
      this,
      'codex_agent_skills_uninstall',
      (callback, userData, out) => _api.skillsUninstall(
        _native.owner.require(),
        _handle,
        input.value,
        callback,
        userData,
        out,
      ),
      (_) {},
      cancellation: cancellation,
      temporaries: <_LeafTemporary>[input],
    );
  }
}

/// Installed hook catalog operations.
final class CodexHooks extends _LeafService {
  CodexHooks._(_NativeContextOwner owner, _HostLifetime lifetime,
      Pointer<Pointer<Void>> slot)
      : super(owner, lifetime, slot, _leafApi(owner).hooksRelease,
            'codex_agent_hooks_release');

  bool get isAvailable => _availability(
        'codex_agent_hooks_is_available',
        _api.hooksIsAvailable,
      );

  Future<CodexHookCatalog> list({CodexCancellation? cancellation}) =>
      _leafOperation<CodexHookCatalog>(
        this,
        'codex_agent_hooks_list',
        (callback, userData, out) => _api.hooksList(
          _native.owner.require(),
          _handle,
          callback,
          userData,
          out,
        ),
        (operation) => _LeafCodec(_native.owner).hookCatalog(
          _leafOperationHandle(
            _native.owner,
            'codex_agent_operation_hook_catalog',
            _api.operationHookCatalog,
            operation,
          ),
        ),
        cancellation: cancellation,
      );

  Future<CodexHook> install(
    String directory,
    CodexInstallationScope scope, {
    CodexCancellation? cancellation,
  }) async {
    final nativeDirectory = NativeString(directory);
    try {
      return await _leafOperation<CodexHook>(
        this,
        'codex_agent_hooks_install',
        (callback, userData, out) => _api.hooksInstall(
          _native.owner.require(),
          _handle,
          nativeDirectory.view,
          scope.value,
          callback,
          userData,
          out,
        ),
        (operation) => _LeafCodec(_native.owner).hook(_leafOperationHandle(
          _native.owner,
          'codex_agent_operation_hook',
          _api.operationHook,
          operation,
        )),
        cancellation: cancellation,
      );
    } finally {
      nativeDirectory.close();
    }
  }

  Future<void> trust(CodexHook hook, {CodexCancellation? cancellation}) =>
      _withHook('codex_agent_hooks_trust', _api.hooksTrust, hook, cancellation);

  Future<void> uninstall(CodexHook hook, {CodexCancellation? cancellation}) =>
      _withHook('codex_agent_hooks_uninstall', _api.hooksUninstall, hook,
          cancellation);

  Future<void> _withHook(
    String symbol,
    _LeafHandleOperationDart call,
    CodexHook hook,
    CodexCancellation? cancellation,
  ) {
    final input = _LeafCodec(_native.owner).createHook(hook);
    return _leafOperation<void>(
      this,
      symbol,
      (callback, userData, out) => call(
        _native.owner.require(),
        _handle,
        input.value,
        callback,
        userData,
        out,
      ),
      (_) {},
      cancellation: cancellation,
      temporaries: <_LeafTemporary>[input],
    );
  }
}

/// Plugin discovery, inspection, installation, and removal.
final class CodexPlugins extends _LeafService {
  CodexPlugins._(_NativeContextOwner owner, _HostLifetime lifetime,
      Pointer<Pointer<Void>> slot)
      : super(owner, lifetime, slot, _leafApi(owner).pluginsRelease,
            'codex_agent_plugins_release');

  bool get isAvailable => _availability(
        'codex_agent_plugins_is_available',
        _api.pluginsIsAvailable,
      );

  Future<CodexPluginCatalog> list({
    bool forceReload = false,
    CodexCancellation? cancellation,
  }) =>
      _leafOperation<CodexPluginCatalog>(
        this,
        'codex_agent_plugins_list',
        (callback, userData, out) => _api.pluginsList(
          _native.owner.require(),
          _handle,
          forceReload ? 1 : 0,
          callback,
          userData,
          out,
        ),
        (operation) => _LeafCodec(_native.owner).pluginCatalog(
          _leafOperationHandle(
            _native.owner,
            'codex_agent_operation_plugin_catalog',
            _api.operationPluginCatalog,
            operation,
          ),
        ),
        cancellation: cancellation,
      );

  Future<CodexPluginDetail> read(
    CodexPluginReference plugin, {
    CodexCancellation? cancellation,
  }) =>
      _withPlugin<CodexPluginDetail>(
        'codex_agent_plugins_read',
        _api.pluginsRead,
        plugin,
        (operation) => _LeafCodec(_native.owner).pluginDetail(
          _leafOperationHandle(
            _native.owner,
            'codex_agent_operation_plugin_detail',
            _api.operationPluginDetail,
            operation,
          ),
        ),
        cancellation,
      );

  Future<CodexPluginInstallResult> install(
    CodexPluginReference plugin, {
    CodexCancellation? cancellation,
  }) =>
      _withPlugin<CodexPluginInstallResult>(
        'codex_agent_plugins_install',
        _api.pluginsInstall,
        plugin,
        (operation) => _LeafCodec(_native.owner).pluginInstallResult(
          _leafOperationHandle(
            _native.owner,
            'codex_agent_operation_plugin_install_result',
            _api.operationPluginInstallResult,
            operation,
          ),
        ),
        cancellation,
      );

  Future<void> uninstall(
    CodexPluginReference plugin, {
    CodexCancellation? cancellation,
  }) =>
      _withPlugin<void>(
        'codex_agent_plugins_uninstall',
        _api.pluginsUninstall,
        plugin,
        (_) {},
        cancellation,
      );

  Future<T> _withPlugin<T>(
    String symbol,
    _LeafHandleOperationDart call,
    CodexPluginReference plugin,
    T Function(Pointer<CodexNativeOperation>) decode,
    CodexCancellation? cancellation,
  ) {
    final input = _LeafCodec(_native.owner).createPluginReference(plugin);
    return _leafOperation<T>(
      this,
      symbol,
      (callback, userData, out) => call(
        _native.owner.require(),
        _handle,
        input.value,
        callback,
        userData,
        out,
      ),
      decode,
      cancellation: cancellation,
      temporaries: <_LeafTemporary>[input],
    );
  }
}

/// Connector discovery operations.
final class CodexConnectors extends _LeafService {
  CodexConnectors._(_NativeContextOwner owner, _HostLifetime lifetime,
      Pointer<Pointer<Void>> slot)
      : super(owner, lifetime, slot, _leafApi(owner).connectorsRelease,
            'codex_agent_connectors_release');

  bool get isAvailable => _availability(
        'codex_agent_connectors_is_available',
        _api.connectorsIsAvailable,
      );

  Future<List<CodexConnector>> list({
    bool forceReload = false,
    CodexCancellation? cancellation,
  }) =>
      _leafOperation<List<CodexConnector>>(
        this,
        'codex_agent_connectors_list',
        (callback, userData, out) => _api.connectorsList(
          _native.owner.require(),
          _handle,
          forceReload ? 1 : 0,
          callback,
          userData,
          out,
        ),
        (operation) {
          final codec = _LeafCodec(_native.owner);
          return List<CodexConnector>.unmodifiable(
            List<CodexConnector>.generate(
              _leafOperationCount(
                _native.owner,
                'codex_agent_operation_connectors_count',
                _api.operationConnectorsCount,
                operation,
              ),
              (index) => codec.connector(_leafOperationAt(
                _native.owner,
                'codex_agent_operation_connector_at',
                _api.operationConnectorAt,
                operation,
                index,
              )),
            ),
          );
        },
        cancellation: cancellation,
      );
}

/// MCP server configuration and catalog operations.
final class CodexMcpServers extends _LeafService {
  CodexMcpServers._(_NativeContextOwner owner, _HostLifetime lifetime,
      Pointer<Pointer<Void>> slot)
      : super(owner, lifetime, slot, _leafApi(owner).mcpServersRelease,
            'codex_agent_mcp_servers_release');

  bool get isAvailable => _availability(
        'codex_agent_mcp_servers_is_available',
        _api.mcpServersIsAvailable,
      );

  Future<List<CodexMcpServer>> list({CodexCancellation? cancellation}) =>
      _leafOperation<List<CodexMcpServer>>(
        this,
        'codex_agent_mcp_servers_list',
        (callback, userData, out) => _api.mcpServersList(
          _native.owner.require(),
          _handle,
          callback,
          userData,
          out,
        ),
        (operation) {
          final codec = _LeafCodec(_native.owner);
          return List<CodexMcpServer>.unmodifiable(
            List<CodexMcpServer>.generate(
              _leafOperationCount(
                _native.owner,
                'codex_agent_operation_mcp_servers_count',
                _api.operationMcpServersCount,
                operation,
              ),
              (index) => codec.mcpServer(_leafOperationAt(
                _native.owner,
                'codex_agent_operation_mcp_server_at',
                _api.operationMcpServerAt,
                operation,
                index,
              )),
            ),
          );
        },
        cancellation: cancellation,
      );

  Future<CodexMcpServer> add(
    CodexMcpServerConfiguration configuration, {
    CodexCancellation? cancellation,
  }) {
    final input =
        _LeafCodec(_native.owner).createMcpConfiguration(configuration);
    return _leafOperation<CodexMcpServer>(
      this,
      'codex_agent_mcp_servers_add',
      (callback, userData, out) => _api.mcpServersAdd(
        _native.owner.require(),
        _handle,
        input.value,
        callback,
        userData,
        out,
      ),
      (operation) => _LeafCodec(_native.owner).mcpServer(
        _leafOperationHandle(
          _native.owner,
          'codex_agent_operation_mcp_server',
          _api.operationMcpServer,
          operation,
        ),
      ),
      cancellation: cancellation,
      temporaries: <_LeafTemporary>[input],
    );
  }

  Future<void> remove(
    CodexMcpServer server, {
    CodexCancellation? cancellation,
  }) {
    final input = _LeafCodec(_native.owner).createMcpServer(server);
    return _leafOperation<void>(
      this,
      'codex_agent_mcp_servers_remove',
      (callback, userData, out) => _api.mcpServersRemove(
        _native.owner.require(),
        _handle,
        input.value,
        callback,
        userData,
        out,
      ),
      (_) {},
      cancellation: cancellation,
      temporaries: <_LeafTemporary>[input],
    );
  }
}

/// Authorization lifecycle for connector and MCP integrations.
final class CodexIntegrationAuthorization extends _LeafService {
  CodexIntegrationAuthorization._(
    _NativeContextOwner owner,
    _HostLifetime lifetime,
    Pointer<Pointer<Void>> slot,
  ) : super(
          owner,
          lifetime,
          slot,
          _leafApi(owner).integrationAuthorizationRelease,
          'codex_agent_integration_authorization_release',
        ) {
    state = CodexObservableState<CodexIntegrationAuthorizationState>(
      current: _readState,
      changes: _stateChanges,
    );
    activeState = CodexObservableState<CodexIntegration?>(
      current: _readActive,
      changes: _activeChanges,
    );
    isAuthorizingState = CodexObservableState<bool>(
      current: _readIsAuthorizing,
      changes: _isAuthorizingChanges,
    );
  }

  late final CodexObservableState<CodexIntegrationAuthorizationState> state;
  late final CodexObservableState<CodexIntegration?> activeState;
  late final CodexObservableState<bool> isAuthorizingState;

  Future<void> authorize(
    CodexIntegration integration, {
    CodexCancellation? cancellation,
  }) {
    final input = _LeafCodec(_native.owner).createIntegration(integration);
    return _leafOperation<void>(
      this,
      'codex_agent_integration_authorization_authorize',
      (callback, userData, out) => _api.integrationAuthorizationAuthorize(
        _native.owner.require(),
        _handle,
        input.value,
        callback,
        userData,
        out,
      ),
      (_) {},
      cancellation: cancellation,
      temporaries: <_LeafTemporary>[input],
    );
  }

  Future<void> cancel({CodexCancellation? cancellation}) =>
      _leafOperation<void>(
        this,
        'codex_agent_integration_authorization_cancel',
        (callback, userData, out) => _api.integrationAuthorizationCancel(
          _native.owner.require(),
          _handle,
          callback,
          userData,
          out,
        ),
        (_) {},
        cancellation: cancellation,
      );

  Future<CodexIntegrationAuthorizationState> _readState() => _currentState(
        _native.owner,
        _handle,
        (context, handle, out) {
          _leafTrace('codex_agent_integration_authorization_state_get');
          return _api.integrationAuthorizationStateGet(context, handle, out);
        },
        _decodeState,
      );
  Stream<CodexIntegrationAuthorizationState> _stateChanges() => _stateStream(
        _native.owner,
        (callback, userData, out) {
          _leafTrace('codex_agent_integration_authorization_state_subscribe');
          return _api.integrationAuthorizationStateSubscribe(
              _native.owner.require(), _handle, callback, userData, out);
        },
        _decodeState,
        this,
        _subscriptions,
      );
  CodexIntegrationAuthorizationState _decodeState(
          Pointer<CodexNativeSnapshot> snapshot) =>
      _LeafCodec(_native.owner).integrationAuthorizationState(
        _leafSnapshotHandle(
          _native.owner,
          'codex_agent_integration_authorization_state_value',
          _api.integrationAuthorizationStateValue,
          snapshot,
        ),
      );

  Future<CodexIntegration?> _readActive() => _currentState(
        _native.owner,
        _handle,
        (context, handle, out) {
          _leafTrace('codex_agent_integration_authorization_active_get');
          return _api.integrationAuthorizationActiveGet(context, handle, out);
        },
        _decodeActive,
      );
  Stream<CodexIntegration?> _activeChanges() => _stateStream(
        _native.owner,
        (callback, userData, out) {
          _leafTrace('codex_agent_integration_authorization_active_subscribe');
          return _api.integrationAuthorizationActiveSubscribe(
              _native.owner.require(), _handle, callback, userData, out);
        },
        _decodeActive,
        this,
        _subscriptions,
      );
  CodexIntegration? _decodeActive(Pointer<CodexNativeSnapshot> snapshot) {
    final present = nativeMemory.allocate<Int32>(sizeOf<Int32>());
    try {
      _leafTrace('codex_agent_integration_authorization_active_has_value');
      checkStatus(
        _api.integrationAuthorizationActiveHasValue(
            _native.owner.require(), snapshot, present),
        'codex_agent_integration_authorization_active_has_value',
      );
      if (present.value == 0) return null;
      _leafTrace('codex_agent_integration_authorization_active_value');
      return _LeafCodec(_native.owner).integration(_leafSnapshotHandle(
        _native.owner,
        'codex_agent_integration_authorization_active_value',
        _api.integrationAuthorizationActiveValue,
        snapshot,
      ));
    } finally {
      nativeMemory.free(present);
    }
  }

  Future<bool> _readIsAuthorizing() => _leafBooleanCurrent(
        this,
        'codex_agent_integration_authorization_is_authorizing_get',
        _api.integrationAuthorizationIsAuthorizingGet,
      );
  Stream<bool> _isAuthorizingChanges() => _leafBooleanChanges(
        this,
        'codex_agent_integration_authorization_is_authorizing_subscribe',
        _api.integrationAuthorizationIsAuthorizingSubscribe,
      );
}

/// Pending approval and elicitation operations and state.
final class CodexInteractions extends _LeafService {
  CodexInteractions._(
    _NativeContextOwner owner,
    _HostLifetime lifetime,
    Pointer<Pointer<Void>> slot,
  ) : super(
          owner,
          lifetime,
          slot,
          _leafApi(owner).interactionsRelease,
          'codex_agent_interactions_release',
        ) {
    state = CodexObservableState<CodexInteractionState>(
      current: _readState,
      changes: _stateChanges,
    );
    approvalsState = CodexObservableState<List<CodexPendingApproval>>(
      current: _readApprovals,
      changes: _approvalsChanges,
    );
    elicitationsState = CodexObservableState<List<CodexPendingElicitation>>(
      current: _readElicitations,
      changes: _elicitationsChanges,
    );
  }

  late final CodexObservableState<CodexInteractionState> state;
  late final CodexObservableState<List<CodexPendingApproval>> approvalsState;
  late final CodexObservableState<List<CodexPendingElicitation>>
      elicitationsState;
  final Map<CodexPendingInteraction, _LeafTemporary> _pending =
      Map<CodexPendingInteraction, _LeafTemporary>.identity();

  Future<void> openUrl(
    CodexPendingElicitation elicitation, {
    CodexCancellation? cancellation,
  }) =>
      _withPending<void>(
        elicitation,
        'codex_agent_interactions_open_url',
        (native, callback, userData, out) => _api.interactionsOpenUrl(
          _native.owner.require(),
          _handle,
          native,
          callback,
          userData,
          out,
        ),
        cancellation,
      );

  Future<void> resolveApproval(
    CodexPendingApproval approval,
    CodexApprovalDecision decision, {
    CodexCancellation? cancellation,
  }) =>
      _withPending<void>(
        approval,
        'codex_agent_interactions_resolve_approval',
        (native, callback, userData, out) => _api.interactionsResolveApproval(
          _native.owner.require(),
          _handle,
          native,
          decision.value,
          callback,
          userData,
          out,
        ),
        cancellation,
      );

  Future<void> resolveElicitation(
    CodexPendingElicitation elicitation,
    CodexElicitationResponse response, {
    CodexCancellation? cancellation,
  }) {
    final pending = _requirePending(elicitation);
    final nativeResponse =
        _LeafCodec(_native.owner).createElicitationResponse(response);
    return _leafOperation<void>(
      this,
      'codex_agent_interactions_resolve_elicitation',
      (callback, userData, out) => _api.interactionsResolveElicitation(
        _native.owner.require(),
        _handle,
        pending,
        nativeResponse.value,
        callback,
        userData,
        out,
      ),
      (_) {},
      cancellation: cancellation,
      temporaries: <_LeafTemporary>[nativeResponse],
    );
  }

  Future<T> _withPending<T>(
    CodexPendingInteraction pending,
    String symbol,
    int Function(
      Pointer<Void>,
      Pointer<NativeFunction<OperationCallbackNative>>,
      Pointer<Void>,
      Pointer<Pointer<CodexNativeOperation>>,
    ) start,
    CodexCancellation? cancellation,
  ) =>
      _leafOperation<T>(
        this,
        symbol,
        (callback, userData, out) =>
            start(_requirePending(pending), callback, userData, out),
        (_) => null as T,
        cancellation: cancellation,
      );

  Pointer<Void> _requirePending(CodexPendingInteraction value) {
    final retained = _pending[value];
    if (retained == null || retained.value == nullptr) {
      throw ArgumentError.value(
        value,
        'interaction',
        'must be the exact live value emitted by this service',
      );
    }
    return retained.value;
  }

  T _remember<T extends CodexPendingInteraction>(
    T value,
    Pointer<Void> native,
    String destroySymbol,
  ) {
    final codec = _LeafCodec(_native.owner);
    final temporary = codec.owned(native, destroySymbol);
    _pending[value] = temporary;
    return value;
  }

  Future<CodexInteractionState> _readState() => _currentState(
        _native.owner,
        _handle,
        (context, handle, out) {
          _leafTrace('codex_agent_interactions_state_get');
          return _api.interactionsStateGet(context, handle, out);
        },
        _decodeState,
      );
  Stream<CodexInteractionState> _stateChanges() => _stateStream(
        _native.owner,
        (callback, userData, out) {
          _leafTrace('codex_agent_interactions_state_subscribe');
          return _api.interactionsStateSubscribe(
              _native.owner.require(), _handle, callback, userData, out);
        },
        _decodeState,
        this,
        _subscriptions,
      );
  CodexInteractionState _decodeState(Pointer<CodexNativeSnapshot> snapshot) {
    final native = _leafSnapshotHandle(
      _native.owner,
      'codex_agent_interactions_state_value',
      _api.interactionsStateValue,
      snapshot,
    );
    return _LeafCodec(_native.owner).interactionState(
      native,
      _remember,
    );
  }

  Future<List<CodexPendingApproval>> _readApprovals() => _currentState(
        _native.owner,
        _handle,
        (context, handle, out) {
          _leafTrace('codex_agent_interactions_approvals_get');
          return _api.interactionsApprovalsGet(context, handle, out);
        },
        _decodeApprovals,
      );
  Stream<List<CodexPendingApproval>> _approvalsChanges() => _stateStream(
        _native.owner,
        (callback, userData, out) {
          _leafTrace('codex_agent_interactions_approvals_subscribe');
          return _api.interactionsApprovalsSubscribe(
              _native.owner.require(), _handle, callback, userData, out);
        },
        _decodeApprovals,
        this,
        _subscriptions,
      );
  List<CodexPendingApproval> _decodeApprovals(
      Pointer<CodexNativeSnapshot> snapshot) {
    final count = _leafSnapshotCount(
      _native.owner,
      'codex_agent_interactions_approvals_count',
      _api.interactionsApprovalsCount,
      snapshot,
    );
    final codec = _LeafCodec(_native.owner);
    return List<CodexPendingApproval>.unmodifiable(
      List<CodexPendingApproval>.generate(count, (index) {
        final handle = _leafSnapshotAt(
          _native.owner,
          'codex_agent_interactions_approvals_at',
          _api.interactionsApprovalsAt,
          snapshot,
          index,
        );
        return _remember(
          codec.pendingApproval(handle),
          handle,
          'codex_agent_pending_approval_destroy',
        );
      }),
    );
  }

  Future<List<CodexPendingElicitation>> _readElicitations() => _currentState(
        _native.owner,
        _handle,
        (context, handle, out) {
          _leafTrace('codex_agent_interactions_elicitations_get');
          return _api.interactionsElicitationsGet(context, handle, out);
        },
        _decodeElicitations,
      );
  Stream<List<CodexPendingElicitation>> _elicitationsChanges() => _stateStream(
        _native.owner,
        (callback, userData, out) {
          _leafTrace('codex_agent_interactions_elicitations_subscribe');
          return _api.interactionsElicitationsSubscribe(
              _native.owner.require(), _handle, callback, userData, out);
        },
        _decodeElicitations,
        this,
        _subscriptions,
      );
  List<CodexPendingElicitation> _decodeElicitations(
      Pointer<CodexNativeSnapshot> snapshot) {
    final count = _leafSnapshotCount(
      _native.owner,
      'codex_agent_interactions_elicitations_count',
      _api.interactionsElicitationsCount,
      snapshot,
    );
    final codec = _LeafCodec(_native.owner);
    return List<CodexPendingElicitation>.unmodifiable(
      List<CodexPendingElicitation>.generate(count, (index) {
        final handle = _leafSnapshotAt(
          _native.owner,
          'codex_agent_interactions_elicitations_at',
          _api.interactionsElicitationsAt,
          snapshot,
          index,
        );
        return _remember(
          codec.pendingElicitation(handle),
          handle,
          'codex_agent_pending_elicitation_destroy',
        );
      }),
    );
  }

  @override
  Future<void> close() async {
    await _subscriptions.close();
    for (final retained in _pending.values.toSet()) {
      retained.destroy();
    }
    _pending.clear();
    await super.close();
  }
}

int _leafSnapshotCount(
  _NativeContextOwner owner,
  String symbol,
  _LeafSnapshotCountDart call,
  Pointer<CodexNativeSnapshot> snapshot,
) {
  final output = nativeMemory.allocate<Size>(sizeOf<Size>());
  try {
    _leafTrace(symbol);
    checkStatus(call(owner.require(), snapshot, output), symbol);
    return output.value;
  } finally {
    nativeMemory.free(output);
  }
}

Pointer<Void> _leafSnapshotAt(
  _NativeContextOwner owner,
  String symbol,
  _LeafSnapshotAtDart call,
  Pointer<CodexNativeSnapshot> snapshot,
  int index,
) {
  final slot = newHandleSlot<Void>();
  try {
    _leafTrace(symbol);
    checkStatus(call(owner.require(), snapshot, index, slot), symbol);
    if (slot.value == nullptr) {
      throw CodexException('$symbol returned an absent owned value');
    }
    return slot.value;
  } finally {
    nativeMemory.free(slot);
  }
}

Pointer<Pointer<Void>> _acquireAgentServiceSlot(
  CodexAgent agent,
  String symbol,
  _LeafAgentServiceDart call,
) {
  final owner = agent._native.owner;
  final slot = newHandleSlot<Void>();
  try {
    _leafTrace(symbol);
    checkStatus(
      call(owner.require(), agent._native.requireHandle('CodexAgent'), slot),
      symbol,
    );
    if (slot.value == nullptr) {
      throw CodexException('$symbol returned an absent owned value');
    }
    return slot;
  } catch (_) {
    nativeMemory.free(slot);
    rethrow;
  }
}

({
  CodexAuthentication authentication,
  CodexInteractions interactions,
  CodexIntegrationAuthorization integrationAuthorization,
  CodexModels models,
  CodexSkills skills,
  CodexHooks hooks,
  CodexPlugins plugins,
  CodexConnectors connectors,
  CodexMcpServers mcpServers,
}) createLeafServicesForTesting(CodexAgent agent) {
  return (
    authentication: agent.authentication,
    interactions: agent.interactions,
    integrationAuthorization: agent.integrationAuthorization,
    models: agent.models,
    skills: agent.skills,
    hooks: agent.hooks,
    plugins: agent.plugins,
    connectors: agent.connectors,
    mcpServers: agent.mcpServers,
  );
}

typedef _LeafValueIntNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Int32>,
);
typedef _LeafValueIntDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Int32>,
);
typedef _LeafValueInt64Native = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Int64>,
);
typedef _LeafValueInt64Dart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Int64>,
);
typedef _LeafValueSizeNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Size>,
);
typedef _LeafValueSizeDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Size>,
);
typedef _LeafValueHandleNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Pointer<Void>>,
);
typedef _LeafValueHandleDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Pointer<Void>>,
);
typedef _LeafValueAtNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Size,
  Pointer<Pointer<Void>>,
);
typedef _LeafValueAtDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  int,
  Pointer<Pointer<Void>>,
);
typedef _LeafValueStringNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Uint8>,
  Size,
  Pointer<Size>,
);
typedef _LeafValueStringDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Uint8>,
  int,
  Pointer<Size>,
);
typedef _LeafValueStringAtNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Size,
  Pointer<Uint8>,
  Size,
  Pointer<Size>,
);
typedef _LeafValueStringAtDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  int,
  Pointer<Uint8>,
  int,
  Pointer<Size>,
);
typedef _LeafValueOptionalInt64Native = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Int32>,
  Pointer<Int64>,
);
typedef _LeafValueOptionalInt64Dart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Int32>,
  Pointer<Int64>,
);
typedef _LeafValueOptionalIntNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Int32>,
  Pointer<Int32>,
);
typedef _LeafValueOptionalIntDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Int32>,
  Pointer<Int32>,
);
typedef _LeafValueOptionalDoubleNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Int32>,
  Pointer<Double>,
);
typedef _LeafValueOptionalDoubleDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Int32>,
  Pointer<Double>,
);
typedef _LeafValueIndexIntNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Size,
  Pointer<Int32>,
);
typedef _LeafValueIndexIntDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  int,
  Pointer<Int32>,
);
typedef _LeafContextOutNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Pointer<Void>>,
);
typedef _LeafContextOutDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Pointer<Void>>,
);
typedef _LeafContextStringOutNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  Pointer<Pointer<Void>>,
);
typedef _LeafContextStringOutDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  Pointer<Pointer<Void>>,
);
typedef _LeafContextHandleOutNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Pointer<Void>>,
);
typedef _LeafContextHandleOutDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Pointer<Void>>,
);
typedef _LeafServiceTierCreateNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  Pointer<Pointer<Void>>,
);
typedef _LeafServiceTierCreateDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  Pointer<Pointer<Void>>,
);
typedef _LeafModelCreateNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  Size,
  Pointer<CodexStringView>,
  Int32,
  Pointer<Pointer<Void>>,
  Size,
  Int32,
  Pointer<CodexStringView>,
  Pointer<Pointer<Void>>,
);
typedef _LeafModelCreateDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  int,
  Pointer<CodexStringView>,
  int,
  Pointer<Pointer<Void>>,
  int,
  int,
  Pointer<CodexStringView>,
  Pointer<Pointer<Void>>,
);
typedef _LeafPluginReferenceCreateNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  Int32,
  Pointer<CodexStringView>,
  Int32,
  Pointer<CodexStringView>,
  Pointer<Pointer<Void>>,
);
typedef _LeafPluginReferenceCreateDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  int,
  Pointer<CodexStringView>,
  int,
  Pointer<CodexStringView>,
  Pointer<Pointer<Void>>,
);
typedef _LeafSkillCreateNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  Int32,
  Int32,
  Int32,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  Size,
  Int32,
  Int32,
  Int32,
  Pointer<Pointer<Void>>,
);
typedef _LeafSkillCreateDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  int,
  int,
  int,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  int,
  int,
  int,
  int,
  Pointer<Pointer<Void>>,
);
typedef _LeafConnectorCreateNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  Int32,
  Pointer<CodexStringView>,
  Int32,
  Int32,
  Pointer<CodexStringView>,
  Size,
  Pointer<Pointer<Void>>,
);
typedef _LeafConnectorCreateDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  int,
  Pointer<CodexStringView>,
  int,
  int,
  Pointer<CodexStringView>,
  int,
  Pointer<Pointer<Void>>,
);
typedef _LeafContextStringIntOutNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  Int32,
  Pointer<Pointer<Void>>,
);
typedef _LeafContextStringIntOutDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  int,
  Pointer<Pointer<Void>>,
);
typedef _LeafContextTwoStringsOutNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  Pointer<Pointer<Void>>,
);
typedef _LeafContextTwoStringsOutDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  Pointer<Pointer<Void>>,
);
typedef _LeafHookCreateNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  Int32,
  Pointer<CodexStringView>,
  Pointer<Void>,
  Int32,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  Int64,
  Int32,
  Int32,
  Pointer<CodexStringView>,
  Int32,
  Pointer<CodexStringView>,
  Int32,
  Pointer<CodexStringView>,
  Int32,
  Int32,
  Int32,
  Pointer<Pointer<Void>>,
);
typedef _LeafHookCreateDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  int,
  Pointer<CodexStringView>,
  Pointer<Void>,
  int,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  int,
  int,
  int,
  Pointer<CodexStringView>,
  int,
  Pointer<CodexStringView>,
  int,
  Pointer<CodexStringView>,
  int,
  int,
  int,
  Pointer<Pointer<Void>>,
);
typedef _LeafMcpEnvironmentCreateNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  Int32,
  Int32,
  Pointer<Pointer<Void>>,
);
typedef _LeafMcpEnvironmentCreateDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  int,
  int,
  Pointer<Pointer<Void>>,
);
typedef _LeafMcpOauthCreateNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Int32,
  Pointer<CodexStringView>,
  Int32,
  Int32,
  Pointer<Pointer<Void>>,
);
typedef _LeafMcpOauthCreateDart = int Function(
  Pointer<CodexNativeContext>,
  int,
  Pointer<CodexStringView>,
  int,
  int,
  Pointer<Pointer<Void>>,
);
typedef _LeafMcpToolCreateNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Int32,
  Int32,
  Pointer<Pointer<Void>>,
);
typedef _LeafMcpToolCreateDart = int Function(
  Pointer<CodexNativeContext>,
  int,
  int,
  Pointer<Pointer<Void>>,
);
typedef _LeafMcpHttpCreateNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  Int32,
  Pointer<CodexStringView>,
  Int32,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  Size,
  Int32,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  Size,
  Int32,
  Pointer<CodexStringView>,
  Pointer<Pointer<Void>>,
);
typedef _LeafMcpHttpCreateDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  int,
  Pointer<CodexStringView>,
  int,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  int,
  int,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  int,
  int,
  Pointer<CodexStringView>,
  Pointer<Pointer<Void>>,
);
typedef _LeafMcpStdioCreateNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  Size,
  Int32,
  Pointer<CodexStringView>,
  Int32,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  Size,
  Pointer<Pointer<Void>>,
  Size,
  Pointer<Pointer<Void>>,
);
typedef _LeafMcpStdioCreateDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  int,
  int,
  Pointer<CodexStringView>,
  int,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  int,
  Pointer<Pointer<Void>>,
  int,
  Pointer<Pointer<Void>>,
);
typedef _LeafMcpConfigurationCreateNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  Pointer<Void>,
  Int32,
  Int32,
  Pointer<CodexStringView>,
  Int32,
  Int32,
  Int32,
  Int32,
  Pointer<Int32>,
  Size,
  Int32,
  Double,
  Int32,
  Double,
  Int32,
  Int32,
  Int32,
  Pointer<CodexStringView>,
  Size,
  Int32,
  Pointer<CodexStringView>,
  Size,
  Int32,
  Pointer<CodexStringView>,
  Size,
  Int32,
  Pointer<Void>,
  Int32,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  Pointer<Pointer<Void>>,
  Size,
  Pointer<Pointer<Void>>,
);
typedef _LeafMcpConfigurationCreateDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  Pointer<Void>,
  int,
  int,
  Pointer<CodexStringView>,
  int,
  int,
  int,
  int,
  Pointer<Int32>,
  int,
  int,
  double,
  int,
  double,
  int,
  int,
  int,
  Pointer<CodexStringView>,
  int,
  int,
  Pointer<CodexStringView>,
  int,
  int,
  Pointer<CodexStringView>,
  int,
  int,
  Pointer<Void>,
  int,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  Pointer<Pointer<Void>>,
  int,
  Pointer<Pointer<Void>>,
);
typedef _LeafMcpServerCreateNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  Int32,
  Pointer<Void>,
  Int32,
  Int32,
  Pointer<Pointer<Void>>,
);
typedef _LeafMcpServerCreateDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  int,
  Pointer<Void>,
  int,
  int,
  Pointer<Pointer<Void>>,
);

typedef _LeafContainsNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<CodexStringView>,
  Pointer<Int32>,
);
typedef _LeafContainsDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<CodexStringView>,
  Pointer<Int32>,
);

final class _LeafNativeStrings {
  _LeafNativeStrings(Iterable<String> source)
      : values = source.map(NativeString.new).toList(growable: false) {
    pointer = values.isEmpty
        ? nullptr
        : nativeMemory.allocate<CodexStringView>(
            sizeOf<CodexStringView>() * values.length,
          );
    for (var index = 0; index < values.length; index++) {
      (pointer + index).ref
        ..data = values[index].view.ref.data
        ..size = values[index].view.ref.size;
    }
  }
  final List<NativeString> values;
  late final Pointer<CodexStringView> pointer;
  void close() {
    nativeMemory.free(pointer);
    for (final value in values) {
      value.close();
    }
  }
}

final class _LeafNativeHandles {
  _LeafNativeHandles(List<Pointer<Void>> values) {
    pointer = values.isEmpty
        ? nullptr
        : nativeMemory.allocate<Pointer<Void>>(
            sizeOf<Pointer<Void>>() * values.length,
          );
    for (var index = 0; index < values.length; index++) {
      (pointer + index).value = values[index];
    }
  }
  late final Pointer<Pointer<Void>> pointer;
  void close() => nativeMemory.free(pointer);
}

final class _LeafNativeStringMap {
  _LeafNativeStringMap(Map<String, String>? source)
      : keys = _LeafNativeStrings((source ?? const {}).keys),
        values = _LeafNativeStrings((source ?? const {}).values),
        length = source?.length ?? 0;
  final _LeafNativeStrings keys;
  final _LeafNativeStrings values;
  final int length;
  void close() {
    values.close();
    keys.close();
  }
}

final class _LeafCodec {
  const _LeafCodec(this.owner);
  final _NativeContextOwner owner;

  DynamicLibrary get library => owner.api.library;
  Pointer<CodexNativeContext> get context => owner.require();

  _LeafTemporary owned(Pointer<Void> value, String destroySymbol) {
    final slot = newHandleSlot<Void>()..value = value;
    return _LeafTemporary(
      owner,
      slot,
      library.lookupFunction<CodexReleaseHandleNative<Void>,
          CodexReleaseHandleDart<Void>>(destroySymbol),
      destroySymbol,
    );
  }

  void destroy(String symbol, Pointer<Void> value) =>
      owned(value, symbol).destroy();

  int intValue(String symbol, Pointer<Void> value) {
    final output = nativeMemory.allocate<Int32>(sizeOf<Int32>());
    try {
      final call = library
          .lookupFunction<_LeafValueIntNative, _LeafValueIntDart>(symbol);
      checkStatus(call(context, value, output), symbol);
      return output.value;
    } finally {
      nativeMemory.free(output);
    }
  }

  int int64Value(String symbol, Pointer<Void> value) {
    final output = nativeMemory.allocate<Int64>(sizeOf<Int64>());
    try {
      final call = library
          .lookupFunction<_LeafValueInt64Native, _LeafValueInt64Dart>(symbol);
      checkStatus(call(context, value, output), symbol);
      return output.value;
    } finally {
      nativeMemory.free(output);
    }
  }

  int count(String symbol, Pointer<Void> value) {
    final output = nativeMemory.allocate<Size>(sizeOf<Size>());
    try {
      final call = library
          .lookupFunction<_LeafValueSizeNative, _LeafValueSizeDart>(symbol);
      checkStatus(call(context, value, output), symbol);
      return output.value;
    } finally {
      nativeMemory.free(output);
    }
  }

  Pointer<Void> handle(String symbol, Pointer<Void> value) {
    final output = newHandleSlot<Void>();
    try {
      final call = library
          .lookupFunction<_LeafValueHandleNative, _LeafValueHandleDart>(symbol);
      checkStatus(call(context, value, output), symbol);
      if (output.value == nullptr) {
        throw CodexException('$symbol returned an absent owned value');
      }
      return output.value;
    } finally {
      nativeMemory.free(output);
    }
  }

  Pointer<Void> handleAt(String symbol, Pointer<Void> value, int index) {
    final output = newHandleSlot<Void>();
    try {
      final call =
          library.lookupFunction<_LeafValueAtNative, _LeafValueAtDart>(symbol);
      checkStatus(call(context, value, index, output), symbol);
      if (output.value == nullptr) {
        throw CodexException('$symbol returned an absent owned value');
      }
      return output.value;
    } finally {
      nativeMemory.free(output);
    }
  }

  String string(String symbol, Pointer<Void> value) => copyString(
        library.lookupFunction<_LeafValueStringNative, _LeafValueStringDart>(
          symbol,
        ),
        context,
        value,
      );

  String stringAt(String symbol, Pointer<Void> value, int index) {
    final call = library.lookupFunction<_LeafValueStringAtNative,
        _LeafValueStringAtDart>(symbol);
    final required = nativeMemory.allocate<Size>(sizeOf<Size>());
    try {
      checkStatus(
        call(context, value, index, nullptr, 0, required),
        symbol,
        allow: const <CodexStatus>{CodexStatus.bufferTooSmall},
      );
      if (required.value == 0) return '';
      final buffer = nativeMemory.allocate<Uint8>(required.value);
      try {
        checkStatus(
          call(context, value, index, buffer, required.value, required),
          symbol,
        );
        return utf8.decode(buffer.asTypedList(required.value));
      } finally {
        nativeMemory.free(buffer);
      }
    } finally {
      nativeMemory.free(required);
    }
  }

  String? optionalString(
    Pointer<Void> value,
    String presence,
    String copy,
  ) =>
      intValue(presence, value) == 0 ? null : string(copy, value);

  List<String> strings(
    Pointer<Void> value,
    String countSymbol,
    String atSymbol,
  ) =>
      List<String>.unmodifiable(List<String>.generate(
        count(countSymbol, value),
        (index) => stringAt(atSymbol, value, index),
      ));

  T enumValue<T>(Iterable<T> values, int native, int Function(T) project) =>
      values.firstWhere((value) => project(value) == native);

  CodexServiceTier serviceTier(Pointer<Void> value) {
    try {
      return CodexServiceTier(
        id: string('codex_agent_service_tier_id_copy', value),
        name: string('codex_agent_service_tier_name_copy', value),
        description: string('codex_agent_service_tier_description_copy', value),
      );
    } finally {
      destroy('codex_agent_service_tier_destroy', value);
    }
  }

  CodexModel model(Pointer<Void> value) {
    try {
      return CodexModel(
        id: string('codex_agent_model_id_copy', value),
        displayName: string('codex_agent_model_display_name_copy', value),
        description: string('codex_agent_model_description_copy', value),
        supportedEfforts: strings(
          value,
          'codex_agent_model_supported_efforts_count',
          'codex_agent_model_supported_effort_copy_at',
        ),
        defaultEffort: string('codex_agent_model_default_effort_copy', value),
        isDefault: intValue('codex_agent_model_is_default', value) != 0,
        serviceTiers: List<CodexServiceTier>.generate(
          count('codex_agent_model_service_tiers_count', value),
          (index) => serviceTier(
            handleAt('codex_agent_model_service_tier_at', value, index),
          ),
        ),
        defaultServiceTier: optionalString(
          value,
          'codex_agent_model_has_default_service_tier',
          'codex_agent_model_default_service_tier_copy',
        ),
      );
    } finally {
      destroy('codex_agent_model_destroy', value);
    }
  }

  CodexConnector connector(Pointer<Void> value) {
    try {
      return CodexConnector(
        id: string('codex_agent_connector_id_copy', value),
        name: string('codex_agent_connector_name_copy', value),
        description: string('codex_agent_connector_description_copy', value),
        installUrl: optionalString(
          value,
          'codex_agent_connector_has_install_url',
          'codex_agent_connector_install_url_copy',
        ),
        isAccessible:
            intValue('codex_agent_connector_is_accessible', value) != 0,
        isEnabled: intValue('codex_agent_connector_is_enabled', value) != 0,
        pluginNames: strings(
          value,
          'codex_agent_connector_plugin_names_count',
          'codex_agent_connector_plugin_names_copy_at',
        ),
      );
    } finally {
      destroy('codex_agent_connector_destroy', value);
    }
  }

  CodexPluginReference pluginReference(Pointer<Void> value) {
    try {
      return CodexPluginReference(
        id: string('codex_agent_plugin_reference_id_copy', value),
        name: string('codex_agent_plugin_reference_name_copy', value),
        marketplaceName:
            string('codex_agent_plugin_reference_marketplace_name_copy', value),
        marketplacePath: optionalString(
          value,
          'codex_agent_plugin_reference_has_marketplace_path',
          'codex_agent_plugin_reference_marketplace_path_copy',
        ),
        remotePluginId: optionalString(
          value,
          'codex_agent_plugin_reference_has_remote_plugin_id',
          'codex_agent_plugin_reference_remote_plugin_id_copy',
        ),
      );
    } finally {
      destroy('codex_agent_plugin_reference_destroy', value);
    }
  }

  CodexPluginSkill pluginSkill(Pointer<Void> value) {
    try {
      return CodexPluginSkill(
        name: string('codex_agent_plugin_skill_name_copy', value),
        description: string('codex_agent_plugin_skill_description_copy', value),
        isEnabled: intValue('codex_agent_plugin_skill_is_enabled', value) != 0,
        path: optionalString(
          value,
          'codex_agent_plugin_skill_has_path',
          'codex_agent_plugin_skill_path_copy',
        ),
      );
    } finally {
      destroy('codex_agent_plugin_skill_destroy', value);
    }
  }

  CodexPluginSummary pluginSummary(Pointer<Void> value) {
    try {
      return CodexPluginSummary(
        reference: pluginReference(
            handle('codex_agent_plugin_summary_reference', value)),
        displayName:
            string('codex_agent_plugin_summary_display_name_copy', value),
        description:
            string('codex_agent_plugin_summary_description_copy', value),
        isInstalled:
            intValue('codex_agent_plugin_summary_is_installed', value) != 0,
        isEnabled:
            intValue('codex_agent_plugin_summary_is_enabled', value) != 0,
        installPolicy: enumValue(
          CodexPluginInstallPolicy.values,
          intValue('codex_agent_plugin_summary_install_policy', value),
          (item) => item.value,
        ),
        authPolicy: enumValue(
          CodexPluginAuthPolicy.values,
          intValue('codex_agent_plugin_summary_auth_policy', value),
          (item) => item.value,
        ),
        isAvailable:
            intValue('codex_agent_plugin_summary_is_available', value) != 0,
        capabilities: strings(
          value,
          'codex_agent_plugin_summary_capabilities_count',
          'codex_agent_plugin_summary_capabilities_copy_at',
        ),
        brandColor: optionalString(
            value,
            'codex_agent_plugin_summary_has_brand_color',
            'codex_agent_plugin_summary_brand_color_copy'),
        privacyPolicyUrl: optionalString(
            value,
            'codex_agent_plugin_summary_has_privacy_policy_url',
            'codex_agent_plugin_summary_privacy_policy_url_copy'),
        termsOfServiceUrl: optionalString(
            value,
            'codex_agent_plugin_summary_has_terms_of_service_url',
            'codex_agent_plugin_summary_terms_of_service_url_copy'),
        websiteUrl: optionalString(
            value,
            'codex_agent_plugin_summary_has_website_url',
            'codex_agent_plugin_summary_website_url_copy'),
      );
    } finally {
      destroy('codex_agent_plugin_summary_destroy', value);
    }
  }

  CodexPluginCatalog pluginCatalog(Pointer<Void> value) {
    try {
      return CodexPluginCatalog(
        plugins: List<CodexPluginSummary>.generate(
          count('codex_agent_plugin_catalog_plugins_count', value),
          (index) => pluginSummary(
              handleAt('codex_agent_plugin_catalog_plugins_at', value, index)),
        ),
        errors: strings(value, 'codex_agent_plugin_catalog_errors_count',
            'codex_agent_plugin_catalog_errors_copy_at'),
        freshness: enumValue(
          CodexCatalogFreshness.values,
          intValue('codex_agent_plugin_catalog_freshness', value),
          (item) => item.value,
        ),
      );
    } finally {
      destroy('codex_agent_plugin_catalog_destroy', value);
    }
  }

  CodexPluginDetail pluginDetail(Pointer<Void> value) {
    try {
      return CodexPluginDetail(
        summary:
            pluginSummary(handle('codex_agent_plugin_detail_summary', value)),
        description:
            string('codex_agent_plugin_detail_description_copy', value),
        skills: List<CodexPluginSkill>.generate(
          count('codex_agent_plugin_detail_skills_count', value),
          (index) => pluginSkill(
              handleAt('codex_agent_plugin_detail_skills_at', value, index)),
        ),
        connectors: List<CodexConnector>.generate(
          count('codex_agent_plugin_detail_connectors_count', value),
          (index) => connector(handleAt(
              'codex_agent_plugin_detail_connectors_at', value, index)),
        ),
        mcpServers: strings(
            value,
            'codex_agent_plugin_detail_mcp_servers_count',
            'codex_agent_plugin_detail_mcp_servers_copy_at'),
        hookCount: intValue('codex_agent_plugin_detail_hook_count', value),
      );
    } finally {
      destroy('codex_agent_plugin_detail_destroy', value);
    }
  }

  CodexPluginInstallResult pluginInstallResult(Pointer<Void> value) {
    try {
      return CodexPluginInstallResult(
        authPolicy: enumValue(
          CodexPluginAuthPolicy.values,
          intValue('codex_agent_plugin_install_result_auth_policy', value),
          (item) => item.value,
        ),
        connectorsNeedingAuthentication: List<CodexConnector>.generate(
          count('codex_agent_plugin_install_result_connectors_count', value),
          (index) => connector(handleAt(
              'codex_agent_plugin_install_result_connectors_at', value, index)),
        ),
        message: optionalString(
            value,
            'codex_agent_plugin_install_result_has_message',
            'codex_agent_plugin_install_result_message_copy'),
      );
    } finally {
      destroy('codex_agent_plugin_install_result_destroy', value);
    }
  }

  CodexSkill skill(Pointer<Void> value) {
    try {
      return CodexSkill(
        name: string('codex_agent_skill_name_copy', value),
        displayName: string('codex_agent_skill_display_name_copy', value),
        description: string('codex_agent_skill_description_copy', value),
        path: string('codex_agent_skill_path_copy', value),
        scope: enumValue(CodexSkillScope.values,
            intValue('codex_agent_skill_scope', value), (item) => item.value),
        isEnabled: intValue('codex_agent_skill_is_enabled', value) != 0,
        brandColor: optionalString(value, 'codex_agent_skill_has_brand_color',
            'codex_agent_skill_brand_color_copy'),
        dependencies: strings(value, 'codex_agent_skill_dependencies_count',
            'codex_agent_skill_dependencies_copy_at'),
        canUninstall: intValue('codex_agent_skill_can_uninstall', value) != 0,
        origin: enumValue<CodexResourceOrigin>(
            CodexResourceOrigin.values,
            intValue('codex_agent_skill_origin', value),
            (CodexResourceOrigin item) => item.value),
      );
    } finally {
      destroy('codex_agent_skill_destroy', value);
    }
  }

  CodexSkillCatalog skillCatalog(Pointer<Void> value) {
    try {
      return CodexSkillCatalog(
        skills: List<CodexSkill>.generate(
          count('codex_agent_skill_catalog_skills_count', value),
          (index) => skill(
              handleAt('codex_agent_skill_catalog_skills_at', value, index)),
        ),
        errors: strings(value, 'codex_agent_skill_catalog_errors_count',
            'codex_agent_skill_catalog_errors_copy_at'),
      );
    } finally {
      destroy('codex_agent_skill_catalog_destroy', value);
    }
  }

  CodexSkillChunk skillChunk(Pointer<Void> value) {
    final present = nativeMemory.allocate<Int32>(sizeOf<Int32>());
    final offset = nativeMemory.allocate<Int64>(sizeOf<Int64>());
    try {
      final next = library.lookupFunction<_LeafValueOptionalInt64Native,
          _LeafValueOptionalInt64Dart>('codex_agent_skill_chunk_next_offset');
      checkStatus(next(context, value, present, offset),
          'codex_agent_skill_chunk_next_offset');
      return CodexSkillChunk(
        content: string('codex_agent_skill_chunk_content_copy', value),
        nextOffset: present.value == 0 ? null : offset.value,
        totalBytes: int64Value('codex_agent_skill_chunk_total_bytes', value),
      );
    } finally {
      nativeMemory.free(present);
      nativeMemory.free(offset);
      destroy('codex_agent_skill_chunk_destroy', value);
    }
  }

  CodexHookHandler hookHandler(Pointer<Void> value) {
    try {
      final kind = intValue('codex_agent_hook_handler_kind', value);
      final suffix = switch (kind) {
        0 => 'agent',
        1 => 'command',
        2 => 'mcp_tool',
        3 => 'prompt',
        _ => throw CodexException('unknown native hook-handler kind $kind'),
      };
      final concrete = handle('codex_agent_hook_handler_$suffix', value);
      try {
        return switch (kind) {
          0 => CodexAgentHookHandler.instance,
          1 => CodexCommandHookHandler(
              command: string(
                  'codex_agent_hook_handler_command_command_copy', concrete),
              isAsync: intValue(
                      'codex_agent_hook_handler_command_is_async', concrete) !=
                  0,
            ),
          2 => CodexMcpToolHookHandler(
              server: string(
                  'codex_agent_hook_handler_mcp_tool_server_copy', concrete),
              tool: string(
                  'codex_agent_hook_handler_mcp_tool_tool_copy', concrete),
            ),
          3 => CodexPromptHookHandler.instance,
          _ => throw StateError('unreachable'),
        };
      } finally {
        destroy('codex_agent_hook_handler_${suffix}_destroy', concrete);
      }
    } finally {
      destroy('codex_agent_hook_handler_destroy', value);
    }
  }

  CodexHook hook(Pointer<Void> value) {
    try {
      return CodexHook(
        key: string('codex_agent_hook_key_copy', value),
        currentHash: string('codex_agent_hook_current_hash_copy', value),
        isEnabled: intValue('codex_agent_hook_is_enabled', value) != 0,
        eventName: string('codex_agent_hook_event_name_copy', value),
        handler: hookHandler(handle('codex_agent_hook_handler', value)),
        isManaged: intValue('codex_agent_hook_is_managed', value) != 0,
        source: string('codex_agent_hook_source_copy', value),
        sourcePath: string('codex_agent_hook_source_path_copy', value),
        timeoutSeconds: int64Value('codex_agent_hook_timeout_seconds', value),
        trustStatus: enumValue(
          CodexHookTrustStatus.values,
          intValue('codex_agent_hook_trust_status', value),
          (item) => item.value,
        ),
        matcher: optionalString(value, 'codex_agent_hook_has_matcher',
            'codex_agent_hook_matcher_copy'),
        pluginId: optionalString(value, 'codex_agent_hook_has_plugin_id',
            'codex_agent_hook_plugin_id_copy'),
        statusMessage: optionalString(
            value,
            'codex_agent_hook_has_status_message',
            'codex_agent_hook_status_message_copy'),
        origin: enumValue<CodexResourceOrigin>(
          CodexResourceOrigin.values,
          intValue('codex_agent_hook_origin', value),
          (CodexResourceOrigin item) => item.value,
        ),
        canUninstall: intValue('codex_agent_hook_can_uninstall', value) != 0,
      );
    } finally {
      destroy('codex_agent_hook_destroy', value);
    }
  }

  CodexHookCatalog hookCatalog(Pointer<Void> value) {
    try {
      return CodexHookCatalog(
        hooks: List<CodexHook>.generate(
          count('codex_agent_hook_catalog_hooks_count', value),
          (index) =>
              hook(handleAt('codex_agent_hook_catalog_hooks_at', value, index)),
        ),
        warnings: strings(value, 'codex_agent_hook_catalog_warnings_count',
            'codex_agent_hook_catalog_warnings_copy_at'),
        errors: strings(value, 'codex_agent_hook_catalog_errors_count',
            'codex_agent_hook_catalog_errors_copy_at'),
      );
    } finally {
      destroy('codex_agent_hook_catalog_destroy', value);
    }
  }

  CodexFailure? optionalFailure(
      Pointer<Void> value, String hasSymbol, String getSymbol) {
    if (intValue(hasSymbol, value) == 0) return null;
    final failure = handle(getSymbol, value);
    final slot = newHandleSlot<CodexNativeFailure>()
      ..value = failure.cast<CodexNativeFailure>();
    return _decodeFailure(owner, slot);
  }

  CodexAuthorizationUrl authorizationUrl(Pointer<Void> value) {
    try {
      final raw = string('codex_agent_authorization_url_value_copy', value);
      final purpose = intValue('codex_agent_authorization_url_purpose', value);
      return switch (purpose) {
        0 => CodexAuthorizationUrl.chatGpt(raw),
        1 => CodexAuthorizationUrl.external(raw),
        _ => throw CodexException('unknown authorization URL purpose $purpose'),
      };
    } finally {
      destroy('codex_agent_authorization_url_destroy', value);
    }
  }

  CodexAuthenticationState authenticationState(Pointer<Void> value) {
    try {
      return CodexAuthenticationState(
        status: enumValue(
          CodexAuthenticationStatus.values,
          intValue('codex_agent_authentication_state_status', value),
          (item) => item.value,
        ),
        pendingSignInUrl: intValue(
                    'codex_agent_authentication_state_has_pending_sign_in_url',
                    value) ==
                0
            ? null
            : authorizationUrl(handle(
                'codex_agent_authentication_state_pending_sign_in_url', value)),
        deviceVerificationUrl: intValue(
                    'codex_agent_authentication_state_has_device_verification_url',
                    value) ==
                0
            ? null
            : authorizationUrl(handle(
                'codex_agent_authentication_state_device_verification_url',
                value)),
        deviceUserCode: optionalString(
          value,
          'codex_agent_authentication_state_has_device_user_code',
          'codex_agent_authentication_state_device_user_code_copy',
        ),
        failure: optionalFailure(
          value,
          'codex_agent_authentication_state_has_failure',
          'codex_agent_authentication_state_failure',
        ),
      );
    } finally {
      destroy('codex_agent_authentication_state_destroy', value);
    }
  }

  CodexMcpServer mcpServer(Pointer<Void> value) {
    try {
      final hasConfiguration =
          intValue('codex_agent_mcp_server_has_configuration', value) != 0;
      return CodexMcpServer(
        name: string('codex_agent_mcp_server_name_copy', value),
        displayName: string('codex_agent_mcp_server_display_name_copy', value),
        authStatus: enumValue(
          CodexMcpAuthStatus.values,
          intValue('codex_agent_mcp_server_auth_status', value),
          (item) => item.value,
        ),
        configuration: hasConfiguration
            ? mcpConfiguration(
                handle('codex_agent_mcp_server_configuration', value))
            : null,
        origin: enumValue(
          CodexResourceOrigin.values,
          intValue('codex_agent_mcp_server_origin', value),
          (item) => item.value,
        ),
        canRemove: intValue('codex_agent_mcp_server_can_remove', value) != 0,
      );
    } finally {
      destroy('codex_agent_mcp_server_destroy', value);
    }
  }

  CodexMcpServerConfiguration mcpConfiguration(Pointer<Void> value) {
    try {
      final transport = mcpTransport(
          handle('codex_agent_mcp_server_configuration_transport', value));
      return CodexMcpServerConfiguration(
        name: string('codex_agent_mcp_server_configuration_name_copy', value),
        transport: transport,
        authentication: _optionalEnum(
          value,
          'codex_agent_mcp_server_configuration_authentication',
          CodexMcpAuthentication.values,
          (item) => item.value,
        ),
        environmentId: string(
            'codex_agent_mcp_server_configuration_environment_id_copy', value),
        isEnabled: intValue(
                'codex_agent_mcp_server_configuration_is_enabled', value) !=
            0,
        isRequired: intValue(
                'codex_agent_mcp_server_configuration_is_required', value) !=
            0,
        supportsParallelToolCalls: intValue(
                'codex_agent_mcp_server_configuration_supports_parallel_tool_calls',
                value) !=
            0,
        // Optional collections and advanced OAuth/tool options are decoded by
        // their exact accessors when present below.
        omitToolsFrom: _optionalEnumList(
          value,
          'codex_agent_mcp_server_configuration_has_omit_tools_from',
          'codex_agent_mcp_server_configuration_omit_tools_from_count',
          'codex_agent_mcp_server_configuration_omit_tools_from_at',
          CodexMcpToolExposureSurface.values,
          (item) => item.value,
        ),
        startupTimeoutSeconds: _optionalDouble(value,
            'codex_agent_mcp_server_configuration_startup_timeout_seconds'),
        toolTimeoutSeconds: _optionalDouble(
            value, 'codex_agent_mcp_server_configuration_tool_timeout_seconds'),
        defaultToolApproval: _optionalEnum(
          value,
          'codex_agent_mcp_server_configuration_default_tool_approval',
          CodexMcpToolApproval.values,
          (item) => item.value,
        ),
        enabledTools: _optionalStrings(
          value,
          'codex_agent_mcp_server_configuration_has_enabled_tools',
          'codex_agent_mcp_server_configuration_enabled_tools_count',
          'codex_agent_mcp_server_configuration_enabled_tool_copy_at',
        ),
        disabledTools: _optionalStrings(
          value,
          'codex_agent_mcp_server_configuration_has_disabled_tools',
          'codex_agent_mcp_server_configuration_disabled_tools_count',
          'codex_agent_mcp_server_configuration_disabled_tool_copy_at',
        ),
        scopes: _optionalStrings(
          value,
          'codex_agent_mcp_server_configuration_has_scopes',
          'codex_agent_mcp_server_configuration_scopes_count',
          'codex_agent_mcp_server_configuration_scope_copy_at',
        ),
        oauth: intValue(
                    'codex_agent_mcp_server_configuration_has_oauth', value) ==
                0
            ? null
            : mcpOauth(
                handle('codex_agent_mcp_server_configuration_oauth', value)),
        oauthResource: optionalString(
          value,
          'codex_agent_mcp_server_configuration_has_oauth_resource',
          'codex_agent_mcp_server_configuration_oauth_resource_copy',
        ),
        tools: _mcpTools(value),
      );
    } finally {
      destroy('codex_agent_mcp_server_configuration_destroy', value);
    }
  }

  T? _optionalEnum<T>(
    Pointer<Void> value,
    String symbol,
    List<T> values,
    int Function(T) project,
  ) {
    final present = nativeMemory.allocate<Int32>(sizeOf<Int32>());
    final output = nativeMemory.allocate<Int32>(sizeOf<Int32>());
    try {
      final call = library.lookupFunction<_LeafValueOptionalIntNative,
          _LeafValueOptionalIntDart>(symbol);
      checkStatus(call(context, value, present, output), symbol);
      return present.value == 0
          ? null
          : enumValue<T>(values, output.value, project);
    } finally {
      nativeMemory.free(present);
      nativeMemory.free(output);
    }
  }

  double? _optionalDouble(Pointer<Void> value, String symbol) {
    final present = nativeMemory.allocate<Int32>(sizeOf<Int32>());
    final output = nativeMemory.allocate<Double>(sizeOf<Double>());
    try {
      final call = library.lookupFunction<_LeafValueOptionalDoubleNative,
          _LeafValueOptionalDoubleDart>(symbol);
      checkStatus(call(context, value, present, output), symbol);
      return present.value == 0 ? null : output.value;
    } finally {
      nativeMemory.free(present);
      nativeMemory.free(output);
    }
  }

  List<String>? _optionalStrings(
    Pointer<Void> value,
    String presence,
    String countSymbol,
    String atSymbol,
  ) =>
      intValue(presence, value) == 0
          ? null
          : strings(value, countSymbol, atSymbol);

  List<T>? _optionalEnumList<T>(
    Pointer<Void> value,
    String presence,
    String countSymbol,
    String atSymbol,
    List<T> values,
    int Function(T) project,
  ) {
    if (intValue(presence, value) == 0) return null;
    final call = library.lookupFunction<_LeafValueIndexIntNative,
        _LeafValueIndexIntDart>(atSymbol);
    return List<T>.unmodifiable(
        List<T>.generate(count(countSymbol, value), (index) {
      final output = nativeMemory.allocate<Int32>(sizeOf<Int32>());
      try {
        checkStatus(call(context, value, index, output), atSymbol);
        return enumValue(values, output.value, project);
      } finally {
        nativeMemory.free(output);
      }
    }));
  }

  CodexMcpOauthConfiguration mcpOauth(Pointer<Void> value) {
    try {
      final port = nativeMemory.allocate<Int32>(sizeOf<Int32>());
      final present = nativeMemory.allocate<Int32>(sizeOf<Int32>());
      try {
        final call = library.lookupFunction<_LeafValueOptionalIntNative,
                _LeafValueOptionalIntDart>(
            'codex_agent_mcp_oauth_configuration_callback_port');
        checkStatus(
          call(context, value, present, port),
          'codex_agent_mcp_oauth_configuration_callback_port',
        );
        return CodexMcpOauthConfiguration(
          clientId: optionalString(
            value,
            'codex_agent_mcp_oauth_configuration_has_client_id',
            'codex_agent_mcp_oauth_configuration_client_id_copy',
          ),
          callbackPort: present.value == 0 ? null : port.value,
        );
      } finally {
        nativeMemory.free(port);
        nativeMemory.free(present);
      }
    } finally {
      destroy('codex_agent_mcp_oauth_configuration_destroy', value);
    }
  }

  CodexMcpToolConfiguration mcpTool(Pointer<Void> value) {
    try {
      return CodexMcpToolConfiguration(
        approval: _optionalEnum(
          value,
          'codex_agent_mcp_tool_configuration_approval',
          CodexMcpToolApproval.values,
          (item) => item.value,
        ),
      );
    } finally {
      destroy('codex_agent_mcp_tool_configuration_destroy', value);
    }
  }

  Map<String, CodexMcpToolConfiguration> _mcpTools(Pointer<Void> value) {
    final result = <String, CodexMcpToolConfiguration>{};
    for (var index = 0;
        index <
            count('codex_agent_mcp_server_configuration_tools_count', value);
        index++) {
      final key = stringAt(
          'codex_agent_mcp_server_configuration_tools_key_copy_at',
          value,
          index);
      if (result.containsKey(key)) {
        throw CodexException('native MCP tools contain duplicate key $key');
      }
      result[key] = mcpTool(handleAt(
          'codex_agent_mcp_server_configuration_tools_value_at', value, index));
    }
    return Map<String, CodexMcpToolConfiguration>.unmodifiable(result);
  }

  CodexMcpTransport mcpTransport(Pointer<Void> value) {
    try {
      final kind = intValue('codex_agent_mcp_transport_kind', value);
      if (kind == 0) {
        final http = handle('codex_agent_mcp_transport_http', value);
        try {
          return CodexMcpHttpTransport(
            url: string('codex_agent_mcp_transport_http_url_copy', http),
            bearerTokenEnvironmentVariable: optionalString(
              http,
              'codex_agent_mcp_transport_http_has_bearer_token_environment_variable',
              'codex_agent_mcp_transport_http_bearer_token_environment_variable_copy',
            ),
            headers: _optionalStringMap(
              http,
              'codex_agent_mcp_transport_http_has_headers',
              'codex_agent_mcp_transport_http_headers_count',
              'codex_agent_mcp_transport_http_headers_key_copy_at',
              'codex_agent_mcp_transport_http_headers_value_copy_at',
            ),
            environmentHeaders: _optionalStringMap(
              http,
              'codex_agent_mcp_transport_http_has_environment_headers',
              'codex_agent_mcp_transport_http_environment_headers_count',
              'codex_agent_mcp_transport_http_environment_headers_key_copy_at',
              'codex_agent_mcp_transport_http_environment_headers_value_copy_at',
            ),
            headersHelper: optionalString(
              http,
              'codex_agent_mcp_transport_http_has_headers_helper',
              'codex_agent_mcp_transport_http_headers_helper_copy',
            ),
          );
        } finally {
          destroy('codex_agent_mcp_transport_http_destroy', http);
        }
      }
      if (kind == 1) {
        final stdio = handle('codex_agent_mcp_transport_stdio', value);
        try {
          return CodexMcpStdioTransport(
            command:
                string('codex_agent_mcp_transport_stdio_command_copy', stdio),
            arguments: strings(
              stdio,
              'codex_agent_mcp_transport_stdio_arguments_count',
              'codex_agent_mcp_transport_stdio_argument_copy_at',
            ),
            workingDirectory: optionalString(
              stdio,
              'codex_agent_mcp_transport_stdio_has_working_directory',
              'codex_agent_mcp_transport_stdio_working_directory_copy',
            ),
            environment: _optionalStringMap(
              stdio,
              'codex_agent_mcp_transport_stdio_has_environment',
              'codex_agent_mcp_transport_stdio_environment_count',
              'codex_agent_mcp_transport_stdio_environment_key_copy_at',
              'codex_agent_mcp_transport_stdio_environment_value_copy_at',
            ),
            forwardedEnvironment: List<CodexMcpEnvironmentVariable>.generate(
              count(
                  'codex_agent_mcp_transport_stdio_forwarded_environment_count',
                  stdio),
              (index) => mcpEnvironmentVariable(handleAt(
                  'codex_agent_mcp_transport_stdio_forwarded_environment_at',
                  stdio,
                  index)),
            ),
          );
        } finally {
          destroy('codex_agent_mcp_transport_stdio_destroy', stdio);
        }
      }
      throw CodexException('unknown native MCP transport kind $kind');
    } finally {
      destroy('codex_agent_mcp_transport_destroy', value);
    }
  }

  Map<String, String>? _optionalStringMap(
    Pointer<Void> value,
    String presence,
    String countSymbol,
    String keySymbol,
    String valueSymbol,
  ) {
    if (intValue(presence, value) == 0) return null;
    final result = <String, String>{};
    for (var index = 0; index < count(countSymbol, value); index++) {
      final key = stringAt(keySymbol, value, index);
      if (result.containsKey(key)) {
        throw CodexException('$countSymbol returned duplicate key $key');
      }
      result[key] = stringAt(valueSymbol, value, index);
    }
    return Map<String, String>.unmodifiable(result);
  }

  CodexMcpEnvironmentVariable mcpEnvironmentVariable(Pointer<Void> value) {
    try {
      return CodexMcpEnvironmentVariable(
        name: string('codex_agent_mcp_environment_variable_name_copy', value),
        source: _optionalEnum(
          value,
          'codex_agent_mcp_environment_variable_source',
          CodexMcpEnvironmentSource.values,
          (item) => item.value,
        ),
      );
    } finally {
      destroy('codex_agent_mcp_environment_variable_destroy', value);
    }
  }

  CodexIntegration integration(Pointer<Void> value) {
    try {
      final kind = intValue('codex_agent_integration_kind', value);
      if (kind == 0) {
        final concrete = handle('codex_agent_integration_connector', value);
        try {
          return CodexConnectorIntegration(connector(
              handle('codex_agent_integration_connector_connector', concrete)));
        } finally {
          destroy('codex_agent_integration_connector_destroy', concrete);
        }
      }
      if (kind == 1) {
        final concrete = handle('codex_agent_integration_mcp_server', value);
        try {
          return CodexMcpServerIntegration(mcpServer(
              handle('codex_agent_integration_mcp_server_server', concrete)));
        } finally {
          destroy('codex_agent_integration_mcp_server_destroy', concrete);
        }
      }
      throw CodexException('unknown native integration kind $kind');
    } finally {
      destroy('codex_agent_integration_destroy', value);
    }
  }

  CodexIntegrationAuthorizationState integrationAuthorizationState(
      Pointer<Void> value) {
    try {
      final targetSlot = newHandleSlot<Void>();
      final failureSlot = newHandleSlot<CodexNativeFailure>();
      try {
        final targetCall = library
            .lookupFunction<_LeafValueHandleNative, _LeafValueHandleDart>(
                'codex_agent_integration_authorization_state_target');
        final targetStatus = targetCall(context, value, targetSlot);
        checkStatus(
          targetStatus,
          'codex_agent_integration_authorization_state_target',
          allow: const <CodexStatus>{CodexStatus.notReady},
        );
        final failureCall = library
            .lookupFunction<_LeafValueHandleNative, _LeafValueHandleDart>(
                'codex_agent_integration_authorization_state_failure');
        final failureStatus =
            failureCall(context, value, failureSlot.cast<Pointer<Void>>());
        checkStatus(
          failureStatus,
          'codex_agent_integration_authorization_state_failure',
          allow: const <CodexStatus>{CodexStatus.notReady},
        );
        return CodexIntegrationAuthorizationState(
          status: enumValue(
            CodexIntegrationAuthorizationStatus.values,
            intValue(
                'codex_agent_integration_authorization_state_status', value),
            (item) => item.value,
          ),
          target: targetStatus == CodexStatus.ok.value &&
                  targetSlot.value != nullptr
              ? integration(targetSlot.value)
              : null,
          failure: failureStatus == CodexStatus.ok.value &&
                  failureSlot.value != nullptr
              ? _decodeFailure(owner, failureSlot)
              : null,
        );
      } finally {
        nativeMemory.free(targetSlot);
        if (failureSlot.value == nullptr) nativeMemory.free(failureSlot);
      }
    } finally {
      destroy('codex_agent_integration_authorization_state_destroy', value);
    }
  }

  CodexConversationId conversationId(Pointer<Void> value) {
    try {
      return CodexConversationId(
          string('codex_agent_conversation_id_value_copy', value));
    } finally {
      destroy('codex_agent_conversation_id_destroy', value);
    }
  }

  CodexPendingApproval pendingApproval(Pointer<Void> value) =>
      CodexPendingApproval(
        requestId:
            string('codex_agent_pending_approval_request_id_copy', value),
        conversationId: conversationId(
            handle('codex_agent_pending_approval_conversation_id', value)),
        title: string('codex_agent_pending_approval_title_copy', value),
        details: string('codex_agent_pending_approval_details_copy', value),
      );

  CodexPendingElicitation pendingElicitation(Pointer<Void> value) =>
      CodexPendingElicitation(elicitation(
          handle('codex_agent_pending_elicitation_elicitation', value)));

  CodexElicitation elicitation(Pointer<Void> value) {
    try {
      final hasForm = intValue('codex_agent_elicitation_has_form', value) != 0;
      return CodexElicitation(
        requestId: string('codex_agent_elicitation_request_id_copy', value),
        serverName: string('codex_agent_elicitation_server_name_copy', value),
        conversationId: conversationId(
            handle('codex_agent_elicitation_conversation_id', value)),
        message: string('codex_agent_elicitation_message_copy', value),
        form: hasForm
            ? List<CodexFormField>.generate(
                count('codex_agent_elicitation_form_count', value),
                (index) => formField(
                    handleAt('codex_agent_elicitation_form_at', value, index)),
              )
            : null,
        url: optionalString(value, 'codex_agent_elicitation_has_url',
            'codex_agent_elicitation_url_copy'),
      );
    } finally {
      destroy('codex_agent_elicitation_destroy', value);
    }
  }

  CodexFormField formField(Pointer<Void> value) {
    try {
      return CodexFormField(
        name: string('codex_agent_form_field_name_copy', value),
        title: string('codex_agent_form_field_title_copy', value),
        type: enumValue(
          CodexFormFieldType.values,
          intValue('codex_agent_form_field_type', value),
          (item) => item.value,
        ),
        description: optionalString(
            value,
            'codex_agent_form_field_has_description',
            'codex_agent_form_field_description_copy'),
        isRequired: intValue('codex_agent_form_field_is_required', value) != 0,
        isSecret: intValue('codex_agent_form_field_is_secret', value) != 0,
        options: List<CodexFormOption>.generate(
          count('codex_agent_form_field_options_count', value),
          (index) => formOption(
              handleAt('codex_agent_form_field_option_at', value, index)),
        ),
        defaultValue: null,
        minimum: _optionalDouble(value, 'codex_agent_form_field_minimum'),
        maximum: _optionalDouble(value, 'codex_agent_form_field_maximum'),
        minimumLength:
            _optionalInt64(value, 'codex_agent_form_field_minimum_length'),
        maximumLength:
            _optionalInt64(value, 'codex_agent_form_field_maximum_length'),
        minimumSelections:
            _optionalInt64(value, 'codex_agent_form_field_minimum_selections'),
        maximumSelections:
            _optionalInt64(value, 'codex_agent_form_field_maximum_selections'),
        allowsOther:
            intValue('codex_agent_form_field_allows_other', value) != 0,
      );
    } finally {
      destroy('codex_agent_form_field_destroy', value);
    }
  }

  int? _optionalInt64(Pointer<Void> value, String symbol) {
    final present = nativeMemory.allocate<Int32>(sizeOf<Int32>());
    final output = nativeMemory.allocate<Int64>(sizeOf<Int64>());
    try {
      final call = library.lookupFunction<_LeafValueOptionalInt64Native,
          _LeafValueOptionalInt64Dart>(symbol);
      checkStatus(call(context, value, present, output), symbol);
      return present.value == 0 ? null : output.value;
    } finally {
      nativeMemory.free(present);
      nativeMemory.free(output);
    }
  }

  CodexFormOption formOption(Pointer<Void> value) {
    try {
      return CodexFormOption(
        value: string('codex_agent_form_option_value_copy', value),
        title: string('codex_agent_form_option_title_copy', value),
        description: optionalString(
            value,
            'codex_agent_form_option_has_description',
            'codex_agent_form_option_description_copy'),
      );
    } finally {
      destroy('codex_agent_form_option_destroy', value);
    }
  }

  CodexInteractionState interactionState(
    Pointer<Void> value,
    T Function<T extends CodexPendingInteraction>(
      T value,
      Pointer<Void> handle,
      String destroy,
    ) remember,
  ) {
    try {
      final pending = <CodexPendingInteraction>[];
      final resolving = <String>{};
      for (var index = 0;
          index < count('codex_agent_interaction_state_pending_count', value);
          index++) {
        final wrapper =
            handleAt('codex_agent_interaction_state_pending_at', value, index);
        final kind = intValue('codex_agent_pending_interaction_kind', wrapper);
        try {
          if (kind == 0) {
            final native =
                handle('codex_agent_pending_interaction_approval', wrapper);
            final decoded = remember(
              pendingApproval(native),
              native,
              'codex_agent_pending_approval_destroy',
            );
            pending.add(decoded);
          } else if (kind == 1) {
            final native =
                handle('codex_agent_pending_interaction_elicitation', wrapper);
            final decoded = remember(
              pendingElicitation(native),
              native,
              'codex_agent_pending_elicitation_destroy',
            );
            pending.add(decoded);
          } else {
            throw CodexException('unknown pending interaction kind $kind');
          }
        } finally {
          destroy('codex_agent_pending_interaction_destroy', wrapper);
        }
      }
      for (final item in pending) {
        final native = NativeString(item.requestId);
        final output = nativeMemory.allocate<Int32>(sizeOf<Int32>());
        try {
          final call = library.lookupFunction<_LeafContainsNative,
                  _LeafContainsDart>(
              'codex_agent_interaction_state_resolving_request_ids_contains');
          checkStatus(call(context, value, native.view, output),
              'codex_agent_interaction_state_resolving_request_ids_contains');
          if (output.value != 0) resolving.add(item.requestId);
        } finally {
          nativeMemory.free(output);
          native.close();
        }
      }
      return CodexInteractionState(
        pending: pending,
        resolvingRequestIds: resolving,
        failure: optionalFailure(
          value,
          'codex_agent_interaction_state_has_failure',
          'codex_agent_interaction_state_failure',
        ),
      );
    } finally {
      destroy('codex_agent_interaction_state_destroy', value);
    }
  }

  _LeafTemporary _create(
    String createSymbol,
    String destroySymbol,
    int Function(Pointer<Pointer<Void>>) invoke,
  ) {
    final slot = newHandleSlot<Void>();
    try {
      checkStatus(invoke(slot), createSymbol);
      if (slot.value == nullptr) {
        throw CodexException('$createSymbol returned an absent owned value');
      }
      return _LeafTemporary(
        owner,
        slot,
        library.lookupFunction<CodexReleaseHandleNative<Void>,
            CodexReleaseHandleDart<Void>>(destroySymbol),
        destroySymbol,
      );
    } catch (_) {
      nativeMemory.free(slot);
      rethrow;
    }
  }

  _LeafTemporary authenticationMethod(CodexAuthenticationMethod method) {
    if (method case CodexApiKeyAuthentication(:final value)) {
      final native = NativeString(value);
      try {
        final call = library.lookupFunction<_LeafContextStringOutNative,
                _LeafContextStringOutDart>(
            'codex_agent_authentication_method_api_key_create');
        return _create(
          'codex_agent_authentication_method_api_key_create',
          'codex_agent_authentication_method_api_key_destroy',
          (output) => call(context, native.view, output),
        );
      } finally {
        native.close();
      }
    }
    final browser = method is CodexChatGptBrowserAuthentication;
    final suffix = browser ? 'chat_gpt_browser' : 'chat_gpt_device_code';
    final call =
        library.lookupFunction<_LeafContextOutNative, _LeafContextOutDart>(
            'codex_agent_authentication_method_${suffix}_create');
    return _create(
      'codex_agent_authentication_method_${suffix}_create',
      'codex_agent_authentication_method_${suffix}_destroy',
      (output) => call(context, output),
    );
  }

  _LeafTemporary createServiceTier(CodexServiceTier tier) {
    final id = NativeString(tier.id);
    final name = NativeString(tier.name);
    final description = NativeString(tier.description);
    try {
      final call = library.lookupFunction<_LeafServiceTierCreateNative,
          _LeafServiceTierCreateDart>('codex_agent_service_tier_create');
      return _create(
        'codex_agent_service_tier_create',
        'codex_agent_service_tier_destroy',
        (output) => call(context, id.view, name.view, description.view, output),
      );
    } finally {
      id.close();
      name.close();
      description.close();
    }
  }

  _LeafTemporary createModel(CodexModel model) {
    final id = NativeString(model.id);
    final display = NativeString(model.displayName);
    final description = NativeString(model.description);
    final efforts = _LeafNativeStrings(model.supportedEfforts);
    final defaultEffort = NativeString(model.defaultEffort);
    final defaultTier = model.defaultServiceTier == null
        ? NativeString.absent()
        : NativeString(model.defaultServiceTier!);
    final tiers = model.serviceTiers.map(createServiceTier).toList();
    final tierHandles =
        _LeafNativeHandles(tiers.map((item) => item.value).toList());
    try {
      final call =
          library.lookupFunction<_LeafModelCreateNative, _LeafModelCreateDart>(
              'codex_agent_model_create');
      return _create(
        'codex_agent_model_create',
        'codex_agent_model_destroy',
        (output) => call(
          context,
          id.view,
          display.view,
          description.view,
          efforts.pointer,
          efforts.values.length,
          defaultEffort.view,
          model.isDefault ? 1 : 0,
          tierHandles.pointer,
          tiers.length,
          model.defaultServiceTier == null ? 0 : 1,
          defaultTier.view,
          output,
        ),
      );
    } finally {
      for (final tier in tiers) {
        tier.destroy();
      }
      tierHandles.close();
      defaultTier.close();
      defaultEffort.close();
      efforts.close();
      description.close();
      display.close();
      id.close();
    }
  }

  _LeafTemporary createPluginReference(CodexPluginReference plugin) {
    final id = NativeString(plugin.id);
    final name = NativeString(plugin.name);
    final marketplace = NativeString(plugin.marketplaceName);
    final path = plugin.marketplacePath == null
        ? NativeString.absent()
        : NativeString(plugin.marketplacePath!);
    final remote = plugin.remotePluginId == null
        ? NativeString.absent()
        : NativeString(plugin.remotePluginId!);
    try {
      final call = library.lookupFunction<_LeafPluginReferenceCreateNative,
          _LeafPluginReferenceCreateDart>(
        'codex_agent_plugin_reference_create',
      );
      return _create(
        'codex_agent_plugin_reference_create',
        'codex_agent_plugin_reference_destroy',
        (output) => call(
          context,
          id.view,
          name.view,
          marketplace.view,
          plugin.marketplacePath == null ? 0 : 1,
          path.view,
          plugin.remotePluginId == null ? 0 : 1,
          remote.view,
          output,
        ),
      );
    } finally {
      remote.close();
      path.close();
      marketplace.close();
      name.close();
      id.close();
    }
  }

  _LeafTemporary createSkill(CodexSkill skill) {
    final name = NativeString(skill.name);
    final display = NativeString(skill.displayName);
    final description = NativeString(skill.description);
    final path = NativeString(skill.path);
    final brand = skill.brandColor == null
        ? NativeString.absent()
        : NativeString(skill.brandColor!);
    final dependencies = _LeafNativeStrings(skill.dependencies);
    try {
      final call =
          library.lookupFunction<_LeafSkillCreateNative, _LeafSkillCreateDart>(
              'codex_agent_skill_create');
      return _create(
        'codex_agent_skill_create',
        'codex_agent_skill_destroy',
        (output) => call(
          context,
          name.view,
          display.view,
          description.view,
          path.view,
          skill.scope.value,
          skill.isEnabled ? 1 : 0,
          skill.brandColor == null ? 0 : 1,
          brand.view,
          dependencies.pointer,
          dependencies.values.length,
          skill.canUninstall ? 1 : 0,
          1,
          skill.origin.value,
          output,
        ),
      );
    } finally {
      dependencies.close();
      brand.close();
      path.close();
      description.close();
      display.close();
      name.close();
    }
  }

  _LeafTemporary createConnector(CodexConnector connector) {
    final id = NativeString(connector.id);
    final name = NativeString(connector.name);
    final description = NativeString(connector.description);
    final install = connector.installUrl == null
        ? NativeString.absent()
        : NativeString(connector.installUrl!);
    final plugins = _LeafNativeStrings(connector.pluginNames);
    try {
      final call = library.lookupFunction<_LeafConnectorCreateNative,
          _LeafConnectorCreateDart>('codex_agent_connector_create');
      return _create(
        'codex_agent_connector_create',
        'codex_agent_connector_destroy',
        (output) => call(
          context,
          id.view,
          name.view,
          description.view,
          connector.installUrl == null ? 0 : 1,
          install.view,
          connector.isAccessible ? 1 : 0,
          connector.isEnabled ? 1 : 0,
          plugins.pointer,
          plugins.values.length,
          output,
        ),
      );
    } finally {
      plugins.close();
      install.close();
      description.close();
      name.close();
      id.close();
    }
  }

  _LeafTemporary createElicitationResponse(CodexElicitationResponse response) {
    final value = createLeafNativeElicitationResponse(
      owner.api,
      context,
      response,
    );
    return owned(value, 'codex_agent_elicitation_response_destroy');
  }

  _LeafTemporary createHookHandler(CodexHookHandler handler) {
    late final _LeafTemporary concrete;
    late final String suffix;
    switch (handler) {
      case CodexAgentHookHandler():
        suffix = 'agent';
        final call =
            library.lookupFunction<_LeafContextOutNative, _LeafContextOutDart>(
                'codex_agent_hook_handler_agent_acquire');
        concrete = _create(
          'codex_agent_hook_handler_agent_acquire',
          'codex_agent_hook_handler_agent_destroy',
          (output) => call(context, output),
        );
      case CodexPromptHookHandler():
        suffix = 'prompt';
        final call =
            library.lookupFunction<_LeafContextOutNative, _LeafContextOutDart>(
                'codex_agent_hook_handler_prompt_acquire');
        concrete = _create(
          'codex_agent_hook_handler_prompt_acquire',
          'codex_agent_hook_handler_prompt_destroy',
          (output) => call(context, output),
        );
      case CodexCommandHookHandler(:final command, :final isAsync):
        suffix = 'command';
        final native = NativeString(command);
        try {
          final call = library.lookupFunction<_LeafContextStringIntOutNative,
                  _LeafContextStringIntOutDart>(
              'codex_agent_hook_handler_command_create');
          concrete = _create(
            'codex_agent_hook_handler_command_create',
            'codex_agent_hook_handler_command_destroy',
            (output) => call(context, native.view, isAsync ? 1 : 0, output),
          );
        } finally {
          native.close();
        }
      case CodexMcpToolHookHandler(:final server, :final tool):
        suffix = 'mcp_tool';
        final nativeServer = NativeString(server);
        final nativeTool = NativeString(tool);
        try {
          final call = library.lookupFunction<_LeafContextTwoStringsOutNative,
                  _LeafContextTwoStringsOutDart>(
              'codex_agent_hook_handler_mcp_tool_create');
          concrete = _create(
            'codex_agent_hook_handler_mcp_tool_create',
            'codex_agent_hook_handler_mcp_tool_destroy',
            (output) =>
                call(context, nativeServer.view, nativeTool.view, output),
          );
        } finally {
          nativeTool.close();
          nativeServer.close();
        }
    }
    try {
      final wrap = library.lookupFunction<_LeafContextHandleOutNative,
          _LeafContextHandleOutDart>('codex_agent_hook_handler_from_$suffix');
      return _create(
        'codex_agent_hook_handler_from_$suffix',
        'codex_agent_hook_handler_destroy',
        (output) => wrap(context, concrete.value, output),
      );
    } finally {
      concrete.destroy();
    }
  }

  _LeafTemporary createHook(CodexHook hook) {
    final key = NativeString(hook.key);
    final hash = NativeString(hook.currentHash);
    final event = NativeString(hook.eventName);
    final source = NativeString(hook.source);
    final sourcePath = NativeString(hook.sourcePath);
    final matcher = hook.matcher == null
        ? NativeString.absent()
        : NativeString(hook.matcher!);
    final plugin = hook.pluginId == null
        ? NativeString.absent()
        : NativeString(hook.pluginId!);
    final status = hook.statusMessage == null
        ? NativeString.absent()
        : NativeString(hook.statusMessage!);
    final handler = createHookHandler(hook.handler);
    try {
      final call =
          library.lookupFunction<_LeafHookCreateNative, _LeafHookCreateDart>(
              'codex_agent_hook_create');
      return _create(
        'codex_agent_hook_create',
        'codex_agent_hook_destroy',
        (output) => call(
          context,
          key.view,
          hash.view,
          hook.isEnabled ? 1 : 0,
          event.view,
          handler.value,
          hook.isManaged ? 1 : 0,
          source.view,
          sourcePath.view,
          hook.timeoutSeconds,
          hook.trustStatus.value,
          hook.matcher == null ? 0 : 1,
          matcher.view,
          hook.pluginId == null ? 0 : 1,
          plugin.view,
          hook.statusMessage == null ? 0 : 1,
          status.view,
          1,
          hook.origin.value,
          hook.canUninstall ? 1 : 0,
          output,
        ),
      );
    } finally {
      handler.destroy();
      status.close();
      plugin.close();
      matcher.close();
      sourcePath.close();
      source.close();
      event.close();
      hash.close();
      key.close();
    }
  }

  _LeafTemporary createMcpEnvironmentVariable(
      CodexMcpEnvironmentVariable variable) {
    final name = NativeString(variable.name);
    try {
      final call = library.lookupFunction<_LeafMcpEnvironmentCreateNative,
              _LeafMcpEnvironmentCreateDart>(
          'codex_agent_mcp_environment_variable_create');
      return _create(
        'codex_agent_mcp_environment_variable_create',
        'codex_agent_mcp_environment_variable_destroy',
        (output) => call(
          context,
          name.view,
          variable.source == null ? 0 : 1,
          variable.source?.value ?? 0,
          output,
        ),
      );
    } finally {
      name.close();
    }
  }

  _LeafTemporary createMcpOauth(CodexMcpOauthConfiguration oauth) {
    final client = oauth.clientId == null
        ? NativeString.absent()
        : NativeString(oauth.clientId!);
    try {
      final call = library
          .lookupFunction<_LeafMcpOauthCreateNative, _LeafMcpOauthCreateDart>(
              'codex_agent_mcp_oauth_configuration_create');
      return _create(
        'codex_agent_mcp_oauth_configuration_create',
        'codex_agent_mcp_oauth_configuration_destroy',
        (output) => call(
          context,
          oauth.clientId == null ? 0 : 1,
          client.view,
          oauth.callbackPort == null ? 0 : 1,
          oauth.callbackPort ?? 0,
          output,
        ),
      );
    } finally {
      client.close();
    }
  }

  _LeafTemporary createMcpTool(CodexMcpToolConfiguration tool) {
    final call = library.lookupFunction<_LeafMcpToolCreateNative,
        _LeafMcpToolCreateDart>('codex_agent_mcp_tool_configuration_create');
    return _create(
      'codex_agent_mcp_tool_configuration_create',
      'codex_agent_mcp_tool_configuration_destroy',
      (output) => call(
        context,
        tool.approval == null ? 0 : 1,
        tool.approval?.value ?? 0,
        output,
      ),
    );
  }

  _LeafTemporary createMcpTransport(CodexMcpTransport transport) {
    late final _LeafTemporary concrete;
    late final String suffix;
    switch (transport) {
      case CodexMcpHttpTransport():
        suffix = 'http';
        final url = NativeString(transport.url);
        final bearer = transport.bearerTokenEnvironmentVariable == null
            ? NativeString.absent()
            : NativeString(transport.bearerTokenEnvironmentVariable!);
        final headers = _LeafNativeStringMap(transport.headers);
        final environment = _LeafNativeStringMap(transport.environmentHeaders);
        final helper = transport.headersHelper == null
            ? NativeString.absent()
            : NativeString(transport.headersHelper!);
        try {
          final call = library.lookupFunction<_LeafMcpHttpCreateNative,
              _LeafMcpHttpCreateDart>('codex_agent_mcp_transport_http_create');
          concrete = _create(
            'codex_agent_mcp_transport_http_create',
            'codex_agent_mcp_transport_http_destroy',
            (output) => call(
              context,
              url.view,
              transport.bearerTokenEnvironmentVariable == null ? 0 : 1,
              bearer.view,
              transport.headers == null ? 0 : 1,
              headers.keys.pointer,
              headers.values.pointer,
              headers.length,
              transport.environmentHeaders == null ? 0 : 1,
              environment.keys.pointer,
              environment.values.pointer,
              environment.length,
              transport.headersHelper == null ? 0 : 1,
              helper.view,
              output,
            ),
          );
        } finally {
          helper.close();
          environment.close();
          headers.close();
          bearer.close();
          url.close();
        }
      case CodexMcpStdioTransport():
        suffix = 'stdio';
        final command = NativeString(transport.command);
        final arguments = _LeafNativeStrings(transport.arguments);
        final directory = transport.workingDirectory == null
            ? NativeString.absent()
            : NativeString(transport.workingDirectory!);
        final environment = _LeafNativeStringMap(transport.environment);
        final forwarded = transport.forwardedEnvironment
            .map(createMcpEnvironmentVariable)
            .toList();
        final forwardedHandles =
            _LeafNativeHandles(forwarded.map((item) => item.value).toList());
        try {
          final call = library.lookupFunction<_LeafMcpStdioCreateNative,
                  _LeafMcpStdioCreateDart>(
              'codex_agent_mcp_transport_stdio_create');
          concrete = _create(
            'codex_agent_mcp_transport_stdio_create',
            'codex_agent_mcp_transport_stdio_destroy',
            (output) => call(
              context,
              command.view,
              arguments.pointer,
              arguments.values.length,
              transport.workingDirectory == null ? 0 : 1,
              directory.view,
              transport.environment == null ? 0 : 1,
              environment.keys.pointer,
              environment.values.pointer,
              environment.length,
              forwardedHandles.pointer,
              forwarded.length,
              output,
            ),
          );
        } finally {
          for (final item in forwarded) {
            item.destroy();
          }
          forwardedHandles.close();
          environment.close();
          directory.close();
          arguments.close();
          command.close();
        }
    }
    try {
      final wrap = library.lookupFunction<_LeafContextHandleOutNative,
          _LeafContextHandleOutDart>('codex_agent_mcp_transport_from_$suffix');
      return _create(
        'codex_agent_mcp_transport_from_$suffix',
        'codex_agent_mcp_transport_destroy',
        (output) => wrap(context, concrete.value, output),
      );
    } finally {
      concrete.destroy();
    }
  }

  _LeafTemporary createMcpConfiguration(
      CodexMcpServerConfiguration configuration) {
    final name = NativeString(configuration.name);
    final environmentId = NativeString(configuration.environmentId);
    final transport = createMcpTransport(configuration.transport);
    final omitValues = configuration.omitToolsFrom
            ?.map((item) => item.value)
            .toList(growable: false) ??
        const <int>[];
    final omit = omitValues.isEmpty
        ? nullptr
        : nativeMemory.allocate<Int32>(sizeOf<Int32>() * omitValues.length);
    for (var index = 0; index < omitValues.length; index++) {
      (omit + index).value = omitValues[index];
    }
    final enabled = _LeafNativeStrings(configuration.enabledTools ?? const []);
    final disabled =
        _LeafNativeStrings(configuration.disabledTools ?? const []);
    final scopes = _LeafNativeStrings(configuration.scopes ?? const []);
    final oauth = configuration.oauth == null
        ? null
        : createMcpOauth(configuration.oauth!);
    final oauthResource = configuration.oauthResource == null
        ? NativeString.absent()
        : NativeString(configuration.oauthResource!);
    final toolKeys = _LeafNativeStrings(configuration.tools.keys);
    final tools = configuration.tools.values.map(createMcpTool).toList();
    final toolHandles =
        _LeafNativeHandles(tools.map((item) => item.value).toList());
    try {
      final call = library.lookupFunction<_LeafMcpConfigurationCreateNative,
              _LeafMcpConfigurationCreateDart>(
          'codex_agent_mcp_server_configuration_create');
      return _create(
        'codex_agent_mcp_server_configuration_create',
        'codex_agent_mcp_server_configuration_destroy',
        (output) => call(
          context,
          name.view,
          transport.value,
          configuration.authentication == null ? 0 : 1,
          configuration.authentication?.value ?? 0,
          environmentId.view,
          configuration.isEnabled ? 1 : 0,
          configuration.isRequired ? 1 : 0,
          configuration.supportsParallelToolCalls ? 1 : 0,
          configuration.omitToolsFrom == null ? 0 : 1,
          omit,
          omitValues.length,
          configuration.startupTimeoutSeconds == null ? 0 : 1,
          configuration.startupTimeoutSeconds ?? 0,
          configuration.toolTimeoutSeconds == null ? 0 : 1,
          configuration.toolTimeoutSeconds ?? 0,
          configuration.defaultToolApproval == null ? 0 : 1,
          configuration.defaultToolApproval?.value ?? 0,
          configuration.enabledTools == null ? 0 : 1,
          enabled.pointer,
          enabled.values.length,
          configuration.disabledTools == null ? 0 : 1,
          disabled.pointer,
          disabled.values.length,
          configuration.scopes == null ? 0 : 1,
          scopes.pointer,
          scopes.values.length,
          oauth == null ? 0 : 1,
          oauth?.value ?? nullptr,
          configuration.oauthResource == null ? 0 : 1,
          oauthResource.view,
          toolKeys.pointer,
          toolHandles.pointer,
          tools.length,
          output,
        ),
      );
    } finally {
      for (final tool in tools) {
        tool.destroy();
      }
      toolHandles.close();
      toolKeys.close();
      oauthResource.close();
      oauth?.destroy();
      scopes.close();
      disabled.close();
      enabled.close();
      nativeMemory.free(omit);
      transport.destroy();
      environmentId.close();
      name.close();
    }
  }

  _LeafTemporary createMcpServer(CodexMcpServer server) {
    final name = NativeString(server.name);
    final display = NativeString(server.displayName);
    final configuration = server.configuration == null
        ? null
        : createMcpConfiguration(server.configuration!);
    try {
      final call = library.lookupFunction<_LeafMcpServerCreateNative,
          _LeafMcpServerCreateDart>('codex_agent_mcp_server_create');
      return _create(
        'codex_agent_mcp_server_create',
        'codex_agent_mcp_server_destroy',
        (output) => call(
          context,
          name.view,
          display.view,
          server.authStatus.value,
          configuration?.value ?? nullptr,
          server.origin.value,
          server.canRemove ? 1 : 0,
          output,
        ),
      );
    } finally {
      configuration?.destroy();
      display.close();
      name.close();
    }
  }

  _LeafTemporary createIntegration(CodexIntegration integration) {
    late final _LeafTemporary item;
    late final String suffix;
    switch (integration) {
      case CodexConnectorIntegration(:final connector):
        item = createConnector(connector);
        suffix = 'connector';
      case CodexMcpServerIntegration(:final server):
        item = createMcpServer(server);
        suffix = 'mcp_server';
    }
    late final _LeafTemporary concrete;
    try {
      final createConcrete = library.lookupFunction<_LeafContextHandleOutNative,
              _LeafContextHandleOutDart>(
          'codex_agent_integration_${suffix}_create');
      concrete = _create(
        'codex_agent_integration_${suffix}_create',
        'codex_agent_integration_${suffix}_destroy',
        (output) => createConcrete(context, item.value, output),
      );
    } finally {
      item.destroy();
    }
    try {
      final wrap = library.lookupFunction<_LeafContextHandleOutNative,
          _LeafContextHandleOutDart>('codex_agent_integration_from_$suffix');
      return _create(
        'codex_agent_integration_from_$suffix',
        'codex_agent_integration_destroy',
        (output) => wrap(context, concrete.value, output),
      );
    } finally {
      concrete.destroy();
    }
  }
}
