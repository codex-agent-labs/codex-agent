using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;

namespace CodexAgent.Interop;

internal sealed class NativeService(ServiceHandle handle)
{
    internal ServiceHandle Handle => handle;

    internal bool Available(Func<nint, nint, (CodexStatus Status, int Value)> read) => handle.Use(pointer =>
    {
        var (status, value) = read(handle.Context.Pointer, pointer);
        NativeApi.ThrowIfFailed(status, "read service availability");
        return value != 0;
    });

    internal T Current<T>(SnapshotGetter getter, Func<nint, nint, T> projector) => handle.Use(pointer =>
    {
        NativeApi.ThrowIfFailed(getter(handle.Context.Pointer, pointer, out var snapshot), "read service state");
        try { using var call = NativeCallContext.Enter(handle.Context); return projector(pointer, snapshot); }
        finally { NativeApi.DestroySnapshot(handle.Context, snapshot); }
    });

    internal async IAsyncEnumerable<T> Observe<T>(
        NativeSubscription<T>.Starter subscriber,
        Func<nint, nint, T> projector,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        await using var subscription = NativeSubscription<T>.Start(handle, subscriber, (owner, snapshot) =>
        {
            using var call = NativeCallContext.Enter(handle.Context);
            return projector(owner, snapshot);
        });
        await foreach (var value in subscription.Reader.ReadAllAsync(cancellationToken).ConfigureAwait(false))
            yield return value;
    }

    internal unsafe Task Run(CancellationToken cancellationToken, NativeOperation.Starter starter) =>
        NativeOperation.Run(handle, cancellationToken, starter);

    internal unsafe Task<T> Run<T>(
        CancellationToken cancellationToken,
        NativeOperation.Starter starter,
        Func<nint, nint, T> projector) => NativeOperation.Run(handle, cancellationToken, starter, (owner, operation) =>
        {
            using var call = NativeCallContext.Enter(handle.Context);
            return projector(owner, operation);
        });

    internal void DisposeOwned() => handle.DisposeChecked();

    internal unsafe delegate CodexStatus SnapshotGetter(nint context, nint service, out nint snapshot);
}
