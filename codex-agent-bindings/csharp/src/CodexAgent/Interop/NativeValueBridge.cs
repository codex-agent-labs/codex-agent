using System.Runtime.InteropServices;

namespace CodexAgent.Interop;

internal static unsafe class NativeValueBridge
{
    internal static CodexAuthorizationUrl AuthorizationUrl(string value, bool chatGpt) => Invoke(scope =>
    {
        using var strings = new Utf8Arena();
        var input = strings.View(value);
        var status = chatGpt
            ? NativeMethods.AuthorizationUrlChatGpt(scope.Context, &input, out var url)
            : NativeMethods.AuthorizationUrlExternal(scope.Context, &input, out url);
        Throw(status, "create authorization URL");
        scope.Own(url, NativeMethods.AuthorizationUrlDestroy, "authorization URL");
        var copied = NativeApi.CopyString((byte* buffer, nuint capacity, out nuint required) =>
            NativeMethods.AuthorizationUrlValueCopy(scope.Context, url, buffer, capacity, out required));
        Throw(NativeMethods.AuthorizationUrlPurpose(scope.Context, url, out var purpose), "read authorization URL purpose");
        return CodexAuthorizationUrl.FromNative(copied, purpose);
    });

    internal static bool FormFieldAccepts(CodexFormField field, CodexFormValue? value) => Invoke(scope =>
    {
        var nativeField = CreateFormField(scope, field);
        var nativeValue = value is null ? 0 : CreateFormValue(scope, value);
        Throw(NativeMethods.FormFieldAccepts(scope.Context, nativeField, nativeValue, out var accepts),
            "validate form field");
        return accepts != 0;
    });

    internal static IReadOnlyDictionary<string, CodexFormValue> ElicitationInitialValues(CodexElicitation value) =>
        Invoke(scope =>
        {
            var elicitation = CreateElicitation(scope, value);
            Throw(NativeMethods.ElicitationInitialValues(scope.Context, elicitation, out var content),
                "read elicitation initial values");
            scope.Own(content, NativeMethods.FormContentDestroy, "form content");
            return ReadContent(scope, content);
        });

    internal static CodexElicitationValidation ElicitationValidate(
        CodexElicitation value,
        IReadOnlyDictionary<string, CodexFormValue> content)
    {
        ArgumentNullException.ThrowIfNull(content);
        return Invoke(scope =>
        {
            var elicitation = CreateElicitation(scope, value);
            var nativeContent = CreateContent(scope, content);
            Throw(NativeMethods.ElicitationValidate(scope.Context, elicitation, nativeContent, out var validation),
                "validate elicitation content");
            scope.Own(validation, NativeMethods.ElicitationValidationDestroy, "elicitation validation");
            return ReadValidation(scope, validation);
        });
    }

    internal static CodexElicitationResponse ElicitationAccept(
        CodexElicitation value,
        IReadOnlyDictionary<string, CodexFormValue> content)
    {
        ArgumentNullException.ThrowIfNull(content);
        return Invoke(scope =>
        {
            var entries = content.ToArray();
            var elicitation = CreateElicitation(scope, value);
            var nativeContent = CreateContent(scope, entries);
            Throw(NativeMethods.ElicitationAccept(scope.Context, elicitation, nativeContent, out var response),
                "accept elicitation content");
            scope.Own(response, NativeMethods.ElicitationResponseDestroy, "elicitation response");
            return ReadResponse(scope, response, entries.Select(static entry => entry.Key).ToArray());
        });
    }

    internal static bool ElicitationAccepts(CodexElicitation value, CodexElicitationResponse response)
    {
        ArgumentNullException.ThrowIfNull(response);
        return Invoke(scope =>
        {
            var elicitation = CreateElicitation(scope, value);
            var nativeResponse = CreateResponse(scope, response);
            Throw(NativeMethods.ElicitationAccepts(scope.Context, elicitation, nativeResponse, out var accepts),
                "check elicitation response");
            return accepts != 0;
        });
    }

