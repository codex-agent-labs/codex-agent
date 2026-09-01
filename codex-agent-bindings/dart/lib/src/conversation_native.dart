import 'dart:convert';
import 'dart:ffi';

import 'errors.dart';
import 'ffi.dart';
import 'models.dart';
import 'residual_models.dart';

final class CodexNativeTurnRequest extends Opaque {}

typedef ConversationsIdOperationNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeConversations>,
  Pointer<Void>,
  Pointer<NativeFunction<OperationCallbackNative>>,
  Pointer<Void>,
  Pointer<Pointer<CodexNativeOperation>>,
);
typedef ConversationsIdOperationDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeConversations>,
  Pointer<Void>,
  Pointer<NativeFunction<OperationCallbackNative>>,
  Pointer<Void>,
  Pointer<Pointer<CodexNativeOperation>>,
);
typedef ConversationsRenameNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeConversations>,
  Pointer<Void>,
  Pointer<CodexStringView>,
  Pointer<NativeFunction<OperationCallbackNative>>,
  Pointer<Void>,
  Pointer<Pointer<CodexNativeOperation>>,
);
typedef ConversationsRenameDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeConversations>,
  Pointer<Void>,
  Pointer<CodexStringView>,
  Pointer<NativeFunction<OperationCallbackNative>>,
  Pointer<Void>,
  Pointer<Pointer<CodexNativeOperation>>,
);
typedef ConversationRequestOperationNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeConversation>,
  Pointer<CodexNativeTurnRequest>,
  Pointer<NativeFunction<OperationCallbackNative>>,
  Pointer<Void>,
  Pointer<Pointer<CodexNativeOperation>>,
);
typedef ConversationRequestOperationDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexNativeConversation>,
  Pointer<CodexNativeTurnRequest>,
  Pointer<NativeFunction<OperationCallbackNative>>,
  Pointer<Void>,
  Pointer<Pointer<CodexNativeOperation>>,
);

typedef ConversationDestroyNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Pointer<Void>>,
);
typedef ConversationDestroyDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Pointer<Void>>,
);
typedef ConversationStringStringHandleOutNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  Pointer<Pointer<Void>>,
);
typedef ConversationStringStringHandleOutDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  Pointer<Pointer<Void>>,
);
typedef ConversationHandleHandleOutNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Pointer<Void>>,
);
typedef ConversationHandleHandleOutDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Pointer<Void>>,
);
typedef ConversationHandleIntOutNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Int32>,
);
typedef ConversationHandleIntOutDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Int32>,
);
typedef ConversationHandleTwoIntsOutNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Int32>,
  Pointer<Int32>,
);
typedef ConversationHandleTwoIntsOutDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Int32>,
  Pointer<Int32>,
);
typedef ConversationHandleSizeOutNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Size>,
);
typedef ConversationHandleSizeOutDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Size>,
);
typedef ConversationHandleIndexHandleOutNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Size,
  Pointer<Pointer<Void>>,
);
typedef ConversationHandleIndexHandleOutDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  int,
  Pointer<Pointer<Void>>,
);
typedef ConversationHandleIntIntOutNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Int32,
  Pointer<Int32>,
);
typedef ConversationHandleIntIntOutDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  int,
  Pointer<Int32>,
);
typedef ConversationCopyStringNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Uint8>,
  Size,
  Pointer<Size>,
);
typedef ConversationCopyStringDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Uint8>,
  int,
  Pointer<Size>,
);
typedef ConversationCopyStringAtNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Size,
  Pointer<Uint8>,
  Size,
  Pointer<Size>,
);
typedef ConversationCopyStringAtDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  int,
  Pointer<Uint8>,
  int,
  Pointer<Size>,
);
typedef ConversationTurnRequestCreateNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  Int32,
  Pointer<CodexStringView>,
  Int32,
  Pointer<CodexStringView>,
  Int32,
  Pointer<CodexStringView>,
  Int32,
  Pointer<CodexStringView>,
  Int32,
  Pointer<Int32>,
  Size,
  Pointer<Pointer<Void>>,
  Size,
  Int32,
  Pointer<Pointer<Void>>,
);
typedef ConversationTurnRequestCreateDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  int,
  Pointer<CodexStringView>,
  int,
  Pointer<CodexStringView>,
  int,
  Pointer<CodexStringView>,
  int,
  Pointer<CodexStringView>,
  int,
  Pointer<Int32>,
  int,
  Pointer<Pointer<Void>>,
  int,
  int,
  Pointer<Pointer<Void>>,
);

