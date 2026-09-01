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

    private static JsonObject Identity(string target = "macos-arm64") => new()
    {
        ["appServerVersion"] = "0.149.0",
        ["buildInputDigest"] = "sha256:" + new string('e', 64),
        ["cAbiVersion"] = "1.13.0",
        ["componentId"] = "sha256:" + new string(target switch
        {
            "linux-arm64" => '0', "linux-x64" => '1', "macos-arm64" => '2',
            "macos-x64" => '3', "windows-x64" => '4', _ => throw new ArgumentException("target"),
        }, 64),
        ["contractComponentDigest"] = "sha256:" + new string('f', 64),
        ["contractDigest"] = "sha256:" + new string('a', 64),
        ["runtimeCompatibilityVersion"] = "0.2.0",
        ["schemaVersion"] = 1,
        ["target"] = target,
    };

    internal static void Verify()
    {
        var compatibility = Compatibility();
        NativeLibraryLoader.ValidateCompatibilityForTests(compatibility);
        NativeLibraryLoader.ValidateIdentityForTests(compatibility, Identity().ToJsonString(), "macos-arm64", true);

        var external = Identity();
        external["componentId"] = "sha256:" + new string('9', 64);
        NativeLibraryLoader.ValidateIdentityForTests(compatibility, external.ToJsonString(), "macos-arm64", false);
        Reject<InvalidDataException>(() => NativeLibraryLoader.ValidateIdentityForTests(
            compatibility, external.ToJsonString(), "macos-arm64", true));

        foreach (var mutation in new Action<JsonObject>[]
        {
            value => value.Remove("schemaVersion"),
            value => value["schemaVersion"] = true,
            value => value["cAbiVersion"] = "1.12.0",
            value => value["cAbiVersion"] = "2.13.0",
            value => value["contractDigest"] = "sha256:" + new string('9', 64),
            value => value["target"] = "linux-arm64",
            value => value["runtimeCompatibilityVersion"] = "0.3.0",
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

        VerifyPathsAndSnapshot();
        VerifyInvalidNativeLibraries(compatibility);
        VerifyChildEmbeddedLoad(compatibility);
        Console.WriteLine("CodexAgent C# Runtime loader security tests passed.");
    }

    private static void VerifyPathsAndSnapshot()
    {
        Reject<ArgumentException>(() => NativeLibraryLoader.ValidateExplicitPathForTests("codex_agent"));
        Reject<ArgumentException>(() => NativeLibraryLoader.ValidateExplicitPathForTests(""));
        var root = Path.Combine(AppContext.BaseDirectory, "runtime-loader-security");
        if (Directory.Exists(root)) Directory.Delete(root, true);
        Directory.CreateDirectory(root);
        try
        {
            var source = Path.Combine(root, "runtime-library");
            File.WriteAllText(source, "verified Runtime");
            NativeLibraryLoader.ValidateExplicitPathForTests(source);
            var expected = "sha256:" + Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(source))).ToLowerInvariant();
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
        var extension = OperatingSystem.IsMacOS() ? ".dylib" : ".so";
        var missing = Path.Combine(AppContext.BaseDirectory, "libcodex_agent_missing_identity" + extension);
        Reject<EntryPointNotFoundException>(() => NativeLibraryLoader.ValidateNativePathForTests(
            missing, compatibility, Target));
        var mismatch = Path.Combine(AppContext.BaseDirectory, "libcodex_agent_abi_mismatch" + extension);
        Reject<InvalidDataException>(() => NativeLibraryLoader.ValidateNativePathForTests(
            mismatch, compatibility, Target));
    }

    private static void VerifyChildEmbeddedLoad(string compatibility)
    {
        var root = Path.Combine(AppContext.BaseDirectory, "runtime-loader-child");
        if (Directory.Exists(root)) Directory.Delete(root, true);
        var snapshotRoot = Directory.CreateDirectory(Path.Combine(root, "snapshots")).FullName;
        try
        {
            var extension = OperatingSystem.IsWindows() ? ".dll" : OperatingSystem.IsMacOS() ? ".dylib" : ".so";
            var library = Path.Combine(AppContext.BaseDirectory, "libcodex_agent" + extension);
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
