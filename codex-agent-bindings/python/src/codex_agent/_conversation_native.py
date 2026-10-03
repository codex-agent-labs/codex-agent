from __future__ import annotations

import ctypes

from ._enums import (
    Capability,
    CollaborationMode,
    HookRunStatus,
    MessageRole,
    PlanStepStatus,
    WorkActivity,
)
from ._errors import NativeStatusError, Status
from ._ffi import Handle, NativeLibrary, null_view, utf8_view
from ._models import ConversationId, ConversationSummary
from ._residual_values import (
    ConversationValue,
    Message,
    PluginInvocation,
    SkillInvocation,
    TurnRequest,
)
from ._values import HookActivity, PlanProgress, PlanStep, TurnProgress


def _optional_string(
    native: NativeLibrary, context: Handle, value: Handle, name: str
) -> str | None:
    present = ctypes.c_int32()
    native.call(
        f"codex_agent_{name.rsplit('_', 1)[0]}_has_{name.rsplit('_', 1)[1]}",
        context,
        value,
        ctypes.byref(present),
    )
    return (
        native.copy_string(f"codex_agent_{name}_copy", context, value)
        if present.value
        else None
    )


def _create_invocation(
    native: NativeLibrary,
    context: Handle,
    value: PluginInvocation | SkillInvocation,
) -> Handle:
    name, name_backing = utf8_view(value.name)
    second_text = value.uri if isinstance(value, PluginInvocation) else value.path
    second, second_backing = utf8_view(second_text)
    kind = "plugin" if isinstance(value, PluginInvocation) else "skill"
    typed = Handle()
    invocation = Handle()
    try:
        native.call(
            f"codex_agent_invocation_{kind}_create",
            context,
            ctypes.byref(name),
            ctypes.byref(second),
            ctypes.byref(typed),
        )
        native.call(
            f"codex_agent_invocation_from_{kind}",
            context,
            typed,
            ctypes.byref(invocation),
        )
        return invocation
    finally:
        if typed.value:
            native.call(
                f"codex_agent_invocation_{kind}_destroy",
                context,
                ctypes.byref(typed),
            )
        del name_backing, second_backing


def create_turn_request(
    native: NativeLibrary, context: Handle, value: TurnRequest
) -> Handle:
    prompt, prompt_backing = utf8_view(value.prompt)
    optional = []
    for text in (
        value.client_message_id,
        value.model,
        value.effort,
        value.service_tier,
    ):
        optional.append(utf8_view(text) if text is not None else (null_view(), None))
    invocations: list[Handle] = []
    result = Handle()
    try:
        for item in value.invocations:
            invocations.append(_create_invocation(native, context, item))
        raw_invocations = (
            (Handle * len(invocations))(*invocations) if invocations else None
        )
        capabilities = sorted(value.capabilities, key=int)
        raw_capabilities = (
            (ctypes.c_int32 * len(capabilities))(*(int(item) for item in capabilities))
            if capabilities
            else None
        )
        native.call(
            "codex_agent_turn_request_create",
            context,
            ctypes.byref(prompt),
            int(value.client_message_id is not None),
            ctypes.byref(optional[0][0]),
            int(value.model is not None),
            ctypes.byref(optional[1][0]),
            int(value.effort is not None),
            ctypes.byref(optional[2][0]),
            int(value.service_tier is not None),
            ctypes.byref(optional[3][0]),
            int(value.approval_preset),
            raw_capabilities,
            len(capabilities),
            raw_invocations,
            len(invocations),
            int(value.collaboration_mode),
            ctypes.byref(result),
        )
        return result
    finally:
        for invocation in invocations:
            native.call(
                "codex_agent_invocation_destroy", context, ctypes.byref(invocation)
            )
        del prompt_backing, optional


def _read_invocation(
    native: NativeLibrary, context: Handle, invocation: Handle
) -> PluginInvocation | SkillInvocation:
    kind = ctypes.c_int32()
    try:
        native.call(
            "codex_agent_invocation_kind", context, invocation, ctypes.byref(kind)
        )
        child = Handle()
        if kind.value == 0:
            native.call(
                "codex_agent_invocation_plugin",
                context,
                invocation,
                ctypes.byref(child),
            )
            try:
                return PluginInvocation(
                    native.copy_string(
                        "codex_agent_invocation_plugin_name_copy", context, child
                    )
                    or "",
                    native.copy_string(
                        "codex_agent_invocation_plugin_uri_copy", context, child
                    )
                    or "",
                )
            finally:
                native.call(
                    "codex_agent_invocation_plugin_destroy",
                    context,
                    ctypes.byref(child),
                )
        if kind.value == 1:
            native.call(
                "codex_agent_invocation_skill",
                context,
                invocation,
                ctypes.byref(child),
            )
            try:
                return SkillInvocation(
                    native.copy_string(
                        "codex_agent_invocation_skill_name_copy", context, child
                    )
                    or "",
                    native.copy_string(
                        "codex_agent_invocation_skill_path_copy", context, child
                    )
                    or "",
                )
            finally:
                native.call(
                    "codex_agent_invocation_skill_destroy",
                    context,
                    ctypes.byref(child),
                )
        raise NativeStatusError(
            Status.INTERNAL_ERROR, f"codex_agent_invocation_kind ({kind.value})"
        )
    finally:
        native.call("codex_agent_invocation_destroy", context, ctypes.byref(invocation))