final class ConversationNativeApi {
  ConversationNativeApi(NativeApi core)
      : conversationsRead = core.library.lookupFunction<
            ConversationsIdOperationNative,
            ConversationsIdOperationDart>('codex_agent_conversations_read'),
        conversationsRename = core.library
            .lookupFunction<ConversationsRenameNative, ConversationsRenameDart>(
                'codex_agent_conversations_rename'),
        conversationsDelete = core.library.lookupFunction<
            ConversationsIdOperationNative,
            ConversationsIdOperationDart>('codex_agent_conversations_delete'),
        conversationSendRequest = core.library.lookupFunction<
                ConversationRequestOperationNative,
                ConversationRequestOperationDart>(
            'codex_agent_conversation_send_request'),
        currentMessagesGet = core.library.lookupFunction<
                CodexGetSnapshotNative<CodexNativeConversation>,
                CodexGetSnapshotDart<CodexNativeConversation>>(
            'codex_agent_conversation_current_messages_get'),
        currentMessagesSubscribe = core.library.lookupFunction<
                CodexSubscribeNative<CodexNativeConversation>,
                CodexSubscribeDart<CodexNativeConversation>>(
            'codex_agent_conversation_current_messages_subscribe'),
        activeProgressGet = core.library.lookupFunction<
                CodexGetSnapshotNative<CodexNativeConversation>,
                CodexGetSnapshotDart<CodexNativeConversation>>(
            'codex_agent_conversation_active_turn_progress_get'),
        activeProgressSubscribe = core.library.lookupFunction<
                CodexSubscribeNative<CodexNativeConversation>,
                CodexSubscribeDart<CodexNativeConversation>>(
            'codex_agent_conversation_active_turn_progress_subscribe'),
        conversationIdCreate = core.library.lookupFunction<
                ConversationStringHandleOutNative,
                ConversationStringHandleOutDart>(
            'codex_agent_conversation_id_create'),
        invocationPluginCreate = core.library.lookupFunction<
                ConversationStringStringHandleOutNative,
                ConversationStringStringHandleOutDart>(
            'codex_agent_invocation_plugin_create'),
        invocationPluginDestroy = core.library
            .lookupFunction<ConversationDestroyNative, ConversationDestroyDart>(
                'codex_agent_invocation_plugin_destroy'),
        invocationPluginName = core.library.lookupFunction<
                ConversationCopyStringNative, ConversationCopyStringDart>(
            'codex_agent_invocation_plugin_name_copy'),
        invocationPluginUri = core.library.lookupFunction<
                ConversationCopyStringNative, ConversationCopyStringDart>(
            'codex_agent_invocation_plugin_uri_copy'),
        invocationSkillCreate = core.library.lookupFunction<
                ConversationStringStringHandleOutNative,
                ConversationStringStringHandleOutDart>(
            'codex_agent_invocation_skill_create'),
        invocationSkillDestroy = core.library
            .lookupFunction<ConversationDestroyNative, ConversationDestroyDart>(
                'codex_agent_invocation_skill_destroy'),
        invocationSkillName = core.library.lookupFunction<
                ConversationCopyStringNative, ConversationCopyStringDart>(
            'codex_agent_invocation_skill_name_copy'),
        invocationSkillPath = core.library.lookupFunction<
                ConversationCopyStringNative, ConversationCopyStringDart>(
            'codex_agent_invocation_skill_path_copy'),
        invocationFromPlugin = core.library.lookupFunction<
                ConversationHandleHandleOutNative,
                ConversationHandleHandleOutDart>(
            'codex_agent_invocation_from_plugin'),
        invocationFromSkill = core.library.lookupFunction<
                ConversationHandleHandleOutNative,
                ConversationHandleHandleOutDart>(
            'codex_agent_invocation_from_skill'),
        invocationDestroy = core.library
            .lookupFunction<ConversationDestroyNative, ConversationDestroyDart>(
                'codex_agent_invocation_destroy'),
        invocationKind = core.library.lookupFunction<
            ConversationHandleIntOutNative,
            ConversationHandleIntOutDart>('codex_agent_invocation_kind'),
        invocationPlugin = core.library.lookupFunction<
            ConversationHandleHandleOutNative,
            ConversationHandleHandleOutDart>('codex_agent_invocation_plugin'),
        invocationSkill = core.library.lookupFunction<
            ConversationHandleHandleOutNative,
            ConversationHandleHandleOutDart>('codex_agent_invocation_skill'),
        turnRequestCreate = core.library.lookupFunction<
                ConversationTurnRequestCreateNative,
                ConversationTurnRequestCreateDart>(
            'codex_agent_turn_request_create'),
        turnRequestDestroy = core.library
            .lookupFunction<ConversationDestroyNative, ConversationDestroyDart>(
                'codex_agent_turn_request_destroy'),
        operationConversationValue = core.library.lookupFunction<
                ConversationHandleHandleOutNative,
                ConversationHandleHandleOutDart>(
            'codex_agent_operation_conversation_value'),
        conversationValueDestroy = core.library
            .lookupFunction<ConversationDestroyNative, ConversationDestroyDart>(
                'codex_agent_conversation_value_destroy'),
        conversationValueSummary = core.library.lookupFunction<
                ConversationHandleHandleOutNative,
                ConversationHandleHandleOutDart>(
            'codex_agent_conversation_value_summary'),
        conversationValueMessagesCount = core.library.lookupFunction<
                ConversationHandleSizeOutNative, ConversationHandleSizeOutDart>(
            'codex_agent_conversation_value_messages_count'),
        conversationValueMessageAt = core.library.lookupFunction<
                ConversationHandleIndexHandleOutNative,
                ConversationHandleIndexHandleOutDart>(
            'codex_agent_conversation_value_message_at'),
        messageDestroy = core.library
            .lookupFunction<ConversationDestroyNative, ConversationDestroyDart>(
                'codex_agent_message_destroy'),
        messageId = core.library.lookupFunction<ConversationCopyStringNative,
            ConversationCopyStringDart>('codex_agent_message_id_copy'),
        messageHasClientId = core.library.lookupFunction<
                ConversationHandleIntOutNative, ConversationHandleIntOutDart>(
            'codex_agent_message_has_client_message_id'),
        messageClientId = core.library.lookupFunction<
                ConversationCopyStringNative, ConversationCopyStringDart>(
            'codex_agent_message_client_message_id_copy'),
        messageRole = core.library.lookupFunction<
            ConversationHandleIntOutNative,
            ConversationHandleIntOutDart>('codex_agent_message_role'),
        messageText = core.library.lookupFunction<ConversationCopyStringNative,
            ConversationCopyStringDart>('codex_agent_message_text_copy'),
        messageMode = core.library.lookupFunction<
                ConversationHandleIntOutNative, ConversationHandleIntOutDart>(
            'codex_agent_message_collaboration_mode'),
        messageHasReasoning = core.library.lookupFunction<
            ConversationHandleIntOutNative,
            ConversationHandleIntOutDart>('codex_agent_message_has_reasoning'),
        messageReasoning = core.library.lookupFunction<
            ConversationCopyStringNative,
            ConversationCopyStringDart>('codex_agent_message_reasoning_copy'),
        messageHasPlan = core.library.lookupFunction<
            ConversationHandleIntOutNative,
            ConversationHandleIntOutDart>('codex_agent_message_has_plan'),
        messagePlan = core.library.lookupFunction<ConversationCopyStringNative,
            ConversationCopyStringDart>('codex_agent_message_plan_copy'),
        messageHasShell = core.library.lookupFunction<
                ConversationHandleIntOutNative, ConversationHandleIntOutDart>(
            'codex_agent_message_has_shell_command'),
        messageShell = core.library.lookupFunction<ConversationCopyStringNative,
                ConversationCopyStringDart>(
            'codex_agent_message_shell_command_copy'),
        messageExitCode = core.library.lookupFunction<
            ConversationHandleTwoIntsOutNative,
            ConversationHandleTwoIntsOutDart>('codex_agent_message_exit_code'),
        messageCapabilitiesCount = core.library.lookupFunction<
                ConversationHandleSizeOutNative, ConversationHandleSizeOutDart>(
            'codex_agent_message_capabilities_count'),
        messageHasCapability = core.library.lookupFunction<
                ConversationHandleIntIntOutNative,
                ConversationHandleIntIntOutDart>(
            'codex_agent_message_has_capability'),
        messageInvocationsCount = core.library.lookupFunction<
                ConversationHandleSizeOutNative, ConversationHandleSizeOutDart>(
            'codex_agent_message_invocations_count'),
        messageInvocationAt = core.library.lookupFunction<
                ConversationHandleIndexHandleOutNative,
                ConversationHandleIndexHandleOutDart>(
            'codex_agent_message_invocation_at'),
        currentMessagesCount = core.library.lookupFunction<
                ConversationHandleSizeOutNative, ConversationHandleSizeOutDart>(
            'codex_agent_conversation_current_messages_count'),
        currentMessagesAt = core.library.lookupFunction<
                ConversationHandleIndexHandleOutNative,
                ConversationHandleIndexHandleOutDart>(
            'codex_agent_conversation_current_messages_at'),
        activeProgressHasValue = core.library.lookupFunction<
                ConversationHandleIntOutNative, ConversationHandleIntOutDart>(
            'codex_agent_conversation_active_turn_progress_has_value'),
        activeProgressValue = core.library.lookupFunction<
                ConversationHandleHandleOutNative,
                ConversationHandleHandleOutDart>(
            'codex_agent_conversation_active_turn_progress_value'),
        turnProgressDestroy = core.library
            .lookupFunction<ConversationDestroyNative, ConversationDestroyDart>(
                'codex_agent_turn_progress_destroy'),
        turnProgressText = core.library.lookupFunction<
            ConversationCopyStringNative,
            ConversationCopyStringDart>('codex_agent_turn_progress_text_copy'),
        turnProgressCommentary = core.library.lookupFunction<
                ConversationCopyStringNative, ConversationCopyStringDart>(
            'codex_agent_turn_progress_commentary_copy'),
        turnProgressReasoning = core.library.lookupFunction<
                ConversationCopyStringNative, ConversationCopyStringDart>(
            'codex_agent_turn_progress_reasoning_copy'),
        turnProgressPlan = core.library.lookupFunction<
            ConversationCopyStringNative,
            ConversationCopyStringDart>('codex_agent_turn_progress_plan_copy'),
        turnProgressHasPlan = core.library.lookupFunction<
                ConversationHandleIntOutNative, ConversationHandleIntOutDart>(
            'codex_agent_turn_progress_has_plan_progress'),
        turnProgressPlanProgress = core.library.lookupFunction<
                ConversationHandleHandleOutNative,
                ConversationHandleHandleOutDart>(
            'codex_agent_turn_progress_plan_progress'),
        turnProgressShellOutput = core.library.lookupFunction<
                ConversationCopyStringNative, ConversationCopyStringDart>(
            'codex_agent_turn_progress_shell_output_copy'),
        turnProgressExitCode = core.library.lookupFunction<
                ConversationHandleTwoIntsOutNative,
                ConversationHandleTwoIntsOutDart>(
            'codex_agent_turn_progress_shell_exit_code'),
        turnProgressWorkActivity = core.library.lookupFunction<
                ConversationHandleTwoIntsOutNative,
                ConversationHandleTwoIntsOutDart>(
            'codex_agent_turn_progress_work_activity'),
        turnProgressHooksCount = core.library.lookupFunction<
                ConversationHandleSizeOutNative, ConversationHandleSizeOutDart>(
            'codex_agent_turn_progress_hook_activities_count'),
        turnProgressHookAt = core.library.lookupFunction<
                ConversationHandleIndexHandleOutNative,
                ConversationHandleIndexHandleOutDart>(
            'codex_agent_turn_progress_hook_activity_at'),
        turnProgressTruncated = core.library.lookupFunction<
                ConversationHandleIntOutNative, ConversationHandleIntOutDart>(
            'codex_agent_turn_progress_is_truncated'),
        planProgressDestroy = core.library
            .lookupFunction<ConversationDestroyNative, ConversationDestroyDart>(
                'codex_agent_plan_progress_destroy'),
        planProgressHasExplanation = core.library.lookupFunction<
                ConversationHandleIntOutNative, ConversationHandleIntOutDart>(
            'codex_agent_plan_progress_has_explanation'),
        planProgressExplanation = core.library.lookupFunction<
                ConversationCopyStringNative, ConversationCopyStringDart>(
            'codex_agent_plan_progress_explanation_copy'),
        planProgressStepsCount = core.library.lookupFunction<
                ConversationHandleSizeOutNative, ConversationHandleSizeOutDart>(
            'codex_agent_plan_progress_steps_count'),
        planProgressStepAt = core.library.lookupFunction<
                ConversationHandleIndexHandleOutNative,
                ConversationHandleIndexHandleOutDart>(
            'codex_agent_plan_progress_step_at'),
        planStepDestroy = core.library
            .lookupFunction<ConversationDestroyNative, ConversationDestroyDart>(
                'codex_agent_plan_step_destroy'),
        planStepText = core.library.lookupFunction<ConversationCopyStringNative,
            ConversationCopyStringDart>('codex_agent_plan_step_text_copy'),
        planStepStatus = core.library.lookupFunction<
            ConversationHandleIntOutNative,
            ConversationHandleIntOutDart>('codex_agent_plan_step_status'),
        hookActivityDestroy = core.library
            .lookupFunction<ConversationDestroyNative, ConversationDestroyDart>(
                'codex_agent_hook_activity_destroy'),
        hookActivityId = core.library.lookupFunction<
            ConversationCopyStringNative,
            ConversationCopyStringDart>('codex_agent_hook_activity_id_copy'),
        hookActivityEvent = core.library.lookupFunction<
                ConversationCopyStringNative, ConversationCopyStringDart>(
            'codex_agent_hook_activity_event_name_copy'),
        hookActivityHandler = core.library.lookupFunction<
                ConversationCopyStringNative, ConversationCopyStringDart>(
            'codex_agent_hook_activity_handler_type_copy'),
        hookActivityStatus = core.library.lookupFunction<
            ConversationHandleIntOutNative,
            ConversationHandleIntOutDart>('codex_agent_hook_activity_status'),
        hookActivityHasStatusMessage = core.library.lookupFunction<
                ConversationHandleIntOutNative, ConversationHandleIntOutDart>(
            'codex_agent_hook_activity_has_status_message'),
        hookActivityStatusMessage = core.library.lookupFunction<
                ConversationCopyStringNative, ConversationCopyStringDart>(
            'codex_agent_hook_activity_status_message_copy'),
        hookActivityDetailsCount = core.library.lookupFunction<
                ConversationHandleSizeOutNative, ConversationHandleSizeOutDart>(
            'codex_agent_hook_activity_details_count'),
        hookActivityDetailAt = core.library.lookupFunction<
                ConversationCopyStringAtNative, ConversationCopyStringAtDart>(
            'codex_agent_hook_activity_detail_copy_at');

