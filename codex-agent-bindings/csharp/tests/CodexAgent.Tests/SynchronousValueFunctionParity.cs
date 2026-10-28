using CodexAgent;
using CodexAgent.Interop;
using System.Collections;
using System.Reflection;
using System.Reflection.Emit;
using System.Runtime.InteropServices;

internal static class SynchronousValueFunctionParity
{
    private const string OwnerPrefix = "common|owner=io.github.codex_agent_labs.codexagent.agent/";
    private static readonly IReadOnlyDictionary<string, Type> OwnerTypes =
        new Dictionary<string, Type>(StringComparer.Ordinal)
        {
            ["AgentElicitationResponse.Companion"] = typeof(CodexElicitationResponse),
            ["AgentElicitation"] = typeof(CodexElicitation),
            ["AgentFormField"] = typeof(CodexFormField),
            ["AgentInteractionState"] = typeof(CodexInteractionState),
            ["CodexAuthorizationUrl.Companion"] = typeof(CodexAuthorizationUrl),
        };

    internal static void VerifyContract(
        IReadOnlyList<string[]> allClaims,
        ISet<string> canonicalCapabilities)
    {
        var claims = allClaims.Where(row => row[2].StartsWith("csharp.function:", StringComparison.Ordinal)).ToArray();
        ValidateClaims(claims, canonicalCapabilities);
        McpValueParity.VerifyEvidenceReferences(claims);
        VerifyNegativeEvidence(claims, canonicalCapabilities);
    }

    internal static void VerifyNative(
        IReadOnlyList<string[]> allClaims,
        ISet<string> canonicalCapabilities,
        ISet<string> executedTests)
    {
        VerifyContract(allClaims, canonicalCapabilities);
        var claims = allClaims.Where(row => row[2].StartsWith("csharp.function:", StringComparison.Ordinal)).ToArray();

        var fixture = new Fixture();
        foreach (var row in claims)
        {
            var publicSymbol = row[1];
            var nativeCalls = new List<string>();
            NativeMethods.SetExactCallObserver(nativeCalls.Add);
            try
            {
                switch (publicSymbol)
                {
                    case "CodexAgent.CodexElicitationResponse.Cancel":
                        Check(CodexElicitationResponse.Cancel() is
                            { Action: CodexElicitationAction.Cancel, Content.Count: 0 }, "cancel factory");
                        break;
                    case "CodexAgent.CodexElicitationResponse.Decline":
                        Check(CodexElicitationResponse.Decline() is
                            { Action: CodexElicitationAction.Decline, Content.Count: 0 }, "decline factory");
                        break;
                    case "CodexAgent.CodexElicitation.Accepts":
                        Check(fixture.Elicitation.Accepts(new CodexElicitationResponse(
                                CodexElicitationAction.Accept, fixture.ValidContent)) &&
                            !fixture.Elicitation.Accepts(new CodexElicitationResponse(
                                CodexElicitationAction.Accept, new Dictionary<string, CodexFormValue>())) &&
                            fixture.Elicitation.Accepts(new CodexElicitationResponse(CodexElicitationAction.Decline)) &&
                            fixture.Elicitation.Accepts(new CodexElicitationResponse(CodexElicitationAction.Cancel)) &&
                            !fixture.Elicitation.Accepts(new CodexElicitationResponse(
                                CodexElicitationAction.Decline, fixture.ValidContent)) &&
                            !fixture.Elicitation.Accepts(new CodexElicitationResponse(
                                CodexElicitationAction.Cancel, fixture.ValidContent)), "accepts truth table");
                        break;
                    case "CodexAgent.CodexElicitation.Accept":
                        VerifyAccept(fixture);
                        break;
                    case "CodexAgent.CodexElicitation.InitialValues":
                        VerifyInitialValues(fixture);
                        break;
                    case "CodexAgent.CodexElicitation.Validate":
                        VerifyValidation(fixture);
                        break;
                    case "CodexAgent.CodexFormField.Accepts":
                        VerifyFormFieldAccepts();
                        break;
                    case "CodexAgent.CodexInteractionState.IsResolving":
                        VerifyIsResolving();
                        break;
                    case "CodexAgent.CodexInteractionState.PendingFor":
                        VerifyPendingFor();
                        break;
                    case "CodexAgent.CodexAuthorizationUrl.ChatGpt":
                        Check(CodexAuthorizationUrl.ChatGpt("https://auth.openai.com/authorize").Purpose ==
                            CodexAuthorizationPurpose.ChatGpt, "ChatGPT URL factory");
                        RequireThrows<ArgumentException>(() => CodexAuthorizationUrl.ChatGpt("https://example.com"));
                        break;
                    case "CodexAgent.CodexAuthorizationUrl.External":
                        Check(CodexAuthorizationUrl.External("http://127.0.0.1:8080/auth").Purpose ==
                            CodexAuthorizationPurpose.External, "external URL factory");
                        RequireThrows<ArgumentException>(() => CodexAuthorizationUrl.External("http://example.com"));
                        break;
                    default:
                        throw new InvalidOperationException($"Unexecuted synchronous value function: {publicSymbol}");
                }
            }
            finally
            {
                NativeMethods.SetExactCallObserver(null);
            }
            var expectedCall = ExpectedNativeCall(row[0]);
            var expectedWrapper = ExpectedNativeWrapper(row[0]);
            Check(row[3].Split(',').Contains($"c-header:{expectedCall}", StringComparer.Ordinal),
                $"{row[2]}: exact native call is a canonical compiler reference");
            ValidateObservedCalls(nativeCalls, expectedWrapper, row[2]);
            Check(executedTests.Add(row[2]), $"{row[2]}: executed exactly once");
        }

        Console.WriteLine("CodexAgent C# synchronous value-function capability tests passed: 11/11.");
    }