    internal static CodexElicitationResponse ElicitationResponse(bool cancel) => Invoke(scope =>
    {
        var status = cancel
            ? NativeMethods.ElicitationResponseCancel(scope.Context, out var response)
            : NativeMethods.ElicitationResponseDecline(scope.Context, out response);
        Throw(status, cancel ? "cancel elicitation" : "decline elicitation");
        scope.Own(response, NativeMethods.ElicitationResponseDestroy, "elicitation response");
        return ReadResponse(scope, response, []);
    });

    internal static bool InteractionStateIsResolving(
        CodexInteractionState state,
        CodexPendingInteraction interaction)
    {
        ArgumentNullException.ThrowIfNull(interaction);
        return Invoke(scope =>
        {
            var native = CreateState(scope, state);
            var index = state.Pending.ToList().FindIndex(candidate => ReferenceEquals(candidate, interaction));
            var selected = index >= 0 ? native.Pending[index] : CreatePendingInteraction(scope, interaction);
            Throw(NativeMethods.InteractionStateIsResolving(scope.Context, native.State, selected, out var resolving),
                "check resolving interaction");
            if (resolving != 0 || index < 0) return resolving != 0;

            // Root-created C snapshots deliberately copy pending values, so C identity cannot
            // survive the language boundary. Preserve managed identity while asking C for the
            // canonical resolving-set membership.
            using var strings = new Utf8Arena();
            var requestId = strings.View(interaction.RequestId);
            Throw(NativeMethods.InteractionStateResolvingRequestIdsContains(
                scope.Context, native.State, &requestId, out var contains), "read resolving interaction membership");
            return contains != 0;
        });
    }

    internal static IReadOnlyList<CodexPendingInteraction> InteractionStatePendingFor(
        CodexInteractionState state,
        CodexConversationId conversationId)
    {
        ArgumentNullException.ThrowIfNull(conversationId);
        return Invoke(scope =>
        {
            var native = CreateState(scope, state);
            var id = CreateConversationId(scope, conversationId);
            Throw(NativeMethods.InteractionStatePendingFor(scope.Context, native.State, id, out var list),
                "select pending interactions");
            scope.Own(list, NativeMethods.PendingInteractionListDestroy, "pending interaction list");
            Throw(NativeMethods.PendingInteractionListCount(scope.Context, list, out var nativeCount),
                "read pending interaction count");
            var count = CheckedCount(nativeCount);
            var result = new CodexPendingInteraction[count];
            var cursor = 0;
            for (var index = 0; index < count; index += 1)
            {
                nint pending = 0;
                Throw(NativeMethods.PendingInteractionListAt(scope.Context, list, (nuint)index, ref pending),
                    "read pending interaction");
                scope.Own(pending, NativeMethods.PendingInteractionDestroy, "pending interaction");
                var key = ReadPendingKey(scope, pending);
                while (cursor < state.Pending.Count && ManagedPendingKey(state.Pending[cursor]) != key) cursor += 1;
                if (cursor == state.Pending.Count)
                    throw new CodexException(CodexStatus.InternalError,
                        "Native pending-interaction order cannot be mapped to the immutable managed snapshot.");
                result[index] = state.Pending[cursor++];
            }
            return CodexValueCopies.List(result);
        });
    }

    private static T Invoke<T>(Func<NativeScope, T> action)
    {
        using var scope = new NativeScope();
        return action(scope);
    }

    private static nint CreateConversationId(NativeScope scope, CodexConversationId value)
    {
        using var strings = new Utf8Arena();
        var input = strings.View(value.Value);
        Throw(NativeMethods.ConversationIdCreate(scope.Context, &input, out var result), "create conversation ID");
        return scope.Own(result, NativeMethods.ConversationIdDestroy, "conversation ID");
    }