  final ConversationsIdOperationDart conversationsRead;
  final ConversationsRenameDart conversationsRename;
  final ConversationsIdOperationDart conversationsDelete;
  final ConversationRequestOperationDart conversationSendRequest;
  final CodexGetSnapshotDart<CodexNativeConversation> currentMessagesGet;
  final CodexSubscribeDart<CodexNativeConversation> currentMessagesSubscribe;
  final CodexGetSnapshotDart<CodexNativeConversation> activeProgressGet;
  final CodexSubscribeDart<CodexNativeConversation> activeProgressSubscribe;
  final ConversationStringHandleOutDart conversationIdCreate;
  final ConversationStringStringHandleOutDart invocationPluginCreate;
  final ConversationDestroyDart invocationPluginDestroy;
  final ConversationCopyStringDart invocationPluginName;
  final ConversationCopyStringDart invocationPluginUri;
  final ConversationStringStringHandleOutDart invocationSkillCreate;
  final ConversationDestroyDart invocationSkillDestroy;
  final ConversationCopyStringDart invocationSkillName;
  final ConversationCopyStringDart invocationSkillPath;
  final ConversationHandleHandleOutDart invocationFromPlugin;
  final ConversationHandleHandleOutDart invocationFromSkill;
  final ConversationDestroyDart invocationDestroy;
  final ConversationHandleIntOutDart invocationKind;
  final ConversationHandleHandleOutDart invocationPlugin;
  final ConversationHandleHandleOutDart invocationSkill;
  final ConversationTurnRequestCreateDart turnRequestCreate;
  final ConversationDestroyDart turnRequestDestroy;
  final ConversationHandleHandleOutDart operationConversationValue;
  final ConversationDestroyDart conversationValueDestroy;
  final ConversationHandleHandleOutDart conversationValueSummary;
  final ConversationHandleSizeOutDart conversationValueMessagesCount;
  final ConversationHandleIndexHandleOutDart conversationValueMessageAt;
  final ConversationDestroyDart messageDestroy;
  final ConversationCopyStringDart messageId;
  final ConversationHandleIntOutDart messageHasClientId;
  final ConversationCopyStringDart messageClientId;
  final ConversationHandleIntOutDart messageRole;
  final ConversationCopyStringDart messageText;
  final ConversationHandleIntOutDart messageMode;
  final ConversationHandleIntOutDart messageHasReasoning;
  final ConversationCopyStringDart messageReasoning;
  final ConversationHandleIntOutDart messageHasPlan;
  final ConversationCopyStringDart messagePlan;
  final ConversationHandleIntOutDart messageHasShell;
  final ConversationCopyStringDart messageShell;
  final ConversationHandleTwoIntsOutDart messageExitCode;
  final ConversationHandleSizeOutDart messageCapabilitiesCount;
  final ConversationHandleIntIntOutDart messageHasCapability;
  final ConversationHandleSizeOutDart messageInvocationsCount;
  final ConversationHandleIndexHandleOutDart messageInvocationAt;
  final ConversationHandleSizeOutDart currentMessagesCount;
  final ConversationHandleIndexHandleOutDart currentMessagesAt;
  final ConversationHandleIntOutDart activeProgressHasValue;
  final ConversationHandleHandleOutDart activeProgressValue;
  final ConversationDestroyDart turnProgressDestroy;
  final ConversationCopyStringDart turnProgressText;
  final ConversationCopyStringDart turnProgressCommentary;
  final ConversationCopyStringDart turnProgressReasoning;
  final ConversationCopyStringDart turnProgressPlan;
  final ConversationHandleIntOutDart turnProgressHasPlan;
  final ConversationHandleHandleOutDart turnProgressPlanProgress;
  final ConversationCopyStringDart turnProgressShellOutput;
  final ConversationHandleTwoIntsOutDart turnProgressExitCode;
  final ConversationHandleTwoIntsOutDart turnProgressWorkActivity;
  final ConversationHandleSizeOutDart turnProgressHooksCount;
  final ConversationHandleIndexHandleOutDart turnProgressHookAt;
  final ConversationHandleIntOutDart turnProgressTruncated;
  final ConversationDestroyDart planProgressDestroy;
  final ConversationHandleIntOutDart planProgressHasExplanation;
  final ConversationCopyStringDart planProgressExplanation;
  final ConversationHandleSizeOutDart planProgressStepsCount;
  final ConversationHandleIndexHandleOutDart planProgressStepAt;
  final ConversationDestroyDart planStepDestroy;
  final ConversationCopyStringDart planStepText;
  final ConversationHandleIntOutDart planStepStatus;
  final ConversationDestroyDart hookActivityDestroy;
  final ConversationCopyStringDart hookActivityId;
  final ConversationCopyStringDart hookActivityEvent;
  final ConversationCopyStringDart hookActivityHandler;
  final ConversationHandleIntOutDart hookActivityStatus;
  final ConversationHandleIntOutDart hookActivityHasStatusMessage;
  final ConversationCopyStringDart hookActivityStatusMessage;
  final ConversationHandleSizeOutDart hookActivityDetailsCount;
  final ConversationCopyStringAtDart hookActivityDetailAt;
}

