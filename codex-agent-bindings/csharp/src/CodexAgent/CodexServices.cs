using CodexAgent.Interop;
using System.Runtime.CompilerServices;

namespace CodexAgent;

/// <summary>Authentication operations and observable authentication state.</summary>
public sealed unsafe class CodexAuthentication : IDisposable, IAsyncDisposable
{
    private readonly NativeService service;
    internal CodexAuthentication(ServiceHandle handle) => service = new NativeService(handle);

    /// <summary>The current authentication state.</summary>
    public CodexAuthenticationState State => service.Current(NativeMethods.AuthenticationStateGet, NativeLeafCodec.AuthenticationState);
    /// <summary>Observes authentication-state changes until cancellation or owner termination.</summary>
    public IAsyncEnumerable<CodexAuthenticationState> ObserveStateAsync(CancellationToken cancellationToken = default) =>
        service.Observe((nint owner, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription) => NativeMethods.AuthenticationStateSubscribe(service.Handle.Context.Pointer, owner, callback, userData, out subscription), NativeLeafCodec.AuthenticationState, cancellationToken);
    /// <summary>Whether the agent is authenticated.</summary>
    public bool IsAuthenticated => service.Current(NativeMethods.AuthenticationIsAuthenticatedGet, NativeLeafCodec.BooleanState);
    /// <summary>Observes authentication-status changes.</summary>
    public IAsyncEnumerable<bool> ObserveIsAuthenticatedAsync(CancellationToken cancellationToken = default) =>
        service.Observe((nint owner, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription) => NativeMethods.AuthenticationIsAuthenticatedSubscribe(service.Handle.Context.Pointer, owner, callback, userData, out subscription), NativeLeafCodec.BooleanState, cancellationToken);
    /// <summary>Whether authentication is in progress.</summary>
    public bool IsAuthenticating => service.Current(NativeMethods.AuthenticationIsAuthenticatingGet, NativeLeafCodec.BooleanState);
    /// <summary>Observes authentication-progress changes.</summary>
    public IAsyncEnumerable<bool> ObserveIsAuthenticatingAsync(CancellationToken cancellationToken = default) =>
        service.Observe((nint owner, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription) => NativeMethods.AuthenticationIsAuthenticatingSubscribe(service.Handle.Context.Pointer, owner, callback, userData, out subscription), NativeLeafCodec.BooleanState, cancellationToken);

    /// <summary>Authenticates with the selected method.</summary>
    public Task AuthenticateAsync(CodexAuthenticationMethod method, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(method);
        return NativeLeafCodec.WithAuthenticationMethod(service.Handle, method, native => method switch
        {
            CodexAuthenticationMethod.ApiKey => service.Run(cancellationToken,
                (nint owner, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation) => NativeMethods.AuthenticationAuthenticateApiKey(service.Handle.Context.Pointer, owner, native, callback, userData, out operation)),
            CodexAuthenticationMethod.ChatGptBrowser => service.Run(cancellationToken,
                (nint owner, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation) => NativeMethods.AuthenticationAuthenticateChatGptBrowser(service.Handle.Context.Pointer, owner, native, callback, userData, out operation)),
            CodexAuthenticationMethod.ChatGptDeviceCode => service.Run(cancellationToken,
                (nint owner, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation) => NativeMethods.AuthenticationAuthenticateChatGptDeviceCode(service.Handle.Context.Pointer, owner, native, callback, userData, out operation)),
            _ => throw new ArgumentOutOfRangeException(nameof(method)),
        });
    }
    /// <summary>Cancels the active authentication attempt.</summary>
    public Task CancelAsync(CancellationToken cancellationToken = default) => service.Run(cancellationToken,
        (nint owner, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation) => NativeMethods.AuthenticationCancel(service.Handle.Context.Pointer, owner, callback, userData, out operation));
    /// <summary>Signs out the current account.</summary>
    public Task SignOutAsync(CancellationToken cancellationToken = default) => service.Run(cancellationToken,
        (nint owner, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation) => NativeMethods.AuthenticationSignOut(service.Handle.Context.Pointer, owner, callback, userData, out operation));
    /// <inheritdoc />
    public void Dispose() => service.DisposeOwned();
    /// <inheritdoc />
    public ValueTask DisposeAsync() { Dispose(); return ValueTask.CompletedTask; }
}