    internal static void WriteNativeEvidence(
        IReadOnlyList<string[]> allClaims,
        ISet<string> executedTests)
    {
        var claims = allClaims.Where(row => row[2].StartsWith("csharp.function:", StringComparison.Ordinal))
            .OrderBy(row => row[2], StringComparer.Ordinal).ToArray();
        Check(executedTests.SetEquals(claims.Select(row => row[2])),
            "native synchronous evidence exactly matches function claims");
        var directory = Path.Combine(AppContext.BaseDirectory, "artifacts");
        Directory.CreateDirectory(directory);
        File.WriteAllText(
            Path.Combine(directory, "synchronous-native-tests.tsv"),
            string.Join('\n', new[] { "executedTestId\tnativeSymbol\tstatus" }.Concat(
                claims.Select(row => $"{row[2]}\t{ExpectedNativeCall(row[0])}\tpassed"))) + "\n");
    }

    internal static void ImportNativeEvidence(
        IReadOnlyList<string[]> allClaims,
        ISet<string> executedTests)
    {
        var expected = allClaims.Where(row => row[2].StartsWith("csharp.function:", StringComparison.Ordinal))
            .ToDictionary(row => row[2], row => ExpectedNativeCall(row[0]), StringComparer.Ordinal);
        var path = Path.Combine(AppContext.BaseDirectory, "artifacts", "synchronous-native-tests.tsv");
        Check(File.Exists(path), "real-SDK synchronous evidence exists");
        var lines = File.ReadAllLines(path);
        Check(lines.Length == expected.Count + 1 && lines[0] == "executedTestId\tnativeSymbol\tstatus",
            "exact real-SDK synchronous evidence shape");
        var rows = lines.Skip(1).Select(line => line.Split('\t')).ToArray();
        Check(rows.All(row => row.Length == 3 && row[2] == "passed"),
            "all real-SDK synchronous evidence passed");
        Check(rows.Select(row => row[0]).SequenceEqual(rows.Select(row => row[0]).Order(StringComparer.Ordinal)),
            "real-SDK synchronous evidence is sorted");
        Check(rows.Select(row => row[0]).Distinct(StringComparer.Ordinal).Count() == expected.Count &&
            rows.All(row => expected.TryGetValue(row[0], out var symbol) && symbol == row[1]),
            "real-SDK synchronous evidence exactly binds every claimed native symbol");
        foreach (var row in rows) Check(executedTests.Add(row[0]), $"{row[0]}: imported exactly once");
    }