typedef ConversationStringHandleOutNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  Pointer<Pointer<Void>>,
);
typedef ConversationStringHandleOutDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  Pointer<Pointer<Void>>,
);

Pointer<Void> createConversationId(
  ConversationNativeApi api,
  Pointer<CodexNativeContext> context,
  CodexConversationId id,
) {
  final text = NativeString(id.value);
  final output = newHandleSlot<Void>();
  try {
    checkStatus(
      api.conversationIdCreate(context, text.view, output),
      'codex_agent_conversation_id_create',
    );
    return output.value;
  } finally {
    nativeMemory.free(output);
    text.close();
  }
}

Pointer<CodexNativeTurnRequest> createTurnRequest(
  ConversationNativeApi api,
  Pointer<CodexNativeContext> context,
  CodexTurnRequest request,
) {
  final prompt = NativeString(request.prompt);
  final optional = <NativeString>[
    request.clientMessageId == null
        ? NativeString.absent()
        : NativeString(request.clientMessageId!),
    request.model == null
        ? NativeString.absent()
        : NativeString(request.model!),
    request.effort == null
        ? NativeString.absent()
        : NativeString(request.effort!),
    request.serviceTier == null
        ? NativeString.absent()
        : NativeString(request.serviceTier!),
  ];
  final invocations = request.invocations
      .map((value) => _createInvocation(api, context, value))
      .toList(growable: false);
  Pointer<Pointer<Void>> invocationArray = nullptr;
  Pointer<Int32> capabilityArray = nullptr;
  final output = newHandleSlot<Void>();
  try {
    if (invocations.isNotEmpty) {
      invocationArray = nativeMemory.allocate<Pointer<Void>>(
        sizeOf<Pointer<Void>>() * invocations.length,
      );
      for (var index = 0; index < invocations.length; index++) {
        (invocationArray + index).value = invocations[index];
      }
    }
    final capabilities = request.capabilities.toList(growable: false)
      ..sort((left, right) => left.value.compareTo(right.value));
    if (capabilities.isNotEmpty) {
      capabilityArray = nativeMemory.allocate<Int32>(
        sizeOf<Int32>() * capabilities.length,
      );
      for (var index = 0; index < capabilities.length; index++) {
        (capabilityArray + index).value = capabilities[index].value;
      }
    }
    checkStatus(
      api.turnRequestCreate(
        context,
        prompt.view,
        request.clientMessageId == null ? 0 : 1,
        optional[0].view,
        request.model == null ? 0 : 1,
        optional[1].view,
        request.effort == null ? 0 : 1,
        optional[2].view,
        request.serviceTier == null ? 0 : 1,
        optional[3].view,
        request.approvalPreset.value,
        capabilityArray,
        capabilities.length,
        invocationArray,
        invocations.length,
        request.collaborationMode.value,
        output,
      ),
      'codex_agent_turn_request_create',
    );
    return output.value.cast<CodexNativeTurnRequest>();
  } finally {
    nativeMemory.free(output);
    nativeMemory.free(capabilityArray);
    nativeMemory.free(invocationArray);
    for (final invocation in invocations) {
      _destroy(api.invocationDestroy, context, invocation,
          'codex_agent_invocation_destroy');
    }
    for (final text in optional) {
      text.close();
    }
    prompt.close();
  }
}

