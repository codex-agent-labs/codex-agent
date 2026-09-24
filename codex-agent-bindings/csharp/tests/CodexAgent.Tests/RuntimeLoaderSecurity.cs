using CodexAgent;
using CodexAgent.Interop;
using System.Diagnostics;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.Json.Nodes;

internal static class RuntimeLoaderSecurity
{
    private static string Compatibility()
    {
        using var stream = typeof(CodexNativeLibrary).Assembly
            .GetManifestResourceStream("CodexAgent.sdk-compatibility.json")
            ?? throw new InvalidOperationException("test SDK compatibility resource missing");
        using var reader = new StreamReader(stream);
        return reader.ReadToEnd();
    }

    private static string Target => CodexNativeLibrary.RuntimeIdentifier switch
    {
        "osx-arm64" => "macos-arm64",
        "osx-x64" => "macos-x64",
        "linux-arm64" => "linux-arm64",
        "linux-x64" => "linux-x64",
        "win-x64" => "windows-x64",
        _ => throw new PlatformNotSupportedException(),
    };

    private static string DifferentDigest(string digest) =>
        "sha256:" + (digest[7] == '0' ? "1" : "0") + digest[8..];

    private static string NativeName(string suffix = "") => OperatingSystem.IsWindows()
        ? "codex_agent" + suffix + ".dll"
        : "libcodex_agent" + suffix + (OperatingSystem.IsMacOS() ? ".dylib" : ".so");

    private static JsonObject Identity(string target = "macos-arm64")
    {
        var compatibility = JsonNode.Parse(Compatibility())!;
        var defaultRuntime = Version.Parse(compatibility["runtime"]!["defaultRuntimeVersion"]!.GetValue<string>());
        var variant = compatibility["runtime"]!["embeddedVariants"]!.AsArray()
            .Single(value => value!["target"]!.GetValue<string>() == target)!;
        return new JsonObject
        {
            ["appServerVersion"] = "0.149.0",
            ["buildInputDigest"] = "sha256:" + new string('e', 64),
            ["cAbiVersion"] = "1.13.0",
            ["componentId"] = variant["componentId"]!.GetValue<string>(),
            ["contractComponentDigest"] = "sha256:" + new string('f', 64),
            ["contractDigest"] = compatibility["contract"]!["digest"]!.GetValue<string>(),
            ["runtimeCompatibilityVersion"] = new Version(defaultRuntime.Major, defaultRuntime.Minor, 0).ToString(3),
            ["schemaVersion"] = 1,
            ["target"] = target,
        };
    }