    private static void ValidateClaims(IReadOnlyList<string[]> claims, ISet<string> canonicalCapabilities)
    {
        Check(claims.Count == 11, "exact synchronous value-function claim count");
        Check(claims.Select(row => row[0]).Distinct(StringComparer.Ordinal).Count() == 11,
            "function capability keys are unique");
        Check(claims.Select(row => row[1]).Distinct(StringComparer.Ordinal).Count() == 11,
            "function public symbols are unique");
        Check(claims.Select(row => row[2]).Distinct(StringComparer.Ordinal).Count() == 11,
            "function executed tests are distinct per capability");
        var expected = canonicalCapabilities.Where(capability =>
            capability.Contains("|kind=function|", StringComparison.Ordinal) &&
            OwnerTypes.Keys.Any(owner => capability.StartsWith($"{OwnerPrefix}{owner}|", StringComparison.Ordinal)))
            .ToHashSet(StringComparer.Ordinal);
        Check(expected.Count == 11 && expected.SetEquals(claims.Select(row => row[0])),
            "claims exactly match the audited synchronous value-function closure");

        foreach (var row in claims)
        {
            Check(row[1].Split(',').Length == 1 && row[2].Split(',').Length == 1,
                $"{row[2]}: exactly one public symbol and executed test");
            Check(row[4] == ExpectedScenarios(row[0]), $"{row[2]}: exact shared scenarios");
            var owner = OwnerTypes.Keys.Single(candidate =>
                row[0].StartsWith($"{OwnerPrefix}{candidate}|", StringComparison.Ordinal));
            var methodName = row[1].Split('.').Last();
            var expectedMethod = PascalCase(Between(row[0], "|abi=", "|").Split('.').Last());
            Check(methodName == expectedMethod, $"{row[2]}: exact idiomatic public method name");
            var method = OwnerTypes[owner].GetMethod(
                methodName, BindingFlags.Public | BindingFlags.Instance | BindingFlags.Static);
            Check(method is not null, $"{row[2]}: exact public method exists");
            Check(row[1] == $"CodexAgent.{OwnerTypes[owner].Name}.{methodName}",
                $"{row[2]}: exact public symbol");
            ValidateProductionConnection(method!, ExpectedNativeWrapper(row[0]), ExpectedNativeCall(row[0]), row[2]);
        }
    }

    private static void VerifyNegativeEvidence(
        IReadOnlyList<string[]> claims,
        ISet<string> canonicalCapabilities)
    {
        var staleCanonical = claims.Select(row => row.ToArray()).ToArray();
        staleCanonical[0][0] = "common|owner=removed/Stale|kind=function|abi=removed";
        RequireThrows<InvalidOperationException>(() => ValidateClaims(staleCanonical, canonicalCapabilities));

        var staleSymbol = claims.Select(row => row.ToArray()).ToArray();
        staleSymbol[0][1] = "CodexAgent.CodexElicitationResponse.Removed";
        RequireThrows<InvalidOperationException>(() => ValidateClaims(staleSymbol, canonicalCapabilities));

        var duplicateTest = claims.Select(row => row.ToArray()).ToArray();
        duplicateTest[^1][2] = duplicateTest[0][2];
        RequireThrows<InvalidOperationException>(() => ValidateClaims(duplicateTest, canonicalCapabilities));

        var staleHeader = claims[0].ToArray();
        staleHeader[3] = staleHeader[3].Replace(
            staleHeader[3].Split(',').First(value => value.StartsWith("c-header:", StringComparison.Ordinal)),
            "c-header:codex_agent_removed_value_function", StringComparison.Ordinal);
        RequireThrows<InvalidOperationException>(() => McpValueParity.VerifyEvidenceReferences([staleHeader]));

        var staleFixture = claims[0].ToArray();
        staleFixture[3] = staleFixture[3].Replace(
            staleFixture[3].Split(',').First(value => value.StartsWith("cabi-fixture:", StringComparison.Ordinal)),
            "cabi-fixture:removed.native.test#stale[macosArm64]", StringComparison.Ordinal);
        RequireThrows<InvalidOperationException>(() => McpValueParity.VerifyEvidenceReferences([staleFixture]));

        var first = claims[0];
        var firstMethod = PublicMethod(first);
        var firstWrapper = ExpectedNativeWrapper(first[0]);
        var firstCall = ExpectedNativeCall(first[0]);
        RequireThrows<InvalidOperationException>(() =>
            ValidateObservedCalls([firstCall], firstWrapper, "stale-trace"));
        RequireThrows<InvalidOperationException>(() =>
            ValidateProductionConnection(
                typeof(SynchronousValueFunctionParity).GetMethod(
                    nameof(LocalOnlyProbe), BindingFlags.NonPublic | BindingFlags.Static)!,
                firstWrapper, firstCall, "local-only"));
        RequireThrows<InvalidOperationException>(() =>
            ValidateProductionConnection(firstMethod, firstWrapper, $"{firstCall}_removed", "wrong-import"));

        var field = claims.Single(row => row[2] == "csharp.function:006");
        var authorization = claims.Single(row => row[2] == "csharp.function:009");
        RequireThrows<InvalidOperationException>(() =>
            ValidateProductionConnection(
                PublicMethod(field), ExpectedNativeWrapper(authorization[0]), ExpectedNativeCall(authorization[0]),
                "missing-production-edge"));
    }

