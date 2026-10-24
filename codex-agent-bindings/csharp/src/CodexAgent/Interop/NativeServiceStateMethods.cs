using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;

namespace CodexAgent.Interop;

internal static unsafe partial class NativeMethods
{
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_authentication_state_get")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus AuthenticationStateGetImport(nint context, nint service, out nint snapshot);
    internal static CodexStatus AuthenticationStateGet(nint context, nint service, out nint snapshot)
    { var status = AuthenticationStateGetImport(context, service, out snapshot); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_authentication_state_subscribe")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus AuthenticationStateSubscribeImport(nint context, nint service, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription);
    internal static CodexStatus AuthenticationStateSubscribe(nint context, nint service, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription)
    { var status = AuthenticationStateSubscribeImport(context, service, callback, userData, out subscription); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_authentication_is_authenticated_get")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus AuthenticationIsAuthenticatedGetImport(nint context, nint service, out nint snapshot);
    internal static CodexStatus AuthenticationIsAuthenticatedGet(nint context, nint service, out nint snapshot)
    { var status = AuthenticationIsAuthenticatedGetImport(context, service, out snapshot); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_authentication_is_authenticated_subscribe")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus AuthenticationIsAuthenticatedSubscribeImport(nint context, nint service, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription);
    internal static CodexStatus AuthenticationIsAuthenticatedSubscribe(nint context, nint service, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription)
    { var status = AuthenticationIsAuthenticatedSubscribeImport(context, service, callback, userData, out subscription); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_authentication_is_authenticating_get")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus AuthenticationIsAuthenticatingGetImport(nint context, nint service, out nint snapshot);
    internal static CodexStatus AuthenticationIsAuthenticatingGet(nint context, nint service, out nint snapshot)
    { var status = AuthenticationIsAuthenticatingGetImport(context, service, out snapshot); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_authentication_is_authenticating_subscribe")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus AuthenticationIsAuthenticatingSubscribeImport(nint context, nint service, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription);
    internal static CodexStatus AuthenticationIsAuthenticatingSubscribe(nint context, nint service, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription)
    { var status = AuthenticationIsAuthenticatingSubscribeImport(context, service, callback, userData, out subscription); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_authentication_state_value")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus AuthenticationStateValueImport(nint context, nint snapshot, out nint state);
    internal static CodexStatus AuthenticationStateValue(nint context, nint snapshot, out nint state)
    { var status = AuthenticationStateValueImport(context, snapshot, out state); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_state_boolean_value")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus StateBooleanValueImport(nint context, nint snapshot, out int value);
    internal static CodexStatus StateBooleanValue(nint context, nint snapshot, out int value)
    { var status = StateBooleanValueImport(context, snapshot, out value); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_integration_authorization_state_get")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus IntegrationAuthorizationStateGetImport(nint context, nint service, out nint snapshot);
    internal static CodexStatus IntegrationAuthorizationStateGet(nint context, nint service, out nint snapshot)
    { var status = IntegrationAuthorizationStateGetImport(context, service, out snapshot); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_integration_authorization_state_subscribe")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus IntegrationAuthorizationStateSubscribeImport(nint context, nint service, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription);
    internal static CodexStatus IntegrationAuthorizationStateSubscribe(nint context, nint service, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription)
    { var status = IntegrationAuthorizationStateSubscribeImport(context, service, callback, userData, out subscription); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_integration_authorization_active_get")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus IntegrationAuthorizationActiveGetImport(nint context, nint service, out nint snapshot);
    internal static CodexStatus IntegrationAuthorizationActiveGet(nint context, nint service, out nint snapshot)
    { var status = IntegrationAuthorizationActiveGetImport(context, service, out snapshot); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_integration_authorization_active_subscribe")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus IntegrationAuthorizationActiveSubscribeImport(nint context, nint service, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription);
    internal static CodexStatus IntegrationAuthorizationActiveSubscribe(nint context, nint service, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription)
    { var status = IntegrationAuthorizationActiveSubscribeImport(context, service, callback, userData, out subscription); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_integration_authorization_is_authorizing_get")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus IntegrationAuthorizationIsAuthorizingGetImport(nint context, nint service, out nint snapshot);
    internal static CodexStatus IntegrationAuthorizationIsAuthorizingGet(nint context, nint service, out nint snapshot)
    { var status = IntegrationAuthorizationIsAuthorizingGetImport(context, service, out snapshot); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_integration_authorization_is_authorizing_subscribe")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus IntegrationAuthorizationIsAuthorizingSubscribeImport(nint context, nint service, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription);
    internal static CodexStatus IntegrationAuthorizationIsAuthorizingSubscribe(nint context, nint service, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription)
    { var status = IntegrationAuthorizationIsAuthorizingSubscribeImport(context, service, callback, userData, out subscription); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_integration_authorization_state_value")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus IntegrationAuthorizationStateValueImport(nint context, nint snapshot, out nint state);
    internal static CodexStatus IntegrationAuthorizationStateValue(nint context, nint snapshot, out nint state)
    { var status = IntegrationAuthorizationStateValueImport(context, snapshot, out state); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_integration_authorization_active_has_value")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus IntegrationAuthorizationActiveHasValueImport(nint context, nint snapshot, out int value);
    internal static CodexStatus IntegrationAuthorizationActiveHasValue(nint context, nint snapshot, out int value)
    { var status = IntegrationAuthorizationActiveHasValueImport(context, snapshot, out value); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_integration_authorization_active_value")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus IntegrationAuthorizationActiveValueImport(nint context, nint snapshot, out nint value);
    internal static CodexStatus IntegrationAuthorizationActiveValue(nint context, nint snapshot, out nint value)
    { var status = IntegrationAuthorizationActiveValueImport(context, snapshot, out value); RecordExactCall(); return status; }

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_interactions_state_get")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus InteractionsStateGetImport(nint context, nint service, out nint snapshot);
    internal static CodexStatus InteractionsStateGet(nint context, nint service, out nint snapshot)
    { var status = InteractionsStateGetImport(context, service, out snapshot); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_interactions_state_subscribe")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus InteractionsStateSubscribeImport(nint context, nint service, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription);
    internal static CodexStatus InteractionsStateSubscribe(nint context, nint service, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription)
    { var status = InteractionsStateSubscribeImport(context, service, callback, userData, out subscription); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_interactions_approvals_get")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus InteractionsApprovalsGetImport(nint context, nint service, out nint snapshot);
    internal static CodexStatus InteractionsApprovalsGet(nint context, nint service, out nint snapshot)
    { var status = InteractionsApprovalsGetImport(context, service, out snapshot); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_interactions_approvals_subscribe")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus InteractionsApprovalsSubscribeImport(nint context, nint service, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription);
    internal static CodexStatus InteractionsApprovalsSubscribe(nint context, nint service, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription)
    { var status = InteractionsApprovalsSubscribeImport(context, service, callback, userData, out subscription); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_interactions_elicitations_get")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus InteractionsElicitationsGetImport(nint context, nint service, out nint snapshot);
    internal static CodexStatus InteractionsElicitationsGet(nint context, nint service, out nint snapshot)
    { var status = InteractionsElicitationsGetImport(context, service, out snapshot); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_interactions_elicitations_subscribe")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus InteractionsElicitationsSubscribeImport(nint context, nint service, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription);
    internal static CodexStatus InteractionsElicitationsSubscribe(nint context, nint service, delegate* unmanaged[Cdecl]<nint, nint, CodexStatus, nint, int, nint, void> callback, nint userData, out nint subscription)
    { var status = InteractionsElicitationsSubscribeImport(context, service, callback, userData, out subscription); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_interactions_state_value")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus InteractionsStateValueImport(nint context, nint snapshot, out nint state);
    internal static CodexStatus InteractionsStateValue(nint context, nint snapshot, out nint state)
    { var status = InteractionsStateValueImport(context, snapshot, out state); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_interactions_approvals_count")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus InteractionsApprovalsCountImport(nint context, nint snapshot, out nuint count);
    internal static CodexStatus InteractionsApprovalsCount(nint context, nint snapshot, out nuint count)
    { var status = InteractionsApprovalsCountImport(context, snapshot, out count); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_interactions_approvals_at")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus InteractionsApprovalsAtImport(nint context, nint snapshot, nuint index, out nint value);
    internal static CodexStatus InteractionsApprovalsAt(nint context, nint snapshot, nuint index, out nint value)
    { var status = InteractionsApprovalsAtImport(context, snapshot, index, out value); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_interactions_elicitations_count")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus InteractionsElicitationsCountImport(nint context, nint snapshot, out nuint count);
    internal static CodexStatus InteractionsElicitationsCount(nint context, nint snapshot, out nuint count)
    { var status = InteractionsElicitationsCountImport(context, snapshot, out count); RecordExactCall(); return status; }
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_interactions_elicitations_at")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    private static partial CodexStatus InteractionsElicitationsAtImport(nint context, nint snapshot, nuint index, out nint value);
    internal static CodexStatus InteractionsElicitationsAt(nint context, nint snapshot, nuint index, out nint value)
    { var status = InteractionsElicitationsAtImport(context, snapshot, index, out value); RecordExactCall(); return status; }
}
