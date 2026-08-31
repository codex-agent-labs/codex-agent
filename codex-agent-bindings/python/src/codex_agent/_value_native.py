from __future__ import annotations

import ctypes
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from types import MappingProxyType

from ._enums import (
    AuthorizationPurpose,
    ElicitationAction,
    ElicitationValidationReason,
)
from ._errors import NativeStatusError, Status
from ._ffi import Handle, NativeLibrary, StringView, load_native, null_view, utf8_view
from ._models import ConversationId
from ._residual_values import (
    AuthorizationUrl,
    Elicitation,
    ElicitationResponse,
    FormBooleanValue,
    FormField,
    FormNumberValue,
    FormTextListValue,
    FormTextValue,
    FormValue,
    InteractionState,
    PendingApproval,
    PendingElicitation,
    PendingInteractionValue,
)
from ._values import ElicitationValidation, ElicitationValidationIssue, FormOption


@contextmanager
def _scope() -> Iterator[tuple[NativeLibrary, Handle]]:
    native = load_native()
    context = Handle()
    native.call("codex_agent_context_create", ctypes.byref(context))
    try:
        yield native, context
    except NativeStatusError as error:
        if error.status is Status.INVALID_ARGUMENT:
            raise ValueError(str(error)) from None
        raise
    finally:
        if context.value:
            native.call("codex_agent_context_destroy", ctypes.byref(context))


def _handle(native: NativeLibrary, name: str, *arguments: object) -> Handle:
    result = Handle()
    native.call(name, *arguments, ctypes.byref(result))
    if not result.value:
        raise RuntimeError(f"{name} returned an absent owned value")
    return result


def _i32(native: NativeLibrary, name: str, *arguments: object) -> int:
    result = ctypes.c_int32()
    native.call(name, *arguments, ctypes.byref(result))
    return result.value


def _size(native: NativeLibrary, name: str, *arguments: object) -> int:
    result = ctypes.c_size_t()
    native.call(name, *arguments, ctypes.byref(result))
    return result.value


def _view(value: str) -> tuple[StringView, object | None]:
    return utf8_view(value)


def _views(values: Sequence[str]) -> tuple[object, tuple[object | None, ...]]:
    converted = tuple(_view(value) for value in values)
    return (
        (StringView * len(converted))(*(view for view, _ in converted))
        if converted
        else None,
        tuple(backing for _, backing in converted),
    )


def _handles(values: Sequence[Handle]) -> object:
    return (Handle * len(values))(*(value.value for value in values)) if values else None


def _create_conversation_id(
    native: NativeLibrary, context: Handle, value: ConversationId
) -> Handle:
    view, backing = _view(value.value)
    return _handle(
        native, "codex_agent_conversation_id_create", context, ctypes.byref(view)
    )


def _create_form_value(
    native: NativeLibrary, context: Handle, value: FormValue
) -> Handle:
    if isinstance(value, FormBooleanValue):
        concrete = _handle(
            native,
            "codex_agent_form_boolean_value_create",
            context,
            int(value.value),
        )
        suffix = "boolean"
    elif isinstance(value, FormNumberValue):
        concrete = _handle(
            native, "codex_agent_form_number_value_create", context, value.value
        )
        suffix = "number"
    elif isinstance(value, FormTextValue):
        view, backing = _view(value.value)
        concrete = _handle(
            native,
            "codex_agent_form_text_value_create",
            context,
            ctypes.byref(view),
        )
        suffix = "text"
    elif isinstance(value, FormTextListValue):
        views, backings = _views(value.value)
        concrete = _handle(
            native,
            "codex_agent_form_text_list_value_create",
            context,
            views,
            len(value.value),
        )
        suffix = "text_list"
    else:
        raise TypeError(f"unsupported form value: {type(value).__name__}")
    try:
        return _handle(native, f"codex_agent_form_value_from_{suffix}", context, concrete)
    finally:
        native.call(
            f"codex_agent_form_{suffix}_value_destroy",
            context,
            ctypes.byref(concrete),
        )