void destroyTurnRequest(
  ConversationNativeApi api,
  Pointer<CodexNativeContext> context,
  Pointer<CodexNativeTurnRequest> request,
) =>
    _destroy(api.turnRequestDestroy, context, request.cast<Void>(),
        'codex_agent_turn_request_destroy');

void destroyConversationId(
  NativeApi api,
  Pointer<CodexNativeContext> context,
  Pointer<Void> id,
) {
  final slot = newHandleSlot<CodexNativeConversationId>();
  try {
    slot.value = id.cast<CodexNativeConversationId>();
    checkStatus(api.conversationIdDestroy(context, slot),
        'codex_agent_conversation_id_destroy');
  } finally {
    nativeMemory.free(slot);
  }
}

CodexConversationSnapshot readConversationValue(
  NativeApi core,
  ConversationNativeApi api,
  Pointer<CodexNativeContext> context,
  Pointer<Void> value,
) {
  try {
    final summary = newHandleSlot<Void>();
    try {
      checkStatus(
        api.conversationValueSummary(context, value, summary),
        'codex_agent_conversation_value_summary',
      );
      final decodedSummary = _readSummary(core, context, summary.value);
      final messages = _readList(
        api.conversationValueMessagesCount,
        api.conversationValueMessageAt,
        context,
        value,
        (message) => _readMessage(api, context, message),
        'codex_agent_conversation_value_messages',
      );
      return CodexConversationSnapshot(
        summary: decodedSummary,
        messages: messages,
      );
    } finally {
      nativeMemory.free(summary);
    }
  } finally {
    _destroy(api.conversationValueDestroy, context, value,
        'codex_agent_conversation_value_destroy');
  }
}

