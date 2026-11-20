using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Threading.Channels;

namespace CodexAgent.Interop;

internal interface INativeSubscription
{
    void Publish(nint subscription, CodexStatus eventStatus, nint snapshot, bool terminal);
}

internal static unsafe class NativeSubscriptionCallback
{
    internal static delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> Pointer => &Publish;

    [UnmanagedCallersOnly(CallConvs = [typeof(CallConvCdecl)])]
    private static void Publish(
        nint context,
        nint subscription,
        CodexStatus eventStatus,
        nint snapshot,
        int terminal,
        nint userData)
    {
        try
        {
            var handle = GCHandle.FromIntPtr(userData);
            if (handle.Target is INativeSubscription state)
            {
                state.Publish(subscription, eventStatus, snapshot, terminal != 0);
            }
        }
        catch
        {
            // Native callbacks must never unwind across the C boundary.
        }
    }
}

internal sealed class NativeSubscription<T> : IAsyncDisposable, INativeSubscription
{
    internal unsafe delegate CodexStatus Starter(
        nint owner,
        delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback,
        nint userData,
        out nint subscription);

    private readonly NativeContext context;
    private readonly ContextBoundHandle owner;
    private readonly bool ownerHeld;
    private readonly Func<nint, nint, T> projector;
    private readonly Channel<T> events = Channel.CreateUnbounded<T>(new UnboundedChannelOptions
    {
        SingleReader = true,
        SingleWriter = true,
        AllowSynchronousContinuations = false,
    });
    private GCHandle self;
    private nint subscription;
    private int started;
    private int disposed;

    private NativeSubscription(ContextBoundHandle owner, Func<nint, nint, T> projector)
    {
        this.owner = owner;
        OwnerPointer = owner.AcquirePointer(out ownerHeld);
        context = owner.Context;
        this.projector = projector;
    }

    internal ChannelReader<T> Reader => events.Reader;
    internal nint OwnerPointer { get; }

    internal static unsafe NativeSubscription<T> Start(
        ContextBoundHandle owner,
        Starter starter,
        Func<nint, nint, T> projector)
    {
        var state = new NativeSubscription<T>(owner, projector);
        try
        {
            state.self = GCHandle.Alloc(state);
        }
        catch
        {
            owner.ReleasePointer(state.ownerHeld);
            throw;
        }
        CodexStatus status;
        nint subscription;
        try
        {
            status = starter(
                state.OwnerPointer,
                NativeSubscriptionCallback.Pointer,
                GCHandle.ToIntPtr(state.self),
                out subscription);
        }
        catch
        {
            state.self.Free();
            owner.ReleasePointer(state.ownerHeld);
            throw;
        }
        if (status != CodexStatus.Ok)
        {
            state.self.Free();
            owner.ReleasePointer(state.ownerHeld);
            NativeApi.ThrowIfFailed(status, "subscribe to native state");
        }
        state.subscription = subscription;
        Volatile.Write(ref state.started, 1);
        return state;
    }

    void INativeSubscription.Publish(nint value, CodexStatus eventStatus, nint snapshot, bool terminal)
    {
        subscription = value;
        try
        {
            if (eventStatus != CodexStatus.Ok)
            {
                events.Writer.TryComplete(new CodexException(
                    eventStatus,
                    $"Native state subscription failed with {eventStatus} ({(int)eventStatus})."));
            }
            else if (snapshot != 0)
            {
                events.Writer.TryWrite(projector(OwnerPointer, snapshot));
            }
            if (terminal) events.Writer.TryComplete();
        }
        catch (Exception error)
        {
            events.Writer.TryComplete(error);
        }
        finally
        {
            try
            {
                NativeApi.DestroySnapshot(context, snapshot);
            }
            catch (Exception error)
            {
                events.Writer.TryComplete(error);
            }
        }
    }

    public async ValueTask DisposeAsync()
    {
        if (Interlocked.Exchange(ref disposed, 1) != 0) return;
        events.Writer.TryComplete();
        while (Volatile.Read(ref started) == 0) await Task.Yield();

        var pointer = subscription;
        CodexStatus status;
        try
        {
            do
            {
                status = NativeMethods.SubscriptionDestroy(context.Pointer, ref pointer);
                if (status == CodexStatus.Busy) await Task.Delay(1).ConfigureAwait(false);
            } while (status == CodexStatus.Busy);
        }
        catch
        {
            Volatile.Write(ref disposed, 0);
            throw;
        }

        if (status != CodexStatus.Ok)
        {
            Volatile.Write(ref disposed, 0);
            NativeApi.ThrowIfFailed(status, "destroy native state subscription");
        }

        if (self.IsAllocated) self.Free();
        owner.ReleasePointer(ownerHeld);
    }
}