def _read_form_value(
    native: NativeLibrary, context: Handle, value: Handle
) -> FormValue:
    try:
        kind = _i32(native, "codex_agent_form_value_kind", context, value)
        names = ("boolean", "number", "text", "text_list")
        if not 0 <= kind < len(names):
            raise RuntimeError(f"unknown native form value kind {kind}")
        name = names[kind]
        concrete = _handle(native, f"codex_agent_form_value_{name}", context, value)
        try:
            if name == "boolean":
                return FormBooleanValue(
                    bool(_i32(native, "codex_agent_form_boolean_value_value", context, concrete))
                )
            if name == "number":
                result = ctypes.c_double()
                native.call(
                    "codex_agent_form_number_value_value",
                    context,
                    concrete,
                    ctypes.byref(result),
                )
                return FormNumberValue(result.value)
            if name == "text":
                return FormTextValue(
                    native.copy_string(
                        "codex_agent_form_text_value_value_copy", context, concrete
                    )
                )
            return FormTextListValue(
                tuple(
                    native.copy_string(
                        "codex_agent_form_text_list_value_copy_at", context, concrete, index
                    )
                    for index in range(
                        _size(
                            native,
                            "codex_agent_form_text_list_value_count",
                            context,
                            concrete,
                        )
                    )
                )
            )
        finally:
            native.call(
                f"codex_agent_form_{name}_value_destroy",
                context,
                ctypes.byref(concrete),
            )
    finally:
        native.call("codex_agent_form_value_destroy", context, ctypes.byref(value))


def _create_option(
    native: NativeLibrary, context: Handle, option: FormOption
) -> Handle:
    value, value_backing = _view(option.value)
    title, title_backing = _view(option.title)
    description, description_backing = (
        _view(option.description) if option.description is not None else (null_view(), None)
    )
    return _handle(
        native,
        "codex_agent_form_option_create",
        context,
        ctypes.byref(value),
        1,
        ctypes.byref(title),
        int(option.description is not None),
        ctypes.byref(description),
    )


def _create_field(native: NativeLibrary, context: Handle, field: FormField) -> Handle:
    name, name_backing = _view(field.name)
    title, title_backing = _view(field.title)
    description, description_backing = (
        _view(field.description) if field.description is not None else (null_view(), None)
    )
    options = tuple(_create_option(native, context, option) for option in field.options)
    options_array = _handles(options)
    default = (
        _create_form_value(native, context, field.default_value)
        if field.default_value is not None
        else Handle()
    )
    return _handle(
        native,
        "codex_agent_form_field_create",
        context,
        ctypes.byref(name),
        ctypes.byref(title),
        int(field.description is not None),
        ctypes.byref(description),
        int(field.is_required),
        int(field.type),
        options_array,
        len(options),
        int(field.default_value is not None),
        default,
        int(field.minimum is not None),
        0.0 if field.minimum is None else field.minimum,
        int(field.maximum is not None),
        0.0 if field.maximum is None else field.maximum,
        int(field.format is not None),
        0 if field.format is None else int(field.format),
        int(field.minimum_length is not None),
        0 if field.minimum_length is None else field.minimum_length,
        int(field.maximum_length is not None),
        0 if field.maximum_length is None else field.maximum_length,
        int(field.minimum_selections is not None),
        0 if field.minimum_selections is None else field.minimum_selections,
        int(field.maximum_selections is not None),
        0 if field.maximum_selections is None else field.maximum_selections,
        int(field.allows_other),
        int(field.is_secret),
    )


def _create_elicitation(
    native: NativeLibrary, context: Handle, elicitation: Elicitation
) -> Handle:
    request_id, request_backing = _view(elicitation.request_id)
    server_name, server_backing = _view(elicitation.server_name)
    message, message_backing = _view(elicitation.message)
    url, url_backing = (
        _view(elicitation.url) if elicitation.url is not None else (null_view(), None)
    )
    conversation_id = _create_conversation_id(
        native, context, elicitation.conversation_id
    )
    fields = tuple(
        _create_field(native, context, field) for field in elicitation.form or ()
    )
    return _handle(
        native,
        "codex_agent_elicitation_create",
        context,
        ctypes.byref(request_id),
        ctypes.byref(server_name),
        conversation_id,
        ctypes.byref(message),
        int(elicitation.form is not None),
        _handles(fields),
        len(fields),
        int(elicitation.url is not None),
        ctypes.byref(url),
    )


def _create_content(
    native: NativeLibrary, context: Handle, content: Mapping[str, FormValue]
) -> Handle:
    keys = tuple(content)
    key_views, key_backings = _views(keys)
    values = tuple(_create_form_value(native, context, content[key]) for key in keys)
    return _handle(
        native,
        "codex_agent_form_content_create",
        context,
        key_views,
        _handles(values),
        len(keys),
    )


def _read_content(
    native: NativeLibrary, context: Handle, content: Handle
) -> Mapping[str, FormValue]:
    result: dict[str, FormValue] = {}
    for index in range(_size(native, "codex_agent_form_content_count", context, content)):
        key = native.copy_string(
            "codex_agent_form_content_key_copy", context, content, index
        )
        view, backing = _view(key)
        result[key] = _read_form_value(
            native,
            context,
            _handle(
                native,
                "codex_agent_form_content_value_at",
                context,
                content,
                ctypes.byref(view),
            ),
        )
    return MappingProxyType(result)