    internal static void Verify()
    {
        var compatibility = Compatibility();
        NativeLibraryLoader.ValidateCompatibilityForTests(compatibility);
        NativeLibraryLoader.ValidateIdentityForTests(compatibility, Identity().ToJsonString(), "macos-arm64", true);

        if (NativeLibraryLoader.CheckedIdentitySize(CodexStatus.BufferTooSmall, 2) != 2 ||
            NativeLibraryLoader.CheckedIdentitySize(CodexStatus.BufferTooSmall, 65536) != 65536)
            throw new InvalidOperationException("valid Runtime identity size was rejected");
        Reject<InvalidDataException>(() => NativeLibraryLoader.CheckedIdentitySize(CodexStatus.Ok, 2));
        Reject<InvalidDataException>(() => NativeLibraryLoader.CheckedIdentitySize(CodexStatus.BufferTooSmall, 1));
        Reject<InvalidDataException>(() => NativeLibraryLoader.CheckedIdentitySize(CodexStatus.BufferTooSmall, 65537));

        var external = Identity();
        external["componentId"] = DifferentDigest(external["componentId"]!.GetValue<string>());
        NativeLibraryLoader.ValidateIdentityForTests(compatibility, external.ToJsonString(), "macos-arm64", false);
        Reject<InvalidDataException>(() => NativeLibraryLoader.ValidateIdentityForTests(
            compatibility, external.ToJsonString(), "macos-arm64", true));

        foreach (var mutation in new Action<JsonObject>[]
        {
            value => value.Remove("schemaVersion"),
            value => value["schemaVersion"] = true,
            value => value["cAbiVersion"] = "1.12.0",
            value => value["cAbiVersion"] = "1.0.0",
            value => value["cAbiVersion"] = "2.13.0",
            value => value["contractDigest"] = DifferentDigest(value["contractDigest"]!.GetValue<string>()),
            value => value["target"] = "linux-arm64",
            value =>
            {
                var current = Version.Parse(value["runtimeCompatibilityVersion"]!.GetValue<string>());
                value["runtimeCompatibilityVersion"] = new Version(current.Major, current.Minor + 1, 0).ToString(3);
            },
        })
        {
            var value = Identity();
            mutation(value);
            Reject<InvalidDataException>(() => NativeLibraryLoader.ValidateIdentityForTests(
                compatibility, value.ToJsonString(), "macos-arm64", false));
        }

        Reject<InvalidDataException>(() => NativeLibraryLoader.ValidateIdentityForTests(
            compatibility, Identity().ToJsonString(new JsonSerializerOptions { WriteIndented = true }),
            "macos-arm64", false));
        Reject<InvalidDataException>(() => NativeLibraryLoader.ValidateCompatibilityForTests(
            JsonNode.Parse(compatibility)!.ToJsonString(new JsonSerializerOptions { WriteIndented = true }) + "\n"));
        foreach (var field in new[] { "requiredIdentitySchema", "requiredAbiMajor", "minimumAbiMinor" })
        {
            var booleanInteger = JsonNode.Parse(compatibility)!.AsObject();
            booleanInteger["runtime"]![field] = true;
            Reject<InvalidDataException>(() => NativeLibraryLoader.ValidateCompatibilityForTests(booleanInteger.ToJsonString() + "\n"));
        }

        foreach (var mutation in new Action<JsonObject>[]
        {
            value => value["contract"]!["digest"] = DifferentDigest(value["contract"]!["digest"]!.GetValue<string>()),
            value =>
            {
                var current = Version.Parse(value["runtime"]!["defaultRuntimeVersion"]!.GetValue<string>());
                value["runtime"]!["defaultRuntimeVersion"] = new Version(current.Major, current.Minor + 1, 0).ToString(3);
            },
            value => value["runtime"]!["embeddedVariants"]![1]!["componentId"] =
                value["runtime"]!["embeddedVariants"]![0]!["componentId"]!.GetValue<string>(),
            value => value["runtime"]!["embeddedVariants"]![1]!["manifestSha256"] =
                value["runtime"]!["embeddedVariants"]![0]!["manifestSha256"]!.GetValue<string>(),
            value => value["platformRuntime"]!["android"]!["desktopRuntimeApplicable"] = true,
        })
        {
            var value = JsonNode.Parse(compatibility)!.AsObject();
            mutation(value);
            Reject<InvalidDataException>(() => NativeLibraryLoader.ValidateCompatibilityForTests(value.ToJsonString() + "\n"));
        }

        VerifyPathsAndSnapshot();
        VerifyInvalidNativeLibraries(compatibility);
        VerifyChildEmbeddedLoad(compatibility);
        Console.WriteLine("CodexAgent C# Runtime loader security tests passed.");
    }

    private static void VerifyPathsAndSnapshot()
    {
        Reject<InvalidDataException>(() => NativeLibraryLoader.ValidateCompatibilityResourceForTests(
            typeof(RuntimeLoaderSecurity).Assembly));
        Reject<ArgumentException>(() => NativeLibraryLoader.ValidateExplicitPathForTests("codex_agent"));
        Reject<ArgumentException>(() => NativeLibraryLoader.ValidateExplicitPathForTests(""));
        var root = Path.Combine(AppContext.BaseDirectory, "runtime-loader-security");
        if (Directory.Exists(root)) Directory.Delete(root, true);
        Directory.CreateDirectory(root);
        try
        {
            var systemDirectory = Directory.CreateDirectory(Path.Combine(root, "system"));
            var packageDirectory = Directory.CreateDirectory(Path.Combine(root, "package"));
            var systemCandidateName = OperatingSystem.IsWindows()
                ? "codex_agent.dll"
                : OperatingSystem.IsMacOS() ? "libcodex_agent.dylib" : "libcodex_agent.so";
            File.WriteAllText(Path.Combine(systemDirectory.FullName, systemCandidateName), "arbitrary system Runtime");
            var previousPath = Environment.GetEnvironmentVariable("PATH");
            try
            {
                Environment.SetEnvironmentVariable("PATH", systemDirectory.FullName);
                Reject<DllNotFoundException>(() => NativeLibraryLoader.FindEmbeddedLibraryForTests(
                    packageDirectory.FullName));
            }
            finally
            {
                Environment.SetEnvironmentVariable("PATH", previousPath);
            }

            var source = Path.Combine(root, "runtime-library");
            File.WriteAllText(source, "verified Runtime");
            NativeLibraryLoader.ValidateExplicitPathForTests(source);
            var expected = "sha256:" + Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(source))).ToLowerInvariant();
            var wrongDigest = JsonNode.Parse(Compatibility())!.AsObject();
            wrongDigest["runtime"]!["embeddedVariants"]!.AsArray()
                .Single(value => value!["target"]!.GetValue<string>() == Target)!["runtimeLibrarySha256"] =
                "sha256:" + new string('9', 64);
            Reject<InvalidDataException>(() => NativeLibraryLoader.LoadEmbeddedForTests(
                source,
                wrongDigest.ToJsonString(new JsonSerializerOptions
                {
                    Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
                }) + "\n",
                Target,
                Path.Combine(root, "rejected-snapshots")));
            var snapshot = NativeLibraryLoader.SnapshotForTests(source, expected);
            try
            {
                var replacement = Path.Combine(root, "replacement");
                File.WriteAllText(replacement, "swapped Runtime");
                File.Move(replacement, source, true);
                if (File.ReadAllText(snapshot) != "verified Runtime")
                    throw new InvalidOperationException("private Runtime snapshot changed after source swap");
                Reject<InvalidDataException>(() => NativeLibraryLoader.SnapshotForTests(source, expected));
            }
            finally
            {
                Directory.Delete(Path.GetDirectoryName(snapshot)!, true);
            }