def read_message(native: NativeLibrary, context: Handle, message: Handle) -> Message:
    try:
        role = ctypes.c_int32()
        mode = ctypes.c_int32()
        native.call("codex_agent_message_role", context, message, ctypes.byref(role))
        native.call(
            "codex_agent_message_collaboration_mode",
            context,
            message,
            ctypes.byref(mode),
        )
        has_exit = ctypes.c_int32()
        exit_code = ctypes.c_int32()
        native.call(
            "codex_agent_message_exit_code",
            context,
            message,
            ctypes.byref(has_exit),
            ctypes.byref(exit_code),
        )
        capability_count = ctypes.c_size_t()
        native.call(
            "codex_agent_message_capabilities_count",
            context,
            message,
            ctypes.byref(capability_count),
        )
        capabilities: set[Capability] = set()
        for capability in Capability:
            present = ctypes.c_int32()
            native.call(
                "codex_agent_message_has_capability",
                context,
                message,
                int(capability),
                ctypes.byref(present),
            )
            if present.value:
                capabilities.add(capability)
        if len(capabilities) != capability_count.value:
            raise NativeStatusError(
                Status.INTERNAL_ERROR, "codex_agent_message_capabilities_count"
            )
        invocation_count = ctypes.c_size_t()
        native.call(
            "codex_agent_message_invocations_count",
            context,
            message,
            ctypes.byref(invocation_count),
        )
        invocations = []
        for index in range(invocation_count.value):
            invocation = Handle()
            native.call(
                "codex_agent_message_invocation_at",
                context,
                message,
                index,
                ctypes.byref(invocation),
            )
            invocations.append(_read_invocation(native, context, invocation))
        return Message(
            id=native.copy_string("codex_agent_message_id_copy", context, message)
            or "",
            role=MessageRole(role.value),
            text=native.copy_string("codex_agent_message_text_copy", context, message)
            or "",
            reasoning=_optional_string(native, context, message, "message_reasoning"),
            plan=_optional_string(native, context, message, "message_plan"),
            shell_command=_optional_string(
                native, context, message, "message_shell_command"
            ),
            exit_code=exit_code.value if has_exit.value else None,
            invocations=invocations,
            capabilities=capabilities,
            collaboration_mode=CollaborationMode(mode.value),
            client_message_id=_optional_string(
                native, context, message, "message_client_message_id"
            ),
        )
    finally:
        native.call("codex_agent_message_destroy", context, ctypes.byref(message))


def read_conversation_summary(
    native: NativeLibrary, context: Handle, summary: Handle
) -> ConversationSummary:
    try:
        conversation_id = Handle()
        native.call(
            "codex_agent_conversation_summary_conversation_id",
            context,
            summary,
            ctypes.byref(conversation_id),
        )
        try:
            identifier = native.copy_string(
                "codex_agent_conversation_id_value_copy", context, conversation_id
            )
        finally:
            native.call(
                "codex_agent_conversation_id_destroy",
                context,
                ctypes.byref(conversation_id),
            )
        updated = ctypes.c_int64()
        native.call(
            "codex_agent_conversation_summary_updated_at_epoch_seconds",
            context,
            summary,
            ctypes.byref(updated),
        )
        return ConversationSummary(
            ConversationId(identifier or ""),
            native.copy_string(
                "codex_agent_conversation_summary_title_copy", context, summary
            )
            or "",
            updated.value,
        )
    finally:
        native.call(
            "codex_agent_conversation_summary_destroy",
            context,
            ctypes.byref(summary),
        )


def read_conversation_value(
    native: NativeLibrary, context: Handle, conversation: Handle
) -> ConversationValue:
    try:
        summary = Handle()
        native.call(
            "codex_agent_conversation_value_summary",
            context,
            conversation,
            ctypes.byref(summary),
        )
        decoded_summary = read_conversation_summary(native, context, summary)
        message_count = ctypes.c_size_t()
        native.call(
            "codex_agent_conversation_value_messages_count",
            context,
            conversation,
            ctypes.byref(message_count),
        )
        messages = []
        for index in range(message_count.value):
            message = Handle()
            native.call(
                "codex_agent_conversation_value_message_at",
                context,
                conversation,
                index,
                ctypes.byref(message),
            )
            messages.append(read_message(native, context, message))
        return ConversationValue(decoded_summary, messages)
    finally:
        native.call(
            "codex_agent_conversation_value_destroy",
            context,
            ctypes.byref(conversation),
        )


