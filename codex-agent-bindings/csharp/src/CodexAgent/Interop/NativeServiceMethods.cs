using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;

namespace CodexAgent.Interop;

internal static unsafe partial class NativeMethods
{
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_agent_authentication")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus AgentAuthenticationImport(nint context, nint agent, out nint service);
    internal static CodexStatus AgentAuthentication(nint context, nint agent, out nint service)
    { var status = AgentAuthenticationImport(context, agent, out service); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_agent_interactions")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus AgentInteractionsImport(nint context, nint agent, out nint service);
    internal static CodexStatus AgentInteractions(nint context, nint agent, out nint service)
    { var status = AgentInteractionsImport(context, agent, out service); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_agent_integration_authorization")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus AgentIntegrationAuthorizationImport(nint context, nint agent, out nint service);
    internal static CodexStatus AgentIntegrationAuthorization(nint context, nint agent, out nint service)
    { var status = AgentIntegrationAuthorizationImport(context, agent, out service); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_agent_models")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus AgentModelsImport(nint context, nint agent, out nint service);
    internal static CodexStatus AgentModels(nint context, nint agent, out nint service)
    { var status = AgentModelsImport(context, agent, out service); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_agent_skills")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus AgentSkillsImport(nint context, nint agent, out nint service);
    internal static CodexStatus AgentSkills(nint context, nint agent, out nint service)
    { var status = AgentSkillsImport(context, agent, out service); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_agent_hooks")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus AgentHooksImport(nint context, nint agent, out nint service);
    internal static CodexStatus AgentHooks(nint context, nint agent, out nint service)
    { var status = AgentHooksImport(context, agent, out service); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_agent_plugins")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus AgentPluginsImport(nint context, nint agent, out nint service);
    internal static CodexStatus AgentPlugins(nint context, nint agent, out nint service)
    { var status = AgentPluginsImport(context, agent, out service); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_agent_connectors")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus AgentConnectorsImport(nint context, nint agent, out nint service);
    internal static CodexStatus AgentConnectors(nint context, nint agent, out nint service)
    { var status = AgentConnectorsImport(context, agent, out service); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_agent_mcp_servers")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus AgentMcpServersImport(nint context, nint agent, out nint service);
    internal static CodexStatus AgentMcpServers(nint context, nint agent, out nint service)
    { var status = AgentMcpServersImport(context, agent, out service); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_agent_workspace")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus AgentWorkspaceImport(nint context, nint agent, out nint workspace);
    internal static CodexStatus AgentWorkspace(nint context, nint agent, out nint workspace)
    { var status = AgentWorkspaceImport(context, agent, out workspace); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_workspace_destroy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus WorkspaceDestroy(nint context, ref nint workspace);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_workspace_path_copy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus WorkspacePathCopy(nint context, nint workspace, byte* buffer, nuint capacity, out nuint required);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_workspace_display_name_copy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus WorkspaceDisplayNameCopy(nint context, nint workspace, byte* buffer, nuint capacity, out nuint required);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_authentication_release")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus AuthenticationRelease(nint context, ref nint service);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_interactions_release")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus InteractionsRelease(nint context, ref nint service);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_integration_authorization_release")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus IntegrationAuthorizationRelease(nint context, ref nint service);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_models_release")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus ModelsRelease(nint context, ref nint service);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_skills_release")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus SkillsRelease(nint context, ref nint service);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_hooks_release")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus HooksRelease(nint context, ref nint service);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_plugins_release")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus PluginsRelease(nint context, ref nint service);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_connectors_release")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus ConnectorsRelease(nint context, ref nint service);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_servers_release")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpServersRelease(nint context, ref nint service);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_skills_is_available")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus SkillsIsAvailableImport(nint context, nint service, out int value);
    internal static CodexStatus SkillsIsAvailable(nint context, nint service, out int value)
    { var status = SkillsIsAvailableImport(context, service, out value); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_hooks_is_available")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus HooksIsAvailableImport(nint context, nint service, out int value);
    internal static CodexStatus HooksIsAvailable(nint context, nint service, out int value)
    { var status = HooksIsAvailableImport(context, service, out value); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_plugins_is_available")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus PluginsIsAvailableImport(nint context, nint service, out int value);
    internal static CodexStatus PluginsIsAvailable(nint context, nint service, out int value)
    { var status = PluginsIsAvailableImport(context, service, out value); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_connectors_is_available")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ConnectorsIsAvailableImport(nint context, nint service, out int value);
    internal static CodexStatus ConnectorsIsAvailable(nint context, nint service, out int value)
    { var status = ConnectorsIsAvailableImport(context, service, out value); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_servers_is_available")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus McpServersIsAvailableImport(nint context, nint service, out int value);
    internal static CodexStatus McpServersIsAvailable(nint context, nint service, out int value)
    { var status = McpServersIsAvailableImport(context, service, out value); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_authentication_authenticate_api_key")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus AuthenticationAuthenticateApiKeyImport(nint context, nint service, nint method, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation);
    internal static CodexStatus AuthenticationAuthenticateApiKey(nint context, nint service, nint method, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation)
    { var status = AuthenticationAuthenticateApiKeyImport(context, service, method, callback, userData, out operation); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_authentication_authenticate_chat_gpt_browser")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus AuthenticationAuthenticateChatGptBrowserImport(nint context, nint service, nint method, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation);
    internal static CodexStatus AuthenticationAuthenticateChatGptBrowser(nint context, nint service, nint method, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation)
    { var status = AuthenticationAuthenticateChatGptBrowserImport(context, service, method, callback, userData, out operation); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_authentication_authenticate_chat_gpt_device_code")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus AuthenticationAuthenticateChatGptDeviceCodeImport(nint context, nint service, nint method, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation);
    internal static CodexStatus AuthenticationAuthenticateChatGptDeviceCode(nint context, nint service, nint method, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation)
    { var status = AuthenticationAuthenticateChatGptDeviceCodeImport(context, service, method, callback, userData, out operation); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_authentication_cancel")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus AuthenticationCancelImport(nint context, nint service, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation);
    internal static CodexStatus AuthenticationCancel(nint context, nint service, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation)
    { var status = AuthenticationCancelImport(context, service, callback, userData, out operation); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_authentication_sign_out")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus AuthenticationSignOutImport(nint context, nint service, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation);
    internal static CodexStatus AuthenticationSignOut(nint context, nint service, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation)
    { var status = AuthenticationSignOutImport(context, service, callback, userData, out operation); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_integration_authorization_authorize")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus IntegrationAuthorizationAuthorizeImport(nint context, nint service, nint target, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation);
    internal static CodexStatus IntegrationAuthorizationAuthorize(nint context, nint service, nint target, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation)
    { var status = IntegrationAuthorizationAuthorizeImport(context, service, target, callback, userData, out operation); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_integration_authorization_cancel")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus IntegrationAuthorizationCancelImport(nint context, nint service, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation);
    internal static CodexStatus IntegrationAuthorizationCancel(nint context, nint service, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation)
    { var status = IntegrationAuthorizationCancelImport(context, service, callback, userData, out operation); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_models_list")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ModelsListImport(nint context, nint service, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation);
    internal static CodexStatus ModelsList(nint context, nint service, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation)
    { var status = ModelsListImport(context, service, callback, userData, out operation); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_models_resolve")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ModelsResolveImport(nint context, nint service, CodexResolution resolution, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation);
    internal static CodexStatus ModelsResolve(nint context, nint service, CodexResolution resolution, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation)
    { var status = ModelsResolveImport(context, service, resolution, callback, userData, out operation); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_models_resolve_effort")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ModelsResolveEffortImport(nint context, nint service, nint model, CodexResolution resolution, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation);
    internal static CodexStatus ModelsResolveEffort(nint context, nint service, nint model, CodexResolution resolution, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation)
    { var status = ModelsResolveEffortImport(context, service, model, resolution, callback, userData, out operation); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_models_resolve_service_tier")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ModelsResolveServiceTierImport(nint context, nint service, nint model, CodexResolution resolution, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation);
    internal static CodexStatus ModelsResolveServiceTier(nint context, nint service, nint model, CodexResolution resolution, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation)
    { var status = ModelsResolveServiceTierImport(context, service, model, resolution, callback, userData, out operation); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_skills_list")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus SkillsListImport(nint context, nint service, int forceReload, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation);
    internal static CodexStatus SkillsList(nint context, nint service, int forceReload, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation)
    { var status = SkillsListImport(context, service, forceReload, callback, userData, out operation); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_skills_read")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus SkillsReadImport(nint context, nint service, NativeStringView* path, long offset, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation);
    internal static CodexStatus SkillsRead(nint context, nint service, NativeStringView* path, long offset, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation)
    { var status = SkillsReadImport(context, service, path, offset, callback, userData, out operation); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_skills_install")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus SkillsInstallImport(nint context, nint service, NativeStringView* directory, CodexInstallationScope scope, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation);
    internal static CodexStatus SkillsInstall(nint context, nint service, NativeStringView* directory, CodexInstallationScope scope, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation)
    { var status = SkillsInstallImport(context, service, directory, scope, callback, userData, out operation); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_skills_uninstall")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus SkillsUninstallImport(nint context, nint service, nint skill, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation);
    internal static CodexStatus SkillsUninstall(nint context, nint service, nint skill, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation)
    { var status = SkillsUninstallImport(context, service, skill, callback, userData, out operation); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_hooks_list")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus HooksListImport(nint context, nint service, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation);
    internal static CodexStatus HooksList(nint context, nint service, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation)
    { var status = HooksListImport(context, service, callback, userData, out operation); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_hooks_install")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus HooksInstallImport(nint context, nint service, NativeStringView* directory, CodexInstallationScope scope, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation);
    internal static CodexStatus HooksInstall(nint context, nint service, NativeStringView* directory, CodexInstallationScope scope, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation)
    { var status = HooksInstallImport(context, service, directory, scope, callback, userData, out operation); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_hooks_uninstall")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus HooksUninstallImport(nint context, nint service, nint hook, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation);
    internal static CodexStatus HooksUninstall(nint context, nint service, nint hook, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation)
    { var status = HooksUninstallImport(context, service, hook, callback, userData, out operation); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_hooks_trust")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus HooksTrustImport(nint context, nint service, nint hook, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation);
    internal static CodexStatus HooksTrust(nint context, nint service, nint hook, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation)
    { var status = HooksTrustImport(context, service, hook, callback, userData, out operation); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_plugins_list")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus PluginsListImport(nint context, nint service, int forceReload, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation);
    internal static CodexStatus PluginsList(nint context, nint service, int forceReload, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation)
    { var status = PluginsListImport(context, service, forceReload, callback, userData, out operation); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_plugins_read")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus PluginsReadImport(nint context, nint service, nint plugin, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation);
    internal static CodexStatus PluginsRead(nint context, nint service, nint plugin, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation)
    { var status = PluginsReadImport(context, service, plugin, callback, userData, out operation); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_plugins_install")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus PluginsInstallImport(nint context, nint service, nint plugin, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation);
    internal static CodexStatus PluginsInstall(nint context, nint service, nint plugin, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation)
    { var status = PluginsInstallImport(context, service, plugin, callback, userData, out operation); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_plugins_uninstall")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus PluginsUninstallImport(nint context, nint service, nint plugin, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation);
    internal static CodexStatus PluginsUninstall(nint context, nint service, nint plugin, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation)
    { var status = PluginsUninstallImport(context, service, plugin, callback, userData, out operation); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_connectors_list")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ConnectorsListImport(nint context, nint service, int forceReload, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation);
    internal static CodexStatus ConnectorsList(nint context, nint service, int forceReload, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation)
    { var status = ConnectorsListImport(context, service, forceReload, callback, userData, out operation); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_servers_list")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus McpServersListImport(nint context, nint service, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation);
    internal static CodexStatus McpServersList(nint context, nint service, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation)
    { var status = McpServersListImport(context, service, callback, userData, out operation); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_servers_add")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus McpServersAddImport(nint context, nint service, nint configuration, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation);
    internal static CodexStatus McpServersAdd(nint context, nint service, nint configuration, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation)
    { var status = McpServersAddImport(context, service, configuration, callback, userData, out operation); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_servers_remove")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus McpServersRemoveImport(nint context, nint service, nint server, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation);
    internal static CodexStatus McpServersRemove(nint context, nint service, nint server, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation)
    { var status = McpServersRemoveImport(context, service, server, callback, userData, out operation); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_interactions_open_url")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus InteractionsOpenUrlImport(nint context, nint service, nint elicitation, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation);
    internal static CodexStatus InteractionsOpenUrl(nint context, nint service, nint elicitation, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation)
    { var status = InteractionsOpenUrlImport(context, service, elicitation, callback, userData, out operation); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_interactions_resolve_approval")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus InteractionsResolveApprovalImport(nint context, nint service, nint approval, CodexApprovalDecision decision, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation);
    internal static CodexStatus InteractionsResolveApproval(nint context, nint service, nint approval, CodexApprovalDecision decision, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation)
    { var status = InteractionsResolveApprovalImport(context, service, approval, decision, callback, userData, out operation); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_interactions_resolve_elicitation")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus InteractionsResolveElicitationImport(nint context, nint service, nint elicitation, nint response, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation);
    internal static CodexStatus InteractionsResolveElicitation(nint context, nint service, nint elicitation, nint response, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation)
    { var status = InteractionsResolveElicitationImport(context, service, elicitation, response, callback, userData, out operation); RecordExactCall(); return status; }
}