List<CodexMessage> readCurrentMessages(
  ConversationNativeApi api,
  Pointer<CodexNativeContext> context,
  Pointer<CodexNativeSnapshot> snapshot,
) =>
    List<CodexMessage>.unmodifiable(_readList(
      api.currentMessagesCount,
      api.currentMessagesAt,
      context,
      snapshot.cast<Void>(),
      (message) => _readMessage(api, context, message),
      'codex_agent_conversation_current_messages',
    ));

CodexTurnProgress? readActiveTurnProgress(
  ConversationNativeApi api,
  Pointer<CodexNativeContext> context,
  Pointer<CodexNativeSnapshot> snapshot,
) {
  final present = _int(
    context,
    snapshot.cast<Void>(),
    api.activeProgressHasValue,
    'codex_agent_conversation_active_turn_progress_has_value',
  );
  if (present == 0) return null;
  final output = newHandleSlot<Void>();
  try {
    checkStatus(
      api.activeProgressValue(context, snapshot.cast<Void>(), output),
      'codex_agent_conversation_active_turn_progress_value',
    );
    return _readTurnProgress(api, context, output.value);
  } finally {
    nativeMemory.free(output);
  }
}

Pointer<Void> _createInvocation(
  ConversationNativeApi api,
  Pointer<CodexNativeContext> context,
  CodexInvocation invocation,
) {
  final name = NativeString(invocation.name);
  final second = NativeString(
    switch (invocation) {
      CodexPluginInvocation(:final uri) => uri,
      CodexSkillInvocation(:final path) => path,
    },
  );
  final typed = newHandleSlot<Void>();
  final result = newHandleSlot<Void>();
  final destroyTyped = invocation is CodexPluginInvocation
      ? api.invocationPluginDestroy
      : api.invocationSkillDestroy;
  try {
    switch (invocation) {
      case CodexPluginInvocation():
        checkStatus(
          api.invocationPluginCreate(context, name.view, second.view, typed),
          'codex_agent_invocation_plugin_create',
        );
        checkStatus(
          api.invocationFromPlugin(context, typed.value, result),
          'codex_agent_invocation_from_plugin',
        );
      case CodexSkillInvocation():
        checkStatus(
          api.invocationSkillCreate(context, name.view, second.view, typed),
          'codex_agent_invocation_skill_create',
        );
        checkStatus(
          api.invocationFromSkill(context, typed.value, result),
          'codex_agent_invocation_from_skill',
        );
    }
    return result.value;
  } finally {
    if (typed.value != nullptr) {
      _destroy(
          destroyTyped,
          context,
          typed.value,
          invocation is CodexPluginInvocation
              ? 'codex_agent_invocation_plugin_destroy'
              : 'codex_agent_invocation_skill_destroy');
    }
    nativeMemory.free(result);
    nativeMemory.free(typed);
    second.close();
    name.close();
  }
}

CodexMessage _readMessage(
  ConversationNativeApi api,
  Pointer<CodexNativeContext> context,
  Pointer<Void> message,
) {
  try {
    final role =
        _int(context, message, api.messageRole, 'codex_agent_message_role');
    final mode = _int(context, message, api.messageMode,
        'codex_agent_message_collaboration_mode');
    final exit = _twoInts(
        context, message, api.messageExitCode, 'codex_agent_message_exit_code');
    final capabilityCount = _size(context, message,
        api.messageCapabilitiesCount, 'codex_agent_message_capabilities_count');
    final capabilities = <CodexCapability>{};
    for (final capability in CodexCapability.values) {
      final present = nativeMemory.allocate<Int32>(sizeOf<Int32>());
      try {
        checkStatus(
          api.messageHasCapability(context, message, capability.value, present),
          'codex_agent_message_has_capability',
        );
        if (present.value != 0) capabilities.add(capability);
      } finally {
        nativeMemory.free(present);
      }
    }
    if (capabilities.length != capabilityCount) {
      throw const CodexNativeException(
        9,
        'codex_agent_message_capabilities_count returned an unknown capability',
      );
    }
    final invocations = _readList(
      api.messageInvocationsCount,
      api.messageInvocationAt,
      context,
      message,
      (invocation) => _readInvocation(api, context, invocation),
      'codex_agent_message_invocations',
    );
    return CodexMessage(
      id: _copy(api.messageId, context, message),
      clientMessageId: _optionalString(
          api.messageHasClientId, api.messageClientId, context, message),
      role: _enumValue(CodexMessageRole.values, role, (value) => value.value,
          'codex_agent_message_role'),
      text: _copy(api.messageText, context, message),
      collaborationMode: _enumValue(CodexCollaborationMode.values, mode,
          (value) => value.value, 'codex_agent_message_collaboration_mode'),
      reasoning: _optionalString(
          api.messageHasReasoning, api.messageReasoning, context, message),
      plan: _optionalString(
          api.messageHasPlan, api.messagePlan, context, message),
      shellCommand: _optionalString(
          api.messageHasShell, api.messageShell, context, message),
      exitCode: exit.$1 == 0 ? null : exit.$2,
      capabilities: capabilities,
      invocations: invocations,
    );
  } finally {
    _destroy(
        api.messageDestroy, context, message, 'codex_agent_message_destroy');
  }
}