    private static nint CreateFormValue(NativeScope scope, CodexFormValue value)
    {
        nint concrete;
        CodexStatus status;
        NativeDestroy destroy;
        switch (value)
        {
            case CodexFormValue.BooleanValue boolean:
                status = NativeMethods.FormBooleanCreate(scope.Context, boolean.Value ? 1 : 0, out concrete);
                destroy = NativeMethods.FormBooleanDestroy;
                break;
            case CodexFormValue.Number number:
                status = NativeMethods.FormNumberCreate(scope.Context, number.Value, out concrete);
                destroy = NativeMethods.FormNumberDestroy;
                break;
            case CodexFormValue.Text text:
                using (var strings = new Utf8Arena())
                {
                    var input = strings.View(text.Value);
                    status = NativeMethods.FormTextCreate(scope.Context, &input, out concrete);
                }
                destroy = NativeMethods.FormTextDestroy;
                break;
            case CodexFormValue.TextList textList:
                using (var strings = new Utf8Arena())
                {
                    var views = textList.Value.Select(strings.View).ToArray();
                    fixed (NativeStringView* inputs = views)
                        status = NativeMethods.FormTextListCreate(scope.Context, inputs, (nuint)views.Length, out concrete);
                }
                destroy = NativeMethods.FormTextListDestroy;
                break;
            default:
                throw new ArgumentOutOfRangeException(nameof(value));
        }

        Throw(status, "create form value");
        scope.Own(concrete, destroy, "concrete form value");
        nint wrapped = 0;
        CodexStatus wrappedStatus = value switch
        {
            CodexFormValue.BooleanValue => NativeMethods.FormValueFromBoolean(scope.Context, concrete, out wrapped),
            CodexFormValue.Number => NativeMethods.FormValueFromNumber(scope.Context, concrete, out wrapped),
            CodexFormValue.Text => NativeMethods.FormValueFromText(scope.Context, concrete, out wrapped),
            CodexFormValue.TextList => NativeMethods.FormValueFromTextList(scope.Context, concrete, out wrapped),
            _ => CodexStatus.InvalidArgument,
        };
        Throw(wrappedStatus, "wrap form value");
        return scope.Own(wrapped, NativeMethods.FormValueDestroy, "form value");
    }

    private static nint CreateFormOption(NativeScope scope, CodexFormOption value)
    {
        using var strings = new Utf8Arena();
        var rawValue = strings.View(value.Value);
        var title = strings.View(value.Title);
        var description = strings.View(value.Description);
        Throw(NativeMethods.FormOptionCreate(
            scope.Context, &rawValue, 1, &title, value.Description is null ? 0 : 1, &description, out var option),
            "create form option");
        return scope.Own(option, NativeMethods.FormOptionDestroy, "form option");
    }

    private static nint CreateFormField(NativeScope scope, CodexFormField value)
    {
        using var strings = new Utf8Arena();
        var name = strings.View(value.Name);
        var title = strings.View(value.Title);
        var description = strings.View(value.Description);
        var options = value.Options.Select(option => CreateFormOption(scope, option)).ToArray();
        var defaultValue = value.DefaultValue is null ? 0 : CreateFormValue(scope, value.DefaultValue);
        fixed (nint* optionPointer = options)
        {
            Throw(NativeMethods.FormFieldCreate(
                scope.Context, &name, &title,
                value.Description is null ? 0 : 1, &description, value.IsRequired ? 1 : 0, value.Type,
                optionPointer, (nuint)options.Length, value.DefaultValue is null ? 0 : 1, defaultValue,
                value.Minimum is null ? 0 : 1, value.Minimum ?? 0,
                value.Maximum is null ? 0 : 1, value.Maximum ?? 0,
                value.Format is null ? 0 : 1, value.Format ?? 0,
                value.MinimumLength is null ? 0 : 1, value.MinimumLength ?? 0,
                value.MaximumLength is null ? 0 : 1, value.MaximumLength ?? 0,
                value.MinimumSelections is null ? 0 : 1, value.MinimumSelections ?? 0,
                value.MaximumSelections is null ? 0 : 1, value.MaximumSelections ?? 0,
                value.AllowsOther ? 1 : 0, value.IsSecret ? 1 : 0, out var field),
                "create form field");
            return scope.Own(field, NativeMethods.FormFieldDestroy, "form field");
        }
    }

