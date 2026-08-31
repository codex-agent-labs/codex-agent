using CodexAgent;
using CodexAgent.Interop;
using System.Collections;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

internal static class McpValueParity
{
    private const string OwnerPrefix = "common|owner=io.github.codex_agent_labs.codexagent.agent/";
    private static readonly string[] Owners =
    [
        "AgentMcpEnvironmentVariable",
        "AgentMcpOauthConfiguration",
        "AgentMcpServer",
        "AgentMcpServerConfiguration",
        "AgentMcpToolConfiguration",
        "AgentMcpTransport.Http",
        "AgentMcpTransport.Stdio",
    ];

    internal static void VerifyManaged(
        IReadOnlyList<string[]> allClaims,
        ISet<string> canonicalCapabilities,
        ISet<string> executedTests)
    {
        VerifyEvidenceReferences(McpClaims(allClaims));
        var expected = ExpectedGraph();
        VerifyClaims(allClaims, canonicalCapabilities, executedTests, expected);
        VerifyValidationAndDefensiveCopies();
    }

    internal static void VerifyNative(
        string sdkPath,
        IReadOnlyList<string[]> allClaims,
        ISet<string> canonicalCapabilities)
    {
        VerifyEvidenceReferences(McpClaims(allClaims));
        CodexNativeLibrary.Configure(sdkPath);
        var context = NativeContext.Create();
        try
        {
            var actual = new ValueGraph(
                ProjectServer(context, 0),
                ProjectServer(context, 1),
                ProjectServer(context, 2));
            var executed = new HashSet<string>(StringComparer.Ordinal);
            VerifyClaims(allClaims, canonicalCapabilities, executed, actual);
            var expectedTests = McpClaims(allClaims).SelectMany(columns => columns[2].Split(','));
            Check(executed.SetEquals(expectedTests), "every MCP native projection claim executed");
        }
        finally
        {
            context.Release();
            context.ThrowIfReleaseFailed();
        }
        Console.WriteLine("CodexAgent C# real C ABI MCP value projection tests passed: 46/46.");
    }

    internal static void EmitEvidence(IReadOnlyList<string[]> claims, ISet<string> executedTests)
    {
        var claimedTests = claims.SelectMany(columns => columns[2].Split(',')).ToHashSet(StringComparer.Ordinal);
        Check(executedTests.SetEquals(claimedTests), "generated executed-test evidence exactly matches used claims");

        var compilerEvidence = new SortedDictionary<string, SortedSet<string>>(StringComparer.Ordinal);
        foreach (var claim in claims)
        {
            var symbols = claim[1].Split(',');
            foreach (var evidenceId in claim[3].Split(','))
            {
                if (!compilerEvidence.TryGetValue(evidenceId, out var evidenceSymbols))
                {
                    evidenceSymbols = new SortedSet<string>(StringComparer.Ordinal);
                    compilerEvidence.Add(evidenceId, evidenceSymbols);
                }
                evidenceSymbols.UnionWith(symbols);
            }
        }

        var directory = Path.Combine(AppContext.BaseDirectory, "artifacts");
        Directory.CreateDirectory(directory);
        WriteLf(
            Path.Combine(directory, "compiler-evidence.tsv"),
            ["compilerEvidenceId\tpublicSymbols", .. compilerEvidence.Select(entry => $"{entry.Key}\t{string.Join(',', entry.Value)}")]);
        WriteLf(
            Path.Combine(directory, "executed-tests.tsv"),
            ["executedTestId\tstatus", .. executedTests.Order(StringComparer.Ordinal).Select(test => $"{test}\tpassed")]);
    }

    private static CodexMcpServer ProjectServer(NativeContext context, int variant)
    {
        NativeApi.ThrowIfFailed(CreateMcpServerFixture(context.Pointer, variant, out var stage, out var server), $"create MCP value fixture {variant} stage {stage}");
        return NativeMcpValues.ReadOwnedServer(context, ref server);
    }

