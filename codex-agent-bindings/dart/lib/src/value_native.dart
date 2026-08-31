import 'dart:convert';
import 'dart:ffi';

import 'errors.dart';
import 'ffi.dart';
import 'models.dart';
import 'residual_models.dart';

/// Internal executable evidence hook; not exported by `codex_agent.dart`.
void Function(String symbol)? valueNativeCallObserver;

typedef _ContextHandleOutNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Pointer<Void>>,
);
typedef _ContextHandleOutDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Pointer<Void>>,
);
typedef _ContextStringHandleOutNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  Pointer<Pointer<Void>>,
);
typedef _ContextStringHandleOutDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  Pointer<Pointer<Void>>,
);
typedef _ContextIntHandleOutNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Int32,
  Pointer<Pointer<Void>>,
);
typedef _ContextIntHandleOutDart = int Function(
  Pointer<CodexNativeContext>,
  int,
  Pointer<Pointer<Void>>,
);
typedef _ContextDoubleHandleOutNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Double,
  Pointer<Pointer<Void>>,
);
typedef _ContextDoubleHandleOutDart = int Function(
  Pointer<CodexNativeContext>,
  double,
  Pointer<Pointer<Void>>,
);
typedef _ContextStringsHandleOutNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  Size,
  Pointer<Pointer<Void>>,
);
typedef _ContextStringsHandleOutDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  int,
  Pointer<Pointer<Void>>,
);
typedef _ContextHandleHandleOutNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Pointer<Void>>,
);
typedef _ContextHandleHandleOutDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Pointer<Void>>,
);
typedef _ContextTwoHandlesHandleOutNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Void>,
  Pointer<Pointer<Void>>,
);
typedef _ContextTwoHandlesHandleOutDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Void>,
  Pointer<Pointer<Void>>,
);
typedef _ContextHandleIntOutNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Int32>,
);
typedef _ContextHandleIntOutDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Int32>,
);
typedef _ContextTwoHandlesIntOutNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Void>,
  Pointer<Int32>,
);
typedef _ContextTwoHandlesIntOutDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Void>,
  Pointer<Int32>,
);
typedef _ContextHandleDoubleOutNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Double>,
);
typedef _ContextHandleDoubleOutDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Double>,
);
typedef _ContextHandleSizeOutNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Size>,
);
typedef _ContextHandleSizeOutDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Size>,
);
typedef _ContextHandleIndexHandleOutNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Size,
  Pointer<Pointer<Void>>,
);
typedef _ContextHandleIndexHandleOutDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  int,
  Pointer<Pointer<Void>>,
);
typedef _ContextHandleStringHandleOutNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<CodexStringView>,
  Pointer<Pointer<Void>>,
);
typedef _ContextHandleStringHandleOutDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<CodexStringView>,
  Pointer<Pointer<Void>>,
);
typedef _ContextHandleStringIntOutNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<CodexStringView>,
  Pointer<Int32>,
);
typedef _ContextHandleStringIntOutDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<CodexStringView>,
  Pointer<Int32>,
);
typedef _CopyHandleStringNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Uint8>,
  Size,
  Pointer<Size>,
);
typedef _CopyHandleStringDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Pointer<Uint8>,
  int,
  Pointer<Size>,
);
typedef _CopyHandleIndexStringNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  Size,
  Pointer<Uint8>,
  Size,
  Pointer<Size>,
);
typedef _CopyHandleIndexStringDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Void>,
  int,
  Pointer<Uint8>,
  int,
  Pointer<Size>,
);

typedef _FormOptionCreateNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  Int32,
  Pointer<CodexStringView>,
  Int32,
  Pointer<CodexStringView>,
  Pointer<Pointer<Void>>,
);
typedef _FormOptionCreateDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  int,
  Pointer<CodexStringView>,
  int,
  Pointer<CodexStringView>,
  Pointer<Pointer<Void>>,
);
typedef _FormFieldCreateNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  Int32,
  Pointer<CodexStringView>,
  Int32,
  Int32,
  Pointer<Pointer<Void>>,
  Size,
  Int32,
  Pointer<Void>,
  Int32,
  Double,
  Int32,
  Double,
  Int32,
  Int32,
  Int32,
  Int64,
  Int32,
  Int64,
  Int32,
  Int64,
  Int32,
  Int64,
  Int32,
  Int32,
  Pointer<Pointer<Void>>,
);
typedef _FormFieldCreateDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  int,
  Pointer<CodexStringView>,
  int,
  int,
  Pointer<Pointer<Void>>,
  int,
  int,
  Pointer<Void>,
  int,
  double,
  int,
  double,
  int,
  int,
  int,
  int,
  int,
  int,
  int,
  int,
  int,
  int,
  int,
  int,
  Pointer<Pointer<Void>>,
);
typedef _ElicitationCreateNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  Pointer<Void>,
  Pointer<CodexStringView>,
  Int32,
  Pointer<Pointer<Void>>,
  Size,
  Int32,
  Pointer<CodexStringView>,
  Pointer<Pointer<Void>>,
);
typedef _ElicitationCreateDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  Pointer<Void>,
  Pointer<CodexStringView>,
  int,
  Pointer<Pointer<Void>>,
  int,
  int,
  Pointer<CodexStringView>,
  Pointer<Pointer<Void>>,
);
typedef _KeyValueCreateNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  Pointer<Pointer<Void>>,
  Size,
  Pointer<Pointer<Void>>,
);
typedef _KeyValueCreateDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  Pointer<Pointer<Void>>,
  int,
  Pointer<Pointer<Void>>,
);
typedef _ResponseCreateNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Int32,
  Pointer<CodexStringView>,
  Pointer<Pointer<Void>>,
  Size,
  Pointer<Pointer<Void>>,
);
typedef _ResponseCreateDart = int Function(
  Pointer<CodexNativeContext>,
  int,
  Pointer<CodexStringView>,
  Pointer<Pointer<Void>>,
  int,
  Pointer<Pointer<Void>>,
);
typedef _PendingApprovalCreateNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  Pointer<Void>,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  Pointer<Pointer<Void>>,
);
typedef _PendingApprovalCreateDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  Pointer<Void>,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  Pointer<Pointer<Void>>,
);
typedef _FailureCreateNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  Int32,
  Pointer<Pointer<Void>>,
);
typedef _FailureCreateDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<CodexStringView>,
  Pointer<CodexStringView>,
  int,
  Pointer<Pointer<Void>>,
);
typedef _InteractionStateCreateNative = Int32 Function(
  Pointer<CodexNativeContext>,
  Pointer<Pointer<Void>>,
  Size,
  Pointer<CodexStringView>,
  Size,
  Int32,
  Pointer<Void>,
  Pointer<Pointer<Void>>,
);
typedef _InteractionStateCreateDart = int Function(
  Pointer<CodexNativeContext>,
  Pointer<Pointer<Void>>,
  int,
  Pointer<CodexStringView>,
  int,
  int,
  Pointer<Void>,
  Pointer<Pointer<Void>>,
);