    private static void LocalOnlyProbe() { }

    private static void VerifyAccept(Fixture fixture)
    {
        var response = fixture.Elicitation.Accept(fixture.ValidContent);
        Check(response.Action == CodexElicitationAction.Accept && response.Content.Count == 2,
            "accept creates a complete response");
        var submitted = (CodexFormValue.TextList)fixture.ValidContent["tags"];
        var accepted = (CodexFormValue.TextList)response.Content["tags"];
        Check(!ReferenceEquals(submitted, accepted) && submitted.Value.SequenceEqual(accepted.Value),
            "accept snapshots nested list values");
        RequireThrows<ArgumentException>(() => fixture.Elicitation.Accept(
            new Dictionary<string, CodexFormValue> { ["name"] = new CodexFormValue.Text(" ") }));
    }

    private static void VerifyInitialValues(Fixture fixture)
    {
        var values = fixture.Elicitation.InitialValues();
        Check(values.Keys.SequenceEqual(["name", "tags"]) && values.Count == 2,
            "initial values preserve field order");
        var source = (CodexFormValue.TextList)fixture.Fields[1].DefaultValue!;
        var projected = (CodexFormValue.TextList)values["tags"];
        Check(!ReferenceEquals(source, projected) && source.Value.SequenceEqual(projected.Value),
            "initial values snapshot nested list values");
        RequireThrows<NotSupportedException>(() => ((IDictionary)values).Clear());
    }

    private static void VerifyValidation(Fixture fixture)
    {
        var content = new Dictionary<string, CodexFormValue>
        {
            ["unknown"] = new CodexFormValue.Text("value"),
            ["tags"] = new CodexFormValue.TextList(["one", "one"]),
        };
        var issues = fixture.Elicitation.Validate(content).Issues;
        Check(issues.SequenceEqual([
            new CodexElicitationValidationIssue("unknown", CodexElicitationValidationReason.UnknownField),
            new CodexElicitationValidationIssue("name", CodexElicitationValidationReason.MissingRequired),
            new CodexElicitationValidationIssue("tags", CodexElicitationValidationReason.DuplicateSelection),
        ]), "validation preserves canonical unknown-then-field issue order");
        Check(fixture.Elicitation.Validate(fixture.ValidContent).IsValid, "valid content has no issues");
    }