    private static nint CreateElicitation(NativeScope scope, CodexElicitation value)
    {
        using var strings = new Utf8Arena();
        var requestId = strings.View(value.RequestId);
        var serverName = strings.View(value.ServerName);
        var message = strings.View(value.Message);
        var url = strings.View(value.Url);
        var conversationId = CreateConversationId(scope, value.ConversationId);
        var form = value.Form?.Select(field => CreateFormField(scope, field)).ToArray() ?? [];
        fixed (nint* formPointer = form)
        {
            Throw(NativeMethods.ElicitationCreate(
                scope.Context, &requestId, &serverName, conversationId, &message,
                value.Form is null ? 0 : 1, formPointer, (nuint)form.Length,
                value.Url is null ? 0 : 1, &url, out var elicitation), "create elicitation");
            return scope.Own(elicitation, NativeMethods.ElicitationDestroy, "elicitation");
        }
    }

    private static nint CreateContent(
        NativeScope scope,
        IReadOnlyDictionary<string, CodexFormValue> content) => CreateContent(scope, content.ToArray());

    private static nint CreateContent(
        NativeScope scope,
        IReadOnlyList<KeyValuePair<string, CodexFormValue>> entries)
    {
        using var strings = new Utf8Arena();
        var keys = entries.Select(entry => strings.View(entry.Key)).ToArray();
        var values = entries.Select(entry => CreateFormValue(scope,
            entry.Value ?? throw new ArgumentException("Form content values must not be null.", nameof(entries)))).ToArray();
        fixed (NativeStringView* keyPointer = keys)
        fixed (nint* valuePointer = values)
        {
            Throw(NativeMethods.FormContentCreate(
                scope.Context, keyPointer, valuePointer, (nuint)entries.Count, out var content),
                "create form content");
            return scope.Own(content, NativeMethods.FormContentDestroy, "form content");
        }
    }

    private static nint CreateResponse(NativeScope scope, CodexElicitationResponse value)
    {
        var entries = value.Content.ToArray();
        using var strings = new Utf8Arena();
        var keys = entries.Select(entry => strings.View(entry.Key)).ToArray();
        var values = entries.Select(entry => CreateFormValue(scope, entry.Value)).ToArray();
        fixed (NativeStringView* keyPointer = keys)
        fixed (nint* valuePointer = values)
        {
            Throw(NativeMethods.ElicitationResponseCreate(
                scope.Context, value.Action, keyPointer, valuePointer, (nuint)entries.Length, out var response),
                "create elicitation response");
            return scope.Own(response, NativeMethods.ElicitationResponseDestroy, "elicitation response");
        }
    }

    private static nint CreatePendingInteraction(NativeScope scope, CodexPendingInteraction value)
    {
        nint interaction;
        switch (value)
        {
            case CodexPendingApproval approval:
            {
                using var strings = new Utf8Arena();
                var requestId = strings.View(approval.RequestId);
                var title = strings.View(approval.Title);
                var details = strings.View(approval.Details);
                var conversationId = CreateConversationId(scope, approval.ConversationId);
                Throw(NativeMethods.PendingApprovalCreate(
                    scope.Context, &requestId, conversationId, &title, &details, out var nativeApproval),
                    "create pending approval");
                scope.Own(nativeApproval, NativeMethods.PendingApprovalDestroy, "pending approval");
                Throw(NativeMethods.PendingInteractionFromApproval(scope.Context, nativeApproval, out interaction),
                    "create pending interaction");
                break;
            }
            case CodexPendingElicitation elicitation:
            {
                var nativeElicitation = CreateElicitation(scope, elicitation.Elicitation);
                Throw(NativeMethods.PendingElicitationCreate(
                    scope.Context, nativeElicitation, out var nativePending), "create pending elicitation");
                scope.Own(nativePending, NativeMethods.PendingElicitationDestroy, "pending elicitation");
                Throw(NativeMethods.PendingInteractionFromElicitation(scope.Context, nativePending, out interaction),
                    "create pending interaction");
                break;
            }
            default:
                throw new ArgumentOutOfRangeException(nameof(value));
        }
        return scope.Own(interaction, NativeMethods.PendingInteractionDestroy, "pending interaction");
    }