/// <summary>Connector discovery operations.</summary>
public sealed unsafe class CodexConnectors : IDisposable, IAsyncDisposable
{
    private readonly NativeService service;
    internal CodexConnectors(ServiceHandle handle) => service = new NativeService(handle);
    /// <summary>Whether connector support is available.</summary>
    public bool IsAvailable => service.Available((context, owner) => { var status = NativeMethods.ConnectorsIsAvailable(context, owner, out var value); return (status, value); });
    /// <summary>Lists connectors in canonical order.</summary>
    public Task<IReadOnlyList<CodexConnector>> ListAsync(bool forceReload = false, CancellationToken cancellationToken = default) =>
        service.Run(cancellationToken,
            (nint owner, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation) => NativeMethods.ConnectorsList(service.Handle.Context.Pointer, owner, forceReload ? 1 : 0, callback, userData, out operation),
            NativeLeafCodec.OperationConnectors);
    /// <inheritdoc />
    public void Dispose() => service.DisposeOwned();
    /// <inheritdoc />
    public ValueTask DisposeAsync() { Dispose(); return ValueTask.CompletedTask; }
}

/// <summary>Model discovery and resolution operations.</summary>
public sealed unsafe class CodexModels : IDisposable, IAsyncDisposable
{
    private readonly NativeService service;
    internal CodexModels(ServiceHandle handle) => service = new NativeService(handle);
    /// <summary>Lists available models in canonical order.</summary>
    public Task<IReadOnlyList<CodexModel>> ListAsync(CancellationToken cancellationToken = default) => service.Run(cancellationToken,
        (nint owner, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation) => NativeMethods.ModelsList(service.Handle.Context.Pointer, owner, callback, userData, out operation), NativeLeafCodec.OperationModels);
    /// <summary>Resolves the model for a resolution policy.</summary>
    public Task<CodexModel> ResolveAsync(CodexResolution resolution = CodexResolution.Preferred, CancellationToken cancellationToken = default) => service.Run(cancellationToken,
        (nint owner, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation) => NativeMethods.ModelsResolve(service.Handle.Context.Pointer, owner, resolution, callback, userData, out operation), NativeLeafCodec.OperationModel);
    /// <summary>Resolves the reasoning effort for a model.</summary>
    public Task<string> ResolveEffortAsync(CodexModel model, CodexResolution resolution = CodexResolution.Preferred, CancellationToken cancellationToken = default) =>
        NativeLeafCodec.WithModel(service.Handle, model, native => service.Run(cancellationToken,
            (nint owner, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation) => NativeMethods.ModelsResolveEffort(service.Handle.Context.Pointer, owner, native, resolution, callback, userData, out operation), NativeLeafCodec.OperationString));
    /// <summary>Resolves the optional service tier for a model.</summary>
    public Task<CodexServiceTier?> ResolveServiceTierAsync(CodexModel model, CodexResolution resolution = CodexResolution.Preferred, CancellationToken cancellationToken = default) =>
        NativeLeafCodec.WithModel(service.Handle, model, native => service.Run(cancellationToken,
            (nint owner, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation) => NativeMethods.ModelsResolveServiceTier(service.Handle.Context.Pointer, owner, native, resolution, callback, userData, out operation), NativeLeafCodec.OperationServiceTier));
    /// <inheritdoc />
    public void Dispose() => service.DisposeOwned();
    /// <inheritdoc />
    public ValueTask DisposeAsync() { Dispose(); return ValueTask.CompletedTask; }
}

