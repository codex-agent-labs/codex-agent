using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace CodexAgent.Interop;

internal static partial class NativeLibraryLoader
{
    private const string ProductNamespace = "codex-agent-product-v1";
    private const string RootNamespace = "codex-agent-sdk-runtime-root-v1";
    private static readonly UTF8Encoding StrictUtf8 = new(false, true);

    private static byte[] ReadPinnedRuntimeRoot()
    {
        using var source = typeof(NativeLibraryLoader).Assembly.GetManifestResourceStream("CodexAgent.sdk-runtime-root.pub")
            ?? throw new InvalidDataException("External Runtime requires release-attested evidence: SDK-pinned root is unavailable.");
        using var output = new MemoryStream();
        source.CopyTo(output);
        return output.ToArray();
    }

    private static byte[] ReadEvidence(string path, int limit = 1024 * 1024)
    {
        _ = ValidateAbsoluteRegularPath(path, "Runtime evidence");
        var file = new FileInfo(path);
        if (file.Length > limit) throw new InvalidDataException("Runtime evidence exceeds its size limit.");
        return File.ReadAllBytes(path);
    }

    private static JsonDocument EvidenceJson(byte[] raw, string description)
    {
        var value = StrictUtf8.GetString(raw);
        if (!value.EndsWith('\n')) throw new InvalidDataException($"{description} is not canonical JSON.");
        var document = ParseDocument(value[..^1], description);
        try
        {
            RequireIntegralJson(document.RootElement);
            RequireCanonical(document.RootElement, value[..^1], description);
            return document;
        }
        catch
        {
            document.Dispose();
            throw;
        }
    }

    private static void RequireIntegralJson(JsonElement value)
    {
        if (value.ValueKind == JsonValueKind.Number &&
            (value.GetRawText().Contains('.') || value.GetRawText().Contains('e') || value.GetRawText().Contains('E')))
            throw new InvalidDataException("Floating-point Runtime evidence JSON is forbidden.");
        if (value.ValueKind == JsonValueKind.Object)
            foreach (var property in value.EnumerateObject()) RequireIntegralJson(property.Value);
        if (value.ValueKind == JsonValueKind.Array)
            foreach (var item in value.EnumerateArray()) RequireIntegralJson(item);
    }

    internal static void ValidateEvidenceJsonForTests(string json)
    {
        using var _ = EvidenceJson(StrictUtf8.GetBytes(json), "test Runtime evidence");
    }

    private static string Digest(byte[] bytes) =>
        "sha256:" + Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();

    private static string Fingerprint(byte[] publicKey)
    {
        var text = StrictUtf8.GetString(publicKey);
        var match = Regex.Match(text, @"\Assh-ed25519 ([A-Za-z0-9+/]+={0,2})\n\z", RegexOptions.CultureInvariant);
        if (!match.Success) throw new InvalidDataException("Invalid Ed25519 public key.");
        byte[] blob;
        try { blob = Convert.FromBase64String(match.Groups[1].Value); }
        catch (FormatException error) { throw new InvalidDataException("Invalid Ed25519 public key.", error); }
        var prefix = new byte[] { 0, 0, 0, 11 }.Concat("ssh-ed25519"u8.ToArray())
            .Concat(new byte[] { 0, 0, 0, 32 }).ToArray();
        if (blob.Length != prefix.Length + 32 || !blob.AsSpan(0, prefix.Length).SequenceEqual(prefix) ||
            Convert.ToBase64String(blob) != match.Groups[1].Value)
            throw new InvalidDataException("Invalid Ed25519 public key.");
        return Digest(blob);
    }