def _create_response(
    native: NativeLibrary, context: Handle, response: ElicitationResponse
) -> Handle:
    keys = tuple(response.content)
    key_views, key_backings = _views(keys)
    values = tuple(
        _create_form_value(native, context, response.content[key]) for key in keys
    )
    try:
        return _handle(
            native,
            "codex_agent_elicitation_response_create",
            context,
            int(response.action),
            key_views,
            _handles(values),
            len(keys),
        )
    finally:
        for value in values:
            native.call("codex_agent_form_value_destroy", context, ctypes.byref(value))


def _read_response(
    native: NativeLibrary,
    context: Handle,
    response: Handle,
    keys: Sequence[str],
) -> ElicitationResponse:
    if _size(
        native, "codex_agent_elicitation_response_content_count", context, response
    ) != len(keys):
        raise RuntimeError("native elicitation response returned an unexpected content size")
    content: dict[str, FormValue] = {}
    for key in keys:
        view, backing = _view(key)
        content[key] = _read_form_value(
            native,
            context,
            _handle(
                native,
                "codex_agent_elicitation_response_content_value",
                context,
                response,
                ctypes.byref(view),
            ),
        )
    return ElicitationResponse(
        ElicitationAction(
            _i32(
                native,
                "codex_agent_elicitation_response_action",
                context,
                response,
            )
        ),
        content,
    )


def response_factory(symbol: str) -> ElicitationResponse:
    with _scope() as (native, context):
        response = _handle(native, symbol, context)
        return _read_response(native, context, response, ())


def elicitation_initial_values(
    elicitation: Elicitation,
) -> Mapping[str, FormValue]:
    with _scope() as (native, context):
        value = _create_elicitation(native, context, elicitation)
        result = _handle(
            native, "codex_agent_elicitation_initial_values", context, value
        )
        return _read_content(native, context, result)


def elicitation_validate(
    elicitation: Elicitation, content: Mapping[str, FormValue]
) -> ElicitationValidation:
    with _scope() as (native, context):
        value = _create_elicitation(native, context, elicitation)
        native_content = _create_content(native, context, content)
        validation = _handle(
            native,
            "codex_agent_elicitation_validate",
            context,
            value,
            native_content,
        )
        issues = []
        for index in range(
            _size(
                native,
                "codex_agent_elicitation_validation_issue_count",
                context,
                validation,
            )
        ):
            issue = _handle(
                native,
                "codex_agent_elicitation_validation_issue_at",
                context,
                validation,
                index,
            )
            issues.append(
                ElicitationValidationIssue(
                    native.copy_string(
                        "codex_agent_elicitation_validation_issue_field_name_copy",
                        context,
                        issue,
                    ),
                    ElicitationValidationReason(
                        _i32(
                            native,
                            "codex_agent_elicitation_validation_issue_reason",
                            context,
                            issue,
                        )
                    ),
                )
            )
        return ElicitationValidation(issues)


def elicitation_accept(
    elicitation: Elicitation, content: Mapping[str, FormValue]
) -> ElicitationResponse:
    with _scope() as (native, context):
        value = _create_elicitation(native, context, elicitation)
        native_content = _create_content(native, context, content)
        response = _handle(
            native,
            "codex_agent_elicitation_accept",
            context,
            value,
            native_content,
        )
        return _read_response(native, context, response, tuple(content))


def elicitation_accepts(
    elicitation: Elicitation, response: ElicitationResponse
) -> bool:
    with _scope() as (native, context):
        value = _create_elicitation(native, context, elicitation)
        native_response = _create_response(native, context, response)
        return bool(
            _i32(
                native,
                "codex_agent_elicitation_accepts",
                context,
                value,
                native_response,
            )
        )


def form_field_accepts(field: FormField, value: FormValue | None) -> bool:
    with _scope() as (native, context):
        native_field = _create_field(native, context, field)
        native_value = (
            _create_form_value(native, context, value) if value is not None else Handle()
        )
        return bool(
            _i32(
                native,
                "codex_agent_form_field_accepts",
                context,
                native_field,
                native_value,
            )
        )


def authorization_url_parts(
    symbol: str, value: str
) -> tuple[str, AuthorizationPurpose]:
    with _scope() as (native, context):
        view, backing = _view(value)
        url = _handle(native, symbol, context, ctypes.byref(view))
        return (
            native.copy_string(
                "codex_agent_authorization_url_value_copy", context, url
            ),
            AuthorizationPurpose(
                _i32(native, "codex_agent_authorization_url_purpose", context, url)
            ),
        )