    private static NativeState CreateState(NativeScope scope, CodexInteractionState value)
    {
        var pending = value.Pending.Select(item => CreatePendingInteraction(scope, item)).ToArray();
        using var strings = new Utf8Arena();
        var resolving = value.ResolvingRequestIds.Select(strings.View).ToArray();
        var failure = value.Failure is null ? 0 : CreateFailure(scope, value.Failure);
        fixed (nint* pendingPointer = pending)
        fixed (NativeStringView* resolvingPointer = resolving)
        {
            Throw(NativeMethods.InteractionStateCreate(
                scope.Context, pendingPointer, (nuint)pending.Length,
                resolvingPointer, (nuint)resolving.Length,
                value.Failure is null ? 0 : 1, failure, out var state), "create interaction state");
            scope.Own(state, NativeMethods.InteractionStateDestroy, "interaction state");
            return new NativeState(state, pending);
        }
    }

    private static nint CreateFailure(NativeScope scope, CodexFailure value)
    {
        using var strings = new Utf8Arena();
        var code = strings.View(value.Code);
        var message = strings.View(value.Message);
        Throw(NativeMethods.FailureCreate(
            scope.Context, &code, &message, value.IsRecoverable ? 1 : 0, out var failure), "create failure");
        return scope.Own(failure, NativeMethods.FailureRelease, "failure");
    }

    private static IReadOnlyDictionary<string, CodexFormValue> ReadContent(NativeScope scope, nint content)
    {
        Throw(NativeMethods.FormContentCount(scope.Context, content, out var nativeCount), "read form content count");
        var result = new Dictionary<string, CodexFormValue>(CheckedCount(nativeCount), StringComparer.Ordinal);
        for (var index = 0; index < (int)nativeCount; index += 1)
        {
            var key = NativeApi.CopyString((byte* buffer, nuint capacity, out nuint required) =>
                NativeMethods.FormContentKeyCopy(scope.Context, content, (nuint)index, buffer, capacity, out required));
            using var strings = new Utf8Arena();
            var keyView = strings.View(key);
            nint value = 0;
            Throw(NativeMethods.FormContentValueAt(scope.Context, content, &keyView, ref value),
                "read form content value");
            scope.Own(value, NativeMethods.FormValueDestroy, "form value");
            if (!result.TryAdd(key, ReadFormValue(scope, value)))
                throw new CodexException(CodexStatus.InternalError, $"Native form content contains duplicate key '{key}'.");
        }
        return CodexValueCopies.Map(result);
    }

    private static CodexElicitationValidation ReadValidation(NativeScope scope, nint validation)
    {
        Throw(NativeMethods.ElicitationValidationIssueCount(scope.Context, validation, out var nativeCount),
            "read elicitation validation issue count");
        var issues = new CodexElicitationValidationIssue[CheckedCount(nativeCount)];
        for (var index = 0; index < issues.Length; index += 1)
        {
            nint issue = 0;
            Throw(NativeMethods.ElicitationValidationIssueAt(
                scope.Context, validation, (nuint)index, ref issue), "read elicitation validation issue");
            scope.Own(issue, NativeMethods.ElicitationValidationIssueDestroy, "elicitation validation issue");
            var fieldName = NativeApi.CopyString((byte* buffer, nuint capacity, out nuint required) =>
                NativeMethods.ElicitationValidationIssueFieldNameCopy(
                    scope.Context, issue, buffer, capacity, out required));
            Throw(NativeMethods.ElicitationValidationIssueReason(scope.Context, issue, out var reason),
                "read elicitation validation reason");
            issues[index] = new CodexElicitationValidationIssue(fieldName, reason);
        }
        return new CodexElicitationValidation(issues);
    }