    private static void VerifyClaims(
        IReadOnlyList<string[]> allClaims,
        ISet<string> canonicalCapabilities,
        ISet<string> executedTests,
        ValueGraph graph)
    {
        var claims = McpClaims(allClaims);
        Check(claims.Length == 46, "exact MCP immutable-value claim count");
        Check(claims.All(columns => canonicalCapabilities.Contains(columns[0])), "every MCP value claim is canonical");

        var expected = ExpectedGraph();
        foreach (var columns in claims)
        {
            var key = columns[0];
            var owner = Owners.Single(candidate => key.StartsWith($"{OwnerPrefix}{candidate}|", StringComparison.Ordinal));
            var actualOwner = SelectOwner(graph, owner);
            var expectedOwner = SelectOwner(expected, owner);
            var kind = Between(key, "|kind=", "|");
            var member = kind == "constructor" ? "#ctor" : PascalCase(Between(key, "|abi=", "|").Split('.').Last());
            var type = actualOwner.GetType();
            var expectedSymbol = $"{PublicTypeName(type)}.{member}";
            Check(columns[1] == expectedSymbol, $"{columns[2]}: exact public symbol");
            Check(columns[2].Split(',').Length == 1, $"{columns[2]}: exactly one per-capability executed test");
            Check(columns[3].Split(',').Any(value => value.StartsWith("c-header:", StringComparison.Ordinal)), $"{columns[2]}: exact C-header evidence");
            Check(columns[3].Split(',').Any(value => value.StartsWith("cabi-fixture:", StringComparison.Ordinal)), $"{columns[2]}: exact native fixture evidence");
            Check(columns[4] == ExpectedScenarios(key), $"{columns[2]}: exact shared scenarios");

            if (kind == "constructor")
            {
                Check((type.IsPublic || type.IsNestedPublic) && type.GetConstructors().Length != 0, $"{columns[2]}: public constructor exists");
            }
            else
            {
                var property = type.GetProperty(member);
                Check(property is { GetMethod.IsPublic: true }, $"{columns[2]}: public property exists");
                Check(StructurallyEqual(property!.GetValue(actualOwner), property.GetValue(expectedOwner)),
                    $"{columns[2]}: exact projected property value");
            }
            Check(executedTests.Add(columns[2]), $"{columns[2]}: executed exactly once");
        }

        Check(graph.Sparse.Configuration is
        {
            Authentication: null,
            OmitToolsFrom.Count: 0,
            StartupTimeoutSeconds: null,
            ToolTimeoutSeconds: null,
            DefaultToolApproval: null,
            EnabledTools.Count: 0,
            DisabledTools.Count: 0,
            Scopes.Count: 0,
            Oauth: null,
            OauthResource: null,
            Tools.Count: 0,
        }, "nullable MCP values preserve present-empty versus absent");
        Check(graph.Sparse.Configuration?.Transport is CodexMcpTransport.Http
        {
            BearerTokenEnvironmentVariable: null,
            Headers: null,
            EnvironmentHeaders: null,
            HeadersHelper: null,
        }, "nullable HTTP values preserve absence");
    }

    private static string[][] McpClaims(IReadOnlyList<string[]> claims) => claims
        .Where(columns => Owners.Any(owner => columns[0].StartsWith($"{OwnerPrefix}{owner}|", StringComparison.Ordinal)))
        .ToArray();