/// <summary>Skill catalog and installation operations.</summary>
public sealed unsafe class CodexSkills : IDisposable, IAsyncDisposable
{
    private readonly NativeService service;
    internal CodexSkills(ServiceHandle handle) => service = new NativeService(handle);
    /// <summary>Whether skill support is available.</summary>
    public bool IsAvailable => service.Available((context, owner) => { var status = NativeMethods.SkillsIsAvailable(context, owner, out var value); return (status, value); });
    /// <summary>Lists installed skills.</summary>
    public Task<CodexSkillCatalog> ListAsync(bool forceReload = false, CancellationToken cancellationToken = default) => service.Run(cancellationToken,
        (nint owner, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation) => NativeMethods.SkillsList(service.Handle.Context.Pointer, owner, forceReload ? 1 : 0, callback, userData, out operation), NativeLeafCodec.OperationSkillCatalog);
    /// <summary>Reads a skill starting at a byte offset.</summary>
    public Task<CodexSkillChunk> ReadAsync(string path, long offset = 0, CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(path);
        return NativeLeafCodec.WithStringAsync(path, view => service.Run(cancellationToken,
            (nint owner, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation) => NativeMethods.SkillsRead(service.Handle.Context.Pointer, owner, view, offset, callback, userData, out operation), NativeLeafCodec.OperationSkillChunk));
    }
    /// <summary>Installs a skill from a directory.</summary>
    public Task<CodexSkill> InstallAsync(string directory, CodexInstallationScope scope, CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(directory);
        return NativeLeafCodec.WithStringAsync(directory, view => service.Run(cancellationToken,
            (nint owner, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation) => NativeMethods.SkillsInstall(service.Handle.Context.Pointer, owner, view, scope, callback, userData, out operation), NativeLeafCodec.OperationSkill));
    }
    /// <summary>Uninstalls a skill.</summary>
    public Task UninstallAsync(CodexSkill skill, CancellationToken cancellationToken = default) => NativeLeafCodec.WithSkill(service.Handle, skill, native => service.Run(cancellationToken,
        (nint owner, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation) => NativeMethods.SkillsUninstall(service.Handle.Context.Pointer, owner, native, callback, userData, out operation)));
    /// <inheritdoc />
    public void Dispose() => service.DisposeOwned();
    /// <inheritdoc />
    public ValueTask DisposeAsync() { Dispose(); return ValueTask.CompletedTask; }
}

/// <summary>Hook catalog, trust, and installation operations.</summary>
public sealed unsafe class CodexHooks : IDisposable, IAsyncDisposable
{
    private readonly NativeService service;
    internal CodexHooks(ServiceHandle handle) => service = new NativeService(handle);
    /// <summary>Whether hook support is available.</summary>
    public bool IsAvailable => service.Available((context, owner) => { var status = NativeMethods.HooksIsAvailable(context, owner, out var value); return (status, value); });
    /// <summary>Lists hooks.</summary>
    public Task<CodexHookCatalog> ListAsync(CancellationToken cancellationToken = default) => service.Run(cancellationToken,
        (nint owner, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation) => NativeMethods.HooksList(service.Handle.Context.Pointer, owner, callback, userData, out operation), NativeLeafCodec.OperationHookCatalog);
    /// <summary>Installs a hook from a directory.</summary>
    public Task<CodexHook> InstallAsync(string directory, CodexInstallationScope scope, CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(directory);
        return NativeLeafCodec.WithStringAsync(directory, view => service.Run(cancellationToken,
            (nint owner, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation) => NativeMethods.HooksInstall(service.Handle.Context.Pointer, owner, view, scope, callback, userData, out operation), NativeLeafCodec.OperationHook));
    }
    /// <summary>Uninstalls a hook.</summary>
    public Task UninstallAsync(CodexHook hook, CancellationToken cancellationToken = default) => NativeLeafCodec.WithHook(service.Handle, hook, native => service.Run(cancellationToken,
        (nint owner, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation) => NativeMethods.HooksUninstall(service.Handle.Context.Pointer, owner, native, callback, userData, out operation)));
    /// <summary>Trusts a hook.</summary>
    public Task TrustAsync(CodexHook hook, CancellationToken cancellationToken = default) => NativeLeafCodec.WithHook(service.Handle, hook, native => service.Run(cancellationToken,
        (nint owner, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation) => NativeMethods.HooksTrust(service.Handle.Context.Pointer, owner, native, callback, userData, out operation)));
    /// <inheritdoc />
    public void Dispose() => service.DisposeOwned();
    /// <inheritdoc />
    public ValueTask DisposeAsync() { Dispose(); return ValueTask.CompletedTask; }
}

