using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;

namespace CodexAgent.Interop;

internal static unsafe partial class NativeMethods
{
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_operation_models_count")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus OperationModelsCountImport(nint context, nint operation, out nuint count);
    internal static CodexStatus OperationModelsCount(nint context, nint operation, out nuint count)
    { var status = OperationModelsCountImport(context, operation, out count); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_operation_model_at")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus OperationModelAtImport(nint context, nint operation, nuint index, out nint model);
    internal static CodexStatus OperationModelAt(nint context, nint operation, nuint index, out nint model)
    { var status = OperationModelAtImport(context, operation, index, out model); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_operation_model")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus OperationModelImport(nint context, nint operation, out nint model);
    internal static CodexStatus OperationModel(nint context, nint operation, out nint model)
    { var status = OperationModelImport(context, operation, out model); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_operation_string_copy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus OperationStringCopyImport(nint context, nint operation, byte* buffer, nuint capacity, out nuint required);
    internal static CodexStatus OperationStringCopy(nint context, nint operation, byte* buffer, nuint capacity, out nuint required)
    { var status = OperationStringCopyImport(context, operation, buffer, capacity, out required); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_operation_has_service_tier")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus OperationHasServiceTierImport(nint context, nint operation, out int value);
    internal static CodexStatus OperationHasServiceTier(nint context, nint operation, out int value)
    { var status = OperationHasServiceTierImport(context, operation, out value); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_operation_service_tier")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus OperationServiceTierImport(nint context, nint operation, out nint tier);
    internal static CodexStatus OperationServiceTier(nint context, nint operation, out nint tier)
    { var status = OperationServiceTierImport(context, operation, out tier); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_operation_skill_catalog")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus OperationSkillCatalogImport(nint context, nint operation, out nint value);
    internal static CodexStatus OperationSkillCatalog(nint context, nint operation, out nint value)
    { var status = OperationSkillCatalogImport(context, operation, out value); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_operation_skill_chunk")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus OperationSkillChunkImport(nint context, nint operation, out nint value);
    internal static CodexStatus OperationSkillChunk(nint context, nint operation, out nint value)
    { var status = OperationSkillChunkImport(context, operation, out value); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_operation_skill")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus OperationSkillImport(nint context, nint operation, out nint value);
    internal static CodexStatus OperationSkill(nint context, nint operation, out nint value)
    { var status = OperationSkillImport(context, operation, out value); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_operation_hook_catalog")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus OperationHookCatalogImport(nint context, nint operation, out nint value);
    internal static CodexStatus OperationHookCatalog(nint context, nint operation, out nint value)
    { var status = OperationHookCatalogImport(context, operation, out value); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_operation_hook")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus OperationHookImport(nint context, nint operation, out nint value);
    internal static CodexStatus OperationHook(nint context, nint operation, out nint value)
    { var status = OperationHookImport(context, operation, out value); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_operation_plugin_catalog")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus OperationPluginCatalogImport(nint context, nint operation, out nint value);
    internal static CodexStatus OperationPluginCatalog(nint context, nint operation, out nint value)
    { var status = OperationPluginCatalogImport(context, operation, out value); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_operation_plugin_detail")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus OperationPluginDetailImport(nint context, nint operation, out nint value);
    internal static CodexStatus OperationPluginDetail(nint context, nint operation, out nint value)
    { var status = OperationPluginDetailImport(context, operation, out value); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_operation_plugin_install_result")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus OperationPluginInstallResultImport(nint context, nint operation, out nint value);
    internal static CodexStatus OperationPluginInstallResult(nint context, nint operation, out nint value)
    { var status = OperationPluginInstallResultImport(context, operation, out value); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_operation_connectors_count")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus OperationConnectorsCountImport(nint context, nint operation, out nuint count);
    internal static CodexStatus OperationConnectorsCount(nint context, nint operation, out nuint count)
    { var status = OperationConnectorsCountImport(context, operation, out count); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_operation_connector_at")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus OperationConnectorAtImport(nint context, nint operation, nuint index, out nint value);
    internal static CodexStatus OperationConnectorAt(nint context, nint operation, nuint index, out nint value)
    { var status = OperationConnectorAtImport(context, operation, index, out value); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_operation_mcp_servers_count")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus OperationMcpServersCountImport(nint context, nint operation, out nuint count);
    internal static CodexStatus OperationMcpServersCount(nint context, nint operation, out nuint count)
    { var status = OperationMcpServersCountImport(context, operation, out count); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_operation_mcp_server_at")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus OperationMcpServerAtImport(nint context, nint operation, nuint index, out nint value);
    internal static CodexStatus OperationMcpServerAt(nint context, nint operation, nuint index, out nint value)
    { var status = OperationMcpServerAtImport(context, operation, index, out value); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_operation_mcp_server")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus OperationMcpServerImport(nint context, nint operation, out nint value);
    internal static CodexStatus OperationMcpServer(nint context, nint operation, out nint value)
    { var status = OperationMcpServerImport(context, operation, out value); RecordExactCall(); return status; }
}