    private static CodexElicitationResponse ReadResponse(
        NativeScope scope,
        nint response,
        IReadOnlyList<string> keys)
    {
        Throw(NativeMethods.ElicitationResponseAction(scope.Context, response, out var action),
            "read elicitation response action");
        Throw(NativeMethods.ElicitationResponseContentCount(scope.Context, response, out var nativeCount),
            "read elicitation response content count");
        if (nativeCount != (nuint)keys.Count)
            throw new CodexException(CodexStatus.InternalError, "Native elicitation response content count changed.");
        var content = new Dictionary<string, CodexFormValue>(keys.Count, StringComparer.Ordinal);
        foreach (var key in keys)
        {
            using var strings = new Utf8Arena();
            var keyView = strings.View(key);
            nint value = 0;
            Throw(NativeMethods.ElicitationResponseContentValue(
                scope.Context, response, &keyView, ref value), "read elicitation response content");
            scope.Own(value, NativeMethods.FormValueDestroy, "form value");
            content.Add(key, ReadFormValue(scope, value));
        }
        return new CodexElicitationResponse(action, content);
    }

    private static CodexFormValue ReadFormValue(NativeScope scope, nint value)
    {
        Throw(NativeMethods.FormValueKind(scope.Context, value, out var kind), "read form value kind");
        switch (kind)
        {
            case 0:
                nint boolean = 0;
                Throw(NativeMethods.FormValueBoolean(scope.Context, value, ref boolean), "read Boolean form value");
                scope.Own(boolean, NativeMethods.FormBooleanDestroy, "Boolean form value");
                Throw(NativeMethods.FormBooleanValue(scope.Context, boolean, out var booleanValue), "read Boolean form value");
                return new CodexFormValue.BooleanValue(booleanValue != 0);
            case 1:
                nint number = 0;
                Throw(NativeMethods.FormValueNumber(scope.Context, value, ref number), "read number form value");
                scope.Own(number, NativeMethods.FormNumberDestroy, "number form value");
                Throw(NativeMethods.FormNumberValue(scope.Context, number, out var numberValue), "read number form value");
                return new CodexFormValue.Number(numberValue);
            case 2:
                nint text = 0;
                Throw(NativeMethods.FormValueText(scope.Context, value, ref text), "read text form value");
                scope.Own(text, NativeMethods.FormTextDestroy, "text form value");
                return new CodexFormValue.Text(NativeApi.CopyString(
                    (byte* buffer, nuint capacity, out nuint required) =>
                        NativeMethods.FormTextValueCopy(scope.Context, text, buffer, capacity, out required)));
            case 3:
                nint textList = 0;
                Throw(NativeMethods.FormValueTextList(scope.Context, value, ref textList), "read text-list form value");
                scope.Own(textList, NativeMethods.FormTextListDestroy, "text-list form value");
                Throw(NativeMethods.FormTextListCount(scope.Context, textList, out var nativeCount),
                    "read text-list form value count");
                var values = new string[CheckedCount(nativeCount)];
                for (var index = 0; index < values.Length; index += 1)
                    values[index] = NativeApi.CopyString((byte* buffer, nuint capacity, out nuint required) =>
                        NativeMethods.FormTextListCopyAt(
                            scope.Context, textList, (nuint)index, buffer, capacity, out required));
                return new CodexFormValue.TextList(values);
            default:
                throw new CodexException(CodexStatus.InternalError, $"Unknown native form-value kind {kind}.");
        }
    }