/// <summary>Plugin catalog and installation operations.</summary>
public sealed unsafe class CodexPlugins : IDisposable, IAsyncDisposable
{
    private readonly NativeService service;
    internal CodexPlugins(ServiceHandle handle) => service = new NativeService(handle);
    /// <summary>Whether plugin support is available.</summary>
    public bool IsAvailable => service.Available((context, owner) => { var status = NativeMethods.PluginsIsAvailable(context, owner, out var value); return (status, value); });
    /// <summary>Lists plugins.</summary>
    public Task<CodexPluginCatalog> ListAsync(bool forceReload = false, CancellationToken cancellationToken = default) => service.Run(cancellationToken,
        (nint owner, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation) => NativeMethods.PluginsList(service.Handle.Context.Pointer, owner, forceReload ? 1 : 0, callback, userData, out operation), NativeLeafCodec.OperationPluginCatalog);
    /// <summary>Reads plugin details.</summary>
    public Task<CodexPluginDetail> ReadAsync(CodexPluginReference plugin, CancellationToken cancellationToken = default) => NativeLeafCodec.WithPluginReference(service.Handle, plugin, native => service.Run(cancellationToken,
        (nint owner, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation) => NativeMethods.PluginsRead(service.Handle.Context.Pointer, owner, native, callback, userData, out operation), NativeLeafCodec.OperationPluginDetail));
    /// <summary>Installs a plugin.</summary>
    public Task<CodexPluginInstallResult> InstallAsync(CodexPluginReference plugin, CancellationToken cancellationToken = default) => NativeLeafCodec.WithPluginReference(service.Handle, plugin, native => service.Run(cancellationToken,
        (nint owner, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation) => NativeMethods.PluginsInstall(service.Handle.Context.Pointer, owner, native, callback, userData, out operation), NativeLeafCodec.OperationPluginInstallResult));
    /// <summary>Uninstalls a plugin.</summary>
    public Task UninstallAsync(CodexPluginReference plugin, CancellationToken cancellationToken = default) => NativeLeafCodec.WithPluginReference(service.Handle, plugin, native => service.Run(cancellationToken,
        (nint owner, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation) => NativeMethods.PluginsUninstall(service.Handle.Context.Pointer, owner, native, callback, userData, out operation)));
    /// <inheritdoc />
    public void Dispose() => service.DisposeOwned();
    /// <inheritdoc />
    public ValueTask DisposeAsync() { Dispose(); return ValueTask.CompletedTask; }
}

