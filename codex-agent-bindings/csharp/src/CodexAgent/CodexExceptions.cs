namespace CodexAgent;

/// <summary>A C ABI call failed before producing a canonical operation result.</summary>
public class CodexException : Exception
{
    /// <summary>Native status returned by the C SDK.</summary>
    public CodexStatus Status { get; }

    /// <summary>Creates an exception for a native status.</summary>
    public CodexException(CodexStatus status, string message, Exception? innerException = null)
        : base(message, innerException) => Status = status;
}

/// <summary>A canonical operation completed with a structured failure.</summary>
public sealed class CodexOperationException : CodexException
{
    /// <summary>The canonical failure.</summary>
    public CodexFailure Failure { get; }

    internal CodexOperationException(CodexFailure failure)
        : base(CodexStatus.OperationFailed, failure.Message) => Failure = failure;
}

/// <summary>The loaded native library does not support the required stable ABI.</summary>
public sealed class CodexAbiException : CodexException
{
    /// <summary>The encoded native ABI version that was loaded.</summary>
    public uint ActualVersion { get; }

    internal CodexAbiException(uint actualVersion)
        : base(CodexStatus.UnsupportedAbi, $"The loaded Codex Agent C SDK ABI 0x{actualVersion:X8} is incompatible with ABI 1.13.0.")
        => ActualVersion = actualVersion;
}