    internal static void VerifyEvidenceReferences(IEnumerable<string[]> claims)
    {
        var parityDirectory = Path.Combine(AppContext.BaseDirectory, "parity");
        using var bootstrap = JsonDocument.Parse(File.ReadAllText(Path.Combine(parityDirectory, "c-abi-bootstrap-evidence.json")));
        var passedNativeTests = bootstrap.RootElement.GetProperty("nativeTests")
            .EnumerateArray()
            .Where(test => test.GetProperty("status").GetString() == "passed")
            .Select(test => test.GetProperty("testId").GetString() ?? throw new InvalidDataException("null native test ID"))
            .ToHashSet(StringComparer.Ordinal);
        var bootstrapClaims = bootstrap.RootElement.GetProperty("claims")
            .EnumerateArray()
            .ToDictionary(
                claim => claim.GetProperty("capabilityKey").GetString() ?? throw new InvalidDataException("null bootstrap capability"),
                claim => claim,
                StringComparer.Ordinal);
        var header = File.ReadAllText(Path.Combine(parityDirectory, "codex_agent.h"));

        static bool HeaderDefines(string source, string symbol) => symbol switch
        {
            _ when symbol.StartsWith("CODEX_AGENT_", StringComparison.Ordinal) =>
                Regex.IsMatch(source, $@"^\s*#define\s+{Regex.Escape(symbol)}\b", RegexOptions.CultureInvariant | RegexOptions.Multiline),
            _ when symbol.EndsWith("_t", StringComparison.Ordinal) =>
                Regex.IsMatch(source, $@"\b{Regex.Escape(symbol)}\b", RegexOptions.CultureInvariant),
            _ when symbol.Contains(';') => source.Contains(symbol, StringComparison.Ordinal),
            _ => Regex.IsMatch(source, $@"\b{Regex.Escape(symbol)}\s*\(", RegexOptions.CultureInvariant),
        };

        foreach (var columns in claims)
        {
            Check(bootstrapClaims.TryGetValue(columns[0], out var canonicalClaim), $"missing canonical C ABI claim: {columns[0]}");
            var expectedHeaders = canonicalClaim.GetProperty("headerReferences").EnumerateArray()
                .Select(value => value.GetString() ?? throw new InvalidDataException("null header reference"))
                .ToHashSet(StringComparer.Ordinal);
            var expectedTests = canonicalClaim.GetProperty("nativeTestIds").EnumerateArray()
                .Select(value => value.GetString() ?? throw new InvalidDataException("null native test reference"))
                .ToHashSet(StringComparer.Ordinal);
            var actualHeaders = columns[3].Split(',').Where(value => value.StartsWith("c-header:", StringComparison.Ordinal))
                .Select(value => value["c-header:".Length..]).ToHashSet(StringComparer.Ordinal);
            var actualTests = columns[3].Split(',').Where(value => value.StartsWith("cabi-fixture:", StringComparison.Ordinal))
                .Select(value => value["cabi-fixture:".Length..]).ToHashSet(StringComparer.Ordinal);
            var actualBindingEvidence = columns[3].Split(',')
                .Where(value => value.StartsWith("csharp-il-leaf:", StringComparison.Ordinal) ||
                    value.StartsWith("csharp-il-conversation:", StringComparison.Ordinal) ||
                    value.StartsWith("csharp-il-agent:", StringComparison.Ordinal) ||
                    value.StartsWith("csharp-il-host:", StringComparison.Ordinal))
                .ToHashSet(StringComparer.Ordinal);
            var expectedBindingEvidence = columns[2] switch
            {
                var test when test.StartsWith("csharp.leaf:", StringComparison.Ordinal) =>
                    new HashSet<string>([$"csharp-il-leaf:{test["csharp.leaf:".Length..]}"], StringComparer.Ordinal),
                var test when test.StartsWith("csharp.conversation:", StringComparison.Ordinal) =>
                    new HashSet<string>([$"csharp-il-conversation:{test["csharp.conversation:".Length..]}"], StringComparer.Ordinal),
                var test when test.StartsWith("csharp.agent:", StringComparison.Ordinal) =>
                    new HashSet<string>([$"csharp-il-agent:{test["csharp.agent:".Length..]}"], StringComparer.Ordinal),
                var test when test.StartsWith("csharp.host:", StringComparison.Ordinal) =>
                    new HashSet<string>([$"csharp-il-host:{test["csharp.host:".Length..]}"], StringComparer.Ordinal),
                _ => new HashSet<string>(StringComparer.Ordinal),
            };
            Check(actualHeaders.SetEquals(expectedHeaders), $"exact canonical C-header references: {columns[0]}");
            Check(actualTests.SetEquals(expectedTests), $"exact canonical native-test references: {columns[0]}");
            Check(actualBindingEvidence.SetEquals(expectedBindingEvidence), $"exact C# IL evidence ID: {columns[0]}");
            Check(columns[3].Split(',').Length == actualHeaders.Count + actualTests.Count + actualBindingEvidence.Count,
                $"no noncanonical evidence IDs: {columns[0]}");
            foreach (var symbol in actualHeaders)
            {
                Check(HeaderDefines(header, symbol), $"stale C-header evidence: {symbol}");
            }
            foreach (var testId in actualTests) Check(passedNativeTests.Contains(testId), $"stale or failed C ABI fixture evidence: {testId}");
        }

        Check(!passedNativeTests.Contains("removed.native.test#stale[macosArm64]"), "stale native-test negative is rejected");
        Check(!HeaderDefines(header, "codex_agent_removed_stale_symbol"), "stale C-header negative is rejected");
    }

