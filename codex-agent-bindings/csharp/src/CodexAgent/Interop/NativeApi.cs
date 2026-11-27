using System.Text;

namespace CodexAgent.Interop;

internal static unsafe class NativeApi
{
    private const int ReleaseBusyLimit = 100;
    private static readonly UTF8Encoding StrictUtf8 = new(false, true);
    private static readonly Lazy<uint> LoadedAbi = new(() =>
    {
        var actual = NativeMethods.GetAbiVersion();
        if ((actual >> 24) != 1 || NativeMethods.IsAbiCompatible(NativeMethods.AbiVersion) != 1)
        {
            throw new CodexAbiException(actual);
        }
        return actual;
    }, LazyThreadSafetyMode.ExecutionAndPublication);

    internal delegate CodexStatus StringCopy(byte* buffer, nuint capacity, out nuint required);

    internal static void EnsureCompatibleAbi() => _ = LoadedAbi.Value;

    internal static void ThrowIfFailed(CodexStatus status, string action)
    {
        if (status != CodexStatus.Ok)
        {
            throw new CodexException(status, $"Could not {action}: native status {status} ({(int)status}).");
        }
    }

    internal static void Release(Func<CodexStatus> release, string action)
    {
        ThrowIfFailed(RetryBusy(release), action);
    }

    internal static CodexStatus RetryBusy(Func<CodexStatus> release)
    {
        for (var attempt = 0; attempt < ReleaseBusyLimit; attempt += 1)
        {
            var status = release();
            if (status != CodexStatus.Busy) return status;
            if (status == CodexStatus.Busy && !Thread.Yield()) Thread.Sleep(1);
        }
        return CodexStatus.Busy;
    }

    internal static byte[] Utf8(string value)
    {
        ArgumentNullException.ThrowIfNull(value);
        return StrictUtf8.GetBytes(value);
    }

    internal static string CopyString(StringCopy copy)
    {
        var status = copy(null, 0, out var required);
        if (status != CodexStatus.Ok && status != CodexStatus.BufferTooSmall)
        {
            ThrowIfFailed(status, "read a native string");
        }
        if (required == 0) return string.Empty;
        if (required > int.MaxValue) throw new CodexException(CodexStatus.OutOfMemory, "Native string is too large.");

        var bytes = GC.AllocateUninitializedArray<byte>((int)required);
        fixed (byte* buffer = bytes)
        {
            ThrowIfFailed(copy(buffer, required, out var written), "read a native string");
            if (written != required)
            {
                throw new CodexException(CodexStatus.InternalError, "Native string size changed while copying immutable state.");
            }
        }
        return StrictUtf8.GetString(bytes);
    }

    internal static string? CopyNullableString(StringCopy copy)
    {
        var status = copy(null, 0, out var required);
        if (status == CodexStatus.NotReady) return null;
        if (status != CodexStatus.Ok && status != CodexStatus.BufferTooSmall)
        {
            ThrowIfFailed(status, "read a nullable native string");
        }
        if (required == 0) return string.Empty;
        if (required > int.MaxValue) throw new CodexException(CodexStatus.OutOfMemory, "Native string is too large.");

        var bytes = GC.AllocateUninitializedArray<byte>((int)required);
        fixed (byte* buffer = bytes)
        {
            status = copy(buffer, required, out var written);
            if (status == CodexStatus.NotReady) return null;
            ThrowIfFailed(status, "read a nullable native string");
            if (written != required)
            {
                throw new CodexException(CodexStatus.InternalError, "Native string size changed while copying immutable state.");
            }
        }
        return StrictUtf8.GetString(bytes);
    }

    internal static CodexFailure ReadFailure(NativeContext context, nint failure)
    {
        try
        {
            var code = CopyString((byte* buffer, nuint capacity, out nuint required) =>
                NativeMethods.FailureCodeCopy(context.Pointer, failure, buffer, capacity, out required));
            var message = CopyString((byte* buffer, nuint capacity, out nuint required) =>
                NativeMethods.FailureMessageCopy(context.Pointer, failure, buffer, capacity, out required));
            ThrowIfFailed(NativeMethods.FailureIsRecoverable(context.Pointer, failure, out var recoverable), "read failure recovery status");
            return new CodexFailure(code, message, recoverable != 0);
        }
        finally
        {
            var owned = failure;
            ThrowIfFailed(NativeMethods.FailureRelease(context.Pointer, ref owned), "release failure");
        }
    }

    internal static void DestroySnapshot(NativeContext context, nint snapshot)
    {
        if (snapshot == 0) return;
        ThrowIfFailed(NativeMethods.SnapshotDestroy(context.Pointer, ref snapshot), "destroy state snapshot");
    }
}