    private static void VerifyFormFieldAccepts()
    {
        var email = new CodexFormField(
            "email", "Email", CodexFormFieldType.String, isRequired: true,
            minimumLength: 3, maximumLength: 30, format: CodexFormStringFormat.Email);
        Check(email.Accepts(new CodexFormValue.Text("a@example.com")) &&
            !email.Accepts(null) && !email.Accepts(new CodexFormValue.Text("invalid")) &&
            !email.Accepts(new CodexFormValue.BooleanValue(true)), "string validation");
        Check(new CodexFormField("optional", "Optional", CodexFormFieldType.String).Accepts(null),
            "optional field accepts null");

        var number = new CodexFormField("number", "Number", CodexFormFieldType.Number, minimum: 1, maximum: 2);
        Check(number.Accepts(new CodexFormValue.Number(1.5)) &&
            !number.Accepts(new CodexFormValue.Number(double.NaN)) &&
            !number.Accepts(new CodexFormValue.Number(3)), "number validation");
        var integer = new CodexFormField("integer", "Integer", CodexFormFieldType.Integer);
        Check(integer.Accepts(new CodexFormValue.Number(2)) &&
            !integer.Accepts(new CodexFormValue.Number(2.5)), "integer validation");
        var boolean = new CodexFormField("boolean", "Boolean", CodexFormFieldType.Boolean);
        Check(boolean.Accepts(new CodexFormValue.BooleanValue(true)) &&
            !boolean.Accepts(new CodexFormValue.Text("true")), "Boolean validation");

        var single = new CodexFormField(
            "single", "Single", CodexFormFieldType.SingleSelect,
            options: [new CodexFormOption("one")], allowsOther: true);
        Check(single.Accepts(new CodexFormValue.Text("one")) &&
            single.Accepts(new CodexFormValue.Text("other")) &&
            !single.Accepts(new CodexFormValue.Text(" ")), "single-select validation");
        var multiple = new CodexFormField(
            "multiple", "Multiple", CodexFormFieldType.MultiSelect, isRequired: true,
            options: [new CodexFormOption("one"), new CodexFormOption("two")],
            minimumSelections: 1, maximumSelections: 2);
        Check(multiple.Accepts(new CodexFormValue.TextList(["one", "two"])) &&
            !multiple.Accepts(new CodexFormValue.TextList([])) &&
            !multiple.Accepts(new CodexFormValue.TextList(["one", "one"])) &&
            !multiple.Accepts(new CodexFormValue.TextList(["other"])), "multi-select validation");

        Check(new CodexFormField("date", "Date", CodexFormFieldType.String,
            format: CodexFormStringFormat.Date).Accepts(new CodexFormValue.Text("2024-02-29")), "date validation");
        Check(!new CodexFormField("date", "Date", CodexFormFieldType.String,
            format: CodexFormStringFormat.Date).Accepts(new CodexFormValue.Text("2024- 1-01")),
            "date validation rejects embedded whitespace");
        Check(new CodexFormField("time", "Time", CodexFormFieldType.String,
            format: CodexFormStringFormat.DateTime).Accepts(
                new CodexFormValue.Text("2024-02-29T23:59:60.1+23:59")), "date-time validation");
        Check(new CodexFormField("uri", "URI", CodexFormFieldType.String,
            format: CodexFormStringFormat.Uri).Accepts(new CodexFormValue.Text("custom+scheme:value")),
            "URI validation");
    }

    private static void VerifyIsResolving()
    {
        var conversationId = new CodexConversationId("conversation");
        var live = new CodexPendingApproval("request", conversationId, "Title", "Details");
        var equalButDistinct = new CodexPendingApproval("request", conversationId, "Title", "Details");
        var state = new CodexInteractionState([live], ["request"]);
        Check(state.IsResolving(live) && !state.IsResolving(equalButDistinct),
            "is-resolving requires exact live pending identity");
        Check(!new CodexInteractionState([live]).IsResolving(live),
            "live pending identity is not enough without resolving membership");
    }

    private static void VerifyPendingFor()
    {
        var selected = new CodexConversationId("selected");
        var other = new CodexConversationId("other");
        var first = new CodexPendingApproval("first", selected, "First", "Details");
        var second = new CodexPendingApproval("second", selected, "Second", "Details");
        var state = new CodexInteractionState([
            first, new CodexPendingApproval("other", other, "Other", "Details"), first, second]);
        var pending = state.PendingFor(new CodexConversationId("selected"));
        Check(pending.Count == 3 && ReferenceEquals(pending[0], first) &&
            ReferenceEquals(pending[1], first) && ReferenceEquals(pending[2], second),
            "pending-for preserves order, duplicates, and owned identity");
        Check(state.PendingFor(new CodexConversationId("missing")).Count == 0,
            "pending-for preserves an empty native result");
        RequireThrows<NotSupportedException>(() => ((IList)pending).Clear());
    }

