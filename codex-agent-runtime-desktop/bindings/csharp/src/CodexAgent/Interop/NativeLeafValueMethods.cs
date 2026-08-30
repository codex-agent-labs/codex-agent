using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;

namespace CodexAgent.Interop;

internal static unsafe partial class NativeMethods
{
    [LibraryImport(LibraryName, EntryPoint="codex_agent_authentication_method_api_key_create")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus AuthenticationMethodApiKeyCreate(nint c,NativeStringView* value,out nint method);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_authentication_method_api_key_destroy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus AuthenticationMethodApiKeyDestroy(nint c,ref nint method);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_authentication_method_chat_gpt_browser_create")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus AuthenticationMethodChatGptBrowserCreate(nint c,out nint method);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_authentication_method_chat_gpt_browser_destroy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus AuthenticationMethodChatGptBrowserDestroy(nint c,ref nint method);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_authentication_method_chat_gpt_device_code_create")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus AuthenticationMethodChatGptDeviceCodeCreate(nint c,out nint method);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_authentication_method_chat_gpt_device_code_destroy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus AuthenticationMethodChatGptDeviceCodeDestroy(nint c,ref nint method);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_authentication_state_destroy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus AuthenticationStateDestroy(nint c,ref nint state);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_authentication_state_status")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus AuthenticationStateStatus(nint c,nint state,out CodexAuthenticationStatus status);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_authentication_state_has_pending_sign_in_url")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus AuthenticationStateHasPendingSignInUrl(nint c,nint state,out int present);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_authentication_state_pending_sign_in_url")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus AuthenticationStatePendingSignInUrl(nint c,nint state,out nint url);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_authentication_state_has_device_verification_url")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus AuthenticationStateHasDeviceVerificationUrl(nint c,nint state,out int present);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_authentication_state_device_verification_url")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus AuthenticationStateDeviceVerificationUrl(nint c,nint state,out nint url);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_authentication_state_has_device_user_code")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus AuthenticationStateHasDeviceUserCode(nint c,nint state,out int present);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_authentication_state_device_user_code_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus AuthenticationStateDeviceUserCodeCopy(nint c,nint state,byte* buffer,nuint capacity,out nuint required);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_authentication_state_has_failure")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus AuthenticationStateHasFailure(nint c,nint state,out int present);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_authentication_state_failure")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus AuthenticationStateFailure(nint c,nint state,out nint failure);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_integration_from_connector")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus IntegrationFromConnector(nint c,nint value,out nint integration);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_integration_from_mcp_server")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus IntegrationFromMcpServer(nint c,nint value,out nint integration);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_integration_destroy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus IntegrationDestroy(nint c,ref nint integration);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_integration_kind")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus IntegrationKind(nint c,nint integration,out int kind);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_integration_connector")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus IntegrationConnector(nint c,nint integration,out nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_integration_mcp_server")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus IntegrationMcpServer(nint c,nint integration,out nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_integration_connector_create")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus IntegrationConnectorCreate(nint c,nint connector,out nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_integration_connector_destroy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus IntegrationConnectorDestroy(nint c,ref nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_integration_connector_connector")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus IntegrationConnectorConnector(nint c,nint value,out nint connector);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_integration_mcp_server_create")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus IntegrationMcpServerCreate(nint c,nint server,out nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_integration_mcp_server_destroy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus IntegrationMcpServerDestroy(nint c,ref nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_integration_mcp_server_server")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus IntegrationMcpServerServer(nint c,nint value,out nint server);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_integration_authorization_state_destroy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus IntegrationAuthorizationStateDestroy(nint c,ref nint state);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_integration_authorization_state_status")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus IntegrationAuthorizationStateStatus(nint c,nint state,out CodexIntegrationAuthorizationStatus status);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_integration_authorization_state_target")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus IntegrationAuthorizationStateTarget(nint c,nint state,out nint target);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_integration_authorization_state_failure")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus IntegrationAuthorizationStateFailure(nint c,nint state,out nint failure);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_reference_create")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginReferenceCreate(nint c,NativeStringView* id,NativeStringView* name,NativeStringView* marketplace,int hasPath,NativeStringView* path,int hasRemote,NativeStringView* remote,out nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_reference_destroy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginReferenceDestroy(nint c,ref nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_reference_id_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginReferenceIdCopy(nint c,nint value,byte* b,nuint n,out nuint r);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_reference_name_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginReferenceNameCopy(nint c,nint value,byte* b,nuint n,out nuint r);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_reference_marketplace_name_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginReferenceMarketplaceNameCopy(nint c,nint value,byte* b,nuint n,out nuint r);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_reference_has_marketplace_path")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginReferenceHasMarketplacePath(nint c,nint value,out int result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_reference_marketplace_path_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginReferenceMarketplacePathCopy(nint c,nint value,byte* b,nuint n,out nuint r);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_reference_has_remote_plugin_id")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginReferenceHasRemotePluginId(nint c,nint value,out int result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_reference_remote_plugin_id_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginReferenceRemotePluginIdCopy(nint c,nint value,byte* b,nuint n,out nuint r);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_summary_destroy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginSummaryDestroy(nint c,ref nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_summary_reference")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginSummaryReference(nint c,nint value,out nint result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_summary_display_name_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginSummaryDisplayNameCopy(nint c,nint value,byte* b,nuint n,out nuint r);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_summary_description_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginSummaryDescriptionCopy(nint c,nint value,byte* b,nuint n,out nuint r);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_summary_is_installed")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginSummaryIsInstalled(nint c,nint value,out int result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_summary_is_enabled")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginSummaryIsEnabled(nint c,nint value,out int result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_summary_install_policy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginSummaryInstallPolicy(nint c,nint value,out CodexPluginInstallPolicy result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_summary_auth_policy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginSummaryAuthPolicy(nint c,nint value,out CodexPluginAuthPolicy result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_summary_is_available")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginSummaryIsAvailable(nint c,nint value,out int result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_summary_capabilities_count")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginSummaryCapabilitiesCount(nint c,nint value,out nuint count);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_summary_capabilities_copy_at")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginSummaryCapabilitiesCopyAt(nint c,nint value,nuint index,byte* b,nuint n,out nuint r);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_summary_has_brand_color")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginSummaryHasBrandColor(nint c,nint value,out int result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_summary_brand_color_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginSummaryBrandColorCopy(nint c,nint value,byte* b,nuint n,out nuint r);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_summary_has_privacy_policy_url")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginSummaryHasPrivacyPolicyUrl(nint c,nint value,out int result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_summary_privacy_policy_url_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginSummaryPrivacyPolicyUrlCopy(nint c,nint value,byte* b,nuint n,out nuint r);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_summary_has_terms_of_service_url")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginSummaryHasTermsOfServiceUrl(nint c,nint value,out int result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_summary_terms_of_service_url_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginSummaryTermsOfServiceUrlCopy(nint c,nint value,byte* b,nuint n,out nuint r);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_summary_has_website_url")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginSummaryHasWebsiteUrl(nint c,nint value,out int result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_summary_website_url_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginSummaryWebsiteUrlCopy(nint c,nint value,byte* b,nuint n,out nuint r);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_skill_destroy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginSkillDestroy(nint c,ref nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_skill_name_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginSkillNameCopy(nint c,nint value,byte* b,nuint n,out nuint r);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_skill_description_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginSkillDescriptionCopy(nint c,nint value,byte* b,nuint n,out nuint r);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_skill_is_enabled")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginSkillIsEnabled(nint c,nint value,out int result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_skill_has_path")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginSkillHasPath(nint c,nint value,out int result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_skill_path_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginSkillPathCopy(nint c,nint value,byte* b,nuint n,out nuint r);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_catalog_destroy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginCatalogDestroy(nint c,ref nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_catalog_plugins_count")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginCatalogPluginsCount(nint c,nint value,out nuint count);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_catalog_plugins_at")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginCatalogPluginsAt(nint c,nint value,nuint index,out nint result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_catalog_errors_count")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginCatalogErrorsCount(nint c,nint value,out nuint count);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_catalog_errors_copy_at")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginCatalogErrorsCopyAt(nint c,nint value,nuint index,byte* b,nuint n,out nuint r);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_catalog_freshness")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginCatalogFreshness(nint c,nint value,out CodexCatalogFreshness result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_detail_destroy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginDetailDestroy(nint c,ref nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_detail_summary")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginDetailSummary(nint c,nint value,out nint result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_detail_description_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginDetailDescriptionCopy(nint c,nint value,byte* b,nuint n,out nuint r);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_detail_skills_count")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginDetailSkillsCount(nint c,nint value,out nuint count);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_detail_skills_at")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginDetailSkillsAt(nint c,nint value,nuint index,out nint result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_detail_connectors_count")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginDetailConnectorsCount(nint c,nint value,out nuint count);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_detail_connectors_at")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginDetailConnectorsAt(nint c,nint value,nuint index,out nint result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_detail_mcp_servers_count")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginDetailMcpServersCount(nint c,nint value,out nuint count);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_detail_mcp_servers_copy_at")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginDetailMcpServersCopyAt(nint c,nint value,nuint index,byte* b,nuint n,out nuint r);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_detail_hook_count")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginDetailHookCount(nint c,nint value,out int result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_install_result_destroy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginInstallResultDestroy(nint c,ref nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_install_result_auth_policy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginInstallResultAuthPolicy(nint c,nint value,out CodexPluginAuthPolicy result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_install_result_connectors_count")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginInstallResultConnectorsCount(nint c,nint value,out nuint count);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_install_result_connectors_at")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginInstallResultConnectorsAt(nint c,nint value,nuint index,out nint result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_install_result_has_message")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginInstallResultHasMessage(nint c,nint value,out int result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_plugin_install_result_message_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginInstallResultMessageCopy(nint c,nint value,byte* b,nuint n,out nuint r);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_handler_agent_acquire")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookHandlerAgentAcquire(nint c,out nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_handler_agent_destroy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookHandlerAgentDestroy(nint c,ref nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_handler_command_create")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookHandlerCommandCreate(nint c,NativeStringView* command,int isAsync,out nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_handler_command_destroy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookHandlerCommandDestroy(nint c,ref nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_handler_command_command_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookHandlerCommandCommandCopy(nint c,nint value,byte* b,nuint n,out nuint r);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_handler_command_is_async")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookHandlerCommandIsAsync(nint c,nint value,out int result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_handler_mcp_tool_create")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookHandlerMcpToolCreate(nint c,NativeStringView* server,NativeStringView* tool,out nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_handler_mcp_tool_destroy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookHandlerMcpToolDestroy(nint c,ref nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_handler_mcp_tool_server_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookHandlerMcpToolServerCopy(nint c,nint value,byte* b,nuint n,out nuint r);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_handler_mcp_tool_tool_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookHandlerMcpToolToolCopy(nint c,nint value,byte* b,nuint n,out nuint r);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_handler_prompt_acquire")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookHandlerPromptAcquire(nint c,out nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_handler_prompt_destroy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookHandlerPromptDestroy(nint c,ref nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_handler_from_agent")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookHandlerFromAgent(nint c,nint concrete,out nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_handler_from_command")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookHandlerFromCommand(nint c,nint concrete,out nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_handler_from_mcp_tool")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookHandlerFromMcpTool(nint c,nint concrete,out nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_handler_from_prompt")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookHandlerFromPrompt(nint c,nint concrete,out nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_handler_destroy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookHandlerDestroy(nint c,ref nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_handler_kind")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookHandlerKind(nint c,nint value,out int kind);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_handler_agent")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookHandlerAgent(nint c,nint value,out nint concrete);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_handler_command")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookHandlerCommand(nint c,nint value,out nint concrete);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_handler_mcp_tool")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookHandlerMcpTool(nint c,nint value,out nint concrete);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_handler_prompt")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookHandlerPrompt(nint c,nint value,out nint concrete);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_create")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookCreate(nint c,NativeStringView* key,NativeStringView* hash,int enabled,NativeStringView* eventName,nint handler,int managed,NativeStringView* source,NativeStringView* sourcePath,long timeout,CodexHookTrustStatus trust,int hasMatcher,NativeStringView* matcher,int hasPlugin,NativeStringView* plugin,int hasStatus,NativeStringView* status,int hasOrigin,CodexResourceOrigin origin,int canUninstall,out nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_destroy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookDestroy(nint c,ref nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_key_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookKeyCopy(nint c,nint value,byte* b,nuint n,out nuint r);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_current_hash_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookCurrentHashCopy(nint c,nint value,byte* b,nuint n,out nuint r);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_is_enabled")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookIsEnabled(nint c,nint value,out int result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_event_name_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookEventNameCopy(nint c,nint value,byte* b,nuint n,out nuint r);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_handler")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookHandler(nint c,nint value,out nint result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_is_managed")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookIsManaged(nint c,nint value,out int result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_source_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookSourceCopy(nint c,nint value,byte* b,nuint n,out nuint r);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_source_path_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookSourcePathCopy(nint c,nint value,byte* b,nuint n,out nuint r);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_timeout_seconds")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookTimeoutSeconds(nint c,nint value,out long result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_trust_status")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookTrustStatus(nint c,nint value,out CodexHookTrustStatus result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_has_matcher")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookHasMatcher(nint c,nint value,out int result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_matcher_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookMatcherCopy(nint c,nint value,byte* b,nuint n,out nuint r);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_has_plugin_id")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookHasPluginId(nint c,nint value,out int result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_plugin_id_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookPluginIdCopy(nint c,nint value,byte* b,nuint n,out nuint r);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_has_status_message")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookHasStatusMessage(nint c,nint value,out int result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_status_message_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookStatusMessageCopy(nint c,nint value,byte* b,nuint n,out nuint r);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_origin")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookOrigin(nint c,nint value,out CodexResourceOrigin result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_can_uninstall")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookCanUninstall(nint c,nint value,out int result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_catalog_destroy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookCatalogDestroy(nint c,ref nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_catalog_hooks_count")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookCatalogHooksCount(nint c,nint value,out nuint count);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_catalog_hooks_at")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookCatalogHooksAt(nint c,nint value,nuint index,out nint result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_catalog_warnings_count")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookCatalogWarningsCount(nint c,nint value,out nuint count);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_catalog_warnings_copy_at")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookCatalogWarningsCopyAt(nint c,nint value,nuint index,byte* b,nuint n,out nuint r);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_catalog_errors_count")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookCatalogErrorsCount(nint c,nint value,out nuint count);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_hook_catalog_errors_copy_at")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookCatalogErrorsCopyAt(nint c,nint value,nuint index,byte* b,nuint n,out nuint r);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_pending_approval_title_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PendingApprovalTitleCopy(nint c,nint value,byte* b,nuint n,out nuint r);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_pending_approval_details_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PendingApprovalDetailsCopy(nint c,nint value,byte* b,nuint n,out nuint r);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_pending_elicitation_elicitation")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus PendingElicitationElicitation(nint c,nint value,out nint elicitation);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_elicitation_request_id_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus ElicitationRequestIdCopy(nint c,nint value,byte* b,nuint n,out nuint r);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_elicitation_server_name_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus ElicitationServerNameCopy(nint c,nint value,byte* b,nuint n,out nuint r);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_elicitation_conversation_id")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus ElicitationConversationId(nint c,nint value,out nint id);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_elicitation_message_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus ElicitationMessageCopy(nint c,nint value,byte* b,nuint n,out nuint r);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_elicitation_has_form")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus ElicitationHasForm(nint c,nint value,out int result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_elicitation_form_count")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus ElicitationFormCount(nint c,nint value,out nuint count);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_elicitation_form_at")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus ElicitationFormAt(nint c,nint value,nuint index,out nint field);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_elicitation_has_url")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus ElicitationHasUrl(nint c,nint value,out int result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_elicitation_url_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus ElicitationUrlCopy(nint c,nint value,byte* b,nuint n,out nuint r);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_form_field_name_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormFieldNameCopy(nint c,nint value,byte* b,nuint n,out nuint r);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_form_field_title_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormFieldTitleCopy(nint c,nint value,byte* b,nuint n,out nuint r);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_form_field_has_description")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormFieldHasDescription(nint c,nint value,out int result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_form_field_description_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormFieldDescriptionCopy(nint c,nint value,byte* b,nuint n,out nuint r);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_form_field_is_required")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormFieldIsRequired(nint c,nint value,out int result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_form_field_is_secret")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormFieldIsSecret(nint c,nint value,out int result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_form_field_type")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormFieldType(nint c,nint value,out CodexFormFieldType result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_form_field_format")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormFieldFormat(nint c,nint value,out int present,out CodexFormStringFormat result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_form_field_has_default_value")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormFieldHasDefaultValue(nint c,nint value,out int result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_form_field_default_value")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormFieldDefaultValue(nint c,nint value,out nint result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_form_field_minimum")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormFieldMinimum(nint c,nint value,out int present,out double result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_form_field_maximum")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormFieldMaximum(nint c,nint value,out int present,out double result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_form_field_minimum_length")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormFieldMinimumLength(nint c,nint value,out int present,out long result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_form_field_maximum_length")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormFieldMaximumLength(nint c,nint value,out int present,out long result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_form_field_options_count")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormFieldOptionsCount(nint c,nint value,out nuint count);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_form_field_option_at")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormFieldOptionAt(nint c,nint value,nuint index,out nint result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_form_field_allows_other")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormFieldAllowsOther(nint c,nint value,out int result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_form_field_minimum_selections")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormFieldMinimumSelections(nint c,nint value,out int present,out long result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_form_field_maximum_selections")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormFieldMaximumSelections(nint c,nint value,out int present,out long result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_form_option_value_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormOptionValueCopy(nint c,nint value,byte* b,nuint n,out nuint r);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_form_option_title_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormOptionTitleCopy(nint c,nint value,byte* b,nuint n,out nuint r);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_form_option_has_description")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormOptionHasDescription(nint c,nint value,out int result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_form_option_description_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormOptionDescriptionCopy(nint c,nint value,byte* b,nuint n,out nuint r);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_interaction_state_pending_count")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus InteractionStatePendingCount(nint c,nint value,out nuint count);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_interaction_state_pending_at")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus InteractionStatePendingAt(nint c,nint value,nuint index,out nint result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_interaction_state_is_resolving")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus InteractionStateIsResolvingValue(nint c,nint value,nint pending,out int result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_interaction_state_has_failure")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus InteractionStateHasFailure(nint c,nint value,out int result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_interaction_state_failure")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus InteractionStateFailure(nint c,nint value,out nint result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_mcp_environment_variable_create")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpEnvironmentVariableCreate(nint c,NativeStringView* name,int hasSource,CodexMcpEnvironmentSource source,out nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_mcp_oauth_configuration_create")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpOauthConfigurationCreate(nint c,int hasClient,NativeStringView* client,int hasPort,int port,out nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_mcp_tool_configuration_create")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpToolConfigurationCreate(nint c,int hasApproval,CodexMcpToolApproval approval,out nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_mcp_transport_http_create")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpTransportHttpCreate(nint c,NativeStringView* url,int hasBearer,NativeStringView* bearer,int hasHeaders,NativeStringView* headerKeys,NativeStringView* headerValues,nuint headerCount,int hasEnvironmentHeaders,NativeStringView* environmentKeys,NativeStringView* environmentValues,nuint environmentCount,int hasHelper,NativeStringView* helper,out nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_mcp_transport_stdio_create")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpTransportStdioCreate(nint c,NativeStringView* command,NativeStringView* arguments,nuint argumentCount,int hasWorkingDirectory,NativeStringView* workingDirectory,int hasEnvironment,NativeStringView* environmentKeys,NativeStringView* environmentValues,nuint environmentCount,nint* forwarded,nuint forwardedCount,out nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_mcp_transport_from_http")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpTransportFromHttp(nint c,nint concrete,out nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_mcp_transport_from_stdio")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpTransportFromStdio(nint c,nint concrete,out nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_mcp_server_configuration_create")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpServerConfigurationCreate(nint c,NativeStringView* name,nint transport,int hasAuthentication,CodexMcpAuthentication authentication,NativeStringView* environmentId,int enabled,int required,int parallel,int hasOmit,CodexMcpToolExposureSurface* omit,nuint omitCount,int hasStartup,double startup,int hasToolTimeout,double toolTimeout,int hasDefaultApproval,CodexMcpToolApproval defaultApproval,int hasEnabled,NativeStringView* enabledTools,nuint enabledCount,int hasDisabled,NativeStringView* disabledTools,nuint disabledCount,int hasScopes,NativeStringView* scopes,nuint scopeCount,int hasOauth,nint oauth,int hasOauthResource,NativeStringView* oauthResource,NativeStringView* toolKeys,nint* tools,nuint toolCount,out nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_mcp_server_create")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpServerCreate(nint c,NativeStringView* name,NativeStringView* displayName,CodexMcpAuthStatus authStatus,nint configuration,CodexResourceOrigin origin,int canRemove,out nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_service_tier_create")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus ServiceTierCreate(nint c, NativeStringView* id, NativeStringView* name, NativeStringView* description, out nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_service_tier_destroy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus ServiceTierDestroy(nint c, ref nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_service_tier_id_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus ServiceTierIdCopy(nint c, nint value, byte* buffer, nuint capacity, out nuint required);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_service_tier_name_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus ServiceTierNameCopy(nint c, nint value, byte* buffer, nuint capacity, out nuint required);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_service_tier_description_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus ServiceTierDescriptionCopy(nint c, nint value, byte* buffer, nuint capacity, out nuint required);

    [LibraryImport(LibraryName, EntryPoint="codex_agent_model_create")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus ModelCreate(nint c, NativeStringView* id, NativeStringView* displayName, NativeStringView* description, NativeStringView* efforts, nuint effortCount, NativeStringView* defaultEffort, int isDefault, nint* tiers, nuint tierCount, int hasDefaultTier, NativeStringView* defaultTier, out nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_model_destroy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus ModelDestroy(nint c, ref nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_model_id_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus ModelIdCopy(nint c,nint value,byte* buffer,nuint capacity,out nuint required);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_model_display_name_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus ModelDisplayNameCopy(nint c,nint value,byte* buffer,nuint capacity,out nuint required);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_model_description_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus ModelDescriptionCopy(nint c,nint value,byte* buffer,nuint capacity,out nuint required);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_model_supported_efforts_count")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus ModelSupportedEffortsCount(nint c,nint value,out nuint count);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_model_supported_effort_copy_at")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus ModelSupportedEffortCopyAt(nint c,nint value,nuint index,byte* buffer,nuint capacity,out nuint required);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_model_default_effort_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus ModelDefaultEffortCopy(nint c,nint value,byte* buffer,nuint capacity,out nuint required);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_model_is_default")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus ModelIsDefault(nint c,nint value,out int result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_model_service_tiers_count")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus ModelServiceTiersCount(nint c,nint value,out nuint count);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_model_service_tier_at")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus ModelServiceTierAt(nint c,nint value,nuint index,out nint tier);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_model_has_default_service_tier")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus ModelHasDefaultServiceTier(nint c,nint value,out int result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_model_default_service_tier_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus ModelDefaultServiceTierCopy(nint c,nint value,byte* buffer,nuint capacity,out nuint required);

    [LibraryImport(LibraryName, EntryPoint="codex_agent_connector_create")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus ConnectorCreate(nint c,NativeStringView* id,NativeStringView* name,NativeStringView* description,int hasInstallUrl,NativeStringView* installUrl,int accessible,int enabled,NativeStringView* plugins,nuint count,out nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_connector_destroy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus ConnectorDestroy(nint c,ref nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_connector_id_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus ConnectorIdCopy(nint c,nint value,byte* buffer,nuint capacity,out nuint required);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_connector_name_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus ConnectorNameCopy(nint c,nint value,byte* buffer,nuint capacity,out nuint required);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_connector_description_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus ConnectorDescriptionCopy(nint c,nint value,byte* buffer,nuint capacity,out nuint required);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_connector_has_install_url")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus ConnectorHasInstallUrl(nint c,nint value,out int result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_connector_install_url_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus ConnectorInstallUrlCopy(nint c,nint value,byte* buffer,nuint capacity,out nuint required);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_connector_is_accessible")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus ConnectorIsAccessible(nint c,nint value,out int result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_connector_is_enabled")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus ConnectorIsEnabled(nint c,nint value,out int result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_connector_plugin_names_count")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus ConnectorPluginNamesCount(nint c,nint value,out nuint count);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_connector_plugin_names_copy_at")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus ConnectorPluginNamesCopyAt(nint c,nint value,nuint index,byte* buffer,nuint capacity,out nuint required);

    [LibraryImport(LibraryName, EntryPoint="codex_agent_skill_create")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus SkillCreate(nint c,NativeStringView* name,NativeStringView* displayName,NativeStringView* description,NativeStringView* path,CodexSkillScope scope,int enabled,int hasBrand,NativeStringView* brand,NativeStringView* dependencies,nuint dependencyCount,int canUninstall,int hasOrigin,CodexResourceOrigin origin,out nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_skill_destroy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus SkillDestroy(nint c,ref nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_skill_name_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus SkillNameCopy(nint c,nint value,byte* buffer,nuint capacity,out nuint required);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_skill_display_name_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus SkillDisplayNameCopy(nint c,nint value,byte* buffer,nuint capacity,out nuint required);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_skill_description_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus SkillDescriptionCopy(nint c,nint value,byte* buffer,nuint capacity,out nuint required);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_skill_path_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus SkillPathCopy(nint c,nint value,byte* buffer,nuint capacity,out nuint required);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_skill_scope")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus SkillScope(nint c,nint value,out CodexSkillScope result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_skill_is_enabled")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus SkillIsEnabled(nint c,nint value,out int result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_skill_has_brand_color")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus SkillHasBrandColor(nint c,nint value,out int result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_skill_brand_color_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus SkillBrandColorCopy(nint c,nint value,byte* buffer,nuint capacity,out nuint required);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_skill_dependencies_count")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus SkillDependenciesCount(nint c,nint value,out nuint count);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_skill_dependencies_copy_at")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus SkillDependenciesCopyAt(nint c,nint value,nuint index,byte* buffer,nuint capacity,out nuint required);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_skill_can_uninstall")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus SkillCanUninstall(nint c,nint value,out int result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_skill_origin")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus SkillOrigin(nint c,nint value,out CodexResourceOrigin result);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_skill_catalog_destroy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus SkillCatalogDestroy(nint c,ref nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_skill_catalog_skills_count")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus SkillCatalogSkillsCount(nint c,nint value,out nuint count);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_skill_catalog_skills_at")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus SkillCatalogSkillsAt(nint c,nint value,nuint index,out nint skill);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_skill_catalog_errors_count")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus SkillCatalogErrorsCount(nint c,nint value,out nuint count);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_skill_catalog_errors_copy_at")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus SkillCatalogErrorsCopyAt(nint c,nint value,nuint index,byte* buffer,nuint capacity,out nuint required);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_skill_chunk_destroy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus SkillChunkDestroy(nint c,ref nint value);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_skill_chunk_content_copy")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus SkillChunkContentCopy(nint c,nint value,byte* buffer,nuint capacity,out nuint required);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_skill_chunk_next_offset")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus SkillChunkNextOffset(nint c,nint value,out int present,out long offset);
    [LibraryImport(LibraryName, EntryPoint="codex_agent_skill_chunk_total_bytes")][UnmanagedCallConv(CallConvs=[typeof(CallConvCdecl)])]
    internal static partial CodexStatus SkillChunkTotalBytes(nint c,nint value,out long result);
}