/// <summary>Integration authorization operations and observable state.</summary>
public sealed unsafe class CodexIntegrationAuthorization : IDisposable, IAsyncDisposable
{
    private readonly NativeService service;
    internal CodexIntegrationAuthorization(ServiceHandle handle) => service = new NativeService(handle);
    /// <summary>The current authorization state.</summary>
    public CodexIntegrationAuthorizationState State => service.Current(NativeMethods.IntegrationAuthorizationStateGet, NativeLeafCodec.IntegrationAuthorizationState);
    /// <summary>Observes authorization-state changes.</summary>
    public IAsyncEnumerable<CodexIntegrationAuthorizationState> ObserveStateAsync(CancellationToken cancellationToken = default) =>
        service.Observe((nint owner, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription) => NativeMethods.IntegrationAuthorizationStateSubscribe(service.Handle.Context.Pointer, owner, callback, userData, out subscription), NativeLeafCodec.IntegrationAuthorizationState, cancellationToken);
    /// <summary>The integration currently being authorized, if any.</summary>
    public CodexIntegration? Active => service.Current(NativeMethods.IntegrationAuthorizationActiveGet, NativeLeafCodec.ActiveIntegration);
    /// <summary>Observes changes to the active integration.</summary>
    public IAsyncEnumerable<CodexIntegration?> ObserveActiveAsync(CancellationToken cancellationToken = default) =>
        service.Observe((nint owner, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription) => NativeMethods.IntegrationAuthorizationActiveSubscribe(service.Handle.Context.Pointer, owner, callback, userData, out subscription), NativeLeafCodec.ActiveIntegration, cancellationToken);
    /// <summary>Whether authorization is in progress.</summary>
    public bool IsAuthorizing => service.Current(NativeMethods.IntegrationAuthorizationIsAuthorizingGet, NativeLeafCodec.BooleanState);
    /// <summary>Observes authorization-progress changes.</summary>
    public IAsyncEnumerable<bool> ObserveIsAuthorizingAsync(CancellationToken cancellationToken = default) =>
        service.Observe((nint owner, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription) => NativeMethods.IntegrationAuthorizationIsAuthorizingSubscribe(service.Handle.Context.Pointer, owner, callback, userData, out subscription), NativeLeafCodec.BooleanState, cancellationToken);
    /// <summary>Authorizes an integration.</summary>
    public Task AuthorizeAsync(CodexIntegration target, CancellationToken cancellationToken = default) => NativeLeafCodec.WithIntegration(service.Handle, target, native => service.Run(cancellationToken,
        (nint owner, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation) => NativeMethods.IntegrationAuthorizationAuthorize(service.Handle.Context.Pointer, owner, native, callback, userData, out operation)));
    /// <summary>Cancels active integration authorization.</summary>
    public Task CancelAsync(CancellationToken cancellationToken = default) => service.Run(cancellationToken,
        (nint owner, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation) => NativeMethods.IntegrationAuthorizationCancel(service.Handle.Context.Pointer, owner, callback, userData, out operation));
    /// <inheritdoc />
    public void Dispose() => service.DisposeOwned();
    /// <inheritdoc />
    public ValueTask DisposeAsync() { Dispose(); return ValueTask.CompletedTask; }
}

/// <summary>Observable pending interactions and resolution operations.</summary>
public sealed unsafe class CodexInteractions : IDisposable, IAsyncDisposable
{
    private readonly NativeService service;
    private readonly NativePendingRegistry pending;
    internal CodexInteractions(ServiceHandle handle) { service = new NativeService(handle); pending = new NativePendingRegistry(handle.Context); }
    /// <summary>The current interaction state.</summary>
    public CodexInteractionState State => service.Current(NativeMethods.InteractionsStateGet, (owner, snapshot) => NativeLeafCodec.InteractionState(pending, owner, snapshot));
    /// <summary>Observes interaction-state changes.</summary>
    public IAsyncEnumerable<CodexInteractionState> ObserveStateAsync(CancellationToken cancellationToken = default) =>
        service.Observe((nint owner, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription) => NativeMethods.InteractionsStateSubscribe(service.Handle.Context.Pointer, owner, callback, userData, out subscription), (owner, snapshot) => NativeLeafCodec.InteractionState(pending, owner, snapshot), cancellationToken);
    /// <summary>The current pending approvals.</summary>
    public IReadOnlyList<CodexPendingApproval> Approvals => service.Current(NativeMethods.InteractionsApprovalsGet, (owner, snapshot) => NativeLeafCodec.Approvals(pending, owner, snapshot));
    /// <summary>Observes pending-approval changes.</summary>
    public IAsyncEnumerable<IReadOnlyList<CodexPendingApproval>> ObserveApprovalsAsync(CancellationToken cancellationToken = default) =>
        service.Observe((nint owner, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription) => NativeMethods.InteractionsApprovalsSubscribe(service.Handle.Context.Pointer, owner, callback, userData, out subscription), (owner, snapshot) => NativeLeafCodec.Approvals(pending, owner, snapshot), cancellationToken);
    /// <summary>The current pending elicitations.</summary>
    public IReadOnlyList<CodexPendingElicitation> Elicitations => service.Current(NativeMethods.InteractionsElicitationsGet, (owner, snapshot) => NativeLeafCodec.Elicitations(pending, owner, snapshot));
    /// <summary>Observes pending-elicitation changes.</summary>
    public IAsyncEnumerable<IReadOnlyList<CodexPendingElicitation>> ObserveElicitationsAsync(CancellationToken cancellationToken = default) =>
        service.Observe((nint owner, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription) => NativeMethods.InteractionsElicitationsSubscribe(service.Handle.Context.Pointer, owner, callback, userData, out subscription), (owner, snapshot) => NativeLeafCodec.Elicitations(pending, owner, snapshot), cancellationToken);
    /// <summary>Resolves a live pending approval.</summary>
    public Task ResolveAsync(CodexPendingApproval approval, CodexApprovalDecision decision, CancellationToken cancellationToken = default) =>
        pending.Use(approval, native => service.Run(cancellationToken,
            (nint owner, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation) => NativeMethods.InteractionsResolveApproval(service.Handle.Context.Pointer, owner, native, decision, callback, userData, out operation)));
    /// <summary>Resolves a live pending elicitation.</summary>
    public Task ResolveAsync(CodexPendingElicitation elicitation, CodexElicitationResponse response, CancellationToken cancellationToken = default) =>
        pending.Use(elicitation, native => NativeLeafCodec.WithElicitationResponse(service.Handle, response, encoded => service.Run(cancellationToken,
            (nint owner, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation) => NativeMethods.InteractionsResolveElicitation(service.Handle.Context.Pointer, owner, native, encoded, callback, userData, out operation))));
    /// <summary>Opens the URL of a live pending elicitation.</summary>
    public Task OpenUrlAsync(CodexPendingElicitation elicitation, CancellationToken cancellationToken = default) =>
        pending.Use(elicitation, native => service.Run(cancellationToken,
            (nint owner, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation) => NativeMethods.InteractionsOpenUrl(service.Handle.Context.Pointer, owner, native, callback, userData, out operation)));
    /// <inheritdoc />
    public void Dispose() { pending.Dispose(); service.DisposeOwned(); }
    /// <inheritdoc />
    public ValueTask DisposeAsync() { Dispose(); return ValueTask.CompletedTask; }
}