final class _ValueNativeApi {
  _ValueNativeApi._(this.core)
      : conversationIdCreate = core.library.lookupFunction<
            _ContextStringHandleOutNative,
            _ContextStringHandleOutDart>('codex_agent_conversation_id_create'),
        conversationIdValue = core.library
            .lookupFunction<_CopyHandleStringNative, _CopyHandleStringDart>(
                'codex_agent_conversation_id_value_copy'),
        formBooleanCreate = core.library.lookupFunction<
            _ContextIntHandleOutNative,
            _ContextIntHandleOutDart>('codex_agent_form_boolean_value_create'),
        formBooleanValue = core.library.lookupFunction<
            _ContextHandleIntOutNative,
            _ContextHandleIntOutDart>('codex_agent_form_boolean_value_value'),
        formNumberCreate = core.library.lookupFunction<
                _ContextDoubleHandleOutNative, _ContextDoubleHandleOutDart>(
            'codex_agent_form_number_value_create'),
        formNumberValue = core.library.lookupFunction<
            _ContextHandleDoubleOutNative,
            _ContextHandleDoubleOutDart>('codex_agent_form_number_value_value'),
        formTextCreate = core.library.lookupFunction<
            _ContextStringHandleOutNative,
            _ContextStringHandleOutDart>('codex_agent_form_text_value_create'),
        formTextValue = core.library
            .lookupFunction<_CopyHandleStringNative, _CopyHandleStringDart>(
                'codex_agent_form_text_value_value_copy'),
        formTextListCreate = core.library.lookupFunction<
            _ContextStringsHandleOutNative, _ContextStringsHandleOutDart>(
          'codex_agent_form_text_list_value_create',
        ),
        formTextListCount = core.library.lookupFunction<
                _ContextHandleSizeOutNative, _ContextHandleSizeOutDart>(
            'codex_agent_form_text_list_value_count'),
        formTextListValueAt = core.library.lookupFunction<
            _CopyHandleIndexStringNative, _CopyHandleIndexStringDart>(
          'codex_agent_form_text_list_value_copy_at',
        ),
        formValueFromBoolean = core.library.lookupFunction<
            _ContextHandleHandleOutNative,
            _ContextHandleHandleOutDart>('codex_agent_form_value_from_boolean'),
        formValueFromNumber = core.library.lookupFunction<
            _ContextHandleHandleOutNative,
            _ContextHandleHandleOutDart>('codex_agent_form_value_from_number'),
        formValueFromText = core.library.lookupFunction<
            _ContextHandleHandleOutNative,
            _ContextHandleHandleOutDart>('codex_agent_form_value_from_text'),
        formValueFromTextList = core.library.lookupFunction<
                _ContextHandleHandleOutNative, _ContextHandleHandleOutDart>(
            'codex_agent_form_value_from_text_list'),
        formValueKind = core.library.lookupFunction<_ContextHandleIntOutNative,
            _ContextHandleIntOutDart>('codex_agent_form_value_kind'),
        formValueBoolean = core.library.lookupFunction<
            _ContextHandleHandleOutNative,
            _ContextHandleHandleOutDart>('codex_agent_form_value_boolean'),
        formValueNumber = core.library.lookupFunction<
            _ContextHandleHandleOutNative,
            _ContextHandleHandleOutDart>('codex_agent_form_value_number'),
        formValueText = core.library.lookupFunction<
            _ContextHandleHandleOutNative,
            _ContextHandleHandleOutDart>('codex_agent_form_value_text'),
        formValueTextList = core.library.lookupFunction<
            _ContextHandleHandleOutNative,
            _ContextHandleHandleOutDart>('codex_agent_form_value_text_list'),
        formOptionCreate = core.library
            .lookupFunction<_FormOptionCreateNative, _FormOptionCreateDart>(
                'codex_agent_form_option_create'),
        formFieldCreate = core.library
            .lookupFunction<_FormFieldCreateNative, _FormFieldCreateDart>(
                'codex_agent_form_field_create'),
        elicitationCreate = core.library
            .lookupFunction<_ElicitationCreateNative, _ElicitationCreateDart>(
                'codex_agent_elicitation_create'),
        formContentCreate = core.library
            .lookupFunction<_KeyValueCreateNative, _KeyValueCreateDart>(
                'codex_agent_form_content_create'),
        formContentCount = core.library.lookupFunction<
            _ContextHandleSizeOutNative,
            _ContextHandleSizeOutDart>('codex_agent_form_content_count'),
        formContentKeyAt = core.library.lookupFunction<
            _CopyHandleIndexStringNative,
            _CopyHandleIndexStringDart>('codex_agent_form_content_key_copy'),
        formContentValue = core.library.lookupFunction<
                _ContextHandleStringHandleOutNative,
                _ContextHandleStringHandleOutDart>(
            'codex_agent_form_content_value_at'),
        responseCreate = core.library
            .lookupFunction<_ResponseCreateNative, _ResponseCreateDart>(
                'codex_agent_elicitation_response_create'),
        responseAction = core.library.lookupFunction<_ContextHandleIntOutNative,
                _ContextHandleIntOutDart>(
            'codex_agent_elicitation_response_action'),
        responseCount = core.library.lookupFunction<_ContextHandleSizeOutNative,
            _ContextHandleSizeOutDart>(
          'codex_agent_elicitation_response_content_count',
        ),
        responseValue = core.library.lookupFunction<
            _ContextHandleStringHandleOutNative,
            _ContextHandleStringHandleOutDart>(
          'codex_agent_elicitation_response_content_value',
        ),
        responseDecline = core.library
            .lookupFunction<_ContextHandleOutNative, _ContextHandleOutDart>(
                'codex_agent_elicitation_response_decline'),
        responseCancel = core.library
            .lookupFunction<_ContextHandleOutNative, _ContextHandleOutDart>(
                'codex_agent_elicitation_response_cancel'),
        elicitationInitialValues = core.library.lookupFunction<
            _ContextHandleHandleOutNative, _ContextHandleHandleOutDart>(
          'codex_agent_elicitation_initial_values',
        ),
        elicitationValidate = core.library.lookupFunction<
                _ContextTwoHandlesHandleOutNative,
                _ContextTwoHandlesHandleOutDart>(
            'codex_agent_elicitation_validate'),
        elicitationAccept = core.library.lookupFunction<
            _ContextTwoHandlesHandleOutNative,
            _ContextTwoHandlesHandleOutDart>('codex_agent_elicitation_accept'),
        elicitationAccepts = core.library.lookupFunction<
            _ContextTwoHandlesIntOutNative,
            _ContextTwoHandlesIntOutDart>('codex_agent_elicitation_accepts'),
        formFieldAccepts = core.library.lookupFunction<
            _ContextTwoHandlesIntOutNative,
            _ContextTwoHandlesIntOutDart>('codex_agent_form_field_accepts'),
        validationCount = core.library.lookupFunction<
            _ContextHandleSizeOutNative, _ContextHandleSizeOutDart>(
          'codex_agent_elicitation_validation_issue_count',
        ),
        validationIssueAt = core.library.lookupFunction<
            _ContextHandleIndexHandleOutNative,
            _ContextHandleIndexHandleOutDart>(
          'codex_agent_elicitation_validation_issue_at',
        ),
        validationIssueField = core.library
            .lookupFunction<_CopyHandleStringNative, _CopyHandleStringDart>(
          'codex_agent_elicitation_validation_issue_field_name_copy',
        ),
        validationIssueReason = core.library.lookupFunction<
            _ContextHandleIntOutNative, _ContextHandleIntOutDart>(
          'codex_agent_elicitation_validation_issue_reason',
        ),
        pendingApprovalCreate = core.library.lookupFunction<
            _PendingApprovalCreateNative,
            _PendingApprovalCreateDart>('codex_agent_pending_approval_create'),
        pendingElicitationCreate = core.library.lookupFunction<
            _ContextHandleHandleOutNative, _ContextHandleHandleOutDart>(
          'codex_agent_pending_elicitation_create',
        ),
        pendingFromApproval = core.library.lookupFunction<
            _ContextHandleHandleOutNative, _ContextHandleHandleOutDart>(
          'codex_agent_pending_interaction_from_approval',
        ),
        pendingFromElicitation = core.library.lookupFunction<
            _ContextHandleHandleOutNative, _ContextHandleHandleOutDart>(
          'codex_agent_pending_interaction_from_elicitation',
        ),
        pendingRequestId = core.library
            .lookupFunction<_CopyHandleStringNative, _CopyHandleStringDart>(
          'codex_agent_pending_interaction_request_id_copy',
        ),
        pendingConversationId = core.library.lookupFunction<
            _ContextHandleHandleOutNative, _ContextHandleHandleOutDart>(
          'codex_agent_pending_interaction_conversation_id',
        ),
        failureCreate = core.library
            .lookupFunction<_FailureCreateNative, _FailureCreateDart>(
                'codex_agent_failure_create'),
        interactionStateCreate = core.library.lookupFunction<
                _InteractionStateCreateNative, _InteractionStateCreateDart>(
            'codex_agent_interaction_state_create'),
        interactionIsResolving = core.library.lookupFunction<
            _ContextTwoHandlesIntOutNative, _ContextTwoHandlesIntOutDart>(
          'codex_agent_interaction_state_is_resolving',
        ),
        interactionContains = core.library.lookupFunction<
            _ContextHandleStringIntOutNative, _ContextHandleStringIntOutDart>(
          'codex_agent_interaction_state_resolving_request_ids_contains',
        ),
        interactionPendingFor = core.library.lookupFunction<
            _ContextTwoHandlesHandleOutNative, _ContextTwoHandlesHandleOutDart>(
          'codex_agent_interaction_state_pending_for',
        ),
        pendingListCount = core.library.lookupFunction<
            _ContextHandleSizeOutNative, _ContextHandleSizeOutDart>(
          'codex_agent_pending_interaction_list_count',
        ),
        pendingListAt = core.library.lookupFunction<
            _ContextHandleIndexHandleOutNative,
            _ContextHandleIndexHandleOutDart>(
          'codex_agent_pending_interaction_list_at',
        ),
        authorizationChatGpt = core.library.lookupFunction<
                _ContextStringHandleOutNative, _ContextStringHandleOutDart>(
            'codex_agent_authorization_url_chat_gpt'),
        authorizationExternal = core.library.lookupFunction<
                _ContextStringHandleOutNative, _ContextStringHandleOutDart>(
            'codex_agent_authorization_url_external'),
        authorizationValue = core.library
            .lookupFunction<_CopyHandleStringNative, _CopyHandleStringDart>(
                'codex_agent_authorization_url_value_copy'),
        authorizationPurpose = core.library.lookupFunction<
            _ContextHandleIntOutNative,
            _ContextHandleIntOutDart>('codex_agent_authorization_url_purpose');