    private static void VerifySignature(byte[] message, byte[] signature, byte[] publicKey,
        string namespaceName, string principal)
    {
        var armor = StrictUtf8.GetString(signature);
        if (!armor.StartsWith("-----BEGIN SSH SIGNATURE-----\n", StringComparison.Ordinal) ||
            !armor.EndsWith("-----END SSH SIGNATURE-----\n", StringComparison.Ordinal))
            throw new InvalidDataException("Invalid Runtime evidence signature.");
        const string header = "-----BEGIN SSH SIGNATURE-----\n";
        const string footer = "-----END SSH SIGNATURE-----\n";
        var lines = armor[header.Length..^footer.Length].Split('\n');
        if (lines.Length < 2 || lines[^1] != "" || lines.SkipLast(2).Any(line => line.Length != 70) ||
            lines[^2].Length is < 1 or > 70)
            throw new InvalidDataException("Invalid Runtime evidence signature.");
        var encoded = string.Concat(lines.SkipLast(1));
        byte[] blob;
        try { blob = Convert.FromBase64String(encoded); }
        catch (FormatException error) { throw new InvalidDataException("Invalid Runtime evidence signature.", error); }
        if (!blob.AsSpan().StartsWith("SSHSIG"u8) || Convert.ToBase64String(blob) != encoded)
            throw new InvalidDataException("Invalid Runtime evidence signature.");
        _ = Fingerprint(publicKey);
        var directory = Directory.CreateTempSubdirectory("codex-agent-runtime-signature-");
        try
        {
            var allowed = Path.Combine(directory.FullName, "allowed-signers");
            var detached = Path.Combine(directory.FullName, "signature.sig");
            File.WriteAllBytes(allowed, Encoding.ASCII.GetBytes(principal + " ").Concat(publicKey).ToArray());
            File.WriteAllBytes(detached, signature);
            var verifier = OperatingSystem.IsWindows()
                ? Path.Combine(Environment.SystemDirectory, "OpenSSH", "ssh-keygen.exe")
                : "/usr/bin/ssh-keygen";
            if (!File.Exists(verifier)) throw new InvalidDataException("System OpenSSH verifier is unavailable.");
            var start = new ProcessStartInfo(verifier)
            {
                RedirectStandardInput = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                UseShellExecute = false,
            };
            foreach (var argument in new[] { "-Y", "verify", "-f", allowed, "-I", principal,
                         "-n", namespaceName, "-s", detached }) start.ArgumentList.Add(argument);
            using var process = Process.Start(start) ?? throw new InvalidDataException("OpenSSH verifier did not start.");
            process.StandardInput.BaseStream.Write(message);
            process.StandardInput.Close();
            if (!process.WaitForExit(10000))
            {
                process.Kill(entireProcessTree: true);
                throw new InvalidDataException("OpenSSH signature verification timed out.");
            }
            _ = process.StandardOutput.ReadToEnd();
            _ = process.StandardError.ReadToEnd();
            if (process.ExitCode != 0) throw new InvalidDataException("Runtime evidence signature verification failed.");
        }
        catch (System.ComponentModel.Win32Exception error)
        {
            throw new InvalidDataException("OpenSSH signature verifier is unavailable.", error);
        }
        finally { directory.Delete(true); }
    }

    private static string ExternalDigestHint(string evidenceRoot)
    {
        var raw = ReadEvidence(Path.Combine(evidenceRoot, "runtime-library-authorization.json"));
        using var claim = EvidenceJson(raw, "Runtime library authorization");
        return Sha(String(claim.RootElement, "runtimeLibrarySha256"), "Runtime library digest");
    }