def _create_pending(
    native: NativeLibrary,
    context: Handle,
    interaction: PendingInteractionValue,
) -> Handle:
    if isinstance(interaction, PendingApproval):
        request_id, request_backing = _view(interaction.request_id)
        title, title_backing = _view(interaction.title)
        details, details_backing = _view(interaction.details)
        conversation_id = _create_conversation_id(
            native, context, interaction.conversation_id
        )
        approval = _handle(
            native,
            "codex_agent_pending_approval_create",
            context,
            ctypes.byref(request_id),
            conversation_id,
            ctypes.byref(title),
            ctypes.byref(details),
        )
        return _handle(
            native,
            "codex_agent_pending_interaction_from_approval",
            context,
            approval,
        )
    if isinstance(interaction, PendingElicitation):
        elicitation = _create_elicitation(native, context, interaction.elicitation)
        pending = _handle(
            native,
            "codex_agent_pending_elicitation_create",
            context,
            elicitation,
        )
        return _handle(
            native,
            "codex_agent_pending_interaction_from_elicitation",
            context,
            pending,
        )
    raise TypeError(f"unsupported pending interaction: {type(interaction).__name__}")


def _create_failure(native: NativeLibrary, context: Handle, failure: object) -> Handle:
    code, code_backing = _view(failure.code)
    message, message_backing = _view(failure.message)
    return _handle(
        native,
        "codex_agent_failure_create",
        context,
        ctypes.byref(code),
        ctypes.byref(message),
        int(failure.is_recoverable),
    )


def _create_interaction_state(
    native: NativeLibrary, context: Handle, state: InteractionState
) -> tuple[Handle, tuple[Handle, ...]]:
    pending = tuple(_create_pending(native, context, value) for value in state.pending)
    resolving = tuple(sorted(state.resolving_request_ids))
    resolving_views, resolving_backings = _views(resolving)
    failure = (
        _create_failure(native, context, state.failure)
        if state.failure is not None
        else Handle()
    )
    return (
        _handle(
            native,
            "codex_agent_interaction_state_create",
            context,
            _handles(pending),
            len(pending),
            resolving_views,
            len(resolving),
            int(state.failure is not None),
            failure,
        ),
        pending,
    )


def interaction_is_resolving(
    state: InteractionState, interaction: PendingInteractionValue
) -> bool:
    with _scope() as (native, context):
        native_state, pending = _create_interaction_state(native, context, state)
        matching = next(
            (
                native_pending
                for candidate, native_pending in zip(state.pending, pending)
                if candidate is interaction
            ),
            None,
        )
        native_interaction = matching or _create_pending(native, context, interaction)
        native_result = bool(
            _i32(
                native,
                "codex_agent_interaction_state_is_resolving",
                context,
                native_state,
                native_interaction,
            )
        )
        if matching is None:
            return native_result
        request_id, request_backing = _view(interaction.request_id)
        return native_result or bool(
            _i32(
                native,
                "codex_agent_interaction_state_resolving_request_ids_contains",
                context,
                native_state,
                ctypes.byref(request_id),
            )
        )


def _pending_signature(
    native: NativeLibrary, context: Handle, interaction: Handle
) -> tuple[str, str]:
    request_id = native.copy_string(
        "codex_agent_pending_interaction_request_id_copy", context, interaction
    )
    conversation = _handle(
        native,
        "codex_agent_pending_interaction_conversation_id",
        context,
        interaction,
    )
    return (
        request_id,
        native.copy_string(
            "codex_agent_conversation_id_value_copy", context, conversation
        ),
    )


def interaction_pending_for(
    state: InteractionState, conversation_id: ConversationId
) -> tuple[PendingInteractionValue, ...]:
    with _scope() as (native, context):
        native_state, pending = _create_interaction_state(native, context, state)
        native_conversation = _create_conversation_id(native, context, conversation_id)
        result = _handle(
            native,
            "codex_agent_interaction_state_pending_for",
            context,
            native_state,
            native_conversation,
        )
        originals: dict[tuple[str, str], list[PendingInteractionValue]] = {}
        for interaction in state.pending:
            originals.setdefault(
                (interaction.request_id, interaction.conversation_id.value), []
            ).append(interaction)
        occurrences: dict[tuple[str, str], int] = {}
        selected: list[PendingInteractionValue] = []
        count = _size(
            native, "codex_agent_pending_interaction_list_count", context, result
        )
        for index in range(count):
            native_pending = _handle(
                native,
                "codex_agent_pending_interaction_list_at",
                context,
                result,
                index,
            )
            signature = _pending_signature(native, context, native_pending)
            occurrence = occurrences.get(signature, 0)
            candidates = originals.get(signature, ())
            if occurrence >= len(candidates):
                raise RuntimeError(
                    "native pendingFor result does not match Python ownership graph"
                )
            selected.append(candidates[occurrence])
            occurrences[signature] = occurrence + 1
        return tuple(selected)