  factory _ValueNativeApi.load() =>
      _ValueNativeApi._(NativeApi.load(resolveLibraryPathSync()));

  final NativeApi core;
  final _ContextStringHandleOutDart conversationIdCreate;
  final _CopyHandleStringDart conversationIdValue;
  final _ContextIntHandleOutDart formBooleanCreate;
  final _ContextHandleIntOutDart formBooleanValue;
  final _ContextDoubleHandleOutDart formNumberCreate;
  final _ContextHandleDoubleOutDart formNumberValue;
  final _ContextStringHandleOutDart formTextCreate;
  final _CopyHandleStringDart formTextValue;
  final _ContextStringsHandleOutDart formTextListCreate;
  final _ContextHandleSizeOutDart formTextListCount;
  final _CopyHandleIndexStringDart formTextListValueAt;
  final _ContextHandleHandleOutDart formValueFromBoolean;
  final _ContextHandleHandleOutDart formValueFromNumber;
  final _ContextHandleHandleOutDart formValueFromText;
  final _ContextHandleHandleOutDart formValueFromTextList;
  final _ContextHandleIntOutDart formValueKind;
  final _ContextHandleHandleOutDart formValueBoolean;
  final _ContextHandleHandleOutDart formValueNumber;
  final _ContextHandleHandleOutDart formValueText;
  final _ContextHandleHandleOutDart formValueTextList;
  final _FormOptionCreateDart formOptionCreate;
  final _FormFieldCreateDart formFieldCreate;
  final _ElicitationCreateDart elicitationCreate;
  final _KeyValueCreateDart formContentCreate;
  final _ContextHandleSizeOutDart formContentCount;
  final _CopyHandleIndexStringDart formContentKeyAt;
  final _ContextHandleStringHandleOutDart formContentValue;
  final _ResponseCreateDart responseCreate;
  final _ContextHandleIntOutDart responseAction;
  final _ContextHandleSizeOutDart responseCount;
  final _ContextHandleStringHandleOutDart responseValue;
  final _ContextHandleOutDart responseDecline;
  final _ContextHandleOutDart responseCancel;
  final _ContextHandleHandleOutDart elicitationInitialValues;
  final _ContextTwoHandlesHandleOutDart elicitationValidate;
  final _ContextTwoHandlesHandleOutDart elicitationAccept;
  final _ContextTwoHandlesIntOutDart elicitationAccepts;
  final _ContextTwoHandlesIntOutDart formFieldAccepts;
  final _ContextHandleSizeOutDart validationCount;
  final _ContextHandleIndexHandleOutDart validationIssueAt;
  final _CopyHandleStringDart validationIssueField;
  final _ContextHandleIntOutDart validationIssueReason;
  final _PendingApprovalCreateDart pendingApprovalCreate;
  final _ContextHandleHandleOutDart pendingElicitationCreate;
  final _ContextHandleHandleOutDart pendingFromApproval;
  final _ContextHandleHandleOutDart pendingFromElicitation;
  final _CopyHandleStringDart pendingRequestId;
  final _ContextHandleHandleOutDart pendingConversationId;
  final _FailureCreateDart failureCreate;
  final _InteractionStateCreateDart interactionStateCreate;
  final _ContextTwoHandlesIntOutDart interactionIsResolving;
  final _ContextHandleStringIntOutDart interactionContains;
  final _ContextTwoHandlesHandleOutDart interactionPendingFor;
  final _ContextHandleSizeOutDart pendingListCount;
  final _ContextHandleIndexHandleOutDart pendingListAt;
  final _ContextStringHandleOutDart authorizationChatGpt;
  final _ContextStringHandleOutDart authorizationExternal;
  final _CopyHandleStringDart authorizationValue;
  final _ContextHandleIntOutDart authorizationPurpose;
}

