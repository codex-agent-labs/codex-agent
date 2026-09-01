using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Encodings.Web;
using System.Text.Json;

namespace CodexAgent.Interop;

internal static class NativeLibraryLoader
{
    private const string CompatibilityResource = "CodexAgent.sdk-compatibility.json";
    private static readonly JsonSerializerOptions CanonicalJson = new()
    {
        Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
    };
    private static readonly object Gate = new();
    private static string? configuredPath;
    private static nint loadedHandle;
    private static Snapshot? windowsSnapshot;
    private static bool processExitRegistered;

    private sealed record Variant(string ComponentId, string RuntimeLibrarySha256);
    private sealed record Snapshot(string Path, DirectoryInfo Owner)
    {
        internal void Delete()
        {
            if (Owner.Exists) Owner.Delete(true);
        }
    }
    private sealed record Compatibility(
        Version ReleaseMinimum,
        Version ReleaseMaximum,
        Version CompatibilityMinimum,
        Version CompatibilityMaximum,
        int IdentitySchema,
        string ContractDigest,
        int AbiMajor,
        int AbiMinor,
        IReadOnlyDictionary<string, Variant> Variants);

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

    private static string RuntimeTarget => RuntimeIdentifier switch
    {
        "osx-arm64" => "macos-arm64",
        "osx-x64" => "macos-x64",
        "linux-arm64" => "linux-arm64",
        "linux-x64" => "linux-x64",
        "win-x64" => "windows-x64",
        _ => throw new PlatformNotSupportedException(),
    };

    internal static void Configure(string path)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(path);
        var fullPath = ValidateAbsoluteRegularPath(path, "configured Codex Agent C SDK library");

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

