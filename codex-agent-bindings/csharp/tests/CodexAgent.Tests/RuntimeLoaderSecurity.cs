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
        using (var exact = new MemoryStream(new byte[4096]))
            if (NativeLibraryLoader.ReadPackagedResourceForTests(exact, 4096).Length != 4096)
                throw new InvalidOperationException("A valid packaged resource was rejected.");
        using (var oversized = new MemoryStream(new byte[4097]))
            Reject<InvalidDataException>(() => NativeLibraryLoader.ReadPackagedResourceForTests(oversized, 4096));
        foreach (var json in new[] { "{\"schemaVersion\":1.0}\n", "{\"nested\":{\"value\":1e0}}\n" })
            Reject<InvalidDataException>(() => NativeLibraryLoader.ValidateEvidenceJsonForTests(json));
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
            value => value["cAbiVersion"] = "1.269.0",
            value => value["cAbiVersion"] = "1.13.65536",
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
        var oversizedAbiMinor = JsonNode.Parse(compatibility)!.AsObject();
        oversizedAbiMinor["runtime"]!["minimumAbiMinor"] = 256;
        Reject<InvalidDataException>(() => NativeLibraryLoader.ValidateCompatibilityForTests(oversizedAbiMinor.ToJsonString() + "\n"));

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
        VerifySignedExternalLoad(compatibility);
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
            var readEvidence = typeof(NativeLibraryLoader).GetMethod(
                "ReadEvidence", BindingFlags.Static | BindingFlags.NonPublic)
                ?? throw new InvalidOperationException("Runtime evidence reader is unavailable");
            var bounded = Path.Combine(root, "bounded-evidence");
            File.WriteAllText(bounded, "12345678");
            if (!((byte[])readEvidence.Invoke(null, [bounded, 8])!).SequenceEqual("12345678"u8.ToArray()))
                throw new InvalidOperationException("exact-limit Runtime evidence changed during reading");
            File.WriteAllText(bounded, "123456789");
            try
            {
                _ = readEvidence.Invoke(null, [bounded, 8]);
                throw new InvalidOperationException("oversized Runtime evidence was accepted");
            }
            catch (TargetInvocationException error) when (error.InnerException is InvalidDataException) { }
            NativeLibraryLoader.ValidateExplicitPathForTests(source);
            Reject<FileNotFoundException>(() => NativeLibraryLoader.RejectUnverifiedExternalForTests(
                source, Compatibility(), Target));
            var expected = "sha256:" + Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(source))).ToLowerInvariant();
            var oversized = Path.Combine(root, "oversized-runtime-library");
            using (var sparse = File.Create(oversized)) sparse.SetLength(1024L * 1024 * 1024 + 1);
            var oversizedSnapshots = Path.Combine(root, "oversized-snapshots");
            Reject<InvalidDataException>(() => NativeLibraryLoader.LoadEmbeddedForTests(
                oversized, Compatibility(), Target, oversizedSnapshots));
            if (Directory.EnumerateFileSystemEntries(oversizedSnapshots).Any())
                throw new InvalidOperationException("oversized Runtime snapshot was not removed");
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

    private static byte[] Canonical(JsonNode value)
    {
        static JsonNode? Sorted(JsonNode? node) => node switch
        {
            JsonObject value => new JsonObject(value.OrderBy(pair => pair.Key, StringComparer.Ordinal)
                .Select(pair => KeyValuePair.Create(pair.Key, Sorted(pair.Value)))),
            JsonArray value => new JsonArray(value.Select(Sorted).ToArray()),
            _ => node?.DeepClone(),
        };
        return Encoding.UTF8.GetBytes(Sorted(value)!.ToJsonString(new JsonSerializerOptions
        {
            Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
        }) + "\n");
    }

    private static void VerifySignedExternalLoad(string compatibility)
    {
        var root = Path.Combine(AppContext.BaseDirectory, "runtime-loader-signed");
        if (Directory.Exists(root)) Directory.Delete(root, true);
        Directory.CreateDirectory(root);
        try
        {
            var library = Path.Combine(root, NativeName());
            File.Copy(Path.Combine(AppContext.BaseDirectory, NativeName()), library);
            var evidence = Directory.CreateDirectory(library + ".evidence").FullName;
            Directory.CreateDirectory(Path.Combine(evidence, "keys"));

            static void Keygen(string path)
            {
                var verifier = OperatingSystem.IsWindows()
                    ? Path.Combine(Environment.SystemDirectory, "OpenSSH", "ssh-keygen.exe")
                    : "/usr/bin/ssh-keygen";
                var start = new ProcessStartInfo(verifier) { UseShellExecute = false,
                    RedirectStandardOutput = true, RedirectStandardError = true };
                foreach (var argument in new[] { "-q", "-t", "ed25519", "-N", "", "-f", path })
                    start.ArgumentList.Add(argument);
                using var process = Process.Start(start) ?? throw new InvalidOperationException("test keygen did not start");
                _ = process.StandardOutput.ReadToEnd();
                _ = process.StandardError.ReadToEnd();
                process.WaitForExit();
                if (process.ExitCode != 0) throw new InvalidOperationException("test keygen failed");
            }

            static byte[] PublicKey(string path)
            {
                var parts = File.ReadAllText(path + ".pub").Split(' ', StringSplitOptions.RemoveEmptyEntries);
                return Encoding.ASCII.GetBytes(parts[0] + " " + parts[1].TrimEnd('\n', '\r') + "\n");
            }

            static string Fingerprint(byte[] publicKey)
            {
                var blob = Convert.FromBase64String(Encoding.ASCII.GetString(publicKey).Split(' ')[1].Trim());
                return "sha256:" + Convert.ToHexString(SHA256.HashData(blob)).ToLowerInvariant();
            }

            static void Sign(string path, string privateKey, string namespaceName, string destination)
            {
                var verifier = OperatingSystem.IsWindows()
                    ? Path.Combine(Environment.SystemDirectory, "OpenSSH", "ssh-keygen.exe")
                    : "/usr/bin/ssh-keygen";
                var start = new ProcessStartInfo(verifier) { UseShellExecute = false,
                    RedirectStandardOutput = true, RedirectStandardError = true };
                foreach (var argument in new[] { "-Y", "sign", "-f", privateKey, "-n", namespaceName, path })
                    start.ArgumentList.Add(argument);
                using var process = Process.Start(start) ?? throw new InvalidOperationException("test signer did not start");
                _ = process.StandardOutput.ReadToEnd();
                _ = process.StandardError.ReadToEnd();
                process.WaitForExit();
                if (process.ExitCode != 0) throw new InvalidOperationException("test signer failed");
                File.Move(path + ".sig", destination);
            }

            var rootKey = Path.Combine(root, "root-key");
            var releaseKey = Path.Combine(root, "release-key");
            var fixtureKey = Path.Combine(AppContext.BaseDirectory, "fixtures", "sdk-runtime-root-test-only");
            File.Copy(fixtureKey, rootKey);
            File.Copy(fixtureKey + ".pub", rootKey + ".pub");
            if (!OperatingSystem.IsWindows())
                File.SetUnixFileMode(rootKey, UnixFileMode.UserRead | UnixFileMode.UserWrite);
            Keygen(releaseKey);
            var rootPublic = PublicKey(rootKey);
            var releasePublic = PublicKey(releaseKey);
            File.WriteAllBytes(Path.Combine(evidence, "keys", "release.pub"), releasePublic);
            var keyring = new JsonObject
            {
                ["schemaVersion"] = 1, ["namespace"] = "codex-agent-product-v1", ["algorithm"] = "ssh-ed25519",
                ["trustDomain"] = "release", ["activeKey"] = new JsonObject
                {
                    ["keyId"] = "release", ["fingerprint"] = Fingerprint(releasePublic),
                },
                ["retiredKeys"] = new JsonArray(),
            };
            var keyringBytes = Canonical(keyring);
            File.WriteAllBytes(Path.Combine(evidence, "release-keyring.json"), keyringBytes);
            var delegation = Path.Combine(evidence, "root-delegation.json");
            File.WriteAllBytes(delegation, Canonical(new JsonObject
            {
                ["schemaVersion"] = 1, ["kind"] = "sdk-runtime-release-keyring-delegation",
                ["scope"] = "desktop-runtime-library", ["rootFingerprint"] = Fingerprint(rootPublic),
                ["keyringSha256"] = "sha256:" + Convert.ToHexString(SHA256.HashData(keyringBytes)).ToLowerInvariant(),
            }));
            Sign(delegation, rootKey, "codex-agent-sdk-runtime-root-v1", Path.Combine(evidence, "root-delegation.sig"));
            var claim = Path.Combine(evidence, "runtime-library-authorization.json");
            File.WriteAllBytes(claim, Canonical(new JsonObject
            {
                ["schemaVersion"] = 1, ["kind"] = "desktop-runtime-library-authorization",
                ["runtimeVersion"] = "0.8.5", ["runtimeIdentity"] = Identity(Target),
                ["runtimeLibrarySha256"] = "sha256:" + Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(library))).ToLowerInvariant(),
                ["variantBundleSha256"] = "sha256:" + new string('1', 64),
                ["variantManifestSha256"] = "sha256:" + new string('2', 64),
                ["aggregateManifestSha256"] = "sha256:" + new string('3', 64),
                ["variantAttestationSha256"] = "sha256:" + new string('4', 64),
                ["aggregateAttestationSha256"] = "sha256:" + new string('5', 64),
                ["signing"] = new JsonObject
                {
                    ["algorithm"] = "ssh-ed25519", ["namespace"] = "codex-agent-product-v1",
                    ["trustDomain"] = "release", ["keyId"] = "release",
                    ["fingerprint"] = Fingerprint(releasePublic),
                },
            }));
            Sign(claim, releaseKey, "codex-agent-product-v1",
                Path.Combine(evidence, "runtime-library-authorization.sig"));
            var signature = Path.Combine(evidence, "runtime-library-authorization.sig");
            var original = File.ReadAllBytes(signature);
            File.WriteAllBytes(signature, [.. original, (byte)'x']);
            Reject<InvalidDataException>(() => NativeLibraryLoader.RejectUnverifiedExternalForTests(
                library, compatibility, Target));
            File.WriteAllBytes(signature, original);
            var cyclicEvidenceLink = Path.Combine(evidence, "cycle");
            Directory.CreateSymbolicLink(cyclicEvidenceLink, evidence);
            try
            {
                Reject<InvalidDataException>(() => NativeLibraryLoader.RejectUnverifiedExternalForTests(
                    library, compatibility, Target));
            }
            finally { Directory.Delete(cyclicEvidenceLink); }
            var originalClaim = File.ReadAllBytes(claim);
            foreach (var mutation in new Action<JsonObject>[]
            {
                value => value["runtimeVersion"] = "0.9.0",
                value => value["runtimeIdentity"]!["target"] = Target == "windows-x64" ? "linux-arm64" : "windows-x64",
            })
            {
                var incompatibleClaim = JsonNode.Parse(originalClaim)!.AsObject();
                mutation(incompatibleClaim);
                File.WriteAllBytes(claim, Canonical(incompatibleClaim));
                File.Delete(signature);
                Sign(claim, releaseKey, "codex-agent-product-v1", signature);
                try
                {
                    NativeLibraryLoader.RejectUnverifiedExternalForTests(library, compatibility, Target);
                    throw new InvalidOperationException("Incompatible signed Runtime authorization was accepted.");
                }
                catch (InvalidDataException error) when (error.Message == "Runtime authorization is incompatible with this SDK.")
                {
                }
            }
            File.WriteAllBytes(claim, originalClaim);
            File.WriteAllBytes(signature, original);
            var keyringPath = Path.Combine(evidence, "release-keyring.json");
            File.Move(keyringPath, keyringPath + ".held");
            try
            {
                Reject<FileNotFoundException>(() => NativeLibraryLoader.RejectUnverifiedExternalForTests(
                    library, compatibility, Target));
            }
            finally { File.Move(keyringPath + ".held", keyringPath); }
            var originalLibrary = File.ReadAllBytes(library);
            File.AppendAllText(library, "tampered Runtime");
            try
            {
                Reject<InvalidDataException>(() => NativeLibraryLoader.RejectUnverifiedExternalForTests(
                    library, compatibility, Target));
            }
            finally { File.WriteAllBytes(library, originalLibrary); }
            CodexNativeLibrary.Configure(library);
            VerifyNative();
        }
        finally { Directory.Delete(root, true); }
    }

    internal static void LoadFakeNativeForTests() => VerifySignedExternalLoad(Compatibility());

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