void _check(String symbol, int status,
    {Set<CodexStatus> allow = const <CodexStatus>{}}) {
  valueNativeCallObserver?.call(symbol);
  checkStatus(status, symbol, allow: allow);
}

Pointer<Void> _handle(
  String symbol,
  int Function(Pointer<Pointer<Void>>) invoke,
) {
  final slot = newHandleSlot<Void>();
  try {
    _check(symbol, invoke(slot));
    if (slot.value == nullptr) {
      throw CodexException('$symbol returned an absent owned value');
    }
    return slot.value;
  } finally {
    nativeMemory.free(slot);
  }
}

int _intValue(
  String symbol,
  int Function(Pointer<Int32>) invoke,
) {
  final output = nativeMemory.allocate<Int32>(sizeOf<Int32>());
  try {
    _check(symbol, invoke(output));
    return output.value;
  } finally {
    nativeMemory.free(output);
  }
}

int _sizeValue(
  String symbol,
  int Function(Pointer<Size>) invoke,
) {
  final output = nativeMemory.allocate<Size>(sizeOf<Size>());
  try {
    _check(symbol, invoke(output));
    return output.value;
  } finally {
    nativeMemory.free(output);
  }
}

double _doubleValue(
  String symbol,
  int Function(Pointer<Double>) invoke,
) {
  final output = nativeMemory.allocate<Double>(sizeOf<Double>());
  try {
    _check(symbol, invoke(output));
    return output.value;
  } finally {
    nativeMemory.free(output);
  }
}

String _copyString(
  String symbol,
  _CopyHandleStringDart copy,
  Pointer<CodexNativeContext> context,
  Pointer<Void> value,
) {
  final required = nativeMemory.allocate<Size>(sizeOf<Size>());
  try {
    _check(
      symbol,
      copy(context, value, nullptr, 0, required),
      allow: const <CodexStatus>{CodexStatus.bufferTooSmall},
    );
    if (required.value == 0) return '';
    final buffer = nativeMemory.allocate<Uint8>(required.value);
    try {
      _check(
        symbol,
        copy(context, value, buffer, required.value, required),
      );
      return utf8.decode(buffer.asTypedList(required.value));
    } finally {
      nativeMemory.free(buffer);
    }
  } finally {
    nativeMemory.free(required);
  }
}

String _copyIndexedString(
  String symbol,
  _CopyHandleIndexStringDart copy,
  Pointer<CodexNativeContext> context,
  Pointer<Void> value,
  int index,
) {
  final required = nativeMemory.allocate<Size>(sizeOf<Size>());
  try {
    _check(
      symbol,
      copy(context, value, index, nullptr, 0, required),
      allow: const <CodexStatus>{CodexStatus.bufferTooSmall},
    );
    if (required.value == 0) return '';
    final buffer = nativeMemory.allocate<Uint8>(required.value);
    try {
      _check(
        symbol,
        copy(context, value, index, buffer, required.value, required),
      );
      return utf8.decode(buffer.asTypedList(required.value));
    } finally {
      nativeMemory.free(buffer);
    }
  } finally {
    nativeMemory.free(required);
  }
}

