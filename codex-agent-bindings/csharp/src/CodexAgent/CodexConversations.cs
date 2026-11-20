using System.Runtime.CompilerServices;
using CodexAgent.Interop;

namespace CodexAgent;

/// <summary>Conversation catalog and active-conversation state owned by an agent.</summary>
public sealed class CodexConversations
{
    private readonly ConversationsHandle handle;
    private readonly object activeGate = new();
    private CodexConversation? active;

    internal CodexConversations(ConversationsHandle handle) => this.handle = handle;

    /// <summary>Lists conversation summaries in canonical order.</summary>
    public unsafe Task<IReadOnlyList<CodexConversationSummary>> ListAsync(CancellationToken cancellationToken = default) =>
        Run(cancellationToken, (nint owner, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation) =>
            NativeMethods.ConversationsList(handle.Context.Pointer, owner, callback, userData, out operation),
            NativeLeafCodec.OperationConversationSummaries);

    /// <summary>Reads a complete immutable conversation snapshot.</summary>
    public unsafe Task<CodexConversationSnapshot> ReadAsync(
        CodexConversationId conversationId,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(conversationId);
        return NativeLeafCodec.WithConversationId(handle, conversationId, nativeId =>
            Run(cancellationToken, (nint owner, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation) =>
                NativeMethods.ConversationsRead(handle.Context.Pointer, owner, nativeId, callback, userData, out operation),
                NativeLeafCodec.OperationConversation));
    }

    /// <summary>Renames an existing conversation.</summary>
    public unsafe Task RenameAsync(
        CodexConversationId conversationId,
        string name,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(conversationId);
        ArgumentException.ThrowIfNullOrWhiteSpace(name);
        return NativeLeafCodec.WithConversationId(handle, conversationId, nativeId =>
            NativeLeafCodec.WithStringAsync(name, value =>
                NativeOperation.Run(handle, cancellationToken,
                    (nint owner, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation) => NativeMethods.ConversationsRename(
                        handle.Context.Pointer, owner, nativeId, value, callback, userData, out operation))));
    }

    /// <summary>Deletes an existing conversation.</summary>
    public unsafe Task DeleteAsync(
        CodexConversationId conversationId,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(conversationId);
        return NativeLeafCodec.WithConversationId(handle, conversationId, nativeId =>
            NativeOperation.Run(handle, cancellationToken,
                (nint owner, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation) => NativeMethods.ConversationsDelete(
                    handle.Context.Pointer, owner, nativeId, callback, userData, out operation)));
    }

    /// <summary>The current active conversation, or null.</summary>
    public CodexConversation? ActiveConversation => handle.Use(pointer =>
    {
        NativeApi.ThrowIfFailed(
            NativeMethods.ConversationsActiveGet(handle.Context.Pointer, pointer, out var snapshot),
            "read active conversation");
        try { return ProjectActive(pointer, snapshot); }
        finally { NativeApi.DestroySnapshot(handle.Context, snapshot); }
    });

    /// <summary>Opens a new conversation or resumes an existing one.</summary>
    public unsafe Task<CodexConversation> OpenAsync(
        CodexConversationOpenOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        options ??= new CodexConversationOpenOptions();
        var conversationId = options.ConversationId is null ? [] : NativeApi.Utf8(options.ConversationId);
        var serviceTier = options.ServiceTier is null ? [] : NativeApi.Utf8(options.ServiceTier);
        fixed (byte* conversationIdPointer = conversationId)
        fixed (byte* serviceTierPointer = serviceTier)
        {
            var nativeOptions = new NativeConversationOpenOptions
            {
                StructSize = (uint)sizeof(NativeConversationOpenOptions),
                HasConversationId = options.ConversationId is null ? 0 : 1,
                ConversationId = new NativeStringView
                {
                    Data = options.ConversationId is null ? null : conversationIdPointer,
                    Size = (nuint)conversationId.Length,
                },
                HasApprovalPreset = options.ApprovalPreset.HasValue ? 1 : 0,
                ApprovalPreset = options.ApprovalPreset ?? CodexApprovalPreset.Never,
                HasServiceTier = options.ServiceTier is null ? 0 : 1,
                ServiceTier = new NativeStringView
                {
                    Data = options.ServiceTier is null ? null : serviceTierPointer,
                    Size = (nuint)serviceTier.Length,
                },
            };
            var prepared = NativeOperation.Prepare(
                handle,
                cancellationToken,
                (owner, operation) =>
                {
                    NativeApi.ThrowIfFailed(
                        NativeMethods.OperationConversation(handle.Context.Pointer, owner, operation, out var conversation),
                        "read opened conversation");
                    return ReconcileActive(conversation);
                });
            try
            {
                var status = NativeMethods.ConversationsOpen(
                    handle.Context.Pointer,
                    prepared.OwnerPointer,
                    &nativeOptions,
                    prepared.Callback,
                    prepared.UserData,
                    out var operation);
                return prepared.Finish(status, operation);
            }
            catch
            {
                prepared.Abort();
                throw;
            }
        }
    }

    /// <summary>Observes current-value-first active conversation changes.</summary>
    public async IAsyncEnumerable<CodexConversation?> ObserveActiveConversationAsync(
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        await using var subscription = SubscribeActive();
        await foreach (var conversation in subscription.Reader.ReadAllAsync(cancellationToken).ConfigureAwait(false))
        {
            yield return conversation;
        }
    }

    private unsafe NativeSubscription<CodexConversation?> SubscribeActive() =>
        NativeSubscription<CodexConversation?>.Start(
            handle,
            (nint owner, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint output) =>
                NativeMethods.ConversationsActiveSubscribe(handle.Context.Pointer, owner, callback, userData, out output),
            ProjectActive);

    private unsafe Task<T> Run<T>(
        CancellationToken cancellationToken,
        NativeOperation.Starter starter,
        Func<nint, nint, T> projector) =>
        NativeOperation.Run(handle, cancellationToken, starter, (owner, operation) =>
        {
            using var call = NativeCallContext.Enter(handle.Context);
            return projector(owner, operation);
        });

    private CodexConversation? ProjectActive(nint conversations, nint snapshot)
    {
        var status = NativeMethods.ActiveConversation(
            handle.Context.Pointer,
            conversations,
            snapshot,
            out var conversation);
        if (status == CodexStatus.NotReady || (status == CodexStatus.Ok && conversation == 0))
        {
            ClearActive();
            return null;
        }
        NativeApi.ThrowIfFailed(status, "read active conversation value");
        return ReconcileActive(conversation);
    }

    private CodexConversation ReconcileActive(nint conversation)
    {
        lock (activeGate)
        {
            if (active is not null && active.IsSameNative(conversation))
            {
                NativeApi.Release(
                    () => NativeMethods.ConversationRelease(handle.Context.Pointer, ref conversation),
                    "release duplicate conversation handle");
                return active;
            }

            active?.DisposeOwned();
            active = new CodexConversation(new ConversationHandle(handle.Context, conversation));
            return active;
        }
    }

    private void ClearActive()
    {
        lock (activeGate)
        {
            active?.DisposeOwned();
            active = null;
        }
    }

    internal void DisposeOwned()
    {
        ClearActive();
        handle.DisposeChecked();
    }
}
