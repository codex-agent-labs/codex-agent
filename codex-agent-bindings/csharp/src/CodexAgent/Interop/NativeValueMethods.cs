using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;

namespace CodexAgent.Interop;

internal static unsafe partial class NativeMethods
{
    private static Action<string>? exactCallObserver;

    internal static void SetExactCallObserver(Action<string>? observer) =>
        Volatile.Write(ref exactCallObserver, observer);

    private static void RecordExactCall([CallerMemberName] string wrapper = "") =>
        Volatile.Read(ref exactCallObserver)?.Invoke(wrapper);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_failure_create")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus FailureCreate(nint context, NativeStringView* code, NativeStringView* message, int recoverable, out nint failure);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversation_id_create")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus ConversationIdCreate(nint context, NativeStringView* value, out nint conversationId);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversation_id_destroy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus ConversationIdDestroy(nint context, ref nint conversationId);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_conversation_id_value_copy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus ConversationIdValueCopy(nint context, nint conversationId, byte* buffer, nuint capacity, out nuint required);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_form_boolean_value_create")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormBooleanCreate(nint context, int value, out nint result);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_form_boolean_value_destroy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormBooleanDestroy(nint context, ref nint value);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_form_boolean_value_value")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormBooleanValue(nint context, nint value, out int result);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_form_number_value_create")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormNumberCreate(nint context, double value, out nint result);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_form_number_value_destroy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormNumberDestroy(nint context, ref nint value);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_form_number_value_value")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormNumberValue(nint context, nint value, out double result);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_form_text_value_create")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormTextCreate(nint context, NativeStringView* value, out nint result);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_form_text_value_destroy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormTextDestroy(nint context, ref nint value);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_form_text_value_value_copy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormTextValueCopy(nint context, nint value, byte* buffer, nuint capacity, out nuint required);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_form_text_list_value_create")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormTextListCreate(nint context, NativeStringView* values, nuint count, out nint result);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_form_text_list_value_destroy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormTextListDestroy(nint context, ref nint value);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_form_text_list_value_count")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormTextListCount(nint context, nint value, out nuint count);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_form_text_list_value_copy_at")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormTextListCopyAt(nint context, nint value, nuint index, byte* buffer, nuint capacity, out nuint required);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_form_value_from_boolean")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormValueFromBoolean(nint context, nint value, out nint result);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_form_value_from_number")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormValueFromNumber(nint context, nint value, out nint result);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_form_value_from_text")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormValueFromText(nint context, nint value, out nint result);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_form_value_from_text_list")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormValueFromTextList(nint context, nint value, out nint result);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_form_value_destroy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormValueDestroy(nint context, ref nint value);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_form_value_kind")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormValueKind(nint context, nint value, out int kind);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_form_value_boolean")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormValueBoolean(nint context, nint value, ref nint result);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_form_value_number")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormValueNumber(nint context, nint value, ref nint result);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_form_value_text")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormValueText(nint context, nint value, ref nint result);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_form_value_text_list")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormValueTextList(nint context, nint value, ref nint result);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_form_option_create")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormOptionCreate(nint context, NativeStringView* value, int hasTitle, NativeStringView* title, int hasDescription, NativeStringView* description, out nint option);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_form_option_destroy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormOptionDestroy(nint context, ref nint option);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_form_field_create")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormFieldCreate(
        nint context, NativeStringView* name, NativeStringView* title,
        int hasDescription, NativeStringView* description, int isRequired, CodexFormFieldType type,
        nint* options, nuint optionCount, int hasDefaultValue, nint defaultValue,
        int hasMinimum, double minimum, int hasMaximum, double maximum,
        int hasFormat, CodexFormStringFormat format,
        int hasMinimumLength, long minimumLength, int hasMaximumLength, long maximumLength,
        int hasMinimumSelections, long minimumSelections, int hasMaximumSelections, long maximumSelections,
        int allowsOther, int isSecret, out nint field);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_form_field_destroy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormFieldDestroy(nint context, ref nint field);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_form_field_accepts")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus FormFieldAcceptsImport(nint context, nint field, nint value, out int accepts);

    internal static CodexStatus FormFieldAccepts(nint context, nint field, nint value, out int accepts)
    {
        var status = FormFieldAcceptsImport(context, field, value, out accepts);
        RecordExactCall();
        return status;
    }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_elicitation_create")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus ElicitationCreate(
        nint context, NativeStringView* requestId, NativeStringView* serverName, nint conversationId,
        NativeStringView* message, int hasForm, nint* form, nuint formCount,
        int hasUrl, NativeStringView* url, out nint elicitation);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_elicitation_destroy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus ElicitationDestroy(nint context, ref nint elicitation);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_form_content_create")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormContentCreate(nint context, NativeStringView* keys, nint* values, nuint count, out nint content);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_form_content_destroy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormContentDestroy(nint context, ref nint content);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_form_content_count")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormContentCount(nint context, nint content, out nuint count);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_form_content_key_copy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormContentKeyCopy(nint context, nint content, nuint index, byte* buffer, nuint capacity, out nuint required);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_form_content_value_at")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus FormContentValueAt(nint context, nint content, NativeStringView* key, ref nint value);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_elicitation_initial_values")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ElicitationInitialValuesImport(nint context, nint elicitation, out nint content);

    internal static CodexStatus ElicitationInitialValues(nint context, nint elicitation, out nint content)
    {
        var status = ElicitationInitialValuesImport(context, elicitation, out content);
        RecordExactCall();
        return status;
    }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_elicitation_validate")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ElicitationValidateImport(
        nint context, nint elicitation, nint content, out nint validation);

    internal static CodexStatus ElicitationValidate(
        nint context, nint elicitation, nint content, out nint validation)
    {
        var status = ElicitationValidateImport(context, elicitation, content, out validation);
        RecordExactCall();
        return status;
    }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_elicitation_validation_destroy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus ElicitationValidationDestroy(nint context, ref nint validation);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_elicitation_validation_issue_count")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus ElicitationValidationIssueCount(nint context, nint validation, out nuint count);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_elicitation_validation_issue_at")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus ElicitationValidationIssueAt(nint context, nint validation, nuint index, ref nint issue);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_elicitation_validation_issue_destroy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus ElicitationValidationIssueDestroy(nint context, ref nint issue);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_elicitation_validation_issue_field_name_copy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus ElicitationValidationIssueFieldNameCopy(nint context, nint issue, byte* buffer, nuint capacity, out nuint required);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_elicitation_validation_issue_reason")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus ElicitationValidationIssueReason(nint context, nint issue, out CodexElicitationValidationReason reason);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_elicitation_accept")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ElicitationAcceptImport(
        nint context, nint elicitation, nint content, out nint response);

    internal static CodexStatus ElicitationAccept(nint context, nint elicitation, nint content, out nint response)
    {
        var status = ElicitationAcceptImport(context, elicitation, content, out response);
        RecordExactCall();
        return status;
    }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_elicitation_accepts")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ElicitationAcceptsImport(
        nint context, nint elicitation, nint response, out int accepts);

    internal static CodexStatus ElicitationAccepts(nint context, nint elicitation, nint response, out int accepts)
    {
        var status = ElicitationAcceptsImport(context, elicitation, response, out accepts);
        RecordExactCall();
        return status;
    }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_elicitation_response_create")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus ElicitationResponseCreate(nint context, CodexElicitationAction action, NativeStringView* keys, nint* values, nuint count, out nint response);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_elicitation_response_destroy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus ElicitationResponseDestroy(nint context, ref nint response);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_elicitation_response_action")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus ElicitationResponseAction(nint context, nint response, out CodexElicitationAction action);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_elicitation_response_content_count")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus ElicitationResponseContentCount(nint context, nint response, out nuint count);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_elicitation_response_content_value")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus ElicitationResponseContentValue(nint context, nint response, NativeStringView* key, ref nint value);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_elicitation_response_decline")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ElicitationResponseDeclineImport(nint context, out nint response);

    internal static CodexStatus ElicitationResponseDecline(nint context, out nint response)
    {
        var status = ElicitationResponseDeclineImport(context, out response);
        RecordExactCall();
        return status;
    }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_elicitation_response_cancel")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus ElicitationResponseCancelImport(nint context, out nint response);

    internal static CodexStatus ElicitationResponseCancel(nint context, out nint response)
    {
        var status = ElicitationResponseCancelImport(context, out response);
        RecordExactCall();
        return status;
    }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_pending_approval_create")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus PendingApprovalCreate(nint context, NativeStringView* requestId, nint conversationId, NativeStringView* title, NativeStringView* details, out nint approval);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_pending_approval_destroy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus PendingApprovalDestroy(nint context, ref nint approval);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_pending_approval_request_id_copy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus PendingApprovalRequestIdCopy(nint context, nint approval, byte* buffer, nuint capacity, out nuint required);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_pending_approval_conversation_id")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus PendingApprovalConversationId(nint context, nint approval, ref nint conversationId);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_pending_elicitation_create")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus PendingElicitationCreate(nint context, nint elicitation, out nint pending);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_pending_elicitation_destroy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus PendingElicitationDestroy(nint context, ref nint pending);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_pending_elicitation_request_id_copy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus PendingElicitationRequestIdCopy(nint context, nint pending, byte* buffer, nuint capacity, out nuint required);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_pending_elicitation_conversation_id")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus PendingElicitationConversationId(nint context, nint pending, ref nint conversationId);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_pending_interaction_from_approval")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus PendingInteractionFromApproval(nint context, nint approval, out nint interaction);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_pending_interaction_from_elicitation")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus PendingInteractionFromElicitation(nint context, nint elicitation, out nint interaction);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_pending_interaction_destroy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus PendingInteractionDestroy(nint context, ref nint interaction);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_pending_interaction_kind")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus PendingInteractionKind(nint context, nint interaction, out int kind);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_pending_interaction_approval")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus PendingInteractionApproval(nint context, nint interaction, ref nint approval);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_pending_interaction_elicitation")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus PendingInteractionElicitation(nint context, nint interaction, ref nint elicitation);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_interaction_state_create")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus InteractionStateCreate(nint context, nint* pending, nuint pendingCount, NativeStringView* resolvingIds, nuint resolvingCount, int hasFailure, nint failure, out nint state);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_interaction_state_destroy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus InteractionStateDestroy(nint context, ref nint state);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_interaction_state_is_resolving")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus InteractionStateIsResolvingImport(
        nint context, nint state, nint interaction, out int resolving);

    internal static CodexStatus InteractionStateIsResolving(
        nint context, nint state, nint interaction, out int resolving)
    {
        var status = InteractionStateIsResolvingImport(context, state, interaction, out resolving);
        RecordExactCall();
        return status;
    }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_interaction_state_resolving_request_ids_contains")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus InteractionStateResolvingRequestIdsContains(
        nint context, nint state, NativeStringView* requestId, out int contains);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_interaction_state_pending_for")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus InteractionStatePendingForImport(
        nint context, nint state, nint conversationId, out nint pending);

    internal static CodexStatus InteractionStatePendingFor(
        nint context, nint state, nint conversationId, out nint pending)
    {
        var status = InteractionStatePendingForImport(context, state, conversationId, out pending);
        RecordExactCall();
        return status;
    }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_pending_interaction_list_destroy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus PendingInteractionListDestroy(nint context, ref nint pending);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_pending_interaction_list_count")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus PendingInteractionListCount(nint context, nint pending, out nuint count);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_pending_interaction_list_at")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus PendingInteractionListAt(nint context, nint pending, nuint index, ref nint interaction);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_authorization_url_chat_gpt")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus AuthorizationUrlChatGptImport(
        nint context, NativeStringView* value, out nint url);

    internal static CodexStatus AuthorizationUrlChatGpt(nint context, NativeStringView* value, out nint url)
    {
        var status = AuthorizationUrlChatGptImport(context, value, out url);
        RecordExactCall();
        return status;
    }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_authorization_url_external")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus AuthorizationUrlExternalImport(
        nint context, NativeStringView* value, out nint url);

    internal static CodexStatus AuthorizationUrlExternal(nint context, NativeStringView* value, out nint url)
    {
        var status = AuthorizationUrlExternalImport(context, value, out url);
        RecordExactCall();
        return status;
    }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_authorization_url_destroy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus AuthorizationUrlDestroy(nint context, ref nint url);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_authorization_url_value_copy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus AuthorizationUrlValueCopy(nint context, nint url, byte* buffer, nuint capacity, out nuint required);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_authorization_url_purpose")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus AuthorizationUrlPurpose(nint context, nint url, out CodexAuthorizationPurpose purpose);
}
