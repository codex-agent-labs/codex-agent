using System.Runtime.CompilerServices;
using CodexAgent.Interop;

namespace CodexAgent;

/// <summary>An owned conversation with asynchronous operations and observable state.</summary>
public sealed class CodexConversation : IDisposable, IAsyncDisposable
{
    private readonly ConversationHandle handle;
    private readonly object disposeGate = new();
    private Task? disposeTask;
    private int disposed;

    internal CodexConversation(ConversationHandle handle) => this.handle = handle;

    /// <summary>The current immutable conversation state.</summary>
    public CodexConversationState State
    {
        get
        {
            ThrowIfDisposed();
            return handle.Use(pointer =>
            {
                NativeApi.ThrowIfFailed(
                    NativeMethods.ConversationStateGet(handle.Context.Pointer, pointer, out var snapshot),
                    "read conversation state");
                try { return ProjectState(pointer, snapshot); }
                finally { NativeApi.DestroySnapshot(handle.Context, snapshot); }
            });
        }
    }

    /// <summary>Sends a prompt as a turn.</summary>
    public unsafe Task SendAsync(string prompt, CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(prompt);
        return RunStringOperation(prompt, cancellationToken, NativeMethods.ConversationSend);
    }

    /// <summary>Sends a structured turn request.</summary>
    public unsafe Task SendAsync(CodexTurnRequest request, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(request);
        ArgumentException.ThrowIfNullOrWhiteSpace(request.Prompt);
        ThrowIfDisposed();
        return NativeLeafCodec.WithTurnRequest(handle, request, nativeRequest =>
            NativeOperation.Run(handle, cancellationToken,
                (nint owner, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation) => NativeMethods.ConversationSendRequest(
                    handle.Context.Pointer, owner, nativeRequest, callback, userData, out operation)));
    }

    /// <summary>Runs a shell command through the canonical conversation operation.</summary>
    public unsafe Task RunShellCommandAsync(string command, CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(command);
        return RunStringOperation(command, cancellationToken, NativeMethods.ConversationRunShellCommand);
    }

    /// <summary>Reloads the conversation.</summary>
    public unsafe Task ReloadAsync(CancellationToken cancellationToken = default) =>
        RunOperation(cancellationToken, NativeMethods.ConversationReload);

    /// <summary>Cancels the active turn.</summary>
    public unsafe Task CancelTurnAsync(CancellationToken cancellationToken = default) =>
        RunOperation(cancellationToken, NativeMethods.ConversationCancelTurn);

    /// <summary>Closes the conversation asynchronously.</summary>
    public Task CloseAsync(CancellationToken cancellationToken = default)
    {
        ThrowIfDisposed();
        return CloseCoreAsync(cancellationToken);
    }

    /// <summary>Tests canonical conversation identity.</summary>
    public bool IsSame(CodexConversation other)
    {
        ArgumentNullException.ThrowIfNull(other);
        ThrowIfDisposed();
        other.ThrowIfDisposed();
        return handle.Use(left => other.handle.Use(right =>
        {
            NativeApi.ThrowIfFailed(
                NativeMethods.ConversationIsSame(handle.Context.Pointer, left, right, out var same),
                "compare conversation identity");
            return same != 0;
        }));
    }

    /// <summary>The current immutable ordered message collection.</summary>
    public IReadOnlyList<CodexMessage> CurrentMessages => Current(
        NativeMethods.ConversationCurrentMessagesGet, NativeLeafCodec.ConversationMessages);

    /// <summary>The current turn progress, or null when no turn is active.</summary>
    public CodexTurnProgress? ActiveTurnProgress => Current(
        NativeMethods.ConversationActiveTurnProgressGet, NativeLeafCodec.ActiveTurnProgress);

    /// <summary>Whether a new turn may start.</summary>
    public bool CanStartTurn => CurrentBoolean(NativeMethods.ConversationCanStartTurnGet);

    /// <summary>Whether the conversation may reload.</summary>
    public bool CanReload => CurrentBoolean(NativeMethods.ConversationCanReloadGet);

    /// <summary>Whether the active turn may be cancelled.</summary>
    public bool CanCancelTurn => CurrentBoolean(NativeMethods.ConversationCanCancelTurnGet);

    /// <summary>Whether shell commands may run.</summary>
    public bool CanRunShellCommand => CurrentBoolean(NativeMethods.ConversationCanRunShellCommandGet);