    private static object SelectOwner(ValueGraph graph, string owner) => owner switch
    {
        "AgentMcpEnvironmentVariable" => ((CodexMcpTransport.Stdio)graph.Stdio.Configuration!.Transport).ForwardedEnvironment.Single(),
        "AgentMcpOauthConfiguration" => graph.Http.Configuration!.Oauth!,
        "AgentMcpToolConfiguration" => graph.Http.Configuration!.Tools["tool"],
        "AgentMcpTransport.Http" => graph.Http.Configuration!.Transport,
        "AgentMcpTransport.Stdio" => graph.Stdio.Configuration!.Transport,
        "AgentMcpServerConfiguration" => graph.Http.Configuration!,
        "AgentMcpServer" => graph.Http,
        _ => throw new InvalidOperationException($"Unknown MCP owner {owner}."),
    };

    private static ValueGraph ExpectedGraph()
    {
        var http = new CodexMcpTransport.Http(
            "https://example.com/mcp",
            "TOKEN_ENV",
            new Dictionary<string, string> { ["X-A"] = "one", ["X-B"] = "two" },
            new Dictionary<string, string> { ["Authorization"] = "AUTH_HEADER" },
            "/usr/bin/headers-helper");
        var httpConfiguration = new CodexMcpServerConfiguration(
            "server_1",
            http,
            CodexMcpAuthentication.Oauth,
            "local",
            true,
            false,
            true,
            [CodexMcpToolExposureSurface.CodeMode, CodexMcpToolExposureSurface.Direct],
            1.5,
            2.5,
            CodexMcpToolApproval.Writes,
            ["one", "one"],
            [],
            ["scope-a", "scope-a"],
            new CodexMcpOauthConfiguration("", 65535),
            "",
            new Dictionary<string, CodexMcpToolConfiguration> { ["tool"] = new(CodexMcpToolApproval.Prompt) });

        var stdio = new CodexMcpTransport.Stdio(
            "node",
            ["server.js", "--flag", "--flag"],
            "/workspace",
            new Dictionary<string, string> { ["A"] = "1", ["B"] = "2" },
            [new CodexMcpEnvironmentVariable("REMOTE_TOKEN", CodexMcpEnvironmentSource.Remote)]);
        var stdioConfiguration = new CodexMcpServerConfiguration(
            "server_1", stdio, environmentId: "local", isEnabled: false, isRequired: true);

        var sparseTransport = new CodexMcpTransport.Http("http://127.0.0.1:7777/mcp");
        var sparseConfiguration = new CodexMcpServerConfiguration(
            "server_1",
            sparseTransport,
            omitToolsFrom: [],
            enabledTools: [],
            disabledTools: [],
            scopes: []);

        return new ValueGraph(
            new CodexMcpServer("server_1", "Server One", CodexMcpAuthStatus.Oauth, httpConfiguration, CodexResourceOrigin.Plugin, true),
            new CodexMcpServer("server_1", "Server One", CodexMcpAuthStatus.Unknown, stdioConfiguration, CodexResourceOrigin.User),
            new CodexMcpServer("server_1", "Server One", CodexMcpAuthStatus.Unknown, sparseConfiguration, CodexResourceOrigin.User));
    }

