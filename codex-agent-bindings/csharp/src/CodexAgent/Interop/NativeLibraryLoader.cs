using System.Reflection;
using System.Runtime.InteropServices;

namespace CodexAgent.Interop;

internal static class NativeLibraryLoader
{
    private static readonly object Gate = new();
    private static string? configuredPath;
    private static nint loadedHandle;

    internal static void Initialize() =>
        NativeLibrary.SetDllImportResolver(typeof(NativeLibraryLoader).Assembly, Resolve);

    internal static string RuntimeIdentifier => (RuntimeInformation.IsOSPlatform(OSPlatform.OSX),
        RuntimeInformation.IsOSPlatform(OSPlatform.Linux),
        RuntimeInformation.IsOSPlatform(OSPlatform.Windows),
        RuntimeInformation.ProcessArchitecture) switch
    {
        (true, _, _, Architecture.Arm64) => "osx-arm64",
        (true, _, _, Architecture.X64) => "osx-x64",
        (_, true, _, Architecture.Arm64) => "linux-arm64",
        (_, true, _, Architecture.X64) => "linux-x64",
        (_, _, true, Architecture.X64) => "win-x64",
        _ => throw new PlatformNotSupportedException(
            $"CodexAgent does not support {RuntimeInformation.OSDescription} {RuntimeInformation.ProcessArchitecture}."),
    };

    internal static void Configure(string path)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(path);
        var fullPath = Path.GetFullPath(path);
        if (!File.Exists(fullPath))
        {
            throw new FileNotFoundException("The configured Codex Agent C SDK library does not exist.", fullPath);
        }

        lock (Gate)
        {
            if (loadedHandle != 0)
            {
                throw new InvalidOperationException("The Codex Agent native library is already loaded.");
            }

            configuredPath = fullPath;
        }
    }

    private static nint Resolve(string libraryName, Assembly _assembly, DllImportSearchPath? _searchPath)
    {
        if (libraryName != NativeMethods.LibraryName)
        {
            return 0;
        }

        lock (Gate)
        {
            if (loadedHandle != 0)
            {
                return loadedHandle;
            }

            _ = RuntimeIdentifier;
            if (configuredPath is not null)
            {
                loadedHandle = NativeLibrary.Load(configuredPath);
                return loadedHandle;
            }

            var fileName = RuntimeInformation.IsOSPlatform(OSPlatform.Windows)
                ? "codex_agent.dll"
                : RuntimeInformation.IsOSPlatform(OSPlatform.OSX)
                    ? "libcodex_agent.dylib"
                    : "libcodex_agent.so";
            var candidates = new[]
            {
                Path.Combine(AppContext.BaseDirectory, fileName),
                Path.Combine(AppContext.BaseDirectory, "runtimes", RuntimeIdentifier, "native", fileName),
            };
            foreach (var candidate in candidates)
            {
                if (File.Exists(candidate))
                {
                    loadedHandle = NativeLibrary.Load(candidate);
                    return loadedHandle;
                }
            }

            throw new DllNotFoundException(
                $"Could not find the Codex Agent C SDK library for {RuntimeIdentifier}. " +
                $"Expected {fileName} beside the application or in its NuGet runtime assets.");
        }
    }
}