CodexInvocation _readInvocation(
  ConversationNativeApi api,
  Pointer<CodexNativeContext> context,
  Pointer<Void> invocation,
) {
  try {
    final kind = _int(
        context, invocation, api.invocationKind, 'codex_agent_invocation_kind');
    final child = newHandleSlot<Void>();
    try {
      if (kind == 0) {
        checkStatus(api.invocationPlugin(context, invocation, child),
            'codex_agent_invocation_plugin');
        try {
          return CodexPluginInvocation(
            name: _copy(api.invocationPluginName, context, child.value),
            uri: _copy(api.invocationPluginUri, context, child.value),
          );
        } finally {
          _destroy(api.invocationPluginDestroy, context, child.value,
              'codex_agent_invocation_plugin_destroy');
        }
      }
      if (kind == 1) {
        checkStatus(api.invocationSkill(context, invocation, child),
            'codex_agent_invocation_skill');
        try {
          return CodexSkillInvocation(
            name: _copy(api.invocationSkillName, context, child.value),
            path: _copy(api.invocationSkillPath, context, child.value),
          );
        } finally {
          _destroy(api.invocationSkillDestroy, context, child.value,
              'codex_agent_invocation_skill_destroy');
        }
      }
      throw CodexNativeException(kind, 'unknown invocation kind');
    } finally {
      nativeMemory.free(child);
    }
  } finally {
    _destroy(api.invocationDestroy, context, invocation,
        'codex_agent_invocation_destroy');
  }
}

CodexTurnProgress _readTurnProgress(
  ConversationNativeApi api,
  Pointer<CodexNativeContext> context,
  Pointer<Void> progress,
) {
  try {
    CodexPlanProgress? planProgress;
    if (_int(context, progress, api.turnProgressHasPlan,
            'codex_agent_turn_progress_has_plan_progress') !=
        0) {
      final plan = newHandleSlot<Void>();
      try {
        checkStatus(api.turnProgressPlanProgress(context, progress, plan),
            'codex_agent_turn_progress_plan_progress');
        planProgress = _readPlanProgress(api, context, plan.value);
      } finally {
        nativeMemory.free(plan);
      }
    }
    final exit = _twoInts(context, progress, api.turnProgressExitCode,
        'codex_agent_turn_progress_shell_exit_code');
    final work = _twoInts(context, progress, api.turnProgressWorkActivity,
        'codex_agent_turn_progress_work_activity');
    final hooks = _readList(
      api.turnProgressHooksCount,
      api.turnProgressHookAt,
      context,
      progress,
      (hook) => _readHookActivity(api, context, hook),
      'codex_agent_turn_progress_hook_activities',
    );
    final truncated = _int(context, progress, api.turnProgressTruncated,
        'codex_agent_turn_progress_is_truncated');
    return CodexTurnProgress(
      text: _copy(api.turnProgressText, context, progress),
      commentary: _copy(api.turnProgressCommentary, context, progress),
      reasoning: _copy(api.turnProgressReasoning, context, progress),
      plan: _copy(api.turnProgressPlan, context, progress),
      planProgress: planProgress,
      shellOutput: _copy(api.turnProgressShellOutput, context, progress),
      shellExitCode: exit.$1 == 0 ? null : exit.$2,
      workActivity: work.$1 == 0
          ? null
          : _enumValue<CodexWorkActivity>(
              CodexWorkActivity.values,
              work.$2,
              (value) => value.value,
              'codex_agent_turn_progress_work_activity'),
      hookActivities: hooks,
      isTruncated: truncated != 0,
    );
  } finally {
    _destroy(api.turnProgressDestroy, context, progress,
        'codex_agent_turn_progress_destroy');
  }
}

CodexPlanProgress _readPlanProgress(
  ConversationNativeApi api,
  Pointer<CodexNativeContext> context,
  Pointer<Void> progress,
) {
  try {
    return CodexPlanProgress(
      explanation: _optionalString(api.planProgressHasExplanation,
          api.planProgressExplanation, context, progress),
      steps: _readList(
        api.planProgressStepsCount,
        api.planProgressStepAt,
        context,
        progress,
        (step) {
          try {
            final status = _int(context, step, api.planStepStatus,
                'codex_agent_plan_step_status');
            return CodexPlanStep(
              text: _copy(api.planStepText, context, step),
              status: _enumValue(CodexPlanStepStatus.values, status,
                  (value) => value.value, 'codex_agent_plan_step_status'),
            );
          } finally {
            _destroy(api.planStepDestroy, context, step,
                'codex_agent_plan_step_destroy');
          }
        },
        'codex_agent_plan_progress_steps',
      ),
    );
  } finally {
    _destroy(api.planProgressDestroy, context, progress,
        'codex_agent_plan_progress_destroy');
  }
}

CodexHookActivity _readHookActivity(
  ConversationNativeApi api,
  Pointer<CodexNativeContext> context,
  Pointer<Void> activity,
) {
  try {
    final status = _int(context, activity, api.hookActivityStatus,
        'codex_agent_hook_activity_status');
    final detailCount = _size(context, activity, api.hookActivityDetailsCount,
        'codex_agent_hook_activity_details_count');
    return CodexHookActivity(
      id: _copy(api.hookActivityId, context, activity),
      eventName: _copy(api.hookActivityEvent, context, activity),
      handlerType: _copy(api.hookActivityHandler, context, activity),
      status: _enumValue(CodexHookRunStatus.values, status,
          (value) => value.value, 'codex_agent_hook_activity_status'),
      statusMessage: _optionalString(api.hookActivityHasStatusMessage,
          api.hookActivityStatusMessage, context, activity),
      details: List<String>.generate(
        detailCount,
        (index) => _copyAt(api.hookActivityDetailAt, context, activity, index),
        growable: false,
      ),
    );
  } finally {
    _destroy(api.hookActivityDestroy, context, activity,
        'codex_agent_hook_activity_destroy');
  }
}