    /// <summary>Whether a turn is active.</summary>
    public bool IsTurnActive => CurrentBoolean(NativeMethods.ConversationIsTurnActiveGet);

    /// <summary>Observes current-value-first conversation state changes.</summary>
    public async IAsyncEnumerable<CodexConversationState> ObserveStatesAsync(
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        ThrowIfDisposed();
        await using var subscription = SubscribeStates();
        await foreach (var state in subscription.Reader.ReadAllAsync(cancellationToken).ConfigureAwait(false))
        {
            yield return state;
        }
    }

    /// <summary>Observes current-value-first ordered message changes.</summary>
    public unsafe IAsyncEnumerable<IReadOnlyList<CodexMessage>> ObserveCurrentMessagesAsync(
        CancellationToken cancellationToken = default) => Observe(
            (nint owner, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint output) =>
                NativeMethods.ConversationCurrentMessagesSubscribe(handle.Context.Pointer, owner, callback, userData, out output),
            NativeLeafCodec.ConversationMessages,
            cancellationToken);

    /// <summary>Observes current-value-first nullable turn-progress changes.</summary>
    public unsafe IAsyncEnumerable<CodexTurnProgress?> ObserveActiveTurnProgressAsync(
        CancellationToken cancellationToken = default) => Observe(
            (nint owner, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint output) =>
                NativeMethods.ConversationActiveTurnProgressSubscribe(handle.Context.Pointer, owner, callback, userData, out output),
            NativeLeafCodec.ActiveTurnProgress,
            cancellationToken);

    /// <summary>Observes whether a new turn may start.</summary>
    public unsafe IAsyncEnumerable<bool> ObserveCanStartTurnAsync(CancellationToken cancellationToken = default) =>
        ObserveBoolean((nint owner, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint output) =>
            NativeMethods.ConversationCanStartTurnSubscribe(handle.Context.Pointer, owner, callback, userData, out output), cancellationToken);

    /// <summary>Observes whether the conversation may reload.</summary>
    public unsafe IAsyncEnumerable<bool> ObserveCanReloadAsync(CancellationToken cancellationToken = default) =>
        ObserveBoolean((nint owner, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint output) =>
            NativeMethods.ConversationCanReloadSubscribe(handle.Context.Pointer, owner, callback, userData, out output), cancellationToken);

    /// <summary>Observes whether the active turn may be cancelled.</summary>
    public unsafe IAsyncEnumerable<bool> ObserveCanCancelTurnAsync(CancellationToken cancellationToken = default) =>
        ObserveBoolean((nint owner, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint output) =>
            NativeMethods.ConversationCanCancelTurnSubscribe(handle.Context.Pointer, owner, callback, userData, out output), cancellationToken);

    /// <summary>Observes whether shell commands may run.</summary>
    public unsafe IAsyncEnumerable<bool> ObserveCanRunShellCommandAsync(CancellationToken cancellationToken = default) =>
        ObserveBoolean((nint owner, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint output) =>
            NativeMethods.ConversationCanRunShellCommandSubscribe(handle.Context.Pointer, owner, callback, userData, out output), cancellationToken);

    /// <summary>Observes whether a turn is active.</summary>
    public unsafe IAsyncEnumerable<bool> ObserveIsTurnActiveAsync(CancellationToken cancellationToken = default) =>
        ObserveBoolean((nint owner, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint output) =>
            NativeMethods.ConversationIsTurnActiveSubscribe(handle.Context.Pointer, owner, callback, userData, out output), cancellationToken);

    private unsafe NativeSubscription<CodexConversationState> SubscribeStates() =>
        NativeSubscription<CodexConversationState>.Start(
            handle,
            (nint owner, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint output) =>
                NativeMethods.ConversationStateSubscribe(handle.Context.Pointer, owner, callback, userData, out output),
            ProjectState);

    private T Current<T>(NativeService.SnapshotGetter getter, Func<nint, nint, T> projector)
    {
        ThrowIfDisposed();
        return handle.Use(pointer =>
        {
            NativeApi.ThrowIfFailed(getter(handle.Context.Pointer, pointer, out var snapshot), "read conversation projection");
            try
            {
                using var call = NativeCallContext.Enter(handle.Context);
                return projector(pointer, snapshot);
            }
            finally { NativeApi.DestroySnapshot(handle.Context, snapshot); }
        });
    }

    private bool CurrentBoolean(NativeService.SnapshotGetter getter) =>
        Current(getter, NativeLeafCodec.BooleanState);

