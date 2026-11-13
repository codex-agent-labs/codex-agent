using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;

namespace CodexAgent.Interop;

internal static unsafe partial class NativeMethods
{
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversations_list")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ConversationsListImport(nint context, nint conversations, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation);
    internal static CodexStatus ConversationsList(nint context, nint conversations, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation)
    { var status = ConversationsListImport(context, conversations, callback, userData, out operation); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversations_read")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ConversationsReadImport(nint context, nint conversations, nint conversationId, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation);
    internal static CodexStatus ConversationsRead(nint context, nint conversations, nint conversationId, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation)
    { var status = ConversationsReadImport(context, conversations, conversationId, callback, userData, out operation); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversations_rename")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ConversationsRenameImport(nint context, nint conversations, nint conversationId, NativeStringView* name, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation);
    internal static CodexStatus ConversationsRename(nint context, nint conversations, nint conversationId, NativeStringView* name, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation)
    { var status = ConversationsRenameImport(context, conversations, conversationId, name, callback, userData, out operation); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversations_delete")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ConversationsDeleteImport(nint context, nint conversations, nint conversationId, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation);
    internal static CodexStatus ConversationsDelete(nint context, nint conversations, nint conversationId, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation)
    { var status = ConversationsDeleteImport(context, conversations, conversationId, callback, userData, out operation); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_operation_conversation_summaries_count")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus OperationConversationSummariesCountImport(nint context, nint operation, out nuint count);
    internal static CodexStatus OperationConversationSummariesCount(nint context, nint operation, out nuint count)
    { var status = OperationConversationSummariesCountImport(context, operation, out count); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_operation_conversation_summary_at")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus OperationConversationSummaryAtImport(nint context, nint operation, nuint index, out nint summary);
    internal static CodexStatus OperationConversationSummaryAt(nint context, nint operation, nuint index, out nint summary)
    { var status = OperationConversationSummaryAtImport(context, operation, index, out summary); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_operation_conversation_value")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus OperationConversationValueImport(nint context, nint operation, out nint conversation);
    internal static CodexStatus OperationConversationValue(nint context, nint operation, out nint conversation)
    { var status = OperationConversationValueImport(context, operation, out conversation); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversation_send_request")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ConversationSendRequestImport(nint context, nint conversation, nint request, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation);
    internal static CodexStatus ConversationSendRequest(nint context, nint conversation, nint request, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation)
    { var status = ConversationSendRequestImport(context, conversation, request, callback, userData, out operation); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversation_current_messages_get")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ConversationCurrentMessagesGetImport(nint context, nint conversation, out nint snapshot);
    internal static CodexStatus ConversationCurrentMessagesGet(nint context, nint conversation, out nint snapshot)
    { var status = ConversationCurrentMessagesGetImport(context, conversation, out snapshot); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversation_current_messages_subscribe")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ConversationCurrentMessagesSubscribeImport(nint context, nint conversation, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription);
    internal static CodexStatus ConversationCurrentMessagesSubscribe(nint context, nint conversation, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription)
    { var status = ConversationCurrentMessagesSubscribeImport(context, conversation, callback, userData, out subscription); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversation_current_messages_count")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ConversationCurrentMessagesCountImport(nint context, nint snapshot, out nuint count);
    internal static CodexStatus ConversationCurrentMessagesCount(nint context, nint snapshot, out nuint count)
    { var status = ConversationCurrentMessagesCountImport(context, snapshot, out count); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversation_current_messages_at")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ConversationCurrentMessagesAtImport(nint context, nint snapshot, nuint index, out nint message);
    internal static CodexStatus ConversationCurrentMessagesAt(nint context, nint snapshot, nuint index, out nint message)
    { var status = ConversationCurrentMessagesAtImport(context, snapshot, index, out message); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversation_active_turn_progress_get")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ConversationActiveTurnProgressGetImport(nint context, nint conversation, out nint snapshot);
    internal static CodexStatus ConversationActiveTurnProgressGet(nint context, nint conversation, out nint snapshot)
    { var status = ConversationActiveTurnProgressGetImport(context, conversation, out snapshot); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversation_active_turn_progress_subscribe")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ConversationActiveTurnProgressSubscribeImport(nint context, nint conversation, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription);
    internal static CodexStatus ConversationActiveTurnProgressSubscribe(nint context, nint conversation, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription)
    { var status = ConversationActiveTurnProgressSubscribeImport(context, conversation, callback, userData, out subscription); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversation_active_turn_progress_has_value")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ConversationActiveTurnProgressHasValueImport(nint context, nint snapshot, out int present);
    internal static CodexStatus ConversationActiveTurnProgressHasValue(nint context, nint snapshot, out int present)
    { var status = ConversationActiveTurnProgressHasValueImport(context, snapshot, out present); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversation_active_turn_progress_value")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ConversationActiveTurnProgressValueImport(nint context, nint snapshot, out nint progress);
    internal static CodexStatus ConversationActiveTurnProgressValue(nint context, nint snapshot, out nint progress)
    { var status = ConversationActiveTurnProgressValueImport(context, snapshot, out progress); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversation_can_cancel_turn_get")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ConversationCanCancelTurnGetImport(nint context, nint conversation, out nint snapshot);
    internal static CodexStatus ConversationCanCancelTurnGet(nint context, nint conversation, out nint snapshot)
    { var status = ConversationCanCancelTurnGetImport(context, conversation, out snapshot); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversation_can_cancel_turn_subscribe")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ConversationCanCancelTurnSubscribeImport(nint context, nint conversation, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription);
    internal static CodexStatus ConversationCanCancelTurnSubscribe(nint context, nint conversation, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription)
    { var status = ConversationCanCancelTurnSubscribeImport(context, conversation, callback, userData, out subscription); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversation_can_reload_get")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ConversationCanReloadGetImport(nint context, nint conversation, out nint snapshot);
    internal static CodexStatus ConversationCanReloadGet(nint context, nint conversation, out nint snapshot)
    { var status = ConversationCanReloadGetImport(context, conversation, out snapshot); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversation_can_reload_subscribe")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ConversationCanReloadSubscribeImport(nint context, nint conversation, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription);
    internal static CodexStatus ConversationCanReloadSubscribe(nint context, nint conversation, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription)
    { var status = ConversationCanReloadSubscribeImport(context, conversation, callback, userData, out subscription); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversation_can_run_shell_command_get")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ConversationCanRunShellCommandGetImport(nint context, nint conversation, out nint snapshot);
    internal static CodexStatus ConversationCanRunShellCommandGet(nint context, nint conversation, out nint snapshot)
    { var status = ConversationCanRunShellCommandGetImport(context, conversation, out snapshot); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversation_can_run_shell_command_subscribe")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ConversationCanRunShellCommandSubscribeImport(nint context, nint conversation, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription);
    internal static CodexStatus ConversationCanRunShellCommandSubscribe(nint context, nint conversation, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription)
    { var status = ConversationCanRunShellCommandSubscribeImport(context, conversation, callback, userData, out subscription); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversation_can_start_turn_get")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ConversationCanStartTurnGetImport(nint context, nint conversation, out nint snapshot);
    internal static CodexStatus ConversationCanStartTurnGet(nint context, nint conversation, out nint snapshot)
    { var status = ConversationCanStartTurnGetImport(context, conversation, out snapshot); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversation_can_start_turn_subscribe")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ConversationCanStartTurnSubscribeImport(nint context, nint conversation, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription);
    internal static CodexStatus ConversationCanStartTurnSubscribe(nint context, nint conversation, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription)
    { var status = ConversationCanStartTurnSubscribeImport(context, conversation, callback, userData, out subscription); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversation_is_turn_active_get")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ConversationIsTurnActiveGetImport(nint context, nint conversation, out nint snapshot);
    internal static CodexStatus ConversationIsTurnActiveGet(nint context, nint conversation, out nint snapshot)
    { var status = ConversationIsTurnActiveGetImport(context, conversation, out snapshot); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversation_is_turn_active_subscribe")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ConversationIsTurnActiveSubscribeImport(nint context, nint conversation, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription);
    internal static CodexStatus ConversationIsTurnActiveSubscribe(nint context, nint conversation, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription)
    { var status = ConversationIsTurnActiveSubscribeImport(context, conversation, callback, userData, out subscription); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversation_summary_destroy")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus ConversationSummaryDestroy(nint context, ref nint summary);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversation_summary_conversation_id")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus ConversationSummaryConversationId(nint context, nint summary, out nint id);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversation_summary_title_copy")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus ConversationSummaryTitleCopy(nint context, nint summary, byte* buffer, nuint capacity, out nuint required);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversation_summary_updated_at_epoch_seconds")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus ConversationSummaryUpdatedAtEpochSeconds(nint context, nint summary, out long value);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversation_value_destroy")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus ConversationValueDestroy(nint context, ref nint conversation);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversation_value_summary")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus ConversationValueSummary(nint context, nint conversation, out nint summary);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversation_value_messages_count")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus ConversationValueMessagesCount(nint context, nint conversation, out nuint count);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversation_value_message_at")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus ConversationValueMessageAt(nint context, nint conversation, nuint index, out nint message);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_message_destroy")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus MessageDestroy(nint context, ref nint message);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_message_id_copy")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus MessageIdCopy(nint context, nint message, byte* buffer, nuint capacity, out nuint required);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_message_has_client_message_id")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus MessageHasClientMessageId(nint context, nint message, out int present);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_message_client_message_id_copy")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus MessageClientMessageIdCopy(nint context, nint message, byte* buffer, nuint capacity, out nuint required);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_message_role")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus MessageRole(nint context, nint message, out CodexMessageRole role);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_message_text_copy")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus MessageTextCopy(nint context, nint message, byte* buffer, nuint capacity, out nuint required);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_message_collaboration_mode")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus MessageCollaborationMode(nint context, nint message, out CodexCollaborationMode mode);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_message_has_reasoning")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus MessageHasReasoning(nint context, nint message, out int present);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_message_reasoning_copy")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus MessageReasoningCopy(nint context, nint message, byte* buffer, nuint capacity, out nuint required);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_message_has_plan")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus MessageHasPlan(nint context, nint message, out int present);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_message_plan_copy")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus MessagePlanCopy(nint context, nint message, byte* buffer, nuint capacity, out nuint required);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_message_has_shell_command")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus MessageHasShellCommand(nint context, nint message, out int present);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_message_shell_command_copy")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus MessageShellCommandCopy(nint context, nint message, byte* buffer, nuint capacity, out nuint required);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_message_exit_code")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus MessageExitCode(nint context, nint message, out int present, out int value);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_message_capabilities_count")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus MessageCapabilitiesCount(nint context, nint message, out nuint count);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_message_has_capability")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus MessageHasCapability(nint context, nint message, CodexCapability capability, out int present);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_message_invocations_count")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus MessageInvocationsCount(nint context, nint message, out nuint count);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_message_invocation_at")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus MessageInvocationAt(nint context, nint message, nuint index, out nint invocation);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_invocation_destroy")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus InvocationDestroy(nint context, ref nint invocation);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_invocation_kind")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus InvocationKind(nint context, nint invocation, out int kind);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_invocation_plugin")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus InvocationPlugin(nint context, nint invocation, out nint plugin);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_invocation_skill")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus InvocationSkill(nint context, nint invocation, out nint skill);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_invocation_plugin_create")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus InvocationPluginCreate(nint context, NativeStringView* name, NativeStringView* uri, out nint plugin);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_invocation_plugin_destroy")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus InvocationPluginDestroy(nint context, ref nint plugin);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_invocation_plugin_name_copy")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus InvocationPluginNameCopy(nint context, nint plugin, byte* buffer, nuint capacity, out nuint required);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_invocation_plugin_uri_copy")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus InvocationPluginUriCopy(nint context, nint plugin, byte* buffer, nuint capacity, out nuint required);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_invocation_skill_create")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus InvocationSkillCreate(nint context, NativeStringView* name, NativeStringView* path, out nint skill);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_invocation_skill_destroy")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus InvocationSkillDestroy(nint context, ref nint skill);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_invocation_skill_name_copy")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus InvocationSkillNameCopy(nint context, nint skill, byte* buffer, nuint capacity, out nuint required);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_invocation_skill_path_copy")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus InvocationSkillPathCopy(nint context, nint skill, byte* buffer, nuint capacity, out nuint required);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_invocation_from_plugin")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus InvocationFromPlugin(nint context, nint plugin, out nint invocation);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_invocation_from_skill")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus InvocationFromSkill(nint context, nint skill, out nint invocation);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_turn_request_create")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus TurnRequestCreate(
        nint context, NativeStringView* prompt,
        int hasClientMessageId, NativeStringView* clientMessageId,
        int hasModel, NativeStringView* model,
        int hasEffort, NativeStringView* effort,
        int hasServiceTier, NativeStringView* serviceTier,
        CodexApprovalPreset approvalPreset,
        CodexCapability* capabilities, nuint capabilityCount,
        nint* invocations, nuint invocationCount,
        CodexCollaborationMode collaborationMode,
        out nint request);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_turn_request_destroy")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus TurnRequestDestroy(nint context, ref nint request);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_turn_progress_destroy")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus TurnProgressDestroy(nint context, ref nint progress);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_turn_progress_text_copy")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus TurnProgressTextCopy(nint context, nint progress, byte* buffer, nuint capacity, out nuint required);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_turn_progress_commentary_copy")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus TurnProgressCommentaryCopy(nint context, nint progress, byte* buffer, nuint capacity, out nuint required);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_turn_progress_reasoning_copy")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus TurnProgressReasoningCopy(nint context, nint progress, byte* buffer, nuint capacity, out nuint required);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_turn_progress_plan_copy")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus TurnProgressPlanCopy(nint context, nint progress, byte* buffer, nuint capacity, out nuint required);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_turn_progress_has_plan_progress")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus TurnProgressHasPlanProgress(nint context, nint progress, out int present);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_turn_progress_plan_progress")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus TurnProgressPlanProgress(nint context, nint progress, out nint planProgress);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_turn_progress_shell_output_copy")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus TurnProgressShellOutputCopy(nint context, nint progress, byte* buffer, nuint capacity, out nuint required);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_turn_progress_shell_exit_code")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus TurnProgressShellExitCode(nint context, nint progress, out int present, out int value);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_turn_progress_work_activity")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus TurnProgressWorkActivity(nint context, nint progress, out int present, out CodexWorkActivity value);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_turn_progress_hook_activities_count")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus TurnProgressHookActivitiesCount(nint context, nint progress, out nuint count);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_turn_progress_hook_activity_at")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus TurnProgressHookActivityAt(nint context, nint progress, nuint index, out nint activity);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_turn_progress_is_truncated")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus TurnProgressIsTruncated(nint context, nint progress, out int value);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_plan_progress_destroy")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus PlanProgressDestroy(nint context, ref nint progress);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_plan_progress_has_explanation")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus PlanProgressHasExplanation(nint context, nint progress, out int present);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_plan_progress_explanation_copy")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus PlanProgressExplanationCopy(nint context, nint progress, byte* buffer, nuint capacity, out nuint required);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_plan_progress_steps_count")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus PlanProgressStepsCount(nint context, nint progress, out nuint count);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_plan_progress_step_at")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus PlanProgressStepAt(nint context, nint progress, nuint index, out nint step);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_plan_step_destroy")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus PlanStepDestroy(nint context, ref nint step);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_plan_step_text_copy")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus PlanStepTextCopy(nint context, nint step, byte* buffer, nuint capacity, out nuint required);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_plan_step_status")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus PlanStepStatus(nint context, nint step, out CodexPlanStepStatus status);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_hook_activity_destroy")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookActivityDestroy(nint context, ref nint activity);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_hook_activity_id_copy")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookActivityIdCopy(nint context, nint activity, byte* buffer, nuint capacity, out nuint required);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_hook_activity_event_name_copy")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookActivityEventNameCopy(nint context, nint activity, byte* buffer, nuint capacity, out nuint required);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_hook_activity_handler_type_copy")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookActivityHandlerTypeCopy(nint context, nint activity, byte* buffer, nuint capacity, out nuint required);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_hook_activity_status")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookActivityStatus(nint context, nint activity, out CodexHookRunStatus status);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_hook_activity_has_status_message")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookActivityHasStatusMessage(nint context, nint activity, out int present);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_hook_activity_status_message_copy")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookActivityStatusMessageCopy(nint context, nint activity, byte* buffer, nuint capacity, out nuint required);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_hook_activity_details_count")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookActivityDetailsCount(nint context, nint activity, out nuint count);
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_hook_activity_detail_copy_at")][UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus HookActivityDetailCopyAt(nint context, nint activity, nuint index, byte* buffer, nuint capacity, out nuint required);
}
