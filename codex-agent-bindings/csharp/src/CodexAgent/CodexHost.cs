using System.Runtime.CompilerServices;
using CodexAgent.Interop;

namespace CodexAgent;

/// <summary>Owns the local desktop runtime and its agent tree.</summary>
public sealed class CodexHost : IDisposable, IAsyncDisposable
{
    private readonly HostHandle handle;
    private readonly object childGate = new();
    private readonly object disposeGate = new();
    private CodexAgent? agent;
    private Task? disposeTask;
    private int disposed;

    private CodexHost(HostHandle handle) => this.handle = handle;

    /// <summary>Creates a host over the verified native C SDK.</summary>
    public static unsafe CodexHost Create(CodexHostOptions options)
    {
        ArgumentNullException.ThrowIfNull(options);
        options.Validate();

        var bundle = NativeApi.Utf8(options.BundleDirectory);
        var data = NativeApi.Utf8(options.DataDirectory);
        var name = NativeApi.Utf8(options.ClientInfo.Name);
        var title = NativeApi.Utf8(options.ClientInfo.Title);
        var version = NativeApi.Utf8(options.ClientInfo.Version);
        var context = NativeContext.Create();
        try
        {
            fixed (byte* bundlePointer = bundle)
            fixed (byte* dataPointer = data)
            fixed (byte* namePointer = name)
            fixed (byte* titlePointer = title)
            fixed (byte* versionPointer = version)
            {
                var nativeOptions = new NativeHostOptions
                {
                    StructSize = (uint)sizeof(NativeHostOptions),
                    BundleDirectory = new NativeStringView { Data = bundlePointer, Size = (nuint)bundle.Length },
                    DataDirectory = new NativeStringView { Data = dataPointer, Size = (nuint)data.Length },
                    ClientInfo = new NativeClientInfo
                    {
                        StructSize = (uint)sizeof(NativeClientInfo),
                        Name = new NativeStringView { Data = namePointer, Size = (nuint)name.Length },
                        Title = new NativeStringView { Data = titlePointer, Size = (nuint)title.Length },
                        Version = new NativeStringView { Data = versionPointer, Size = (nuint)version.Length },
                    },
                };
                NativeApi.ThrowIfFailed(
                    NativeMethods.HostCreate(context.Pointer, &nativeOptions, out var pointer),
                    "create host");
                var host = new CodexHost(new HostHandle(context, pointer));
                context.Release();
                return host;
            }
        }
        catch
        {
            context.Release();
            throw;
        }
    }

    /// <summary>The current immutable host state.</summary>
    public CodexHostState State
    {
        get
        {
            ThrowIfDisposed();
            return handle.Use(pointer =>
            {
                NativeApi.ThrowIfFailed(
                    NativeMethods.HostStateGet(handle.Context.Pointer, pointer, out var snapshot),
                    "read host state");
                try { return ProjectState(pointer, snapshot); }
                finally { NativeApi.DestroySnapshot(handle.Context, snapshot); }
            });
        }
    }

    /// <summary>Starts or retries host preparation.</summary>
    public unsafe Task StartAsync(CancellationToken cancellationToken = default)
    {
        ThrowIfDisposed();
        return NativeOperation.Run(
            handle,
            cancellationToken,
            (nint owner, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation) =>
                NativeMethods.HostStart(handle.Context.Pointer, owner, callback, userData, out operation));
    }