            var finalLink = Path.Combine(root, "final-link");
            File.CreateSymbolicLink(finalLink, source);
            Reject<IOException>(() => NativeLibraryLoader.ValidateExplicitPathForTests(finalLink));
            var realParent = Directory.CreateDirectory(Path.Combine(root, "real-parent"));
            var nested = Path.Combine(realParent.FullName, "runtime-library");
            File.WriteAllText(nested, "runtime");
            var linkedParent = Path.Combine(root, "linked-parent");
            Directory.CreateSymbolicLink(linkedParent, realParent.FullName);
            Reject<IOException>(() => NativeLibraryLoader.ValidateExplicitPathForTests(
                Path.Combine(linkedParent, "runtime-library")));
        }
        finally
        {
            Directory.Delete(root, true);
        }
    }

    private static void VerifyInvalidNativeLibraries(string compatibility)
    {
        var valid = Path.Combine(AppContext.BaseDirectory, NativeName());
        var identityVariable = "CODEX_AGENT_TEST_IDENTITY_" + Target.Replace('-', '_').ToUpperInvariant();
        var root = Path.Combine(AppContext.BaseDirectory, "runtime-loader-native-child");
        if (Directory.Exists(root)) Directory.Delete(root, true);
        Directory.CreateDirectory(root);
        try
        {
            var compatibilityPath = Path.Combine(root, "sdk-compatibility.json");
            File.WriteAllText(compatibilityPath, compatibility, new UTF8Encoding(false));
            var external = Identity(Target);
            external["componentId"] = DifferentDigest(external["componentId"]!.GetValue<string>());
            RunNativeChild(valid, compatibilityPath, identityVariable, external, "accept");
            external["runtimeCompatibilityVersion"] = "0.8.5";
            RunNativeChild(valid, compatibilityPath, identityVariable, external, "accept");

            foreach (var mutation in new Action<JsonObject>[]
            {
                value => value["cAbiVersion"] = "1.12.0",
                value => value["contractDigest"] = DifferentDigest(value["contractDigest"]!.GetValue<string>()),
                value => value["target"] = "unsupported-target",
                value => value["runtimeCompatibilityVersion"] = "0.0.0",
                value => value["runtimeCompatibilityVersion"] = "0.9.0",
            })
            {
                var incompatible = Identity(Target);
                mutation(incompatible);
                RunNativeChild(valid, compatibilityPath, identityVariable, incompatible, "InvalidDataException");
            }
        }
        finally
        {
            Directory.Delete(root, true);
        }

        var incompatibleOverride = JsonNode.Parse(compatibility)!.AsObject();
        var incompatibleDigest = DifferentDigest(incompatibleOverride["contract"]!["digest"]!.GetValue<string>());
        incompatibleOverride["contract"]!["digest"] = incompatibleDigest;
        incompatibleOverride["runtime"]!["requiredContractDigest"] = incompatibleDigest;
        Reject<InvalidDataException>(() => NativeLibraryLoader.ValidateNativePathForTests(
            valid,
            incompatibleOverride.ToJsonString(new JsonSerializerOptions
            {
                Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
            }) + "\n",
            Target));

        var missing = Path.Combine(AppContext.BaseDirectory, NativeName("_missing_identity"));
        Reject<EntryPointNotFoundException>(() => NativeLibraryLoader.ValidateNativePathForTests(
            missing, compatibility, Target));
        var oldAbi = Path.Combine(AppContext.BaseDirectory, NativeName("_abi_1_12"));
        Reject<CodexAbiException>(() => NativeLibraryLoader.ValidateNativePathForTests(
            oldAbi, compatibility, Target));
        var mismatch = Path.Combine(AppContext.BaseDirectory, NativeName("_abi_mismatch"));
        Reject<InvalidDataException>(() => NativeLibraryLoader.ValidateNativePathForTests(
            mismatch, compatibility, Target));
    }

    internal static void VerifyNativeChild(string library, string compatibilityPath, string target, string expected)
    {
        try
        {
            NativeLibraryLoader.ValidateNativePathForTests(library, File.ReadAllText(compatibilityPath), target);
            if (expected != "accept") throw new InvalidOperationException("incompatible native Runtime was accepted");
        }
        catch (InvalidDataException) when (expected == "InvalidDataException")
        {
            return;
        }
        if (expected != "accept" && expected != "InvalidDataException")
            throw new InvalidOperationException("unknown native Runtime child expectation");
    }

    private static void RunNativeChild(
        string library, string compatibilityPath, string identityVariable, JsonObject identity, string expected)
    {
        var process = new ProcessStartInfo
        {
            FileName = Environment.ProcessPath ?? throw new InvalidOperationException("test process path unavailable"),
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };
        if (Path.GetFileNameWithoutExtension(process.FileName).Equals("dotnet", StringComparison.OrdinalIgnoreCase))
            process.ArgumentList.Add(Assembly.GetEntryAssembly()!.Location);
        foreach (var argument in new[] { "--runtime-loader-native-child", library, compatibilityPath, Target, expected })
            process.ArgumentList.Add(argument);
        process.Environment[identityVariable] = identity.ToJsonString();
        using var child = Process.Start(process) ?? throw new InvalidOperationException("native Runtime child did not start");
        var output = child.StandardOutput.ReadToEnd();
        var error = child.StandardError.ReadToEnd();
        child.WaitForExit();
        if (child.ExitCode != 0)
            throw new InvalidOperationException($"native Runtime child failed ({child.ExitCode}): {output}{error}");
    }

    private static void VerifyChildEmbeddedLoad(string compatibility)
    {
        var root = Path.Combine(AppContext.BaseDirectory, "runtime-loader-child");
        if (Directory.Exists(root)) Directory.Delete(root, true);
        var snapshotRoot = Directory.CreateDirectory(Path.Combine(root, "snapshots")).FullName;
        try
        {
            var library = Path.Combine(AppContext.BaseDirectory, NativeName());
            var digest = "sha256:" + Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(library))).ToLowerInvariant();
            var document = JsonNode.Parse(compatibility)!.AsObject();
            var variants = document["runtime"]!["embeddedVariants"]!.AsArray();
            variants.Single(value => value!["target"]!.GetValue<string>() == Target)!["runtimeLibrarySha256"] = digest;
            var options = new JsonSerializerOptions { Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping };
            var compatibilityPath = Path.Combine(root, "sdk-compatibility.json");
            File.WriteAllText(compatibilityPath, document.ToJsonString(options) + "\n", new UTF8Encoding(false));

            var before = Directory.EnumerateDirectories(snapshotRoot, "codex-agent-runtime-*")
                .Select(Path.GetFileName).ToHashSet(StringComparer.Ordinal);
            var process = new ProcessStartInfo
            {
                FileName = Environment.ProcessPath ?? throw new InvalidOperationException("test process path unavailable"),
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
            };
            if (Path.GetFileNameWithoutExtension(process.FileName).Equals("dotnet", StringComparison.OrdinalIgnoreCase))
                process.ArgumentList.Add(Assembly.GetEntryAssembly()!.Location);
            foreach (var argument in new[]
            {
                "--runtime-loader-embedded-child", library, compatibilityPath, Target, snapshotRoot,
            }) process.ArgumentList.Add(argument);
            using var child = Process.Start(process) ?? throw new InvalidOperationException("child process did not start");
            var output = child.StandardOutput.ReadToEnd();
            var error = child.StandardError.ReadToEnd();
            child.WaitForExit();
            if (child.ExitCode != 0 || !output.Contains("embedded Runtime child load passed", StringComparison.Ordinal))
                throw new InvalidOperationException($"embedded Runtime child failed ({child.ExitCode}): {output}{error}");
            var after = Directory.EnumerateDirectories(snapshotRoot, "codex-agent-runtime-*")
                .Select(Path.GetFileName).ToHashSet(StringComparer.Ordinal);
            if (!before.SetEquals(after))
                throw new InvalidOperationException("embedded Runtime child leaked a private snapshot directory");
        }
        finally
        {
            Directory.Delete(root, true);
        }
    }

    internal static void VerifyNative()
    {
        if (NativeMethods.GetAbiVersion() != NativeMethods.AbiVersion)
            throw new InvalidOperationException("authenticated native ABI version mismatch");
        Console.WriteLine("CodexAgent C# authenticated native loader test passed.");
    }

    private static void Reject<TException>(Action action) where TException : Exception
    {
        try
        {
            action();
            throw new InvalidOperationException("invalid Runtime input was accepted");
        }
        catch (TException)
        {
        }
    }
}