    private sealed class Fixture
    {
        internal Fixture()
        {
            Fields = [
                new CodexFormField(
                    "name", "Name", CodexFormFieldType.String, isRequired: true,
                    defaultValue: new CodexFormValue.Text("Codex")),
                new CodexFormField(
                    "tags", "Tags", CodexFormFieldType.MultiSelect,
                    options: [new CodexFormOption("one"), new CodexFormOption("two")],
                    defaultValue: new CodexFormValue.TextList(["one"])),
            ];
            Elicitation = new CodexElicitation(
                "request", "server", new CodexConversationId("conversation"), "Complete", Fields);
            ValidContent = new Dictionary<string, CodexFormValue>
            {
                ["name"] = new CodexFormValue.Text("Codex"),
                ["tags"] = new CodexFormValue.TextList(["one", "two"]),
            };
        }

        internal IReadOnlyList<CodexFormField> Fields { get; }
        internal CodexElicitation Elicitation { get; }
        internal IReadOnlyDictionary<string, CodexFormValue> ValidContent { get; }
    }

    private static MethodInfo PublicMethod(string[] row)
    {
        var owner = OwnerTypes.Keys.Single(candidate =>
            row[0].StartsWith($"{OwnerPrefix}{candidate}|", StringComparison.Ordinal));
        var methodName = row[1].Split('.').Last();
        return OwnerTypes[owner].GetMethod(
                   methodName, BindingFlags.Public | BindingFlags.Instance | BindingFlags.Static) ??
               throw new InvalidOperationException($"{row[2]}: exact public method exists");
    }

    private static void ValidateObservedCalls(
        IReadOnlyList<string> wrappers,
        string expectedWrapper,
        string testId) =>
        Check(wrappers.Count > 0 && wrappers.All(wrapper => wrapper == expectedWrapper),
            $"{testId}: only the compiler-connected exact native wrapper executed");

    private static void ValidateProductionConnection(
        MethodInfo publicMethod,
        string wrapperName,
        string expectedEntryPoint,
        string testId)
    {
        var bridgeMethods = CalledMethods(publicMethod)
            .Where(method => method.DeclaringType == typeof(NativeValueBridge))
            .ToArray();
        Check(bridgeMethods.Length > 0, $"{testId}: public method reaches NativeValueBridge");

        var wrapper = typeof(NativeMethods).GetMethod(
            wrapperName, BindingFlags.NonPublic | BindingFlags.Static);
        Check(wrapper is not null, $"{testId}: exact NativeValueMethods wrapper exists");
        Check(bridgeMethods.Any(bridge => ReachesNativeWrapper(bridge, wrapper!)),
            $"{testId}: public method reaches the exact NativeValueMethods wrapper");

        var imports = CalledMethods(wrapper!)
            .Select(method => (Method: method, Import: method.GetCustomAttribute<LibraryImportAttribute>()))
            .Where(value => value.Import is not null)
            .ToArray();
        Check(imports.Length == 1 && imports[0].Import!.EntryPoint == expectedEntryPoint,
            $"{testId}: wrapper calls one LibraryImport with the exact claimed entry point");
    }