final class _NativeStrings {
  _NativeStrings(Iterable<String> values)
      : values = values.map(NativeString.new).toList(growable: false) {
    if (this.values.isEmpty) {
      pointer = nullptr;
      return;
    }
    pointer = nativeMemory.allocate<CodexStringView>(
      sizeOf<CodexStringView>() * this.values.length,
    );
    for (var index = 0; index < this.values.length; index++) {
      final source = this.values[index].view.ref;
      (pointer + index).ref
        ..data = source.data
        ..size = source.size;
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

final class _NativeHandles {
  _NativeHandles(List<Pointer<Void>> values) : length = values.length {
    if (values.isEmpty) {
      pointer = nullptr;
      return;
    }
    pointer = nativeMemory.allocate<Pointer<Void>>(
      sizeOf<Pointer<Void>>() * values.length,
    );
    for (var index = 0; index < values.length; index++) {
      (pointer + index).value = values[index];
    }
  }

  final int length;
  late final Pointer<Pointer<Void>> pointer;

  void close() => nativeMemory.free(pointer);
}

T _scope<T>(
  T Function(_ValueNativeApi api, Pointer<CodexNativeContext> context) body,
) {
  final api = _ValueNativeApi.load();
  final contextSlot = newHandleSlot<CodexNativeContext>();
  try {
    _check('codex_agent_context_create', api.core.contextCreate(contextSlot));
    try {
      return body(api, contextSlot.value);
    } on CodexNativeException catch (error) {
      if (error.status == CodexStatus.invalidArgument) {
        throw ArgumentError(error.message);
      }
      rethrow;
    } finally {
      if (contextSlot.value != nullptr) {
        _check(
          'codex_agent_context_destroy',
          api.core.contextDestroy(contextSlot),
        );
      }
    }
  } finally {
    nativeMemory.free(contextSlot);
  }
}

Pointer<Void> _createConversationId(
  _ValueNativeApi api,
  Pointer<CodexNativeContext> context,
  CodexConversationId id,
) {
  final value = NativeString(id.value);
  try {
    return _handle(
      'codex_agent_conversation_id_create',
      (output) => api.conversationIdCreate(context, value.view, output),
    );
  } finally {
    value.close();
  }
}

Pointer<Void> _createFormValue(
  _ValueNativeApi api,
  Pointer<CodexNativeContext> context,
  CodexFormValue value,
) {
  late final Pointer<Void> concrete;
  late final String wrapperSymbol;
  late final _ContextHandleHandleOutDart wrapper;
  switch (value) {
    case CodexBooleanFormValue(:final value):
      concrete = _handle(
        'codex_agent_form_boolean_value_create',
        (output) => api.formBooleanCreate(context, value ? 1 : 0, output),
      );
      wrapperSymbol = 'codex_agent_form_value_from_boolean';
      wrapper = api.formValueFromBoolean;
    case CodexNumberFormValue(:final value):
      concrete = _handle(
        'codex_agent_form_number_value_create',
        (output) => api.formNumberCreate(context, value, output),
      );
      wrapperSymbol = 'codex_agent_form_value_from_number';
      wrapper = api.formValueFromNumber;
    case CodexTextFormValue(:final value):
      final text = NativeString(value);
      try {
        concrete = _handle(
          'codex_agent_form_text_value_create',
          (output) => api.formTextCreate(context, text.view, output),
        );
      } finally {
        text.close();
      }
      wrapperSymbol = 'codex_agent_form_value_from_text';
      wrapper = api.formValueFromText;
    case CodexTextListFormValue(:final value):
      final values = _NativeStrings(value);
      try {
        concrete = _handle(
          'codex_agent_form_text_list_value_create',
          (output) => api.formTextListCreate(
            context,
            values.pointer,
            values.values.length,
            output,
          ),
        );
      } finally {
        values.close();
      }
      wrapperSymbol = 'codex_agent_form_value_from_text_list';
      wrapper = api.formValueFromTextList;
  }
  return _handle(
    wrapperSymbol,
    (output) => wrapper(context, concrete, output),
  );
}

CodexFormValue _readFormValue(
  _ValueNativeApi api,
  Pointer<CodexNativeContext> context,
  Pointer<Void> value,
) {
  final kind = _intValue(
    'codex_agent_form_value_kind',
    (output) => api.formValueKind(context, value, output),
  );
  final concrete = switch (kind) {
    0 => _handle(
        'codex_agent_form_value_boolean',
        (output) => api.formValueBoolean(context, value, output),
      ),
    1 => _handle(
        'codex_agent_form_value_number',
        (output) => api.formValueNumber(context, value, output),
      ),
    2 => _handle(
        'codex_agent_form_value_text',
        (output) => api.formValueText(context, value, output),
      ),
    3 => _handle(
        'codex_agent_form_value_text_list',
        (output) => api.formValueTextList(context, value, output),
      ),
    _ => throw CodexException('unknown native form value kind: $kind'),
  };
  return switch (kind) {
    0 => CodexBooleanFormValue(
        _intValue(
              'codex_agent_form_boolean_value_value',
              (output) => api.formBooleanValue(context, concrete, output),
            ) !=
            0,
      ),
    1 => CodexNumberFormValue(
        _doubleValue(
          'codex_agent_form_number_value_value',
          (output) => api.formNumberValue(context, concrete, output),
        ),
      ),
    2 => CodexTextFormValue(
        _copyString(
          'codex_agent_form_text_value_value_copy',
          api.formTextValue,
          context,
          concrete,
        ),
      ),
    3 => CodexTextListFormValue(
        List<String>.generate(
          _sizeValue(
            'codex_agent_form_text_list_value_count',
            (output) => api.formTextListCount(context, concrete, output),
          ),
          (index) => _copyIndexedString(
            'codex_agent_form_text_list_value_copy_at',
            api.formTextListValueAt,
            context,
            concrete,
            index,
          ),
          growable: false,
        ),
      ),
    _ => throw StateError('unreachable form value kind'),
  };
}

Pointer<Void> _createOption(
  _ValueNativeApi api,
  Pointer<CodexNativeContext> context,
  CodexFormOption option,
) {
  final value = NativeString(option.value);
  final title = NativeString(option.title);
  final description = option.description == null
      ? NativeString.absent()
      : NativeString(option.description!);
  try {
    return _handle(
      'codex_agent_form_option_create',
      (output) => api.formOptionCreate(
        context,
        value.view,
        1,
        title.view,
        option.description == null ? 0 : 1,
        description.view,
        output,
      ),
    );
  } finally {
    description.close();
    title.close();
    value.close();
  }
}

Pointer<Void> _createField(
  _ValueNativeApi api,
  Pointer<CodexNativeContext> context,
  CodexFormField field,
) {
  final name = NativeString(field.name);
  final title = NativeString(field.title);
  final description = field.description == null
      ? NativeString.absent()
      : NativeString(field.description!);
  final optionHandles = field.options
      .map((option) => _createOption(api, context, option))
      .toList(growable: false);
  final options = _NativeHandles(optionHandles);
  final defaultValue = field.defaultValue == null
      ? nullptr
      : _createFormValue(api, context, field.defaultValue!);
  try {
    return _handle(
      'codex_agent_form_field_create',
      (output) => api.formFieldCreate(
        context,
        name.view,
        title.view,
        field.description == null ? 0 : 1,
        description.view,
        field.isRequired ? 1 : 0,
        field.type.value,
        options.pointer,
        options.length,
        field.defaultValue == null ? 0 : 1,
        defaultValue,
        field.minimum == null ? 0 : 1,
        field.minimum ?? 0,
        field.maximum == null ? 0 : 1,
        field.maximum ?? 0,
        field.format == null ? 0 : 1,
        field.format?.value ?? 0,
        field.minimumLength == null ? 0 : 1,
        field.minimumLength ?? 0,
        field.maximumLength == null ? 0 : 1,
        field.maximumLength ?? 0,
        field.minimumSelections == null ? 0 : 1,
        field.minimumSelections ?? 0,
        field.maximumSelections == null ? 0 : 1,
        field.maximumSelections ?? 0,
        field.allowsOther ? 1 : 0,
        field.isSecret ? 1 : 0,
        output,
      ),
    );
  } finally {
    options.close();
    description.close();
    title.close();
    name.close();
  }
}

Pointer<Void> _createElicitation(
  _ValueNativeApi api,
  Pointer<CodexNativeContext> context,
  CodexElicitation elicitation,
) {
  final requestId = NativeString(elicitation.requestId);
  final serverName = NativeString(elicitation.serverName);
  final message = NativeString(elicitation.message);
  final url = elicitation.url == null
      ? NativeString.absent()
      : NativeString(elicitation.url!);
  final conversationId =
      _createConversationId(api, context, elicitation.conversationId);
  final fields = (elicitation.form ?? const <CodexFormField>[])
      .map((field) => _createField(api, context, field))
      .toList(growable: false);
  final fieldHandles = _NativeHandles(fields);
  try {
    return _handle(
      'codex_agent_elicitation_create',
      (output) => api.elicitationCreate(
        context,
        requestId.view,
        serverName.view,
        conversationId,
        message.view,
        elicitation.form == null ? 0 : 1,
        fieldHandles.pointer,
        fieldHandles.length,
        elicitation.url == null ? 0 : 1,
        url.view,
        output,
      ),
    );
  } finally {
    fieldHandles.close();
    url.close();
    message.close();
    serverName.close();
    requestId.close();
  }
}

Pointer<Void> _createContent(
  _ValueNativeApi api,
  Pointer<CodexNativeContext> context,
  Map<String, CodexFormValue> content,
) {
  final keys = content.keys.toList(growable: false);
  final nativeKeys = _NativeStrings(keys);
  final values = keys
      .map((key) => _createFormValue(api, context, content[key]!))
      .toList(growable: false);
  final nativeValues = _NativeHandles(values);
  try {
    return _handle(
      'codex_agent_form_content_create',
      (output) => api.formContentCreate(
        context,
        nativeKeys.pointer,
        nativeValues.pointer,
        keys.length,
        output,
      ),
    );
  } finally {
    nativeValues.close();
    nativeKeys.close();
  }
}

Map<String, CodexFormValue> _readContent(
  _ValueNativeApi api,
  Pointer<CodexNativeContext> context,
  Pointer<Void> content,
) {
  final result = <String, CodexFormValue>{};
  final count = _sizeValue(
    'codex_agent_form_content_count',
    (output) => api.formContentCount(context, content, output),
  );
  for (var index = 0; index < count; index++) {
    final key = _copyIndexedString(
      'codex_agent_form_content_key_copy',
      api.formContentKeyAt,
      context,
      content,
      index,
    );
    final nativeKey = NativeString(key);
    try {
      result[key] = _readFormValue(
        api,
        context,
        _handle(
          'codex_agent_form_content_value_at',
          (output) =>
              api.formContentValue(context, content, nativeKey.view, output),
        ),
      );
    } finally {
      nativeKey.close();
    }
  }
  return Map<String, CodexFormValue>.unmodifiable(result);
}

Pointer<Void> _createResponse(
  _ValueNativeApi api,
  Pointer<CodexNativeContext> context,
  CodexElicitationResponse response,
) {
  final keys = response.content.keys.toList(growable: false);
  final nativeKeys = _NativeStrings(keys);
  final values = keys
      .map((key) => _createFormValue(api, context, response.content[key]!))
      .toList(growable: false);
  final nativeValues = _NativeHandles(values);
  try {
    return _handle(
      'codex_agent_elicitation_response_create',
      (output) => api.responseCreate(
        context,
        response.action.value,
        nativeKeys.pointer,
        nativeValues.pointer,
        keys.length,
        output,
      ),
    );
  } finally {
    nativeValues.close();
    nativeKeys.close();
  }
}

/// Reuses the verified value bridge for a service operation in the caller's
/// native context. This library-internal seam is not exported by the SDK.
Pointer<Void> createLeafNativeElicitationResponse(
  NativeApi core,
  Pointer<CodexNativeContext> context,
  CodexElicitationResponse response,
) =>
    _createResponse(_ValueNativeApi._(core), context, response);

CodexElicitationResponse _readResponse(
  _ValueNativeApi api,
  Pointer<CodexNativeContext> context,
  Pointer<Void> response,
  List<String> keys,
) {
  final count = _sizeValue(
    'codex_agent_elicitation_response_content_count',
    (output) => api.responseCount(context, response, output),
  );
  if (count != keys.length) {
    throw CodexException('native elicitation response content is inexact');
  }
  final content = <String, CodexFormValue>{};
  for (final key in keys) {
    final nativeKey = NativeString(key);
    try {
      content[key] = _readFormValue(
        api,
        context,
        _handle(
          'codex_agent_elicitation_response_content_value',
          (output) =>
              api.responseValue(context, response, nativeKey.view, output),
        ),
      );
    } finally {
      nativeKey.close();
    }
  }
  final action = _intValue(
    'codex_agent_elicitation_response_action',
    (output) => api.responseAction(context, response, output),
  );
  if (action < 0 || action >= CodexElicitationAction.values.length) {
    throw CodexException('unknown native elicitation action: $action');
  }
  return CodexElicitationResponse(
    action: CodexElicitationAction.values[action],
    content: content,
  );
}

CodexElicitationResponse nativeResponseFactory(String symbol) =>
    _scope((api, context) {
      final factory = switch (symbol) {
        'codex_agent_elicitation_response_decline' => api.responseDecline,
        'codex_agent_elicitation_response_cancel' => api.responseCancel,
        _ => throw ArgumentError.value(symbol, 'symbol', 'unsupported factory'),
      };
      final response = _handle(
        symbol,
        (output) => factory(context, output),
      );
      return _readResponse(api, context, response, const <String>[]);
    });

Map<String, CodexFormValue> nativeElicitationInitialValues(
  CodexElicitation elicitation,
) =>
    _scope((api, context) {
      final nativeElicitation = _createElicitation(api, context, elicitation);
      final content = _handle(
        'codex_agent_elicitation_initial_values',
        (output) =>
            api.elicitationInitialValues(context, nativeElicitation, output),
      );
      return _readContent(api, context, content);
    });

CodexElicitationValidation nativeElicitationValidate(
  CodexElicitation elicitation,
  Map<String, CodexFormValue> content,
) =>
    _scope((api, context) {
      final nativeElicitation = _createElicitation(api, context, elicitation);
      final nativeContent = _createContent(api, context, content);
      final validation = _handle(
        'codex_agent_elicitation_validate',
        (output) => api.elicitationValidate(
          context,
          nativeElicitation,
          nativeContent,
          output,
        ),
      );
      final count = _sizeValue(
        'codex_agent_elicitation_validation_issue_count',
        (output) => api.validationCount(context, validation, output),
      );
      final issues = <CodexElicitationValidationIssue>[];
      for (var index = 0; index < count; index++) {
        final issue = _handle(
          'codex_agent_elicitation_validation_issue_at',
          (output) => api.validationIssueAt(context, validation, index, output),
        );
        final reason = _intValue(
          'codex_agent_elicitation_validation_issue_reason',
          (output) => api.validationIssueReason(context, issue, output),
        );
        if (reason < 0 ||
            reason >= CodexElicitationValidationReason.values.length) {
          throw CodexException('unknown native validation reason: $reason');
        }
        issues.add(
          CodexElicitationValidationIssue(
            fieldName: _copyString(
              'codex_agent_elicitation_validation_issue_field_name_copy',
              api.validationIssueField,
              context,
              issue,
            ),
            reason: CodexElicitationValidationReason.values[reason],
          ),
        );
      }
      return CodexElicitationValidation(issues: issues);
    });

CodexElicitationResponse nativeElicitationAccept(
  CodexElicitation elicitation,
  Map<String, CodexFormValue> content,
) =>
    _scope((api, context) {
      final nativeElicitation = _createElicitation(api, context, elicitation);
      final nativeContent = _createContent(api, context, content);
      final response = _handle(
        'codex_agent_elicitation_accept',
        (output) => api.elicitationAccept(
          context,
          nativeElicitation,
          nativeContent,
          output,
        ),
      );
      return _readResponse(
        api,
        context,
        response,
        content.keys.toList(growable: false),
      );
    });

bool nativeElicitationAccepts(
  CodexElicitation elicitation,
  CodexElicitationResponse response,
) =>
    _scope((api, context) {
      final nativeElicitation = _createElicitation(api, context, elicitation);
      final nativeResponse = _createResponse(api, context, response);
      return _intValue(
            'codex_agent_elicitation_accepts',
            (output) => api.elicitationAccepts(
              context,
              nativeElicitation,
              nativeResponse,
              output,
            ),
          ) !=
          0;
    });

bool nativeFormFieldAccepts(
  CodexFormField field,
  CodexFormValue? value,
) =>
    _scope((api, context) {
      final nativeField = _createField(api, context, field);
      final nativeValue =
          value == null ? nullptr : _createFormValue(api, context, value);
      return _intValue(
            'codex_agent_form_field_accepts',
            (output) => api.formFieldAccepts(
              context,
              nativeField,
              nativeValue,
              output,
            ),
          ) !=
          0;
    });

Pointer<Void> _createPending(
  _ValueNativeApi api,
  Pointer<CodexNativeContext> context,
  CodexPendingInteraction pending,
) {
  switch (pending) {
    case CodexPendingApproval():
      final requestId = NativeString(pending.requestId);
      final title = NativeString(pending.title);
      final details = NativeString(pending.details);
      final conversationId =
          _createConversationId(api, context, pending.conversationId);
      try {
        final approval = _handle(
          'codex_agent_pending_approval_create',
          (output) => api.pendingApprovalCreate(
            context,
            requestId.view,
            conversationId,
            title.view,
            details.view,
            output,
          ),
        );
        return _handle(
          'codex_agent_pending_interaction_from_approval',
          (output) => api.pendingFromApproval(context, approval, output),
        );
      } finally {
        details.close();
        title.close();
        requestId.close();
      }
    case CodexPendingElicitation():
      final elicitation = _createElicitation(api, context, pending.elicitation);
      final pendingElicitation = _handle(
        'codex_agent_pending_elicitation_create',
        (output) => api.pendingElicitationCreate(context, elicitation, output),
      );
      return _handle(
        'codex_agent_pending_interaction_from_elicitation',
        (output) =>
            api.pendingFromElicitation(context, pendingElicitation, output),
      );
  }
}

Pointer<Void> _createFailure(
  _ValueNativeApi api,
  Pointer<CodexNativeContext> context,
  CodexFailure failure,
) {
  final code = NativeString(failure.code);
  final message = NativeString(failure.message);
  try {
    return _handle(
      'codex_agent_failure_create',
      (output) => api.failureCreate(
        context,
        code.view,
        message.view,
        failure.isRecoverable ? 1 : 0,
        output,
      ),
    );
  } finally {
    message.close();
    code.close();
  }
}

({Pointer<Void> state, List<Pointer<Void>> pending}) _createInteractionState(
  _ValueNativeApi api,
  Pointer<CodexNativeContext> context,
  CodexInteractionState state,
) {
  final pending = state.pending
      .map((value) => _createPending(api, context, value))
      .toList(growable: false);
  final nativePending = _NativeHandles(pending);
  final resolving = _NativeStrings(state.resolvingRequestIds.toList()..sort());
  final failure = state.failure == null
      ? nullptr
      : _createFailure(api, context, state.failure!);
  try {
    return (
      state: _handle(
        'codex_agent_interaction_state_create',
        (output) => api.interactionStateCreate(
          context,
          nativePending.pointer,
          nativePending.length,
          resolving.pointer,
          resolving.values.length,
          state.failure == null ? 0 : 1,
          failure,
          output,
        ),
      ),
      pending: pending,
    );
  } finally {
    resolving.close();
    nativePending.close();
  }
}

bool nativeInteractionIsResolving(
  CodexInteractionState state,
  CodexPendingInteraction interaction,
) =>
    _scope((api, context) {
      final nativeState = _createInteractionState(api, context, state);
      Pointer<Void>? matching;
      for (var index = 0; index < state.pending.length; index++) {
        if (identical(state.pending[index], interaction)) {
          matching = nativeState.pending[index];
          break;
        }
      }
      final nativeInteraction =
          matching ?? _createPending(api, context, interaction);
      final exact = _intValue(
            'codex_agent_interaction_state_is_resolving',
            (output) => api.interactionIsResolving(
              context,
              nativeState.state,
              nativeInteraction,
              output,
            ),
          ) !=
          0;
      if (matching == null || exact) return exact;
      final requestId = NativeString(interaction.requestId);
      try {
        return _intValue(
              'codex_agent_interaction_state_resolving_request_ids_contains',
              (output) => api.interactionContains(
                context,
                nativeState.state,
                requestId.view,
                output,
              ),
            ) !=
            0;
      } finally {
        requestId.close();
      }
    });

({String requestId, String conversationId}) _pendingSignature(
  _ValueNativeApi api,
  Pointer<CodexNativeContext> context,
  Pointer<Void> pending,
) {
  final conversation = _handle(
    'codex_agent_pending_interaction_conversation_id',
    (output) => api.pendingConversationId(context, pending, output),
  );
  return (
    requestId: _copyString(
      'codex_agent_pending_interaction_request_id_copy',
      api.pendingRequestId,
      context,
      pending,
    ),
    conversationId: _copyString(
      'codex_agent_conversation_id_value_copy',
      api.conversationIdValue,
      context,
      conversation,
    ),
  );
}

List<CodexPendingInteraction> nativeInteractionPendingFor(
  CodexInteractionState state,
  CodexConversationId conversationId,
) =>
    _scope((api, context) {
      final nativeState = _createInteractionState(api, context, state);
      final nativeConversation =
          _createConversationId(api, context, conversationId);
      final result = _handle(
        'codex_agent_interaction_state_pending_for',
        (output) => api.interactionPendingFor(
          context,
          nativeState.state,
          nativeConversation,
          output,
        ),
      );
      final originals = <({String requestId, String conversationId}),
          List<CodexPendingInteraction>>{};
      for (final interaction in state.pending) {
        originals.putIfAbsent(
          (
            requestId: interaction.requestId,
            conversationId: interaction.conversationId.value,
          ),
          () => <CodexPendingInteraction>[],
        ).add(interaction);
      }
      final occurrences = <({String requestId, String conversationId}), int>{};
      final selected = <CodexPendingInteraction>[];
      final count = _sizeValue(
        'codex_agent_pending_interaction_list_count',
        (output) => api.pendingListCount(context, result, output),
      );
      for (var index = 0; index < count; index++) {
        final pending = _handle(
          'codex_agent_pending_interaction_list_at',
          (output) => api.pendingListAt(context, result, index, output),
        );
        final signature = _pendingSignature(api, context, pending);
        final occurrence = occurrences[signature] ?? 0;
        final candidates =
            originals[signature] ?? const <CodexPendingInteraction>[];
        if (occurrence >= candidates.length) {
          throw CodexException(
            'native pendingFor result does not match Dart ownership graph',
          );
        }
        selected.add(candidates[occurrence]);
        occurrences[signature] = occurrence + 1;
      }
      return List<CodexPendingInteraction>.unmodifiable(selected);
    });

({String value, CodexAuthorizationPurpose purpose}) nativeAuthorizationUrl(
  String symbol,
  String value,
) =>
    _scope((api, context) {
      final nativeValue = NativeString(value);
      try {
        final factory = switch (symbol) {
          'codex_agent_authorization_url_chat_gpt' => api.authorizationChatGpt,
          'codex_agent_authorization_url_external' => api.authorizationExternal,
          _ => throw ArgumentError.value(
              symbol,
              'symbol',
              'unsupported authorization URL factory',
            ),
        };
        final url = _handle(
          symbol,
          (output) => factory(context, nativeValue.view, output),
        );
        final purpose = _intValue(
          'codex_agent_authorization_url_purpose',
          (output) => api.authorizationPurpose(context, url, output),
        );
        if (purpose < 0 || purpose >= CodexAuthorizationPurpose.values.length) {
          throw CodexException(
              'unknown native authorization purpose: $purpose');
        }
        return (
          value: _copyString(
            'codex_agent_authorization_url_value_copy',
            api.authorizationValue,
            context,
            url,
          ),
          purpose: CodexAuthorizationPurpose.values[purpose],
        );
      } finally {
        nativeValue.close();
      }
    });