    /// <summary>Selects a workspace and resumes host preparation.</summary>
    public unsafe Task SelectWorkspaceAsync(string path, CancellationToken cancellationToken = default)
    {
        ThrowIfDisposed();
        ArgumentException.ThrowIfNullOrWhiteSpace(path);
        var bytes = NativeApi.Utf8(path);
        fixed (byte* data = bytes)
        {
            var selection = new NativePathWorkspaceSelection
            {
                StructSize = (uint)sizeof(NativePathWorkspaceSelection),
                Path = new NativeStringView { Data = data, Size = (nuint)bytes.Length },
            };
            var prepared = NativeOperation.Prepare(handle, cancellationToken);
            try
            {
                var status = NativeMethods.HostSelectWorkspace(
                    handle.Context.Pointer,
                    prepared.OwnerPointer,
                    &selection,
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

    /// <summary>Closes the host and its owned children asynchronously.</summary>
    public Task CloseAsync(CancellationToken cancellationToken = default)
    {
        ThrowIfDisposed();
        return CloseCoreAsync(cancellationToken);
    }

    /// <summary>Observes current-value-first host state changes.</summary>
    public async IAsyncEnumerable<CodexHostState> ObserveStatesAsync(
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        ThrowIfDisposed();
        await using var subscription = SubscribeStates();
        await foreach (var state in subscription.Reader.ReadAllAsync(cancellationToken).ConfigureAwait(false))
        {
            yield return state;
        }
    }

    private unsafe NativeSubscription<CodexHostState> SubscribeStates() =>
        NativeSubscription<CodexHostState>.Start(
            handle,
            (nint owner, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint output) =>
                NativeMethods.HostStateSubscribe(handle.Context.Pointer, owner, callback, userData, out output),
            ProjectState);

    private unsafe Task CloseCoreAsync(CancellationToken cancellationToken) => NativeOperation.Run(
        handle,
        cancellationToken,
        (nint owner, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation) =>
            NativeMethods.HostClose(handle.Context.Pointer, owner, callback, userData, out operation));

    private unsafe CodexHostState ProjectState(nint host, nint snapshot)
    {
        NativeApi.ThrowIfFailed(
            NativeMethods.HostStateKind(handle.Context.Pointer, snapshot, out var kind),
            "read host state kind");

        CodexWorkspace? workspace = null;
        NativeApi.ThrowIfFailed(
            NativeMethods.HostStateHasWorkspace(handle.Context.Pointer, snapshot, out var hasWorkspace),
            "read host workspace availability");
        if (hasWorkspace != 0)
        {
            var path = NativeApi.CopyString((byte* buffer, nuint capacity, out nuint required) =>
                NativeMethods.HostStateWorkspacePathCopy(handle.Context.Pointer, snapshot, buffer, capacity, out required));
            var displayName = NativeApi.CopyNullableString((byte* buffer, nuint capacity, out nuint required) =>
                NativeMethods.HostStateWorkspaceDisplayNameCopy(handle.Context.Pointer, snapshot, buffer, capacity, out required));
            workspace = new CodexWorkspace(path, displayName);
        }

        CodexWorkspaceSelectionReason? reason = null;
        string? requirementMessage = null;
        if (kind == CodexHostStateKind.WorkspaceRequired)
        {
            NativeApi.ThrowIfFailed(
                NativeMethods.HostStateRequirementReason(handle.Context.Pointer, snapshot, out var value),
                "read workspace selection reason");
            reason = value;
            requirementMessage = NativeApi.CopyString((byte* buffer, nuint capacity, out nuint required) =>
                NativeMethods.HostStateRequirementMessageCopy(handle.Context.Pointer, snapshot, buffer, capacity, out required));
        }

        CodexFailure? failure = null;
        if (kind == CodexHostStateKind.Failed)
        {
            NativeApi.ThrowIfFailed(
                NativeMethods.HostStateFailure(handle.Context.Pointer, snapshot, out var nativeFailure),
                "read host failure");
            failure = NativeApi.ReadFailure(handle.Context, nativeFailure);
        }

        CodexAgent? readyAgent = null;
        if (kind == CodexHostStateKind.Ready)
        {
            NativeApi.ThrowIfFailed(
                NativeMethods.HostStateAgent(handle.Context.Pointer, host, snapshot, out var nativeAgent),
                "read ready agent");
            lock (childGate)
            {
                if (agent is null)
                {
                    agent = new CodexAgent(new AgentHandle(handle.Context, nativeAgent));
                }
                else
                {
                    NativeApi.Release(
                        () => NativeMethods.AgentRelease(handle.Context.Pointer, ref nativeAgent),
                        "release duplicate agent handle");
                }
                readyAgent = agent;
            }
        }

        return new CodexHostState(kind, workspace, readyAgent, reason, requirementMessage, failure);
    }

    /// <summary>Releases an already-closed host. Use <see cref="DisposeAsync"/> while it is open.</summary>
    public void Dispose()
    {
        if (Volatile.Read(ref disposed) != 0) return;
        if (State.Kind != CodexHostStateKind.Closed)
        {
            throw new InvalidOperationException("The host is open; use DisposeAsync() so it can close before native release.");
        }
        if (Interlocked.Exchange(ref disposed, 1) != 0) return;
        lock (childGate) agent?.DisposeOwned();
        handle.DisposeChecked();
    }

    /// <summary>Closes the host, then releases all native ownership.</summary>
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
        lock (childGate) agent?.DisposeOwned();
        handle.DisposeChecked();
    }

    private void ThrowIfDisposed() => ObjectDisposedException.ThrowIf(disposed != 0, this);
}