    private static PendingKey ReadPendingKey(NativeScope scope, nint interaction)
    {
        Throw(NativeMethods.PendingInteractionKind(scope.Context, interaction, out var kind),
            "read pending interaction kind");
        nint pending;
        NativeApi.StringCopy requestCopy;
        if (kind == 0)
        {
            pending = 0;
            Throw(NativeMethods.PendingInteractionApproval(scope.Context, interaction, ref pending),
                "read pending approval");
            scope.Own(pending, NativeMethods.PendingApprovalDestroy, "pending approval");
            requestCopy = (byte* buffer, nuint capacity, out nuint required) =>
                NativeMethods.PendingApprovalRequestIdCopy(scope.Context, pending, buffer, capacity, out required);
            nint conversationId = 0;
            Throw(NativeMethods.PendingApprovalConversationId(scope.Context, pending, ref conversationId),
                "read pending approval conversation ID");
            scope.Own(conversationId, NativeMethods.ConversationIdDestroy, "conversation ID");
            return new PendingKey(kind, NativeApi.CopyString(requestCopy), ReadConversationId(scope, conversationId));
        }
        if (kind == 1)
        {
            pending = 0;
            Throw(NativeMethods.PendingInteractionElicitation(scope.Context, interaction, ref pending),
                "read pending elicitation");
            scope.Own(pending, NativeMethods.PendingElicitationDestroy, "pending elicitation");
            requestCopy = (byte* buffer, nuint capacity, out nuint required) =>
                NativeMethods.PendingElicitationRequestIdCopy(scope.Context, pending, buffer, capacity, out required);
            nint conversationId = 0;
            Throw(NativeMethods.PendingElicitationConversationId(scope.Context, pending, ref conversationId),
                "read pending elicitation conversation ID");
            scope.Own(conversationId, NativeMethods.ConversationIdDestroy, "conversation ID");
            return new PendingKey(kind, NativeApi.CopyString(requestCopy), ReadConversationId(scope, conversationId));
        }
        throw new CodexException(CodexStatus.InternalError, $"Unknown native pending-interaction kind {kind}.");
    }

    private static string ReadConversationId(NativeScope scope, nint conversationId) =>
        NativeApi.CopyString((byte* buffer, nuint capacity, out nuint required) =>
            NativeMethods.ConversationIdValueCopy(scope.Context, conversationId, buffer, capacity, out required));

    private static PendingKey ManagedPendingKey(CodexPendingInteraction value) => value switch
    {
        CodexPendingApproval => new PendingKey(0, value.RequestId, value.ConversationId.Value),
        CodexPendingElicitation => new PendingKey(1, value.RequestId, value.ConversationId.Value),
        _ => throw new ArgumentOutOfRangeException(nameof(value)),
    };

    private static int CheckedCount(nuint count)
    {
        if (count > int.MaxValue)
            throw new CodexException(CodexStatus.OutOfMemory, "Native collection is too large.");
        return (int)count;
    }

    private static void Throw(CodexStatus status, string action)
    {
        if (status == CodexStatus.InvalidArgument)
            throw new ArgumentException($"Could not {action}: native input validation failed.");
        NativeApi.ThrowIfFailed(status, action);
    }

    private readonly record struct NativeState(nint State, nint[] Pending);
    private readonly record struct PendingKey(int Kind, string RequestId, string ConversationId);

    private delegate CodexStatus NativeDestroy(nint context, ref nint value);

    private sealed class NativeScope : IDisposable
    {
        private readonly List<(nint Handle, NativeDestroy Destroy, string Name)> owned = [];
        private readonly NativeContext context = NativeContext.Create();

        internal nint Context => context.Pointer;

        internal nint Own(nint handle, NativeDestroy destroy, string name)
        {
            if (handle == 0)
                throw new CodexException(CodexStatus.InternalError, $"Native {name} creation returned a null handle.");
            owned.Add((handle, destroy, name));
            return handle;
        }

        public void Dispose()
        {
            for (var index = owned.Count - 1; index >= 0; index -= 1)
            {
                var (handle, destroy, name) = owned[index];
                var status = NativeApi.RetryBusy(() => destroy(Context, ref handle));
                if (status != CodexStatus.Ok) NativeCleanup.Report(name, status, this);
            }
            context.Release();
        }
    }

    private sealed class Utf8Arena : IDisposable
    {
        private readonly List<nint> allocations = [];

        internal NativeStringView View(string? value)
        {
            if (value is null) return default;
            var bytes = NativeApi.Utf8(value);
            if (bytes.Length == 0) return default;
            var pointer = Marshal.AllocHGlobal(bytes.Length);
            Marshal.Copy(bytes, 0, pointer, bytes.Length);
            allocations.Add(pointer);
            return new NativeStringView { Data = (byte*)pointer, Size = (nuint)bytes.Length };
        }

        public void Dispose()
        {
            foreach (var pointer in allocations) Marshal.FreeHGlobal(pointer);
        }
    }
}
