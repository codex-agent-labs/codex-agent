using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;

namespace CodexAgent.Interop;

[StructLayout(LayoutKind.Sequential)]
internal unsafe struct NativeStringView
{
    internal byte* Data;
    internal nuint Size;
}

[StructLayout(LayoutKind.Sequential)]
internal unsafe struct NativeClientInfo
{
    internal uint StructSize;
    internal NativeStringView Name;
    internal NativeStringView Title;
    internal NativeStringView Version;
}

[StructLayout(LayoutKind.Sequential)]
internal unsafe struct NativeHostOptions
{
    internal uint StructSize;
    internal NativeStringView BundleDirectory;
    internal NativeStringView DataDirectory;
    internal NativeClientInfo ClientInfo;
}

[StructLayout(LayoutKind.Sequential)]
internal unsafe struct NativePathWorkspaceSelection
{
    internal uint StructSize;
    internal NativeStringView Path;
}

[StructLayout(LayoutKind.Sequential)]
internal unsafe struct NativeConversationOpenOptions
{
    internal uint StructSize;
    internal int HasConversationId;
    internal NativeStringView ConversationId;
    internal int HasApprovalPreset;
    internal CodexApprovalPreset ApprovalPreset;
    internal int HasServiceTier;
    internal NativeStringView ServiceTier;
}

internal static unsafe partial class NativeMethods
{
    internal const string LibraryName = "codex_agent";
    internal const uint AbiVersion = 0x010D0000;

