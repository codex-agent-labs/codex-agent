using CodexAgent.Interop;

namespace CodexAgent;

/// <summary>A native handle that could not be safely released and was quarantined.</summary>
/// <param name="Resource">Managed native-handle type.</param>
/// <param name="Status">Final native release status after bounded retry.</param>
public sealed record CodexNativeCleanupIssue(string Resource, CodexStatus Status);

/// <summary>Controls the process-wide native C SDK selection before first use.</summary>
public static class CodexNativeLibrary
{
    /// <summary>The current process's supported NuGet runtime identifier.</summary>
    public static string RuntimeIdentifier => NativeLibraryLoader.RuntimeIdentifier;

    /// <summary>Uses an explicit C SDK library path. Call once before creating a host.</summary>
    public static void Configure(string path) => NativeLibraryLoader.Configure(path);

    /// <summary>Process-lifetime native handles quarantined after release could not safely complete.</summary>
    public static IReadOnlyList<CodexNativeCleanupIssue> CleanupIssues => NativeCleanup.Issues;
}