            var compatibility = ReadCompatibility();
            var external = configuredPath is not null;
            var path = configuredPath ?? FindEmbeddedLibrary();
            return LoadAuthenticated(path, compatibility, RuntimeTarget, !external, null);
        }
    }

    private static string FindEmbeddedLibrary()
    {
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
        var candidate = candidates.FirstOrDefault(File.Exists) ?? throw new DllNotFoundException(
            $"Could not find the Codex Agent C SDK library for {RuntimeIdentifier}. " +
            $"Expected {fileName} beside the application or in its NuGet runtime assets.");
        return ValidateAbsoluteRegularPath(candidate, "embedded Codex Agent Runtime library");
    }

    private static Compatibility ReadCompatibility()
    {
        using var stream = typeof(NativeLibraryLoader).Assembly.GetManifestResourceStream(CompatibilityResource)
            ?? throw new InvalidDataException("Codex Agent SDK compatibility declaration is missing.");
        using var bytes = new MemoryStream();
        stream.CopyTo(bytes);
        return ParseCompatibility(new UTF8Encoding(false, true).GetString(bytes.ToArray()));
    }

    internal static void ValidateCompatibilityForTests(string json) => _ = ParseCompatibility(json);

    internal static void ValidateExplicitPathForTests(string path) =>
        _ = ValidateAbsoluteRegularPath(path, "configured Codex Agent C SDK library");

    internal static void ValidateIdentityForTests(
        string compatibilityJson,
        string identityJson,
        string target,
        bool embedded)
    {
        using var identity = ParseDocument(identityJson, "Runtime identity");
        RequireCanonical(identity.RootElement, identityJson, "Runtime identity");
        ValidateIdentity(ParseCompatibility(compatibilityJson), identity.RootElement, target, embedded);
    }

    internal static void VerifyDigestForTests(string path, string expected) => VerifyDigest(path, expected);

    internal static string SnapshotForTests(string path, string expected) =>
        SnapshotEmbeddedLibrary(path, expected, null).Path;

    internal static void LoadEmbeddedForTests(
        string path,
        string compatibilityJson,
        string target,
        string snapshotRoot)
    {
        lock (Gate)
        {
            if (loadedHandle != 0) throw new InvalidOperationException("The test Runtime library is already loaded.");
            _ = LoadAuthenticated(path, ParseCompatibility(compatibilityJson), target, true, snapshotRoot);
        }
    }

    internal static void ValidateNativePathForTests(string path, string compatibilityJson, string target)
    {
        var handle = NativeLibrary.Load(ValidateAbsoluteRegularPath(path, "test Runtime library"));
        try { ValidateLoadedLibrary(handle, ParseCompatibility(compatibilityJson), target, false); }
        finally { NativeLibrary.Free(handle); }
    }

    private static nint LoadAuthenticated(
        string path,
        Compatibility compatibility,
        string target,
        bool embedded,
        string? snapshotRoot)
    {
        Snapshot? snapshot = null;
        nint handle = 0;
        try
        {
            if (embedded)
                snapshot = SnapshotEmbeddedLibrary(path, compatibility.Variants[target].RuntimeLibrarySha256, snapshotRoot);
            handle = NativeLibrary.Load(snapshot?.Path ?? path);
            ValidateLoadedLibrary(handle, compatibility, target, embedded);
            loadedHandle = handle;
            if (snapshot is not null) CompleteSnapshotOwnership(snapshot);
            return handle;
        }
        catch
        {
            loadedHandle = 0;
            if (handle != 0) NativeLibrary.Free(handle);
            snapshot?.Delete();
            throw;
        }
    }

    private static Compatibility ParseCompatibility(string json)
    {
        using var document = ParseDocument(json, "SDK compatibility declaration");
        var root = document.RootElement;
        RequireObject(root, ["schemaVersion", "sdkVersion", "contract", "runtime", "platformRuntime"], "SDK compatibility declaration");
        if (Integer(root, "schemaVersion") != 1) throw new InvalidDataException("Unsupported SDK compatibility schema.");
        _ = Semver(String(root, "sdkVersion"), "SDK version");

        var contract = root.GetProperty("contract");
        RequireObject(contract, ["version", "digest"], "Contract compatibility");
        _ = Semver(String(contract, "version"), "Contract version");
        var contractDigest = Sha(String(contract, "digest"), "Contract digest");

        var runtime = root.GetProperty("runtime");
        RequireObject(runtime,
            ["compatibleReleaseRange", "compatibleRuntimeCompatibilityRange", "requiredIdentitySchema",
             "requiredContractDigest", "requiredAbiMajor", "minimumAbiMinor", "defaultRuntimeVersion",
             "defaultManifestSha256", "embeddedVariants"],
            "Runtime compatibility");
        var release = Range(String(runtime, "compatibleReleaseRange"), "Runtime release range");
        var compatible = Range(String(runtime, "compatibleRuntimeCompatibilityRange"), "Runtime compatibility range");
        var identitySchema = Integer(runtime, "requiredIdentitySchema");
        var abiMajor = Integer(runtime, "requiredAbiMajor");
        var abiMinor = Integer(runtime, "minimumAbiMinor");
        if (identitySchema != 1 || abiMajor != 1 || abiMinor < 0)
            throw new InvalidDataException("Unsupported Runtime identity or ABI policy.");
        if (Sha(String(runtime, "requiredContractDigest"), "required Contract digest") != contractDigest)
            throw new InvalidDataException("SDK compatibility Contract digest mismatch.");
        _ = Sha(String(runtime, "defaultManifestSha256"), "default Runtime manifest digest");
        var defaultRuntime = Semver(String(runtime, "defaultRuntimeVersion"), "default Runtime version");
        if (defaultRuntime < release.Minimum || defaultRuntime >= release.Maximum)
            throw new InvalidDataException("Default Runtime is outside its compatible range.");

        var expectedTargets = new[] { "linux-arm64", "linux-x64", "macos-arm64", "macos-x64", "windows-x64" };
        var variants = runtime.GetProperty("embeddedVariants");
        if (variants.ValueKind != JsonValueKind.Array || variants.GetArrayLength() != expectedTargets.Length)
            throw new InvalidDataException("SDK compatibility must contain exactly five Runtime targets.");
        var parsedVariants = new Dictionary<string, Variant>(StringComparer.Ordinal);
        var manifestDigests = new HashSet<string>(StringComparer.Ordinal);
        for (var index = 0; index < expectedTargets.Length; index++)
        {
            var variant = variants[index];
            RequireObject(variant, ["target", "componentId", "bundleSha256", "manifestSha256", "runtimeLibrarySha256"], "embedded Runtime variant");
            var target = String(variant, "target");
            if (target != expectedTargets[index]) throw new InvalidDataException("Embedded Runtime targets are not exact and sorted.");
            var component = Sha(String(variant, "componentId"), "Runtime component ID");
            _ = Sha(String(variant, "bundleSha256"), "Runtime bundle digest");
            var manifest = Sha(String(variant, "manifestSha256"), "Runtime manifest digest");
            var library = Sha(String(variant, "runtimeLibrarySha256"), "Runtime library digest");
            if (!parsedVariants.TryAdd(target, new Variant(component, library)) || !manifestDigests.Add(manifest))
                throw new InvalidDataException("Embedded Runtime identities must be unique.");
        }
        if (parsedVariants.Values.Select(value => value.ComponentId).Distinct(StringComparer.Ordinal).Count() != expectedTargets.Length)
            throw new InvalidDataException("Embedded Runtime component IDs must be unique.");

        var platform = root.GetProperty("platformRuntime");
        RequireObject(platform, ["android", "ios"], "platform Runtime compatibility");
        foreach (var name in new[] { "android", "ios" })
        {
            var value = platform.GetProperty(name);
            RequireObject(value, ["owner", "desktopRuntimeApplicable"], $"{name} Runtime compatibility");
            if (String(value, "owner") != "sdk" || Boolean(value, "desktopRuntimeApplicable"))
                throw new InvalidDataException($"Invalid {name} Runtime ownership.");
        }
        if (JsonSerializer.Serialize(root, CanonicalJson) + "\n" != json)
            throw new InvalidDataException("SDK compatibility declaration is not canonical JSON.");
        return new Compatibility(release.Minimum, release.Maximum, compatible.Minimum, compatible.Maximum,
            identitySchema, contractDigest, abiMajor, abiMinor, parsedVariants);
    }

    private static unsafe void ValidateLoadedLibrary(nint handle, Compatibility compatibility, string target, bool embedded)
    {
        var identityFunction = (delegate* unmanaged[Cdecl]<byte*, nuint*, CodexStatus>)
            NativeLibrary.GetExport(handle, "codex_agent_runtime_identity");
        nuint required = 0;
        if (identityFunction(null, &required) != CodexStatus.BufferTooSmall || required < 2)
            throw new InvalidDataException("Runtime identity size query failed.");
        var bytes = new byte[checked((int)required)];
        fixed (byte* buffer = bytes)
        {
            var capacity = required;
            if (identityFunction(buffer, &capacity) != CodexStatus.Ok || capacity != required)
                throw new InvalidDataException("Runtime identity read failed.");
        }
        if (bytes[^1] != 0 || bytes.AsSpan(0, bytes.Length - 1).Contains((byte)0))
            throw new InvalidDataException("Runtime identity is not a canonical NUL-terminated string.");
        var identityJson = new UTF8Encoding(false, true).GetString(bytes, 0, bytes.Length - 1);
        using var identity = ParseDocument(identityJson, "Runtime identity");
        RequireCanonical(identity.RootElement, identityJson, "Runtime identity");
        ValidateIdentity(compatibility, identity.RootElement, target, embedded);

        var abiVersion = (delegate* unmanaged[Cdecl]<uint>)NativeLibrary.GetExport(handle, "codex_agent_abi_version");
        var abiCompatible = (delegate* unmanaged[Cdecl]<uint, int>)NativeLibrary.GetExport(handle, "codex_agent_abi_is_compatible");
        var actual = abiVersion();
        var requested = checked((uint)((compatibility.AbiMajor << 24) | (compatibility.AbiMinor << 16)));
        if (abiCompatible(requested) != 1 || actual >> 24 != compatibility.AbiMajor || ((actual >> 16) & 0xff) < compatibility.AbiMinor)
            throw new CodexAbiException(actual);
        var declared = Semver(String(identity.RootElement, "cAbiVersion"), "Runtime identity ABI");
        var declaredEncoded = checked((uint)((declared.Major << 24) | (declared.Minor << 16) | declared.Build));
        if (actual != declaredEncoded) throw new InvalidDataException("Runtime identity ABI disagrees with the loaded library.");
    }

    private static void ValidateIdentity(Compatibility compatibility, JsonElement identity, string target, bool embedded)
    {
        RequireObject(identity,
            ["appServerVersion", "buildInputDigest", "cAbiVersion", "componentId", "contractComponentDigest",
             "contractDigest", "runtimeCompatibilityVersion", "schemaVersion", "target"],
            "Runtime identity");
        if (Integer(identity, "schemaVersion") != compatibility.IdentitySchema)
            throw new InvalidDataException("Runtime identity schema mismatch.");
        foreach (var name in new[] { "buildInputDigest", "componentId", "contractComponentDigest", "contractDigest" })
            _ = Sha(String(identity, name), $"Runtime identity {name}");
        if (String(identity, "target") != target) throw new InvalidDataException("Runtime identity target mismatch.");
        if (String(identity, "contractDigest") != compatibility.ContractDigest)
            throw new InvalidDataException("Runtime identity Contract mismatch.");
        var abi = Semver(String(identity, "cAbiVersion"), "Runtime identity ABI");
        if (abi.Major != compatibility.AbiMajor || abi.Minor < compatibility.AbiMinor)
            throw new InvalidDataException("Runtime identity ABI is incompatible.");
        var runtimeCompatibility = Semver(String(identity, "runtimeCompatibilityVersion"), "Runtime compatibility version");
        if (runtimeCompatibility < compatibility.CompatibilityMinimum || runtimeCompatibility >= compatibility.CompatibilityMaximum)
            throw new InvalidDataException("Runtime compatibility version is unsupported.");
        _ = Semver(String(identity, "appServerVersion"), "Runtime app-server version");
        if (embedded && String(identity, "componentId") != compatibility.Variants[target].ComponentId)
            throw new InvalidDataException("Embedded Runtime component mismatch.");
    }

    private static void VerifyDigest(string path, string expected)
    {
        using var stream = File.OpenRead(path);
        var actual = "sha256:" + Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant();
        if (actual != expected) throw new InvalidDataException("Embedded Codex Agent Runtime library digest mismatch.");
    }

    private static Snapshot SnapshotEmbeddedLibrary(string path, string expected, string? snapshotRoot)
    {
        path = ValidateAbsoluteRegularPath(path, "embedded Codex Agent Runtime library");
        var directory = snapshotRoot is null
            ? Directory.CreateTempSubdirectory("codex-agent-runtime-")
            : Directory.CreateDirectory(Path.Combine(snapshotRoot, $"codex-agent-runtime-{Guid.NewGuid():N}"));
        if (!OperatingSystem.IsWindows())
            File.SetUnixFileMode(directory.FullName, UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute);
        var snapshot = Path.Combine(directory.FullName, Path.GetFileName(path));
        try
        {
            using (var input = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read, 1024 * 1024, FileOptions.SequentialScan))
            using (var output = new FileStream(snapshot, FileMode.CreateNew, FileAccess.Write, FileShare.None, 1024 * 1024, FileOptions.WriteThrough))
            {
                input.CopyTo(output);
                output.Flush(true);
            }
            VerifyDigest(snapshot, expected);
            if (!OperatingSystem.IsWindows()) File.SetUnixFileMode(snapshot, UnixFileMode.UserRead);
            return new Snapshot(snapshot, directory);
        }
        catch
        {
            directory.Delete(true);
            throw;
        }
    }

    private static void CompleteSnapshotOwnership(Snapshot snapshot)
    {
        if (!OperatingSystem.IsWindows())
        {
            snapshot.Delete();
            return;
        }
        windowsSnapshot = snapshot;
        if (processExitRegistered) return;
        AppDomain.CurrentDomain.ProcessExit += (_, _) =>
        {
            var handle = Interlocked.Exchange(ref loadedHandle, 0);
            if (handle != 0) NativeLibrary.Free(handle);
            windowsSnapshot?.Delete();
            windowsSnapshot = null;
        };
        processExitRegistered = true;
    }

    private static string ValidateAbsoluteRegularPath(string path, string description)
    {
        if (!Path.IsPathFullyQualified(path)) throw new ArgumentException($"The {description} path must be absolute.", nameof(path));
        var fullPath = Path.GetFullPath(path);
        if (!File.Exists(fullPath)) throw new FileNotFoundException($"The {description} does not exist.", fullPath);
        for (FileSystemInfo? item = new FileInfo(fullPath); item is not null; item = item switch
        {
            FileInfo file => file.Directory,
            DirectoryInfo directory => directory.Parent,
            _ => null,
        })
        {
            item.Refresh();
            if ((item.Attributes & FileAttributes.ReparsePoint) != 0)
                throw new IOException($"The {description} path must not contain symlinks or reparse points: {fullPath}");
        }
        if ((File.GetAttributes(fullPath) & FileAttributes.Directory) != 0)
            throw new FileNotFoundException($"The {description} is not a regular file.", fullPath);
        return fullPath;
    }

    private static JsonDocument ParseDocument(string json, string description)
    {
        try { return JsonDocument.Parse(json); }
        catch (JsonException error) { throw new InvalidDataException($"Invalid {description}.", error); }
    }

    private static void RequireObject(JsonElement value, string[] keys, string description)
    {
        if (value.ValueKind != JsonValueKind.Object) throw new InvalidDataException($"Invalid {description}.");
        var actual = value.EnumerateObject().Select(property => property.Name).ToArray();
        if (actual.Length != keys.Length || actual.Distinct(StringComparer.Ordinal).Count() != actual.Length ||
            !actual.SequenceEqual(actual.Order(StringComparer.Ordinal), StringComparer.Ordinal) ||
            !actual.ToHashSet(StringComparer.Ordinal).SetEquals(keys))
            throw new InvalidDataException($"Invalid {description}: unexpected fields.");
    }

    private static string String(JsonElement owner, string name) =>
        owner.GetProperty(name).ValueKind == JsonValueKind.String
            ? owner.GetProperty(name).GetString()!
            : throw new InvalidDataException($"Invalid {name}.");

    private static int Integer(JsonElement owner, string name) =>
        owner.GetProperty(name).ValueKind == JsonValueKind.Number && owner.GetProperty(name).TryGetInt32(out var value)
            ? value
            : throw new InvalidDataException($"Invalid {name}.");

    private static bool Boolean(JsonElement owner, string name) => owner.GetProperty(name).ValueKind switch
    {
        JsonValueKind.True => true,
        JsonValueKind.False => false,
        _ => throw new InvalidDataException($"Invalid {name}."),
    };

    private static Version Semver(string value, string description)
    {
        var parts = value.Split('.');
        if (parts.Length != 3 || parts.Any(part => part.Length == 0 || part.Any(character => character is < '0' or > '9') ||
                (part.Length > 1 && part[0] == '0')) || !Version.TryParse(value, out var version))
            throw new InvalidDataException($"Invalid {description}.");
        return version;
    }

    private static (Version Minimum, Version Maximum) Range(string value, string description)
    {
        var parts = value.Split(' ');
        if (parts.Length != 2 || !parts[0].StartsWith(">=", StringComparison.Ordinal) || !parts[1].StartsWith('<'))
            throw new InvalidDataException($"Invalid {description}.");
        var minimum = Semver(parts[0][2..], description);
        var maximum = Semver(parts[1][1..], description);
        if (minimum >= maximum) throw new InvalidDataException($"Invalid {description}.");
        return (minimum, maximum);
    }

    private static string Sha(string value, string description)
    {
        if (value.Length != 71 || !value.StartsWith("sha256:", StringComparison.Ordinal) ||
            value.AsSpan(7).ContainsAnyExcept("0123456789abcdef"))
            throw new InvalidDataException($"Invalid {description}.");
        return value;
    }

    private static void RequireCanonical(JsonElement value, string json, string description)
    {
        if (JsonSerializer.Serialize(value, CanonicalJson) != json)
            throw new InvalidDataException($"{description} is not canonical JSON.");
    }
}
