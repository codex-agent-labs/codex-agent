using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;

namespace CodexAgent.Interop;

internal readonly struct NativeUnit;

internal static class NativeOperation
{
    internal unsafe delegate CodexStatus Starter(
        nint owner,
        delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback,
        nint userData,
        out nint operation);

    internal static unsafe Task Run(
        ContextBoundHandle owner,
        CancellationToken cancellationToken,
        Starter starter) => Run(owner, cancellationToken, starter, static (_, _) => new NativeUnit());

    internal static unsafe Task<T> Run<T>(
        ContextBoundHandle owner,
        CancellationToken cancellationToken,
        Starter starter,
        Func<nint, nint, T> projector)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var state = new State<T>(owner, cancellationToken, projector);
        nint userData;
        try
        {
            userData = state.Allocate();
        }
        catch
        {
            state.AbortStart();
            throw;
        }

        CodexStatus status;
        nint operation;
        try
        {
            status = starter(state.OwnerPointer, &Complete, userData, out operation);
        }
        catch
        {
            state.AbortStart();
            throw;
        }
        if (status != CodexStatus.Ok)
        {
            state.AbortStart();
            NativeApi.ThrowIfFailed(status, "start native operation");
        }
        state.MarkStarted(operation);
        return state.Task;
    }

    internal static Prepared<T> Prepare<T>(
        ContextBoundHandle owner,
        CancellationToken cancellationToken,
        Func<nint, nint, T> projector)
    {
        cancellationToken.ThrowIfCancellationRequested();
        return new Prepared<T>(new State<T>(owner, cancellationToken, projector));
    }

    internal static Prepared<NativeUnit> Prepare(
        ContextBoundHandle owner,
        CancellationToken cancellationToken) =>
        Prepare(owner, cancellationToken, static (_, _) => new NativeUnit());

    internal sealed unsafe class Prepared<T>
    {
        private readonly State<T> state;

        internal Prepared(State<T> state)
        {
            this.state = state;
            try
            {
                UserData = state.Allocate();
            }
            catch
            {
                state.AbortStart();
                throw;
            }
        }

        internal delegate* unmanaged[Cdecl]<nint, nint, nint, void> Callback => &Complete;
        internal nint OwnerPointer => state.OwnerPointer;
        internal nint UserData { get; }

        internal Task<T> Finish(CodexStatus status, nint operation)
        {
            if (status != CodexStatus.Ok)
            {
                state.AbortStart();
                NativeApi.ThrowIfFailed(status, "start native operation");
            }
            state.MarkStarted(operation);
            return state.Task;
        }

        internal void Abort() => state.AbortStart();
    }

    [UnmanagedCallersOnly(CallConvs = [typeof(CallConvCdecl)])]
    private static void Complete(nint context, nint operation, nint userData)
    {
        try
        {
            var handle = GCHandle.FromIntPtr(userData);
            if (handle.Target is IState state) state.Complete(operation);
        }
        catch
        {
            // Native callbacks must never unwind across the C boundary.
        }
    }

    internal interface IState
    {
        void Complete(nint operation);
    }

    internal sealed class State<T> : IState
    {
        private readonly object gate = new();
        private readonly ContextBoundHandle owner;
        private readonly NativeContext context;
        private readonly CancellationToken cancellationToken;
        private readonly Func<nint, nint, T> projector;
        private readonly TaskCompletionSource<T> completion = new(TaskCreationOptions.RunContinuationsAsynchronously);
        private readonly CancellationTokenRegistration cancellationRegistration;
        private readonly bool ownerHeld;
        private GCHandle self;
        private nint operation;
        private T outcome = default!;
        private Exception? outcomeError;
        private Exception? cancelError;
        private bool outcomeCancelled;
        private bool started;
        private bool callbackStarted;
        private bool callbackFinished;
        private bool cancellationRequested;
        private bool cancellationIssued;
        private bool cleanupStarted;
        private int cancelCalls;
        private int startAborted;

        internal State(
            ContextBoundHandle owner,
            CancellationToken cancellationToken,
            Func<nint, nint, T> projector)
        {
            this.owner = owner;
            this.cancellationToken = cancellationToken;
            this.projector = projector;
            OwnerPointer = owner.AcquirePointer(out ownerHeld);
            context = owner.Context;
            cancellationRegistration = cancellationToken.Register(static value => ((State<T>)value!).Cancel(), this);
        }

        internal nint OwnerPointer { get; }
        internal Task<T> Task => completion.Task;

        internal nint Allocate()
        {
            self = GCHandle.Alloc(this);
            return GCHandle.ToIntPtr(self);
        }

        internal void MarkStarted(nint pointer)
        {
            var issueCancellation = false;
            lock (gate)
            {
                operation = pointer;
                started = true;
                if (cancellationRequested && !callbackStarted && !cancellationIssued)
                {
                    cancellationIssued = true;
                    cancelCalls += 1;
                    issueCancellation = true;
                }
            }
            if (issueCancellation) CancelNative(pointer);
            TryCleanup();
        }

        internal void AbortStart()
        {
            if (Interlocked.Exchange(ref startAborted, 1) != 0) return;
            cancellationRegistration.Dispose();
            if (self.IsAllocated) self.Free();
            owner.ReleasePointer(ownerHeld);
        }

        public void Complete(nint pointer)
        {
            lock (gate)
            {
                if (callbackStarted) return;
                callbackStarted = true;
                operation = pointer;
            }

            try
            {
                NativeApi.ThrowIfFailed(
                    NativeMethods.OperationResult(context.Pointer, pointer, out var result),
                    "read native operation result");
                switch (result)
                {
                    case CodexStatus.Ok:
                        outcome = projector(OwnerPointer, pointer);
                        break;
                    case CodexStatus.Cancelled:
                        outcomeCancelled = true;
                        break;
                    case CodexStatus.OperationFailed:
                        NativeApi.ThrowIfFailed(
                            NativeMethods.OperationFailure(context.Pointer, pointer, out var failure),
                            "read native operation failure");
                        outcomeError = new CodexOperationException(NativeApi.ReadFailure(context, failure));
                        break;
                    default:
                        outcomeError = new CodexException(
                            result,
                            $"Native operation failed with {result} ({(int)result}).");
                        break;
                }
            }
            catch (Exception error)
            {
                outcomeError = error;
            }
            finally
            {
                lock (gate) callbackFinished = true;
                TryCleanup();
            }
        }

        private void Cancel()
        {
            nint pointer = 0;
            lock (gate)
            {
                cancellationRequested = true;
                if (started && !callbackStarted && !cancellationIssued)
                {
                    cancellationIssued = true;
                    cancelCalls += 1;
                    pointer = operation;
                }
            }
            if (pointer != 0) CancelNative(pointer);
        }

        private void CancelNative(nint pointer)
        {
            Exception? error = null;
            try
            {
                var status = NativeMethods.OperationCancel(context.Pointer, pointer);
                if (status != CodexStatus.Ok)
                {
                    error = new CodexException(
                        status,
                        $"Could not cancel native operation: native status {status} ({(int)status}).");
                }
            }
            catch (Exception exception)
            {
                error = exception;
            }
            finally
            {
                lock (gate)
                {
                    cancelCalls -= 1;
                    if (error is not null) cancelError ??= error;
                }
                TryCleanup();
            }
        }

        private void TryCleanup()
        {
            lock (gate)
            {
                if (!started || !callbackFinished || cancelCalls != 0 || cleanupStarted) return;
                cleanupStarted = true;
            }
            _ = CleanupAsync();
        }

        private async Task CleanupAsync()
        {
            var pointer = operation;
            CodexStatus status;
            try
            {
                do
                {
                    status = NativeMethods.OperationDestroy(context.Pointer, ref pointer);
                    if (status == CodexStatus.Busy)
                    {
                        await System.Threading.Tasks.Task.Delay(1).ConfigureAwait(false);
                    }
                } while (status == CodexStatus.Busy);
            }
            catch (Exception error)
            {
                completion.TrySetException(error);
                return;
            }

            if (status != CodexStatus.Ok)
            {
                completion.TrySetException(new CodexException(
                    status,
                    $"Could not destroy native operation: native status {status} ({(int)status})."));
                return;
            }

            cancellationRegistration.Dispose();
            if (self.IsAllocated) self.Free();
            owner.ReleasePointer(ownerHeld);

            if (cancelError is not null)
            {
                completion.TrySetException(cancelError);
            }
            else if (outcomeError is not null)
            {
                completion.TrySetException(outcomeError);
            }
            else if (outcomeCancelled)
            {
                completion.TrySetCanceled(cancellationToken.IsCancellationRequested
                    ? cancellationToken
                    : new CancellationToken(true));
            }
            else
            {
                completion.TrySetResult(outcome);
            }
        }
    }
}