    private async IAsyncEnumerable<T> Observe<T>(
        NativeSubscription<T>.Starter subscriber,
        Func<nint, nint, T> projector,
        [EnumeratorCancellation] CancellationToken cancellationToken)
    {
        ThrowIfDisposed();
        await using var subscription = NativeSubscription<T>.Start(handle, subscriber, (owner, snapshot) =>
        {
            using var call = NativeCallContext.Enter(handle.Context);
            return projector(owner, snapshot);
        });
        await foreach (var value in subscription.Reader.ReadAllAsync(cancellationToken).ConfigureAwait(false))
            yield return value;
    }

    private IAsyncEnumerable<bool> ObserveBoolean(
        NativeSubscription<bool>.Starter subscriber,
        CancellationToken cancellationToken) =>
        Observe(subscriber, NativeLeafCodec.BooleanState, cancellationToken);

    internal bool IsSameNative(nint other)
    {
        if (disposed != 0) return false;
        return handle.Use(pointer =>
        {
            NativeApi.ThrowIfFailed(
                NativeMethods.ConversationIsSame(handle.Context.Pointer, pointer, other, out var same),
                "compare active conversation identity");
            return same != 0;
        });
    }

    private unsafe delegate CodexStatus StringOperation(
        nint context,
        nint conversation,
        NativeStringView* value,
        delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback,
        nint userData,
        out nint operation);

    private unsafe delegate CodexStatus Operation(
        nint context,
        nint conversation,
        delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback,
        nint userData,
        out nint operation);

    private unsafe Task RunStringOperation(string value, CancellationToken cancellationToken, StringOperation operation)
    {
        ThrowIfDisposed();
        return NativeLeafCodec.WithStringAsync(value, nativeValue =>
            NativeOperation.Run(
                handle,
                cancellationToken,
                (nint owner, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint output) =>
                    operation(handle.Context.Pointer, owner, nativeValue, callback, userData, out output)));
    }

    private unsafe Task RunOperation(CancellationToken cancellationToken, Operation operation)
    {
        ThrowIfDisposed();
        return NativeOperation.Run(
            handle,
            cancellationToken,
            (nint owner, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint output) =>
                operation(handle.Context.Pointer, owner, callback, userData, out output));
    }

    private unsafe Task CloseCoreAsync(CancellationToken cancellationToken) => NativeOperation.Run(
        handle,
        cancellationToken,
        (nint owner, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint output) =>
            NativeMethods.ConversationClose(handle.Context.Pointer, owner, callback, userData, out output));

    private CodexConversationState ProjectState(nint _owner, nint snapshot)
    {
        NativeApi.ThrowIfFailed(
            NativeMethods.ConversationStateStatus(handle.Context.Pointer, snapshot, out var status),
            "read conversation status");
        CodexFailure? failure = null;
        if (status == CodexConversationStatus.Failed)
        {
            NativeApi.ThrowIfFailed(
                NativeMethods.ConversationStateFailure(handle.Context.Pointer, snapshot, out var nativeFailure),
                "read conversation failure");
            failure = NativeApi.ReadFailure(handle.Context, nativeFailure);
        }
        return new CodexConversationState(status, failure);
    }

    /// <summary>Releases an already-closed conversation. Use <see cref="DisposeAsync"/> while it is open.</summary>
    public void Dispose()
    {
        if (Volatile.Read(ref disposed) != 0) return;
        if (State.Status != CodexConversationStatus.Closed)
        {
            throw new InvalidOperationException(
                "The conversation is open; use DisposeAsync() so it can close before native release.");
        }
        DisposeOwned();
    }

    /// <summary>Closes the conversation, then releases native ownership.</summary>
    public ValueTask DisposeAsync()
    {
        lock (disposeGate)
        {
            disposeTask ??= DisposeCoreAsync();
            return new ValueTask(disposeTask);
        }
    }

    private async Task DisposeCoreAsync()
    {
        if (Interlocked.Exchange(ref disposed, 1) != 0) return;
        await CloseCoreAsync(CancellationToken.None).ConfigureAwait(false);
        handle.DisposeChecked();
    }

    internal void DisposeOwned()
    {
        if (Interlocked.Exchange(ref disposed, 1) == 0) handle.DisposeChecked();
    }

    private void ThrowIfDisposed() => ObjectDisposedException.ThrowIf(disposed != 0, this);
}