    private static void VerifyValidationAndDefensiveCopies()
    {
        var arguments = new List<string> { "one" };
        var environment = new Dictionary<string, string> { ["A"] = "1" };
        var transport = new CodexMcpTransport.Stdio("node", arguments, environment: environment);
        arguments[0] = "changed";
        environment["A"] = "changed";
        Check(transport.Arguments.SequenceEqual(["one"]) && transport.Environment!["A"] == "1", "MCP transport defensively copies collections");
        Check(!StructurallyEqual(new[] { "one" }, new[] { "different" }), "collection matcher rejects unequal members");

        RequireThrows<ArgumentException>(() => new CodexMcpTransport.Http("http://example.com"));
        RequireThrows<ArgumentException>(() => new CodexMcpTransport.Http("http://localhost.evil.example/mcp"));
        RequireThrows<ArgumentException>(() => new CodexMcpTransport.Http("https:///missing-host"));
        RequireThrows<ArgumentException>(() => new CodexMcpTransport.Http("https://?missing-host"));
        RequireThrows<ArgumentException>(() => new CodexMcpTransport.Http("https://mcp.example.com:invalid"));
        RequireThrows<ArgumentException>(() => new CodexMcpTransport.Http("https://%ZZ"));
        _ = new CodexMcpTransport.Http("https://mcp.example.com:443/path");
        _ = new CodexMcpTransport.Http("http://[::1]:8080/mcp");
        RequireThrows<ArgumentOutOfRangeException>(() => new CodexMcpOauthConfiguration(callbackPort: 0));
        RequireThrows<ArgumentOutOfRangeException>(() => new CodexMcpEnvironmentVariable("TOKEN", (CodexMcpEnvironmentSource)99));
        RequireThrows<ArgumentOutOfRangeException>(() => new CodexMcpToolConfiguration((CodexMcpToolApproval)99));
        RequireThrows<ArgumentException>(() => new CodexMcpServerConfiguration("bad name", transport));
        RequireThrows<ArgumentException>(() => new CodexMcpServerConfiguration("server", transport, CodexMcpAuthentication.Oauth));
        RequireThrows<ArgumentOutOfRangeException>(() => new CodexMcpServerConfiguration("server", transport, startupTimeoutSeconds: double.NaN));
    }

    private static void RequireThrows<T>(Action action) where T : Exception
    {
        try { action(); }
        catch (T) { return; }
        throw new InvalidOperationException($"Expected {typeof(T).Name}.");
    }

    internal static bool StructurallyEqual(object? actual, object? expected)
    {
        if (actual is null || expected is null) return actual is null && expected is null;
        if (actual is string || actual.GetType().IsValueType) return actual.Equals(expected);
        if (actual is IDictionary actualMap && expected is IDictionary expectedMap)
        {
            if (actualMap.Count != expectedMap.Count) return false;
            foreach (DictionaryEntry entry in actualMap)
                if (!expectedMap.Contains(entry.Key) || !StructurallyEqual(entry.Value, expectedMap[entry.Key])) return false;
            return true;
        }
        if (actual is IEnumerable actualItems && expected is IEnumerable expectedItems)
        {
            var actualValues = actualItems.Cast<object?>().ToArray();
            var expectedValues = expectedItems.Cast<object?>().ToArray();
            return actualValues.Length == expectedValues.Length &&
                actualValues.Zip(expectedValues, StructurallyEqual).All(static equal => equal);
        }
        return JsonSerializer.Serialize(actual, actual.GetType()) == JsonSerializer.Serialize(expected, expected.GetType());
    }

    private static string PublicTypeName(Type type) => type == typeof(CodexMcpTransport.Http)
        ? "CodexAgent.CodexMcpTransport.Http"
        : type == typeof(CodexMcpTransport.Stdio)
            ? "CodexAgent.CodexMcpTransport.Stdio"
            : $"CodexAgent.{type.Name}";

    private static string ExpectedScenarios(string capabilityKey)
    {
        var scenarios = new List<string> { "value-conversion" };
        if (capabilityKey.Contains('?')) scenarios.Add("nullability");
        if (capabilityKey.Contains("kotlin.collections", StringComparison.Ordinal)) scenarios.Add("collection-immutability-ordering");
        scenarios.Sort(StringComparer.Ordinal);
        return string.Join(',', scenarios);
    }

    private static string Between(string value, string prefix, string suffix)
    {
        var start = value.IndexOf(prefix, StringComparison.Ordinal) + prefix.Length;
        var end = value.IndexOf(suffix, start, StringComparison.Ordinal);
        return value[start..end];
    }

    private static string PascalCase(string value) => char.ToUpperInvariant(value[0]) + value[1..];

    private static void WriteLf(string path, IEnumerable<string> lines) =>
        File.WriteAllText(path, string.Join('\n', lines) + "\n", new UTF8Encoding(false));

    private static void Check(bool condition, string message)
    {
        if (!condition) throw new InvalidOperationException(message);
    }

    private sealed record ValueGraph(CodexMcpServer Http, CodexMcpServer Stdio, CodexMcpServer Sparse);

    [DllImport("codex_agent_csharp_fixture", EntryPoint = "codex_agent_test_mcp_server_fixture", CallingConvention = CallingConvention.Cdecl)]
    private static extern CodexStatus CreateMcpServerFixture(nint context, int variant, out int stage, out nint server);
}