CodexConversationSummary _readSummary(
  NativeApi api,
  Pointer<CodexNativeContext> context,
  Pointer<Void> summary,
) {
  final typed = summary.cast<CodexNativeConversationSummary>();
  final id = newHandleSlot<CodexNativeConversationId>();
  final summarySlot = newHandleSlot<CodexNativeConversationSummary>();
  final updated = nativeMemory.allocate<Int64>(sizeOf<Int64>());
  try {
    summarySlot.value = typed;
    checkStatus(api.summaryConversationId(context, typed, id),
        'codex_agent_conversation_summary_conversation_id');
    checkStatus(api.summaryUpdated(context, typed, updated),
        'codex_agent_conversation_summary_updated_at_epoch_seconds');
    return CodexConversationSummary(
      conversationId: CodexConversationId(
          copyString(api.conversationIdValue, context, id.value)),
      title: copyString(api.summaryTitle, context, typed),
      updatedAtEpochSeconds: updated.value,
    );
  } finally {
    if (id.value != nullptr) {
      checkStatus(api.conversationIdDestroy(context, id),
          'codex_agent_conversation_id_destroy');
    }
    checkStatus(api.summaryDestroy(context, summarySlot),
        'codex_agent_conversation_summary_destroy');
    nativeMemory.free(updated);
    nativeMemory.free(summarySlot);
    nativeMemory.free(id);
  }
}

List<T> _readList<T>(
  ConversationHandleSizeOutDart countFunction,
  ConversationHandleIndexHandleOutDart atFunction,
  Pointer<CodexNativeContext> context,
  Pointer<Void> owner,
  T Function(Pointer<Void>) decode,
  String symbol,
) {
  final count = _size(context, owner, countFunction, '${symbol}_count');
  return List<T>.generate(count, (index) {
    final output = newHandleSlot<Void>();
    try {
      checkStatus(atFunction(context, owner, index, output), '${symbol}_at');
      return decode(output.value);
    } finally {
      nativeMemory.free(output);
    }
  }, growable: false);
}

String? _optionalString(
  ConversationHandleIntOutDart hasValue,
  ConversationCopyStringDart copy,
  Pointer<CodexNativeContext> context,
  Pointer<Void> owner,
) =>
    _int(context, owner, hasValue, 'optional string presence') == 0
        ? null
        : _copy(copy, context, owner);

String _copy(
  ConversationCopyStringDart copy,
  Pointer<CodexNativeContext> context,
  Pointer<Void> owner,
) =>
    copyString<Void>(copy, context, owner);

String _copyAt(
  ConversationCopyStringAtDart copy,
  Pointer<CodexNativeContext> context,
  Pointer<Void> owner,
  int index,
) {
  final required = nativeMemory.allocate<Size>(sizeOf<Size>());
  try {
    checkStatus(copy(context, owner, index, nullptr, 0, required),
        'indexed string size',
        allow: const {CodexStatus.bufferTooSmall});
    if (required.value == 0) return '';
    final buffer = nativeMemory.allocate<Uint8>(required.value);
    try {
      checkStatus(copy(context, owner, index, buffer, required.value, required),
          'indexed string copy');
      return utf8.decode(buffer.asTypedList(required.value));
    } finally {
      nativeMemory.free(buffer);
    }
  } finally {
    nativeMemory.free(required);
  }
}

int _int(
  Pointer<CodexNativeContext> context,
  Pointer<Void> owner,
  ConversationHandleIntOutDart function,
  String symbol,
) {
  final output = nativeMemory.allocate<Int32>(sizeOf<Int32>());
  try {
    checkStatus(function(context, owner, output), symbol);
    return output.value;
  } finally {
    nativeMemory.free(output);
  }
}

int _size(
  Pointer<CodexNativeContext> context,
  Pointer<Void> owner,
  ConversationHandleSizeOutDart function,
  String symbol,
) {
  final output = nativeMemory.allocate<Size>(sizeOf<Size>());
  try {
    checkStatus(function(context, owner, output), symbol);
    return output.value;
  } finally {
    nativeMemory.free(output);
  }
}

(int, int) _twoInts(
  Pointer<CodexNativeContext> context,
  Pointer<Void> owner,
  ConversationHandleTwoIntsOutDart function,
  String symbol,
) {
  final first = nativeMemory.allocate<Int32>(sizeOf<Int32>());
  final second = nativeMemory.allocate<Int32>(sizeOf<Int32>());
  try {
    checkStatus(function(context, owner, first, second), symbol);
    return (first.value, second.value);
  } finally {
    nativeMemory.free(second);
    nativeMemory.free(first);
  }
}

T _enumValue<T>(
  Iterable<T> values,
  int raw,
  int Function(T) valueOf,
  String symbol,
) {
  for (final value in values) {
    if (valueOf(value) == raw) return value;
  }
  throw CodexNativeException(raw, '$symbol returned an unknown value');
}

void _destroy(
  ConversationDestroyDart destroy,
  Pointer<CodexNativeContext> context,
  Pointer<Void> value,
  String symbol,
) {
  if (value == nullptr) return;
  final slot = newHandleSlot<Void>();
  try {
    slot.value = value;
    checkStatus(destroy(context, slot), symbol);
  } finally {
    nativeMemory.free(slot);
  }
}