    private static string RequireExternalRuntimeEvidence(string snapshot, string evidenceRoot, byte[] pinnedRoot,
        Compatibility compatibility, string target)
    {
        var directory = new DirectoryInfo(evidenceRoot);
        directory.Refresh();
        if (!directory.Exists || (directory.Attributes & FileAttributes.ReparsePoint) != 0)
            throw new InvalidDataException("Runtime evidence directory is missing or unsafe.");
        var rootFingerprint = Fingerprint(pinnedRoot);
        var keyringBytes = ReadEvidence(Path.Combine(evidenceRoot, "release-keyring.json"));
        var delegationBytes = ReadEvidence(Path.Combine(evidenceRoot, "root-delegation.json"));
        using var delegationDocument = EvidenceJson(delegationBytes, "Runtime root delegation");
        var delegation = delegationDocument.RootElement;
        RequireObject(delegation, ["schemaVersion", "kind", "scope", "rootFingerprint", "keyringSha256"],
            "Runtime root delegation");
        if (Integer(delegation, "schemaVersion") != 1 ||
            String(delegation, "kind") != "sdk-runtime-release-keyring-delegation" ||
            String(delegation, "scope") != "desktop-runtime-library" ||
            String(delegation, "rootFingerprint") != rootFingerprint ||
            String(delegation, "keyringSha256") != Digest(keyringBytes))
            throw new InvalidDataException("Runtime delegation differs from the SDK root or keyring.");
        VerifySignature(delegationBytes, ReadEvidence(Path.Combine(evidenceRoot, "root-delegation.sig")),
            pinnedRoot, RootNamespace, "codex-agent-sdk-runtime-root");

        using var keyringDocument = EvidenceJson(keyringBytes, "Runtime release keyring");
        var keyring = keyringDocument.RootElement;
        RequireObject(keyring, ["schemaVersion", "namespace", "algorithm", "trustDomain", "activeKey", "retiredKeys"],
            "Runtime release keyring");
        if (Integer(keyring, "schemaVersion") != 1 || String(keyring, "namespace") != ProductNamespace ||
            String(keyring, "algorithm") != "ssh-ed25519" || String(keyring, "trustDomain") != "release")
            throw new InvalidDataException("Invalid Runtime release keyring.");
        var retired = keyring.GetProperty("retiredKeys");
        if (retired.ValueKind != JsonValueKind.Array) throw new InvalidDataException("Invalid Runtime retired keys.");
        var records = new List<JsonElement>();
        var active = keyring.GetProperty("activeKey");
        if (active.ValueKind != JsonValueKind.Null) records.Add(active);
        records.AddRange(retired.EnumerateArray());
        var keys = new Dictionary<string, byte[]>(StringComparer.Ordinal);
        var fingerprints = new HashSet<string>(StringComparer.Ordinal);
        var retiredIds = new List<string>();
        foreach (var record in records)
        {
            RequireObject(record, ["keyId", "fingerprint"], "Runtime release key");
            var id = String(record, "keyId");
            if (!Regex.IsMatch(id, @"\A[a-z0-9][a-z0-9-]{0,63}\z", RegexOptions.CultureInvariant) || keys.ContainsKey(id))
                throw new InvalidDataException("Invalid Runtime release key ID.");
            var publicKey = ReadEvidence(Path.Combine(evidenceRoot, "keys", id + ".pub"), 4096);
            var fingerprint = Fingerprint(publicKey);
            if (String(record, "fingerprint") != fingerprint || !fingerprints.Add(fingerprint))
                throw new InvalidDataException("Runtime release key fingerprint mismatch.");
            keys.Add(id, publicKey);
            if (records.IndexOf(record) >= (active.ValueKind == JsonValueKind.Null ? 0 : 1)) retiredIds.Add(id);
        }
        if (!retiredIds.SequenceEqual(retiredIds.Order(StringComparer.Ordinal), StringComparer.Ordinal))
            throw new InvalidDataException("Invalid Runtime retired key order.");

        var claimBytes = ReadEvidence(Path.Combine(evidenceRoot, "runtime-library-authorization.json"));
        using var claimDocument = EvidenceJson(claimBytes, "Runtime library authorization");
        var claim = claimDocument.RootElement;
        RequireObject(claim, ["schemaVersion", "kind", "runtimeVersion", "runtimeIdentity", "runtimeLibrarySha256",
            "variantBundleSha256", "variantManifestSha256", "aggregateManifestSha256",
            "variantAttestationSha256", "aggregateAttestationSha256", "signing"], "Runtime library authorization");
        var signing = claim.GetProperty("signing");
        RequireObject(signing, ["algorithm", "namespace", "trustDomain", "keyId", "fingerprint"],
            "Runtime authorization signing");
        var signerId = String(signing, "keyId");
        if (String(signing, "algorithm") != "ssh-ed25519" || String(signing, "namespace") != ProductNamespace ||
            String(signing, "trustDomain") != "release" || !keys.TryGetValue(signerId, out var signer) ||
            String(signing, "fingerprint") != Fingerprint(signer))
            throw new InvalidDataException("Runtime authorization signer is not delegated.");
        VerifySignature(claimBytes, ReadEvidence(Path.Combine(evidenceRoot, "runtime-library-authorization.sig")),
            signer, ProductNamespace, "codex-agent-product");

        var expectedFiles = new HashSet<string>(StringComparer.Ordinal)
        {
            "release-keyring.json", "root-delegation.json", "root-delegation.sig",
            "runtime-library-authorization.json", "runtime-library-authorization.sig",
        };
        foreach (var id in keys.Keys) expectedFiles.Add("keys/" + id + ".pub");
        var actualFiles = new HashSet<string>(StringComparer.Ordinal);
        foreach (var entry in Directory.EnumerateFileSystemEntries(evidenceRoot, "*", SearchOption.AllDirectories))
        {
            if ((File.GetAttributes(entry) & FileAttributes.ReparsePoint) != 0)
                throw new InvalidDataException("Runtime evidence contains an unsafe link.");
            var relative = Path.GetRelativePath(evidenceRoot, entry).Replace('\\', '/');
            if (Directory.Exists(entry))
            {
                if (relative != "keys") throw new InvalidDataException("Runtime evidence contains an extra directory.");
            }
            else actualFiles.Add(relative);
        }
        if (!actualFiles.SetEquals(expectedFiles))
            throw new InvalidDataException("Runtime evidence contains extra or missing files.");
        if (Integer(claim, "schemaVersion") != 1 || String(claim, "kind") != "desktop-runtime-library-authorization")
            throw new InvalidDataException("Invalid Runtime authorization identity.");
        foreach (var field in new[] { "runtimeLibrarySha256", "variantBundleSha256", "variantManifestSha256",
                     "aggregateManifestSha256", "variantAttestationSha256", "aggregateAttestationSha256" })
            _ = Sha(String(claim, field), $"Runtime authorization {field}");
        var identity = claim.GetProperty("runtimeIdentity");
        RequireObject(identity, ["schemaVersion", "componentId", "runtimeCompatibilityVersion", "contractDigest",
            "contractComponentDigest", "cAbiVersion", "target", "appServerVersion", "buildInputDigest"],
            "authorized Runtime identity");
        foreach (var field in new[] { "componentId", "contractDigest", "contractComponentDigest", "buildInputDigest" })
            _ = Sha(String(identity, field), $"authorized Runtime {field}");
        var abi = Semver(String(identity, "cAbiVersion"), "authorized Runtime ABI");
        _ = Semver(String(identity, "appServerVersion"), "authorized app-server version");
        var release = Semver(String(claim, "runtimeVersion"), "authorized Runtime version");
        var compatible = Semver(String(identity, "runtimeCompatibilityVersion"), "authorized Runtime compatibility");
        if (Integer(identity, "schemaVersion") != compatibility.IdentitySchema || String(identity, "target") != target ||
            String(identity, "contractDigest") != compatibility.ContractDigest ||
            release < compatibility.ReleaseMinimum || release >= compatibility.ReleaseMaximum ||
            compatible < compatibility.CompatibilityMinimum || compatible >= compatibility.CompatibilityMaximum ||
            abi.Major > 255 || abi.Major != compatibility.AbiMajor || abi.Minor < compatibility.AbiMinor ||
            abi.Minor > 255 || abi.Build > 65535)
            throw new InvalidDataException("Runtime authorization is incompatible with this SDK.");
        if (Digest(File.ReadAllBytes(snapshot)) != String(claim, "runtimeLibrarySha256"))
            throw new InvalidDataException("Runtime library differs from its signed authorization.");
        return JsonSerializer.Serialize(identity, CanonicalJson);
    }
}