    static NativeMethods() => NativeLibraryLoader.Initialize();

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_abi_version")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial uint GetAbiVersion();

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_abi_is_compatible")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial int IsAbiCompatible(uint requestedVersion);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_context_create")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus ContextCreate(out nint context);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_context_destroy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus ContextDestroy(ref nint context);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_host_create")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus HostCreateImport(nint context, NativeHostOptions* options, out nint host);
    internal static CodexStatus HostCreate(nint context, NativeHostOptions* options, out nint host)
    { var status = HostCreateImport(context, options, out host); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_host_release")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus HostRelease(nint context, ref nint host);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_host_start")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus HostStartImport(nint context, nint host, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation);
    internal static CodexStatus HostStart(nint context, nint host, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation)
    { var status = HostStartImport(context, host, callback, userData, out operation); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_host_select_workspace")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus HostSelectWorkspaceImport(nint context, nint host, NativePathWorkspaceSelection* selection, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation);
    internal static CodexStatus HostSelectWorkspace(nint context, nint host, NativePathWorkspaceSelection* selection, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation)
    { var status = HostSelectWorkspaceImport(context, host, selection, callback, userData, out operation); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_host_close")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus HostCloseImport(nint context, nint host, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation);
    internal static CodexStatus HostClose(nint context, nint host, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation)
    { var status = HostCloseImport(context, host, callback, userData, out operation); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_host_state_get")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus HostStateGetImport(nint context, nint host, out nint snapshot);
    internal static CodexStatus HostStateGet(nint context, nint host, out nint snapshot)
    { var status = HostStateGetImport(context, host, out snapshot); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_host_state_subscribe")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus HostStateSubscribeImport(nint context, nint host, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription);
    internal static CodexStatus HostStateSubscribe(nint context, nint host, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription)
    { var status = HostStateSubscribeImport(context, host, callback, userData, out subscription); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_agent_release")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus AgentRelease(nint context, ref nint agent);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_agent_conversations")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus AgentConversationsImport(nint context, nint agent, out nint conversations);
    internal static CodexStatus AgentConversations(nint context, nint agent, out nint conversations)
    { var status = AgentConversationsImport(context, agent, out conversations); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversations_release")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus ConversationsRelease(nint context, ref nint conversations);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversations_active_get")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ConversationsActiveGetImport(nint context, nint conversations, out nint snapshot);
    internal static CodexStatus ConversationsActiveGet(nint context, nint conversations, out nint snapshot)
    { var status = ConversationsActiveGetImport(context, conversations, out snapshot); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversations_active_subscribe")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ConversationsActiveSubscribeImport(nint context, nint conversations, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription);
    internal static CodexStatus ConversationsActiveSubscribe(nint context, nint conversations, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription)
    { var status = ConversationsActiveSubscribeImport(context, conversations, callback, userData, out subscription); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversations_open")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ConversationsOpenImport(nint context, nint conversations, NativeConversationOpenOptions* options, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation);
    internal static CodexStatus ConversationsOpen(nint context, nint conversations, NativeConversationOpenOptions* options, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation)
    { var status = ConversationsOpenImport(context, conversations, options, callback, userData, out operation); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversation_release")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus ConversationRelease(nint context, ref nint conversation);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversation_is_same")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus ConversationIsSame(nint context, nint left, nint right, out int same);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversation_send")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ConversationSendImport(nint context, nint conversation, NativeStringView* prompt, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation);
    internal static CodexStatus ConversationSend(nint context, nint conversation, NativeStringView* prompt, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation)
    { var status = ConversationSendImport(context, conversation, prompt, callback, userData, out operation); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversation_run_shell_command")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ConversationRunShellCommandImport(nint context, nint conversation, NativeStringView* command, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation);
    internal static CodexStatus ConversationRunShellCommand(nint context, nint conversation, NativeStringView* command, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation)
    { var status = ConversationRunShellCommandImport(context, conversation, command, callback, userData, out operation); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversation_reload")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ConversationReloadImport(nint context, nint conversation, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation);
    internal static CodexStatus ConversationReload(nint context, nint conversation, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation)
    { var status = ConversationReloadImport(context, conversation, callback, userData, out operation); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversation_cancel_turn")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ConversationCancelTurnImport(nint context, nint conversation, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation);
    internal static CodexStatus ConversationCancelTurn(nint context, nint conversation, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation)
    { var status = ConversationCancelTurnImport(context, conversation, callback, userData, out operation); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversation_close")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ConversationCloseImport(nint context, nint conversation, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation);
    internal static CodexStatus ConversationClose(nint context, nint conversation, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation)
    { var status = ConversationCloseImport(context, conversation, callback, userData, out operation); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversation_state_get")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ConversationStateGetImport(nint context, nint conversation, out nint snapshot);
    internal static CodexStatus ConversationStateGet(nint context, nint conversation, out nint snapshot)
    { var status = ConversationStateGetImport(context, conversation, out snapshot); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversation_state_subscribe")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ConversationStateSubscribeImport(nint context, nint conversation, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription);
    internal static CodexStatus ConversationStateSubscribe(nint context, nint conversation, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription)
    { var status = ConversationStateSubscribeImport(context, conversation, callback, userData, out subscription); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_operation_cancel")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus OperationCancel(nint context, nint operation);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_operation_result")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus OperationResultImport(nint context, nint operation, out CodexStatus result);

    internal static CodexStatus OperationResult(nint context, nint operation, out CodexStatus result)
    {
        var status = OperationResultImport(context, operation, out result);
        RecordExactCall();
        return status;
    }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_operation_conversation")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus OperationConversationImport(nint context, nint conversations, nint operation, out nint conversation);
    internal static CodexStatus OperationConversation(nint context, nint conversations, nint operation, out nint conversation)
    { var status = OperationConversationImport(context, conversations, operation, out conversation); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_operation_failure")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus OperationFailure(nint context, nint operation, out nint failure);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_operation_destroy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus OperationDestroy(nint context, ref nint operation);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_subscription_destroy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus SubscriptionDestroy(nint context, ref nint subscription);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_snapshot_destroy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus SnapshotDestroy(nint context, ref nint snapshot);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_host_state_kind")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus HostStateKindImport(nint context, nint snapshot, out CodexHostStateKind kind);
    internal static CodexStatus HostStateKind(nint context, nint snapshot, out CodexHostStateKind kind)
    { var status = HostStateKindImport(context, snapshot, out kind); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_host_state_agent")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus HostStateAgentImport(nint context, nint host, nint snapshot, out nint agent);
    internal static CodexStatus HostStateAgent(nint context, nint host, nint snapshot, out nint agent)
    { var status = HostStateAgentImport(context, host, snapshot, out agent); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_host_state_failure")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus HostStateFailure(nint context, nint snapshot, out nint failure);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_host_state_has_workspace")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus HostStateHasWorkspace(nint context, nint snapshot, out int hasWorkspace);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_host_state_workspace_path_copy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus HostStateWorkspacePathCopy(nint context, nint snapshot, byte* buffer, nuint capacity, out nuint required);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_host_state_workspace_display_name_copy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus HostStateWorkspaceDisplayNameCopy(nint context, nint snapshot, byte* buffer, nuint capacity, out nuint required);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_host_state_requirement_reason")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus HostStateRequirementReason(nint context, nint snapshot, out CodexWorkspaceSelectionReason reason);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_host_state_requirement_message_copy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus HostStateRequirementMessageCopy(nint context, nint snapshot, byte* buffer, nuint capacity, out nuint required);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_active_conversation")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ActiveConversationImport(nint context, nint conversations, nint snapshot, out nint conversation);
    internal static CodexStatus ActiveConversation(nint context, nint conversations, nint snapshot, out nint conversation)
    { var status = ActiveConversationImport(context, conversations, snapshot, out conversation); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversation_state_status")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus ConversationStateStatus(nint context, nint snapshot, out CodexConversationStatus status);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversation_state_failure")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus ConversationStateFailure(nint context, nint snapshot, out nint failure);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_failure_release")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus FailureRelease(nint context, ref nint failure);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_failure_code_copy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus FailureCodeCopy(nint context, nint failure, byte* buffer, nuint capacity, out nuint required);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_failure_message_copy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus FailureMessageCopy(nint context, nint failure, byte* buffer, nuint capacity, out nuint required);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_failure_is_recoverable")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus FailureIsRecoverable(nint context, nint failure, out int recoverable);
}