def _read_plan_progress(
    native: NativeLibrary, context: Handle, progress: Handle
) -> PlanProgress:
    try:
        explanation = _optional_string(
            native, context, progress, "plan_progress_explanation"
        )
        count = ctypes.c_size_t()
        native.call(
            "codex_agent_plan_progress_steps_count",
            context,
            progress,
            ctypes.byref(count),
        )
        steps = []
        for index in range(count.value):
            step = Handle()
            native.call(
                "codex_agent_plan_progress_step_at",
                context,
                progress,
                index,
                ctypes.byref(step),
            )
            try:
                status = ctypes.c_int32()
                native.call(
                    "codex_agent_plan_step_status",
                    context,
                    step,
                    ctypes.byref(status),
                )
                steps.append(
                    PlanStep(
                        native.copy_string(
                            "codex_agent_plan_step_text_copy", context, step
                        )
                        or "",
                        PlanStepStatus(status.value),
                    )
                )
            finally:
                native.call(
                    "codex_agent_plan_step_destroy", context, ctypes.byref(step)
                )
        return PlanProgress(explanation, steps)
    finally:
        native.call(
            "codex_agent_plan_progress_destroy", context, ctypes.byref(progress)
        )


def _read_hook_activity(
    native: NativeLibrary, context: Handle, activity: Handle
) -> HookActivity:
    try:
        status = ctypes.c_int32()
        native.call(
            "codex_agent_hook_activity_status",
            context,
            activity,
            ctypes.byref(status),
        )
        count = ctypes.c_size_t()
        native.call(
            "codex_agent_hook_activity_details_count",
            context,
            activity,
            ctypes.byref(count),
        )
        details = [
            native.copy_string(
                "codex_agent_hook_activity_detail_copy_at", context, activity, index
            )
            or ""
            for index in range(count.value)
        ]
        return HookActivity(
            id=native.copy_string(
                "codex_agent_hook_activity_id_copy", context, activity
            )
            or "",
            event_name=native.copy_string(
                "codex_agent_hook_activity_event_name_copy", context, activity
            )
            or "",
            handler_type=native.copy_string(
                "codex_agent_hook_activity_handler_type_copy", context, activity
            )
            or "",
            status=HookRunStatus(status.value),
            status_message=_optional_string(
                native, context, activity, "hook_activity_status_message"
            ),
            details=details,
        )
    finally:
        native.call(
            "codex_agent_hook_activity_destroy", context, ctypes.byref(activity)
        )


def read_turn_progress(
    native: NativeLibrary, context: Handle, progress: Handle
) -> TurnProgress:
    try:
        has_plan = ctypes.c_int32()
        native.call(
            "codex_agent_turn_progress_has_plan_progress",
            context,
            progress,
            ctypes.byref(has_plan),
        )
        plan_progress = None
        if has_plan.value:
            plan = Handle()
            native.call(
                "codex_agent_turn_progress_plan_progress",
                context,
                progress,
                ctypes.byref(plan),
            )
            plan_progress = _read_plan_progress(native, context, plan)
        has_exit = ctypes.c_int32()
        exit_code = ctypes.c_int32()
        native.call(
            "codex_agent_turn_progress_shell_exit_code",
            context,
            progress,
            ctypes.byref(has_exit),
            ctypes.byref(exit_code),
        )
        has_activity = ctypes.c_int32()
        activity = ctypes.c_int32()
        native.call(
            "codex_agent_turn_progress_work_activity",
            context,
            progress,
            ctypes.byref(has_activity),
            ctypes.byref(activity),
        )
        hook_count = ctypes.c_size_t()
        native.call(
            "codex_agent_turn_progress_hook_activities_count",
            context,
            progress,
            ctypes.byref(hook_count),
        )
        hooks = []
        for index in range(hook_count.value):
            hook = Handle()
            native.call(
                "codex_agent_turn_progress_hook_activity_at",
                context,
                progress,
                index,
                ctypes.byref(hook),
            )
            hooks.append(_read_hook_activity(native, context, hook))
        truncated = ctypes.c_int32()
        native.call(
            "codex_agent_turn_progress_is_truncated",
            context,
            progress,
            ctypes.byref(truncated),
        )
        return TurnProgress(
            text=native.copy_string(
                "codex_agent_turn_progress_text_copy", context, progress
            )
            or "",
            commentary=native.copy_string(
                "codex_agent_turn_progress_commentary_copy", context, progress
            )
            or "",
            reasoning=native.copy_string(
                "codex_agent_turn_progress_reasoning_copy", context, progress
            )
            or "",
            plan=native.copy_string(
                "codex_agent_turn_progress_plan_copy", context, progress
            )
            or "",
            plan_progress=plan_progress,
            shell_output=native.copy_string(
                "codex_agent_turn_progress_shell_output_copy", context, progress
            )
            or "",
            shell_exit_code=exit_code.value if has_exit.value else None,
            work_activity=WorkActivity(activity.value) if has_activity.value else None,
            hook_activities=hooks,
            is_truncated=bool(truncated.value),
        )
    finally:
        native.call(
            "codex_agent_turn_progress_destroy", context, ctypes.byref(progress)
        )
