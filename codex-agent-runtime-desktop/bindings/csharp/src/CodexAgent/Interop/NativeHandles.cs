using System.Collections.Concurrent;
using Microsoft.Win32.SafeHandles;

namespace CodexAgent.Interop;

internal static class NativeCleanup
{
    private sealed record Quarantine(CodexNativeCleanupIssue Issue, object Owner);

    private static readonly ConcurrentQueue<Quarantine> Quarantined = new();

    internal static IReadOnlyList<CodexNativeCleanupIssue> Issues =>
        Quarantined.Select(static value => value.Issue).ToArray();

    internal static void Report(string resource, CodexStatus status, object owner) =>
        Quarantined.Enqueue(new Quarantine(new CodexNativeCleanupIssue(resource, status), owner));
}

internal sealed class NativeContext
{
    private readonly ContextHandle handle;
    private int references = 1;

    private NativeContext(ContextHandle handle) => this.handle = handle;

    internal nint Pointer => handle.DangerousGetHandle();

    internal static NativeContext Create()
    {
        NativeApi.EnsureCompatibleAbi();
        NativeApi.ThrowIfFailed(NativeMethods.ContextCreate(out var pointer), "create native context");
        return new NativeContext(new ContextHandle(pointer));
    }

    internal void Acquire()
    {
        if (Interlocked.Increment(ref references) <= 1)
        {
            Interlocked.Decrement(ref references);
            throw new ObjectDisposedException(nameof(NativeContext));
        }
    }

    internal void Release()
    {
        if (Interlocked.Decrement(ref references) == 0)
        {
            handle.Dispose();
        }
    }

    internal void ThrowIfReleaseFailed() => handle.ThrowIfReleaseFailed();
}

internal sealed class ContextHandle : SafeHandleZeroOrMinusOneIsInvalid
{
    private int releaseFailure = -1;

    internal ContextHandle(nint pointer) : base(true) => SetHandle(pointer);

    public ContextHandle() : base(true) { }

    protected override bool ReleaseHandle()
    {
        var pointer = handle;
        var status = NativeApi.RetryBusy(() => NativeMethods.ContextDestroy(ref pointer));
        if (status == CodexStatus.Ok)
        {
            SetHandle(pointer);
        }
        else if (Interlocked.CompareExchange(ref releaseFailure, (int)status, -1) == -1)
        {
            try { NativeCleanup.Report(nameof(ContextHandle), status, this); }
            catch { /* ReleaseHandle must not unwind on the finalizer thread. */ }
        }
        return status == CodexStatus.Ok;
    }

    internal void ThrowIfReleaseFailed()
    {
        var status = Volatile.Read(ref releaseFailure);
        if (status >= 0)
        {
            throw new CodexException(
                (CodexStatus)status,
                $"Could not release native context: native status {(CodexStatus)status} ({status}).");
        }
    }
}

internal abstract class ContextBoundHandle : SafeHandleZeroOrMinusOneIsInvalid
{
    private int contextReleased;
    private int releaseFailure = -1;

    protected ContextBoundHandle(NativeContext context, nint pointer) : base(true)
    {
        Context = context;
        context.Acquire();
        SetHandle(pointer);
    }

    internal NativeContext Context { get; }

    internal T Use<T>(Func<nint, T> action)
    {
        var added = false;
        try
        {
            DangerousAddRef(ref added);
            if (IsInvalid || IsClosed)
            {
                throw new ObjectDisposedException(GetType().Name);
            }
            return action(DangerousGetHandle());
        }
        finally
        {
            if (added) DangerousRelease();
        }
    }

    internal nint AcquirePointer(out bool added)
    {
        added = false;
        DangerousAddRef(ref added);
        if (IsInvalid || IsClosed)
        {
            if (added) DangerousRelease();
            added = false;
            throw new ObjectDisposedException(GetType().Name);
        }
        return DangerousGetHandle();
    }

    internal void ReleasePointer(bool added)
    {
        if (added) DangerousRelease();
    }

    internal void DisposeChecked()
    {
        Dispose();
        var status = Volatile.Read(ref releaseFailure);
        if (status >= 0)
        {
            throw new CodexException(
                (CodexStatus)status,
                $"Could not release native {GetType().Name}: native status {(CodexStatus)status} ({status}).");
        }
        Context.ThrowIfReleaseFailed();
    }

    protected sealed override bool ReleaseHandle()
    {
        var pointer = handle;
        var status = NativeApi.RetryBusy(() => ReleaseNative(Context.Pointer, ref pointer));
        if (status != CodexStatus.Ok)
        {
            if (Interlocked.CompareExchange(ref releaseFailure, (int)status, -1) == -1)
            {
                try { NativeCleanup.Report(GetType().Name, status, this); }
                catch { /* ReleaseHandle must not unwind on the finalizer thread. */ }
            }
            return false;
        }

        SetHandle(pointer);
        if (Interlocked.Exchange(ref contextReleased, 1) == 0) Context.Release();
        return true;
    }

    protected abstract CodexStatus ReleaseNative(nint context, ref nint pointer);
}

internal sealed class HostHandle(NativeContext context, nint pointer) : ContextBoundHandle(context, pointer)
{
    protected override CodexStatus ReleaseNative(nint context, ref nint pointer) =>
        NativeMethods.HostRelease(context, ref pointer);
}

internal sealed class AgentHandle(NativeContext context, nint pointer) : ContextBoundHandle(context, pointer)
{
    protected override CodexStatus ReleaseNative(nint context, ref nint pointer) =>
        NativeMethods.AgentRelease(context, ref pointer);
}

internal sealed class ConversationsHandle(NativeContext context, nint pointer) : ContextBoundHandle(context, pointer)
{
    protected override CodexStatus ReleaseNative(nint context, ref nint pointer) =>
        NativeMethods.ConversationsRelease(context, ref pointer);
}

internal sealed class ConversationHandle(NativeContext context, nint pointer) : ContextBoundHandle(context, pointer)
{
    protected override CodexStatus ReleaseNative(nint context, ref nint pointer) =>
        NativeMethods.ConversationRelease(context, ref pointer);
}

internal delegate CodexStatus NativeHandleRelease(nint context, ref nint pointer);

internal sealed class ServiceHandle(
    NativeContext context,
    nint pointer,
    NativeHandleRelease release) : ContextBoundHandle(context, pointer)
{
    protected override CodexStatus ReleaseNative(nint context, ref nint pointer) => release(context, ref pointer);
}