/// <summary>MCP server catalog and lifecycle operations.</summary>
public sealed unsafe class CodexMcpServers : IDisposable, IAsyncDisposable
{
    private readonly NativeService service;
    internal CodexMcpServers(ServiceHandle handle) => service = new NativeService(handle);
    /// <summary>Whether MCP server support is available.</summary>
    public bool IsAvailable => service.Available((context, owner) => { var status = NativeMethods.McpServersIsAvailable(context, owner, out var value); return (status, value); });
    /// <summary>Lists configured MCP servers.</summary>
    public Task<IReadOnlyList<CodexMcpServer>> ListAsync(CancellationToken cancellationToken = default) => service.Run(cancellationToken,
        (nint owner, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation) => NativeMethods.McpServersList(service.Handle.Context.Pointer, owner, callback, userData, out operation), NativeLeafCodec.OperationMcpServers);
    /// <summary>Adds an MCP server configuration.</summary>
    public Task<CodexMcpServer> AddAsync(CodexMcpServerConfiguration configuration, CancellationToken cancellationToken = default) => NativeLeafCodec.WithMcpConfiguration(service.Handle, configuration, native => service.Run(cancellationToken,
        (nint owner, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation) => NativeMethods.McpServersAdd(service.Handle.Context.Pointer, owner, native, callback, userData, out operation), NativeLeafCodec.OperationMcpServer));
    /// <summary>Removes an MCP server.</summary>
    public Task RemoveAsync(CodexMcpServer server, CancellationToken cancellationToken = default) => NativeLeafCodec.WithMcpServer(service.Handle, server, native => service.Run(cancellationToken,
        (nint owner, delegate* unmanaged[Cdecl]<nint, nint, nint, void> callback, nint userData, out nint operation) => NativeMethods.McpServersRemove(service.Handle.Context.Pointer, owner, native, callback, userData, out operation)));
    /// <inheritdoc />
    public void Dispose() => service.DisposeOwned();
    /// <inheritdoc />
    public ValueTask DisposeAsync() { Dispose(); return ValueTask.CompletedTask; }
}