    internal static void ValidateLeafProductionConnection(
        IReadOnlyList<MethodInfo> publicMethods,
        IReadOnlyList<string> expectedEntryPoints,
        string testId)
    {
        Check(publicMethods.Count > 0 && publicMethods.All(method => method.IsPublic),
            $"{testId}: exact public production members exist");
        foreach (var entryPoint in expectedEntryPoints)
        {
            var wrapperName = string.Concat(entryPoint["codex_agent_".Length..]
                .Split('_', StringSplitOptions.RemoveEmptyEntries)
                .Select(PascalCase));
            var wrapper = typeof(NativeMethods).GetMethod(wrapperName, BindingFlags.NonPublic | BindingFlags.Static);
            Check(wrapper is not null, $"{testId}: exact native wrapper exists for {entryPoint}");
            if (entryPoint == "codex_agent_operation_result")
            {
                Check(publicMethods.Any(method => ReachesBindingMethod(method, called =>
                        called.DeclaringType == typeof(NativeOperation) && called.Name == nameof(NativeOperation.Run))),
                    $"{testId}: claimed public member reaches the canonical operation runner");
                var completion = typeof(NativeOperation).GetNestedType("State`1", BindingFlags.NonPublic)!
                    .GetMethod(nameof(NativeOperation.IState.Complete), BindingFlags.Public | BindingFlags.Instance)!;
                Check(ReachesBindingMethod(completion, wrapper!),
                    $"{testId}: canonical operation completion reaches {wrapperName}");
            }
            else
            {
                Check(publicMethods.Any(method => ReachesBindingMethod(method, wrapper!)),
                    $"{testId}: claimed public member reaches exact wrapper {wrapperName}");
            }
            var imports = CalledMethods(wrapper!)
                .Select(method => method.GetCustomAttribute<LibraryImportAttribute>())
                .Where(attribute => attribute is not null).ToArray();
            Check(imports.Length == 1 && imports[0]!.EntryPoint == entryPoint,
                $"{testId}: exact wrapper has one LibraryImport for {entryPoint}");
        }
    }

    private static IReadOnlyList<MethodInfo> CalledMethods(MethodInfo method)
    {
        var body = method.GetMethodBody()?.GetILAsByteArray() ?? [];
        var calls = new List<MethodInfo>();
        for (var offset = 0; offset < body.Length;)
        {
            var code = body[offset++];
            var operation = code == 0xfe ? MultiByteOpCodes[body[offset++]] : SingleByteOpCodes[code];
            var operandOffset = offset;
            if (operation.OperandType == OperandType.InlineMethod)
            {
                var token = BitConverter.ToInt32(body, operandOffset);
                if (method.Module.ResolveMethod(
                        token,
                        method.DeclaringType?.GetGenericArguments(),
                        method.GetGenericArguments()) is MethodInfo called)
                    calls.Add(called);
            }
            offset += OperandSize(operation.OperandType, body, operandOffset);
        }
        return calls;
    }

    private static bool ReachesNativeWrapper(MethodInfo start, MethodInfo wrapper)
    {
        var pending = new Queue<MethodInfo>();
        var visited = new HashSet<(Module Module, int Token)>();
        pending.Enqueue(start);
        while (pending.TryDequeue(out var method))
        {
            if (!visited.Add((method.Module, method.MetadataToken))) continue;
            var stateMachineType = method.GetCustomAttribute<System.Runtime.CompilerServices.AsyncIteratorStateMachineAttribute>()?.StateMachineType ??
                method.GetCustomAttribute<System.Runtime.CompilerServices.AsyncStateMachineAttribute>()?.StateMachineType;
            if (stateMachineType?.GetMethod("MoveNext", BindingFlags.NonPublic | BindingFlags.Instance) is { } moveNext)
                pending.Enqueue(moveNext);
            foreach (var called in CalledMethods(method))
            {
                if (SameMethod(called, wrapper)) return true;
                if (IsBridgeImplementation(called.DeclaringType)) pending.Enqueue(called);
            }
        }
        return false;
    }

    private static bool ReachesBindingMethod(MethodInfo start, MethodInfo target)
        => ReachesBindingMethod(start, called => SameMethod(called, target));

    private static bool ReachesBindingMethod(MethodInfo start, Func<MethodInfo, bool> matches)
    {
        var bindingAssembly = typeof(CodexAgent.CodexAgent).Assembly;
        var pending = new Queue<MethodInfo>();
        var visited = new HashSet<(Module Module, int Token)>();
        pending.Enqueue(start);
        while (pending.TryDequeue(out var method))
        {
            if (!visited.Add((method.Module, method.MetadataToken))) continue;
            var stateMachineType = method.GetCustomAttribute<System.Runtime.CompilerServices.AsyncIteratorStateMachineAttribute>()?.StateMachineType ??
                method.GetCustomAttribute<System.Runtime.CompilerServices.AsyncStateMachineAttribute>()?.StateMachineType;
            if (stateMachineType?.GetMethod("MoveNext", BindingFlags.NonPublic | BindingFlags.Instance) is { } moveNext)
                pending.Enqueue(moveNext);
            foreach (var called in CalledMethods(method))
            {
                if (matches(called)) return true;
                if (called.Module.Assembly == bindingAssembly) pending.Enqueue(called);
            }
        }
        return false;
    }

