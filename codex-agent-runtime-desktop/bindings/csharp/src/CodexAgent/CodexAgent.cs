using CodexAgent.Interop;

namespace CodexAgent;

/// <summary>The stable user-facing agent owned by a ready host.</summary>
public sealed class CodexAgent
{
    private readonly AgentHandle handle;
    private readonly object gate = new();
    private CodexAuthentication? authentication;
    private CodexConnectors? connectors;
    private CodexConversations? conversations;
    private CodexHooks? hooks;
    private CodexIntegrationAuthorization? integrationAuthorization;
    private CodexInteractions? interactions;
    private CodexMcpServers? mcpServers;
    private CodexModels? models;
    private CodexPlugins? plugins;
    private CodexSkills? skills;
    private CodexWorkspace? workspace;

    internal CodexAgent(AgentHandle handle) => this.handle = handle;

    /// <summary>Authentication operations and state.</summary>
    public CodexAuthentication Authentication { get { lock (gate) return authentication ??= OpenAuthentication(); } }

    /// <summary>Connector catalog operations.</summary>
    public CodexConnectors Connectors { get { lock (gate) return connectors ??= OpenConnectors(); } }

    /// <summary>Conversation catalog and lifecycle operations.</summary>
    public CodexConversations Conversations { get { lock (gate) return conversations ??= CreateConversations(); } }

    /// <summary>Hook catalog operations.</summary>
    public CodexHooks Hooks { get { lock (gate) return hooks ??= OpenHooks(); } }

    /// <summary>Integration authorization operations and state.</summary>
    public CodexIntegrationAuthorization IntegrationAuthorization { get { lock (gate) return integrationAuthorization ??= OpenIntegrationAuthorization(); } }

    /// <summary>User-interaction operations and state.</summary>
    public CodexInteractions Interactions { get { lock (gate) return interactions ??= OpenInteractions(); } }

    /// <summary>MCP server operations.</summary>
    public CodexMcpServers McpServers { get { lock (gate) return mcpServers ??= OpenMcpServers(); } }

    /// <summary>Model catalog operations.</summary>
    public CodexModels Models { get { lock (gate) return models ??= OpenModels(); } }

    /// <summary>Plugin catalog operations.</summary>
    public CodexPlugins Plugins { get { lock (gate) return plugins ??= OpenPlugins(); } }

    /// <summary>Skill catalog operations.</summary>
    public CodexSkills Skills { get { lock (gate) return skills ??= OpenSkills(); } }

    /// <summary>The immutable workspace snapshot owned by this agent.</summary>
    public CodexWorkspace Workspace { get { lock (gate) return workspace ??= CreateWorkspace(); } }

    private CodexConversations CreateConversations() => handle.Use(pointer =>
    {
        NativeApi.ThrowIfFailed(
            NativeMethods.AgentConversations(handle.Context.Pointer, pointer, out var value),
            "open conversation service");
        return new CodexConversations(new ConversationsHandle(handle.Context, value));
    });

    private unsafe CodexWorkspace CreateWorkspace() => handle.Use(pointer =>
    {
        NativeApi.ThrowIfFailed(
            NativeMethods.AgentWorkspace(handle.Context.Pointer, pointer, out var value),
            "read agent workspace");
        try
        {
            var path = NativeApi.CopyString((byte* buffer, nuint capacity, out nuint required) =>
                NativeMethods.WorkspacePathCopy(handle.Context.Pointer, value, buffer, capacity, out required));
            var displayName = NativeApi.CopyString((byte* buffer, nuint capacity, out nuint required) =>
                NativeMethods.WorkspaceDisplayNameCopy(handle.Context.Pointer, value, buffer, capacity, out required));
            return new CodexWorkspace(path, displayName);
        }
        finally
        {
            NativeApi.ThrowIfFailed(NativeMethods.WorkspaceDestroy(handle.Context.Pointer, ref value), "destroy agent workspace");
        }
    });

    internal CodexAuthentication OpenAuthentication() =>
        new(OpenService(NativeMethods.AgentAuthentication, NativeMethods.AuthenticationRelease, "authentication"));
    internal CodexInteractions OpenInteractions() =>
        new(OpenService(NativeMethods.AgentInteractions, NativeMethods.InteractionsRelease, "interactions"));
    internal CodexIntegrationAuthorization OpenIntegrationAuthorization() =>
        new(OpenService(NativeMethods.AgentIntegrationAuthorization, NativeMethods.IntegrationAuthorizationRelease, "integration authorization"));
    internal CodexModels OpenModels() =>
        new(OpenService(NativeMethods.AgentModels, NativeMethods.ModelsRelease, "models"));
    internal CodexSkills OpenSkills() =>
        new(OpenService(NativeMethods.AgentSkills, NativeMethods.SkillsRelease, "skills"));
    internal CodexHooks OpenHooks() =>
        new(OpenService(NativeMethods.AgentHooks, NativeMethods.HooksRelease, "hooks"));
    internal CodexPlugins OpenPlugins() =>
        new(OpenService(NativeMethods.AgentPlugins, NativeMethods.PluginsRelease, "plugins"));
    internal CodexConnectors OpenConnectors() =>
        new(OpenService(NativeMethods.AgentConnectors, NativeMethods.ConnectorsRelease, "connectors"));
    internal CodexMcpServers OpenMcpServers() =>
        new(OpenService(NativeMethods.AgentMcpServers, NativeMethods.McpServersRelease, "MCP servers"));

    private ServiceHandle OpenService(ServiceGetter getter, NativeHandleRelease release, string name) => handle.Use(pointer =>
    {
        NativeApi.ThrowIfFailed(getter(handle.Context.Pointer, pointer, out var service), $"open {name} service");
        return new ServiceHandle(handle.Context, service, release);
    });

    private delegate CodexStatus ServiceGetter(nint context, nint agent, out nint service);

    internal void DisposeOwned()
    {
        lock (gate)
        {
            authentication?.Dispose();
            connectors?.Dispose();
            conversations?.DisposeOwned();
            hooks?.Dispose();
            integrationAuthorization?.Dispose();
            interactions?.Dispose();
            mcpServers?.Dispose();
            models?.Dispose();
            plugins?.Dispose();
            skills?.Dispose();
            handle.DisposeChecked();
        }
    }
}