    private static bool IsBridgeImplementation(Type? type) =>
        type == typeof(NativeValueBridge) || type?.DeclaringType == typeof(NativeValueBridge);

    private static int OperandSize(OperandType type, byte[] body, int offset) => type switch
    {
        OperandType.InlineNone => 0,
        OperandType.ShortInlineBrTarget or OperandType.ShortInlineI or OperandType.ShortInlineVar => 1,
        OperandType.InlineVar => 2,
        OperandType.InlineI or OperandType.InlineBrTarget or OperandType.InlineField or
            OperandType.InlineMethod or OperandType.InlineSig or OperandType.InlineString or
            OperandType.InlineTok or OperandType.InlineType or OperandType.ShortInlineR => 4,
        OperandType.InlineI8 or OperandType.InlineR => 8,
        OperandType.InlineSwitch => 4 + BitConverter.ToInt32(body, offset) * 4,
        _ => throw new InvalidOperationException($"Unsupported IL operand type {type}."),
    };

    private static bool SameMethod(MethodInfo left, MethodInfo right) =>
        left.Module == right.Module && left.MetadataToken == right.MetadataToken;

    private static readonly OpCode[] SingleByteOpCodes = BuildOpCodes(false);
    private static readonly OpCode[] MultiByteOpCodes = BuildOpCodes(true);

    private static OpCode[] BuildOpCodes(bool multiByte)
    {
        var result = new OpCode[256];
        foreach (var field in typeof(OpCodes).GetFields(BindingFlags.Public | BindingFlags.Static))
        {
            var operation = (OpCode)field.GetValue(null)!;
            var value = unchecked((ushort)operation.Value);
            if ((value > byte.MaxValue) == multiByte) result[value & byte.MaxValue] = operation;
        }
        return result;
    }

    private static string ExpectedScenarios(string capability)
    {
        var scenarios = new List<string> { "value-conversion" };
        if (capability.Contains('?')) scenarios.Add("nullability");
        if (capability.Contains("kotlin.collections", StringComparison.Ordinal))
            scenarios.Add("collection-immutability-ordering");
        scenarios.Sort(StringComparer.Ordinal);
        return string.Join(',', scenarios);
    }

    private static string PascalCase(string value) => char.ToUpperInvariant(value[0]) + value[1..];

    private static string ExpectedNativeCall(string capability)
    {
        var owner = Between(capability, "owner=io.github.codex_agent_labs.codexagent.agent/", "|")
            .Replace(".Companion", "", StringComparison.Ordinal);
        if (owner.StartsWith("Agent", StringComparison.Ordinal)) owner = owner[5..];
        else if (owner.StartsWith("Codex", StringComparison.Ordinal)) owner = owner[5..];
        var signature = Between(capability, "|abi=", "|");
        var member = signature.Split('.').Last();
        return $"codex_agent_{SnakeCase(owner)}_{SnakeCase(member)}";
    }

    private static string ExpectedNativeWrapper(string capability) => string.Concat(
        ExpectedNativeCall(capability)["codex_agent_".Length..]
            .Split('_').Select(part => char.ToUpperInvariant(part[0]) + part[1..]));

    private static string SnakeCase(string value) => string.Concat(value.Select((character, index) =>
        index > 0 && char.IsUpper(character) ? $"_{char.ToLowerInvariant(character)}" :
        char.ToLowerInvariant(character).ToString()));

    private static string Between(string value, string prefix, string suffix)
    {
        var start = value.IndexOf(prefix, StringComparison.Ordinal) + prefix.Length;
        var end = value.IndexOf(suffix, start, StringComparison.Ordinal);
        return value[start..end];
    }

    private static void RequireThrows<T>(Action action) where T : Exception
    {
        try { action(); }
        catch (T) { return; }
        throw new InvalidOperationException($"Expected {typeof(T).Name}.");
    }

    private static void Check(bool condition, string message)
    {
        if (!condition) throw new InvalidOperationException(message);
    }
}
